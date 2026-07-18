import { useRef, useState } from "react";
import { Proposal, streamChat } from "../api";
import { RoutinePreviewCard } from "../components/RoutinePreviewCard";
import { renderLite } from "../renderLite";

interface Msg {
  role: "user" | "assistant";
  content: string;
  tools: string[];
  proposals: Proposal[];
}

const SUGGESTIONS = [
  "How has my bench progressed over the last few months?",
  "What's stalling and what should I change?",
  "Generate my next push day, prioritizing side and rear delts.",
];

// Friendly labels for the live "working" indicator.
const TOOL_LABEL: Record<string, string> = {
  get_progression: "Reviewing your progression",
  get_lift_progression: "Checking a lift in detail",
  get_exercise_trend: "Pulling a lift's trend",
  get_workout_history: "Reading recent workouts",
  search_exercises: "Looking up exercises",
  list_routines: "Reviewing your whole program",
  get_routine: "Reading a routine in full",
  propose_routine: "Drafting the routine",
};

export function Chat({ anthropicReady }: { anthropicReady: boolean }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Deliberately do NOT replay past history into the view: each browser session starts as a
  // clean slate. The coach still remembers, though - the backend feeds the recent stored
  // turns to the model as context on every message, so memory is preserved server-side.

  function scrollDown() {
    requestAnimationFrame(() => {
      const el = scrollRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }

  // Remove a denied proposal card from its message (backend already marked it dismissed).
  function dismissProposal(msgIdx: number, proposalId: number) {
    setMessages((prev) =>
      prev.map((m, idx) =>
        idx === msgIdx ? { ...m, proposals: m.proposals.filter((p) => p.id !== proposalId) } : m,
      ),
    );
  }

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setMessages((prev) => [
      ...prev,
      { role: "user", content: text, tools: [], proposals: [] },
      { role: "assistant", content: "", tools: [], proposals: [] },
    ]);
    setInput("");
    setBusy(true);
    setStatus("Thinking");
    scrollDown();

    const patchAssistant = (fn: (m: Msg) => Msg) =>
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = fn(next[next.length - 1]);
        return next;
      });

    try {
      await streamChat(text, (e) => {
        if (e.type === "text") {
          setStatus(null);
          patchAssistant((m) => ({ ...m, content: m.content + e.text }));
        } else if (e.type === "tool_use") {
          setStatus(TOOL_LABEL[e.name] ?? "Working");
          patchAssistant((m) => ({ ...m, tools: [...m.tools, e.name] }));
        } else if (e.type === "proposal") {
          setStatus("Drafting the routine");
          patchAssistant((m) => ({ ...m, proposals: [...m.proposals, e.proposal] }));
        } else if (e.type === "error") {
          patchAssistant((m) => ({ ...m, content: m.content + `\n\n⚠️ ${e.message}` }));
        }
        scrollDown();
      });
    } catch (err: any) {
      patchAssistant((m) => ({ ...m, content: m.content + `\n\n⚠️ ${err.message ?? err}` }));
    } finally {
      setBusy(false);
      setStatus(null);
      scrollDown();
    }
  }

  return (
    <div className="chat-wrap">
      {!anthropicReady && (
        <div className="banner">ANTHROPIC_API_KEY is not set — chat is disabled. Add it to .env and restart.</div>
      )}
      <div className="messages" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="panel">
            <h2>Ask your coach</h2>
            <div className="muted" style={{ marginBottom: 10 }}>
              It reads your real Hevy history and remembers past chats. Routines are proposed, never pushed without your approval.
            </div>
            {SUGGESTIONS.map((s) => (
              <button key={s} className="btn ghost" style={{ display: "block", marginBottom: 8, width: "100%", textAlign: "left" }} onClick={() => send(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => {
          const isLast = i === messages.length - 1;
          return (
            <div key={i} className={`msg ${m.role}`}>
              {m.role === "assistant" ? (
                m.content && <div className="msg-md">{renderLite(m.content)}</div>
              ) : (
                m.content
              )}
              {m.role === "assistant" && isLast && busy && (
                <div className="thinking">
                  {status ?? "Thinking"}
                  <span className="dots"><i /><i /><i /></span>
                </div>
              )}
              {m.tools.length > 0 && (
                <div className="toolchips">
                  {m.tools.map((t, j) => (
                    <span key={j} className="toolchip">🔧 {TOOL_LABEL[t] ?? t}</span>
                  ))}
                </div>
              )}
              {m.proposals.map((p) => (
                <RoutinePreviewCard
                  key={p.id}
                  proposal={p}
                  badge={p.kind === "update" ? "UPDATE" : undefined}
                  rationale={p.change_summary}
                  onDismiss={() => dismissProposal(i, p.id)}
                />
              ))}
            </div>
          );
        })}
      </div>

      <div className="composer">
        <textarea
          value={input}
          placeholder={anthropicReady ? "Ask about your lifts, or ask for a routine…" : "Chat disabled"}
          disabled={!anthropicReady || busy}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
        />
        <button className="btn" disabled={!anthropicReady || busy} onClick={() => send(input)}>
          {busy ? "…" : "Send"}
        </button>
      </div>
    </div>
  );
}
