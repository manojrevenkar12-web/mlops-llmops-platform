import type { Release } from "../../app/types";
import { chart, color, stations, stroke } from "../../theme/tokens";

const WIDTH = chart.trackWidth;

function endMark(decision: string, x: number, y: number) {
  const s = chart.station + 2;
  if (decision === "promoted") return <circle cx={x} cy={y} r={s} fill={color.go} />;
  if (decision === "blocked") return <rect x={x - s} y={y - s} width={2 * s} height={2 * s} fill={color.stop} />;
  if (decision === "rolled_back")
    return <path d={`M${x} ${y - s - 1} L${x + s + 1} ${y} L${x} ${y + s + 1} L${x - s - 1} ${y} Z`} fill={color.stop} />;
  return <circle cx={x} cy={y} r={s} fill={color.card} stroke={color.hold} strokeWidth={stroke.mark} />;
}

/** One release as a stretch of track: stations it passed are filled, the shape at the end says what happened
 *  (circle shipped, square blocked, diamond rolled back, ring held). */
export function Track({ release }: { release: Release }) {
  const p = release.decisions.platform;
  const stop = stations.indexOf(p.stoppedAt);
  const x = (i: number) => 8 + (i / (stations.length - 1)) * (WIDTH - 16);
  const y = 10;
  return (
    <svg width={WIDTH} height={20} viewBox={`0 0 ${WIDTH} 20`} aria-hidden>
      <line x1={x(0)} x2={x(stations.length - 1)} y1={y} y2={y} stroke={color.rule} strokeWidth={stroke.track} />
      <line x1={x(0)} x2={x(stop)} y1={y} y2={y} stroke={color.ink2} strokeWidth={stroke.track} />
      {stations.map((s, i) =>
        i === stop ? null : (
          <circle key={s} cx={x(i)} cy={y} r={chart.station - 1} fill={i < stop ? color.ink2 : color.card} stroke={color.track} />
        ),
      )}
      {endMark(release.decisions.platform.decision, x(stop), y)}
    </svg>
  );
}
