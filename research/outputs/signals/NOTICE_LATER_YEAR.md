# The ranking with notices against 2019

The deployed model was fitted on 2001 to 2018 and the notice steps on 2017 and 2018. Here both score the 1,349,789 homes of
the test chunks on 1 January 2019, as the product does, and the ranking is set against the sales of 2019: a year no part
of it was fitted on. The 2019 sale records undercount late registrations (3.3% sold against 3.7% expected),
which lowers every rate alike and leaves the comparison standing.

## Sellers found in the best tenth of each postcode district, times random

| Owned for | Homes | Deployed model | With notices | Change (95% range) | Bankruptcy orders alone | Deceased-estate notices alone |
|---|---|---|---|---|---|---|
| All | 1,349,789 | 1.759 | 1.786 | +0.027 (+0.020 to +0.033) | +0.001 (-0.001 to +0.003) | +0.027 (+0.021 to +0.033) |
| Under 10 years | 626,542 | 1.782 | 1.794 | +0.012 (+0.006 to +0.018) | +0.001 (-0.001 to +0.003) | +0.010 (+0.004 to +0.017) |
| 10 to 19 years | 555,005 | 1.502 | 1.527 | +0.025 (+0.014 to +0.037) | -0.001 (-0.006 to +0.005) | +0.025 (+0.016 to +0.036) |
| 20 years or more | 168,242 | 1.354 | 1.472 | +0.118 (+0.081 to +0.158) | +0.010 (-0.008 to +0.029) | +0.108 (+0.075 to +0.144) |

## The homes with a notice

| Notice | Published | Homes | Sold in 2019 | Deployed model said | With the step | In the best tenth before | After |
|---|---|---|---|---|---|---|---|
| Bankruptcy order | 1 to 6 months before | 332 | 2.7% | 3.7% | 3.8% | 10% | 10% |
| Bankruptcy order | 7 to 12 months before | 344 | 4.1% | 3.9% | 4.5% | 14% | 25% |
| Bankruptcy order | 13 to 24 months before | 542 | 5.3% | 3.9% | 4.8% | 11% | 29% |
| Bankruptcy order | 25 to 36 months before | 499 | 3.6% | 3.8% | 4.7% | 12% | 31% |
| Bankruptcy order | 37 to 48 months before | 503 | 2.0% | 3.7% | 4.6% | 10% | 28% |
| Bankruptcy order | Any time in the window, about an earlier owner | 249 | 2.8% | 3.0% | 3.2% | 6% | 8% |
| Bankruptcy order | Every home with one | 2,469 | 3.5% | 3.7% | 4.4% | 11% | 24% |
| Deceased-estate notice | 1 to 6 months before | 315 | 27.3% | 3.4% | 28.7% | 7% | 81% |
| Deceased-estate notice | 7 to 12 months before | 232 | 16.4% | 3.5% | 17.7% | 7% | 82% |
| Deceased-estate notice | 13 to 24 months before | 432 | 7.2% | 3.5% | 8.8% | 6% | 71% |
| Deceased-estate notice | 25 to 36 months before | 317 | 3.8% | 3.6% | 5.0% | 4% | 38% |
| Deceased-estate notice | 37 to 48 months before | 314 | 3.5% | 3.8% | 4.7% | 8% | 30% |
| Deceased-estate notice | Any time in the window, about an earlier owner | 3,450 | 3.9% | 3.3% | 3.8% | 8% | 13% |
| Deceased-estate notice | Every home with one | 5,060 | 6.2% | 3.4% | 6.5% | 7% | 28% |

Log loss on the 7,527 homes with a notice: 0.20968 before, 0.18536 with the step.
