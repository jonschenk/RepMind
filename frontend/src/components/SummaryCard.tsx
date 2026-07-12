import { useEffect, useState } from "react";
import { api } from "../api";
import { renderLite } from "../renderLite";

// Reads the cached "what to improve this week" summary. It is NOT regenerated on load
// (that would cost tokens on every visit); the backend refreshes it Saturday mornings.
export function SummaryCard({ enabled }: { enabled: boolean }) {
  const [text, setText] = useState<string | null>(null);
  const [updated, setUpdated] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .summary()
      .then((r) => {
        setText(r.summary);
        setUpdated(r.generated_at ?? null);
      })
      .catch((e: any) => setText(`Could not load summary: ${e.message ?? e}`))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="panel">
      <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
        <h2 style={{ margin: 0 }}>What to improve this week{!enabled && " (rule-based)"}</h2>
        <div className="spacer" />
        {updated && (
          <span className="muted" style={{ fontSize: 12 }}>
            updated {new Date(updated).toLocaleDateString()}
          </span>
        )}
      </div>
      {loading && <div className="muted" style={{ marginTop: 10 }}>Loading…</div>}
      {!loading && text && <div className="summary" style={{ marginTop: 10 }}>{renderLite(text)}</div>}
    </div>
  );
}
