# AREA: what it is worth

From the ONS UPRN Directory: deprivation rank (IMD 2025), rural or urban, and the census output-area classification (2021), as the share of the postcode's addresses in each group

**Verdict:** add it: the model finds more sellers and the range is clear of zero

Coverage: 99.4% of postcodes, 99.8% of the home-years the model is tested on.

## Does it make the national model better?

| Owners | Current model | With this family | Gain | 95% range |
|---|---|---|---|---|
| All | 1.689 | 1.713 | +0.024 | +0.009 to +0.038 |
| Under 10 years | 1.705 | 1.740 | +0.035 | +0.006 to +0.055 |
| 10 to 19 years | 1.486 | 1.513 | +0.027 | +0.001 to +0.049 |
| 20 years or more | 1.233 | 1.256 | +0.022 | -0.043 to +0.089 |

Sellers found in the best tenth of each postcode district, times random, 2017 and 2018.

## Each column: sale timing, what is left on top of the model, and price

| Column | Sale chance, points a year per step | Same sign in regions | Left on top of the model | Price per step |
|---|---|---|---|---|
| imd_rank | +0.368 (+0.355 to +0.379) | 8 of 8 | -0.044 (-0.064 to -0.023) | +10.2% (+10.1 to +10.3) |
| rural | +0.079 (+0.069 to +0.091) | 5 of 8 | +0.048 (+0.026 to +0.071) | +6.1% (+6.0 to +6.3) |
| oac_1 | +0.045 (+0.033 to +0.054) | 6 of 8 | +0.028 (+0.002 to +0.048) | +3.4% (+3.4 to +3.5) |
| oac_2 | +0.169 (+0.158 to +0.179) | 8 of 8 | +0.114 (+0.093 to +0.140) | +1.6% (+1.6 to +1.7) |
| oac_3 | -0.146 (-0.157 to -0.132) | 8 of 8 | -0.191 (-0.214 to -0.172) | -0.7% (-0.8 to -0.5) |
| oac_4 | -0.277 (-0.288 to -0.265) | 8 of 8 | -0.093 (-0.114 to -0.070) | -3.1% (-3.2 to -3.0) |
| oac_5 | +0.037 (+0.028 to +0.048) | 7 of 8 | -0.030 (-0.049 to -0.005) | +3.4% (+3.3 to +3.5) |
| oac_6 | +0.075 (+0.063 to +0.087) | 6 of 8 | +0.031 (+0.002 to +0.059) | -2.5% (-2.6 to -2.4) |
| oac_7 | -0.079 (-0.087 to -0.069) | 7 of 8 | +0.072 (+0.047 to +0.096) | -4.3% (-4.4 to -4.3) |
| oac_8 | +0.002 (-0.009 to +0.016) | 3 of 8 | +0.006 (-0.015 to +0.031) | -0.2% (-0.3 to -0.1) |

A step is one standard deviation of the column across the country. Ranges are 95% block-bootstrap ranges.
