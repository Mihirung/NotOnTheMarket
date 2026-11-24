# EPC: Energy certificates lodged before a sale (by UPRN; no address field is used)

**Verdict:** add it: the model finds more sellers and the range is clear of zero and of the fit's own noise

Source: MHCLG energy performance of buildings data (OGL, address fields excluded); ONS UPRN Directory.

| Owners | Current model | With this family | Gain | 95% range |
|---|---|---|---|---|
| All | 1.741 | 2.063 | +0.322 | +0.282 to +0.365 |
| Under 10 years | 1.740 | 1.887 | +0.146 | +0.105 to +0.191 |
| 10 to 19 years | 1.514 | 2.151 | +0.637 | +0.582 to +0.687 |
| 20 years or more | 1.291 | 2.247 | +0.956 | +0.838 to +1.077 |

Sellers found in the best tenth of each postcode district, times random, 2017 and 2018. The current model is the deployed one: BASE + HIST + GEO + VIEW + HOUSE + AREA + PD. The range includes the fit's own randomness (SEED_NOISE.md).

Share of the refitted model's gain that comes from this family: 16.0%.
