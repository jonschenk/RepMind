import { useState } from "react";
import { api, Proposal } from "../api";

// Never allow em/en dashes into notes (hard user preference). Strip on input so the
// field never even displays one; the backend also strips at push time as a backstop.
const noDash = (s: string) => s.replace(/[—–]/g, "-");

// Renders a proposed routine as a preview. Routine + per-exercise notes are editable
// here before pushing. Nothing reaches Hevy until the user clicks Approve & Push.
export function RoutinePreviewCard({ proposal }: { proposal: Proposal }) {
  const [status, setStatus] = useState<string>(proposal.status ?? "pending");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const [routineNotes, setRoutineNotes] = useState(noDash(proposal.notes ?? ""));
  const [exNotes, setExNotes] = useState<string[]>(
    proposal.exercises.map((e) => noDash(e.notes ?? "")),
  );

  const editable = status !== "pushed";

  function buildPayload() {
    return {
      title: proposal.title,
      notes: routineNotes.trim() || undefined,
      exercises: proposal.exercises.map((e, i) => ({
        name: e.name,
        rest_seconds: e.rest_seconds,
        notes: exNotes[i].trim() || undefined,
        sets: e.sets,
      })),
    };
  }

  function setExNote(i: number, v: string) {
    setSaved(false);
    setExNotes((prev) => prev.map((n, j) => (j === i ? noDash(v) : n)));
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.updateProposal(proposal.id, buildPayload());
      setSaved(true);
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.approveProposal(proposal.id, buildPayload());
      setStatus("pushed");
      setResult(
        r.dry_run
          ? `DRY RUN - resolved payload logged server-side (fake id ${r.hevy_routine_id}). Nothing pushed.`
          : `Pushed to Hevy (routine id ${r.hevy_routine_id}).`,
      );
    } catch (e: any) {
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

      <label className="ex-sub">Routine notes</label>
      <textarea
        className="note-edit"
        rows={2}
        value={routineNotes}
        disabled={!editable}
        placeholder="Add a note for this routine…"
        onChange={(e) => {
          setSaved(false);
          setRoutineNotes(noDash(e.target.value));
        }}
      />

      {proposal.exercises.map((ex, i) => (
        <div key={i}>
          <div className="ex-name">{ex.name}</div>
          <div className="ex-sub">
            {ex.rest_seconds != null ? `${ex.rest_seconds}s rest` : "rest: default"}
          </div>
          <input
            className="note-edit"
            value={exNotes[i]}
            disabled={!editable}
            placeholder="exercise note (cue, tempo, load)…"
            onChange={(e) => setExNote(i, e.target.value)}
          />
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
        {editable ? (
          <>
            <button className="btn approve" onClick={approve} disabled={busy}>
              {busy ? "Working…" : "Approve & Push to Hevy"}
            </button>
            <button className="btn ghost" onClick={save} disabled={busy}>
              Save notes
            </button>
            {saved && <span className="result-ok">✓ saved</span>}
            <span className="muted" style={{ fontSize: 12 }}>
              Nothing is sent until you approve.
            </span>
          </>
        ) : (
          <span className="result-ok">✓ {result}</span>
        )}
      </div>
      {error && <div className="result-err">{error}</div>}
    </div>
  );
}
