# The notice step for the model aimed at homes not yet on the market

**Verdict:** add the notices: homes with a notice are scored better on homes and a year the step was not fitted on, and the best tenth is no worse

Homes are scored on 1 January by the later-sales model with energy certificates (LATE_MODEL.md). A later seller completes
between July of that year and June of the next. For each kind of notice a small second step reads the months since the
latest notice at the home, how long the home had been owned when it appeared, and how many there were, and adds to the
first step's log-odds. Test homes of 2017 and 2018; each home-year is scored by a step fitted on other homes in the other year.

## Are the homes with a notice better scored?

| Notices | Home-years | Sold later | First step expected | With the step | Log loss before | After | Change (95% range) |
|---|---|---|---|---|---|---|---|
| Both | 150,186 | 7,498 | 5,093 | 7,532 | 0.1993 | 0.1930 | -0.0063 (-0.0073 to -0.0053) |
| Bankruptcy orders | 55,994 | 2,554 | 1,923 | 2,453 | 0.1867 | 0.1871 | +0.0004 (-0.0005 to +0.0012) |
| Deceased-estate notices | 94,269 | 4,945 | 3,172 | 5,081 | 0.2066 | 0.1964 | -0.0103 (-0.0117 to -0.0086) |

## Sellers found in the best tenth of each postcode district, times random

### Completes July to June

| Owners | First step | With the notices | Gain (95% range) | Bankruptcy orders alone | Deceased-estate notices alone |
|---|---|---|---|---|---|
| All | 1.696 | 1.699 | +0.004 (-0.000 to +0.008) | -0.004 (-0.006 to -0.002) | +0.006 (+0.003 to +0.010) |
| Under 10 years | 1.640 | 1.639 | -0.001 (-0.007 to +0.005) | -0.003 (-0.005 to +0.000) | +0.002 (-0.003 to +0.007) |
| 10 to 19 years | 1.577 | 1.585 | +0.008 (+0.003 to +0.014) | +0.000 (-0.004 to +0.004) | +0.009 (+0.004 to +0.013) |
| 20 years or more | 1.613 | 1.617 | +0.003 (-0.019 to +0.024) | -0.007 (-0.022 to +0.008) | +0.012 (-0.008 to +0.028) |

### Completes July to June, not yet listed

| Owners | First step | With the notices | Gain (95% range) | Bankruptcy orders alone | Deceased-estate notices alone |
|---|---|---|---|---|---|
| All | 1.604 | 1.609 | +0.004 (+0.000 to +0.008) | -0.004 (-0.006 to -0.002) | +0.007 (+0.004 to +0.010) |
| Under 10 years | 1.565 | 1.564 | -0.001 (-0.007 to +0.005) | -0.003 (-0.005 to +0.000) | +0.002 (-0.004 to +0.007) |
| 10 to 19 years | 1.415 | 1.425 | +0.010 (+0.004 to +0.016) | +0.001 (-0.002 to +0.005) | +0.009 (+0.004 to +0.013) |
| 20 years or more | 1.335 | 1.345 | +0.010 (-0.011 to +0.032) | -0.004 (-0.018 to +0.010) | +0.015 (-0.006 to +0.032) |

### Sells in the calendar year

| Owners | First step | With the notices | Gain (95% range) | Bankruptcy orders alone | Deceased-estate notices alone |
|---|---|---|---|---|---|
| All | 1.927 | 1.943 | +0.016 (+0.012 to +0.020) | -0.001 (-0.002 to +0.002) | +0.015 (+0.012 to +0.019) |
| Under 10 years | 1.868 | 1.870 | +0.002 (-0.004 to +0.008) | -0.003 (-0.005 to -0.000) | +0.004 (-0.002 to +0.009) |
| 10 to 19 years | 1.904 | 1.924 | +0.020 (+0.013 to +0.027) | +0.001 (-0.004 to +0.005) | +0.020 (+0.014 to +0.026) |
| 20 years or more | 2.154 | 2.180 | +0.026 (+0.004 to +0.053) | -0.006 (-0.022 to +0.010) | +0.034 (+0.014 to +0.056) |

## The homes with a notice

| Notice | Published | Home-years | Sold later | First step said | With the step | In the best tenth before | After |
|---|---|---|---|---|---|---|---|
| Bankruptcy order | 1 to 6 months before | 5,955 | 4.0% | 3.5% | 4.1% | 11% | 18% |
| Bankruptcy order | 7 to 12 months before | 5,665 | 4.4% | 3.6% | 4.4% | 11% | 30% |
| Bankruptcy order | 13 to 24 months before | 11,013 | 5.2% | 3.6% | 4.7% | 11% | 32% |
| Bankruptcy order | 25 to 36 months before | 11,965 | 4.5% | 3.4% | 4.4% | 10% | 29% |
| Bankruptcy order | 37 to 48 months before | 13,928 | 4.8% | 3.4% | 4.5% | 9% | 32% |
| Bankruptcy order | Any, owner bought before it | 48,526 | 4.7% | 3.5% | 4.5% | 10% | 30% |
| Bankruptcy order | Any, about an earlier owner | 7,468 | 3.9% | 3.1% | 3.9% | 8% | 21% |
| Deceased-estate notice | 1 to 6 months before | 5,685 | 15.6% | 3.5% | 14.8% | 9% | 86% |
| Deceased-estate notice | 7 to 12 months before | 4,891 | 8.8% | 3.4% | 9.1% | 6% | 76% |
| Deceased-estate notice | 13 to 24 months before | 7,166 | 6.2% | 3.4% | 6.0% | 6% | 58% |
| Deceased-estate notice | 25 to 36 months before | 6,246 | 4.7% | 3.6% | 5.1% | 9% | 44% |
| Deceased-estate notice | 37 to 48 months before | 5,144 | 4.5% | 3.5% | 4.5% | 8% | 27% |
| Deceased-estate notice | Any, owner bought before it | 29,132 | 7.9% | 3.5% | 7.8% | 8% | 58% |
| Deceased-estate notice | Any, about an earlier owner | 65,137 | 4.1% | 3.3% | 4.3% | 6% | 23% |

In the product: deceased-estate notices (100 rounds). Left out, because the homes that have one are not better scored on this target: bankruptcy orders. With what is in, the best tenth finds 1.702 times random.
