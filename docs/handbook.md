# Platform handbook

For data scientists and ML engineers putting a model or an agent on the platform. Ten minutes to read.

## The path every release takes

```
workload.yaml ─► offline ─► shadow ─► canary 5% ─► 25% ─► 50% ─► all customers
                   │           │          │          │      │
                 blocked     blocked   rolled back at any step, or held after the last
```

You do not choose the path; you choose what your workload is (its contract). The platform decides each step from
evidence and writes the evidence and the reason into the release record (`paved status <events> --release <id>`).

## Starting

```bash
paved init --kind model --name churn-score --team customer-analytics --owner you@example.com
paved validate workloads/churn-score/workload.yaml
```

`init` writes the contract, a code stub, a contract test and a CI workflow that hands releases to the control
plane on merge. Nothing in the platform changes for a new workload; `damage-cost` was added this way
(`tests/test_onboarding.py`).

## Models

Your training code returns an object with:

| Member | What the platform does with it |
|---|---|
| `features(data, online)` | Offline gate: features for logged rows. Shadow: replays the training pipeline on the very requests the endpoint served and compares feature by feature |
| `predict(frame)` | Scores the holdout, mirrored traffic and canary traffic |
| `train_to` | Must end before the platform's holdout window (`holdout_days`) |
| `complexity` | Recorded with the release |

The contract's `evaluation` block names the label, the metric (`logloss` or `rmse`), the slices that must not
regress, and features whose distribution moves by design (`skew_exclude`, for example a price the policy sets).

What blocks a model, and how to read it:

- **Offline, loss vs champion**: the upper 95% bound of your loss change exceeds the margin. Usually stale data
  or a weaker model. The holdout is the last `holdout_days`, which your training must not touch.
- **Offline, worst slice**: one slice (an airport, a car class) got clearly worse even if the average did not.
- **Offline, calibration vs champion**: your probabilities moved away from observed rates more than the
  champion's. Fleet planning reads these numbers as forecasts.
- **Shadow, online/offline parity**: a feature as your endpoint received it differs from what your training
  pipeline computes for the same request. This is where leaks (a column written after the outcome), unit changes
  and renamed categories show up. The check names the feature and the share of requests.
- **Shadow, p95 latency**: against the SLO (the platform's, or your tighter one).

## Agents

Build your graph against `paved.agentkit`: an `LLM` port (classify, propose an action, draft a reply) and a
`Tools` port. In production the platform gives you `BedrockConverseLLM` (application inference profile tagged
with your team, guardrail, prompt caching on the static prefix, tool use for structured output); in evaluation a
simulated model. The model reads; your code decides: put the rules that must hold in plain code nodes (the
reference agent's `policy_guard`).

What blocks an agent:

- **Offline, task success vs champion** on the labelled evaluation set: intent, action and the facts in the
  reply against the published knowledge base.
- **Offline, worst slice** by language and rental phase.
- **Offline, policy suite**: any action the policy reserves for a person (a deposit refund above the limit).
  Zero allowed, and not overridable.
- **Offline/shadow, cost per conversation** more than 30% above the champion, **p95 latency** over the SLO,
  **tool errors** against the live API version (in dry-run mode).

## The canary

Traffic moves 5% → 25% → 50%. After each step the platform computes the effect on the primary metric (revenue per
offer for pricing, resolution for agents) with an always-valid confidence interval, so it can look after every
step without raising its false-alarm rate. It rolls back as soon as the interval is wholly below the margin, or a
guardrail trips (conversion, latency, forecast quality; policy violations in audited conversations, escalations,
cost, tool errors). It ships only if, after the last step, the interval is wholly above the margin. Otherwise it
holds the release for a person.

## Overrides

A person can promote a held or blocked release with `paved override ... --person you@example.com --reason "..."`.
The record keeps who and why. A policy-violation block cannot be overridden.

## Cost

Every endpoint and inference profile carries `team` and `workload` tags; each team has a budget
(`infra/terraform`). `make cost` shows spend by team and what the platform recommends: prompt caching, a cheaper
model that passed your gates, Bedrock batch for replies that are not needed within seconds, fewer instances for
idle endpoints.
