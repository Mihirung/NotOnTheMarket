# LIFE: what it is worth

Later life: the owner's likely age from years owned and the 2011 age mix of the output area, and the yearly chance of a death or move into care at that age, moved by local life expectancy (life_signals.py). For the model's ranking only; never shown

**Verdict:** do not add it to the model: no gain clear of zero and of the fit's own noise; it stays out of search and pricing too (model ranking only)

Coverage: 99.4% of postcodes, 99.8% of the home-years the model is tested on.

## Does it make the national model better?

| Owners | Current model | With this family | Gain | 95% range |
|---|---|---|---|---|
| All | 1.741 | 1.730 | -0.011 | -0.043 to +0.024 |
| Under 10 years | 1.740 | 1.749 | +0.008 | -0.023 to +0.042 |
| 10 to 19 years | 1.514 | 1.526 | +0.013 | -0.023 to +0.048 |
| 20 years or more | 1.291 | 1.283 | -0.008 | -0.081 to +0.072 |

Sellers found in the best tenth of each postcode district, times random, 2017 and 2018. The current model is the deployed one: BASE + HIST + GEO + VIEW + HOUSE + AREA + PD. The range includes the fit's own randomness (SEED_NOISE.md): two fits of the same model differ by up to about 0.02, so a gain smaller than that is not evidence.

## Each column: sale timing, what is left on top of the model, and price

| Column | Sale chance, points a year per step | Same sign in regions | Left on top of the model | Price per step |
|---|---|---|---|---|
| owner_age | +0.024 (+0.009 to +0.037) | 1 of 8 | +0.018 (-0.007 to +0.041) |  |
| p_owner_75 | +0.068 (+0.057 to +0.079) | 6 of 8 | +0.028 (+0.003 to +0.053) |  |
| p_owner_85 | +0.096 (+0.084 to +0.106) | 8 of 8 | +0.018 (-0.009 to +0.041) |  |
| p_exit | +0.054 (+0.043 to +0.065) | 6 of 8 | +0.059 (+0.035 to +0.084) |  |
| p_exit_alone | +0.037 (+0.026 to +0.049) | 6 of 8 | +0.040 (+0.015 to +0.063) |  |
| le65 | +0.262 (+0.247 to +0.276) | 8 of 8 | -0.229 (-0.253 to -0.208) | +4.7% (+4.4 to +5.2) |
| health_dep | -0.307 (-0.320 to -0.296) | 8 of 8 | +0.179 (+0.156 to +0.201) | -8.9% (-9.1 to -8.8) |
| older_income_dep | -0.344 (-0.357 to -0.333) | 7 of 8 | +0.020 (-0.004 to +0.041) | -7.6% (-7.7 to -7.5) |
| alone_share | -0.084 (-0.096 to -0.070) | 7 of 8 | -0.059 (-0.080 to -0.037) |  |

A step is one standard deviation of the column across the country. Ranges are 95% block-bootstrap ranges.
