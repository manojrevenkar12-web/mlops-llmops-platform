import { motion, useReducedMotion } from "framer-motion";
import type { Policy, Release, Station } from "../../app/types";
import { policyName } from "../../shared/format";
import { chart, color, font, motion as m, stationLabel, stations, stroke } from "../../theme/tokens";

const POLICIES: Policy[] = ["platform", "fixed_canary", "offline_only"];

/** Where each release was stopped, one row per way of releasing. Bad releases should stop early; good ones
 *  should reach all customers. Every mark is one release. */
export function StopChart({ releases, show }: { releases: Release[]; show: "bad" | "good" }) {
  const reduce = useReducedMotion();
  const subset = releases.filter((r) => (show === "bad" ? !r.truthGood : r.truthGood));
  const inner = chart.stopWidth - chart.stopLabel - chart.stopPadRight;
  const x = (s: Station) => chart.stopLabel + (stations.indexOf(s) / (stations.length - 1)) * inner;
  const height = POLICIES.length * chart.stopRow + chart.stopAxis;
  const wrongColour = show === "bad" ? color.stop : color.hold;

  return (
    <figure style={{ margin: 0 }}>
      <svg
        viewBox={`0 0 ${chart.stopWidth} ${height}`}
        width="100%"
        role="img"
        aria-label={`Where ${subset.length} ${show} releases were stopped, for each way of releasing`}
      >
        {stations.map((s) => (
          <g key={s}>
            <line x1={x(s)} x2={x(s)} y1={chart.stopTop} y2={height - chart.stopAxis + chart.stopTop} stroke={color.rule} strokeWidth={stroke.hair} />
            <text x={x(s)} y={height - chart.stopTop} textAnchor="middle" fontFamily={font.narrow} fontSize={font.size.sm} fill={color.ink2}>
              {stationLabel[s]}
            </text>
          </g>
        ))}
        {POLICIES.map((p, row) => {
          const y = chart.stopFirst + row * chart.stopRow;
          const counts: Partial<Record<Station, number>> = {};
          return (
            <g key={p}>
              <text x={0} y={y + 4} fontSize={font.size.sm} fontWeight={p === "platform" ? 600 : 400} fill={color.ink}>
                {policyName[p]}
              </text>
              <line x1={chart.stopLabel} x2={chart.stopLabel + inner} y1={y} y2={y} stroke={color.track} strokeWidth={stroke.track} />
              {subset.map((r, i) => {
                const at = r.decisions[p].stoppedAt;
                const k = counts[at] ?? 0;
                counts[at] = k + 1;
                const reached = at === "shipped";
                const wrong = show === "bad" ? reached : !reached;
                const cy = y + chart.markGap + Math.floor(k / chart.stopCols) * chart.markGap;
                const cx = x(at) + ((k % chart.stopCols) - (chart.stopCols - 1) / 2) * chart.markGap;
                return (
                  <motion.circle
                    key={r.id}
                    r={chart.mark}
                    cy={cy}
                    fill={wrong ? wrongColour : p === "platform" ? color.platform : color.baseline}
                    initial={reduce ? false : { cx: chart.stopLabel, opacity: 0 }}
                    animate={{ cx, opacity: 1 }}
                    transition={{ duration: m.travel, ease: m.ease, delay: row * 0.15 + i * m.stagger }}
                  >
                    <title>{`${r.scenario}: ${r.note} — ${stationLabel[at]}`}</title>
                  </motion.circle>
                );
              })}
            </g>
          );
        })}
      </svg>
      <figcaption className="legend">
        <span>
          <svg width={12} height={12} aria-hidden>
            <circle cx={6} cy={6} r={5} fill={wrongColour} />
          </svg>
          {show === "bad" ? "a bad release that reached every customer" : "a good release that was stopped"}
        </span>
        <span>
          <svg width={12} height={12} aria-hidden>
            <circle cx={6} cy={6} r={5} fill={color.platform} />
          </svg>
          {show === "bad" ? "stopped by this path" : "shipped by this path"}
        </span>
        <span>
          <svg width={12} height={12} aria-hidden>
            <circle cx={6} cy={6} r={5} fill={color.baseline} />
          </svg>
          the old ways
        </span>
      </figcaption>
    </figure>
  );
}
