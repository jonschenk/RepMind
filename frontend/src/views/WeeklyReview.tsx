import { useEffect, useState } from "react";
import { api, Proposal, WeeklyProposal, WeeklyReviewData } from "../api";
import { RoutinePreviewCard } from "../components/RoutinePreviewCard";
import { renderLite } from "../renderLite";

function statusClass(s: string): string {
  if (s === "under") return "warn";
  if (s === "over") return "dry";
  if (s === "in_range") return "good";
  return "";
}

function asProposal(p: WeeklyProposal): Proposal {
  return {
    id: p.id,
    title: p.payload.title,
    notes: p.payload.notes,
    exercises: p.payload.exercises,
    status: p.status,
  };
}

export function WeeklyReview({ anthropicReady }: { anthropicReady: boolean }) {
  const [data, setData] = useState<WeeklyReviewData | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    try {
      await api.generateWeekly();
      await load();
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

      {generating && <div className="muted">Analyzing your week and drafting updates…</div>}

      {data?.exists && (
        <>
          <div className="panel">
            <div className="summary">{renderLite(data.narrative ?? "")}</div>
          </div>

          {s && (
            <div className="grid2">
              <div className="panel">
                <h2>Volume vs targets (hard sets)</h2>
                {s.volume.map((v) => (
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
                <h2>PRs this week</h2>
                {s.prs.length === 0 && <div className="muted">No est-1RM PRs this week.</div>}
                {s.prs.slice(0, 6).map((p) => (
                  <div className="stalled-row" key={p.exercise}>
                    <span className="name">{p.exercise}</span>
                    <span className="pill good">
                      {p.est_1rm}kg (+{p.gain})
                    </span>
                  </div>
                ))}

                <h2 style={{ marginTop: 16 }}>Heavy-lane stalls</h2>
                {s.heavy_lane_stalls.length === 0 && <div className="muted">Nothing stalling.</div>}
                {s.heavy_lane_stalls.slice(0, 5).map((x) => (
                  <div className="stalled-row" key={x.exercise}>
                    <span className="name">{x.exercise}</span>
                    <span className="pill warn">{x.sessions_since_pr} since PR</span>
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

          {data.proposals && data.proposals.length > 0 && (
            <div className="panel">
              <h2>Proposed routine updates</h2>
              <div className="muted" style={{ marginBottom: 8 }}>
                Review each, edit if you like, and approve to push. Nothing changes in Hevy until you approve.
              </div>
              {data.proposals.map((p) => (
                <RoutinePreviewCard
                  key={p.id}
                  proposal={asProposal(p)}
                  badge={(p.kind === "update" ? "UPDATE · " : "NEW · ") + (p.diff?.changes_summary ?? "")}
                  rationale={p.diff?.rationale}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
