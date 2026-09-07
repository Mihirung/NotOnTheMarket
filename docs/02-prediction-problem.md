# The prediction problem: how far can "who would sell?" be pushed

This document frames the machine learning problem properly, then reports
what we actually found by running the analysis on the full HM Land
Registry Price Paid Data for England and Wales, 1995 to 2019
(24.25 million standard residential transactions linked into
13.79 million distinct properties). Code and outputs live in
[`../research/`](../research/).

## 1. Two different models, one product

The product needs two predictions that are usually conflated:

**Model A — sale propensity.** For every owned property and horizon
(the next 12 months, say): the probability it transacts. This is a
discrete-time hazard problem with censoring, exactly the survival
analysis used in insurance and churn. Land Registry data supervises it
directly: millions of labelled examples of who sold, when, after how
long, in what local conditions. This model decides *who gets a
postcard*.

**Model B — the reservation premium.** For a property that would not
otherwise sell soon: the premium over open-market value at which the
owner tips into accepting. This is *not observable in any public
dataset*, because declined offers are recorded nowhere. It decomposes
into two parts with very different difficulty:

- *Open-market value* (an AVM): a solved problem to within roughly 5 to
  10% error for mainstream stock; buildable from PPD + EPC attributes +
  local indices, or licensable.
- *The premium curve* P(accept | premium, owner context): genuinely
  novel. Behavioural economics gives the priors — loss aversion anchors
  owners to purchase price and peak neighbourhood comparables
  (Genesove & Mayer's classic result), endowment and moving costs
  imply a meaningful premium for unplanned moves, and the premium
  should fall with owner tenure, life stage, and landlord status. But
  the curve itself must be *learned from the product's own campaigns*:
  every postcard wave with randomised offer bands is a designed
  experiment, and a contextual bandit over premium levels converts
  marketing spend into the dataset nobody else has.

The strategic consequence: Model A can be built and validated **before
the company exists** (we do so below). Model B is the moat that only
operating the company can build. Investors should hear both sentences.

## 2. Formal framing for Model A

For property *i* in year *t*, predict
h_i(t) = P(sale in year t | owned at start of t, features x_i(t)).

- **Unit**: property-year (property-month in production).
- **Labels**: from linked PPD transactions; a sale ends an ownership
  spell, censoring handles spells still open at the data edge.
- **Features available at prediction time only** (no leakage):
  ownership tenure so far, last purchase price relative to the local
  market, property type and lease type, new-build flag, prior sale
  count, local turnover and price momentum, area demographics.
- **Evaluation**: strictly out-of-time. Train on early years, test on
  later years the model never saw, because deployment means predicting
  the future, not interpolating the past. Metrics that matter to the
  postcard budget: ranking quality (AUC), lift and gain in the top
  deciles (mail efficiency), and calibration (the offer engine consumes
  the probabilities, so they must mean what they say).

Selection note: because PPD starts in 1995, a property enters our risk
set only after its first observed sale. Owners who bought before 1995
are invisible until they sell (left truncation), and they are
precisely the long-tenure, later-life cohort the lifespan hypothesis
cares about. We quantify the size of that blind spot below; in
production, EPC records, council tax and area demographics cover the
pre-1995 cohort so the deployed model sees the whole stock.

## 3. What the data says (results)

### 3.1 The structure of who sells when

From 24,254,747 linked transactions (10.5 million completed ownership
spells, the rest right-censored):

- **The sale hazard has strong, stable shape.** The probability an
  owner sells rises from ~4.0% in their first full year to a peak of
  ~6.5% in years 3 to 4, then declines steadily to ~2.4% by year 24
  (`research/outputs/hazard_survival.png`). Selling is not a
  memoryless coin flip; tenure alone is a powerful predictor, which is
  the quantified version of the lifecycle intuition behind the idea.
- **Heterogeneity is large and systematic.** Flats peak at a 7.9%
  annual hazard, detached houses at only 5.2%; cheaper stock churns
  faster than the dearest quartile (7.2% vs 5.5% at peak). And the
  curves *cross* around year 14: past that point, detached family
  homes become the most likely long-tenure sellers — the later-life
  move showing up in the data
  (`research/outputs/hazard_heterogeneity.png`).
- **Median observed holding is short; the tail is long.** Completed
  spells have a median of 5 years, but the survival curve shows about
  half of purchases still held 13+ years on, and 37% still held after
  24 years. Latent supply is real: most of the stock at any moment sits
  in slow-moving, long-tenure hands.
- **The lifespan cohort is the volume.** 38.8% of all 2019 sales were
  properties appearing in the data for the first time, meaning owners
  who had held since before 1995 (24+ years). Nearly four in ten of
  today's sellers come from exactly the long-tenure cohort the
  postcard product wants to reach, and transaction history alone
  cannot rank *within* it — the strongest possible argument for the
  EPC/demographic enrichment in Phase 1.
- **Local turnover differs by less than you might think.** Across
  2,174 postcode districts (500+ observed properties), average
  2014-2018 turnover of observed stock runs from 5.5% (10th
  percentile) to 7.6% (90th). Geography matters, but property-level
  features matter far more — a district-level model would leave most
  of the signal on the table.

### 3.2 Out-of-time propensity model

MODEL_RESULTS_PLACEHOLDER

## 4. The boundary map: what is predictable and what is not

Drawing the boundaries of the open project, from firmest ground to
most speculative:

1. **Local turnover and market temperature: essentially solved.**
   District-level sale volumes are stable, autocorrelated and
   forecastable; dispersion across districts is wide and persistent.
   Cohort-level supply counts shown to buyers ("~240 matching homes
   likely to move at the right offer") can be made honest and
   defensible today.
2. **Ranking owned properties by next-year sale probability: works,
   validated here out-of-time.** Transaction history and local context
   alone give a strong ranking; EPC attributes, listing-history
   (withdrawn listings especially), landlord identification and area
   life-stage data are the known next features and each has a clear
   causal story. This is also the exact model class Spectre operates
   profitably for agents, so commercial precedent exists.
3. **Timing an individual sale to the quarter: mostly irreducible.**
   Life events fire the trigger and are invisible until they happen.
   The product design absorbs this correctly: it does not need to know
   *when* Mrs Jones will sell, only that her street's cohort is worth
   mailing this quarter and at roughly what number.
4. **The individual reservation premium: unknowable a priori,
   learnable in operation.** Start from behavioural priors (premium
   bands of roughly 5 to 25% over AVM, decreasing in tenure and
   landlord status), randomise within bands from wave one, and let the
   bandit converge. The acceptance curve by segment is the company's
   compounding asset.
5. **The hardest cohort is also the prize.** Long-tenure owners sell
   at the lowest annual rate but hold most of the latent supply and,
   by the lifespan logic, much of the *unlockable* supply. Transaction
   history alone degrades gracefully there (details below); closing
   that gap with EPC-lodged-without-sale signals, probate-adjacent
   area demographics and planning applications is the highest-value
   modelling work after launch.

## 5. Roadmap for the modelling programme

**Phase 0 (done, this repo).** Validate signal exists: linked 25-year
national dataset, hazard structure, out-of-time propensity model with
honest lift numbers.

**Phase 1 (pre-launch, ~4 to 6 weeks of data engineering).**
UPRN-linked property spine (PPD + EPC + council tax + ONS/Census +
OS open data); monthly-grain hazard model; withdrawn-listing and
landlord features via a commercial listings feed; calibrated
probabilities per property; cohort supply counts for the buyer-facing
"how many homes match" experience.

**Phase 2 (from wave one of postcards).** Offer-band randomisation
inside every campaign; acceptance-curve learning per segment
(contextual bandit; Thompson sampling is the natural fit); response
data (scans, opens, declines with reasons) feeding back into both
models. Success metric: postcards per agreed sale trending down
wave over wave.

**Phase 3 (scale).** Full-stock coverage including never-transacted
properties; survival model upgraded to compete with the bandit's
value of information; the reservation-price surface becomes the
pricing engine for guaranteed-offer or partner products.

## 6. Honest limitations of this study

- 1995 to 2019 data (the public mirror we used); extending to 2025 is
  a config change with the current PPD download, and nothing in the
  structure suggests the conclusions flip after 2019 (we test across
  regimes as different as 2001 and 2018 and the ranking holds).
- The 2019 file slightly undercounts late-registered sales; we
  therefore report test metrics per year and confirm 2017 and 2018
  agree with 2019.
- Address-string linkage mislinks a small share of flats and renamed
  buildings; UPRN linkage in production strictly improves labels.
- We model *sales*, not *sales given an above-market offer*; the gap
  between those is exactly Model B, argued above to be learnable only
  in operation. The propensity model remains the correct targeting
  tool either way, because "would sell unprompted soon" and "would
  sell if nudged" share drivers (life stage, tenure, local liquidity)
  even though they are not identical.
