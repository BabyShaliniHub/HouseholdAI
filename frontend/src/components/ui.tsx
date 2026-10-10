import type { ReactNode } from "react";

export function SectionHeader({ kicker, title, children }: { kicker?: string; title: string; children?: ReactNode }) {
  return (
    <div className="section-head">
      <div>{kicker && <div className="kicker">{kicker}</div>}<h2>{title}</h2></div>
      {children && <p>{children}</p>}
    </div>
  );
}

export function StatMetric({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return <div><dt>{label}</dt><dd>{value}{note && <> <small>{note}</small></>}</dd></div>;
}

export function ResourceLegend({ electricity = true, water = true }: { electricity?: boolean; water?: boolean }) {
  return (
    <div className="legend">
      {electricity && <span><i style={{ background: "var(--elec)" }} />Electricity</span>}
      {water && <span><i style={{ background: "var(--water)" }} />Water flow</span>}
      <span><i style={{ background: "var(--muted)", opacity: 0.6 }} />Normal rhythm for the hour (dashed)</span>
    </div>
  );
}
