import type { Step } from "../../app/types";
import { chart, color, font, stroke } from "../../theme/tokens";

/** Each canary step: the estimated effect and its always-valid interval, against the margin the release must
 *  stay above. An interval wholly below the margin line is a rollback; one wholly above it at the last step ships. */
export function IntervalChart({ steps, unit }: { steps: Step[]; unit: "eur" | "pp" }) {
  const { intervalWidth: W, intervalHeight: H, intervalPad: P } = chart;
  const margin = steps[0]?.margin ?? 0;
  const lo = Math.min(-margin * 1.6, ...steps.map((s) => s.lower));
  const hi = Math.max(margin * 1.6, ...steps.map((s) => s.upper));
  const y = (v: number) => P.top + ((hi - v) / (hi - lo)) * (H - P.top - P.bottom);
  const labels = ["5%", "25%", "50%"];
  const x = (i: number) => P.left + ((i + 0.5) / labels.length) * (W - P.left - P.right);
  const fmt = (v: number) => (unit === "pp" ? `${(v * 100).toFixed(1)}` : `€${v.toFixed(2)}`);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: W }} role="img"
      aria-label={`Canary effect per step with confidence intervals; margin ${fmt(-margin)}`}>
      <line x1={P.left} x2={W - P.right} y1={y(0)} y2={y(0)} stroke={color.rule} strokeWidth={stroke.hair} />
      <line x1={P.left} x2={W - P.right} y1={y(-margin)} y2={y(-margin)} stroke={color.stop} strokeDasharray="4 4" strokeWidth={stroke.hair} />
      <text x={W - P.right} y={y(-margin) - 4} textAnchor="end" fontSize={font.size.xs} fill={color.stop} fontFamily={font.narrow}>
        margin {fmt(-margin)}{unit === "pp" ? " pts" : " per offer"}
      </text>
      {[lo, 0, hi].map((v) => (
        <text key={v} x={P.left - 6} y={y(v) + 4} textAnchor="end" fontSize={font.size.xs} fill={color.ink2} fontFamily={font.narrow}>
          {fmt(v)}
        </text>
      ))}
      {labels.map((l, i) => (
        <text key={l} x={x(i)} y={H - 10} textAnchor="middle" fontSize={font.size.sm} fill={color.ink2} fontFamily={font.narrow}>
          {l}
        </text>
      ))}
      {steps.map((s, i) => (
        <g key={s.step}>
          <line x1={x(i)} x2={x(i)} y1={y(s.upper)} y2={y(s.lower)} stroke={color.platform} strokeWidth={stroke.mark * 2} />
          <circle cx={x(i)} cy={y(s.effect)} r={chart.mark - 1} fill={color.card} stroke={color.platform} strokeWidth={stroke.mark} />
        </g>
      ))}
    </svg>
  );
}
