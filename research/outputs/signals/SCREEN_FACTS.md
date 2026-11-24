# Screen: past intent and home facts from the energy certificates

First step: `+HOUSE+AREA+PD@100.npy`. Homes that sell later and were not yet listed on the scoring day, found in the best
tenth of each postcode district, times random, test years 2017 and 2018. Each gain is against the same second
step (which has the first certificate family) without the new columns. Ranges are 95% and cover sampling only.

| Owners | First step | Second step | With all new columns | Gain | Gain, nine months out or more | Intent on the home | Facts about the home | Intent in the pool | Facts for the postcode |
|---|---|---|---|---|---|---|---|---|---|
| all | 1.690 | 1.692 | 1.706 | +0.014 (-0.004 to +0.032) | +0.008 (-0.009 to +0.027) | -0.000 (-0.009 to +0.011) | +0.004 (-0.007 to +0.014) | +0.008 (-0.004 to +0.022) | +0.006 (-0.011 to +0.024) |
| t0_9 | 1.638 | 1.653 | 1.643 | -0.010 (-0.036 to +0.016) | -0.019 (-0.047 to +0.008) | +0.004 (-0.010 to +0.019) | -0.011 (-0.031 to +0.008) | +0.003 (-0.017 to +0.023) | -0.018 (-0.043 to +0.007) |
| t10_19 | 1.519 | 1.528 | 1.557 | +0.029 (+0.002 to +0.058) | +0.031 (+0.002 to +0.065) | +0.008 (-0.009 to +0.024) | +0.004 (-0.010 to +0.019) | +0.009 (-0.016 to +0.033) | +0.030 (+0.004 to +0.057) |
| t20p | 1.334 | 1.425 | 1.360 | -0.066 (-0.144 to +0.026) | -0.068 (-0.164 to +0.025) | +0.015 (-0.033 to +0.073) | +0.052 (-0.001 to +0.108) | -0.013 (-0.092 to +0.080) | -0.025 (-0.097 to +0.051) |

## What the columns say on their own

| Homes on 1 January | Home-years | Sell later, not yet listed | Complete nine months out or more | The model said (calendar year) |
|---|---|---|---|---|
| UPRN known | 398,678 | 4.0% | 3.1% | 4.2% |
| UPRN known, a sale certificate over a year old and no sale | 8,101 | 1.3% | 4.0% | 4.7% |
| UPRN known, that certificate over 24 months old | 6,214 | 1.1% | 3.7% | 4.8% |
| UPRN known, a sale certificate in the last 12 months | 2,902 | 1.1% | 6.9% | 4.5% |
| UPRN known, a rental certificate since buying | 4,262 | 3.4% | 2.6% | 4.5% |
| UPRN known, a grant-scheme certificate since buying | 14,827 | 3.8% | 3.0% | 4.2% |
| UPRN known, let privately when last assessed | 8,764 | 3.3% | 2.4% | 4.2% |
| UPRN known, a bungalow | 49,427 | 3.4% | 2.6% | 3.9% |
| UPRN not known | 2,192,753 | 3.6% | 2.7% | 4.0% |
| UPRN not known, left-over sale certificates 24 to 60 months old | 444,557 | 3.6% | 2.7% | 3.6% |
| UPRN not known, at least one for every four homes | 123,291 | 3.5% | 2.6% | 3.5% |
