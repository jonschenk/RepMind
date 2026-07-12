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
import { api, TrackedExercise, TrendResponse } from "../api";
import { round1, toUnit, useUnit } from "../units";

type Metric = "est_1rm" | "volume" | "top_set";
const METRIC_LABEL: Record<Metric, string> = {
  est_1rm: "Est. 1RM",
  volume: "Volume-load",
  top_set: "Top set",
};

export function TrendChart({ exercises }: { exercises: TrackedExercise[] }) {
  const { unit } = useUnit();
  const [selected, setSelected] = useState<string>("");
  const [metric, setMetric] = useState<Metric>("est_1rm");
  const [resp, setResp] = useState<TrendResponse | null>(null);

  useEffect(() => {
    if (!selected && exercises.length) setSelected(exercises[0].exercise);
  }, [exercises, selected]);

  useEffect(() => {
    if (!selected) return;
    api.trend(selected).then(setResp).catch(() => setResp(null));
  }, [selected]);

  const series = resp ? resp[metric] : [];
  // All three metrics are in kg (1RM / top-set weight, or volume-load tonnage); convert.
  const data = series.map((p) => ({
    label: p.label,
    value: p.value == null ? null : round1(toUnit(p.value, unit)),
  }));

  return (
    <div className="panel">
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 10, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, flex: 1 }}>Per-lift trend</h2>
        <div className="metric-tabs">
          {(["est_1rm", "volume", "top_set"] as Metric[]).map((m) => (
            <button key={m} className={`metric-tab ${metric === m ? "active" : ""}`} onClick={() => setMetric(m)}>
              {METRIC_LABEL[m]}
            </button>
          ))}
        </div>
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          {exercises.map((e) => (
            <option key={e.exercise} value={e.exercise}>
              {e.exercise} ({e.sessions})
            </option>
          ))}
        </select>
      </div>
      {data.length === 0 ? (
        <div className="muted">No data yet — run a sync.</div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -4 }}>
            <CartesianGrid stroke="#2a2f3a" strokeDasharray="3 3" />
            <XAxis dataKey="label" stroke="#9aa3b2" fontSize={11} />
            <YAxis stroke="#9aa3b2" fontSize={11} domain={["auto", "auto"]} />
            <Tooltip
              contentStyle={{ background: "#1e222b", border: "1px solid #2a2f3a", borderRadius: 8 }}
              labelStyle={{ color: "#9aa3b2" }}
              formatter={(v: number) => [`${v} ${unit}`, METRIC_LABEL[metric]]}
            />
            <Line type="monotone" dataKey="value" stroke="#ff6b3d" strokeWidth={2} dot={{ r: 2 }} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
