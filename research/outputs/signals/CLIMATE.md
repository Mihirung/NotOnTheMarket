# CLIMATE: what it is worth

Climate now and how it is changing: Met Office HadUK-Grid 1991-2020 (2 km and 12 km), UKCP18 projections at 2 C of global warming (12 km), CHELSA cloud, solar energy and wind, sunshine hours calibrated on Met Office stations (climate_signals.py)

**Verdict:** do not add it to the model: no gain clear of zero; use it for search and pricing

Coverage: 99.4% of postcodes, 99.8% of the home-years the model is tested on.

## Does it make the national model better?

| Owners | Current model | With this family | Gain | 95% range |
|---|---|---|---|---|
| All | 1.741 | 1.718 | -0.022 | -0.039 to -0.004 |
| Under 10 years | 1.740 | 1.737 | -0.003 | -0.026 to +0.020 |
| 10 to 19 years | 1.514 | 1.517 | +0.003 | -0.019 to +0.027 |
| 20 years or more | 1.291 | 1.328 | +0.037 | -0.023 to +0.099 |

Sellers found in the best tenth of each postcode district, times random, 2017 and 2018. The current model is the deployed one: BASE + HIST + GEO + VIEW + HOUSE + AREA + PD.

## Each column: sale timing, what is left on top of the model, and price

| Column | Sale chance, points a year per step | Same sign in regions | Left on top of the model | Price per step |
|---|---|---|---|---|
| temp_year | -0.017 (-0.032 to -0.005) | 7 of 8 | -0.227 (-0.245 to -0.206) | -3.8% (-4.1 to -3.4) |
| temp_summer | -0.017 (-0.029 to -0.003) | 6 of 8 | -0.256 (-0.276 to -0.235) | -4.0% (-4.3 to -3.6) |
| temp_winter | -0.019 (-0.033 to -0.008) | 8 of 8 | -0.144 (-0.166 to -0.121) | -4.8% (-5.1 to -4.3) |
| temp_range | +0.001 (-0.011 to +0.012) | 3 of 8 | -0.195 (-0.219 to -0.174) | +0.1% (-0.3 to +0.5) |
| warmest_days | +0.058 (+0.046 to +0.070) | 5 of 8 | -0.259 (-0.282 to -0.237) | -3.8% (-4.3 to -3.2) |
| coldest_nights | -0.049 (-0.060 to -0.039) | 8 of 8 | -0.117 (-0.140 to -0.097) | -1.9% (-2.2 to -1.5) |
| rain_year | -0.005 (-0.015 to +0.006) | 4 of 8 | +0.188 (+0.163 to +0.216) | +2.2% (+1.7 to +2.6) |
| rain_summer | -0.063 (-0.075 to -0.051) | 4 of 8 | +0.249 (+0.226 to +0.278) | +1.4% (+1.1 to +1.8) |
| rain_winter | +0.016 (+0.005 to +0.027) | 5 of 8 | +0.153 (+0.130 to +0.183) | +2.9% (+2.3 to +3.4) |
| heavy_rain_days | +0.016 (+0.006 to +0.027) | 4 of 8 | +0.161 (+0.137 to +0.190) | +4.0% (+3.4 to +4.5) |
| frost_days | +0.083 (+0.073 to +0.095) | 8 of 8 | +0.053 (+0.031 to +0.075) | +6.7% (+6.2 to +7.1) |
| icing_days | +0.046 (+0.037 to +0.057) | 6 of 8 | +0.068 (+0.045 to +0.087) | +3.8% (+3.5 to +4.0) |
| summer_days | -0.033 (-0.045 to -0.019) | 4 of 8 | -0.267 (-0.288 to -0.248) | -10.0% (-10.6 to -9.5) |
| sun_hours_year | +0.110 (+0.100 to +0.122) | 5 of 8 | -0.167 (-0.189 to -0.143) | -3.8% (-4.3 to -3.3) |
| sun_hours_summer | +0.123 (+0.111 to +0.135) | 5 of 8 | -0.186 (-0.209 to -0.160) | -5.8% (-6.6 to -5.0) |
| sun_hours_winter | +0.074 (+0.065 to +0.085) | 5 of 8 | -0.120 (-0.142 to -0.096) | -2.0% (-2.2 to -1.8) |
| cloud_year | -0.108 (-0.120 to -0.097) | 5 of 8 | +0.193 (+0.167 to +0.214) | +4.3% (+3.9 to +4.7) |
| cloud_winter | -0.021 (-0.032 to -0.010) | 4 of 8 | +0.058 (+0.034 to +0.081) | +3.5% (+3.2 to +3.7) |
| solar_year | +0.119 (+0.108 to +0.130) | 5 of 8 | -0.152 (-0.177 to -0.127) | -0.6% (-1.3 to +0.1) |
| wind | +0.153 (+0.142 to +0.165) | 7 of 8 | +0.107 (+0.082 to +0.132) | +7.4% (+7.3 to +7.6) |
| warming_so_far | -0.017 (-0.030 to -0.005) | 4 of 8 | -0.237 (-0.260 to -0.217) | +1.4% (+0.6 to +2.6) |
| warming_2c | +0.009 (-0.004 to +0.021) | 4 of 8 | -0.245 (-0.268 to -0.223) | +8.1% (+6.9 to +9.7) |
| summer_heat_2c | +0.173 (+0.164 to +0.185) | 6 of 8 | -0.045 (-0.069 to -0.022) | +0.5% (+0.1 to +1.1) |
| winter_nights_2c | -0.102 (-0.113 to -0.091) | 3 of 8 | +0.115 (+0.090 to +0.135) | +0.3% (-0.2 to +0.8) |
| summer_rain_so_far | -0.053 (-0.064 to -0.043) | 6 of 8 | -0.168 (-0.190 to -0.143) | -0.6% (-1.2 to -0.1) |
| summer_rain_2c | -0.095 (-0.106 to -0.085) | 4 of 8 | -0.043 (-0.068 to -0.019) | -1.8% (-2.5 to -1.0) |
| winter_rain_so_far | +0.015 (+0.006 to +0.025) | 5 of 8 | +0.036 (+0.012 to +0.061) | +0.8% (+0.3 to +1.2) |
| winter_rain_2c | +0.093 (+0.082 to +0.104) | 5 of 8 | -0.140 (-0.161 to -0.116) | +1.2% (+0.5 to +1.9) |
| hot_days_now | -0.017 (-0.029 to -0.003) | 4 of 8 | -0.248 (-0.270 to -0.230) | -2.9% (-3.5 to -2.3) |
| hot_days_2c | +0.032 (+0.019 to +0.046) | 4 of 8 | -0.251 (-0.272 to -0.231) | -3.1% (-3.6 to -2.4) |
| frost_days_lost_2c | -0.083 (-0.094 to -0.071) | 4 of 8 | +0.140 (+0.118 to +0.161) | +2.4% (+2.1 to +2.8) |

A step is one standard deviation of the column across the country. Ranges are 95% block-bootstrap ranges.
