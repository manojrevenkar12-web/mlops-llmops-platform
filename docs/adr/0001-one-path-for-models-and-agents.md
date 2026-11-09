# 1. One release path for models and agents

**Context.** Classical models (pricing, forecasting, damage) and agents (customer service) were released by
different teams in different ways: models by comparing one offline number, agents by trying a prompt on a few
emails. Both fail in the same three places: the offline check misses what only production shows, nothing
compares what the endpoint receives with what training saw, and nobody decides with statistics when to stop.

**Decision.** One state machine for both (contract, offline, shadow, canary, decision) with kind-specific evidence
behind each gate. One event record, one override rule, one set of delivery metrics.

**Consequences.** A data scientist and an agent engineer read the same release record. Adding a third kind
(for example a batch scorer) means adding its evidence, not a new path.
