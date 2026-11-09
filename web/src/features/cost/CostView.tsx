import { motion, useReducedMotion } from "framer-motion";
import type { Cost } from "../../app/types";
import { usd } from "../../shared/format";
import { EmptyState } from "../../shared/states";
import { chart, color, font, motion as m, space } from "../../theme/tokens";

export function CostView({ cost }: { cost: Cost }) {
  const reduce = useReducedMotion();
  const teams = Object.entries(cost.by_team);
  if (teams.length === 0) return <EmptyState title="No usage recorded yet.">Spend appears once workloads run with team tags.</EmptyState>;
  const max = Math.max(...teams.map(([, t]) => t.spend_usd_month));
  const rowH = chart.barHeight + space[3];
  return (
    <div className="board">
      <div className="figures" style={{ marginTop: 0 }}>
        <div className="figure">
          <strong>{usd(cost.total_spend_usd_month)}</strong>
          <span className="ink2">a month across {teams.length} teams, attributed by the tags the platform writes</span>
        </div>
        <div className="figure">
          <strong>{usd(cost.identified_saving_usd_month)}</strong>
          <span className="ink2">a month the platform can see to save (estimates, applied in order per workload)</span>
        </div>
      </div>
      <svg viewBox={`0 0 ${chart.barLabel + chart.barArea + 90} ${teams.length * rowH}`} width="100%" style={{ marginTop: space[6] }}
        role="img" aria-label="Monthly spend by team">
        {teams.map(([team, t], i) => {
          const w = (t.spend_usd_month / max) * chart.barArea;
          const y = i * rowH;
          return (
            <g key={team}>
              <text x={chart.barLabel - space[2]} y={y + chart.barHeight - 2} textAnchor="end" fontSize={font.size.sm} fill={color.ink}>
                {team}
              </text>
              <motion.rect x={chart.barLabel} y={y} height={chart.barHeight} fill={color.platform}
                initial={reduce ? false : { width: 0 }} animate={{ width: w }} transition={{ duration: m.base, ease: m.ease }} />
              <text x={chart.barLabel + w + space[2]} y={y + chart.barHeight - 2} fontSize={font.size.sm} fill={color.ink2} fontFamily={font.narrow}>
                {usd(t.spend_usd_month)}
              </text>
            </g>
          );
        })}
      </svg>
      <table className="table" style={{ marginTop: space[6] }}>
        <thead>
          <tr>
            <th scope="col">Workload</th>
            <th scope="col">What to do</th>
            <th scope="col">Why</th>
            <th scope="col" className="r">
              Saving a month
            </th>
          </tr>
        </thead>
        <tbody>
          {cost.recommendations.map((r) => (
            <tr key={`${r.workload}-${r.action}`}>
              <td>
                {r.workload} <span className="muted">({r.team})</span>
              </td>
              <td>{r.action}</td>
              <td className="ink2">{r.reason}</td>
              <td className="r num">{usd(r.saving_usd_month)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted" style={{ marginTop: space[3], fontSize: font.size.sm }}>
        {cost.note}
      </p>
    </div>
  );
}
