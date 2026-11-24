# STOCK: what it is worth

The homes around the postcode in 2016: when built, type, bedrooms and council tax bands (Valuation Office Agency, stock_signals.py)

**Verdict:** do not add it to the model: no gain clear of zero and of the fit's own noise; use it for search and pricing

Coverage: 99.4% of postcodes, 99.8% of the home-years the model is tested on.

## Does it make the national model better?

| Owners | Current model | With this family | Gain | 95% range |
|---|---|---|---|---|
| All | 1.741 | 1.726 | -0.015 | -0.048 to +0.020 |
| Under 10 years | 1.740 | 1.743 | +0.003 | -0.025 to +0.035 |
| 10 to 19 years | 1.514 | 1.515 | +0.001 | -0.033 to +0.038 |
| 20 years or more | 1.291 | 1.330 | +0.039 | -0.047 to +0.122 |

Sellers found in the best tenth of each postcode district, times random, 2017 and 2018. The current model is the deployed one: BASE + HIST + GEO + VIEW + HOUSE + AREA + PD. The range includes the fit's own randomness (SEED_NOISE.md): two fits of the same model differ by up to about 0.02, so a gain smaller than that is not evidence.

## Each column: sale timing, what is left on top of the model, and price

| Column | Sale chance, points a year per step | Same sign in regions | Left on top of the model | Price per step |
|---|---|---|---|---|
| built_pre1919 | -0.042 (-0.051 to -0.032) | 7 of 8 | -0.045 (-0.067 to -0.025) | +1.8% (+1.6 to +1.9) |
| built_1919_44 | -0.116 (-0.125 to -0.104) | 7 of 8 | +0.018 (-0.004 to +0.037) | +0.1% (+0.0 to +0.2) |
| built_1945_64 | -0.035 (-0.045 to -0.025) | 8 of 8 | +0.060 (+0.037 to +0.081) | -1.5% (-1.6 to -1.4) |
| built_1965_82 | +0.038 (+0.026 to +0.050) | 6 of 8 | +0.013 (-0.006 to +0.035) | -1.1% (-1.2 to -1.1) |
| built_1983_99 | +0.144 (+0.134 to +0.156) | 8 of 8 | -0.009 (-0.034 to +0.022) | -0.2% (-0.2 to -0.1) |
| built_2000_09 | +0.063 (+0.051 to +0.076) | 7 of 8 | -0.026 (-0.050 to -0.006) | +1.9% (+1.8 to +2.0) |
| built_2010_16 | -0.016 (-0.029 to -0.004) | 4 of 8 | -0.025 (-0.049 to -0.001) | +0.8% (+0.7 to +0.8) |
| one_period | -0.095 (-0.104 to -0.084) | 8 of 8 | -0.035 (-0.057 to -0.012) | -2.3% (-2.4 to -2.2) |
| band_ab | -0.236 (-0.249 to -0.224) | 8 of 8 | +0.193 (+0.172 to +0.215) | -9.9% (-10.0 to -9.8) |
| band_fgh | +0.068 (+0.054 to +0.082) | 4 of 8 | -0.145 (-0.163 to -0.121) | +10.8% (+10.7 to +10.9) |
| bungalows | +0.113 (+0.104 to +0.125) | 8 of 8 | +0.079 (+0.055 to +0.103) | +0.9% (+0.8 to +0.9) |
| flats | -0.166 (-0.179 to -0.154) | 8 of 8 | -0.231 (-0.253 to -0.209) | -0.6% (-0.7 to -0.4) |
| terraced | -0.106 (-0.117 to -0.095) | 6 of 8 | +0.072 (+0.050 to +0.093) | -4.8% (-4.9 to -4.7) |
| semis | +0.009 (-0.003 to +0.020) | 6 of 8 | +0.135 (+0.113 to +0.156) | -0.2% (-0.3 to -0.1) |
| detached | +0.213 (+0.203 to +0.225) | 8 of 8 | +0.026 (+0.006 to +0.055) | +6.4% (+6.3 to +6.5) |
| beds_1_2 | -0.070 (-0.082 to -0.059) | 8 of 8 | -0.119 (-0.142 to -0.099) | -4.1% (-4.2 to -4.0) |
| beds_4_plus | +0.162 (+0.151 to +0.174) | 8 of 8 | -0.034 (-0.053 to -0.007) | +8.1% (+8.0 to +8.2) |

A step is one standard deviation of the column across the country. Ranges are 95% block-bootstrap ranges.
