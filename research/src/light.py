"""Is a light home a home people stay in?

For every house in a city this works out how many hours of direct sun
fall on its windows, front and back, downstairs and at the top floor,
through the year, allowing for every roof, tree and hill in the way.
Then it asks whether homes with more sun on their windows are sold less
often.

How the sun on a window is worked out. The front of a house faces the
nearest road; the back is the opposite side. From the address point we
walk out through the house in each direction until we leave its
footprint, and stand one metre outside that wall, once at ground-floor
window height and once at top-floor height. From each of those four
spots the skyline is traced all the way round. On three days
(midsummer, the equinox, midwinter) the sun is followed every ten
minutes: the window is in direct sun when the sun is above the skyline
and within 75 degrees of square-on to the wall. The yearly figure
averages the three days, counting the equinox twice.

The sale-rate test joins houses to sale records at the postcode, so it
is run twice: on every postcode, and on "one-sided" postcodes where
every house faces the same way, where a postcode average is a fair
description of each house.

Usage:
  python light.py compute <exeter|bath> <views2_dir> [workers]
  python light.py analyse <transactions.parquet> <views2_dir>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import views2 as V  # noqa: E402
import city_views as CV  # noqa: E402
from city_views import CITIES, facade_points, front_bearing  # noqa: E402
from propensity_model import build_panel, district_year_features, featurise  # noqa: E402

DAYS = (("jun", 172, 1), ("equinox", 80, 2), ("dec", 355, 1))
MEASURES = ["light_front", "light_back", "light_best", "light_both", "winter_front", "winter_back",
            "summer_evening_back", "top_front", "top_back"]
LABEL = {"light_front": "downstairs front windows, yearly average", "light_back": "downstairs back windows, yearly average",
         "light_best": "the sunnier side downstairs", "light_both": "front and back downstairs together",
         "winter_front": "downstairs front at midwinter", "winter_back": "downstairs back at midwinter",
         "summer_evening_back": "downstairs back, midsummer after 5pm",
         "top_front": "top-floor front windows, yearly average", "top_back": "top-floor back windows, yearly average"}
CTRL = ["tenure", "log_price_rel", "leasehold", "is_new", "n_prior", "turnover_3y", "price_rel_nat",
        "ptype_D", "ptype_S", "ptype_T", "ptype_F"]


def facade_sun(hz, normal, lat):
    """Hours of direct sun on a wall facing `normal`, per viewpoint, per day."""
    R = hz.shape[1]; step = 360.0 / R
    out = {}
    for name, doy, _ in DAYS:
        t, az, el = V.sun_path(lat, doy, 10)
        idx = np.round(az / step).astype(int) % R
        lit = (el[None, :] > 1.0) & (el[None, :] > hz[:, idx])
        lit &= np.abs(((az[None, :] - normal[:, None] + 180) % 360) - 180) < 75
        out[name] = lit.sum(1) / 6.0
        if name == "jun":
            out["evening_jun"] = (lit & (t[None, :] >= 16.0)).sum(1) / 6.0
    out["year"] = sum(w * out[n] for n, _, w in DAYS) / sum(w for *_, w in DAYS)
    return out


def _cast(batch):
    e, n, z = batch
    o, _ = V.cast(CV.CITY, e, n, z, False, step_deg=3.0)
    return o["hz_deg"].astype("float16")


def compute(city, views_dir, workers=2):
    """Trace the skyline from each house's front and back windows and count the sun."""
    from multiprocessing import Pool
    cfg = CITIES[city]
    CV.CITY, bld, _ = CV.load_city(cfg, f"research/data/terrain/cache_{city}")
    h = pd.read_parquet(Path(views_dir) / f"houses_{city}.parquet")
    front, road_m = front_bearing(h, cfg)
    pts = facade_points(h, front, bld, CV.CITY)
    out = pd.DataFrame({"postcode": h.postcode.to_numpy(), "sector": h.sector.to_numpy(), "n_uprn": h.n_uprn.to_numpy(),
                        "front_bearing": np.round(front, 0), "road_m": np.round(road_m, 1),
                        "depth_m": np.round(pts["front"][3] + pts["back"][3] - 2, 0)})
    eye_top = h.eye_up.to_numpy()
    B = 80
    for side, normal in (("front", front), ("back", (front + 180) % 360)):
        fe, fn, fg, _ = pts[side]
        for floor, z in (("down", fg + 1.6), ("top", np.maximum(eye_top, fg + 1.6))):
            jobs = [(fe[i:i + B], fn[i:i + B], z[i:i + B]) for i in range(0, len(h), B)]
            with Pool(int(workers)) as pool:
                hz = np.concatenate(list(pool.imap(_cast, jobs, chunksize=4))).astype("float32")
            s = facade_sun(hz, normal, cfg["centre"][0])
            for k, v in s.items():
                out[f"{floor}_{side}_{k}"] = np.round(v, 2)
            print(f"  {city} {side} {floor}: median {np.median(s['year']):.1f} h a day", flush=True)
    out["light_front"], out["light_back"] = out.down_front_year, out.down_back_year
    out["top_front"], out["top_back"] = out.top_front_year, out.top_back_year
    out["winter_front"], out["winter_back"] = out.down_front_dec, out.down_back_dec
    out["summer_evening_back"] = out.down_back_evening_jun
    out["light_best"] = out[["light_front", "light_back"]].max(axis=1)
    out["light_both"] = out.light_front + out.light_back
    out.to_parquet(Path(views_dir) / f"light_{city}.parquet", index=False)
    print(f"{cfg['name']}: {len(out):,} houses; sunnier side downstairs, yearly average: "
          f"{out.light_best.quantile([.1, .5, .9]).round(1).tolist()} h a day (10th, 50th, 90th percentile)")


def postcode_table(L):
    rad = np.radians(L.front_bearing)
    g = L.assign(cx=np.cos(rad), sx=np.sin(rad)).groupby("postcode")
    t = g[MEASURES].mean()
    t["n_houses"] = g.size()
    t["one_sided"] = (np.hypot(g.cx.mean(), g.sx.mean()) >= 0.9) & (t.n_houses >= 4)
    return t


def city_panel(tx_all, city, pct):
    tx = tx_all[tx_all["outcode"].astype(str).isin(CITIES[city]["outcodes"])].copy()
    for c in ("postcode", "outcode", "ptype"):
        tx[c] = tx[c].astype(str).astype("category")
    tx = tx.sort_values(["key", "year", "month"], ignore_index=True)
    panel = featurise(build_panel(tx, district_year_features(tx), 100))
    v = pct.reindex(pd.Index(tx["postcode"].cat.categories))
    code = panel["pc_code"].to_numpy(); ok = code >= 0
    for c in MEASURES + ["one_sided"]:
        vals = v[c].to_numpy(dtype="float32"); col = np.full(len(panel), np.nan, dtype="float32")
        col[ok] = vals[code[ok]]; panel[c] = col
    panel = panel[panel["light_front"].notna()].copy()
    panel["one_sided"] = panel["one_sided"] > 0.5
    return panel


def read_out(panel):
    """Yearly sale rate by quarter of each measure, and the change in the yearly
    chance of a sale for one more hour of sun, holding property type, price,
    length of ownership and calendar year fixed. The second is a straight-line
    fit, with its range from a block bootstrap over properties."""
    res = {}
    y = panel["label"].to_numpy(dtype="float64")
    C = panel[CTRL].astype("float64"); C = C.fillna(C.median()); C["tenure_sq"] = C["tenure"] ** 2
    C = (C - C.mean()) / C.std().replace(0, 1)
    yr = pd.get_dummies(panel["year"].astype(int), drop_first=True, dtype="float64")
    base = np.column_stack([np.ones(len(panel)), C.to_numpy(), yr.to_numpy()])
    blk = ((np.abs(panel["key"].to_numpy()) // 7) % 300).astype(int)
    order = np.argsort(blk, kind="stable"); cuts = np.searchsorted(blk[order], np.arange(301))
    rng = np.random.default_rng(1); W = rng.poisson(1.0, (200, 300)).astype("float64")
    for c in MEASURES:
        v = panel[c].to_numpy(dtype="float64")
        band = pd.qcut(panel[c].rank(method="first"), 4, labels=False)
        rate = panel.groupby(band)["label"].mean()
        X = np.column_stack([base, v])
        XtX = np.stack([X[order[cuts[i]:cuts[i + 1]]].T @ X[order[cuts[i]:cuts[i + 1]]] for i in range(300)])
        Xty = np.stack([X[order[cuts[i]:cuts[i + 1]]].T @ y[order[cuts[i]:cuts[i + 1]]] for i in range(300)])
        beta = np.linalg.solve(XtX.sum(0), Xty.sum(0))[-1]
        bs = [np.linalg.solve(np.tensordot(w, XtX, 1), w @ Xty)[-1] for w in W]
        res[c] = {"sale_rate_by_quarter": [round(float(x), 4) for x in rate],
                  "quarter_cuts_hours": [round(float(panel[c].quantile(q)), 2) for q in (.25, .5, .75)],
                  "points_per_hour": round(100 * float(beta), 3),
                  "points_per_hour_ci": [round(100 * float(np.percentile(bs, 2.5)), 3), round(100 * float(np.percentile(bs, 97.5)), 3)],
                  "sd_hours": round(float(np.std(v)), 2)}
    return res


def analyse(tx_path, views_dir):
    lights = {city: pd.read_parquet(Path(views_dir) / f"light_{city}.parquet") for city in CITIES
              if (Path(views_dir) / f"light_{city}.parquet").exists()}
    tx = pd.read_parquet(tx_path)
    res = {}
    for city, L in lights.items():
        face = pd.cut((L.front_bearing + 45) % 360, [0, 90, 180, 270, 360], labels=["north", "east", "south", "west"],
                      include_lowest=True)
        by_face = L.assign(face=face).groupby("face", observed=True)[["light_front", "light_back", "winter_front", "winter_back"]].median().round(1)
        pc = postcode_table(L)
        panel = city_panel(tx, city, pc)
        res[city] = {
            "n_houses": int(len(L)),
            "median": {c: round(float(L[c].median()), 2) for c in MEASURES},
            "quartiles_light_best": [round(float(L.light_best.quantile(q)), 1) for q in (.1, .25, .5, .75, .9)],
            "by_front_facing": by_face.to_dict("index"),
            "within_postcode_variance": {c: round(float(L.groupby("postcode")[c].var().mean() / L[c].var()), 2) for c in MEASURES[:4]},
            "one_sided_postcodes": int(pc.one_sided.sum()), "postcodes": int(len(pc)),
            "home_years": int(len(panel)), "home_years_one_sided": int(panel.one_sided.sum()),
            "sales": int(panel.label.sum()), "sales_one_sided": int(panel.label[panel.one_sided].sum()),
            "all_postcodes": read_out(panel), "one_sided_only": read_out(panel[panel.one_sided])}
        print(f"\n{CITIES[city]['name']}: {len(L):,} houses; typical yearly-average sun on the sunnier side "
              f"{res[city]['median']['light_best']} h a day; {pc.one_sided.sum():,} of {len(pc):,} postcodes are one-sided; "
              f"{len(panel):,} home-years, {int(panel.one_sided.sum()):,} on one-sided postcodes", flush=True)
        print("  front faces   sun front / back (h a day, yearly)   midwinter front / back")
        for k, v in res[city]["by_front_facing"].items():
            print(f"  {k:8s}      {v['light_front']:.1f} / {v['light_back']:.1f}                         {v['winter_front']:.1f} / {v['winter_back']:.1f}")
        for scope in ("all_postcodes", "one_sided_only"):
            print(f"  {scope}: yearly sale rate, darkest quarter -> lightest quarter; change in yearly sale chance per extra hour (points), 95% range")
            for c in MEASURES:
                r = res[city][scope][c]; q = r["sale_rate_by_quarter"]
                print(f"    {LABEL[c]:44s} {100*q[0]:.2f}% {100*q[1]:.2f}% {100*q[2]:.2f}% {100*q[3]:.2f}%   "
                      f"{r['points_per_hour']:+.3f} ({r['points_per_hour_ci'][0]:+.3f} to {r['points_per_hour_ci'][1]:+.3f})", flush=True)
    json.dump(res, open(Path(views_dir) / "light.json", "w"), indent=1)


if __name__ == "__main__":
    if sys.argv[1] == "compute":
        compute(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else 2)
    else:
        analyse(sys.argv[2], sys.argv[3])
