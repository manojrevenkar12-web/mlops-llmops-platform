# 3. Shadow compares features request by request, not distributions

**Context.** A first version compared the distribution of served features with the training data (PSI). It
flagged every model, because time features always move between the training window and today, and it would miss a
leak whose feature has a plausible distribution online.

**Decision.** In shadow, replay the training pipeline on the very requests the endpoint received (from SageMaker
data capture, joined with the log once outcomes arrive) and compare each feature value. Report the feature and the
share of requests that differ.

**Consequences.** Leaks, unit changes and renamed categories are caught exactly and named. Distribution drift is a
monitoring question, not a release question.
