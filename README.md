# Not On The Market

A consumer platform built on one observation: at any moment only about
3% of the UK's 29.9 million homes are visibly for sale, yet almost all
of them would sell at some price. Not On The Market predicts which
homes would sell if made the right offer, describes those hidden groups
of homes to registered buyers, and reaches the owners directly by
postcard, with a QR code to a private offer page. It then acts as the
transaction's admin layer and emotional circuit breaker in place of a
traditional estate agent.

The prototype trades under the working name **Quiet Market**.

## What is in this repository

| Path | Contents |
|---|---|
| [`docs/01-concept-assessment.md`](docs/01-concept-assessment.md) | Honest evaluation of the concept: reality check on the premise, what is strong, the problems most likely to kill it, regulation, business model, where to start and the numbers that decide go or no-go. |
| [`docs/02-prediction-problem.md`](docs/02-prediction-problem.md) | The prediction problem in depth: how it is framed, results from 25 years of Land Registry data, a map of what is and is not predictable, and the modelling roadmap. |
| [`docs/03-data-sources.md`](docs/03-data-sources.md) | Inventory of usable UK data sources, their licences and catches, and the plan for linking them. |
| [`docs/04-does-open-geography-help.md`](docs/04-does-open-geography-help.md) | Does open environmental data make targeting good enough? An honest test with ranges, plus the response economics that decide whether buyers get replies and how much postage is at risk. |
| [`docs/05-views-without-photos.md`](docs/05-views-without-photos.md) | The first view experiment: the outlook from every Exeter postcode, computed from a 1 metre laser survey and a 3-D model of buildings and trees, searchable without a photograph. |
| [`docs/06-national-model-review.md`](docs/06-national-model-review.md) | The whole country and a harder look at the model: every home in England and Wales, 190 million home-years, 73 signals, a fairer local yardstick, and a clear answer on whether more data unlocks bigger effects. |
| [`docs/07-house-level-views.md`](docs/07-house-level-views.md) | House by house: every home's view and garden sun, "can see the cathedral" as a search, the drawn panorama, Bath as the second city, and whether views or sunlight predict how long people stay, tested in four cities and on top of the national model. |
| [`research/`](research/) | The reproducible study behind all of the above. See [`research/README.md`](research/README.md). |
| [`web/`](web/) | The prototype site. `template.html` is the page, `demo_v4.json` its data, `build.py` joins them into `index.html`. |

## Headline findings

1. **When a home sells has strong, learnable structure.** The yearly
   chance of a sale peaks at about 6.5% in years 3 and 4 of ownership
   and falls to about 2.4% by year 24, with large, steady differences by
   property type and price band.
2. **Long-held homes are the volume.** Nearly 4 in 10 sales now come
   from owners who bought 24 or more years ago. That is exactly the
   hidden supply the product targets.
3. **Targeting works on years the model has never seen, and its ceiling
   is now mapped.** Writing to the best tenth of homes in a district
   reaches 1.68 times as many sellers as writing at random. A rebuild
   on every home in England and Wales, twenty times the data, with 73
   signals instead of 13, moved that from 1.61 to 1.68
   ([docs/06](docs/06-national-model-review.md)).
4. **More data helps, but only a richer model, and only slowly.** The
   original 13 signals had learned all they could from 1% of the
   country. The 73-signal model is no better at 1%, clearly better at
   5%, and best with every home in the country. But each doubling of
   data adds only about 0.01, and there are no doublings left.
5. **Owners of 20 years or more remain the weak spot.** The original
   model manages 1.17 times random for them and the every-home model
   1.25, which is encouraging but not yet proven. The next real gain has
   to come from signs of intent: a new energy certificate with no sale,
   a withdrawn listing, a planning application, a probate notice.
6. **Fixed facts about a place do not help choose which doors to write
   to.** Air quality, distances and a national view layer add nothing
   inside a district once local sale history is in the model. For views
   this was tested on every home in the country.
7. **The view can be computed, drawn and searched for every house,
   without a photograph.** All 89,539 houses in Exeter and Bath have
   their own drawn panorama. In Exeter 22% of addresses can see the
   cathedral, and in Bath 28% can see the Abbey. On nearly half of
   Exeter's postcodes some homes have the cathedral in sight and their
   neighbours do not, which is why it has to be done house by house
   ([docs/07](docs/07-house-level-views.md)).
8. **The method travels, and a view is worth the same in both cities.**
   Built in Exeter and run unchanged in Bath, it puts the long views on
   the hillside streets and not the valley floor, and buyers pay 4% to
   5% more for a long view in both places. A score built from Exeter's
   sales alone, never shown a Bath sale, predicts Bath prices, and the
   reverse holds too.
9. **A view changes what a home is worth, not when its owner sells.** An
   earlier finding that homes with long views sell less often holds in
   Exeter and nowhere else among four cities. Views are for the buyer's
   search and for setting the offer, not for choosing doors.
10. **Lighter homes are kept longer, and the national model already
   knows.** Two cities left this as a lead. Adding Plymouth and Bristol,
   401,845 houses in all, made it a finding: more sun on the windows
   and in the garden goes with fewer sales in every city, like for
   like. But once the national model's own score is allowed for,
   nothing is left, and adding these measures does not pick better
   doors. The model sees the same streets through how often they
   sell.
11. **Whether a buyer hears back is a product-design problem, not a
    modelling one.** Break-even is 1 owner in 300 scanning their card.
    The whole model review moved the postage per conversation by £5.
    What decides the outcome is how wide the buyer's brief is, which is
    why the prototype searches by the life you want rather than by
    street.

## The prototype

Open `web/index.html` in a browser. It covers two cities, Exeter and
Bath:

- **Describe the life you want**: clean air, open surroundings, minutes
  from the centre, a GP nearby, a budget.
- **Say what you would like to see**: long views, water, hills, a garden
  that is not overlooked, evening sun, sunny back rooms, and whether you
  can see the cathedral or the Abbey. Homes are counted only if they
  have everything you asked for.
- **See the view drawn**: page through six real houses in each
  neighbourhood, each with its upstairs view and its garden with the
  sun's path.
- **Send postcards** (simulated: nothing is printed or posted) and
  follow the replies.
- **The owner's side**: a private offer page reached from the card,
  showing the offer and the drawn view of a house on the owner's
  postcode.

No address, postcode or coordinate of any individual home is in the
site's data.
