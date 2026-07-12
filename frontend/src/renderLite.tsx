import { ReactNode } from "react";

// Minimal markdown: #/##/### headings, "- " bullets, and **bold**. Enough for the
// coach's narrative and summary cards without pulling in a markdown lib.
function bold(line: string): ReactNode[] {
  return line.split(/(\*\*[^*]+\*\*)/g).map((p, j) =>
    p.startsWith("**") && p.endsWith("**") ? <strong key={j}>{p.slice(2, -2)}</strong> : <span key={j}>{p}</span>,
  );
}

export function renderLite(text: string): ReactNode {
  return text.split("\n").map((line, i) => {
    const h = line.match(/^(#{1,6})\s+(.*)/);
    if (h) {
      const level = h[1].length;
      return (
        <div key={i} className={`md-h md-h${level}`}>
          {bold(h[2])}
        </div>
      );
    }
    const bullet = line.match(/^\s*[-*]\s+(.*)/);
    if (bullet) {
      return (
        <div key={i} className="md-li">
          <span className="md-bullet">•</span>
          <span>{bold(bullet[1])}</span>
        </div>
      );
    }
    if (!line.trim()) return <div key={i} className="md-gap" />;
    return <div key={i}>{bold(line)}</div>;
  });
}
