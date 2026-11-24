# SCHOOLS: what it is worth

Schools nearby: Ofsted grades as at August 2016, selective and independent schools (schools_access_signals.py)

**Verdict:** do not add it to the model: no gain clear of zero and of the fit's own noise; use it for search and pricing

Coverage: 99.4% of postcodes, 99.8% of the home-years the model is tested on.

## Does it make the national model better?

| Owners | Current model | With this family | Gain | 95% range |
|---|---|---|---|---|
| All | 1.741 | 1.728 | -0.013 | -0.046 to +0.020 |
| Under 10 years | 1.740 | 1.739 | -0.001 | -0.030 to +0.030 |
| 10 to 19 years | 1.514 | 1.521 | +0.007 | -0.029 to +0.040 |
| 20 years or more | 1.291 | 1.260 | -0.031 | -0.102 to +0.037 |

Sellers found in the best tenth of each postcode district, times random, 2017 and 2018. The current model is the deployed one: BASE + HIST + GEO + VIEW + HOUSE + AREA + PD. The range includes the fit's own randomness (SEED_NOISE.md): two fits of the same model differ by up to about 0.02, so a gain smaller than that is not evidence.

## Each column: sale timing, what is left on top of the model, and price

| Column | Sale chance, points a year per step | Same sign in regions | Left on top of the model | Price per step |
|---|---|---|---|---|
| km_primary_good | +0.029 (+0.020 to +0.039) | 4 of 8 | +0.007 (-0.015 to +0.031) | +4.8% (+4.7 to +4.9) |
| km_primary_outstanding | +0.085 (+0.074 to +0.096) | 6 of 8 | +0.035 (+0.010 to +0.059) | +1.7% (+1.5 to +1.9) |
| km_secondary_good | +0.072 (+0.062 to +0.082) | 5 of 8 | +0.040 (+0.018 to +0.062) | +4.8% (+4.7 to +5.0) |
| km_secondary_outstanding | +0.101 (+0.091 to +0.112) | 7 of 8 | +0.036 (+0.014 to +0.065) | +3.5% (+3.1 to +3.9) |
| good_primaries_2km | -0.257 (-0.268 to -0.246) | 8 of 8 | -0.134 (-0.153 to -0.113) | -6.8% (-7.1 to -6.4) |
| km_primary | -0.047 (-0.058 to -0.036) | 7 of 8 | +0.122 (+0.095 to +0.154) | +70.1% (+68.4 to +72.0) |
| km_secondary | -0.035 (-0.046 to -0.024) | 3 of 8 | +0.126 (+0.098 to +0.154) | +19.8% (+19.1 to +20.4) |
| km_grammar | +0.068 (+0.054 to +0.081) | 5 of 8 | +0.026 (+0.006 to +0.051) | +0.7% (-0.3 to +1.7) |
| km_independent | -0.015 (-0.025 to -0.002) | 2 of 8 | +0.155 (+0.132 to +0.182) | +0.5% (+0.0 to +1.1) |

A step is one standard deviation of the column across the country. Ranges are 95% block-bootstrap ranges.
