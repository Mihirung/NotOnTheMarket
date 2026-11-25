# A 60-month look-back for bankruptcy orders

A test, not a change to the product. The product reads notices published in the 48 months before the scoring day.
Here bankruptcy orders are read 60 months back for the home-years of 2017 and 2018, with every other notice as deployed.

## The homes with an older notice

| Latest notice | Home-years | Sold in the year | Deployed model said | Times (95% range) | Step says |
|---|---|---|---|---|---|
| 25 to 36 months before | 11,965 | 4.9% | 4.0% | 1.21 (1.11 to 1.31) | 4.8% |
| 37 to 48 months before | 13,928 | 5.2% | 4.0% | 1.29 (1.20 to 1.39) | 4.8% |
| 49 to 60 months before | 17,129 | 4.3% | 4.0% | 1.05 (0.98 to 1.14) | 4.3% |
| 49 to 60 months before, about an earlier owner | 6,128 | 3.6% | 3.8% | 0.95 (0.82 to 1.08) | 3.7% |

## Sellers found in the best tenth of each postcode district, times random

| Owned for | No notices | 48 months | 60 months | 60 against 48 (95% range) |
|---|---|---|---|---|
| All | 1.741 | 1.759 | 1.760 | +0.000 (-0.001 to +0.001) |
| Under 10 years | 1.740 | 1.750 | 1.750 | -0.001 (-0.002 to +0.001) |
| 10 to 19 years | 1.514 | 1.536 | 1.535 | -0.001 (-0.003 to +0.001) |
| 20 years or more | 1.291 | 1.351 | 1.354 | +0.003 (-0.007 to +0.015) |

Log loss on the 8,009 test home-years with one in 60 months: 0.18685 with no notices, 0.18633 on 48 months, 0.18681 on 60.

## Reading it

The longer look-back does not find more sellers: the change is not clear of zero. The product keeps 48 months.
