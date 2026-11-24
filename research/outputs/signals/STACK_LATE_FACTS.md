# A second step aimed at homes not yet on the market (with past intent and home facts)

**Verdict:** do not add the second step: it does not clearly find more homes that are not yet on the market

Homes are scored on 1 January. The deployed model is kept; the second step reads its prediction, the years owned and
the certificate columns, and is aimed at homes that sell later and were not yet listed on the scoring day. Figures
are sellers found in the best tenth of each postcode district, times random, test years 2017 and 2018, each year
scored by a second step fitted on the other. Ranges are 95% and include the spread of the gain over 3 fits
of the deployed model.

## Not yet listed

| Owners | Deployed model | Second step, no certificates | Second step, with certificates | Gain from certificates | Gain in all |
|---|---|---|---|---|---|
| All | 1.691 | 1.683 | 1.702 | +0.019 (-0.011 to +0.051) | +0.011 (-0.015 to +0.041) |
| Under 10 years | 1.636 | 1.630 | 1.645 | +0.015 (-0.021 to +0.048) | +0.009 (-0.021 to +0.039) |
| 10 to 19 years | 1.519 | 1.506 | 1.559 | +0.053 (+0.015 to +0.089) | +0.040 (+0.009 to +0.072) |
| 20 years or more | 1.334 | 1.286 | 1.350 | +0.064 (-0.044 to +0.159) | +0.016 (-0.067 to +0.119) |

## Completes July to June

| Owners | Deployed model | Second step, no certificates | Second step, with certificates | Gain from certificates | Gain in all |
|---|---|---|---|---|---|
| All | 1.662 | 1.653 | 1.652 | -0.001 (-0.028 to +0.029) | -0.010 (-0.036 to +0.018) |
| Under 10 years | 1.620 | 1.616 | 1.612 | -0.004 (-0.036 to +0.027) | -0.008 (-0.035 to +0.018) |
| 10 to 19 years | 1.486 | 1.481 | 1.520 | +0.039 (+0.002 to +0.076) | +0.034 (-0.002 to +0.069) |
| 20 years or more | 1.314 | 1.255 | 1.324 | +0.070 (-0.032 to +0.163) | +0.010 (-0.069 to +0.096) |

## Completes October to June

| Owners | Deployed model | Second step, no certificates | Second step, with certificates | Gain from certificates | Gain in all |
|---|---|---|---|---|---|
| All | 1.645 | 1.642 | 1.641 | -0.002 (-0.021 to +0.021) | -0.005 (-0.031 to +0.024) |
| Under 10 years | 1.594 | 1.598 | 1.583 | -0.015 (-0.058 to +0.032) | -0.011 (-0.050 to +0.027) |
| 10 to 19 years | 1.488 | 1.472 | 1.528 | +0.056 (+0.005 to +0.106) | +0.039 (+0.005 to +0.078) |
| 20 years or more | 1.360 | 1.325 | 1.381 | +0.056 (-0.062 to +0.163) | +0.021 (-0.081 to +0.130) |

Gain in all (not yet listed, all owners) by fit of the deployed model: +0.011, +0.011, +0.029.
Forward direction only (2018 scored by a second step fitted on 2017): 1.699 to 1.700.

## What the list is made of (all owners)

| Ranking | Sells later, not yet listed | Sells later, already listed | Sale already under way | Sellers in the calendar year, times random |
|---|---|---|---|---|
| Deployed model | 6.3% | 0.2% | 3.3% | 1.741 |
| With the second step | 6.3% | 0.1% | 3.2% | 1.717 |

## What the second step leans on

| Column | Share of gain |
|---|---|
| epc_months_owned | 12.1% |
| first_step | 10.3% |
| epc2_pk_rooms | 7.1% |
| epc2_pk_area | 6.9% |
| epc2_pk_built | 6.4% |
| epc2_pk_score | 4.7% |
| epc2_pool_rent_share | 4.6% |
| epc_uprn_pc | 4.4% |
| epc2_pk_let | 3.8% |
| epc2_pk_certs | 3.3% |
| epc2_pool_share_old | 3.2% |
| epc_pool_homes | 2.7% |
