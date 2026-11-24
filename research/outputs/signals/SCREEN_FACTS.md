# Screen: past intent and home facts from the energy certificates

First step: `+HOUSE+AREA+PD@100.npy`. Homes that sell later and were not yet listed on the scoring day, found in the best
tenth of each postcode district, times random, test years 2017 and 2018. Each gain is against the same second
step (which has the first certificate family) without the new columns. Ranges are 95% and cover sampling only.

| Owners | First step | Second step | With all new columns | Gain | Gain, nine months out or more | Intent on the home | Facts about the home | Intent in the pool | Facts for the postcode |
|---|---|---|---|---|---|---|---|---|---|
| all | 1.691 | 1.690 | 1.703 | +0.013 (-0.005 to +0.030) | +0.008 (-0.012 to +0.028) | +0.005 (-0.005 to +0.017) | +0.013 (-0.001 to +0.024) | +0.014 (+0.001 to +0.026) | +0.022 (+0.004 to +0.040) |
| t0_9 | 1.636 | 1.638 | 1.642 | +0.004 (-0.018 to +0.026) | -0.005 (-0.028 to +0.023) | +0.003 (-0.010 to +0.017) | -0.019 (-0.037 to -0.002) | +0.008 (-0.011 to +0.029) | +0.012 (-0.012 to +0.035) |
| t10_19 | 1.519 | 1.533 | 1.547 | +0.014 (-0.014 to +0.040) | +0.018 (-0.017 to +0.048) | +0.004 (-0.012 to +0.018) | +0.003 (-0.011 to +0.019) | +0.010 (-0.015 to +0.038) | +0.018 (-0.011 to +0.046) |
| t20p | 1.334 | 1.427 | 1.396 | -0.031 (-0.122 to +0.057) | -0.037 (-0.135 to +0.062) | +0.016 (-0.037 to +0.077) | +0.019 (-0.036 to +0.073) | -0.024 (-0.112 to +0.059) | -0.036 (-0.112 to +0.046) |

## What the columns say on their own

| Homes on 1 January | Home-years | Sell later, not yet listed | Complete nine months out or more | The model said (calendar year) |
|---|---|---|---|---|
| UPRN known | 398,678 | 4.1% | 3.1% | 4.2% |
| UPRN known, a sale certificate over a year old and no sale | 8,101 | 5.4% | 4.0% | 4.7% |
| UPRN known, that certificate over 24 months old | 6,214 | 4.9% | 3.7% | 4.8% |
| UPRN known, a sale certificate in the last 12 months | 2,902 | 1.1% | 6.9% | 4.5% |
| UPRN known, a rental certificate since buying | 4,262 | 3.5% | 2.6% | 4.5% |
| UPRN known, a grant-scheme certificate since buying | 14,827 | 3.9% | 3.0% | 4.2% |
| UPRN known, let privately when last assessed | 8,764 | 3.4% | 2.4% | 4.2% |
| UPRN known, a bungalow | 49,427 | 3.5% | 2.6% | 3.9% |
| UPRN not known | 2,192,753 | 3.6% | 2.7% | 4.0% |
| UPRN not known, left-over sale certificates 24 to 60 months old | 444,557 | 3.6% | 2.7% | 3.6% |
| UPRN not known, at least one for every four homes | 123,291 | 3.5% | 2.6% | 3.5% |
