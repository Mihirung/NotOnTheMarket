# Notices in The Gazette: bankruptcy orders and deceased estates

**Verdict:** add the notices: homes with a notice are scored better on homes and a year the step was not fitted on, and the best tenth is no worse (too few homes carry a notice to move it measurably)

Homes are scored on 1 January. The deployed model is kept; for each kind of notice a small second step reads the months
since the latest notice at the home, how long the home had been owned when it appeared, and how many there were, and adds
to the deployed model's log-odds. Notices from the 48 months before the scoring day count. Only the home and the
month of publication are used; no name is held. A home with no notice keeps its score exactly.

## What the notices say on their own

Every home-year of 2017 and 2018 with a notice, against what the deployed model expected of the same homes.

| Notice | Published | Home-years | Sold in the year (95% range) | The model said | Times (95% range) |
|---|---|---|---|---|---|
| Bankruptcy order | 1 to 6 months before | 5,961 | 3.8% (3.3% to 4.3%) | 4.0% | 0.94 (0.81 to 1.06) |
| Bankruptcy order | 7 to 12 months before | 5,665 | 4.7% (4.2% to 5.3%) | 4.1% | 1.14 (1.00 to 1.28) |
| Bankruptcy order | 13 to 24 months before | 11,018 | 5.4% (5.0% to 5.9%) | 4.2% | 1.31 (1.20 to 1.42) |
| Bankruptcy order | 25 to 36 months before | 11,965 | 4.9% (4.5% to 5.3%) | 4.0% | 1.21 (1.11 to 1.31) |
| Bankruptcy order | 37 to 48 months before | 13,936 | 5.2% (4.9% to 5.6%) | 4.0% | 1.29 (1.20 to 1.39) |
| Bankruptcy order | Any time in the window, about an earlier owner | 7,468 | 3.6% (3.1% to 4.0%) | 3.3% | 1.09 (0.96 to 1.24) |

## Are the homes with a notice better scored?

Log loss on every home-year with a notice (lower is better), each scored by a step fitted on other homes in the other year.

| Notices | Home-years | Sold | Deployed model expected | Second step expected | Log loss before | After | Change (95% range) |
|---|---|---|---|---|---|---|---|
| Bankruptcy orders | 56,013 | 2,670 | 2,223 | 2,564 | 0.1914 | 0.1907 | -0.0007 (-0.0012 to -0.0003) |

## Sellers found in the best tenth of each postcode district, times random

Test homes of 2017 and 2018. Ranges are 95% and include the spread of the gain over 3 fits of the deployed model.

### Sells in the calendar year

| Owners | Deployed model | With the notices | Gain |
|---|---|---|---|
| All | 1.741 | 1.741 | -0.000 (-0.003 to +0.003) |
| Under 10 years | 1.740 | 1.739 | -0.002 (-0.003 to +0.000) |
| 10 to 19 years | 1.514 | 1.512 | -0.002 (-0.006 to +0.002) |
| 20 years or more | 1.291 | 1.297 | +0.006 (-0.012 to +0.025) |

### Completes July to June

| Owners | Deployed model | With the notices | Gain |
|---|---|---|---|
| All | 1.662 | 1.660 | -0.002 (-0.005 to +0.000) |
| Under 10 years | 1.620 | 1.619 | -0.002 (-0.004 to +0.000) |
| 10 to 19 years | 1.486 | 1.483 | -0.003 (-0.008 to +0.003) |
| 20 years or more | 1.314 | 1.318 | +0.003 (-0.015 to +0.024) |

### Completes July to June, not yet listed

| Owners | Deployed model | With the notices | Gain |
|---|---|---|---|
| All | 1.691 | 1.689 | -0.002 (-0.004 to +0.001) |
| Under 10 years | 1.636 | 1.634 | -0.001 (-0.004 to +0.001) |
| 10 to 19 years | 1.519 | 1.516 | -0.003 (-0.007 to +0.002) |
| 20 years or more | 1.334 | 1.338 | +0.004 (-0.013 to +0.024) |

## The homes with a notice

The first four columns are every home; the last three are the test homes alone.

| Notice | Published | Home-years | Sold in the year | Deployed model said | Second step says | Sold later, not yet listed | In the best tenth before | After |
|---|---|---|---|---|---|---|---|---|
| Bankruptcy order | 1 to 6 months before | 5,961 | 3.8% | 4.0% | 4.2% | 4.9% | 11% | 11% |
| Bankruptcy order | 7 to 12 months before | 5,665 | 4.7% | 4.1% | 4.7% | 4.3% | 14% | 22% |
| Bankruptcy order | 13 to 24 months before | 11,018 | 5.4% | 4.2% | 4.9% | 4.6% | 12% | 23% |
| Bankruptcy order | 25 to 36 months before | 11,965 | 4.9% | 4.0% | 4.8% | 3.8% | 10% | 20% |
| Bankruptcy order | 37 to 48 months before | 13,936 | 5.2% | 4.0% | 4.9% | 4.3% | 8% | 23% |
| Bankruptcy order | Any, owner bought before it | 48,545 | 5.0% | 4.1% | 4.8% | 4.3% | 10% | 21% |
| Bankruptcy order | Any, about an earlier owner | 7,468 | 3.6% | 3.3% | 3.4% | 4.2% | 7% | 10% |

Rounds chosen for each fit (0 means the kind added nothing in that fit): bankruptcy orders 18, 18, 26, 29, 31, 33, 35, 35, 36, 39.
In the product: bankruptcy orders (36 rounds).
