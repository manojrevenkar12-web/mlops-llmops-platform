import type { Policy, SetData } from "../../app/types";
import { hours, int, policyName } from "../../shared/format";

const POLICIES: Policy[] = ["platform", "fixed_canary", "offline_only"];

export function DeliveryTable({ set }: { set: SetData }) {
  return (
    <div className="board">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Way of releasing</th>
            <th scope="col" className="r">Bad releases shipped</th>
            <th scope="col" className="r">Good releases shipped</th>
            <th scope="col" className="r">Requests served by bad releases before a stop</th>
            <th scope="col" className="r">Median time to a decision</th>
          </tr>
        </thead>
        <tbody>
          {POLICIES.map((p) => {
            const s = set.summary[p];
            return (
              <tr key={p}>
                <th scope="row" style={{ fontWeight: p === "platform" ? 600 : 400 }}>
                  {policyName[p]}
                </th>
                <td className="r num">{s.bad_shipped} of {s.bad}</td>
                <td className="r num">{s.good_shipped} of {s.good}</td>
                <td className="r num">{int(s.bad_exposure_requests)}</td>
                <td className="r num">{hours(s.median_hours_to_decision)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
