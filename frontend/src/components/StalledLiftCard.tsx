import { StalledLift } from "../api";
import { fmtWeight, useUnit } from "../units";

export function StalledLiftCard({ lifts }: { lifts: StalledLift[] }) {
  const { unit } = useUnit();
  return (
    <div className="panel">
      <h2>Stalled lifts</h2>
      {lifts.length === 0 && <div className="muted">No stalled lifts — everything is trending.</div>}
      {lifts.map((l) => (
        <div className="stalled-row" key={l.exercise}>
          <div>
            <div className="name">{l.exercise}</div>
            <div className="meta">
              best est. 1RM {fmtWeight(l.best_est_1rm, unit)} · now {fmtWeight(l.current_est_1rm, unit)}
            </div>
          </div>
          <span className="pill warn">{l.sessions_since_pr} sessions since PR</span>
        </div>
      ))}
    </div>
  );
}
