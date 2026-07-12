import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, BodyStats } from "../api";
import { fmtWeight, round1, toUnit, useUnit } from "../units";

export function BodyCard() {
  const { unit } = useUnit();
  const [bs, setBs] = useState<BodyStats | null>(null);

  useEffect(() => {
    api.body().then(setBs).catch(() => setBs(null));
  }, []);

  if (!bs) return null;
  if (!bs.has_data) {
    return (
      <div className="panel">
        <h2>Bodyweight</h2>
        <div className="muted">
          No bodyweight logged in Hevy yet. Weigh in on your scale (it syncs through Apple
          Health into Hevy) and it'll show up here.
        </div>
      </div>
    );
  }

  const latest = bs.latest!;
  const toDisp = (lb: number) => (unit === "lb" ? lb : round1(lb / 2.2046));
  const [tLo, tHi] = [toDisp(bs.target_lb[0]), toDisp(bs.target_lb[1])];
  const data = (bs.trend || []).map((p) => ({ date: p.date, value: round1(toUnit(p.weight_kg, unit)) }));

  return (
    <div className="panel">
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Bodyweight</h2>
        <div className="spacer" />
        <span className="muted" style={{ fontSize: 12 }}>as of {latest.date}</span>
        {bs.stale && <span className="pill warn">logged {bs.days_since}d ago</span>}
      </div>

      <div style={{ display: "flex", gap: 20, margin: "10px 0 4px", alignItems: "baseline" }}>
        <span style={{ fontSize: 24, fontWeight: 700 }}>{fmtWeight(latest.weight_kg, unit)}</span>
        {latest.fat_percent != null && <span className="muted">{latest.fat_percent}% body fat</span>}
        <span className="muted" style={{ fontSize: 13 }}>
          target {tLo}-{tHi} {unit}
        </span>
      </div>

      {data.length > 1 && (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -4 }}>
            <CartesianGrid stroke="#2a2f3a" strokeDasharray="3 3" />
            <XAxis dataKey="date" stroke="#9aa3b2" fontSize={10} />
            <YAxis stroke="#9aa3b2" fontSize={11} domain={["auto", "auto"]} />
            <ReferenceArea y1={tLo} y2={tHi} fill="#3ecf8e" fillOpacity={0.12} />
            <Tooltip
              contentStyle={{ background: "#1e222b", border: "1px solid #2a2f3a", borderRadius: 8 }}
              labelStyle={{ color: "#9aa3b2" }}
              formatter={(v: number) => [`${v} ${unit}`, "weight"]}
            />
            <Line type="monotone" dataKey="value" stroke="#4c8dff" strokeWidth={2} dot={{ r: 2 }} />
          </LineChart>
        </ResponsiveContainer>
      )}

      {bs.relative_strength && bs.relative_strength.length > 0 && (
        <>
          <h2 style={{ marginTop: 14 }}>Relative strength</h2>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
            Best est. 1RM per bodyweight{bs.stale ? " (using last known weight)" : ""}.
          </div>
          {bs.relative_strength.map((r) => (
            <div className="stalled-row" key={r.exercise}>
              <span className="name">{r.exercise}</span>
              <span className="pill">{r.ratio}x BW</span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
