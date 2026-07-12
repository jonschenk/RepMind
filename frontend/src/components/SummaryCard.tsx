import { useEffect, useState } from "react";
import { api } from "../api";
import { renderLite } from "../renderLite";

export function SummaryCard({ enabled }: { enabled: boolean }) {
  const [text, setText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const r = await api.summary();
      setText(r.summary);
    } catch (e: any) {
      setText(`Could not generate summary: ${e.message ?? e}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="panel">
      <h2>What to improve this week{!enabled && " (rule-based)"}</h2>
      {loading && <div className="muted">Analyzing recent training…</div>}
      {!loading && text && <div className="summary">{renderLite(text)}</div>}
      {!loading && (
        <button className="btn ghost" style={{ marginTop: 12 }} onClick={load}>
          Regenerate
        </button>
      )}
    </div>
  );
}
