# Data landscape for predicting latent supply

Every dataset that plausibly helps predict "would this property sell at the right offer", what it contains, what it costs, and what it is legally good for. England and Wales focus (Scotland has parallel sources via Registers of Scotland).

## Tier 1: the spine (open, address-level, use from day one)

| Source | What it gives the model | Access & licence | Gotchas |
|---|---|---|---|
| **HM Land Registry Price Paid Data** (1995 to now, ~30m rows) | Every residential sale: price, date, address, type, new-build flag, tenure (freehold/leasehold). The spine for ownership spells, tenure-at-address, local turnover and price dynamics. | Free bulk CSV, OGL. Monthly updates. | Address fields are PAF-derived: fine for price-information services, but a bulk *mailing* operation needs a Royal Mail PAF licence. No property attributes beyond type. Registration lag of weeks to months for recent sales. |
| **Energy Performance Certificates** (England & Wales register, ~25m certificates) | Floor area, property age band, built form, current condition proxies (energy score, glazing, heating), **tenure at assessment** (owner-occupied vs privately rented vs social) and inspection date. The single richest free attribute source, and an EPC lodged *without* a subsequent sale or letting is itself a signal someone considered moving. | Free bulk download after registration, quarterly refresh. OGL except address/postcode (PAF terms again). | Coverage biased to properties transacted, let or retrofitted since 2008. Tenure is as-at-assessment, so stale for long holders. |
| **HM Land Registry UK House Price Index** | Local price levels and momentum by local authority and property type. | Free, OGL. | Coarser geography than postcode district; complement with PPD-derived local indices. |
| **ONS Postcode Directory + Census 2021 (LSOA level)** | Age structure (the lifespan hypothesis lives here: share of residents 70+, pensioner one-person households), tenure mix, occupancy, deprivation (IMD), household composition. Maps every postcode to LSOA/ward/LA. | Free, OGL. | Decennial staleness; mid-year estimates help. Area-level, not property-level: this is context, not identity. |
| **VOA Council Tax bands** | Band per dwelling, a rough value and size proxy that exists for *every* dwelling, including the ~40% never seen in PPD. | Free lookup; bulk via VOA open data. | 1991 valuations in England; useful mainly as a stratifier. |
| **OS Open products (OpenUPRN, Open Greenspace, OS Open Rivers, Code-Point Open)** | Canonical property IDs (UPRN) for linkage; green/blue space proximity; land-use context. | Free, OGL. | Full AddressBase (address-to-UPRN with rich attributes) is a paid licence and becomes worthwhile at pilot stage; it also solves the PAF question through one licence. |

## Tier 2: strong additions at pilot stage

- **Historical listings data** (portal scrapes are contractually fraught; licensed feeds via TwentyCi, Sprift, or Land Insight are the clean route). Gives you: current and past listings, withdrawn listings (a *very* high-propensity signal: tried to sell, failed), time-on-market, price reductions. Withdrawn-in-last-3-years may be the single best targeting feature available anywhere.
- **Planning applications** (open via planning.data.gov.uk and council portals). An extension application can signal staying (invest to stay) or selling (adding value pre-sale); a *granted but unbuilt* permission skews sell. Also flags developers and landlords.
- **Probate and mortality**: individual probate records are searchable but not bulk-open; ONS mortality by LSOA and age is open. In practice, the model reaches the lifespan effect through proxies: owner tenure length, EPC-derived age of last intervention, census age structure and single-occupancy at small-area level. Long tenure plus an ageing single-person household area is the actionable version of "houses sell when lives end", without processing anyone's personal data.
- **Rental listings and HMO licence registers**: identifies landlords (Section 24 tax pressure and regulation have been pushing amateur landlords to exit since 2016; exiting landlords are chain-free and price-rational, the ideal early cohort).
- **Companies House**: corporate ownership, SIC codes for landlord companies, dissolution events (a dissolving property SPV often precedes disposal).
- **HM Land Registry paid datasets**: Overseas Companies and UK Companies that own property (free); full title register lookups are £3 each at point of need (owner name for legal process, never for the mailing list without care).

## Tier 3: later, or buy-side products

- **TwentyCi / Sprift / PropertyData / Land Insight aggregations**: commercial bundles of much of the above with UPRN matching done. Worth benchmarking build vs buy once the pilot proves the funnel; likely buy for speed, build for moat.
- **Mobility and demographic panels** (CACI, Experian): household-level life-stage segments. Costly, and GDPR-weighty; probably unnecessary given how far area plus property plus tenure features go.
- **Electoral roll (edited register)**: purchasable, but personal data with opt-out bias; avoid until there is a lawyer in the building.

## The one dataset money cannot buy

Offer-acceptance outcomes: which owners, receiving which premium over which estimated value, engaged, declined, or accepted. It does not exist anywhere. The postcard campaigns generate it as a by-product from wave one, which is why the pilot should randomise offer bands within cohorts from the start (a contextual bandit over premium levels). Eighteen months of waves at even modest scale produces a proprietary reservation-price surface for UK latent supply that neither portals (demand-side data only) nor agents (unstructured, branch-local knowledge) can replicate. That, not the propensity model, is the defensible asset.

## Linkage plan

UPRN is the join key that makes this a database rather than a pile of CSVs: PPD address → UPRN (via AddressBase or open matching against OS OpenUPRN + Code-Point), EPC address → UPRN (the register now carries UPRNs for most certificates), council tax → UPRN, listings feeds arrive UPRN-keyed from the commercial providers. Postcode → LSOA carries all area features. Our feasibility study used (postcode, PAON, SAON) string keys, which is the correct zero-budget approximation and matched ~15m distinct properties; production should move to UPRN in week one.
