import { ReactNode, useState } from "react";

// A panel whose body collapses behind a clickable header (chevron + title). Used on the
// dashboard to keep space-heavy sections (progression, bodyweight, weekly volume) tucked
// away by default.
export function Collapsible({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="panel">
      <button className="collapse-head" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className={`chevron ${open ? "open" : ""}`}>▸</span>
        <h2>{title}</h2>
      </button>
      {open && <div className="collapse-body">{children}</div>}
    </div>
  );
}
