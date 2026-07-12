import { useEffect, useState } from "react";
import { api, DashboardData, Health, RepMix } from "../api";
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

export function Dashboard({ health }: { health: Health | null }) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.dashboard().then(setData).catch((e) => setError(String(e.message ?? e)));
  }, []);

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
        <BodyCard bare />
      </Collapsible>
      <Collapsible title="Weekly volume by muscle">
        <VolumeChart rows={data.weekly_volume} bare />
      </Collapsible>
    </div>
  );
}
