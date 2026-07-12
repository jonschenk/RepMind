import { useState } from "react";
import { api, Proposal } from "../api";

// Renders a proposed routine as a structured preview. Nothing reaches Hevy until the
// user clicks Approve & Push.
export function RoutinePreviewCard({ proposal }: { proposal: Proposal }) {
  const [status, setStatus] = useState<string>(proposal.status ?? "pending");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function approve() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.approveProposal(proposal.id);
      setStatus("pushed");
      setResult(
        r.dry_run
          ? `DRY RUN — resolved payload logged server-side (fake id ${r.hevy_routine_id}). Nothing pushed.`
          : `Pushed to Hevy (routine id ${r.hevy_routine_id}).`,
      );
    } catch (e: any) {
      // Backend returns 422 with unresolved exercise names when it can't map them.
      let msg = String(e.message ?? e);
      const m = msg.match(/\{.*\}/s);
      if (m) {
        try {
          const detail = JSON.parse(m[0]).detail;
          if (detail?.unresolved) msg = `Couldn't map: ${detail.unresolved.join(", ")}. Nothing pushed.`;
          else if (detail?.message) msg = detail.message;
        } catch {}
      }
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="routine-card">
      <h3>{proposal.title}</h3>
      {proposal.notes && <div className="ex-sub">{proposal.notes}</div>}

      {proposal.exercises.map((ex, i) => (
        <div key={i}>
          <div className="ex-name">{ex.name}</div>
          <div className="ex-sub">
            {ex.rest_seconds != null ? `${ex.rest_seconds}s rest` : "rest: default"}
            {ex.notes ? ` · ${ex.notes}` : ""}
          </div>
          <table>
            <thead>
              <tr>
                <th>Set</th>
                <th>Type</th>
                <th>Weight (kg)</th>
                <th>Reps</th>
              </tr>
            </thead>
            <tbody>
              {ex.sets.map((s, j) => (
                <tr key={j}>
                  <td>{j + 1}</td>
                  <td>{s.type}</td>
                  <td>{s.weight_kg ?? "—"}</td>
                  <td>{s.reps ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      <div className="card-actions">
        {status !== "pushed" ? (
          <button className="btn approve" onClick={approve} disabled={busy}>
            {busy ? "Pushing…" : "Approve & Push to Hevy"}
          </button>
        ) : (
          <span className="result-ok">✓ {result}</span>
        )}
        {status !== "pushed" && <span className="muted" style={{ fontSize: 12 }}>Nothing is sent until you approve.</span>}
      </div>
      {error && <div className="result-err">{error}</div>}
    </div>
  );
}
