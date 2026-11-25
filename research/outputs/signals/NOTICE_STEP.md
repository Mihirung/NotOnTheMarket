# Notices in The Gazette: bankruptcy orders and deceased estates

**Verdict:** add the notices: homes with a notice are scored better on homes and a year the step was not fitted on, and the best tenth finds more sellers, clear of zero and of the fit's own noise

Homes are scored on 1 January. The deployed model is kept; for each kind of notice a small second step reads the months
since the latest notice at the home, how long the home had been owned when it appeared, and how many there were, and adds
to the deployed model's log-odds. Notices from the 48 months before the scoring day count. Only the home and the
month of publication are used; no name is held. A home with no notice keeps its score exactly.

## What the notices say on their own

Every home-year of 2017 and 2018 with a notice, against what the deployed model expected of the same homes.

| Notice | Published | Home-years | Sold in the year (95% range) | The model said | Times (95% range) |
|---|---|---|---|---|---|
| Bankruptcy order | 1 to 6 months before | 5,955 | 3.8% (3.3% to 4.3%) | 4.0% | 0.94 (0.81 to 1.06) |
| Bankruptcy order | 7 to 12 months before | 5,665 | 4.7% (4.2% to 5.3%) | 4.1% | 1.14 (1.00 to 1.28) |
| Bankruptcy order | 13 to 24 months before | 11,013 | 5.4% (5.0% to 5.9%) | 4.2% | 1.31 (1.20 to 1.42) |
| Bankruptcy order | 25 to 36 months before | 11,965 | 4.9% (4.5% to 5.3%) | 4.0% | 1.21 (1.11 to 1.31) |
| Bankruptcy order | 37 to 48 months before | 13,928 | 5.2% (4.9% to 5.6%) | 4.0% | 1.29 (1.20 to 1.39) |
| Bankruptcy order | Any time in the window, about an earlier owner | 7,468 | 3.6% (3.1% to 4.0%) | 3.3% | 1.09 (0.96 to 1.24) |
| Deceased-estate notice | 1 to 6 months before | 5,685 | 30.1% (28.6% to 31.8%) | 3.8% | 8.01 (7.60 to 8.44) |
| Deceased-estate notice | 7 to 12 months before | 4,891 | 17.4% (16.1% to 18.7%) | 3.8% | 4.64 (4.30 to 4.99) |
| Deceased-estate notice | 13 to 24 months before | 7,166 | 8.9% (8.2% to 9.8%) | 3.8% | 2.34 (2.15 to 2.56) |
| Deceased-estate notice | 25 to 36 months before | 6,246 | 5.5% (4.9% to 6.1%) | 4.0% | 1.36 (1.21 to 1.52) |
| Deceased-estate notice | 37 to 48 months before | 5,144 | 4.9% (4.3% to 5.6%) | 4.1% | 1.21 (1.05 to 1.38) |
| Deceased-estate notice | Any time in the window, about an earlier owner | 65,137 | 4.2% (4.0% to 4.3%) | 3.6% | 1.14 (1.09 to 1.18) |

## Are the homes with a notice better scored?

Log loss on every home-year with a notice (lower is better), each scored by a step fitted on other homes in the other year.

| Notices | Home-years | Sold | Deployed model expected | Second step expected | Log loss before | After | Change (95% range) |
|---|---|---|---|---|---|---|---|
| Both | 150,186 | 9,170 | 5,729 | 9,060 | 0.2315 | 0.2065 | -0.0250 (-0.0265 to -0.0235) |
| Bankruptcy orders | 55,994 | 2,670 | 2,222 | 2,561 | 0.1915 | 0.1908 | -0.0007 (-0.0011 to -0.0003) |
| Deceased-estate notices | 94,269 | 6,504 | 3,510 | 6,501 | 0.2553 | 0.2158 | -0.0394 (-0.0418 to -0.0369) |

## Sellers found in the best tenth of each postcode district, times random

Test homes of 2017 and 2018. Ranges are 95% and include the spread of the gain over 3 fits of the deployed model.

### Sells in the calendar year

| Owners | Deployed model | With the notices | Gain | Bankruptcy orders alone | Deceased-estate notices alone |
|---|---|---|---|---|---|
| All | 1.741 | 1.759 | +0.019 (+0.013 to +0.023) | -0.000 (-0.002 to +0.001) | +0.019 (+0.015 to +0.023) |
| Under 10 years | 1.740 | 1.750 | +0.010 (+0.004 to +0.016) | -0.002 (-0.003 to +0.000) | +0.011 (+0.006 to +0.015) |
| 10 to 19 years | 1.514 | 1.536 | +0.022 (+0.013 to +0.029) | -0.002 (-0.005 to +0.001) | +0.024 (+0.018 to +0.029) |
| 20 years or more | 1.291 | 1.351 | +0.060 (+0.032 to +0.084) | +0.005 (-0.008 to +0.019) | +0.056 (+0.034 to +0.081) |

### Completes July to June

| Owners | Deployed model | With the notices | Gain | Bankruptcy orders alone | Deceased-estate notices alone |
|---|---|---|---|---|---|
| All | 1.662 | 1.668 | +0.006 (+0.002 to +0.011) | -0.002 (-0.004 to -0.001) | +0.008 (+0.004 to +0.011) |
| Under 10 years | 1.620 | 1.624 | +0.004 (-0.003 to +0.010) | -0.002 (-0.003 to -0.000) | +0.005 (+0.001 to +0.009) |
| 10 to 19 years | 1.486 | 1.494 | +0.008 (+0.000 to +0.015) | -0.002 (-0.005 to +0.001) | +0.011 (+0.006 to +0.015) |
| 20 years or more | 1.314 | 1.334 | +0.020 (-0.005 to +0.047) | +0.003 (-0.010 to +0.020) | +0.017 (-0.002 to +0.032) |

### Completes July to June, not yet listed

| Owners | Deployed model | With the notices | Gain | Bankruptcy orders alone | Deceased-estate notices alone |
|---|---|---|---|---|---|
| All | 1.691 | 1.697 | +0.006 (+0.001 to +0.011) | -0.002 (-0.003 to -0.000) | +0.007 (+0.004 to +0.011) |
| Under 10 years | 1.636 | 1.639 | +0.004 (-0.003 to +0.010) | -0.001 (-0.003 to +0.000) | +0.005 (+0.000 to +0.009) |
| 10 to 19 years | 1.519 | 1.525 | +0.006 (-0.001 to +0.014) | -0.002 (-0.005 to +0.001) | +0.009 (+0.005 to +0.014) |
| 20 years or more | 1.334 | 1.352 | +0.018 (-0.008 to +0.046) | +0.005 (-0.009 to +0.022) | +0.013 (-0.004 to +0.029) |

## The homes with a notice

The first four columns are every home; the last three are the test homes alone.

| Notice | Published | Home-years | Sold in the year | Deployed model said | Second step says | Sold later, not yet listed | In the best tenth before | After |
|---|---|---|---|---|---|---|---|---|
| Bankruptcy order | 1 to 6 months before | 5,955 | 3.8% | 4.0% | 4.2% | 4.9% | 11% | 10% |
| Bankruptcy order | 7 to 12 months before | 5,665 | 4.7% | 4.1% | 4.7% | 4.3% | 14% | 22% |
| Bankruptcy order | 13 to 24 months before | 11,013 | 5.4% | 4.2% | 4.9% | 4.6% | 12% | 23% |
| Bankruptcy order | 25 to 36 months before | 11,965 | 4.9% | 4.0% | 4.8% | 3.8% | 10% | 20% |
| Bankruptcy order | 37 to 48 months before | 13,928 | 5.2% | 4.0% | 4.9% | 4.3% | 8% | 24% |
| Bankruptcy order | Any, owner bought before it | 48,526 | 5.0% | 4.1% | 4.8% | 4.3% | 10% | 21% |
| Bankruptcy order | Any, about an earlier owner | 7,468 | 3.6% | 3.3% | 3.4% | 4.2% | 7% | 10% |
| Deceased-estate notice | 1 to 6 months before | 5,685 | 30.1% | 3.8% | 29.0% | 13.8% | 7% | 84% |
| Deceased-estate notice | 7 to 12 months before | 4,891 | 17.4% | 3.8% | 17.6% | 8.3% | 8% | 79% |
| Deceased-estate notice | 13 to 24 months before | 7,166 | 8.9% | 3.8% | 8.9% | 6.0% | 5% | 67% |
| Deceased-estate notice | 25 to 36 months before | 6,246 | 5.5% | 4.0% | 5.7% | 3.1% | 9% | 44% |
| Deceased-estate notice | 37 to 48 months before | 5,144 | 4.9% | 4.1% | 5.2% | 6.2% | 8% | 29% |
| Deceased-estate notice | Any, owner bought before it | 29,132 | 13.0% | 3.9% | 12.9% | 7.3% | 7% | 61% |
| Deceased-estate notice | Any, about an earlier owner | 65,137 | 4.2% | 3.6% | 4.2% | 3.9% | 8% | 16% |

Rounds chosen for each fit (0 means the kind added nothing in that fit): bankruptcy orders 16, 18, 24, 29, 31, 32, 34, 35, 38, 39; deceased-estate notices 57, 60, 62, 62, 67, 72, 74, 83, 89, 99.
In the product: bankruptcy orders (35 rounds), deceased-estate notices (156 rounds).
