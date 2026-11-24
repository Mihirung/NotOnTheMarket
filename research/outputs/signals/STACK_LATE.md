# A second step aimed at homes not yet on the market

**Verdict:** do not add the second step: it does not clearly find more homes that are not yet on the market

Homes are scored on 1 January. The deployed model is kept; the second step reads its prediction, the years owned and
the certificate columns, and is aimed at homes that sell later and were not yet listed on the scoring day. Figures
are sellers found in the best tenth of each postcode district, times random, test years 2017 and 2018, each year
scored by a second step fitted on the other. Ranges are 95% and include the spread of the gain over 3 fits
of the deployed model.

## Not yet listed

| Owners | Deployed model | Second step, no certificates | Second step, with certificates | Gain from certificates | Gain in all |
|---|---|---|---|---|---|
| All | 1.690 | 1.686 | 1.692 | +0.006 (-0.019 to +0.030) | +0.002 (-0.018 to +0.023) |
| Under 10 years | 1.638 | 1.628 | 1.653 | +0.025 (-0.008 to +0.057) | +0.015 (-0.020 to +0.048) |
| 10 to 19 years | 1.519 | 1.509 | 1.528 | +0.019 (-0.013 to +0.049) | +0.009 (-0.017 to +0.030) |
| 20 years or more | 1.334 | 1.270 | 1.425 | +0.155 (+0.047 to +0.259) | +0.091 (-0.004 to +0.174) |

## Completes July to June

| Owners | Deployed model | Second step, no certificates | Second step, with certificates | Gain from certificates | Gain in all |
|---|---|---|---|---|---|
| All | 1.662 | 1.658 | 1.642 | -0.016 (-0.037 to +0.006) | -0.020 (-0.040 to -0.001) |
| Under 10 years | 1.620 | 1.608 | 1.609 | +0.001 (-0.035 to +0.036) | -0.011 (-0.046 to +0.025) |
| 10 to 19 years | 1.486 | 1.480 | 1.494 | +0.014 (-0.023 to +0.049) | +0.008 (-0.017 to +0.030) |
| 20 years or more | 1.314 | 1.241 | 1.389 | +0.148 (+0.042 to +0.241) | +0.075 (-0.011 to +0.152) |

## Completes October to June

| Owners | Deployed model | Second step, no certificates | Second step, with certificates | Gain from certificates | Gain in all |
|---|---|---|---|---|---|
| All | 1.645 | 1.646 | 1.632 | -0.015 (-0.032 to +0.007) | -0.014 (-0.038 to +0.013) |
| Under 10 years | 1.594 | 1.589 | 1.590 | +0.001 (-0.036 to +0.036) | -0.005 (-0.043 to +0.032) |
| 10 to 19 years | 1.488 | 1.475 | 1.494 | +0.019 (-0.016 to +0.057) | +0.005 (-0.025 to +0.032) |
| 20 years or more | 1.360 | 1.311 | 1.442 | +0.131 (+0.008 to +0.244) | +0.082 (-0.033 to +0.215) |

Gain in all (not yet listed, all owners) by fit of the deployed model: +0.002, -0.001, +0.011.
Forward direction only (2018 scored by a second step fitted on 2017): 1.699 to 1.704.

## What the list is made of (all owners)

| Ranking | Sells later, not yet listed | Sells later, already listed | Sale already under way | Sellers in the calendar year, times random |
|---|---|---|---|---|
| Deployed model | 6.3% | 0.2% | 3.3% | 1.741 |
| With the second step | 6.3% | 0.1% | 3.1% | 1.683 |

## What the second step leans on

| Column | Share of gain |
|---|---|
| first_step | 71.7% |
| epc_months_owned | 8.5% |
| epc_uprn_pc | 3.6% |
| epc_pool_homes | 2.1% |
| epc_own_cert_age | 2.1% |
| tenure | 2.0% |
| epc_homes_kind | 1.9% |
| epc_pool_sale_24m | 1.3% |
| epc_pool_share_6m | 1.2% |
| epc_pool_share_12m | 1.1% |
| epc_pool_sales_12m | 1.1% |
| epc_cert_rent_24m | 0.8% |
