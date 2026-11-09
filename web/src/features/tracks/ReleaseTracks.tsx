import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState } from "react";
import type { Release } from "../../app/types";
import { decisionWord } from "../../shared/format";
import { EmptyState } from "../../shared/states";
import { chart, font, motion as m, space } from "../../theme/tokens";
import { ReleaseDetail } from "../release/ReleaseDetail";
import { Track } from "./Track";

type Filter = "all" | "bad" | "good" | "wrong";

export function ReleaseTracks({ releases }: { releases: Release[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [kind, setKind] = useState<"all" | "model" | "agent">("all");
  const [open, setOpen] = useState<string | null>(null);
  const shown = useMemo(
    () =>
      releases.filter((r) => {
        if (kind !== "all" && r.kind !== kind) return false;
        const shipped = r.decisions.platform.decision === "promoted";
        if (filter === "bad") return !r.truthGood;
        if (filter === "good") return r.truthGood;
        if (filter === "wrong") return shipped !== r.truthGood;
        return true;
      }),
    [releases, filter, kind],
  );
  const wrong = releases.filter((r) => (r.decisions.platform.decision === "promoted") !== r.truthGood).length;
  return (
    <div className="board">
      <div className="chips" role="group" aria-label="Filter releases" style={{ marginTop: 0 }}>
        {(
          [
            ["all", `All ${releases.length}`],
            ["bad", "Bad"],
            ["good", "Good"],
            ["wrong", `Wrong calls (${wrong})`],
          ] as [Filter, string][]
        ).map(([f, label]) => (
          <button key={f} className="chip" aria-pressed={filter === f} onClick={() => setFilter(f)}>
            {label}
          </button>
        ))}
        <span style={{ width: space[4] }} />
        {(["all", "model", "agent"] as const).map((k) => (
          <button key={k} className="chip" aria-pressed={kind === k} onClick={() => setKind(k)}>
            {k === "all" ? "Models and agents" : k === "model" ? "Pricing model" : "Service agent"}
          </button>
        ))}
      </div>
      <p className="legend">
        Each track runs offline, shadow, 5%, 25%, 50%, all customers. The end shows what happened: a filled circle
        shipped, a square blocked, a diamond rolled back, a ring held for a person.
      </p>
      <div style={{ marginTop: space[4] }}>
        {shown.length === 0 ? (
          <EmptyState title="No releases match.">Clear a filter to see the others.</EmptyState>
        ) : (
          shown.map((r) => (
            <div key={r.id}>
              <button className="track-row" aria-expanded={open === r.id} onClick={() => setOpen(open === r.id ? null : r.id)}>
                <span className="row">
                  <span>
                    <span className="narrow">
                      {r.kind === "model" ? "Pricing model" : "Service agent"}: {r.scenario.replaceAll("_", " ")}
                    </span>
                    <span className="ink2" style={{ display: "block", fontSize: font.size.sm }}>
                      {r.note}
                    </span>
                  </span>
                  <span style={{ display: "flex", gap: space[4], alignItems: "center" }}>
                    <Track release={r} />
                    <span className="narrow" style={{ width: chart.verdictWidth, fontSize: font.size.sm }}>
                      {decisionWord[r.decisions.platform.decision]}; {r.truthGood ? "was good" : "was bad"}
                    </span>
                  </span>
                </span>
              </button>
              <AnimatePresence initial={false}>
                {open === r.id && (
                  <motion.div
                    className="detail"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: m.base, ease: m.ease }}
                  >
                    <ReleaseDetail release={r} />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
