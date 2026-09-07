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
