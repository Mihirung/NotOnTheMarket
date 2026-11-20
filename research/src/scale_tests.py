"""More places: do the house-level measures hold up beyond two cities?

The sunlight, garden and outlook measures need the 1 metre laser survey,
so they exist only for the cities that have been run through
city_views.py and light.py. Two cities left wide ranges. This repeats
the tests on every city available and asks two things. A third, whether
the measures add anything to the national model, is in on_top.py.

1. Sunlight and how often homes are sold. The change in the yearly
   chance of a sale for one more hour of direct sun on the windows (or
   one typical step of a view measure), holding the kind of home, its
   price, the length of ownership and the year fixed. Shown for each
   city, for the first two cities pooled, and for all cities pooled, so
   the effect of more data on the range is visible.

2. Does it carry to a city it has not seen? A score is built from all
   cities but one and tested on the one left out, for sale timing and
   for price. A slope of 1 means it carries in full, 0 not at all.

Ranges re-sample whole properties (timing) or whole postcodes (price).
Sale records join houses at the postcode.

Usage: python scale_tests.py <transactions.parquet> <views2_dir>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from city_views import CITIES as ALL_CITIES  # noqa: E402
from light import CTRL, postcode_table  # noqa: E402
from propensity_model import build_panel, district_year_features, featurise  # noqa: E402
from transfer_tests import NB, SIZE, Design  # noqa: E402

OUTLOOK = ["m_u_long", "log_reach", "m_u_hills", "s_has_water"]
GARDEN = ["m_g_overlooked", "m_g_horizon", "m_sun_evening_jun", "m_sun_equinox"]
LIGHT = ["light_front", "light_back"]
SETS = {"outlook": OUTLOOK, "garden_light": GARDEN + LIGHT, "all": OUTLOOK + GARDEN + LIGHT}
SINGLE = [("light_both", "sun on front and back windows together", "hour"),
          ("light_front", "sun on the front windows", "hour"),
          ("light_back", "sun on the back windows", "hour"),
          ("winter_front", "sun on the front windows at midwinter", "hour"),
          ("winter_back", "sun on the back windows at midwinter", "hour"),
          ("m_sun_evening_jun", "evening sun in the garden", "hour"),
          ("m_g_overlooked", "how overlooked the garden is", "step"),
          ("m_u_long", "share of the horizon with a long view", "step")]
COLS = SETS["all"] + [c for c, _, _ in SINGLE if c not in SETS["all"]]
IDX = {c: i for i, c in enumerate(COLS)}
BOOT = 300
FIRST_TWO = ("exeter", "bath")


def view_table(city, views_dir):
    vd = Path(views_dir)
    v = pd.read_parquet(vd / f"postcodes_{city}.parquet").set_index("postcode")
    v = v.join(postcode_table(pd.read_parquet(vd / f"light_{city}.parquet")).drop(columns=["n_houses", "one_sided"]))
    v["log_reach"] = np.log(v.m_u_longest_km.clip(lower=0.05))
    h = pd.read_parquet(vd / f"houses_{city}.parquet",
                        columns=["postcode", "storeys", "depth_m", "n_uprn", "plot_open", "has_garden"])
    h["log_addr"] = np.log(h.n_uprn.clip(lower=1)); h["has_garden"] = h.has_garden.astype(float)
    return v[COLS].join(h.groupby("postcode")[SIZE].mean())


def timing_panel(tx_all, city, V):
    tx = tx_all[tx_all.outcode.astype(str).isin(ALL_CITIES[city]["outcodes"])].copy()
    for c in ("postcode", "outcode", "ptype"):
        tx[c] = tx[c].astype(str).astype("category")
    tx = tx.sort_values(["key", "year", "month"], ignore_index=True)
    panel = featurise(build_panel(tx, district_year_features(tx), 100))
    v = V.reindex(pd.Index(tx["postcode"].cat.categories))
    code = panel["pc_code"].to_numpy(); ok = code >= 0
    seen = np.zeros(len(panel), bool); seen[ok] = v[COLS[0]].notna().to_numpy()[code[ok]]
    for c in COLS:
        col = np.zeros(len(panel)); col[ok] = np.nan_to_num(v[c].to_numpy()[code[ok]]); panel[c] = col
    panel = panel[seen].copy()
    return panel


def timing_design(panel):
    C = panel[CTRL].astype("float64"); C = C.fillna(C.median()); C["tenure_sq"] = C["tenure"] ** 2
    C = (C - C.mean()) / C.std().replace(0, 1)
    yr = pd.get_dummies(panel["year"].astype(int), drop_first=True, dtype="float64")
    base = np.column_stack([np.ones(len(panel)), C.to_numpy(), yr.to_numpy()])
    blk = ((np.abs(panel["key"].to_numpy()) // 7) % NB).astype(int)
    return Design(base, panel[COLS].to_numpy(dtype="float64"), panel["label"].to_numpy(), blk)


def price_design(tx_all, city, V):
    tx = tx_all[tx_all.outcode.astype(str).isin(ALL_CITIES[city]["outcodes"]) & tx_all.year.between(2010, 2019)].copy()
    tx["postcode"] = tx.postcode.astype(str)
    tx = tx[tx.postcode.isin(V.index)]
    part = tx.postcode.str.rsplit(" ", n=1)
    tx["sector"] = part.str[0] + " " + part.str[1].str[0]
    D = pd.get_dummies(tx[["year", "ptype", "sector"]].astype(str), drop_first=True, dtype="float64")
    rows = V.reindex(tx.postcode)
    base = np.column_stack([np.ones(len(tx)), tx.is_new.to_numpy(dtype="float64"),
                            tx.leasehold.to_numpy(dtype="float64"), D.to_numpy(), rows[SIZE].to_numpy()])
    blk = pd.factorize(tx.postcode)[0] % NB
    return Design(base, rows[COLS].to_numpy(), np.log(tx.price.to_numpy(dtype="float64")), blk), len(tx)


def pooled(D, cities, W, cols):
    """Weights on the measures from several cities at once, each city keeping
    its own controls."""
    SVV = SVy = 0
    for c in cities:
        a, b = D[c].partial(W[c], cols); SVV = SVV + a; SVy = SVy + b
    return np.linalg.lstsq(SVV, SVy, rcond=None)[0]


def draws(cities, rng):
    return [{c: rng.poisson(1.0, NB).astype("float64") for c in cities} for _ in range(BOOT)]


def rng_ci(vals):
    return [round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3)]


def per_unit(D, cities, groups, sd, scale, boots):
    """One measure at a time: the change in the outcome for one more unit, for
    each city and for each pooled group of cities."""
    one = {c: np.ones(NB) for c in cities}
    out = {}
    for col, label, unit in SINGLE:
        j = [IDX[col]]; k = scale / (sd[col] if unit == "hour" else 1.0)
        row = {"label": label, "unit": unit}
        for name, grp in groups.items():
            est = k * float(pooled(D, grp, one, j)[0])
            bs = [k * float(pooled(D, grp, w, j)[0]) for w in boots]
            row[name] = {"est": round(est, 3), "range": rng_ci(bs)}
        out[col] = row
    return out


def loco(D, cities, sets, boots):
    one = {c: np.ones(NB) for c in cities}
    out = {}
    for held in cities:
        rest = [c for c in cities if c != held]
        for name, cols in sets.items():
            j = [IDX[c] for c in cols]
            b = pooled(D, rest, one, j)
            g, ssr_base, ssr_idx, ssr_own = D[held].slope(one[held], j, b)
            bs = [D[held].slope(w[held], j, pooled(D, rest, w, j))[0] for w in boots]
            out[f"{held}_{name}"] = {"slope": round(float(g), 2), "range": [round(x, 2) for x in rng_ci(bs)],
                                     "share_of_own_fit": round(float((ssr_base - ssr_idx) / max(ssr_base - ssr_own, 1e-12)), 2)}
    return out


def show_units(res, groups, what):
    print(f"  {'one more...':46s} " + " ".join(f"{g:>26s}" for g in groups))
    for col, row in res.items():
        cells = " ".join(f"{row[g]['est']:+8.3f} ({row[g]['range'][0]:+.3f} to {row[g]['range'][1]:+.3f})" for g in groups)
        print(f"  {row['unit'] + ' of ' + row['label']:46s} {cells}", flush=True)


def main(tx_path, views_dir):
    cities = [c for c in ALL_CITIES if (Path(views_dir) / f"light_{c}.parquet").exists()
              and (Path(views_dir) / f"postcodes_{c}.parquet").exists()]
    names = {c: ALL_CITIES[c]["name"] for c in cities}
    print("cities:", ", ".join(names.values()), flush=True)
    tx = pd.read_parquet(tx_path)
    V = {c: view_table(c, views_dir) for c in cities}
    both = pd.concat(V.values()); mu, sd = both.mean(), both.std()
    V = {c: ((v - mu) / sd)[v[COLS[0]].notna()].fillna(0.0) for c, v in V.items()}   # one scale for every city
    rng = np.random.default_rng(23); boots = draws(cities, rng)
    groups = {names[c]: [c] for c in cities}
    if all(c in cities for c in FIRST_TWO) and len(cities) > 2:
        groups["First two pooled"] = list(FIRST_TWO)
    groups[f"All {len(cities)} pooled"] = cities
    res = {"cities": names, "houses": {c: int(len(pd.read_parquet(Path(views_dir) / f'houses_{c}.parquet', columns=['postcode']))) for c in cities}}

    panels = {c: timing_panel(tx, c, V[c]) for c in cities}
    T = {c: timing_design(panels[c]) for c in cities}
    res["timing"] = {"home_years": {c: int(len(panels[c])) for c in cities}, "sales": {c: int(panels[c].label.sum()) for c in cities}}
    print("\nSALE TIMING. Change in the yearly chance of a sale, in percentage points, like for like (95% range)")
    print("  home-years:", res["timing"]["home_years"], " sales:", res["timing"]["sales"])
    res["timing"]["per_unit"] = per_unit(T, cities, groups, sd, 100.0, boots)
    show_units(res["timing"]["per_unit"], groups, "points")
    if len(cities) > 2:
        print("\nSALE TIMING. Score built from every city but one, tested on the one left out (1 = carries in full)")
        res["timing"]["left_out"] = loco(T, cities, SETS, boots)
        for k, r in res["timing"]["left_out"].items():
            print(f"  {k:26s} {r['slope']:+6.2f} ({r['range'][0]:+.2f} to {r['range'][1]:+.2f})   share of own fit {100*r['share_of_own_fit']:.0f}%", flush=True)

    P = {}; res["price"] = {"sales": {}}
    for c in cities:
        P[c], n = price_design(tx, c, V[c]); res["price"]["sales"][c] = int(n)
    print("\nPRICE. Per cent more paid, like for like and holding stand-ins for size fixed (95% range)")
    print("  sales 2010 to 2019:", res["price"]["sales"])
    res["price"]["per_unit"] = per_unit(P, cities, groups, sd, 100.0, boots)
    show_units(res["price"]["per_unit"], groups, "per cent")
    if len(cities) > 2:
        print("\nPRICE. Score built from every city but one, tested on the one left out (1 = carries in full)")
        res["price"]["left_out"] = loco(P, cities, SETS, boots)
        for k, r in res["price"]["left_out"].items():
            print(f"  {k:26s} {r['slope']:+6.2f} ({r['range'][0]:+.2f} to {r['range'][1]:+.2f})   share of own fit {100*r['share_of_own_fit']:.0f}%", flush=True)

    json.dump(res, open(Path(views_dir) / "scale_tests.json", "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:3])
