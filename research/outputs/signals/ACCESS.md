# ACCESS: what it is worth

Transport: railway stations, underground, metro and tram stops, bus stops (NaPTAN), motorways and A roads (OS OpenMap Local) (schools_access_signals.py)

**Verdict:** do not add it to the model: no gain clear of zero and of the fit's own noise; use it for search and pricing

Coverage: 99.4% of postcodes, 99.8% of the home-years the model is tested on.

## Does it make the national model better?

| Owners | Current model | With this family | Gain | 95% range |
|---|---|---|---|---|
| All | 1.741 | 1.718 | -0.022 | -0.056 to +0.011 |
| Under 10 years | 1.740 | 1.742 | +0.001 | -0.028 to +0.032 |
| 10 to 19 years | 1.514 | 1.536 | +0.022 | -0.012 to +0.057 |
| 20 years or more | 1.291 | 1.320 | +0.029 | -0.042 to +0.097 |

Sellers found in the best tenth of each postcode district, times random, 2017 and 2018. The current model is the deployed one: BASE + HIST + GEO + VIEW + HOUSE + AREA + PD. The range includes the fit's own randomness (SEED_NOISE.md): two fits of the same model differ by up to about 0.02, so a gain smaller than that is not evidence.

## Each column: sale timing, what is left on top of the model, and price

| Column | Sale chance, points a year per step | Same sign in regions | Left on top of the model | Price per step |
|---|---|---|---|---|
| km_rail | +0.082 (+0.072 to +0.094) | 5 of 8 | +0.077 (+0.057 to +0.099) | +4.9% (+4.6 to +5.1) |
| km_metro | +0.103 (+0.091 to +0.114) | 5 of 8 | +0.110 (+0.089 to +0.135) | +0.0% (-1.2 to +1.1) |
| bus_stops_500m | -0.126 (-0.136 to -0.114) | 8 of 8 | -0.015 (-0.038 to +0.007) | -5.5% (-5.6 to -5.4) |
| km_motorway | +0.114 (+0.101 to +0.126) | 6 of 8 | -0.014 (-0.036 to +0.013) | +3.9% (+2.8 to +4.9) |
| km_a_road | +0.055 (+0.045 to +0.068) | 5 of 8 | +0.032 (+0.012 to +0.058) | +2.6% (+2.5 to +2.7) |

A step is one standard deviation of the column across the country. Ranges are 95% block-bootstrap ranges.
