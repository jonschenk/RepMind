import { useEffect, useState } from "react";
import { api, ChangeEntry, DashboardData, Health, RepMix, UsageData } from "../api";
import { BodyCard } from "../components/BodyCard";
import { Collapsible } from "../components/Collapsible";
import { ProgressionCard } from "../components/ProgressionCard";
import { SummaryCard } from "../components/SummaryCard";
import { TrendChart } from "../components/TrendChart";
import { VolumeChart } from "../components/VolumeChart";

function TrainingMixPanel({ mix }: { mix: RepMix }) {
  const rows: [string, number, string][] = [
    ["Strength (1-5 reps)", mix.strength, "var(--accent-2)"],
    ["Hypertrophy (6-15)", mix.hypertrophy, "var(--good)"],
    ["Endurance (16+)", mix.endurance, "var(--warn)"],
  ];
  return (
    <div className="panel">
      <h2>Training mix</h2>
      <div className="muted" style={{ marginBottom: 10, fontSize: 13 }}>
        {mix.total_sets} working sets, by rep range.
      </div>
      {rows.map(([label, pct, color]) => (
        <div className="mix-row" key={label}>
          <span className="mix-label">{label}</span>
          <div className="mix-track">
            <div className="mix-fill" style={{ width: `${pct}%`, background: color }} />
          </div>
          <span className="mix-pct">{pct}%</span>
        </div>
      ))}
    </div>
  );
}

function UsagePanel({ usage }: { usage: UsageData }) {
  const surfaces = Object.entries(usage.month.by_surface).sort((a, b) => b[1].cost_usd - a[1].cost_usd);
  return (
    <>
      <div className="muted" style={{ marginBottom: 8, fontSize: 13 }}>
        {usage.month_label} · {usage.month_calls} Claude calls · all-time ≈ ${usage.all_time_cost_usd.toFixed(2)}
      </div>
      {surfaces.length === 0 && <div className="muted">No usage yet this month.</div>}
      {surfaces.map(([s, v]) => (
        <div className="stalled-row" key={s}>
          <span className="name" style={{ textTransform: "capitalize" }}>{s}</span>
          <span className="meta">{v.calls} calls · ${v.cost_usd.toFixed(2)}</span>
        </div>
      ))}
      <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
        Estimate from list prices (thinking counts as output); actual billing may differ.
      </div>
    </>
  );
}

function ChangeLog({ changes }: { changes: ChangeEntry[] }) {
  if (changes.length === 0) return <div className="muted">No routine changes yet.</div>;
  return (
    <>
      {changes.map((c, i) => (
        <div className="stalled-row" key={i}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="name">
              {c.routine}{" "}
              <span className="pill" style={{ marginLeft: 4 }}>{c.source}</span>{" "}
              <span className="muted" style={{ fontSize: 12 }}>{c.kind}</span>
            </div>
            <div className="meta">{c.summary}</div>
          </div>
          <span className="meta" style={{ whiteSpace: "nowrap" }}>{(c.when ?? "").slice(0, 10)}</span>
        </div>
      ))}
    </>
  );
}

export function Dashboard({ health, refreshKey }: { health: Health | null; refreshKey?: number }) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [changes, setChanges] = useState<ChangeEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Re-fetch when a sync bumps refreshKey so newly-logged workouts show without a reload.
  useEffect(() => {
    api.dashboard().then(setData).catch((e) => setError(String(e.message ?? e)));
    api.usage().then(setUsage).catch(() => {});
    api.changes().then((r) => setChanges(r.changes)).catch(() => {});
  }, [refreshKey]);

  if (error) return <div className="panel result-err">{error}</div>;
  if (!data) return <div className="muted">Loading dashboard…</div>;

  const empty = data.exercises.length === 0;

  return (
    <div>
      {empty && (
        <div className="banner">
          No workouts cached yet. Click <b>Sync now</b> above to pull your Hevy history.
        </div>
      )}
      <SummaryCard enabled={!!health?.anthropic_configured} />
      <div className="grid2">
        <TrainingMixPanel mix={data.training_mix} />
        <div className="panel">
          <h2>Most-trained lifts</h2>
          {data.exercises.slice(0, 8).map((e) => (
            <div className="stalled-row" key={e.exercise}>
              <span className="name">{e.exercise}</span>
              <span className="pill">{e.sessions} sessions</span>
            </div>
          ))}
        </div>
      </div>
      <TrendChart exercises={data.exercises} />
      <Collapsible title="Progression (load · reps · volume)">
        <ProgressionCard items={data.progression} bare />
      </Collapsible>
      <Collapsible title="Bodyweight">
        <BodyCard bare refreshKey={refreshKey} />
      </Collapsible>
      <Collapsible title="Weekly volume by muscle">
        <VolumeChart rows={data.weekly_volume} bare />
      </Collapsible>
      <Collapsible
        title={changes ? `Recent routine changes${changes.length ? ` (${changes.length})` : ""}` : "Recent routine changes"}
      >
        {changes ? <ChangeLog changes={changes} /> : <div className="muted">Loading…</div>}
      </Collapsible>
      <Collapsible
        title={usage ? `AI spend this month: ≈ $${usage.month.cost_usd.toFixed(2)}` : "AI spend this month"}
      >
        {usage ? <UsagePanel usage={usage} /> : <div className="muted">Loading…</div>}
      </Collapsible>
    </div>
  );
}
