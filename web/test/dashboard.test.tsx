import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/app/App";
import type { Dashboard, Release } from "../src/app/types";

function rel(id: string, good: boolean, platform: string, stoppedAt: string, extra: Partial<Release> = {}): Release {
  return {
    id, workload: "pricing-conversion", kind: "model", scenario: id, note: `note ${id}`, truthGood: good,
    truthWhy: good ? [] : ["revenue per offer -4.0%"], trueEffect: good ? 0.01 : -0.04,
    decisions: {
      platform: { decision: platform, stoppedAt } as Release["decisions"]["platform"],
      fixed_canary: { decision: "promoted", stoppedAt: "shipped" },
      offline_only: { decision: "promoted", stoppedAt: "shipped" },
    },
    reason: platform === "blocked" ? "offline: log loss change 0.05 > 0.01" : "non-inferior at the last step",
    exposure: platform === "blocked" ? 0 : 340000, hours: 79,
    steps: platform === "blocked" ? [] : [0, 1, 2].map((s) => ({ step: s, share: 0.05, effect: 0.2, lower: -1, upper: 1.4, margin: 1.8, decision: "continue", reason: "", n_candidate: 1 })),
    gates: { offline: { passed: platform !== "blocked", checks: [{ name: "loss_vs_champion", value: 0.05, limit: 0.01, passed: platform !== "blocked", reason: "log loss change 0.05 > 0.01" }] } },
    ...extra,
  };
}

const summary = (bs: number) => ({ releases: 2, good: 1, bad: 1, bad_shipped: bs, good_shipped: 1, good_blocked: 0, bad_exposure_requests: 0, median_hours_to_decision: 79 });

const data: Dashboard = {
  generated: "test",
  sets: [{
    name: "heldout", title: "Held-out releases", seeds: [1], unseenKinds: ["unit_bug"],
    summary: { platform: summary(0), fixed_canary: summary(1), offline_only: summary(1) },
    releases: [rel("good_one", true, "promoted", "shipped"), rel("leaky", false, "blocked", "offline")],
  }],
  cost: { note: "simulated", total_spend_usd_month: 1000, identified_saving_usd_month: 200, by_team: { pricing: { spend_usd_month: 1000, workloads: 1 } },
    recommendations: [{ team: "pricing", workload: "bandit", action: "scale 4 → 1 instances", reason: "idle", saving_usd_month: 200 }] },
};

function serve(body: unknown, ok = true) {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok, status: ok ? 200 : 500, json: async () => body })));
}

afterEach(() => vi.unstubAllGlobals());

describe("dashboard", () => {
  it("shows a skeleton while loading", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    render(<App />);
    expect(screen.getByRole("status", { name: /loading release results/i })).toBeInTheDocument();
  });

  it("shows an error with a retry that loads again", async () => {
    serve({}, false);
    render(<App />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/could not be loaded/);
    serve(data);
    await userEvent.click(within(alert).getByRole("button", { name: /load again/i }));
    expect(await screen.findByRole("heading", { name: /where releases were stopped/i })).toBeInTheDocument();
  });

  it("shows an empty state when nothing has been evaluated", async () => {
    serve({ ...data, sets: [] });
    render(<App />);
    expect(await screen.findByText(/no releases evaluated yet/i)).toBeInTheDocument();
  });

  it("summarises outcomes and opens a release's evidence", async () => {
    serve(data);
    render(<App />);
    expect((await screen.findAllByText("0 of 1")).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: /leaky/i }));
    expect(screen.getByText(/stopped before any customer saw it/i)).toBeInTheDocument();
    expect(screen.getAllByText(/log loss change 0.05 > 0.01/).length).toBeGreaterThan(0);
  });

  it("filters to wrong calls and says so when there are none", async () => {
    serve(data);
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /wrong calls/i }));
    expect(screen.getByText(/no releases match/i)).toBeInTheDocument();
  });

  it("lists cost recommendations", async () => {
    serve(data);
    render(<App />);
    expect(await screen.findByText("scale 4 → 1 instances")).toBeInTheDocument();
  });
});
