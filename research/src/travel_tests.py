"""Does the method travel? Two tests that the views mean the same thing in a
second city as in the first.

1. Known places. Streets with a reputation for their outlook, and streets
   on the valley floor, in each city. If the method works, the first group
   should see further and see the city's landmark more often than the
   second, in Bath just as in Exeter. Streets are found by name in OS
   OpenMap Local and houses within 35 m of them are taken.

2. What a view is worth. If "long views" measures something real, homes
   that have them should sell for more, after allowing for the kind of home,
   the neighbourhood and the year, and they should do so in both cities.
   Each measure is tested on its own. Sale records join houses at the
   postcode, so each sale takes its postcode's average. Ranges come from
   re-sampling whole postcodes.

Usage: python travel_tests.py <transactions.parquet> <views2_dir>
"""
import glob
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

sys.path.insert(0, str(Path(__file__).parent))
from city_views import CITIES  # noqa: E402

STREETS = {
    "exeter": {"high": ["Barley Lane", "Pennsylvania Road", "Dunsford Road", "Rosebarn Lane", "Higher Kings Avenue"],
               "low": ["Okehampton Street", "Sidwell Street", "Clifton Road", "Cowick Street", "Alphington Road"]},
    "bath": {"high": ["Camden Crescent", "Lansdown Crescent", "Sion Hill", "Bathwick Hill", "Widcombe Hill"],
             "low": ["Lower Bristol Road", "Walcot Street", "Great Pulteney Street", "Livingstone Road", "Upper Bristol Road"]},
}
MAIN = {"exeter": "Exeter Cathedral", "bath": "Bath Abbey"}
MEASURES = [("m_u_long", "share of the horizon with a long view"), ("log_reach", "furthest sight-line"),
            ("m_u_hills", "hills on the skyline"), ("s_main", "the cathedral or the Abbey in sight"),
            ("s_has_water", "water in view"), ("m_sun_evening_jun", "evening sun in the garden"),
            ("m_g_overlooked", "how overlooked the garden is"), ("m_g_horizon", "how enclosed the garden is"),
            ("light_best", "sun on the sunnier side of the house")]


def known_places(city, views_dir):
    cfg = CITIES[city]
    h = pd.read_parquet(Path(views_dir) / f"houses_{city}.parquet")
    E0, E1, N0, N1 = cfg["grid"]
    base = glob.glob(f"{cfg['om']}/*/data/")[0]
    roads = gpd.read_file(f"{base}{cfg['sq']}_Road.shp", bbox=(E0, N0, E1, N1), engine="pyogrio")
    pts = shapely.points(h.e.to_numpy(), h.n.to_numpy())
    main = "sees_" + MAIN[city]
    rows = []
    for group, names in STREETS[city].items():
        for name in names:
            seg = roads[roads.DISTNAME.astype(str).str.lower() == name.lower()]
            if not len(seg):
                continue
            near = shapely.distance(pts, shapely.union_all(seg.geometry.values)) <= 35
            g = h[near]
            if len(g) < 8:
                continue
            w = g.n_uprn
            rows.append({"street": name, "group": group, "houses": int(len(g)),
                         "ground_m": round(float(g.ground.median())),
                         "reach_km": round(float(g.u_longest_km.median()), 1),
                         "long_views": round(float(np.average(g.has_long, weights=w)), 2),
                         "landmark": round(float(np.average(g[main], weights=w)), 2),
                         "any_landmark": round(float(np.average(g[[c for c in g.columns if c.startswith("sees_")]].any(axis=1), weights=w)), 2)})
    return rows


def price_test(tx_all, city, views_dir):
    cfg = CITIES[city]
    v = pd.read_parquet(Path(views_dir) / f"postcodes_{city}.parquet").set_index("postcode")
    lf = Path(views_dir) / f"light_{city}.parquet"
    if lf.exists():
        L = pd.read_parquet(lf)
        v = v.join(L.groupby("postcode").light_best.mean())
    v["log_reach"] = np.log(v.m_u_longest_km.clip(lower=0.05))
    v["s_main"] = v["s_sees_" + MAIN[city]]
    tx = tx_all[tx_all.outcode.astype(str).isin(cfg["outcodes"]) & tx_all.year.between(2010, 2019)].copy()
    tx["postcode"] = tx.postcode.astype(str)
    tx = tx.join(v[[m for m, _ in MEASURES if m in v.columns]], on="postcode", how="inner")
    part = tx.postcode.str.rsplit(" ", n=1)
    tx["sector"] = part.str[0] + " " + part.str[1].str[0]
    y = np.log(tx.price.to_numpy(dtype="float64"))
    D = pd.get_dummies(tx[["year", "ptype", "sector"]].astype(str), drop_first=True, dtype="float64")
    base = np.column_stack([np.ones(len(tx)), tx.is_new.to_numpy(dtype="float64"),
                            tx.leasehold.to_numpy(dtype="float64"), D.to_numpy()])
    blk = pd.factorize(tx.postcode)[0] % 400                       # blocks of whole postcodes
    order = np.argsort(blk, kind="stable"); cuts = np.searchsorted(blk[order], np.arange(401))
    rng = np.random.default_rng(2); W = rng.poisson(1.0, (200, 400)).astype("float64")
    out = {"sales": int(len(tx)), "postcodes": int(tx.postcode.nunique())}
    for m, label in MEASURES:
        if m not in tx.columns:
            continue
        x = tx[m].to_numpy(dtype="float64"); ok = np.isfinite(x)
        z = np.where(ok, (x - np.nanmean(x)) / np.nanstd(x), 0.0)
        X = np.column_stack([base, z])
        XtX = np.stack([X[order[cuts[i]:cuts[i + 1]]].T @ X[order[cuts[i]:cuts[i + 1]]] for i in range(400)])
        Xty = np.stack([X[order[cuts[i]:cuts[i + 1]]].T @ y[order[cuts[i]:cuts[i + 1]]] for i in range(400)])
        solve = lambda A, b: np.linalg.lstsq(A, b, rcond=None)[0][-1]
        beta = solve(XtX.sum(0), Xty.sum(0))
        bs = [solve(np.tensordot(w, XtX, 1), w @ Xty) for w in W]
        pct = lambda b: round(100 * (np.exp(b) - 1), 1)
        out[m] = {"label": label, "premium_pct_per_sd": pct(beta),
                  "range": [pct(np.percentile(bs, 2.5)), pct(np.percentile(bs, 97.5))]}
    return out


def main(tx_path, views_dir):
    res = {"known_places": {}, "price": {}}
    for city in CITIES:
        rows = known_places(city, views_dir)
        res["known_places"][city] = rows
        print(f"\n{CITIES[city]['name']}: streets known for their outlook against streets on low ground")
        print(f"  {'street':24s} {'group':5s} {'houses':>6s} {'ground':>7s} {'reach':>6s} {'long views':>10s} {MAIN[city]:>16s} {'any landmark':>12s}")
        for r in rows:
            print(f"  {r['street']:24s} {r['group']:5s} {r['houses']:6d} {r['ground_m']:6d}m {r['reach_km']:5.1f}km "
                  f"{r['long_views']*100:9.0f}% {r['landmark']*100:15.0f}% {r['any_landmark']*100:11.0f}%")
        for grp in ("high", "low"):
            g = [r for r in rows if r["group"] == grp]
            if g:
                n = sum(r["houses"] for r in g)
                print(f"  {grp:5s} overall: reach {np.average([r['reach_km'] for r in g], weights=[r['houses'] for r in g]):.1f} km, "
                      f"long views {100*np.average([r['long_views'] for r in g], weights=[r['houses'] for r in g]):.0f}%, "
                      f"landmark {100*np.average([r['landmark'] for r in g], weights=[r['houses'] for r in g]):.0f}%  ({n} houses)")
    tx = pd.read_parquet(tx_path, columns=["year", "price", "ptype", "is_new", "leasehold", "postcode", "outcode"])
    for city in CITIES:
        res["price"][city] = price_test(tx, city, views_dir)
    print("\nPrice premium for one standard deviation more of each measure, like for like (95% range)")
    print(f"  {'measure':44s} {'Exeter':>24s} {'Bath':>24s}")
    for m, label in MEASURES:
        cells = []
        for city in CITIES:
            r = res["price"][city].get(m)
            cells.append(f"{r['premium_pct_per_sd']:+5.1f}% ({r['range'][0]:+.1f} to {r['range'][1]:+.1f})" if r else "n/a")
        print(f"  {label:44s} {cells[0]:>24s} {cells[1]:>24s}")
    print("  sales:", {c: res["price"][c]["sales"] for c in CITIES})
    json.dump(res, open(Path(views_dir) / "travel_tests.json", "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:3])
