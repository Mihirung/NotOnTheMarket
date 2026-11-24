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
| All | 1.691 | 1.683 | 1.690 | +0.007 (-0.020 to +0.035) | -0.001 (-0.024 to +0.022) |
| Under 10 years | 1.636 | 1.630 | 1.638 | +0.008 (-0.015 to +0.035) | +0.002 (-0.022 to +0.025) |
| 10 to 19 years | 1.519 | 1.506 | 1.533 | +0.027 (-0.014 to +0.067) | +0.014 (-0.022 to +0.045) |
| 20 years or more | 1.334 | 1.286 | 1.427 | +0.141 (+0.029 to +0.249) | +0.093 (-0.002 to +0.179) |

## Completes July to June

| Owners | Deployed model | Second step, no certificates | Second step, with certificates | Gain from certificates | Gain in all |
|---|---|---|---|---|---|
| All | 1.662 | 1.653 | 1.641 | -0.012 (-0.037 to +0.015) | -0.021 (-0.043 to +0.002) |
| Under 10 years | 1.620 | 1.616 | 1.604 | -0.012 (-0.034 to +0.013) | -0.016 (-0.039 to +0.006) |
| 10 to 19 years | 1.486 | 1.481 | 1.502 | +0.021 (-0.021 to +0.061) | +0.015 (-0.023 to +0.054) |
| 20 years or more | 1.314 | 1.255 | 1.387 | +0.133 (+0.028 to +0.236) | +0.073 (-0.014 to +0.153) |

## Completes October to June

| Owners | Deployed model | Second step, no certificates | Second step, with certificates | Gain from certificates | Gain in all |
|---|---|---|---|---|---|
| All | 1.645 | 1.642 | 1.633 | -0.010 (-0.031 to +0.013) | -0.013 (-0.040 to +0.015) |
| Under 10 years | 1.594 | 1.598 | 1.580 | -0.017 (-0.049 to +0.016) | -0.014 (-0.046 to +0.011) |
| 10 to 19 years | 1.488 | 1.472 | 1.495 | +0.024 (-0.023 to +0.068) | +0.007 (-0.024 to +0.038) |
| 20 years or more | 1.360 | 1.325 | 1.456 | +0.131 (+0.027 to +0.240) | +0.096 (-0.016 to +0.205) |

Gain in all (not yet listed, all owners) by fit of the deployed model: -0.001, -0.005, +0.011.
Forward direction only (2018 scored by a second step fitted on 2017): 1.699 to 1.689.

## What the list is made of (all owners)

| Ranking | Sells later, not yet listed | Sells later, already listed | Sale already under way | Sellers in the calendar year, times random |
|---|---|---|---|---|
| Deployed model | 6.3% | 0.2% | 3.3% | 1.741 |
| With the second step | 6.3% | 0.1% | 3.2% | 1.689 |

## What the second step leans on

| Column | Share of gain |
|---|---|
| epc_months_owned | 20.1% |
| first_step | 19.5% |
| epc_uprn_pc | 11.8% |
| epc_pool_homes | 7.1% |
| epc_homes_kind | 6.6% |
| epc_own_cert_age | 5.3% |
| tenure | 4.6% |
| epc_pool_share_6m | 3.8% |
| epc_pool_sale_24m | 3.7% |
| epc_pool_share_12m | 3.5% |
| epc_pool_sales_12m | 2.9% |
| epc_cert_rent_24m | 2.7% |
