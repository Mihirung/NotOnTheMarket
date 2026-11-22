# AMENITY: what it is worth

Green and blue space (OS Open Greenspace, OS OpenMap Local) and pubs, takeaways and restaurants (Food Standards Agency hygiene register), by distance from the postcode centre

**Verdict:** do not add it to the model: no gain clear of zero; use it for search and pricing

Coverage: 99.4% of postcodes, 99.8% of the home-years the model is tested on.

## Does it make the national model better?

| Owners | Current model | With this family | Gain | 95% range |
|---|---|---|---|---|
| All | 1.689 | 1.693 | +0.004 | -0.011 to +0.019 |
| Under 10 years | 1.705 | 1.701 | -0.004 | -0.028 to +0.020 |
| 10 to 19 years | 1.486 | 1.505 | +0.019 | -0.005 to +0.043 |
| 20 years or more | 1.233 | 1.231 | -0.002 | -0.066 to +0.069 |

Sellers found in the best tenth of each postcode district, times random, 2017 and 2018.

## Each column: sale timing, what is left on top of the model, and price

| Column | Sale chance, points a year per step | Same sign in regions | Left on top of the model | Price per step |
|---|---|---|---|---|
| km_pub | +0.019 (+0.008 to +0.029) | 4 of 8 | +0.021 (-0.001 to +0.044) | +2.4% (+2.3 to +2.4) |
| pubs_1km | -0.112 (-0.124 to -0.101) | 8 of 8 | -0.083 (-0.106 to -0.060) | +0.9% (+0.7 to +1.2) |
| takeaways_1km | -0.239 (-0.249 to -0.229) | 8 of 8 | -0.099 (-0.118 to -0.084) | -3.6% (-3.8 to -3.4) |
| restaurants_1km | -0.145 (-0.157 to -0.134) | 8 of 8 | -0.142 (-0.163 to -0.124) | +1.8% (+1.5 to +2.1) |
| km_park | -0.026 (-0.037 to -0.018) | 7 of 8 | +0.009 (-0.017 to +0.033) | +3.8% (+3.7 to +3.9) |
| park_ha_1km | -0.038 (-0.050 to -0.027) | 5 of 8 | -0.020 (-0.047 to +0.003) | -0.2% (-0.3 to -0.1) |
| km_play | -0.031 (-0.041 to -0.022) | 7 of 8 | +0.032 (+0.009 to +0.052) | +5.4% (+5.3 to +5.5) |
| km_wood | -0.043 (-0.054 to -0.032) | 7 of 8 | -0.048 (-0.072 to -0.027) | -2.0% (-2.3 to -1.8) |
| km_water | +0.021 (+0.009 to +0.031) | 2 of 8 | -0.005 (-0.029 to +0.018) | +0.9% (+0.7 to +1.0) |
| km_sea | +0.012 (+0.002 to +0.025) | 5 of 8 | +0.036 (+0.012 to +0.063) | -1.4% (-2.7 to -0.2) |
| km_blue | +0.006 (-0.004 to +0.017) | 3 of 8 | -0.019 (-0.042 to +0.004) | -0.6% (-0.8 to -0.5) |

A step is one standard deviation of the column across the country. Ranges are 95% block-bootstrap ranges.
