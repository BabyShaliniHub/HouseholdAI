import type { Level } from "../lib/api";
import { homeState, levelColor, num } from "../lib/format";
import { useCountUp } from "./useWidth";

const C = 150, R = 118, START = -135, SWEEP = 270;
const pt = (angle: number, r: number) => { const a = (angle * Math.PI) / 180; return [C + r * Math.sin(a), C - r * Math.cos(a)]; };
function arc(from: number, to: number, r: number) {
  const [x1, y1] = pt(from, r), [x2, y2] = pt(to, r);
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${to - from > 180 ? 1 : 0} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
}

/** Home state ring. The number is the backend's risk index; the word is derived from the backend's risk level. */
export default function RiskGauge({ value, level }: { value: number | null; level: Level }) {
  const shown = useCountUp(value ?? 0);
  const v = Math.max(0, Math.min(100, value ?? 0));
  const color = levelColor(level), state = homeState(level);
  const [nx1, ny1] = pt(START + SWEEP * 0.4, R - 15), [nx2, ny2] = pt(START + SWEEP * 0.4, R + 15);
  return (
    <svg className="gauge" viewBox="0 0 300 300" role="img" style={{ "--glow": color } as React.CSSProperties}
      aria-label={`Risk index ${num(value)} out of 100. State: ${state.word.toLowerCase()}.`}>
      {Array.from({ length: 51 }, (_, i) => {
        const a = START + (SWEEP * i) / 50, major = i % 5 === 0;
        const [x1, y1] = pt(a, 134), [x2, y2] = pt(a, major ? 147 : 141);
        return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} strokeWidth={major ? 2 : 1.2} strokeLinecap="round" stroke={i * 2 <= v ? color : "rgba(255,255,255,.12)"} />;
      })}
      <path d={arc(START, START + SWEEP, R)} fill="none" stroke="rgba(255,255,255,.06)" strokeWidth="12" strokeLinecap="round" />
      <path className="glow" d={arc(START, START + (SWEEP * Math.max(v, 0.6)) / 100, R)} fill="none" stroke={color} strokeWidth="12" strokeLinecap="round" />
      <line x1={nx1} y1={ny1} x2={nx2} y2={ny2} stroke="var(--ink)" strokeWidth="2" />
      <text x={C} y={C - 38} textAnchor="middle" fontSize="11" letterSpacing="3" fill="var(--muted)">RISK INDEX</text>
      <text className="num" x={C} y={C + 28} textAnchor="middle" fontSize="84" fill="var(--ink)">{num(shown)}</text>
      <text x={C} y={C + 62} textAnchor="middle" fontSize="14" fontWeight="700" letterSpacing="3" fill={color}>{state.word}</text>
    </svg>
  );
}
