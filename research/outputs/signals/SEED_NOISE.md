# Two fits of the same model: how far apart?

The deployed model (BASE + HIST + GEO + VIEW + HOUSE + AREA + PD) fitted with different random seeds and nothing else changed. Sellers found in the best tenth of each district, times random, 2017 and 2018.

| Seeds | Owners | First | Second | Difference | 95% range (test homes only) |
|---|---|---|---|---|---|
| 7 vs 8 | all | 1.741 | 1.724 | -0.017 | -0.035 to -0.002 |
| 7 vs 8 | t0_9 | 1.740 | 1.730 | -0.010 | -0.034 to +0.011 |
| 7 vs 8 | t10_19 | 1.514 | 1.533 | +0.019 | -0.003 to +0.041 |
| 7 vs 8 | t20p | 1.291 | 1.304 | +0.013 | -0.056 to +0.086 |
| 7 vs 9 | all | 1.741 | 1.720 | -0.021 | -0.036 to -0.008 |
| 7 vs 9 | t0_9 | 1.740 | 1.745 | +0.005 | -0.019 to +0.034 |
| 7 vs 9 | t10_19 | 1.514 | 1.522 | +0.008 | -0.018 to +0.033 |
| 7 vs 9 | t20p | 1.291 | 1.301 | +0.010 | -0.052 to +0.073 |
| 8 vs 9 | all | 1.724 | 1.720 | -0.003 | -0.019 to +0.015 |
| 8 vs 9 | t0_9 | 1.730 | 1.745 | +0.015 | -0.009 to +0.043 |
| 8 vs 9 | t10_19 | 1.533 | 1.522 | -0.011 | -0.035 to +0.016 |
| 8 vs 9 | t20p | 1.304 | 1.301 | -0.003 | -0.066 to +0.063 |

Largest difference for all owners between two fits of the same model: 0.021. A new family's gain has to be judged against this, not only against zero.
