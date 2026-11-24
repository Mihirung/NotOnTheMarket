# Averaging fits, and the new families judged against more than one fit

Deployed model: BASE + HIST + GEO + VIEW + HOUSE + AREA + PD, fitted with seed 7. Seeds 8 and 9 are the same model refitted. Family fits are the deployed model plus one family, seed 7. Sellers found in the best tenth of each district, times random, 2017 and 2018, all owners.

| Prediction | Lift | vs deployed fit | 95% range | vs mean of 3 fits | 95% range incl. fit noise |
|---|---|---|---|---|---|
| fit seed 7 | 1.741 | +0.000 | +0.000 to +0.000 | +0.013 | -0.014 to +0.039 |
| fit seed 8 | 1.724 | -0.017 | -0.035 to -0.002 | -0.005 | -0.032 to +0.022 |
| fit seed 9 | 1.720 | -0.021 | -0.036 to -0.008 | -0.008 | -0.035 to +0.018 |
| average of 3 fits | 1.740 | -0.001 | -0.013 to +0.010 | +0.012 | -0.003 to +0.027 |
| average of 3 fits (ranks) | 1.741 | +0.000 | -0.012 to +0.011 | +0.013 | -0.003 to +0.028 |
| 3 fits + 7 family fits | 1.743 | +0.002 | -0.008 to +0.015 | +0.015 | -0.000 to +0.030 |
| 3 fits + 4 clean families | 1.740 | -0.000 | -0.012 to +0.010 | +0.012 | -0.003 to +0.027 |
| family LIFE | 1.730 | -0.011 | -0.024 to +0.005 | +0.002 | -0.026 to +0.030 |
| family PEOPLE | 1.739 | -0.002 | -0.020 to +0.014 | +0.011 | -0.019 to +0.040 |
| family STOCK | 1.726 | -0.015 | -0.029 to +0.001 | -0.003 | -0.030 to +0.025 |
| family SCHOOLS | 1.728 | -0.013 | -0.025 to -0.001 | +0.000 | -0.027 to +0.028 |
| family ACCESS | 1.718 | -0.022 | -0.036 to -0.009 | -0.010 | -0.038 to +0.018 |
| family CRIME | 1.724 | -0.017 | -0.030 to -0.001 | -0.004 | -0.032 to +0.024 |
| family COMMUNITY | 1.721 | -0.020 | -0.034 to -0.004 | -0.008 | -0.036 to +0.021 |

Spread of the three fits (standard deviation): 0.011.

Best prediction: 3 fits + 7 family fits, 1.743 against 1.741 for the deployed fit (not clear of zero).

## By length of ownership

Gain over the deployed fit, with its 95% range (test homes only; averaged predictions carry little fit noise).

| Owners | Deployed fit | Average of 3 fits | 3 fits + STOCK, SCHOOLS, ACCESS, CRIME | 3 fits + all 7 families |
|---|---|---|---|---|
| All | 1.741 | -0.001 (-0.013 to +0.010) | -0.000 (-0.012 to +0.010) | +0.002 (-0.008 to +0.015) |
| Under 10 years | 1.740 | +0.018 (+0.001 to +0.035) | +0.027 (+0.009 to +0.045) | +0.027 (+0.008 to +0.046) |
| 10 to 19 years | 1.514 | +0.032 (+0.015 to +0.048) | +0.025 (+0.009 to +0.047) | +0.036 (+0.017 to +0.058) |
| 20 years or more | 1.291 | +0.015 (-0.042 to +0.065) | +0.035 (-0.022 to +0.094) | +0.016 (-0.041 to +0.069) |

## What this means

- The deployed fit is a lucky draw: 0.013 above the mean of three fits of the same model.
- Averaging three fits removes that luck. It matches the lucky fit for all owners and beats it inside the under-10 and 10-to-19-year bands, with ranges clear of zero.
- No new family hurts the model once the fit's own noise is counted, and none helps on its own. The earlier 'clear losses' for SCHOOLS, ACCESS, CRIME and COMMUNITY were the luck of the deployed fit.
- assess_signal.py now adds the fit noise to every range, so future verdicts cannot be decided by a lucky or unlucky fit.
- At the next refit, deploy an average of three fits rather than one. Blending in the four families cleared for search adds a little more inside the bands; COMMUNITY stays out until legal sign-off.
