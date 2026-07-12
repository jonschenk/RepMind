import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { VolumeRow } from "../api";

const COLORS = ["#ff6b3d", "#4c8dff", "#3ecf8e", "#f2c14e", "#c07bff", "#5fd4d0", "#ef5f5f", "#8b9bb4"];

// Pivot [{week,muscle,volume}] into stacked-bar rows: {week, <muscle>: volume, ...}.
export function VolumeChart({ rows }: { rows: VolumeRow[] }) {
  const { data, muscles } = useMemo(() => {
    const byWeek: Record<string, any> = {};
    const muscleSet = new Set<string>();
    for (const r of rows) {
      muscleSet.add(r.muscle);
      byWeek[r.week] = byWeek[r.week] || { week: r.week };
      byWeek[r.week][r.muscle] = r.volume_kg;
    }
    const weeks = Object.keys(byWeek).sort();
    return { data: weeks.map((w) => byWeek[w]), muscles: Array.from(muscleSet).sort() };
  }, [rows]);

  return (
    <div className="panel">
      <h2>Weekly volume by muscle (kg)</h2>
      {data.length === 0 ? (
        <div className="muted">No data yet — run a sync.</div>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -10 }}>
            <CartesianGrid stroke="#2a2f3a" strokeDasharray="3 3" />
            <XAxis dataKey="week" stroke="#9aa3b2" fontSize={10} />
            <YAxis stroke="#9aa3b2" fontSize={11} />
            <Tooltip
              contentStyle={{ background: "#1e222b", border: "1px solid #2a2f3a", borderRadius: 8 }}
              labelStyle={{ color: "#9aa3b2" }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {muscles.map((m, i) => (
              <Bar key={m} dataKey={m} stackId="v" fill={COLORS[i % COLORS.length]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
