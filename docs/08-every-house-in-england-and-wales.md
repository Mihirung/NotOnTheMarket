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
| House-level views, garden sun, window light and landmarks for 401,845 houses in four cities | The same for **HOUSES_TOTAL houses** in England and Wales |
| The national model saw only a 30 m view from each postcode centre | The national model has been offered every house-level measure, averaged over each postcode's addresses |
| Houses joined to sale records by the nearest postcode centre | Houses joined by their **exact postcode**, from the ONS UPRN Directory |
| A drawing for every house in four cities | A drawing for every house in the country |
| A hand-picked list of ten landmarks | **LANDMARKS_TOTAL landmarks**: every cathedral, abbey, castle, lighthouse, folly, tower and Grade I listed church with an English Wikipedia article, and every hill with 30 m or more of prominence |
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

RESULTS_PLACEHOLDER

## Finding the best house in the country

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
SEARCH_RESULTS

## The site, for every postcode area

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

## Adding a signal

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
