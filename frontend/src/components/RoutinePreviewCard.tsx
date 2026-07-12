import { useState } from "react";
import { api, Proposal, ProposedSet } from "../api";
import { fromUnit, round1, toUnit, useUnit } from "../units";

// Never allow em/en dashes into notes (hard user preference). Strip on input so the
// field never even displays one; the backend also strips at push time as a backstop.
const noDash = (s: string) => s.replace(/[—–]/g, "-");

const numOrUndef = (v: string): number | undefined => {
  const n = parseFloat(v);
  return v.trim() === "" || Number.isNaN(n) ? undefined : n;
};
const intOrUndef = (v: string): number | undefined => {
  const n = parseInt(v, 10);
  return v.trim() === "" || Number.isNaN(n) ? undefined : n;
};

interface EditExercise {
  name: string;
  rest_seconds?: number;
  notes: string;
  sets: ProposedSet[];
}

// Renders a proposed routine as a preview. Notes and set values are editable here before
// pushing. Nothing reaches Hevy until the user clicks Approve & Push. `badge`/`rationale`
// are used by the weekly review to frame a change ("Updates: Legs 1" + why).
export function RoutinePreviewCard({
  proposal,
  badge,
  rationale,
}: {
  proposal: Proposal;
  badge?: string;
  rationale?: string;
}) {
  const { unit } = useUnit();
  const [status, setStatus] = useState<string>(proposal.status ?? "pending");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  // True once the user changes any set/rep from the coach's proposal.
  const [setsEdited, setSetsEdited] = useState(false);

  const [routineNotes, setRoutineNotes] = useState(noDash(proposal.notes ?? ""));
  const [folder, setFolder] = useState(noDash(proposal.folder ?? ""));
  const [exercises, setExercises] = useState<EditExercise[]>(() =>
    proposal.exercises.map((e) => ({
      name: e.name,
      rest_seconds: e.rest_seconds,
      notes: noDash(e.notes ?? ""),
      sets: e.sets.map((s) => ({ type: s.type ?? "normal", weight_kg: s.weight_kg, reps: s.reps })),
    })),
  );

  const editable = status !== "pushed";

  function buildPayload() {
    return {
      title: proposal.title,
      notes: routineNotes.trim() || undefined,
      folder: folder.trim() || undefined,
      exercises: exercises.map((e) => ({
        name: e.name,
        rest_seconds: e.rest_seconds,
        notes: e.notes.trim() || undefined,
        sets: e.sets.map((s) => ({ type: s.type, weight_kg: s.weight_kg, reps: s.reps })),
      })),
    };
  }

  function patchExercise(ei: number, fn: (e: EditExercise) => EditExercise) {
    setSaved(false);
    setExercises((prev) => prev.map((e, i) => (i === ei ? fn(e) : e)));
  }
  const setExNote = (ei: number, v: string) => patchExercise(ei, (e) => ({ ...e, notes: noDash(v) }));
  function updateSet(ei: number, si: number, patch: Partial<ProposedSet>) {
    setSetsEdited(true);
    patchExercise(ei, (e) => ({ ...e, sets: e.sets.map((s, j) => (j === si ? { ...s, ...patch } : s)) }));
  }
  function addSet(ei: number) {
    setSetsEdited(true);
    patchExercise(ei, (e) => ({ ...e, sets: [...e.sets, { ...(e.sets[e.sets.length - 1] ?? { type: "normal" }) }] }));
  }
  function removeSet(ei: number, si: number) {
    setSetsEdited(true);
    patchExercise(ei, (e) => ({ ...e, sets: e.sets.filter((_, j) => j !== si) }));
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
      {badge && <div className="change-badge">{badge}</div>}
      <h3>{proposal.title}</h3>
      {rationale && <div className="change-rationale">{rationale}</div>}

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

      {/* Folder only applies to new routines; Hevy won't move an existing one on update. */}
      {!badge && (
        <>
          <label className="ex-sub">Folder (groups routines in Hevy)</label>
          <input
            className="note-edit"
            value={folder}
            disabled={!editable}
            placeholder="e.g. PPL (leave blank for My Routines)"
            onChange={(e) => {
              setSaved(false);
              setFolder(noDash(e.target.value));
            }}
          />
        </>
      )}

      {exercises.map((ex, i) => (
        <div key={i}>
          <div className="ex-name">{ex.name}</div>
          <div className="ex-sub">{ex.rest_seconds != null ? `${ex.rest_seconds}s rest` : "rest: default"}</div>
          <input
            className="note-edit"
            value={ex.notes}
            disabled={!editable}
            placeholder="exercise note (cue, tempo, load)…"
            onChange={(e) => setExNote(i, e.target.value)}
          />
          <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Set</th>
                <th>Type</th>
                <th>Weight ({unit})</th>
                <th>Reps</th>
                {editable && <th></th>}
              </tr>
            </thead>
            <tbody>
              {ex.sets.map((s, j) => (
                <tr key={j}>
                  <td>{j + 1}</td>
                  <td>
                    {editable ? (
                      <select
                        className="set-type"
                        value={s.type}
                        onChange={(e) => updateSet(i, j, { type: e.target.value })}
                      >
                        <option value="normal">normal</option>
                        <option value="warmup">warmup</option>
                        <option value="failure">failure</option>
                        <option value="dropset">dropset</option>
                      </select>
                    ) : (
                      s.type
                    )}
                  </td>
                  <td>
                    {editable ? (
                      <input
                        className="set-input"
                        type="number"
                        step="0.5"
                        value={s.weight_kg != null ? round1(toUnit(s.weight_kg, unit)) : ""}
                        placeholder="-"
                        onChange={(e) => {
                          const v = numOrUndef(e.target.value);
                          updateSet(i, j, { weight_kg: v == null ? undefined : fromUnit(v, unit) });
                        }}
                      />
                    ) : s.weight_kg != null ? (
                      round1(toUnit(s.weight_kg, unit))
                    ) : (
                      "-"
                    )}
                  </td>
                  <td>
                    {editable ? (
                      <input
                        className="set-input reps"
                        type="number"
                        step="1"
                        value={s.reps ?? ""}
                        placeholder="-"
                        onChange={(e) => updateSet(i, j, { reps: intOrUndef(e.target.value) })}
                      />
                    ) : (
                      s.reps ?? "-"
                    )}
                  </td>
                  {editable && (
                    <td>
                      <button className="set-remove" title="remove set" onClick={() => removeSet(i, j)}>
                        ×
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          {editable && (
            <button className="btn ghost add-set" onClick={() => addSet(i)}>
              + set
            </button>
          )}
        </div>
      ))}

      {editable && setsEdited && (
        <div className="edit-warn">
          ⚠ You've changed sets or reps from the coach's plan. These edits may not reflect the
          intended progression or goals. Ask the coach in chat if you want them reworked to fit.
        </div>
      )}

      <div className="card-actions">
        {editable ? (
          <>
            <button className="btn approve" onClick={approve} disabled={busy}>
              {busy ? "Working…" : "Approve & Push to Hevy"}
            </button>
            <button className="btn ghost" onClick={save} disabled={busy}>
              Save changes
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
