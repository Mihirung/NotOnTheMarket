# Would the deceased-estate notice step rank better with facts about the home?

A test, not a change to the product. The deployed step reads three columns: months since the latest notice, months the home
had been owned when it appeared, and how many there were. Here it is also given the home's type, price and years owned
(10 columns), the 2011 make-up of its output area (14), the later-life figures (5) and, in the second row of
each pair, the first step's own figure. 35,034 home-years of 2017 and 2018 have one; each is scored by a step fitted
on other homes in the other year. Figures are sellers found in the best tenth of each postcode district, times random.

| The step reads | Columns | All homes | Against the deployed step (95% range) | Owned 20 years or more | Log loss, test homes with one |
|---|---|---|---|---|---|
| No notices | 0 | 1.7408 |  | 1.2910 | 0.24531 |
| The notice alone, as deployed | 3 | 1.7594 |  | 1.3506 | 0.20676 |
| The notice and the home | 13 | 1.7589 | -0.0005 (-0.0016 to +0.0006) | 1.3506 | 0.20609 |
| The notice and the home, with the first step's figure | 14 | 1.7588 | -0.0006 (-0.0019 to +0.0005) | 1.3506 | 0.20589 |
| The notice, the home and its area | 27 | 1.7596 | +0.0002 (-0.0010 to +0.0013) | 1.3506 | 0.20613 |
| The notice, the home and its area, with the first step's figure | 28 | 1.7588 | -0.0006 (-0.0017 to +0.0005) | 1.3506 | 0.20600 |
| The notice, the home, its area and later life | 32 | 1.7590 | -0.0004 (-0.0016 to +0.0006) | 1.3506 | 0.20642 |
| The notice, the home, its area and later life, with the first step's figure | 33 | 1.7589 | -0.0005 (-0.0016 to +0.0006) | 1.3506 | 0.20613 |

In the widest step, months owned when the notice appeared carries 48%, months since the notice carries 45%, `price_pct` carries 2%, `owner_age` carries 1% of what the trees gain.

## Reading it

No wider step finds more sellers: every change is within its own range of zero. When the notice appeared and how long the home had been owned say what there is to say; the step stays as it is.
