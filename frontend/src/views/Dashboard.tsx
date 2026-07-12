import { useEffect, useState } from "react";
import { api, DashboardData, Health } from "../api";
import { StalledLiftCard } from "../components/StalledLiftCard";
import { SummaryCard } from "../components/SummaryCard";
import { TrendChart } from "../components/TrendChart";
import { VolumeChart } from "../components/VolumeChart";

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
        <StalledLiftCard lifts={data.stalled_lifts} />
        <div className="panel">
          <h2>Tracked lifts</h2>
          <div className="muted" style={{ marginBottom: 8 }}>
            {data.exercises.length} exercises with logged working sets.
          </div>
          {data.exercises.slice(0, 8).map((e) => (
            <div className="stalled-row" key={e.exercise}>
              <span className="name">{e.exercise}</span>
              <span className="pill">{e.sessions} sessions</span>
            </div>
          ))}
        </div>
      </div>
      <TrendChart exercises={data.exercises} />
      <VolumeChart rows={data.weekly_volume} />
    </div>
  );
}
