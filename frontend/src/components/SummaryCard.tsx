import { useEffect, useState } from "react";
import { api } from "../api";

// Renders **bold** markdown and line breaks minimally (no external md lib needed).
function renderLite(text: string) {
  return text.split("\n").map((line, i) => {
    const parts = line.split(/(\*\*[^*]+\*\*)/g).map((p, j) =>
      p.startsWith("**") && p.endsWith("**") ? <strong key={j}>{p.slice(2, -2)}</strong> : <span key={j}>{p}</span>,
    );
    return <div key={i}>{parts}</div>;
  });
}

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
