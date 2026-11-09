import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import { CostView } from "../features/cost/CostView";
import { DeliveryTable } from "../features/delivery/DeliveryTable";
import { Overview } from "../features/overview/Overview";
import { ReleaseTracks } from "../features/tracks/ReleaseTracks";
import { Section } from "../shared/Section";
import { EmptyState, ErrorState, Skeleton } from "../shared/states";
import { chart, font, motion as m, space } from "../theme/tokens";
import type { Dashboard } from "./types";
import { useJson } from "./useData";

export function App() {
  const load = useJson<Dashboard>("dashboard.json");
  const [which, setWhich] = useState<"heldout" | "dev">("heldout");
  const reduce = useReducedMotion();

  return (
    <main className="page">
      <motion.header initial={reduce ? false : { opacity: 0, y: space[2] }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: m.base, ease: m.ease }}>
        <h1 style={{ fontSize: font.size.xxxl }}>One release path for models and agents</h1>
        <p className="lede measure">
          A pricing model on SageMaker and a customer-service agent on Bedrock go through the same steps: offline
          gates, shadow traffic, then a canary that moves 5%, 25% and 50% of customers and can roll back at any step.
          Below, every simulated release and where the path stopped it, judged against a truth the platform never saw.
        </p>
      </motion.header>

      {load.state === "loading" && (
        <div className="section">
          <Skeleton height={chart.skeleton} lines={3} label="Loading release results" />
        </div>
      )}
      {load.state === "error" && (
        <div className="section">
          <ErrorState what="Release results" message={load.message} onRetry={load.retry} />
        </div>
      )}
      {load.state === "ready" && <Ready data={load.data} which={which} setWhich={setWhich} />}
    </main>
  );
}

function Ready({ data, which, setWhich }: { data: Dashboard; which: "heldout" | "dev"; setWhich: (w: "heldout" | "dev") => void }) {
  const set = data.sets.find((s) => s.name === which) ?? data.sets[0];
  if (!set) {
    return (
      <div className="section">
        <EmptyState title="No releases evaluated yet.">Run `make dev`, then `make report`.</EmptyState>
      </div>
    );
  }
  return (
    <>
      <div className="tabs" role="tablist" aria-label="Release set">
        {data.sets.map((s) => (
          <button key={s.name} role="tab" className="tab" aria-selected={s.name === set.name} onClick={() => setWhich(s.name)}>
            {s.title}
          </button>
        ))}
      </div>
      <Section id="stops" title="Where releases were stopped"
        lede={set.name === "heldout"
          ? `Held-out releases: new seeds, and ${set.unseenKinds.length} kinds of fault the gates were never shown (${set.unseenKinds.map((k) => k.replaceAll("_", " ")).join(", ")}). Run once, published as it came out.`
          : "Development releases: the ones the gates and thresholds were built and tuned on."}>
        <Overview set={set} />
      </Section>
      <Section id="tracks" title="Every release" lede="Open a release to see the checks that decided it and, if it reached customers, the canary's interval at each step.">
        <ReleaseTracks releases={set.releases} />
      </Section>
      <Section id="delivery" title="Compared with the old ways" lede="The same releases, decided by a data scientist comparing one offline number, or by a single 10% canary and a z-test.">
        <DeliveryTable set={set} />
      </Section>
      <Section id="cost" title="Cost by team" lede="Spend from tagged usage, and what the platform recommends.">
        <CostView cost={data.cost} />
      </Section>
    </>
  );
}
