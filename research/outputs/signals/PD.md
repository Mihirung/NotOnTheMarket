# PD: what it is worth

What the houses of the postcode could add without planning permission (permitted development, planning constraints from planning.data.gov.uk and DataMapWales), and their price per m2

**Verdict:** add it: the model finds more sellers and the range is clear of zero

Coverage: 98.9% of postcodes, 99.2% of the home-years the model is tested on.

## Does it make the national model better?

| Owners | Current model | With this family | Gain | 95% range |
|---|---|---|---|---|
| All | 1.689 | 1.727 | +0.038 | +0.020 to +0.053 |
| Under 10 years | 1.705 | 1.751 | +0.046 | +0.023 to +0.069 |
| 10 to 19 years | 1.486 | 1.507 | +0.021 | -0.008 to +0.046 |
| 20 years or more | 1.233 | 1.283 | +0.050 | -0.024 to +0.123 |

Sellers found in the best tenth of each postcode district, times random, 2017 and 2018.

## Each column: sale timing, what is left on top of the model, and price

| Column | Sale chance, points a year per step | Same sign in regions | Left on top of the model | Price per step |
|---|---|---|---|---|
| pd_rear_share | +0.044 (+0.030 to +0.056) | 7 of 8 | +0.044 (+0.018 to +0.070) | -2.5% (-2.6 to -2.4) |
| pd_rear_prior_m | +0.019 (+0.008 to +0.030) | 5 of 8 | -0.018 (-0.043 to +0.005) | -1.2% (-1.3 to -1.1) |
| pd_loft_share | -0.014 (-0.025 to -0.001) | 4 of 8 | +0.082 (+0.061 to +0.106) | -6.2% (-6.2 to -6.1) |
| pd_two_storey_share | -0.024 (-0.037 to -0.013) | 5 of 8 | +0.017 (-0.006 to +0.044) | -0.9% (-1.0 to -0.9) |
| pd_side_share | +0.027 (+0.013 to +0.040) | 5 of 8 | +0.029 (+0.007 to +0.050) | +1.2% (+1.1 to +1.3) |
| pd_heritage_share | +0.056 (+0.043 to +0.067) | 5 of 8 | -0.041 (-0.063 to -0.020) | +4.5% (+4.4 to +4.6) |
| pd_add_m2 | -0.065 (-0.077 to -0.052) | 8 of 8 | -0.052 (-0.073 to -0.024) | +5.9% (+5.8 to +6.0) |
| pd_add_pct | -0.003 (-1.953 to -0.002) | 5 of 8 | -0.000 (-0.001 to +10.587) | -0.6% (-27.6 to -0.5) |
| price_m2 | +0.174 (+0.161 to +0.189) | 8 of 8 | -0.142 (-0.160 to -0.120) | +6.6% (+6.3 to +6.8) |
| flat_share | -0.171 (-0.186 to -0.155) | 8 of 8 | -0.210 (-0.233 to -0.184) | +0.8% (+0.6 to +0.9) |
| listed_share | +0.011 (-0.002 to +0.023) | 2 of 8 | +0.009 (-0.013 to +0.033) | +3.5% (+3.4 to +3.6) |

A step is one standard deviation of the column across the country. Ranges are 95% block-bootstrap ranges.
