# PEOPLE: what it is worth

Who lives around the postcode: life stage, household type, tenure, spare bedrooms, work, cars, marital status and health, from the 2011 Census output area (people_signals.py)

**Verdict:** do not add it to the model: no gain clear of zero and of the fit's own noise; use it for search and pricing

Coverage: 99.4% of postcodes, 99.8% of the home-years the model is tested on.

## Does it make the national model better?

| Owners | Current model | With this family | Gain | 95% range |
|---|---|---|---|---|
| All | 1.741 | 1.739 | -0.002 | -0.038 to +0.032 |
| Under 10 years | 1.740 | 1.760 | +0.019 | -0.011 to +0.052 |
| 10 to 19 years | 1.514 | 1.543 | +0.029 | -0.010 to +0.066 |
| 20 years or more | 1.291 | 1.272 | -0.019 | -0.096 to +0.048 |

Sellers found in the best tenth of each postcode district, times random, 2017 and 2018. The current model is the deployed one: BASE + HIST + GEO + VIEW + HOUSE + AREA + PD. The range includes the fit's own randomness (SEED_NOISE.md): two fits of the same model differ by up to about 0.02, so a gain smaller than that is not evidence.

## Each column: sale timing, what is left on top of the model, and price

| Column | Sale chance, points a year per step | Same sign in regions | Left on top of the model | Price per step |
|---|---|---|---|---|
| children | -0.054 (-0.065 to -0.044) | 6 of 8 | +0.070 (+0.050 to +0.093) | -2.8% (-2.9 to -2.7) |
| age_20_29 | -0.182 (-0.194 to -0.170) | 8 of 8 | -0.129 (-0.154 to -0.108) | -5.0% (-5.1 to -4.9) |
| age_30_44 | +0.117 (+0.107 to +0.131) | 8 of 8 | -0.103 (-0.126 to -0.084) | -3.5% (-3.6 to -3.4) |
| age_45_59 | +0.066 (+0.054 to +0.076) | 5 of 8 | +0.070 (+0.049 to +0.093) | +5.0% (+4.9 to +5.0) |
| age_60_64 | +0.066 (+0.055 to +0.077) | 5 of 8 | +0.093 (+0.075 to +0.113) | +4.5% (+4.5 to +4.6) |
| age_65_74 | +0.054 (+0.042 to +0.065) | 4 of 8 | +0.080 (+0.059 to +0.105) | +3.7% (+3.7 to +3.8) |
| age_75_84 | +0.081 (+0.070 to +0.092) | 7 of 8 | +0.057 (+0.035 to +0.082) | +1.8% (+1.7 to +1.9) |
| age_85_plus | +0.117 (+0.105 to +0.128) | 8 of 8 | +0.035 (+0.008 to +0.059) | +1.1% (+1.0 to +1.3) |
| median_age | +0.161 (+0.149 to +0.172) | 8 of 8 | +0.074 (+0.053 to +0.099) | +6.0% (+5.9 to +6.2) |
| hh_alone_65 | +0.079 (+0.067 to +0.090) | 6 of 8 | +0.062 (+0.040 to +0.092) | -0.9% (-1.0 to -0.8) |
| hh_alone_under_65 | -0.100 (-0.113 to -0.088) | 7 of 8 | -0.098 (-0.124 to -0.079) | -5.1% (-5.2 to -5.0) |
| hh_couple_65 | +0.076 (+0.063 to +0.086) | 6 of 8 | +0.067 (+0.045 to +0.093) | +5.9% (+5.9 to +6.0) |
| hh_couple_no_children | +0.318 (+0.308 to +0.329) | 8 of 8 | +0.044 (+0.023 to +0.063) | +5.4% (+5.4 to +5.5) |
| hh_young_children | -0.052 (-0.063 to -0.041) | 5 of 8 | +0.062 (+0.041 to +0.087) | -1.3% (-1.4 to -1.2) |
| hh_grown_children | -0.144 (-0.157 to -0.133) | 8 of 8 | +0.118 (+0.095 to +0.141) | +0.4% (+0.3 to +0.5) |
| hh_lone_parent | -0.160 (-0.171 to -0.149) | 8 of 8 | +0.087 (+0.064 to +0.108) | -7.2% (-7.3 to -7.1) |
| hh_students | -0.097 (-0.105 to -0.088) | 8 of 8 | -0.131 (-0.147 to -0.110) | -0.0% (-0.2 to +0.1) |
| own_outright | +0.125 (+0.112 to +0.136) | 8 of 8 | +0.063 (+0.044 to +0.087) | +7.6% (+7.5 to +7.7) |
| own_mortgage | +0.326 (+0.314 to +0.338) | 8 of 8 | +0.134 (+0.113 to +0.160) | +2.9% (+2.9 to +3.0) |
| social_rent | -0.214 (-0.224 to -0.204) | 8 of 8 | +0.015 (-0.007 to +0.039) | -5.8% (-5.8 to -5.7) |
| private_rent | -0.201 (-0.212 to -0.187) | 8 of 8 | -0.197 (-0.221 to -0.174) | -2.2% (-2.4 to -2.1) |
| spare_2_bedrooms | +0.171 (+0.158 to +0.182) | 8 of 8 | +0.081 (+0.064 to +0.108) | +13.2% (+13.1 to +13.3) |
| overcrowded | -0.358 (-0.369 to -0.348) | 8 of 8 | -0.155 (-0.173 to -0.139) | -8.4% (-8.5 to -8.3) |
| retired | +0.074 (+0.061 to +0.085) | 6 of 8 | +0.112 (+0.092 to +0.135) | +3.6% (+3.5 to +3.7) |
| self_employed | +0.149 (+0.137 to +0.162) | 6 of 8 | -0.125 (-0.151 to -0.102) | +11.7% (+11.6 to +11.8) |
| unemployed | -0.346 (-0.357 to -0.335) | 8 of 8 | +0.048 (+0.026 to +0.068) | -7.5% (-7.5 to -7.4) |
| students | -0.198 (-0.206 to -0.188) | 8 of 8 | -0.143 (-0.162 to -0.124) | +0.1% (+0.0 to +0.2) |
| hh_size | -0.158 (-0.168 to -0.148) | 7 of 7 | -0.018 (-0.037 to +0.005) | +2.9% (+2.8 to +3.0) |
| rooms | +0.154 (+0.142 to +0.164) | 8 of 8 | +0.078 (+0.061 to +0.101) | +14.7% (+14.6 to +14.8) |
| bedrooms | +0.076 (+0.064 to +0.086) | 8 of 8 | +0.059 (+0.039 to +0.082) | +11.8% (+11.7 to +11.9) |
| no_central_heating | -0.098 (-0.110 to -0.086) | 8 of 8 | -0.027 (-0.052 to -0.003) | -3.4% (-3.5 to -3.3) |
| no_car | -0.406 (-0.418 to -0.395) | 8 of 8 | -0.101 (-0.125 to -0.084) | -12.1% (-12.2 to -12.0) |
| cars_per_household | +0.334 (+0.322 to +0.346) | 8 of 8 | +0.071 (+0.054 to +0.095) | +16.7% (+16.6 to +16.8) |
| married | +0.154 (+0.142 to +0.165) | 8 of 8 | +0.064 (+0.045 to +0.088) | +10.8% (+10.7 to +10.9) |
| separated_divorced | +0.043 (+0.033 to +0.053) | 5 of 8 | +0.086 (+0.062 to +0.112) | -6.4% (-6.5 to -6.4) |
| widowed | +0.065 (+0.053 to +0.077) | 6 of 8 | +0.094 (+0.072 to +0.118) | -0.4% (-0.5 to -0.2) |
| never_married | -0.194 (-0.204 to -0.181) | 8 of 8 | -0.121 (-0.143 to -0.099) | -8.3% (-8.4 to -8.2) |
| bad_health | -0.199 (-0.209 to -0.184) | 8 of 8 | +0.136 (+0.112 to +0.161) | -4.6% (-4.6 to -4.5) |
| limited_a_lot | -0.117 (-0.128 to -0.104) | 8 of 8 | +0.152 (+0.126 to +0.177) | -3.0% (-3.1 to -2.9) |
| carers_20h | -0.162 (-0.174 to -0.150) | 8 of 8 | +0.179 (+0.156 to +0.203) | -2.9% (-3.0 to -2.9) |

A step is one standard deviation of the column across the country. Ranges are 95% block-bootstrap ranges.
