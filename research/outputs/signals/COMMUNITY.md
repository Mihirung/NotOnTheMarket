# COMMUNITY: what it is worth

Ethnicity and religion of the output area, 2011 Census (people_signals.py). Measured, never deployed automatically: special category data under UK GDPR when used to treat people differently, so it needs legal sign-off. Used to audit fairness

**Verdict:** do not add it to the model: no gain clear of zero; use it for search and pricing

Coverage: 99.4% of postcodes, 99.8% of the home-years the model is tested on.

## Does it make the national model better?

| Owners | Current model | With this family | Gain | 95% range |
|---|---|---|---|---|
| All | 1.741 | 1.721 | -0.020 | -0.034 to -0.004 |
| Under 10 years | 1.740 | 1.720 | -0.021 | -0.041 to +0.001 |
| 10 to 19 years | 1.514 | 1.530 | +0.016 | -0.013 to +0.039 |
| 20 years or more | 1.291 | 1.322 | +0.031 | -0.034 to +0.091 |

Sellers found in the best tenth of each postcode district, times random, 2017 and 2018. The current model is the deployed one: BASE + HIST + GEO + VIEW + HOUSE + AREA + PD.

## Each column: sale timing, what is left on top of the model, and price

| Column | Sale chance, points a year per step | Same sign in regions | Left on top of the model | Price per step |
|---|---|---|---|---|
| white_british | +0.401 (+0.390 to +0.412) | 8 of 8 | +0.250 (+0.234 to +0.268) | +6.4% (+6.2 to +6.6) |
| white_other | -0.227 (-0.240 to -0.211) | 8 of 8 | -0.280 (-0.298 to -0.263) | -0.8% (-0.9 to -0.6) |
| mixed | -0.155 (-0.167 to -0.144) | 7 of 8 | -0.176 (-0.194 to -0.157) | -2.6% (-2.7 to -2.5) |
| indian | -0.207 (-0.216 to -0.198) | 8 of 8 | -0.137 (-0.153 to -0.119) | +1.8% (+1.7 to +1.9) |
| pakistani | -0.199 (-0.209 to -0.189) | 8 of 8 | -0.017 (-0.036 to +0.002) | -1.5% (-1.6 to -1.4) |
| bangladeshi | -0.166 (-0.174 to -0.157) | 8 of 8 | -0.065 (-0.085 to -0.048) | -1.7% (-1.8 to -1.6) |
| chinese | -0.142 (-0.152 to -0.131) | 8 of 8 | -0.168 (-0.189 to -0.145) | +0.0% (-0.1 to +0.1) |
| other_asian | -0.238 (-0.250 to -0.228) | 8 of 8 | -0.185 (-0.204 to -0.166) | -1.9% (-2.0 to -1.8) |
| black_african | -0.219 (-0.228 to -0.210) | 8 of 8 | -0.137 (-0.156 to -0.118) | -4.3% (-4.5 to -4.2) |
| black_caribbean | -0.174 (-0.183 to -0.163) | 7 of 8 | -0.108 (-0.130 to -0.091) | -4.4% (-4.5 to -4.3) |
| other_ethnic | -0.233 (-0.246 to -0.220) | 8 of 8 | -0.168 (-0.188 to -0.150) | -1.2% (-1.4 to -1.1) |
| ethnic_mix | -0.357 (-0.368 to -0.344) | 8 of 8 | -0.261 (-0.279 to -0.245) | -5.1% (-5.2 to -4.9) |
| christian | +0.189 (+0.177 to +0.201) | 8 of 8 | +0.160 (+0.138 to +0.178) | +5.6% (+5.5 to +5.7) |
| buddhist | -0.085 (-0.097 to -0.076) | 7 of 8 | -0.157 (-0.178 to -0.138) | -0.5% (-0.6 to -0.4) |
| hindu | -0.182 (-0.190 to -0.172) | 8 of 8 | -0.150 (-0.166 to -0.135) | +1.1% (+1.0 to +1.2) |
| jewish | -0.028 (-0.038 to -0.019) | 7 of 8 | -0.054 (-0.074 to -0.031) | +3.7% (+3.4 to +3.9) |
| muslim | -0.298 (-0.309 to -0.289) | 8 of 8 | -0.092 (-0.114 to -0.075) | -3.4% (-3.5 to -3.2) |
| sikh | -0.137 (-0.143 to -0.129) | 8 of 8 | -0.057 (-0.073 to -0.037) | +1.4% (+1.4 to +1.5) |
| other_religion | -0.042 (-0.052 to -0.032) | 7 of 8 | -0.099 (-0.120 to -0.075) | -0.5% (-0.6 to -0.5) |
| no_religion | +0.187 (+0.178 to +0.198) | 6 of 8 | +0.002 (-0.021 to +0.026) | -4.6% (-4.7 to -4.5) |
| religion_not_stated | +0.015 (+0.005 to +0.026) | 4 of 8 | -0.089 (-0.110 to -0.068) | +0.2% (+0.1 to +0.3) |

A step is one standard deviation of the column across the country. Ranges are 95% block-bootstrap ranges.
