import type { Release } from "../../app/types";
import { decisionWord, hours, int, pct, pp } from "../../shared/format";
import { chart, font, space } from "../../theme/tokens";
import { IntervalChart } from "./IntervalChart";

export function ReleaseDetail({ release }: { release: Release }) {
  const r = release;
  const effect = r.kind === "model" ? pct(r.trueEffect) : pp(r.trueEffect);
  return (
    <div className="row" style={{ alignItems: "start" }}>
      <div>
        <p>
          <strong>{decisionWord[r.decisions.platform.decision]}</strong> — {r.reason}
        </p>
        <p className="ink2" style={{ marginTop: space[1] }}>
          {int(r.exposure)} customer requests served by the candidate; decided after {hours(r.hours)}.
        </p>
        <p className="ink2" style={{ marginTop: space[1] }}>
          Truth (hidden from the platform): {r.truthGood ? "a good release" : "a bad release"}, true effect {effect}
          {r.kind === "model" ? " revenue per offer" : " resolution"}
          {r.truthWhy.length > 0 && <> — {r.truthWhy.join("; ")}</>}.
        </p>
        {(["offline", "shadow"] as const).map((g) =>
          r.gates[g] ? (
            <table key={g} className="checks" style={{ marginTop: space[4] }}>
              <caption style={{ textAlign: "left", fontWeight: font.weight.medium, padding: `${space[1]}px ${space[2]}px` }}>{g === "offline" ? "Offline gate" : "Shadow gate"}</caption>
              <thead>
                <tr>
                  <th scope="col">Check</th>
                  <th scope="col">Result</th>
                </tr>
              </thead>
              <tbody>
                {r.gates[g]!.checks.map((c) => (
                  <tr key={c.name}>
                    <td>{c.passed ? "passed" : <strong>failed</strong>}</td>
                    <td>{c.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null,
        )}
      </div>
      <div>
        {r.steps.length > 0 ? (
          <IntervalChart steps={r.steps} unit={r.kind === "model" ? "eur" : "pp"} />
        ) : (
          <p className="muted" style={{ maxWidth: chart.noteWidth }}>
            No canary: stopped before any customer saw it.
          </p>
        )}
      </div>
    </div>
  );
}
