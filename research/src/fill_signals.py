"""Give postcodes that no area table matched the values of the nearest postcode
that has them.

Area tables (census, housing stock, crime) are keyed by 2011 statistical
areas; a few per cent of postcodes carry a newer area code or none. Their
neighbours a few hundred metres away live in the same streets, so the
nearest matched postcode stands in. Only postcodes with every column
missing are filled: a column left blank on purpose (no Ofsted grades in
Wales) stays blank.

Usage: python fill_signals.py FAMILY [FAMILY ...]
"""
import sys

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, "research/src")
import signals as SG  # noqa: E402


def main(fams):
    from pyproj import Transformer
    g = pd.read_parquet("research/data/geo_postcode.parquet", columns=["postcode", "lon", "lat"]).dropna()
    x, y = Transformer.from_crs(4326, 27700, always_xy=True).transform(g.lon.to_numpy(), g.lat.to_numpy())
    pos = pd.DataFrame({"x": x, "y": y}, index=g.postcode.to_numpy())
    for f in fams:
        path = SG.ROOT / SG.FAMILIES[f]["table"]
        if not path.exists():
            print(f"{f}: no table, skipped"); continue
        t = pd.read_parquet(path)
        cols = SG.FAMILIES[f]["columns"]
        empty = t[cols].isna().all(axis=1).to_numpy()
        have = ~empty & t.postcode.isin(pos.index).to_numpy()
        need = empty & t.postcode.isin(pos.index).to_numpy()
        if need.any() and have.any():
            src = pos.loc[t.postcode[have]].to_numpy(); dst = pos.loc[t.postcode[need]].to_numpy()
            d, j = cKDTree(src).query(dst, distance_upper_bound=3000)
            ok = np.isfinite(d)
            rows_src = np.nonzero(have)[0][j[ok]]; rows_dst = np.nonzero(need)[0][ok]
            t.loc[t.index[rows_dst], cols] = t.loc[t.index[rows_src], cols].to_numpy()
            print(f"{f}: {need.sum():,} postcodes had nothing; {ok.sum():,} filled from a neighbour within 3 km "
                  f"(median {np.median(d[ok]):.0f} m)")
        t.to_parquet(path, index=False)
        print(f"{f}: {t[cols].notna().any(axis=1).mean():.1%} of postcodes now have values")


if __name__ == "__main__":
    main(sys.argv[1:])
