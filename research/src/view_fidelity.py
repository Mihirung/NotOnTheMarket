"""How much of the 1 m truth does the national 30 m layer recover?

Compares, postcode by postcode in the two LIDAR cities, the national
terrain-scale outlook with the house-level outlook averaged over the
houses on that postcode. Spearman rank correlations, because the two
are measured on different scales.

Usage: python view_fidelity.py <view30.parquet> <views2_dir> <out_json>
"""
import json
import sys
from pathlib import Path

import pandas as pd

PAIRS = [("v30_long2", "m_u_long", "long views (2 km+)"), ("v30_longest_km", "m_u_longest_km", "longest sight-line"),
         ("v30_water", "m_u_water", "water in view"), ("v30_hills", "m_u_hills", "hills on the skyline"),
         ("v30_horizon", "m_u_horizon", "skyline height, upstairs"), ("v30_horizon", "m_g_horizon", "skyline height, garden"),
         ("v30_rough", "m_g_overlooked", "roughness vs overlooked"), ("v30_hz_w", "m_sun_evening_jun", "west horizon vs evening sun"),
         ("v30_skyview", "m_sun_equinox", "sky view vs equinox sun"), ("v30_tpi1k", "m_u_long", "relief vs long views")]


def main(v30_path, views_dir, out_json):
    v30 = pd.read_parquet(v30_path).set_index("postcode")
    res = {}
    for city in ("exeter", "bath"):
        f = Path(views_dir) / f"postcodes_{city}.parquet"
        if not f.exists():
            continue
        d = pd.read_parquet(f).set_index("postcode").join(v30, how="inner")
        res[city] = {"n_postcodes": int(len(d)),
                     "spearman": {label: round(float(d[a].corr(d[b], method="spearman")), 2) for a, b, label in PAIRS}}
        print(f"{city}: {len(d):,} postcodes")
        for label, r in res[city]["spearman"].items():
            print(f"  {label:32s} rho = {r:+.2f}")
    json.dump(res, open(out_json, "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:4])
