# Feasibility research: predicting latent housing supply

Empirical study of how predictable UK property sales are, run on the full
HM Land Registry Price Paid Data for England and Wales, 1995 to 2019
(24,254,747 standard residential transactions, 13,790,299 distinct
properties linked by address).

## Reproducing

```bash
pip install pandas scikit-learn matplotlib pyarrow

# 1. Get the yearly PPD files (pp-1995.csv.zip ... pp-2019.csv.zip) from
#    https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads
#    (or extend to the present with the current single-file download).

# 2. Build the linked transaction dataset (~5 min, ~4 GB RAM):
python src/build_dataset.py <dir-with-zips> data/transactions.parquet

# 3. Descriptive survival analysis (tenure, hazard curves, turnover):
python src/survival_analysis.py data/transactions.parquet outputs/

# 4. Propensity model with out-of-time evaluation (5% property sample):
python src/propensity_model.py data/transactions.parquet outputs/ 5

# 5. Geographic layer (needs the AHAH repo and Geovation postcode DBs):
#    github.com/GeographicDataService/ahah
#    github.com/Geovation/postcode-lookup-sqlite
python src/build_geo_features.py <pc-db-dir> <ahah-data-dir> data/geo_postcode.parquet

# 6. Does geography help? Ablation, then where it helps, then economics:
python src/geo_ablation.py data/transactions.parquet data/geo_postcode.parquet outputs/ 5
python src/longtenure_analysis.py data/transactions.parquet data/geo_postcode.parquet outputs/ 5
python src/response_economics.py outputs/ 1.59

# 7. Data for the prototype site:
python src/export_demo_v2.py data/transactions.parquet data/geo_postcode.parquet data/demo_v2.json
```

Outputs land in `outputs/`: charts (PNG), `survival_results.json`,
`model_results.json`. Headline findings are written up in
[`../docs/02-prediction-problem.md`](../docs/02-prediction-problem.md).

## What each script does

- **`src/build_dataset.py`** parses the yearly PPD zips, keeps standard
  (category A) residential sales, and links transactions into properties
  keyed on (postcode, PAON, SAON) — the standard repeat-sales approach
  for this dataset. Production would switch to UPRN matching.
- **`src/survival_analysis.py`** builds ownership spells
  (purchase → next sale, right-censored at end-2019) and estimates the
  discrete-time sale hazard by tenure year, overall and by property type
  and price band, plus local turnover dispersion across ~2,300 postcode
  districts.
- **`src/propensity_model.py`** frames "which homes sell next year?" as
  discrete-time hazard prediction on a property-year panel, trains a
  gradient-boosted model on 2001-2015 and evaluates strictly
  out-of-time on 2017-2019, reporting AUC, lift, gain and calibration.
- **`src/build_geo_features.py`** builds a postcode-level geographic
  table for England and Wales (1.57M postcodes): real AHAH air quality
  by nearest LSOA, distance to the nearest GP / hospital / dentist /
  pharmacy, built density, and settlement gravity. All in EPSG:27700.
- **`src/geo_ablation.py`** compares transaction-history-only against
  +geography and +life-stage feature sets, out-of-time.
- **`src/longtenure_analysis.py`** bootstraps where the added data
  actually helps, by owner tenure band, with 95% intervals and
  permutation importance for long-tenure owners.
- **`src/response_economics.py`** converts model lift into break-even
  scan rate, postage per completed sale, wave-protocol spend caps, and
  the probability a buyer hears nothing.

## The national model review (docs/06)

```bash
pip install lightgbm rasterio pyproj

# 8. A 30 m outlook for every postcode in England and Wales, from the
#    Copernicus GLO-30 surface model and its water mask (48 tiles):
python src/build_view30.py data/cop30 <pc-db-dir> data/view30_postcode.parquet 4

# 9. The national property-year panel, version 2: 73 signals per home-year,
#    written as float16 chunks of 5% of all properties each (8 chunks = 40%,
#    76 million home-years, 11 GB):
python src/panel2.py data/transactions.parquet data/geo_postcode.parquet \
    data/view30_postcode.parquet data/panel 8

# 10. The experiments, each out-of-time with block-bootstrap intervals:
for e in ladder curve deploy rolling sampling ablate; do
  python src/model_lab.py data/panel outputs/lab $e 4
done

# 10b. Judge every fitted model inside each postcode district, the way a
#      campaign is mailed, then print the tables and draw the charts:
python src/panel_districts.py data/transactions.parquet data/panel 2
python src/local_eval.py data/panel outputs/lab
python src/lab_report.py outputs/lab outputs/views2
```

- **`src/build_view30.py`** warps the Copernicus tiles to the British
  National Grid and casts 120 rays to 30 km from every postcode: skyline
  height by compass quarter, how far you can see, sea and inland water in
  view, hills on the horizon, plus relief, slope, aspect and distance to
  the coast.
- **`src/panel2.py`** rebuilds the property-year panel around what the
  Price Paid Data is actually like: repeat sales per property, prices at
  both ends of an ownership, 1.2 million postcodes nested in sectors and
  districts, a strong market cycle, and new-build estates that sell in
  waves. Every signal for year *t* uses data up to *t − 1* only.
- **`src/model_lab.py`** trains LightGBM out-of-core on those chunks.
  `ladder` adds one family of signals at a time; `curve` trains the same
  model on 1% to 40% of the country; `rolling` compares a model frozen
  in 2015 with one refitted each year; `sampling` checks that training on
  every sale plus a quarter of the non-sales loses nothing; `ablate`
  removes geography or outlook from the largest model; `deploy` fits the
  model the prototype scores with.
- **`src/panel_districts.py`** and **`src/local_eval.py`** recover the
  district of every test row and score each model on its ranking inside
  a district and year. National scores reward a model for knowing that
  one town turns over faster than another, which is no help once a buyer
  has chosen the town.
- **`src/lab_report.py`** prints every figure quoted in the write-up and
  draws the two charts.

## House-level views in two cities (docs/07)

```bash
# 11. Terrain: 1 m LIDAR surface and ground models, OS OpenMap Local,
#     OS Open UPRN address points (all open data):
python src/fetch_lidar.py dsm data/terrain/lidar_bath 368000 382000 160000 170000
python src/fetch_lidar.py dtm data/terrain/lidar_bath 368000 382000 160000 170000

# 12. Every house in the city: upper-window and garden outlooks, garden sun,
#     sight-lines to landmarks, and drawn panoramas per postcode sector:
python src/city_views.py exeter outputs/views2 3
python src/city_views.py bath outputs/views2 3
python src/city_views.py bath outputs/views2 3 sectors   # redraw panoramas only

# 13. Do the views predict sale timing in both cities, and does the effect
#     carry from one city to the other? How well does the national 30 m
#     layer track the 1 m truth?
python src/view_ablation2.py data/transactions.parquet outputs/views2 outputs/views2
python src/view_fidelity.py data/view30_postcode.parquet outputs/views2 outputs/views2/view_fidelity.json

# 13b. Sun on the windows, front and back, downstairs and at the top floor,
#      for every house; then whether lighter homes are sold less often:
python src/light.py compute bath outputs/views2 3
python src/light.py compute exeter outputs/views2 3
python src/light.py analyse data/transactions.parquet outputs/views2

# 14. Data for prototype v4, then inline it into the page:
python src/export_site_v4.py score data/transactions.parquet data/geo_postcode.parquet \
    data/view30_postcode.parquet outputs/lab/model_deploy.txt data/site_cache
python src/export_site_v4.py export data/site_cache data/geo_postcode.parquet \
    outputs/views2 outputs/lab ../web/demo_v4.json
python ../web/build.py
```

- **`src/views2.py`** is the house-level engine: one viewpoint at the
  upper windows and one in the garden of each address point, 240 rays
  each, 1 m surface to 1 km and 30 m terrain to 30 km in one pass; hours
  of direct sun in the garden from the horizon profile and the sun's
  path; sight-lines to named landmarks; and the layered panorama used to
  draw the view.
- **`src/city_views.py`** runs it for a whole city and writes per-house,
  per-postcode and per-sector tables. Exeter and Bath are configured;
  adding a city is a grid, a list of outcodes and a list of landmarks.
- **`src/view_ablation2.py`** and **`src/view_fidelity.py`** are the two
  checks: sale timing, and national-layer fidelity.
- **`src/light.py`** stands one metre outside each house's front and back
  walls at window height, traces the skyline, and counts the hours of
  direct sun on those windows through the year. Its `analyse` step tests
  the link to how often homes are sold, on all postcodes and on those
  where every house faces the same way.
- **`src/export_site_v4.py`** scores every owned home in both cities with
  the deployed national model and joins house-level views at the
  postcode. No address, postcode or coordinate of an individual home is
  exported.
