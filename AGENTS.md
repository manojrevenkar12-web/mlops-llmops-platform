# AGENTS.md

How to work in this repository, for people and coding agents.

## Fast feedback

```bash
make lint        # ruff format --check and ruff check
make test        # all Python tests (about a minute): stats, contract, gates, canary, pipeline, AWS adapters, cost, API
make web-test    # vitest for the dashboard
make tf          # tofu fmt, init and validate (needs the provider registry; CI runs it)
make lock-check  # the held-out lock still verifies
make cost        # reports/cost.json from a month of tagged usage
make dev         # every development release through the path and the baselines (about an hour on 2 cores)
make report      # RESULTS.md and web/public/data/dashboard.json from reports/*.json
make api         # FastAPI on :8000
```

## Invariants (tests enforce them)

1. **The platform never sees the truth.** `paved_world` simulates customers, bookings and foundation-model
   behaviour and keeps the truth; `paved_eval` scores decisions against it. Nothing under `src/paved` or
   `src/paved_workloads` imports either (`test_the_platform_never_imports_the_world_or_the_evaluation`). The
   platform sees what AWS and customers would show: captured requests, latency, outcomes, billing.
2. **One path for models and agents.** Both kinds go contract → offline → shadow → canary → decision through
   `paved.pipeline.Pipeline`; only the evidence differs (`tests/test_pipeline.py`).
3. **Steps happen once.** Every step is an event with an idempotency key; a pipeline that dies mid-canary
   resumes without moving traffic twice, and the log is hash-chained (`test_a_pipeline_that_died_mid_canary_resumes_without_repeating_steps`,
   `test_the_chain_detects_an_edited_history`).
4. **Floors are never lowered.** A team may tighten a gate in its workload.yaml and may not loosen one
   (`test_floors_are_never_lowered`). A policy-violation block cannot be overridden; any other override needs a
   named person and a reason, and is recorded.
5. **Looking early is free.** Canary decisions use an always-valid confidence sequence, so checking after every
   step keeps the error rate (`test_confidence_sequence_keeps_its_error_rate_under_repeated_looks`).
6. **Settings in config.** Every threshold and step size is in `config/paved.toml`; prices in
   `config/prices.toml` with their sources; the dashboard's sizes and colours in `web/src/theme/tokens.ts`.
7. **Generated reports.** `RESULTS.md` and `web/public/data/dashboard.json` come from `scripts/report.py`; CI
   regenerates them and fails on a difference.

## The held-out rule

The held-out releases use seeds the gates were never run on (`heldout_seeds`) and four kinds of fault that the
development set does not contain at all (`heldout_only_kinds`: a unit change and a renamed category in the online
feature pipeline, a tool API version drift, a prompt that only works in English). Every gate, threshold and
canary size was set on the development set.

Before the held-out run, every file that decides a release (platform, workloads, world, evaluation, both config
files, the workload contracts) is pinned in `config/heldout.lock` with `scripts/lock.py write`.
`scripts/evaluate.py heldout` checks the lock, refuses to run a second time, and `reports/heldout.json` is
published as it came out. Changing a gate after that needs new held-out seeds and new unseen faults.

## Layout

```
config/               paved.toml (every setting), prices.toml (list prices + sources), heldout.lock
workloads/            one workload.yaml per model or agent on the platform
src/paved/            the platform: contract, pipeline, gates (model, agent, canary), events, cost, adoption,
                      agentkit (the agent SDK), serving (SageMaker, Bedrock, AgentCore), API, CLI, scaffold
src/paved_workloads/  team code: pricing conversion model, LangGraph customer-service agent, damage-cost model
src/paved_world/      the simulated world (truth side): rental market, customer service and models, org usage
src/paved_eval/       release scenarios, the two baselines, the harness that scores decisions
scripts/              evaluate, lock, report, cost_report
infra/terraform/      capture bucket, guardrail, team budgets, least-privilege IAM for the control plane
deploy/k8s/           the control-plane API on EKS
web/                  the dashboard (React, TypeScript, Framer Motion)
docs/                 handbook for data scientists, architecture decisions
```
