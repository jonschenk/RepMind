import { StalledLift } from "../api";

export function StalledLiftCard({ lifts }: { lifts: StalledLift[] }) {
  return (
    <div className="panel">
      <h2>Stalled lifts</h2>
      {lifts.length === 0 && <div className="muted">No stalled lifts — everything is trending.</div>}
      {lifts.map((l) => (
        <div className="stalled-row" key={l.exercise}>
          <div>
            <div className="name">{l.exercise}</div>
            <div className="meta">
              best est. 1RM {l.best_est_1rm} kg · now {l.current_est_1rm} kg
            </div>
          </div>
          <span className="pill warn">{l.sessions_since_pr} sessions since PR</span>
        </div>
      ))}
    </div>
  );
}
