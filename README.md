# Not On The Market

A consumer platform built on one observation: at any moment only ~3% of
the UK's 29.9 million homes are visibly for sale, yet essentially all of
them would sell at some price. Not On The Market predicts which
properties would sell if made the right offer, describes those latent
cohorts to registered buyers, and reaches the owners directly by
postcard (QR code to a private offer page) — then acts as the
transaction's admin layer and emotional circuit breaker in place of a
traditional estate agent.

## What is in this repository

| Path | Contents |
|---|---|
| [`docs/01-concept-assessment.md`](docs/01-concept-assessment.md) | Honest evaluation of the concept: premise reality-check, what is strong, the problems most likely to kill it, regulation, business model, recommended wedge and go/no-go metrics. |
| [`docs/02-prediction-problem.md`](docs/02-prediction-problem.md) | The machine learning deep dive: formal framing, empirical results from 25 years of Land Registry data, the boundary map of what is and is not predictable, and the modelling roadmap. |
| [`docs/03-data-sources.md`](docs/03-data-sources.md) | Full inventory of usable UK data sources, their licences and gotchas, and the linkage plan. |
| [`research/`](research/) | Reproducible feasibility study: pipeline that links 24.25M Land Registry transactions into 13.8M property histories, survival analysis of ownership spells, and an out-of-time sale-propensity model with honest performance numbers. |

## Headline findings from the feasibility study

1. **Sale timing has strong learnable structure.** The annual sale
   hazard peaks at ~6.5% in years 3-4 of ownership and declines to
   ~2.4% by year 24, with large systematic differences by property
   type and price band.
2. **The long-tenure cohort is the volume.** Nearly 4 in 10 sales now
   come from owners who bought 24+ years ago — exactly the latent
   supply the product targets, and the cohort where enrichment beyond
   transaction data (EPC, demographics) matters most.
3. **Targeting works out-of-time, and its limits are mapped.** A model
   trained on 2001-2015 and tested on 2017-2019 delivers a stable AUC
   of 0.588 and 1.6x-1.9x mail efficiency in its top deciles from
   open transaction data alone; the analysis shows trigger signals
   (withdrawn listings, EPC-without-sale, landlord exits) are what
   buy the next multiple (full metrics in
   [`docs/02-prediction-problem.md`](docs/02-prediction-problem.md)).
4. **The moat is the model nobody can pre-build.** Offer-acceptance
   data (which premium unlocks which owner) exists nowhere publicly;
   the postcard campaigns generate it as a by-product from wave one.
