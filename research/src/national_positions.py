"""Every house position in England and Wales, from OS Open UPRN.

As in the city runs: address points are grouped by the 1 m cell they fall
in (a block of flats is one position), and a position is kept if it is
within 150 m of an England or Wales postcode centre, which it is given.
Each position keeps its lowest UPRN, so exact postcodes or any other
address-level data can be joined later.

Usage: python national_positions.py <osopenuprn.zip> <geo_postcode.parquet> <out.parquet>
"""
import sys
import zipfile

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree


def main(zip_path, geo_path, out):
    geo = pd.read_parquet(geo_path, columns=["postcode", "lon", "lat"])
    pe, pn = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True).transform(geo.lon.to_numpy(), geo.lat.to_numpy())
    parts = []
    with zipfile.ZipFile(zip_path) as z:
        name = [m for m in z.namelist() if m.endswith(".csv")][0]
        with z.open(name) as f:
            for ch in pd.read_csv(f, chunksize=4_000_000, usecols=[0, 1, 2], dtype={0: "int64", 1: "float64", 2: "float64"}):
                ch.columns = ["uprn", "e", "n"]
                parts.append(pd.DataFrame({"x": np.floor(ch.e).astype(np.int32), "y": np.floor(ch.n).astype(np.int32),
                                           "uprn": ch.uprn.to_numpy()}))
    u = pd.concat(parts, ignore_index=True)
    g = u.groupby(["x", "y"], sort=False).agg(uprn=("uprn", "min"), n_uprn=("uprn", "size")).reset_index()
    d, idx = cKDTree(np.column_stack([pe, pn])).query(np.column_stack([g.x + 0.5, g.y + 0.5]), k=1, distance_upper_bound=150)
    ok = np.isfinite(d)
    g = g[ok].reset_index(drop=True)
    g["postcode"] = geo.postcode.to_numpy()[idx[ok]]
    g["n_uprn"] = g.n_uprn.astype(np.int32)
    g["cell"] = ((g.x // 10_000) * 1000 + g.y // 10_000).astype(np.int32)
    g = g.sort_values(["cell", "y", "x"]).reset_index(drop=True)
    g.to_parquet(out, index=False)
    print(f"{len(u):,} address points -> {len(g):,} positions in {g.cell.nunique():,} cells, {int(g.n_uprn.sum()):,} addresses")


if __name__ == "__main__":
    main(*sys.argv[1:4])
