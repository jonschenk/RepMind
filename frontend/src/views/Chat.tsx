import { useRef, useState } from "react";
import { Proposal, streamChat } from "../api";
import { RoutinePreviewCard } from "../components/RoutinePreviewCard";

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

export function Chat({ anthropicReady }: { anthropicReady: boolean }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  function scrollDown() {
    requestAnimationFrame(() => {
      const el = scrollRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }

  async function send(text: string) {
    if (!text.trim() || busy) return;
    const userMsg: Msg = { role: "user", content: text, tools: [], proposals: [] };
    const history = [...messages, userMsg].map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [
      ...prev,
      userMsg,
      { role: "assistant", content: "", tools: [], proposals: [] },
    ]);
    setInput("");
    setBusy(true);
    scrollDown();

    const patchAssistant = (fn: (m: Msg) => Msg) =>
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = fn(next[next.length - 1]);
        return next;
      });

    try {
      await streamChat(history, (e) => {
        if (e.type === "text") patchAssistant((m) => ({ ...m, content: m.content + e.text }));
        else if (e.type === "tool_use") patchAssistant((m) => ({ ...m, tools: [...m.tools, e.name] }));
        else if (e.type === "proposal") patchAssistant((m) => ({ ...m, proposals: [...m.proposals, e.proposal] }));
        else if (e.type === "error") patchAssistant((m) => ({ ...m, content: m.content + `\n\n⚠️ ${e.message}` }));
        scrollDown();
      });
    } catch (err: any) {
      patchAssistant((m) => ({ ...m, content: m.content + `\n\n⚠️ ${err.message ?? err}` }));
    } finally {
      setBusy(false);
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
              It reads your real Hevy history. Routines are proposed, never pushed without your approval.
            </div>
            {SUGGESTIONS.map((s) => (
              <button key={s} className="btn ghost" style={{ display: "block", marginBottom: 8, width: "100%", textAlign: "left" }} onClick={() => send(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.content || (m.role === "assistant" && busy && i === messages.length - 1 ? "…" : "")}
            {m.tools.length > 0 && (
              <div className="toolchips">
                {m.tools.map((t, j) => (
                  <span key={j} className="toolchip">🔧 {t}</span>
                ))}
              </div>
            )}
            {m.proposals.map((p) => (
              <RoutinePreviewCard key={p.id} proposal={p} />
            ))}
          </div>
        ))}
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
