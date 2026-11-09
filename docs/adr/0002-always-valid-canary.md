# 2. Canary decisions with an always-valid confidence sequence

**Context.** A canary is looked at after every step. A fixed-horizon z-test checked three or thirty times finds
"significant" differences far more often than its nominal 5% (`test_naive_repeated_testing_would_not_keep_it`).

**Decision.** A normal-mixture confidence sequence (mSPRT) on the difference between candidate and champion,
non-inferiority against a margin, variance reduced with the champion's own expected value for each request
(CUPED). Roll back when the interval is wholly below the margin; ship when it is wholly above after the last step;
otherwise hold for a person.

**Consequences.** Clearly bad releases stop at 5% of traffic. A truly neutral release is sometimes held rather
than shipped: the price of not shipping by luck. Step sizes in `config/paved.toml` set that trade-off.
