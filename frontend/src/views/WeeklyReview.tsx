import { useEffect, useState } from "react";
import { api, generateWeeklyStream, Proposal, WeeklyProposal, WeeklyReviewData } from "../api";
import { RoutinePreviewCard } from "../components/RoutinePreviewCard";
import { renderLite } from "../renderLite";
import { fmtWeight, round1, toUnit, useUnit } from "../units";

function statusClass(s: string): string {
  if (s === "under") return "warn";
  if (s === "over") return "dry";
  if (s === "in_range") return "good";
  return "";
}

// The weekly review is scheduled Monday 06:00 (see main.py). Compute ms until the next one
// in the viewer's local time.
function msUntilNextReview(now: Date): number {
  const target = new Date(now);
  target.setHours(6, 0, 0, 0);
  let daysToMon = (1 - target.getDay() + 7) % 7; // 0 = today is Monday
  if (daysToMon === 0 && now.getTime() >= target.getTime()) daysToMon = 7; // past 6am Mon
  target.setDate(target.getDate() + daysToMon);
  return target.getTime() - now.getTime();
}

function fmtCountdown(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function NextCheckIn() {
  const [ms, setMs] = useState(() => msUntilNextReview(new Date()));
  useEffect(() => {
    const id = setInterval(() => setMs(msUntilNextReview(new Date())), 60_000);
    return () => clearInterval(id);
  }, []);
  return (
    <span
      className="pill"
      title="The review generates automatically when you finish your split. Monday 6am is a backup if a cycle hasn't completed."
    >
      Auto-review when you finish your split · backup Mon 6am (in {fmtCountdown(ms)})
    </span>
  );
}

function asProposal(p: WeeklyProposal): Proposal {
  return {
    id: p.id,
    title: p.payload.title,
    notes: p.payload.notes,
    folder: p.payload.folder,
    exercises: p.payload.exercises,
    status: p.status,
  };
}

export function WeeklyReview({ anthropicReady }: { anthropicReady: boolean }) {
  const { unit } = useUnit();
  const [data, setData] = useState<WeeklyReviewData | null>(null);
  const [generating, setGenerating] = useState(false);
  const [steps, setSteps] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState<Set<number>>(new Set());

  async function load() {
    try {
      setData(await api.weeklyReview());
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function generate() {
    setGenerating(true);
    setError(null);
    setSteps([]);
    try {
      await generateWeeklyStream((ev) => {
        if (ev.type === "step") setSteps((prev) => [...prev, ev.message]);
        else if (ev.type === "error") setError(ev.message);
      });
      await load(); // pull the freshly generated review (assembled shape with proposals)
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setGenerating(false);
    }
  }

  const s = data?.signals;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <h2 style={{ margin: 0, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.05em", fontSize: 15 }}>
          Weekly Review
        </h2>
        {data?.period && (
          <span className="muted" style={{ fontSize: 13 }}>
            {data.period.start.slice(0, 10)} to {data.period.end.slice(0, 10)}
          </span>
        )}
        <div className="spacer" />
        <NextCheckIn />
        <button className="btn" onClick={generate} disabled={generating}>
          {generating ? "Generating…" : "Generate now"}
        </button>
      </div>

      {error && <div className="panel result-err">{error}</div>}

      {!data?.exists && !generating && (
        <div className="banner">
          No weekly review yet. Click <b>Generate now</b> to build one from your last week of
          training{anthropicReady ? "." : " (needs ANTHROPIC_API_KEY)."}
        </div>
      )}

      {generating && (
        <div className="panel">
          <div className="name" style={{ marginBottom: 10 }}>Building your weekly review…</div>
          {steps.map((m, i) => {
            const last = i === steps.length - 1;
            return (
              <div key={i} className="gen-step">
                <span className={`gen-dot ${last ? "active" : "done"}`} />
                <span className={last ? "" : "muted"}>{m}</span>
              </div>
            );
          })}
        </div>
      )}

      {data?.exists && !generating && (
        <>
          <div className="panel">
            <div className="summary">{renderLite(data.narrative ?? "")}</div>
          </div>

          {s && (
            <div className="grid2">
              <div className="panel">
                <h2>Volume vs targets (hard sets)</h2>
                {s.muscle_volume.map((v) => (
                  <div className={`stalled-row ${v.priority ? "priority-row" : ""}`} key={v.muscle}>
                    <div>
                      <div className="name">{v.muscle}</div>
                      <div className="meta">
                        {v.sets} sets{v.mav ? ` · target ${v.mev}-${v.mav}` : ""}
                      </div>
                    </div>
                    {v.status !== "no_landmark" && <span className={`pill ${statusClass(v.status)}`}>{v.status.replace("_", " ")}</span>}
                  </div>
                ))}
              </div>

              <div className="panel">
                <h2>Needs attention</h2>
                {s.progression.filter((p) => p.verdict === "regressing" || p.verdict === "holding").length === 0 && (
                  <div className="muted">Everything is progressing.</div>
                )}
                {s.progression
                  .filter((p) => p.verdict === "regressing" || p.verdict === "holding")
                  .slice(0, 6)
                  .map((p) => (
                    <div className="stalled-row" key={p.exercise}>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div className="name">{p.exercise}</div>
                        <div className="meta">{p.reason}</div>
                      </div>
                      <span className={`pill ${p.verdict === "regressing" ? "warn" : ""}`}>{p.verdict}</span>
                    </div>
                  ))}

                <h2 style={{ marginTop: 16 }}>Est-1RM PRs</h2>
                {s.est_1rm_prs.length === 0 && <div className="muted">None this window (expected for hypertrophy work).</div>}
                {s.est_1rm_prs.slice(0, 5).map((p) => (
                  <div className="stalled-row" key={p.exercise}>
                    <span className="name">{p.exercise}</span>
                    <span className="pill good">
                      {fmtWeight(p.est_1rm, unit)} (+{round1(toUnit(p.gain, unit))})
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {s && s.notes.length > 0 && (
            <div className="panel">
              <h2>From your notes</h2>
              {s.notes.map((n, i) => (
                <div className="note-theme" key={i}>
                  <span className={`pill ${n.category === "pain" ? "warn" : ""}`}>{n.category}</span>
                  <span className="muted">{n.exercise ? `${n.exercise}: ` : ""}</span>
                  <span>{n.insight}</span>
                </div>
              ))}
            </div>
          )}

          {data.proposals && data.proposals.filter((p) => !dismissed.has(p.id)).length > 0 && (
            <div className="panel">
              <h2>Proposed routine updates</h2>
              <div className="muted" style={{ marginBottom: 8 }}>
                Review each, edit if you like, and approve to push. Nothing changes in Hevy until you approve. Deny to clear one you don't want.
              </div>
              {data.proposals
                .filter((p) => !dismissed.has(p.id))
                .map((p) => (
                  <RoutinePreviewCard
                    key={p.id}
                    proposal={asProposal(p)}
                    badge={(p.kind === "update" ? "UPDATE · " : "NEW · ") + (p.diff?.changes_summary ?? "")}
                    rationale={p.diff?.rationale}
                    onDismiss={() => setDismissed((prev) => new Set(prev).add(p.id))}
                  />
                ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
