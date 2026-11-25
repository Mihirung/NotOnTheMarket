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
  keyed on (postcode, PAON, SAON), the standard repeat-sales approach
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
#    written as float16 chunks of 5% of all properties each. 20 chunks is
#    every home: 190 million home-years, 28 GB. A further argument starts
#    at a later chunk, to extend a table already built:
python src/panel2.py data/transactions.parquet data/geo_postcode.parquet \
    data/view30_postcode.parquet data/panel 20

# 10. The experiments, each out-of-time with block-bootstrap intervals:
for e in ladder curve rolling sampling ablate; do
  python src/model_lab.py data/panel outputs/lab $e 4
done
python src/model_lab.py data/panel outputs/lab ablate_view 4 100   # views, on every home
python src/model_lab.py data/panel outputs/lab deploy 4 100        # the site's model

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
  model on 1% of the country up to every home in it; `rolling` compares a model frozen
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
python src/city_views.py bath outputs/views2 3 sectors   # rebuild sector summaries only

# 12b. Draw any one house from the stored arrays (no terrain data needed),
#      by its row in the house table or by easting and northing:
python src/house_view.py exeter outputs/views2 one_house.html 4216

# 13. Do the views predict sale timing in both cities, and does the effect
#     carry from one city to the other? How well does the national 30 m
#     layer track the 1 m truth?
python src/view_ablation2.py data/transactions.parquet outputs/views2 outputs/views2
python src/view_fidelity.py data/view30_postcode.parquet outputs/views2 outputs/views2/view_fidelity.json

# 13a. Does the method travel? Known streets in each city, and whether a
#      view is worth the same price premium in both:
python src/travel_tests.py data/transactions.parquet outputs/views2

# 13b. Sun on the windows, front and back, downstairs and at the top floor,
#      for every house; then whether lighter homes are sold less often:
python src/light.py compute bath outputs/views2 3
python src/light.py compute exeter outputs/views2 3
python src/light.py analyse data/transactions.parquet outputs/views2

# 13c. The strict version of 13a: a score built from one city's sales
#      alone, tested on the other city, for price and for sale timing;
#      then the chart of it:
python src/transfer_tests.py data/transactions.parquet outputs/views2
python src/transfer_chart.py outputs/views2 ../docs/img/transfer.png

# 13d. More places. Plymouth and Bristol through the same program, then the
#      sunlight, garden and outlook tests on all four cities:
python src/fetch_lidar.py dsm data/terrain/lidar_plymouth 243000 259000 49000 63000
python src/fetch_lidar.py dtm data/terrain/lidar_plymouth 243000 259000 49000 63000
python src/fetch_lidar.py dsm data/terrain/lidar_bristol 351000 369000 166000 182000
python src/fetch_lidar.py dtm data/terrain/lidar_bristol 351000 369000 166000 182000
python src/city_views.py plymouth outputs/views2 4 && python src/light.py compute plymouth outputs/views2 4
python src/city_views.py bristol outputs/views2 4 && python src/light.py compute bristol outputs/views2 4
python src/scale_tests.py data/transactions.parquet outputs/views2

# 13e. Would these measures add to the national model? Score 2017 and 2018
#      in the four cities with the every-home model, then test on top of it:
python src/on_top.py score data/transactions.parquet data/geo_postcode.parquet data/view30_postcode.parquet \
    outputs/lab/model_all_100.txt data/site_cache/national_scores_cities.parquet
python src/on_top.py test data/site_cache/national_scores_cities.parquet outputs/views2
python src/scale_chart.py outputs/views2 ../docs/img/more-cities.png

# 14. Data for prototype v4, then inline it into the page:
python src/export_site_v4.py score data/transactions.parquet data/geo_postcode.parquet \
    data/view30_postcode.parquet outputs/lab/model_deploy.txt data/site_cache
python src/export_site_v4.py export data/site_cache data/geo_postcode.parquet \
    outputs/views2 outputs/lab ../web/demo_v4.json
python ../web/build.py
```

- **`src/views2.py`** is the house-level engine: viewpoints one metre
  outside the front and back walls at top-floor height, joined into one
  all-round view, and one in the garden; 240 rays each, 1 m surface to
  1 km and 30 m terrain to 30 km in one pass; hours
  of direct sun in the garden from the horizon profile and the sun's
  path; sight-lines to named landmarks; and the layered panorama used to
  draw the view.
- **`src/city_views.py`** runs it for a whole city and writes per-house,
  per-postcode and per-sector tables. Exeter and Bath are configured;
  adding a city is a grid, a list of outcodes and a list of landmarks.
- **`src/house_view.py`** draws any single house from the drawing stored
  for it: every house in both cities has one.
- **`src/view_ablation2.py`** and **`src/view_fidelity.py`** are two
  checks: sale timing, and national-layer fidelity.
- **`src/travel_tests.py`** is the proof that the method travels: named
  hillside and valley streets in each city, and the price premium for
  each view measure in each city.
- **`src/transfer_tests.py`** is the strict version: weights fitted in
  one city make a score for every home in the other, and the other
  city's prices and sale timing are tested against it, with and without
  stand-ins for the size of the home. `src/transfer_chart.py` draws it.
- **`src/scale_tests.py`** repeats the sunlight and view tests on every
  city that has been computed, pooled and with one city left out.
  **`src/on_top.py`** asks what the same measures add to the national
  model's own score. `src/scale_chart.py` draws both.
- **`src/light.py`** stands one metre outside each house's front and back
  walls at window height, traces the skyline, and counts the hours of
  direct sun on those windows through the year. Its `analyse` step tests
  the link to how often homes are sold, on all postcodes and on those
  where every house faces the same way.
- **`src/export_site_v4.py`** scores every owned home in both cities with
  the deployed national model and joins house-level views at the
  postcode. No address, postcode or coordinate of an individual home is
  exported.

## Every house in England and Wales (docs/08)

Everything the city runs did, done for every house in the country with
the same method, and a national model that can take any new signal.

```bash
# 15. National inputs (all open data): OS OpenMap Local for every 100 km square,
#     cut into 10 km cells; every house position from OS Open UPRN; the Wales
#     survey's tile list; a national 30 m terrain grid; the national landmark
#     list (Wikidata structures, Database of British and Irish Hills); and each
#     address's exact postcode and small-area codes from the ONS UPRN Directory.
python src/osmap_national.py data/ew_positions_raw.npz data/osmap/cells 4
python src/national_positions.py data/uprn/osopenuprn.zip data/geo_postcode.parquet data/ew_positions.parquet
python src/tiles.py wales-catalogue <wales_wfs.json> data/wales_lidar_tiles.parquet
python src/far_national.py data/cop30 data/far30
python src/build_landmarks.py data/landmarks/DoBIH_v18_6.csv data/geo_postcode.parquet data/landmarks/national_landmarks.parquet
python src/onsud_extract.py data/onsud/onsud.zip data/onsud/parts
python src/area_signals.py data/onsud/parts data/signals/area_postcode.parquet data/onsud/uprn_postcode.parquet

# 16. The compiled engine reproduces the city engine (run on any city cache):
python src/check_fastviews.py bath outputs/views2 400

# 17. Every house: resumable, 10 km cell by cell, survey tiles fetched ahead
#     and deleted behind. About 30 hours on 4 cores.
python src/national_views.py data/ew_positions.parquet data/landmarks/national_landmarks.parquet outputs/national 4

# 18. Exact postcodes, HOUSE signals by postcode, sector summaries, checks:
python src/national_tables.py outputs/national data/onsud/uprn_postcode.parquet data/signals/house_postcode.parquet
python src/national_checks.py outputs/national outputs/views2 data/panel3 outputs/national/checks.json

# 19. The training table, year-by-year features only (place signals attach by
#     postcode), then the national model with and without each family:
python src/panel2.py data/transactions.parquet data/panel3 20
python src/model_lab.py data/panel3 outputs/lab fitset 4 CURRENT BASE+HIST+GEO+VIEW 100
python src/assess_signal.py HOUSE
python src/assess_signal.py AREA
python src/model_lab.py data/panel3 outputs/lab fitset 4 +HOUSE+AREA BASE+HIST+GEO+VIEW+HOUSE+AREA 100
python src/model_lab.py data/panel3 outputs/lab fitset 4 NOVIEW30+HOUSE BASE+HIST+GEO+HOUSE 100
python src/local_eval.py data/panel3 outputs/lab

# 20. Find the best houses in the country, and draw them:
python src/find_best.py --all --top 20 --draw best.html
python src/find_best.py --want views water quiet_garden evening_sun --region "South West"
python src/find_best.py --want views --sees "Salisbury Cathedral"
python src/national_house_view.py <easting> <northing> one_house.html

# 21. The site for every postcode area: score every owned home, split the
#     national run by area, write one file per area plus the page's own data.
python src/model_lab.py data/panel3 outputs/lab deploy_set <NAME> <FAM+FAM> 100
python src/export_site_v5.py score data/transactions.parquet outputs/lab/model_deploy.txt outputs/lab/lab_deploy.json outputs/site5_cache
python src/export_site_v5.py houses outputs/national outputs/site5_cache
python src/export_site_v5.py export outputs/site5_cache data/geo_postcode.parquet outputs/national outputs/lab outputs/site5
python src/export_travel.py outputs/site5      # stations, place names, postcode positions, sectors' nearest stations
python ../web/build.py outputs/site5/site_data.json ../web/template_v5.html outputs/site5/index.html

# 22. Signals from dated events on a home (energy certificates), and the
#     measure that matters for homes not on the market. The token file is
#     kept outside the repository; no address field of a certificate is read.
EPC_TOKEN_FILE=<file> python src/epc_fetch.py fetch
python src/panel2.py data/transactions.parquet data/panel3 rowfam EPC
python src/assess_rowfam.py EPC                 # sellers in the calendar year
python src/late_sale.py EPC                     # the same gain, by the quarter the sale completed
python src/panel2.py data/transactions.parquet data/panel3 late
QM_LABEL=late python src/assess_late.py         # the whole model refitted on sales completing July to June
python src/listed_truth.py                      # which later sellers were already listed on the scoring day
python src/stack_late.py                        # the deployed model plus a second step, judged on homes not yet listed
python src/screen_facts.py                      # past intent and home facts from the certificates
python src/stack_late.py facts
python src/gazette_fetch.py data/gazette deceased days 12 2016
python src/gazette_test.py deceased             # do homes in a deceased-estate notice sell soon after?

# 23. Notices in The Gazette (bankruptcy orders, deceased estates) in the
#     ranking. The search listing gives 100 notices a request, so a year
#     takes about an hour at the site's 10-second crawl delay. No name is
#     kept; the notices rank homes and are never shown as a reason.
python src/gazette_list.py data/gazette_bankruptcy bankruptcy 2013 2014 2015 2016 2017 2018 2019
python src/gazette_list.py data/gazette deceased 2013 2014 2015 2016 2017 2018 2019
python src/notice_step.py first                 # the deployed model's figure for every home-year of 2017 and 2018 (once)
python src/notice_step.py features              # months since a notice at each home
python src/notice_step.py                       # the second step: fitted on 18 chunks, tested on the 2 test chunks
python src/notice_unseen.py                     # homes named in a notice with no sale on record: rates, and the model that scores them
python src/notice_fairness.py 2020              # where the notices fall, by deprivation and by the make-up of the postcode
python src/notice_timing.py                     # how soon after a notice a home is sold, month by month
python src/notice_later_year.py                 # the deployed ranking with notices against 2019, a year no part of it was fitted on
python src/notice_refresh.py                    # a test: what refreshing the scores on 1 July, with notices to 30 June, would add
python src/notice_monthly.py                    # a test: the same on the first of every month, and the average over the year
python src/notice_context.py                    # a test: would the notice step rank better with facts about the home
python src/gazette_list.py data/gazette_bankruptcy bankruptcy 2012   # only for the look-back test below
python src/notice_lookback.py                   # a test: a 60-month look-back for bankruptcy orders
python src/export_site_v5.py score data/transactions.parquet outputs/lab/model_deploy.txt outputs/lab/lab_deploy.json outputs/site5_cache outputs/lab/lab_second_notice.json
```

**Signals that begin after the training years.** The notices reach back to
2012, so the main model (fitted on 2001 to 2015) cannot be refitted with
them. `notice_step.py` keeps the model and fits a small second step that
reads only the notice columns and adds to the model's log-odds; a home with
no notice keeps its place. Because a notice touches a few homes in a
thousand, the step is judged on whether those homes are better scored (log
loss on homes and a year it was not fitted on) as well as on the best
tenth. Homes named in a notice with no sale since 1995 are outside the
model altogether. `notice_unseen.py` measures how often they sell and, where
that is clearly above a home on record, fits a small model of its own for
them: months since the notice, whether the address is a flat, and how the
postcode's homes are owned and how many have a sale on record. Care and
nursing homes are dropped first. The scorer adds each such home at that
model's figure when it is above the average home's.

**The live site.** The research table stops in December 2019; the site does
not. `live_sales.py` keeps a second table up to date from the Land Registry's
yearly files (reissued near the end of each month), `gazette_list.py --since
auto` adds the notices published since the last read, and
`export_site_v5.py live` scores every owned home on the first of the month
after the sale records end, with the notices read to today. `refresh.sh` runs
the three and writes the site's files; run it weekly.

```bash
bash refresh.sh                                 # notices to today, sales if reissued, every home scored, the site's files (about an hour)
python ../web/build.py outputs/site5/site_data.json ../web/template_v5.html outputs/site5/index.html
bash ../web/check_page.sh outputs/site5         # the page in a headless browser: a last line of [] is a clean run
python src/live_check.py                        # the checks behind it, on the up-to-date sale records
python src/notice_timing.py live 2025 2025      # how soon recent notices are followed by a sale
```

The model has only ever scored on a 1 January. `panel2.clock()` moves every
date on so that the scoring day falls on one, and each feature then reads the
twelve months before that day instead of a calendar year. Scored that way in
April, July and October the model ranks as well as in January (1.73, 1.75 and
1.73 against 1.73 in 2017), and the model fitted to 2018 still finds 1.73
times random on the sales of 2025 (`outputs/signals/LIVE_CHECK.md`). Scores
left at their January figure fall from 1.74 to 1.63 by December, and
the notices add 2.3 times as much read as they appear as read once a year
(`NOTICE_MONTHLY.md`); weekly is worth a little more than monthly, and costs a
dozen requests.

**What the score means.** The site's score is the chance that a sale
completes six to eighteen months after the scoring day. A home that completes
sooner was, with few exceptions, already on the market that day, and a buyer
can find it on a portal. The model is the later-sales fit with energy
certificates (`outputs/signals/LATE_MODEL.md`), which read a certificate
lodged for a marketed sale as a sign the home is already for sale. On the
2017 and 2018 test it finds 1.70 times random among later sellers against
1.66 for the model of sales in the next twelve months, and on the up-to-date
records it wins in six of the seven years from 2019 to 2025 (1.80 against
1.68 scored on 1 January 2025; 2021 is the exception). Homes owned for 20
years or more gain most: 1.63 against 1.33 in 2025. Only deceased-estate
notices are added to this model: bankruptcy orders make its ranking slightly
worse (`NOTICE_STEP_LATE.md`).

```bash
EPC_TOKEN_FILE=<file> python src/epc_fetch.py fetch       # certificates for every year (refresh: this year's again, monthly)
QM_LABEL=late python src/model_lab.py data/panel3 outputs/lab deploy_set 4 "+HOUSE+AREA+PD+EPC" "BASE+HIST+GEO+VIEW+HOUSE+AREA+PD+EPC" 100
python src/notice_step_late.py first                      # the later-sales model's figure for every home-year of 2017 and 2018 (once)
python src/notice_step_late.py                            # its notice step
QM_LABEL=late python src/notice_unseen.py                 # and its model for homes with no sale on record
python src/live_check.py late                             # the check on current sales: each 1 January from 2019
python src/live_check.py late lag                         # and one day with part of its last six months hidden
MODEL=year bash refresh.sh                                # the site on the model of sales in the next twelve months instead
```

The product fit and the certificate features need most of a 16 GB machine.
Run them one at a time; `MEMORY_CAP_GB=15 bash refresh.sh` makes a job that
outgrows the machine stop with an error instead of starving the rest.

A sale reaches the register weeks or months after it completes, so the last
six months of every file are part empty (the newest month holds about a
quarter of its sales). Left alone that costs the ranking 0.06, because every local and
national count reads as a falling market. `live_sales.registered()` judges
how much of each month is in, and the panel counts each of its sales for the
ones still to come (`late` weights), which wins back 0.05. What cannot be
won back: about one home in a hundred of the best tenth has just been sold
and the register does not yet say so.

**Judge a signal on homes not yet listed.** A home scored on 1 January that
completes a sale by June was almost certainly for sale already, so "sells
in the calendar year" rewards a signal for spotting listings. Energy
certificates show it: 1.74 to 2.06 times random on the calendar year, and
no gain (1.691 to 1.690) on later sellers that were not yet listed
(`outputs/signals/EPC.md`, `LATE_EPC.md`, `STACK_LATE.md`). A new signal
should be read on the second measure before anything is deployed.

**Adding a signal.** Write a table with one row per postcode, add an entry
to `FAMILIES` in `src/signals.py`, and run `python src/assess_signal.py
<NAME>`. It reports coverage; each column's link with sale timing like for
like, nationally and region by region; what is left once the current
model's score is allowed for; whether the model finds more sellers in the
best tenth of each district with the family added, with a range; and the
price premium. The training table never needs rebuilding: place signals
are looked up by postcode when a model is trained or scored.

- **`src/fastviews.py`** is the compiled engine. It walks each ray once
  for a whole batch of neighbouring houses and keeps only what the
  measures and drawings need; `check_fastviews.py` shows it gives the same
  answers as `views2.py`.
- **`src/national_views.py`** runs it for every house, 10 km cell by cell:
  house geometry, the upstairs view from the front and back walls, the
  garden and its sun, sun on the windows, landmark sight-lines and a
  drawing for every house (3 degree steps).
- **`src/tiles.py`** fetches and stores the 1 m surveys for England
  (Environment Agency) and Wales (Natural Resources Wales).
- **`src/signals.py`**, **`src/assess_signal.py`**: the register of signal
  families and the one-command test of what a family is worth.
- **`src/find_best.py`**, **`src/national_house_view.py`**: search every
  house in the country on any mix of characteristics and draw the result.
- **`src/export_site_v5.py`**, **`web/template_v5.html`**: the prototype for
  every postcode area. Each area is a file the page loads when chosen; the
  page carries every postcode sector's share of each outlook, so a brief
  can be matched against the whole country first. No address, postcode or
  position of an individual home is exported.
