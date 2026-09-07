# Not On The Market: concept assessment

*An honest evaluation of the idea, its mechanics, and where the risk actually sits.*

## Verdict in one paragraph

The core insight is sound and the timing is decent: live listings are a tiny fraction of the housing stock, buyer pain in low-stock markets is real, and the machinery to act on latent supply (open transaction data, cheap ML, postcard APIs, QR flows) all exists. The propensity-to-sell model is not speculative; Street Group's Spectre already sells one to estate agents and claims campaign uplift of around 300%, so the ML core is commercially proven. What is genuinely novel here is pointing that machinery at buyers rather than agents, and pooling buyer demand to manufacture supply. The hard part is not the model. The hard part is the last mile: response economics on the postcard, the credibility gap between "the right offer" in a model and an offer a specific buyer will actually complete on, and the operational weight of progressing transactions between two parties who were not looking for each other. Those are solvable, but they are the business, and the ML is the top of the funnel.

## Reality-checking the premise

The "1,000x" framing needs tightening, because investors and journalists will check it.

- The UK has roughly 29.9 million dwellings (about 25.6 million in England).
- Rightmove carries roughly 900,000 sale listings at any one time, and portal overlap is near-total, so live supply is about 3% of stock.
- Around 1.0 to 1.2 million residential transactions complete in a normal year (HMRC SDLT data), so about 3.5 to 4% of the stock trades annually.

So the honest multiplier on *visible* supply is about 30x, not 1,000x. The stronger and equally true framing: at any moment, 97% of the housing stock is invisible to buyers, and economic theory says essentially all of it is for sale at some price. The product question is not whether latent supply exists. It is what premium unlocks it, and whether that premium still leaves a deal the buyer wants. That reframing also survives diligence.

There is a second premise worth keeping: your human-lifespan point. Most owners do sell within their lifetime, and life events (death, divorce, downsizing, job moves, schools) drive a large share of sales. That means sale timing is not noise; it has structure a model can learn. Our own analysis of 25 years of Land Registry data (see `docs/02-prediction-problem.md`) confirms strong, stable structure in who sells when.

## What is genuinely strong

**1. Demand-weighted canvassing flips the economics.** The naive version (each buyer triggers their own mail-out) is ruinously expensive. The right version pools all registered buyer demand, scores every property against it, and sends one postcard per property on behalf of many buyers: "Three vetted buyers are ready to pay £415,000 to £445,000 for a house like yours. No viewings circus. Scan to see the offer." Cost is amortised across the buyer side, and the message is radically stronger than an estate agent's "we have buyers in your area" letter because it contains a number.

**2. The learning loop is a genuine moat.** Land Registry tells everyone what sold. Only Not On The Market would know what offers were *declined*, at what premium to estimated value, for which property types, from which owner tenure bands. Every postcard is a labelled experiment on reservation prices. Nobody else is running that experiment at scale; agents' canvassing feedback is unstructured and hoarded branch by branch. Two years in, the offer-acceptance model is the asset, not the propensity model.

**3. Precedent failure supports this design rather than condemning it.** Zillow's Make Me Move (owners self-declare a dream price) was quietly discontinued: passive, owner-initiated latent supply does not move. This is the mirror image: outbound, buyer-funded, with a concrete number attached. The lesson from Make Me Move is that latent sellers do not come to you, which is precisely the assumption this idea is built on.

**4. The seller-side pitch is underrated.** For a certain owner (older, private, dreading the staging-viewings-chain circus), "a vetted buyer will pay £X and complete in eight weeks, and we handle everything" is a better product than a listing. Off-market is a *premium* experience for sellers, not a compromise. This deserves equal billing with the buyer-side story.

## The hard problems, in order of how likely they are to kill it

**1. Funnel economics on the postcard.** Direct mail response rates run roughly 0.5 to 2% for cold commercial mail; a genuinely specific offer should beat that, but assume it does not until proven. Illustrative funnel for one buyer cohort: 5,000 targeted properties, at 60 to 80p per printed and posted card (Stannp-class API pricing, volume dependent) is £3,000 to £4,000 per wave. At a 2% scan rate that is 100 engaged owners; at 10% of those seriously entertaining the range, 10 live conversations; perhaps 2 to 4 agreed sales if the offer logic is right. Against a combined fee of, say, 1.5 to 2.5% on a £400k transaction (£6k to £10k), the arithmetic works *only if* targeting quality holds and one mail wave serves many buyers. This is exactly what the propensity model is for: our feasibility model concentrates around a third of all next-year sellers into the top decile of stock, which triples mail efficiency against random from day one, before any acceptance-model learning. The pilot's single most important measurement is scan rate by propensity decile.

**2. The credibility gap in "the right offer".** The model prices a cohort; the buyer buys a specific house they have never seen, with unknown condition, and the owner anchors on the postcard number. Surveys, condition and lender valuations will move figures after acceptance, and a retreating offer poisons trust in both directions. Mitigations that need designing in from day one: present a range, not a point; make the mechanics explicit ("indicative range, refined after a walkthrough"); collect condition signals early (EPC data gives floor area, age band and current condition proxies); and consider light reservation agreements with mutual lock-in once a figure is agreed. Expectation choreography is the product here.

**3. The chain problem.** A majority of responding owners will need somewhere to go, and off-market approaches over-sample owners who were not planning a move. Three partial answers: target cohorts with high chain-free propensity (probate executors, landlords exiting, downsizers with obvious equity); make "we will find your next home too" part of the accept flow, which turns each seller into a buyer inside the system and compounds the flywheel; and be honest that median time-to-complete will look more like a normal purchase than the postcard's "quickly" promise, then engineer the exceptions.

**4. Making cohorts feel real without faking it.** Describing a cohort instead of showing listings is clever and legally safer than it sounds, provided the imagery is honest. AI-generated photoreal "homes" that buyers mistake for real inventory would invite trouble under consumer protection law (the DMCC regime is less forgiving than the old CPRs) and would corrode trust on first contact with reality. Better: data-rich archetype cards (real aggregate statistics: "typically 1930s semis, around 1,100 sq ft, EPC D, 8 minutes' walk to the station, likely to need £420k to £450k"), clearly-labelled illustrative imagery, street-level context photos rather than fake interiors, and above all the number that no portal can show: "an estimated 240 properties matching this brief would likely sell at the right offer; 31 score in our top likelihood band". That count is the wow moment. Sell the certainty of the mechanism, not fake photos.

**5. Regulation is a cost, not a blocker, but it starts on day one.** Introducing buyers to sellers and sending out property particulars is "estate agency work" under the Estate Agents Act 1979 from the very first postcard. That means membership of an approved redress scheme (The Property Ombudsman or PRS), HMRC registration for anti-money-laundering supervision, customer due diligence on both sides, and compliance with material-information rules. All routine, all budgetable. Two sharper points: (a) postcards addressed to "The Homeowner" avoid processing personal data, which keeps UK GDPR exposure minimal, and postal marketing sits outside PECR's consent rules anyway; (b) the address fields in Price Paid Data and the EPC register are derived from Royal Mail's PAF and are licensed for property-price-information services, not for bulk mailing lists, so the mailing operation needs a proper PAF licence or a licensed address supplier. Modest cost, but skipping it would hand Royal Mail a stick to beat you with.

**6. The name.** "Not On The Market" is a direct play on OnTheMarket.com, a major portal owned since late 2023 by CoStar, a litigious US data giant. The pun is excellent and the trademark risk is real. Get a clearance opinion before spending on brand.

## On acting as the estate agent (the emotional circuit breaker)

Agree, and would go further: this is not optional. Someone must verify the buyer is proceedable, manage the viewing that must eventually happen, absorb the negotiation heat, and drive sales progression, where roughly a quarter to a third of agreed UK sales normally collapse. If Not On The Market only makes introductions, it inherits the fall-through rate and none of the fee. If it owns progression (checked mortgage in principle, conveyancers instructed at acceptance, milestone tracking, both parties talking to the platform rather than each other), it earns the fee and the data. The emotional-circuit-breaker framing is exactly right: principals negotiating directly is how off-market deals die. An interesting structural advantage over traditional agents: an agent is legally and commercially the seller's champion, which is why buyers distrust them. A platform paid by both sides for *completion* can be honest with both, closer to a mediator with admin superpowers. That positioning ("the first agent that works for the transaction, not the listing") is also a clean marketing line. It does mean holding both-sides duties carefully: fee transparency under the 1979 Act, and clarity in the terms about who the client is at each stage.

## Business model sketch

- **Buyer side**: subscription or success fee for access to latent supply (scarce, differentiated, and buyers are the party in pain). A US-style buyer's-agent fee is unusual in the UK but plausible here because the inventory does not exist anywhere else.
- **Seller side**: fixed fee or low percentage on completion, undercutting the 1 to 1.5% high-street norm, justified by zero marketing cost and no viewings circus.
- **Later**: the acceptance-model data itself (pricing latent supply) has obvious institutional value, but consumer trust dies if the model is seen to serve funds first. Sequence carefully.

## Recommended wedge

Do not launch nationally. Pick two or three micro-markets where demand visibly exceeds supply and cohorts are describable: family houses near named school catchments in two or three cities, and one lifestyle market (coastal Devon or Cornwall, the Cotswolds). Then:

1. Build the buyer waitlist first (cheap: content about off-market buying, the "how many homes match your brief" calculator as the lead magnet).
2. Score the local stock, mail the top decile only, in waves, measuring scan rate by model decile so the first campaign is also the first model-validation experiment.
3. Run offers at two or three premium bands per cohort to start learning the acceptance curve immediately (this is a bandit experiment wearing a postcard costume).
4. Progress the first ten transactions by hand, with founders doing the circuit-breaking. Write down what breaks; that becomes the ops playbook.

**Go/no-go metrics after two mail waves**: scan rate above 1.5% overall and monotonically increasing in model decile; at least 5% of scanners requesting the offer detail; at least one agreed sale per 3,000 cards; CAC per agreed sale under half of expected completion revenue.

## Sources

- [HMRC monthly property transactions commentary](https://www.gov.uk/government/publications/monthly-property-transactions-completed-in-the-uk-with-value-40000-or-above/uk-monthly-property-transactions-commentary)
- [Dwelling stock estimates, England (MHCLG)](https://www.gov.uk/government/statistics/housing-supply-net-additional-dwellings-england-2024-to-2025/housing-supply-net-additional-dwellings-england-2024-to-2025)
- [Rightmove property for sale (live listing count)](https://www.rightmove.co.uk/property-for-sale.html)
- [Spectre (Street Group) propensity-to-sell prospecting](https://spectre.uk.com/product/spectre-prospecting)
- [Zillow Make Me Move discontinuation](https://www.realestatewitch.com/zillow_make_me_move/)
- [Who regulates estate agents? House of Commons Library](https://commonslibrary.parliament.uk/research-briefings/cbp-10692/)
- [HMRC AML guidance for estate agency businesses](https://www.gov.uk/government/publications/money-laundering-understanding-risks-and-taking-action-for-estate-agency-and-letting-agency-businesses/understanding-risks-and-taking-action-for-estate-agency-businesses)
- [About the Price Paid Data (licensing, PAF address restrictions)](https://www.gov.uk/guidance/about-the-price-paid-data)
- [EPC open data licensing analysis (Owen Boswarva)](https://www.owenboswarva.com/blog/post-hou2.htm)
- [Stannp direct mail API pricing](https://www.stannp.com/uk/detailed-pricing)
