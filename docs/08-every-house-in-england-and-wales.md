# Every house in England and Wales

This finishes the job [07-house-level-views.md](07-house-level-views.md)
started. Everything that was worked out house by house for Exeter, Bath,
Plymouth and Bristol has now been worked out, the same way, for every
house in England and Wales. The national model has been offered all of
it. Any house in the country can be found by any mix of these
characteristics and drawn. And any new signal can be tested on every
home with one command.

| Before | Now |
|---|---|
| House-level views, garden sun, window light and landmarks for 401,845 houses in four cities | The same for **24,114,764 houses** in England and Wales |
| The national model saw only a 30 m view from each postcode centre | The national model has been offered every house-level measure, averaged over each postcode's addresses |
| Houses joined to sale records by the nearest postcode centre | Houses joined by their **exact postcode**, from the ONS UPRN Directory |
| A drawing for every house in four cities | A drawing for every house in the country |
| A hand-picked list of ten landmarks | **9,765 landmarks**: every cathedral, abbey, castle, lighthouse, folly, tower and Grade I listed church with an English Wikipedia article, and every hill with 30 m or more of prominence |
| Each new signal needed new code to test | A signal is a table with one row per postcode; one command says what it is worth |

## 1. How it was done

**The same method, compiled.** The city runs used a program that held
every sample of every ray in memory, about a tenth of a second a house.
For 25 million houses that is a week. It was rewritten to walk each ray
once, for a batch of neighbouring houses together, keeping only what the
measures and drawings need. On a sample of Bath houses it gives the same
answer as the city program on every ray to the last decimal place, and
the same drawings, and takes about a tenth of the time. The one
deliberate change: a landmark's sight-line now follows the exact bearing
to the landmark rather than the nearest of the 240 rays, which agrees
with the old answer for 96% to 99% of houses and is the more accurate of
the two.

**The data, all open.**

| What | Where from |
|---|---|
| The 1 m surface (buildings and trees) and bare ground | Environment Agency LIDAR composite (England), Natural Resources Wales and Welsh Government national survey 2020 to 2023 (Wales) |
| Terrain beyond 1 km, and the sea | Copernicus 30 m elevation model and its water mask |
| Buildings, roads, water, woodland | Ordnance Survey OpenMap Local, all 32 squares that cover England and Wales |
| Where each house is | Ordnance Survey Open UPRN: 41.7 million address points, 28.1 million house positions in England and Wales |
| Which postcode each address is in | ONS UPRN Directory, September 2026 |
| Landmarks | Wikidata (structures with an English Wikipedia article), Database of British and Irish Hills (prominence 30 m or more), and the ten hand-picked Exeter and Bath landmarks |

**The run.** The country was cut into 1,711 cells of 10 km. For each,
the survey tiles for the cell and 1.1 km around it were downloaded,
assembled and deleted once no unfinished cell needed them, so the 1.1
terabytes of survey never had to be stored at once. Every house in the
cell then got exactly what the city houses got: its height and storeys,
its garden and which way it faces, the view from 1 m outside its front
and back walls at the top floor, the view and sun from its garden, the
hours of direct sun on its front and back windows downstairs and at the
top floor, which landmarks are in sight, and a drawing of both views.

**One concession: the drawings.** A drawing at the city runs' detail, a
point every 1.5 degrees, is about 1.6 kB a house compressed. For the
whole country that is 40 GB, more than this machine can hold. So the
national drawings keep a point every 3 degrees, taking the higher of
each pair of angles so nothing that stands above the skyline is lost.
Every measure is still worked out at 1.5 degrees, exactly as in the
cities.

**One failure, caught and fixed.** For about fifteen minutes on the first
night the England survey service answered with errors. The download code
treated five failed tries as "no survey here", so 23 cells in the Midlands
and Essex were filled from the 30 m terrain and kept only a fraction of
their houses. An audit of every cell (houses kept against address points,
survey coverage against land area, building heights) found them. The rule
is now strict: a tile is marked as missing only when the service says it
is outside its area; anything else is retried, and the cell waits until the
service is back. Those 23 cells and 14 others with any doubt were deleted
and recomputed. Each cell now records how many tiles were ruled out, and a
check runs every 50 cells.

## 2. What it found

**The run.** 24,114,764 houses at 27,968,320 address positions, with
37,323,304 landmark sightings, in 75.7 hours of computing over 1,711 cells.

**It matches the city runs.** Every house of the four city runs was found
again in the national run and compared measure by measure. Storeys, the way
the house faces, long views, water, hills, how overlooked it is, sun and
window light all correlate at 0.98 to 1.00 with the city answers, and their
averages agree to the second decimal place
(`research/outputs/national/checks.json`).

**It is not a sharper copy of the 30 m view.** Ranked postcode by postcode
across 1.48 million postcodes, the house-level measures agree with the old
30 m layer only loosely: 0.26 for long views, 0.45 for the furthest
sight-line, 0.37 for water in view. Only the sea (0.73) and hills on the
skyline (0.70) are close. The 30 m layer sees the land from the postcode
centre; the house-level run sees it from each window, past the
neighbouring roofs and trees.

## 3. The national model with every house-level signal

Every family was tested the same way, on every home: the national model
refitted with and without it on all 39,935,433 home-years from 2001 to
2015, and judged on 2017 and 2018 sales it never saw, ranked inside each
postcode district as a campaign would rank them. "Times random" is how much
more common sellers are in the best tenth of each district than in the
district as a whole.

| Family added to the current model | Sellers in each district's best tenth | Gain | 95% range | Verdict |
|---|---|---|---|---|
| None (the current model) | 1.689 times random | | | |
| House: views, garden, sun, window light, size, landmarks (43 columns) | 1.721 | +0.032 | +0.013 to +0.048 | add |
| Area character (10 columns) | 1.713 | +0.025 | +0.007 to +0.039 | add |
| What could be built without permission (11 columns, [09](09-planning-health-and-amenities.md)) | 1.727 | +0.037 | +0.020 to +0.053 | add |
| Pubs, parks, water, sea, restaurants (11 columns) | 1.693 | +0.005 | -0.010 to +0.020 | search and price only |
| **House, area and what could be built, together** | **1.741** | **+0.052** | **+0.032 to +0.068** | **deployed** |
| All of the above and the amenities | 1.720 | -0.020 against the deployed set | -0.035 to -0.006 | no |

Against the model deployed before this work began, the new one finds
+0.059 more (range +0.040 to +0.078). In plain terms, a mailing to the
best tenth of every district reaches about 3% more real sellers for the same
number of letters. The gain is clear of zero for owners of under 10 years
(+0.035, range +0.009 to +0.060) and of 10 to 19 years (+0.027, range +0.004
to +0.055); for owners of 20 years or more it is larger but less certain,
because they sell least often (+0.061, range -0.020 to +0.137).

Taken one at a time and comparing like with like, the clearest links are
the ones the cities suggested: overlooked homes sell more often (the same
sign in all eight regions), homes with more summer sun sell more often,
and homes boxed in by a high skyline to the south or west sell less often.
Once the national score is allowed for, 32 of the 43 house columns still
carry a link of their own, and all 43 carry a price.

**The house-level views can replace the 30 m views, but both are better.**
With the 30 m views taken out and the house-level ones put in, the model
gains +0.018 (range +0.002 to +0.034); with both it gains +0.032. The 30 m
layer still adds something the house-level one does not.

**The deployed model** has all 137 columns of the base, history, location,
30 m view, house, area and building families. It is trained on every home,
2001 to 2018 (50,694,427 home-years, 613 rounds), because a model refreshed
with recent years finds 2% to 4% more sellers than one that is not. It
scores 13,790,299 owned homes, and expects 512,042 of them to sell within
the year.

**Room to run.** Fitting on every home with 137 columns at first ran out of
memory: the library built a second, row-by-row copy of the table to time two
ways of training. It now trains column by column, which grows the same
trees without the copy, and the largest fit peaks at 13 GB on a 16 GB
machine. Each family takes under an hour to assess on every home.


## 4. Finding the best house in the country

Every house is given its national percentile on each of seventeen
characteristics: long views, the furthest sight-line, water, the sea,
hills, how overlooked the upstairs windows are, how overlooked the garden
is, room in the garden, evening sun, sun at the equinox and at midwinter in
the garden, sun on the windows over the year and at midwinter, and
landmarks, cathedrals, castles and named hills in sight. A search names the
characteristics that matter and averages their percentiles, so a house has
to be good at all of them to come top; the weakest of them breaks ties.

```bash
python research/src/find_best.py --all --top 20 --draw best.html
python research/src/find_best.py --want views water quiet_garden evening_sun --region "South West"
python research/src/find_best.py --want views light --sees "Salisbury Cathedral"
python research/src/national_best_pages.py best_homes.html best_homes.csv 5
```

The last one runs several briefs at once and draws every winner.
The search now covers 33 characteristics for all 24,114,764 houses: the
seventeen above, and clean air, a GP, a hospital, a park and parkland,
woods and water within reach, pubs near or pubs far, restaurants, few
takeaways, and what could be added without planning permission
([09](09-planning-health-and-amenities.md)). A house with a measure missing
ranks last on it, never first. The full report, with each winner's drawing
and postcode, stays on this machine and is not published; in outline:

| Brief | Where the winners are |
|---|---|
| The very best of everything | The Tamar above Saltash and Plymouth, the Somerset coast at Weston, Torbay |
| The finest views | The Llŷn peninsula, the Burry estuary, the north Somerset levels and coast |
| By the sea, with the evening sun | The Northumberland coast, Walney and Barrow, Whitby, Holderness, west Cumbria |
| A cathedral or abbey in sight | The Fens around Ely |
| A castle in sight | The Cumbrian and Northumbrian border |
| Salisbury Cathedral in sight | 11,485 houses; the best on the downs north of Salisbury and towards Romsey |

## 5. The site, for every postcode area

The prototype searched Exeter and Bath. It now searches any postcode area
in England and Wales, with the same measures drawn the same way. Each area
is a file the page loads when it is chosen. The page also carries every
postcode sector's share of homes with each combination of outlook and
light, so a brief can be matched against the whole country before choosing
where to look: tick "long views" and "evening sun in the garden" and it
lists the sectors in England and Wales where most homes have both, with a
button to look there. As before, no address, postcode or position of an
individual home is published; the drawings are of unnamed houses inside a
sector.
SITE_RESULTS

## 6. Adding a signal

A signal is a table with one row per postcode. Register it in
`research/src/signals.py` and run one command:

```bash
python research/src/assess_signal.py <NAME>
```

It answers five questions on the whole of England and Wales and writes
the answers to `research/outputs/signals/<NAME>.md`:

| Question | How |
|---|---|
| How much of the country has it? | Share of postcodes, and of the test home-years |
| Is each column linked with selling, like for like? | Holding type, price, years owned and year fixed; for the country and region by region |
| Is anything left once the current model's score is allowed for? | The same link, with the deployed model's own score held fixed |
| Does the model find more sellers with it? | The model refitted with and without the family, ranked inside each district as a campaign would be, with a range from resampling owners |
| Does it carry a price? | The premium for one step of each column within a sector, year and type |

The verdict line says whether to add it. A family goes into the deployed
model only if the gain in sellers found has a range clear of zero, so a
new signal can never make the model worse. The training table never needs
rebuilding: it holds only the year-by-year history of each home, and place
signals are looked up by postcode when a model is trained or scored.
