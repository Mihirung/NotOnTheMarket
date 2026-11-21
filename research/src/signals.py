"""The register of signals the national model can use.

There are two kinds.

  Time-varying signals change from year to year for the same home: how
  long it has been owned, local sale rates, the market cycle. They are
  computed in panel2.py and stored row by row in the training table.

  Place signals belong to a postcode and do not change: air quality,
  the view, sunlight on the windows, deprivation. Each family is one
  table with one row per postcode, registered below. The training table
  stores only each row's postcode, and place signals are looked up when
  a model is trained or scored.

So a new signal needs no rebuild. Write a table keyed by postcode,
register it here, and run:

    python assess_signal.py <FAMILY>

which measures what it adds (see assess_signal.py). Nothing else changes.

A family entry:
  table       parquet file with a 'postcode' column ('AB1 2CD' format)
  columns     the signal columns to use, in order
  about       one line on what it is and where it comes from
  derive      optional: name of a function in this module that adds
              derived columns to the table before use
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]          # the repository; table paths below are relative to it

TIME_VARYING = {
    "BASE": ["tenure", "log_price_rel", "leasehold", "is_new", "n_prior", "turnover_3y",
             "price_rel_nat", "price_growth_3y", "pc_sales_2y", "ptype_D", "ptype_S", "ptype_T", "ptype_F"],
    "HIST": ["equity_gain", "gain_ann", "prev_gap", "mean_prev_gap", "prev_ann_ret", "price_pct",
             "ls_band", "pc_sales_1y", "pc_sales_5y", "pc_stock", "pc_rate_5y", "pc_age",
             "pc_new_share", "sec_rate_5y", "sec_rate_1y", "sec_accel", "sec_price_rel",
             "sec_gentrify", "dist_rate_1y", "dist_yoy", "dist_new_share_2y",
             "nat_yoy", "nat_vol_rel5", "nat_price_g1", "buy_price_g1"],
}

HOUSE_COLS = [
    # the view from the upper windows, front and back together
    "u_horizon", "u_open", "u_long", "u_long5", "u_longest_km", "u_water", "u_tidal", "u_hills", "u_overlooked",
    "u_hz_s", "u_hz_w",
    # the garden
    "g_horizon", "g_long", "g_overlooked", "g_hz_s", "g_hz_w", "sun_jun", "sun_evening_jun", "sun_equinox", "sun_dec",
    "garden", "garden_clear", "plot_open",
    # sun on the windows
    "light_front", "light_back", "light_best", "light_both", "winter_front", "winter_back", "top_front", "top_back",
    # the house
    "storeys", "height", "depth_m", "road_m",
    # landmarks in sight from the upper windows
    "lm_n", "lm_cathedral", "lm_castle", "lm_tower", "lm_church", "lm_hill",
    # how much the houses on the postcode differ (one-sided streets, mixed outlooks)
    "sd_u_long", "sd_light_both",
]

FAMILIES = {
    "GEO": dict(table="research/data/geo_postcode.parquet",
                columns=["nox", "pm10", "so2", "km_gp", "km_hospital", "km_dentist", "km_pharmacy",
                         "pc_within_1km", "pc_within_5km", "km_town", "km_regional", "km_major", "aq_rel_region"],
                about="Access to Healthy Assets and Hazards (air quality, distance to services) and settlement distances",
                derive="derive_geo"),
    "VIEW": dict(table="research/data/view30_postcode.parquet",
                 columns=["v30_elev", "v30_horizon", "v30_hz_s", "v30_hz_w", "v30_hz_e", "v30_hz_n",
                          "v30_long2", "v30_long5", "v30_long10", "v30_longest_km", "v30_logreach",
                          "v30_sea", "v30_water", "v30_water_near", "v30_hills", "v30_skyview",
                          "v30_rough", "v30_tpi1k", "v30_slope", "v30_south", "v30_west", "v30_km_coast"],
                 about="The outlook from each postcode centre on 30 m terrain (no buildings or trees)"),
    "HOUSE": dict(table="research/data/signals/house_postcode.parquet",
                  columns=HOUSE_COLS,
                  about="House by house from the 1 m laser survey, averaged over the postcode's addresses: the upstairs "
                        "view, the garden and its sun, sun on the windows, the house's size, landmarks in sight"),
    "AREA": dict(table="research/data/signals/area_postcode.parquet",
                 columns=["imd_rank", "rural", "oac_1", "oac_2", "oac_3", "oac_4", "oac_5", "oac_6", "oac_7", "oac_8"],
                 about="From the ONS UPRN Directory: deprivation rank (IMD 2025), rural or urban, and the census "
                       "output-area classification (2021), as the share of the postcode's addresses in each group"),
}


def derive_geo(t):
    oc = t.postcode.str.split(" ").str[0]
    t["aq_rel_region"] = t["nox"] - t.groupby(oc)["nox"].transform("median")
    return t


def available(families=None):
    """Registered place families whose table exists."""
    return [f for f in (families or FAMILIES) if (ROOT / FAMILIES[f]["table"]).exists()]


def lookup(family, postcodes):
    """(n_postcodes, n_columns) float32 matrix of a family's signals, rows in the order of `postcodes`."""
    spec = FAMILIES[family]
    t = pd.read_parquet(ROOT / spec["table"])
    if spec.get("derive"):
        t = globals()[spec["derive"]](t)
    t = t.drop_duplicates("postcode").set_index("postcode").reindex(pd.Index(postcodes))
    m = np.array(t[spec["columns"]].to_numpy(dtype="float32"), copy=True)
    m[~np.isfinite(m)] = np.nan
    return m


def columns(families):
    out = []
    for f in families:
        out += TIME_VARYING[f] if f in TIME_VARYING else FAMILIES[f]["columns"]
    return out
