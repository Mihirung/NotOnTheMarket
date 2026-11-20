"""Attach outlook data to the prototype's sector cells.

Per sector (postcode sector, ~15-40 postcodes, hundreds of homes):
  * shares of postcodes with each kind of view, so the site can say
    "6 in 10 homes here have long views upstairs" rather than pretend
    to know one house
  * one representative 360-degree horizon profile (the postcode whose
    upstairs long-view share is the sector median), at 2-degree steps,
    for drawing the horizon card
  * which landmarks are typically in sight

Usage: python export_views_demo.py <views_dir> <demo_v2.json> <out_json>
"""
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, __import__("os").path.dirname(__file__))
from compute_views import LANDMARKS  # noqa: E402


def bearing_deg(e0, n0, e1, n1):
    return float(np.degrees(np.arctan2(e1 - e0, n1 - n0)) % 360)

# Absolute, physically meaningful cut-offs (see docs/05): a home "has" the
# view if at least this much of the horizon qualifies.
THRESH = dict(long=0.10, water=0.02, hills=0.02, private=0.50, west=15.0, open=15.0)


def sector_of(pc):
    a, b = pc.rsplit(" ", 1)
    return f"{a} {b[0]}"


def main(views_dir, demo_path, out_path):
    df = pd.read_parquet(f"{views_dir}/views_postcode.parquet")
    prof = json.load(open(f"{views_dir}/views_profiles.json"))
    df["sector"] = df.postcode.map(sector_of)
    landmarks = [c[5:] for c in df.columns if c.startswith("sees_")]

    sectors = {}
    for sec, g in df.groupby("sector"):
        rep_target = g.u_long_view_share.median()
        rep = g.iloc[(g.u_long_view_share - rep_target).abs().argsort().iloc[0]]
        best = g.iloc[g.u_long_view_share.argmax()]
        p = prof[rep.postcode]
        pb = prof[best.postcode]
        def thin(arr, k=2):
            return arr[::k]
        sectors[sec] = {
            "n_postcodes": int(len(g)),
            "ground_m": int(g.ground_m.median()),
            "shares": {
                "long":    round(float((g.u_long_view_share >= THRESH["long"]).mean()), 2),
                "water":   round(float((g.u_water_share >= THRESH["water"]).mean()), 2),
                "hills":   round(float((g.u_hills_share >= THRESH["hills"]).mean()), 2),
                "private": round(float((g.g_overlooked_share <= THRESH["private"]).mean()), 2),
                "west":    round(float((g.g_west_horizon_deg <= THRESH["west"]).mean()), 2),
                "open":    round(float((g.g_median_horizon_deg <= THRESH["open"]).mean()), 2),
            },
            "typical": {
                "horizon_deg": round(float(g.g_median_horizon_deg.median()), 1),
                "overlooked": round(float(g.g_overlooked_share.median()), 2),
                "longest_km": round(float(g.u_longest_view_km.median()), 1),
                "west_deg": round(float(g.g_west_horizon_deg.median()), 1),
            },
            "landmarks": {lm: round(float(g["sees_" + lm].mean()), 2) for lm in landmarks},
            "landmark_bearing": {lm: round(bearing_deg(rep.e, rep.n, *LANDMARKS[lm][:2]))
                                 for lm in landmarks if lm in LANDMARKS},
            "landmark_km": {lm: round(float(np.hypot(LANDMARKS[lm][0] - rep.e,
                                                     LANDMARKS[lm][1] - rep.n)) / 1000, 1)
                            for lm in landmarks if lm in LANDMARKS},
            "profile": {  # representative postcode, 2-degree steps
                "g_deg": thin(np.round(p["g_deg"], 1)).tolist(),
                "g_cls": thin(np.array(p["g_cls"])).tolist(),
                "u_deg": thin(np.round(p["u_deg"], 1)).tolist(),
                "u_cls": thin(np.array(p["u_cls"])).tolist(),
                "u_dist": thin(np.array(p["u_dist"])).tolist(),
            },
            "best": {  # the best upstairs outlook in the sector, for the seller page
                "u_deg": thin(np.round(pb["u_deg"], 1)).tolist(),
                "u_cls": thin(np.array(pb["u_cls"])).tolist(),
                "u_dist": thin(np.array(pb["u_dist"])).tolist(),
                "longest_km": round(float(best.u_longest_view_km), 1),
            },
        }

    demo = json.load(open(demo_path))
    demo["views"] = sectors
    demo["view_landmarks"] = landmarks
    demo["area"]["view_sources"] = ("Environment Agency LIDAR composite 1 m DSM/DTM (OGL); "
                                    "OS OpenMap Local buildings, water, woodland (OGL); "
                                    "Copernicus GLO-30 terrain. Outlooks computed per postcode "
                                    "from the nearest open ground to its centre, not per house.")
    cells_with = sum(1 for c in demo["cells"] if c["sector"] in sectors)
    with open(out_path, "w") as fh:
        json.dump(demo, fh, separators=(",", ":"))
    print(f"{len(sectors)} sectors with outlooks; {cells_with}/{len(demo['cells'])} cells covered -> {out_path}")
    sh = pd.DataFrame({s: v["shares"] for s, v in sectors.items()}).T
    print("share of postcodes per sector, distribution across sectors:")
    print(sh.describe().round(2).loc[["min", "25%", "50%", "75%", "max"]].to_string())


if __name__ == "__main__":
    main(*sys.argv[1:4])
