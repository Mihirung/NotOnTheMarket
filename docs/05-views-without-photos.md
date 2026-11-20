# The view, without a photograph

*Can we tell a buyer what they would see from a home nobody has
photographed — and let them search on it?*

Yes, and more precisely than expected. This document describes the
viewshed experiment: what we built from open 3-D data, what it can and
cannot say about a home's outlook, how it validated against places
anyone from Exeter knows, and how it now appears in the prototype.

## 1. Why this matters for a photo-less product

Every other property site is organised around photographs. We cannot
show any, because none of these homes is for sale. That forces a choice
between apologising for the gap and filling it with something better.
The view is the one thing a photograph is actually *bad* at: a picture
shows one window, on one day, at one focal length. A model of the land,
the buildings and the trees can describe every bearing from every
window, and can be searched.

It also serves the point you made about unconventional filters. "Water
somewhere in the upstairs view" or "a low western horizon so the garden
gets evening sun" cut across named areas entirely. A buyer who thinks
they want Topsham may find the same estuary view from a street in
Countess Wear they had never considered.

## 2. What we built

All sources are open and current:

| Layer | Source | Role |
|---|---|---|
| Surface model, 1 m | Environment Agency LIDAR composite DSM (last return), via the Defra WCS | Every building and tree as an obstacle, out to 1 km |
| Terrain model, 1 m | Environment Agency LIDAR composite DTM, same route | Ground height at the viewpoint; tree height from DSM minus DTM |
| Wide terrain, 30 m | Copernicus GLO-30, reprojected to British National Grid | The far field to 30 km, with earth-curvature and refraction correction, for hills and sea |
| Buildings, water, woodland | OS OpenMap Local (polygons rasterised to the 1 m grid) | Classifying what forms the skyline on each bearing |
| Viewpoints | ONS postcode centroids, moved to the nearest open ground | The garden or street in front of a typical home in that postcode |

Study area: 18 × 14 km around Exeter, 63 surface-model tiles and 41 of 63 terrain tiles (the rest filled from a ground proxy), 3,961 postcodes.

For each viewpoint the engine casts 360 rays and records, per bearing,
the horizon angle, what defines it (building, trees, land, water, hills,
or open sky), how far the eye can see, and whether six named landmarks
are in line of sight. Two outlooks are computed:

- **Garden**: eye 1.6 m above ground, the owner's own house left in
  place. Governs enclosure, privacy and sun.
- **Upstairs**: eye 5 m above ground, the owner's own building
  flattened, since you may stand at whichever window faces the view.
  Governs long views, water and hills.

From those come the plain-English properties a buyer asks about: long
views, water in view, hills on the horizon, not overlooked, evening sun.

## 3. What it found: Exeter's outlooks, measured

All 3,961 postcodes in EX1–EX4, computed in about four minutes.

**From the garden** (eye 1.6 m, middle of the nearest open space):

| | 25th pct | median | 75th pct |
|---|---|---|---|
| Skyline height above eye level | 8° | 12° | 18° |
| Share of bearings with a neighbouring building within 40 m above eye level | 37% | 58% | 74% |

A 12° skyline is what a 7 m house 25 m away gives you: a typical
garden with houses round it. The city centre is tighter (22°, two in
three bearings overlooked); the hill at Pennsylvania and the estuary
town of Topsham are the most open (10°).

**From upstairs** (eye 5 m, own house set aside):

| | 25th pct | median | 75th pct |
|---|---|---|---|
| Share of bearings that see 2 km or more | 0% | 4% | 14% |
| Longest line of sight | 2.7 km | 12 km | 27 km |
| Share of bearings with water in view | 0% | 0.6% | 6% |
| Share of bearings with hills (180 m+) in view | 0% | 0.3% | 4% |

Long views are a minority asset even upstairs: half of all homes see
2 km on fewer than one bearing in twenty. But the half that do, see a
long way — the median home's longest sight-line is 12 km.

**Landmarks** (line of sight from upstairs to one named point; a
strict test): the Haldon ridge 6.7% of postcodes, the sea at Exmouth
5.9%, the Exe estuary 4.9%, Exeter Cathedral 4.6%, Woodbury Common
4.5%, Haytor on Dartmoor 0%.

### Validation against places anyone from Exeter knows

Stated before looking: Topsham should show water; Pennsylvania long
views; the centre enclosure; St Leonard's trees.

| Place | Garden skyline | Overlooked | Long views upstairs | Longest sight-line | Water in view | Sees Haldon |
|---|---|---|---|---|---|---|
| Pennsylvania (hill, north) | 10° | 43% | 17% | 30 km | 9% | — |
| Topsham (estuary) | 10° | 48% | 15% | 27 km | **14%** | **35%** |
| Exwick (river valley) | 10° | 45% | 12% | 23 km | 9% | — |
| St Leonard's (villas) | 15° | 60% | 6% | 15 km | 6% | 7% |
| City centre | **22°** | **67%** | **3%** | 7 km | 1% | — |

Every expectation held. Two things the model got right that I had
wrong going in: distant hills clear a neighbour's roof far more easily
than nearby water does (Topsham sees the Haldon ridge nine kilometres
away from a third of its streets, but the river two hundred metres
away from one in seven — the next row of houses is in the way), and a
first-floor window in a dense city mostly sees the house opposite.

Three skylines, drawn from the model rather than photographed, are in
`research/outputs/skylines.png`: Topsham walled in east and west but
open across the estuary flats to the south; Pennsylvania open to the
east with Woodbury Common on the horizon; the city centre closed in by
buildings and trees all the way round.

### What it took to get right

Three bugs, each of which produced plausible-looking nonsense, are
worth recording for whoever builds the production version:

1. `rasterio.merge` silently returned an all-zero grid from the EA
   tiles (a float32 nodata edge case). Every horizon came out flat.
   Caught because "overlooked" was exactly zero everywhere.
2. The nearest non-building cell put the eye on the pavement against a
   wall, giving 60–70° skylines. The viewpoint is now the middle of the
   nearest open space.
3. The 30 m far-field terrain is itself a surface model with smoothed
   canopy; sampled from 30 m out it registered a wall in leafy suburbs
   and overrode the 1 m pass. Far samples now start at the local
   radius. Pinhoe went from "blocked at 30 m" to a 12 km sight-line.

## 4. Does the view predict when a home sells?

Yes, modestly, and in the direction you would guess. Within Exeter,
every property with sale history (469,627 property-years; 18,486 sales
to train on, 3,698 to test on), the published propensity model's
features against the same plus ten outlook metrics, strictly
out-of-time (train 2001–2015, test 2017–2019), 300 bootstrap resamples:

| | AUC | Top-decile lift |
|---|---|---|
| Transaction history + local market | 0.5926 | 1.52 |
| + outlook | **0.5991** | **1.54** |
| Difference (95% interval) | **+0.0065** (+0.0024 to +0.0101) | |
| Share of resamples where outlook helped | **100%** | |

That is a cleaner result than the AHAH environmental data gave
(+0.0034, interval touching zero): smaller sample, but the interval
sits well clear of zero.

Raw annual sale rates by quartile, before any controls:

| | Lowest quarter | Highest quarter | |
|---|---|---|---|
| Long views upstairs | 5.8% | 5.1% | homes with a view **stay** |
| Water in view | 5.8% | 5.1% | homes with water **stay** |
| Skyline height (enclosure) | 4.9% | 6.0% | enclosed homes **sell** |
| Overlooked within 40 m | 5.2% | 6.0% | overlooked homes **sell** |

With controls for tenure, type, price and local market in a
standardised logistic model, the strongest single terms are hills in
view (−0.033 per standard deviation: stay) and skyline height
(+0.027: sell). The view metrics are collinear with each other, so
read them as a set — openness and views lower the hazard, enclosure
and overlooking raise it — rather than trusting any one coefficient.

Two uses follow. The targeting model should carry these features.
More interestingly, the **offer model** should too: a home whose owner
has a view has measurably more inertia, so it needs a larger premium
to unlock, and the postcard can say why.

## 5. What it cannot tell you (yet)

Being straight about the edges:

- **It is a postcode, not a house.** The viewpoint is the nearest open
  ground to the postcode centre — a street of roughly 15 homes. Two
  houses on the same street can have very different views. The site
  therefore says "6 in 10 homes here" rather than pretending to know
  one house. Moving to house level needs addresses with coordinates
  (OS AddressBase / UPRN), which is a licence, not a research problem,
  and the engine already works per point.
- **It does not know which side your garden is.** The garden outlook
  is from the open ground nearest the centroid. A fuller version would
  compute from several points round the footprint and report the best
  and the worst.
- **Trees are as the LIDAR found them.** The surface model is a
  composite, largely flown in leaf-off winter months; summer views
  through deciduous trees will be shorter. The 2.5 m threshold for
  "tree" also ignores hedges and fences, so garden privacy is slightly
  overstated where a 2 m fence does the work.
- **Windows face where they face.** "Upstairs" assumes a window on the
  side that matters. For a mid-terrace that is front and back only.
- **Landmark visibility is a point test.** "Can see Haytor" tests the
  line of sight to one summit coordinate; a view of the moor's flank
  without the summit counts as no.
- **Vintage.** The composite DSM is the 2022 release; new buildings
  since then are absent.

## 6. Where to push it next

1. **House-level outlooks** with AddressBase, and a per-window variant
   that computes from each face of the footprint. Then the seller page
   can say "from your rear bedroom" rather than "on your street".
2. **Seasonal canopy**: use the first-return and last-return DSMs
   together to separate leaf-on and leaf-off horizons.
3. **A proper 3-D building model** (OS Building Height Attribute, or
   LIDAR-derived roof forms) to tell a neighbour's roof from their
   bedroom window — the difference between "overlooked" and "a roof is
   nearby".
4. **Render the view**: the horizon profile is one step from a
   synthetic panorama — a drawn skyline with the estuary, the hills and
   the cathedral tower in their true places. That is a picture of the
   view that is honest precisely because it is not a photograph.
5. **Search by the view of a specific thing**: "can see the cathedral",
   "can see the sea", "faces the sunset over Haldon" are all one line of
   code each now.
