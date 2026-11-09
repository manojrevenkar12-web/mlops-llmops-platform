import type { stations } from "../theme/tokens";

export type Station = (typeof stations)[number];
export type Policy = "platform" | "fixed_canary" | "offline_only";

export interface Step {
  step: number;
  share: number;
  effect: number;
  lower: number;
  upper: number;
  margin: number;
  decision: string;
  reason: string;
  n_candidate: number;
}

export interface Check {
  name: string;
  value: number;
  limit: number;
  passed: boolean;
  reason: string;
}

export interface Gate {
  passed: boolean;
  checks: Check[];
}

export interface Release {
  id: string;
  workload: string;
  kind: "model" | "agent";
  scenario: string;
  note: string;
  truthGood: boolean;
  truthWhy: string[];
  trueEffect: number;
  decisions: Record<Policy, { decision: string; stoppedAt: Station }>;
  reason: string;
  exposure: number;
  hours: number;
  steps: Step[];
  gates: Partial<Record<"offline" | "shadow", Gate>>;
}

export interface PolicySummary {
  releases: number;
  good: number;
  bad: number;
  bad_shipped: number;
  good_shipped: number;
  good_blocked: number;
  bad_exposure_requests: number;
  median_hours_to_decision: number;
}

export interface SetData {
  name: "dev" | "heldout";
  title: string;
  seeds: number[];
  unseenKinds: string[];
  summary: Record<Policy, PolicySummary>;
  releases: Release[];
}

export interface Cost {
  note: string;
  total_spend_usd_month: number;
  identified_saving_usd_month: number;
  by_team: Record<string, { spend_usd_month: number; workloads: number }>;
  recommendations: { team: string; workload: string; action: string; reason: string; saving_usd_month: number }[];
}

export interface Dashboard {
  generated: string;
  sets: SetData[];
  cost: Cost;
}
