import type { Level, ProblemType } from "./api";

export const LEVELS: Level[] = ["HIGH", "MEDIUM", "LOW"];
export const levelColor = (l: Level) => `var(--${l.toLowerCase()})`;
export const levelWord = (l: Level) => (l === "NORMAL" ? "Normal" : l[0] + l.slice(1).toLowerCase());
export const levelText = (l: Level) => (l === "NORMAL" ? "Normal" : `${levelWord(l)} risk`);

/** Plain-language state of a home for a risk level. The words come from the level, nothing is scored separately. */
export function homeState(l: Level) {
  return l === "NORMAL" ? { word: "STABLE", line: "Nothing unusual in this reading" }
    : l === "LOW" ? { word: "KEEP AN EYE", line: "Slightly unusual, worth watching" }
    : { word: "ATTENTION", line: "Worth checking soon" };
}

/** Numbers that are missing or not finite render as an em dash, never "NaN" or "undefined". */
export function num(v: number | null | undefined, digits = 0, unit = ""): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}${unit ? ` ${unit}` : ""}`;
}

/** Display numbering: installation_0 is "House 1" ... installation_9 is "House 10". The installation id stays the
 *  real identifier everywhere else (API paths, warning ids, data). This is the only place that maps one to the other. */
export const houseNumber = (id: string) => Number(id.replace("installation_", "")) + 1;
export const homeName = (id: string) => `House ${houseNumber(id)}`;
/** Sort by house number, so House 10 comes after House 9. */
export const byHouse = (a: { installation: string }, b: { installation: string }) => houseNumber(a.installation) - houseNumber(b.installation);

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** Timestamps are naive local strings ("2025-03-04T08:00:00"); parsed by hand so no timezone shift can occur. */
export function parts(ts: string) {
  const [d, t = "00:00:00"] = ts.split("T");
  const [y, m, day] = d.split("-").map(Number);
  const [hh, mm] = t.split(":").map(Number);
  return { y, m, day, hh, mm };
}
export const fmtDate = (ts: string) => { const p = parts(ts); return `${MONTHS[p.m - 1]} ${p.day}, ${p.y}`; };
export const fmtShort = (ts: string) => { const p = parts(ts); return `${MONTHS[p.m - 1]} ${p.day}`; };
export function fmtTime(ts: string): string {
  const p = parts(ts); const h = p.hh % 12 || 12;
  return `${h}:${String(p.mm).padStart(2, "0")} ${p.hh < 12 ? "AM" : "PM"}`;
}
export const fmtFull = (ts: string) => `${fmtDate(ts)}, ${fmtTime(ts)}`;
export const dayOf = (ts: string) => ts.slice(0, 10);
export const hourOf = (ts: string) => parts(ts).hh;
export const msOf = (ts: string) => { const p = parts(ts); return Date.UTC(p.y, p.m - 1, p.day, p.hh, p.mm); };
export function addDays(day: string, n: number): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

export const TYPE_LABEL: Record<ProblemType, string> = {
  electricity: "Electricity", water: "Water flow", combined: "Electricity + water",
  inactivity: "Quiet period", low_activity: "Low activity", contextual: "Unusual pattern", none: "Normal",
};
export const hourLabel = (h: number) => `${String(h).padStart(2, "0")}:00`;
