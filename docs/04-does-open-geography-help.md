# Does open geographic data make the targeting good enough?

*The question behind the question: will buyers get replies, and how much
postage is at risk if they don't?*

This document reports a real experiment. We took the AHAH inputs
(Access to Healthy Assets & Hazards) you suggested, built a national
geographic feature layer, and re-ran the propensity model as a strict
out-of-time ablation. Code in
[`../research/src/`](../research/src/), results in
[`../research/outputs/`](../research/outputs/).

## 1. What we actually built

AHAH's own portal is not reachable from this environment, but the
Geographic Data Service publishes the toolkit and its inputs on GitHub,
so we used the real source data:

| Layer | Source | What we derived |
|---|---|---|
| Air quality | AHAH v4 inputs (NOx, PM10, SO2 per LSOA, 2024) | Value at each postcode via nearest LSOA centroid; plus air quality *relative to the surrounding district*, since people judge air against the local alternatives |
| Health access | AHAH v4 POI sets: 9,129 GPs, 18,105 hospital sites, 10,046 dentists, 12,196 pharmacies | Straight-line distance from every postcode to the nearest of each |
| Postcode geography | ONS Postcode Directory via Geovation's SQLite build | Coordinates for **1,573,898** England & Wales postcodes |
| Built density | derived | Postcodes within 1km and 5km — our stand-in for the greenspace domain, which the AHAH repository does not publish |
| Settlement gravity | derived | Distance to nearest town, regional centre and major city, thresholds calibrated against known places |

The geographic layer matched **99.8%** of the property-year panel.

Two methodological notes worth carrying forward, because both would
silently corrupt a production build:

- The AHAH boundary geometries are in **British National Grid metres**,
  not latitude/longitude. Joined naively against WGS84 coordinates,
  every postcode matches essentially one LSOA and the air-quality
  feature becomes a constant. We caught this because the variance was
  exactly zero. Everything is now computed in EPSG:27700.
- Defining "a city" by a **percentile** of density is swamped by
  London: on that definition most of England is 160km from a city.
  Absolute, calibrated thresholds are required (Exeter reads ~3,600
  postcodes within 5km, Bristol ~8,800, central London ~37,000).

## 2. The headline result: geography barely moves overall targeting

Train 2001–2015, test out-of-time on 2017–2019. 10.1M property-years,
1.97M in test.

| | Transaction history | + AHAH geography | + life stage |
|---|---|---|---|
| Features | 13 | 25 | 30 |
| AUC | 0.5883 | **0.5917** | 0.5910 |
| Lift, top 1% | 1.885 | 1.908 | **1.911** |
| Lift, top 10% | 1.594 | **1.619** | 1.615 |
| Sellers reached, top 20% | 29.3% | 29.5% | 29.5% |
| Postcards per conversation | 57 | 56 | 56 |

That is a **1.5% improvement in top-decile targeting**. Real, consistent,
and far too small to change the business case on its own. If the pitch
were "AHAH makes the model work", the data does not support it.

The reason is not that the environment doesn't matter. It is that the
model already carries district turnover, local price level and price
momentum, and those absorb most of what "what kind of place is this"
contributes. AHAH's domains are also *static*: they describe a place's
persistent character, and the hard part of this problem is **timing**,
not character.

## 3. The real result: it helps exactly where the base model fails

Overall averages hide the finding. Split the test set by how long the
owner has been there:

| Owner tenure | AUC, history only | AUC, + geography | Top-decile lift, history | Top-decile lift, full |
|---|---|---|---|---|
| 10+ years | 0.5613 | 0.5664 | 1.460 | 1.489 |
| 20+ years | 0.5175 | **0.5374** | 1.161 | **1.257** |

For owners of 20 years or more, transaction history is nearly useless —
AUC 0.5175 is barely better than a coin flip, and top-decile lift of
1.16 means targeting is almost pointless. Adding geography and
life-stage inference lifts that to 1.257, an **8.3% improvement in the
cohort where the base model has almost nothing**.

That matters far more than the headline number, because of a finding
from the earlier study: **38.8% of current sellers are owners who bought
24+ years ago.** The long-tenure cohort is not a niche. It is the
largest single source of the latent supply this business is built on,
and it is precisely where public transaction records go quiet.

LONGTENURE_DETAIL

Your instinct about inferring life stage from what people bought is
where this shows up most. The features that encode "this household
bought a family home and has now been there far longer than families
normally stay" carry more weight for long-tenure owners than any single
environmental measure.

## 4. The reframe: AHAH's biggest value is on the demand side

Here is the conclusion we did not expect when we started.

Air quality, green surroundings and travel time turn out to be modest
predictors of **who will sell**. They are excellent descriptors of
**what a buyer wants** — which is exactly how you used them when you
chose your own house. And that matters more to the response-rate problem
than the model does, for a reason the economics makes precise.

A buyer who asks for "three-bed semi in St Leonard's" is describing a
pocket of a few hundred homes. A buyer who asks for "clean air, open
surroundings, half an hour from a centre, under £475k" is describing
thousands, spread across the whole city. Same person, same real
requirement — but one brief is ten times wider than the other.

Brief width is the dominant term in whether a buyer hears anything back.

## 5. What actually controls the response risk

From [`../research/outputs/response_economics.json`](../research/outputs/response_economics.json):

**Break-even is low.** With the measured 1.59x targeting lift, a campaign
pays for itself at a **0.34% scan rate** (0.55% with no targeting at
all). Direct mail with a specific, credible number on it should beat
that comfortably — but it is unmeasured, and it is the single number
that decides the business.

**The uncertainty in the response rate dwarfs the uncertainty in the
model.** Across the plausible range:

| Base scan rate | Conversations per 1,000 cards | Postage per completed sale | Contribution per sale |
|---|---|---|---|
| 0.5% | 2.6 | £2,613 | £1,186 |
| 1.0% | 5.2 | £1,306 | £2,493 |
| 2.4% | 12.6 | £544 | £3,255 |
| 5.0% | 26.2 | £261 | £3,538 |

Every one of those rows is profitable. The model improved cost per
conversation from £57 to £56; moving the scan rate from 1% to 2.4% moves
it from £1,306 to £544 per sale. **Spend the effort on the offer and the
card, not on the fourth decimal place of the model.**

**Silence is a brief-width problem, not a response-rate problem.**
Probability a buyer's own campaign returns nothing at all:

| Homes mailed for that buyer | at 0.5% scan | at 1.0% | at 2.4% |
|---|---|---|---|
| 50 | 88% | 77% | 53% |
| 200 | 59% | 35% | 8% |
| 800 | 12% | 2% | 0% |
| 3,200 | 0% | 0% | 0% |

A narrow brief is a bad experience *even if the response rate is fine*.
This is the risk you were pointing at, and it is a product-design
problem with a product-design fix.

**The stamp-cost risk is controllable to about £1,400.** Simulating a
wave protocol (2,000 → 5,000 → 12,000 → 30,000 cards, stopping when a
wave under-performs) against one 49,000-card campaign costing £35,280:
if the true scan rate is 0.5%, the protocol abandons after wave one
**100% of the time**, at a median spend of **£1,440**. If it is 2.4%, it
never abandons. You find out the world is bad for four figures instead
of five.

## 6. What we would do about it

1. **Make the lifestyle search the primary search.** It is the better
   experience, and it is the risk control: it produces briefs an order
   of magnitude wider, which is what moves silence risk from 59% to
   near zero. This is now built into the prototype.
2. **Canvass continuously, city-wide; don't run per-buyer campaigns.**
   Mail on behalf of the whole demand book rather than one brief. A
   reply becomes an asset matchable to any buyer, cost is amortised, and
   a new buyer arrives to sellers who are *already warm* rather than
   waiting a fortnight to hear nothing. Continuous canvassing at 6,000
   cards/month yields roughly 19 matching warm sellers waiting at a 1%
   scan rate — a buyer's silence risk becomes effectively zero.
3. **Never spend the mail budget before measuring.** Run the wave
   protocol from day one, with randomised offer premiums inside each
   wave so the first campaign is also the first experiment.
4. **Buy the trigger data before optimising the model.** Withdrawn
   listings, EPCs lodged without a sale, and landlord-exit signals are
   worth more than any further work on the open-data feature set. The
   ceiling analysis in [`02-prediction-problem.md`](02-prediction-problem.md)
   still holds.
5. **Keep AHAH.** Not because it materially improves targeting overall,
   but because it earns its place twice: it is the buyer's search
   vocabulary, and it is the only thing that gives us any grip at all on
   long-tenure owners.

## Honest limitations

- AHAH air quality and POI locations are **current vintage** applied to a
  2001–2019 panel. Geography is persistent, so this is acceptable for a
  feasibility read, but it slightly flatters the model wherever
  environmental quality correlates with recent gentrification. A
  production model should use vintage-matched environmental data.
- Drive times are straight-line distance at 50 km/h, not routed. True
  isochrones need a routing engine (Valhalla, OSRM or the Ordnance
  Survey network); AHAH's own toolkit uses Valhalla. Every figure
  derived this way is labelled an approximation in the prototype.
- Greenspace is proxied by built density because the AHAH repository
  does not publish that domain. OS Open Greenspace would replace it
  directly.
- All response-rate figures are **assumptions, not measurements**. That
  is the entire point of section 5: the pilot exists to replace them.
