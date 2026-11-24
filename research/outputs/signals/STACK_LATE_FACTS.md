# A second step aimed at homes not yet on the market (with past intent and home facts)

**Verdict:** add the second step: it finds more homes that are not yet on the market, the range is clear of zero and of the fit's own noise, it is no worse nine months out or more, and its lists hold fewer homes whose sale is already under way

Homes are scored on 1 January. The deployed model is kept; the second step reads its prediction, the years owned and
the certificate columns, and is aimed at homes that sell later and were not yet listed on the scoring day. Figures
are sellers found in the best tenth of each postcode district, times random, test years 2017 and 2018, each year
scored by a second step fitted on the other. Ranges are 95% and include the spread of the gain over 3 fits
of the deployed model.

## Not yet listed

| Owners | Deployed model | Second step, no certificates | Second step, with certificates | Gain from certificates | Gain in all |
|---|---|---|---|---|---|
| All | 1.690 | 1.686 | 1.711 | +0.025 (+0.006 to +0.045) | +0.021 (+0.004 to +0.041) |
| Under 10 years | 1.638 | 1.628 | 1.655 | +0.027 (+0.000 to +0.057) | +0.017 (-0.008 to +0.046) |
| 10 to 19 years | 1.519 | 1.509 | 1.553 | +0.044 (+0.001 to +0.087) | +0.034 (-0.008 to +0.077) |
| 20 years or more | 1.334 | 1.270 | 1.413 | +0.143 (+0.023 to +0.264) | +0.079 (-0.051 to +0.215) |

## Completes July to June

| Owners | Deployed model | Second step, no certificates | Second step, with certificates | Gain from certificates | Gain in all |
|---|---|---|---|---|---|
| All | 1.662 | 1.658 | 1.656 | -0.002 (-0.020 to +0.017) | -0.006 (-0.024 to +0.015) |
| Under 10 years | 1.620 | 1.608 | 1.610 | +0.002 (-0.026 to +0.029) | -0.010 (-0.033 to +0.019) |
| 10 to 19 years | 1.486 | 1.480 | 1.512 | +0.032 (-0.011 to +0.075) | +0.026 (-0.015 to +0.071) |
| 20 years or more | 1.314 | 1.241 | 1.378 | +0.136 (+0.014 to +0.244) | +0.063 (-0.049 to +0.180) |

## Completes October to June

| Owners | Deployed model | Second step, no certificates | Second step, with certificates | Gain from certificates | Gain in all |
|---|---|---|---|---|---|
| All | 1.645 | 1.646 | 1.643 | -0.004 (-0.028 to +0.024) | -0.003 (-0.021 to +0.022) |
| Under 10 years | 1.594 | 1.589 | 1.586 | -0.003 (-0.039 to +0.033) | -0.008 (-0.043 to +0.031) |
| 10 to 19 years | 1.488 | 1.475 | 1.524 | +0.050 (+0.001 to +0.102) | +0.036 (+0.001 to +0.077) |
| 20 years or more | 1.360 | 1.311 | 1.419 | +0.108 (-0.059 to +0.246) | +0.059 (-0.060 to +0.188) |

Gain in all (not yet listed, all owners) by fit of the deployed model: +0.021, +0.025, +0.025.
Forward direction only (2018 scored by a second step fitted on 2017): 1.699 to 1.713.

## What the list is made of (all owners)

| Ranking | Sells later, not yet listed | Sells later, already listed | Sale already under way | Sellers in the calendar year, times random |
|---|---|---|---|---|
| Deployed model | 6.3% | 0.2% | 3.3% | 1.741 |
| With the second step | 6.3% | 0.1% | 3.2% | 1.707 |

## What the second step leans on

| Column | Share of gain |
|---|---|
| first_step | 58.4% |
| epc_months_owned | 7.6% |
| epc2_pk_area | 3.5% |
| epc2_pk_built | 3.1% |
| epc2_pk_rooms | 3.0% |
| epc2_pool_rent_share | 2.0% |
| epc2_pk_score | 1.9% |
| epc2_pk_let | 1.8% |
| tenure | 1.5% |
| epc_uprn_pc | 1.5% |
| epc2_pool_share_old | 1.4% |
| epc2_pk_certs | 1.1% |
