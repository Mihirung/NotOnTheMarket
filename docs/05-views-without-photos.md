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

Study area: 18 × 14 km around Exeter, 126 LIDAR tiles, 3,961 postcodes.

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

RESULTS_SECTION

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
