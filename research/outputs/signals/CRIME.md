# CRIME: what it is worth

Recorded crime and anti-social behaviour per 1,000 residents a year, February 2014 to January 2017 (data.police.uk, crime_signals.py)

**Verdict:** do not add it to the model: no gain clear of zero and of the fit's own noise; use it for search and pricing

Coverage: 99.4% of postcodes, 99.8% of the home-years the model is tested on.

## Does it make the national model better?

| Owners | Current model | With this family | Gain | 95% range |
|---|---|---|---|---|
| All | 1.741 | 1.724 | -0.017 | -0.050 to +0.018 |
| Under 10 years | 1.740 | 1.746 | +0.005 | -0.027 to +0.035 |
| 10 to 19 years | 1.514 | 1.517 | +0.003 | -0.031 to +0.041 |
| 20 years or more | 1.291 | 1.280 | -0.011 | -0.071 to +0.057 |

Sellers found in the best tenth of each postcode district, times random, 2017 and 2018. The current model is the deployed one: BASE + HIST + GEO + VIEW + HOUSE + AREA + PD. The range includes the fit's own randomness (SEED_NOISE.md): two fits of the same model differ by up to about 0.02, so a gain smaller than that is not evidence.

## Each column: sale timing, what is left on top of the model, and price

| Column | Sale chance, points a year per step | Same sign in regions | Left on top of the model | Price per step |
|---|---|---|---|---|
| crime_all | -0.159 (-0.170 to -0.149) | 8 of 8 | -0.031 (-0.053 to -0.008) | -1.2% (-1.4 to -1.0) |
| burglary | -0.193 (-0.203 to -0.183) | 8 of 8 | -0.006 (-0.028 to +0.014) | +0.7% (+0.6 to +0.8) |
| antisocial | -0.148 (-0.160 to -0.137) | 8 of 8 | +0.009 (-0.015 to +0.031) | -1.9% (-2.1 to -1.7) |
| violence | -0.172 (-0.183 to -0.162) | 8 of 8 | -0.029 (-0.054 to -0.006) | -2.0% (-2.2 to -1.8) |
| vehicle | -0.179 (-0.190 to -0.170) | 7 of 8 | -0.062 (-0.081 to -0.042) | +1.0% (+0.9 to +1.1) |
| damage | -0.203 (-0.213 to -0.194) | 8 of 8 | +0.045 (+0.018 to +0.067) | -3.1% (-3.3 to -3.0) |
| drugs | -0.144 (-0.154 to -0.133) | 8 of 8 | -0.049 (-0.072 to -0.025) | -0.6% (-0.7 to -0.4) |
| theft | -0.114 (-0.126 to -0.103) | 8 of 8 | -0.079 (-0.099 to -0.057) | +0.3% (+0.2 to +0.5) |

A step is one standard deviation of the column across the country. Ranges are 95% block-bootstrap ranges.
