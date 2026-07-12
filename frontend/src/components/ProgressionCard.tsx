import { ProgressionItem, Verdict } from "../api";

const VERDICT_PILL: Record<Verdict, string> = {
  regressing: "warn",
  holding: "",
  progressing: "good",
  new: "",
};

// A compact strength / hypertrophy / endurance rep-range bar for one lift.
function RepMixBar({ mix }: { mix: ProgressionItem["rep_mix"] }) {
  const seg = [
    { pct: mix.strength, color: "var(--accent-2)", label: "strength" },
    { pct: mix.hypertrophy, color: "var(--good)", label: "hypertrophy" },
    { pct: mix.endurance, color: "var(--warn)", label: "endurance" },
  ].filter((s) => s.pct > 0);
  return (
    <div className="repmix" title={seg.map((s) => `${s.label} ${s.pct}%`).join(" · ")}>
      {seg.map((s, i) => (
        <div key={i} style={{ width: `${s.pct}%`, background: s.color }} />
      ))}
    </div>
  );
}

export function ProgressionCard({ items, bare }: { items: ProgressionItem[]; bare?: boolean }) {
  const shown = items.filter((i) => i.verdict !== "new").slice(0, 12);
  const body = (
    <>
      {shown.length === 0 && <div className="muted">Not enough history yet.</div>}
      {shown.map((p) => (
        <div className="stalled-row" key={p.exercise}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="name">{p.exercise}</div>
            <div className="meta">{p.reason}</div>
            <RepMixBar mix={p.rep_mix} />
          </div>
          <span className={`pill ${VERDICT_PILL[p.verdict]}`}>{p.verdict}</span>
        </div>
      ))}
    </>
  );
  if (bare) return body;
  return (
    <div className="panel">
      <h2>Progression (load · reps · volume)</h2>
      {body}
    </div>
  );
}
