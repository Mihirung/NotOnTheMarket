"""Every postcode sector in England and Wales, with what the search ranks on, in one small file.

The search has no area step: it ranks all sectors in the country on the brief
first, then loads the detail (areas/<code>.json) for the few areas that hold the
best fits. This file carries, per sector, its position, air, openness, distances
and climate, and per kind of home its count, the homes we would write to,
expected sellers, the typical chance to sell and the typical offer.

Built from the area files export_site_v5.py writes, so it always matches them.

Usage: python export_sectors.py <site_dir>      (writes <site_dir>/sectors.json)
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

PLACE = ["nox", "density", "km_gp", "km_hosp", "km_park", "km_blue", "km_pub",
         "sun_h", "rain_mm", "winter_c", "summer_c", "frosts", "wind", "warm_2c", "hot_2c"]
ROUND = {"nox": 1, "density": 0, "km_gp": 2, "km_hosp": 1, "km_park": 2, "km_blue": 2, "km_pub": 2,
         "sun_h": 0, "rain_mm": 0, "winter_c": 1, "summer_c": 1, "frosts": 0, "wind": 2, "warm_2c": 1, "hot_2c": 1}


def wmean(v, w):
    v, w = np.asarray(v, float), np.asarray(w, float)
    ok = ~np.isnan(v) & (w > 0)
    return float(np.average(v[ok], weights=w[ok])) if ok.any() else None


def wmedian(v, w):
    v, w = np.asarray(v, float), np.asarray(w, float)
    ok = ~np.isnan(v) & (w > 0)
    if not ok.any():
        return None
    o = np.argsort(v[ok])
    c = np.cumsum(w[ok][o])
    return float(v[ok][o][np.searchsorted(c, c[-1] / 2)])


def build(site_dir):
    site_dir = Path(site_dir)
    rows = []
    for f in sorted((site_dir / "areas").glob("*.json")):
        d = json.loads(f.read_text())
        cols = d["cell_cols"]
        ix = {c: i for i, c in enumerate(cols)}
        by = defaultdict(list)
        for c in d["cells"]:
            by[c[ix["sector"]]].append(c)
        for sec, cells in by.items():
            n = [c[ix["n"]] for c in cells]
            num = lambda k: [np.nan if c[ix[k]] is None else c[ix[k]] for c in cells] if k in ix else [np.nan] * len(cells)
            lat, lon = wmean(num("lat"), n), wmean(num("lon"), n)
            if lat is None:
                continue
            place = []
            for k in PLACE:
                v = wmean(num(k), n)
                place.append(None if v is None else round(v, ROUND[k]) if ROUND[k] else int(round(v)))
            types = []
            for t in sorted({c[ix["ptype"]] for c in cells}):
                tc = [c for c in cells if c[ix["ptype"]] == t]
                tn = [c[ix["n"]] for c in tc]
                types.append([t, int(sum(tn)), int(sum(c[ix["n_top"]] for c in tc)),
                              round(sum(c[ix["exp_sellers"]] for c in tc), 2),
                              round(wmean([c[ix["p_med"]] for c in tc], tn) or 0, 4),
                              int(round(wmedian([c[ix["offer_med"]] for c in tc], tn) or 0, -3))])
            rows.append([sec, d["code"], round(lat, 4), round(lon, 4), *place, types])
    out = site_dir / "sectors.json"
    out.write_text(json.dumps({"cols": ["sector", "area", "lat", "lon", *PLACE, "types"],
                               "type_cols": ["ptype", "n", "n_top", "exp_sellers", "p_med", "offer_med"],
                               "rows": rows}, separators=(",", ":")))
    print(f"{len(rows):,} sectors -> {out} ({out.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    build(sys.argv[1])
