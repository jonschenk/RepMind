import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, TrackedExercise, TrendPoint } from "../api";
import { round1, toUnit, useUnit } from "../units";

export function TrendChart({ exercises }: { exercises: TrackedExercise[] }) {
  const [selected, setSelected] = useState<string>("");
  const [formula, setFormula] = useState<string>("epley");
  const [series, setSeries] = useState<TrendPoint[]>([]);

  useEffect(() => {
    if (!selected && exercises.length) setSelected(exercises[0].exercise);
  }, [exercises, selected]);

  useEffect(() => {
    if (!selected) return;
    api.trend(selected, formula).then((r) => setSeries(r.series)).catch(() => setSeries([]));
  }, [selected, formula]);

  const { unit } = useUnit();
  const data = series.map((p) => ({
    date: p.date ? p.date.slice(0, 10) : "",
    est_1rm: round1(toUnit(p.est_1rm, unit)),
  }));

  return (
    <div className="panel">
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 10 }}>
        <h2 style={{ margin: 0, flex: 1 }}>Estimated 1RM trend</h2>
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          {exercises.map((e) => (
            <option key={e.exercise} value={e.exercise}>
              {e.exercise} ({e.sessions})
            </option>
          ))}
        </select>
        <select value={formula} onChange={(e) => setFormula(e.target.value)}>
          <option value="epley">Epley</option>
          <option value="brzycki">Brzycki</option>
        </select>
      </div>
      {data.length === 0 ? (
        <div className="muted">No data yet — run a sync.</div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -10 }}>
            <CartesianGrid stroke="#2a2f3a" strokeDasharray="3 3" />
            <XAxis dataKey="date" stroke="#9aa3b2" fontSize={11} />
            <YAxis stroke="#9aa3b2" fontSize={11} domain={["auto", "auto"]} unit="" />
            <Tooltip
              contentStyle={{ background: "#1e222b", border: "1px solid #2a2f3a", borderRadius: 8 }}
              labelStyle={{ color: "#9aa3b2" }}
              formatter={(v: number) => [`${v} ${unit}`, "est. 1RM"]}
            />
            <Line type="monotone" dataKey="est_1rm" stroke="#ff6b3d" strokeWidth={2} dot={{ r: 2 }} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
