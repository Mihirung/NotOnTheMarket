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
    "AMENITY": dict(table="research/data/signals/amenity_postcode.parquet",
                    columns=["km_pub", "pubs_1km", "takeaways_1km", "restaurants_1km", "km_park", "park_ha_1km",
                             "km_play", "km_wood", "km_water", "km_sea", "km_blue"],
                    about="Green and blue space (OS Open Greenspace, OS OpenMap Local) and pubs, takeaways and "
                          "restaurants (Food Standards Agency hygiene register), by distance from the postcode centre"),
    "PD": dict(table="research/data/signals/pd_postcode.parquet",
               columns=["pd_rear_share", "pd_rear_prior_m", "pd_loft_share", "pd_two_storey_share", "pd_side_share",
                        "pd_heritage_share", "pd_add_m2", "pd_add_pct", "price_m2", "flat_share", "listed_share"],
               about="What the houses of the postcode could add without planning permission (permitted development, "
                     "planning constraints from planning.data.gov.uk and DataMapWales), and their price per m2"),
    "CLIMATE": dict(table="research/data/signals/climate_postcode.parquet",
                    columns=["temp_year", "temp_summer", "temp_winter", "temp_range", "warmest_days", "coldest_nights",
                             "rain_year", "rain_summer", "rain_winter", "heavy_rain_days", "frost_days", "icing_days",
                             "summer_days", "sun_hours_year", "sun_hours_summer", "sun_hours_winter", "cloud_year",
                             "cloud_winter", "solar_year", "wind", "warming_so_far", "warming_2c", "summer_heat_2c",
                             "winter_nights_2c", "summer_rain_so_far", "summer_rain_2c", "winter_rain_so_far",
                             "winter_rain_2c", "hot_days_now", "hot_days_2c", "frost_days_lost_2c"],
                    about="Climate now and how it is changing: Met Office HadUK-Grid 1991-2020 (2 km and 12 km), "
                          "UKCP18 projections at 2 C of global warming (12 km), CHELSA cloud, solar energy and wind, "
                          "sunshine hours calibrated on Met Office stations (climate_signals.py)"),
    "PEOPLE": dict(table="research/data/signals/people_postcode.parquet",
                   columns=["children", "age_20_29", "age_30_44", "age_45_59", "age_60_64", "age_65_74", "age_75_84",
                            "age_85_plus", "median_age", "hh_alone_65", "hh_alone_under_65", "hh_couple_65",
                            "hh_couple_no_children", "hh_young_children", "hh_grown_children", "hh_lone_parent",
                            "hh_students", "own_outright", "own_mortgage", "social_rent", "private_rent",
                            "spare_2_bedrooms", "overcrowded", "retired", "self_employed", "unemployed", "students",
                            "hh_size", "rooms", "bedrooms", "no_central_heating", "no_car", "cars_per_household"],
                   about="Who lives around the postcode: life stage, household type, tenure, spare bedrooms, work "
                         "and cars, from the 2011 Census output area (people_signals.py). No ethnicity, religion, "
                         "marital status or health"),
    "SCHOOLS": dict(table="research/data/signals/schools_postcode.parquet",
                    columns=["km_primary_good", "km_primary_outstanding", "km_secondary_good",
                             "km_secondary_outstanding", "good_primaries_2km", "km_primary", "km_secondary",
                             "km_grammar", "km_independent"],
                    about="Schools nearby: Ofsted grades as at August 2016, selective and independent schools "
                          "(schools_access_signals.py)"),
    "ACCESS": dict(table="research/data/signals/access_postcode.parquet",
                   columns=["km_rail", "km_metro", "bus_stops_500m", "km_motorway", "km_a_road"],
                   about="Transport: railway stations, underground, metro and tram stops, bus stops (NaPTAN), "
                         "motorways and A roads (OS OpenMap Local) (schools_access_signals.py)"),
    "STOCK": dict(table="research/data/signals/stock_postcode.parquet",
                  columns=["built_pre1919", "built_1919_44", "built_1945_64", "built_1965_82", "built_1983_99",
                           "built_2000_09", "built_2010_16", "one_period", "band_ab", "band_fgh", "bungalows",
                           "flats", "terraced", "semis", "detached", "beds_1_2", "beds_4_plus"],
                  about="The homes around the postcode in 2016: when built, type, bedrooms and council tax bands "
                        "(Valuation Office Agency, stock_signals.py)"),
    "AREA15": dict(table="research/data/signals/area15_postcode.parquet",
                   columns=["imd_score_15", "income_15", "employment_15", "education_15", "health_15", "crime_15",
                            "barriers_15", "living_env_15", "idaci_15", "idaopi_15", "rural"],
                   about="The area family rebuilt from before the test years and without the census area "
                         "classification: English Indices of Deprivation 2015 and its domains, and rurality "
                         "(area15_signals.py)"),
    "LIFE": dict(table="research/data/signals/life_postcode.parquet",
                 inputs=["ab_20_24", "ab_25_29", "ab_30_44", "ab_45_59", "ab_60_64", "ab_65_74", "ab_75_84", "ab_85_89",
                         "ab_90_plus", "alone_65", "couple_65", "le65", "health_dep", "older_income_dep"],
                 columns=["owner_age", "p_owner_75", "p_owner_85", "p_exit", "p_exit_alone", "le65", "health_dep",
                          "older_income_dep", "alone_share"],
                 rowwise="life_rows",
                 about="Later life: the owner's likely age from years owned and the 2011 age mix of the output area, "
                       "and the yearly chance of a death or move into care at that age, moved by local life "
                       "expectancy (life_signals.py). For the model's ranking only; never shown"),
    "CRIME": dict(table="research/data/signals/crime_postcode.parquet",
                  columns=["crime_all", "burglary", "antisocial", "violence", "vehicle", "damage", "drugs", "theft"],
                  about="Recorded crime and anti-social behaviour per 1,000 residents a year, February 2014 to "
                        "January 2017 (data.police.uk, crime_signals.py)"),
}


def derive_geo(t):
    oc = t.postcode.str.split(" ").str[0]
    t["aq_rel_region"] = t["nox"] - t.groupby(oc)["nox"].transform("median")
    return t


def available(families=None):
    """Registered place families whose table exists."""
    return [f for f in (families or FAMILIES) if (ROOT / FAMILIES[f]["table"]).exists()]


# ---------------------------------------------------------------- families worked out home by home
# A family with `rowwise` keeps per-postcode `inputs` in its table; its `columns` are worked out for each
# home-year from those inputs and the home's years of ownership (model_lab.View.take, panel2.full_features).
LIFE_BANDS = np.array([(20, 25), (25, 30), (30, 45), (45, 60), (60, 65), (65, 75), (75, 85), (85, 90), (90, 100)])
GOMPERTZ = (-11.34, 0.105)        # ln(yearly chance of death) = A + B * age, through the 2014-16 England and Wales life tables
LE65_EW = 19.85                   # life expectancy at 65, England and Wales 2014-16, men and women averaged
CARE_SHARE = 0.5                  # moves into care, as a share of deaths at the same age
MIN_BUY_AGE = 25


def life_rows(M, tenure):
    """LIFE columns for each home-year: M holds the postcode inputs, tenure the years owned."""
    M = np.asarray(M, np.float32); ten = np.asarray(tenure, np.float32)
    ages = np.arange(20, 100, dtype=np.float32)
    band = np.searchsorted(LIFE_BANDS[:, 1], ages, side="right")             # band of each single year of age
    width = (LIFE_BANDS[:, 1] - LIFE_BANDS[:, 0]).astype(np.float32)
    dens = M[:, band] / width[band]                                          # (n, 80): share per year of age
    lo = np.clip(ten + MIN_BUY_AGE, 20, 95)
    w = np.where(ages[None, :] >= lo[:, None], dens, 0.0)
    tot = w.sum(axis=1)
    tot = np.where(tot > 0, tot, np.nan)
    alone, couple, le, hd, inc = M[:, 9], M[:, 10], M[:, 11], M[:, 12], M[:, 13]
    A, B = GOMPERTZ
    shift = np.exp(-B * np.nan_to_num(le - LE65_EW))                        # longer local lives, lower yearly risk
    hz = np.minimum((1 + CARE_SHARE) * np.exp(A + B * ages)[None, :] * shift[:, None], 1.0)
    owner_age = (w * ages).sum(axis=1) / tot
    p75 = (w * (ages >= 75)).sum(axis=1) / tot
    p85 = (w * (ages >= 85)).sum(axis=1) / tot
    p_exit = (w * hz).sum(axis=1) / tot
    alone_share = alone / np.where(alone + couple > 0, alone + couple, np.nan)
    return np.column_stack([owner_age, p75, p85, p_exit, p_exit * alone_share, le, hd, inc, alone_share]).astype(np.float32)


def rowwise(family, M, tenure):
    return globals()[FAMILIES[family]["rowwise"]](M, tenure)


def lookup(family, postcodes):
    """(n_postcodes, n_columns) float32 matrix of a family's signals, rows in the order of `postcodes`.
    For a family worked out home by home, its inputs."""
    spec = FAMILIES[family]
    t = pd.read_parquet(ROOT / spec["table"])
    if spec.get("derive"):
        t = globals()[spec["derive"]](t)
    t = t.drop_duplicates("postcode").set_index("postcode").reindex(pd.Index(postcodes))
    m = np.array(t[spec.get("inputs", spec["columns"])].to_numpy(dtype="float32"), copy=True)
    m[~np.isfinite(m)] = np.nan
    return m


def columns(families):
    out = []
    for f in families:
        out += TIME_VARYING[f] if f in TIME_VARYING else FAMILIES[f]["columns"]
    return out
