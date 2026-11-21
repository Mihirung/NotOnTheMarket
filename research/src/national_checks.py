"""Checks on the national house-level run.

  1. Parity with the city runs. For Exeter, Bath, Plymouth and Bristol the
     national run and the city run measured the same houses with the same
     method; this shows how closely they agree, measure by measure.
  2. What the old 30 m layer missed. Postcode by postcode across the
     country, how well the 30 m view (the national model's VIEW family)
     tracks the house-level measures (HOUSE), as view_fidelity.py did for
     two cities.
  3. Light and sale rates nationally. The yearly share of homes sold, from
     the darkest quarter of postcodes to the lightest, as light.py did for
     two cities.

Usage: python national_checks.py <national_dir> <views2_dir> <panel_dir> <out.json>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import signals as SG  # noqa: E402

CITY_CELLS = {"exeter": "EX", "bath": "BA", "plymouth": "PL", "bristol": "BS"}
COMPARE = ["storeys", "front_bearing", "u_long", "u_longest_km", "u_water", "u_hills", "u_overlooked", "g_overlooked",
           "sun_evening_jun", "sun_equinox", "light_front", "light_back", "top_front", "winter_back"]


def parity(nat, views2):
    res = {}
    for city in CITY_CELLS:
        hp = Path(views2) / f"houses_{city}.parquet"; lp = Path(views2) / f"light_{city}.parquet"
        if not hp.exists() or not lp.exists():
            continue
        c = pd.read_parquet(hp)
        L = pd.read_parquet(lp).drop(columns=["postcode", "sector", "n_uprn", "front_bearing", "road_m", "depth_m"])
        c = pd.concat([c, L], axis=1).rename(columns={"ce": "x", "cn": "y"})
        cells = sorted({f"{x // 10_000}_{y // 10_000}" for x, y in zip(c.x, c.y)})
        n = pd.concat([pd.read_parquet(Path(nat) / "cells" / f"{k}.parquet", columns=["x", "y"] + COMPARE)
                       for k in cells if (Path(nat) / "cells" / f"{k}.parquet").exists()])
        m = c.merge(n, on=["x", "y"], suffixes=("_c", "_n"))
        r = {"city_houses": int(len(c)), "matched": int(len(m))}
        for col in COMPARE:
            a, b = m[f"{col}_c"].astype(float), m[f"{col}_n"].astype(float); ok = a.notna() & b.notna()
            r[col] = {"identical": round(float((np.abs(a[ok] - b[ok]) < 1e-3).mean()), 4),
                      "mean_city": round(float(a[ok].mean()), 4), "mean_national": round(float(b[ok].mean()), 4),
                      "corr": round(float(np.corrcoef(a[ok], b[ok])[0, 1]), 4) if ok.sum() > 2 else None}
        res[city] = r
        print(city, {k: (v["identical"], v["corr"]) if isinstance(v, dict) else v for k, v in r.items()}, flush=True)
    return res


def fidelity():
    v = SG.FAMILIES["VIEW"]; h = SG.FAMILIES["HOUSE"]
    V = pd.read_parquet(SG.ROOT / v["table"]).set_index("postcode")
    H = pd.read_parquet(SG.ROOT / h["table"]).set_index("postcode")
    j = H.join(V, how="inner")
    pairs = [("long views (2 km+)", "v30_long2", "u_long"), ("longest sight-line", "v30_longest_km", "u_longest_km"),
             ("water in view", "v30_water", "u_water"), ("sea in view", "v30_sea", "u_tidal"),
             ("hills on the skyline", "v30_hills", "u_hills"), ("skyline height", "v30_horizon", "u_horizon"),
             ("west horizon vs evening sun", "v30_hz_w", "sun_evening_jun"),
             ("south horizon vs winter sun indoors", "v30_hz_s", "winter_front"),
             ("anything vs how overlooked", "v30_rough", "u_overlooked")]
    out = {"postcodes": int(len(j))}
    for label, a, b in pairs:
        out[label] = round(float(j[a].rank().corr(j[b].rank())), 3)
    print("30 m layer vs house level, rank correlation by postcode:", out, flush=True)
    return out


def light_rates(panel_dir):
    import model_lab as ML
    ch = ML.Chunks(panel_dir)
    res = {}
    for col in ("light_both", "light_front", "light_back", "winter_front", "sun_evening_jun", "u_long"):
        rates = []
        ys, xs = [], []
        for c in (0, 1):
            r = ch.rows(c, (2010, 2019))
            idx = ch.names.index(col)
            xs.append(ch.X(c).take(r, [idx])[:, 0]); ys.append(ch.col("y", c)[r])
        x, y = np.concatenate(xs), np.concatenate(ys)
        ok = np.isfinite(x)
        q = pd.qcut(pd.Series(x[ok]).rank(method="first"), 4, labels=False).to_numpy()
        rates = [round(float(y[ok][q == k].mean()), 4) for k in range(4)]
        res[col] = {"sale_rate_by_quarter": rates, "quarter_cuts": [round(float(np.quantile(x[ok], p)), 2) for p in (.25, .5, .75)],
                    "home_years": int(ok.sum())}
        print(col, rates, flush=True)
    return res


if __name__ == "__main__":
    nat, views2, panel, out = sys.argv[1:5]
    R = {"parity": parity(nat, views2), "fidelity": fidelity()}
    if Path(panel).exists():
        R["light_rates"] = light_rates(panel)
    json.dump(R, open(out, "w"), indent=1)
