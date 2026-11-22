"""Green space, blue space, pubs and food for every postcode in England and Wales.

Air quality and distances to GPs, hospitals, dentists and pharmacies are
already in the GEO family (build_geo_features.py, from AHAH v4 inputs).
This adds what AHAH measures but does not publish openly:

  green space   OS Open Greenspace: distance to the nearest entrance of a
                public park or garden or a playing field, the area of those
                within 1 km, distance to the nearest play space; and from OS
                OpenMap Local, distance to the nearest wood of 10 ha or more
  blue space    OS OpenMap Local: distance to the nearest river, lake or
                reservoir of 2 ha or more, and to the sea or an estuary
  pubs and food Food Standards Agency hygiene register (every food business
                must register): distance to the nearest pub or bar, pubs and
                bars within 1 km, takeaways within 1 km, restaurants and
                cafes within 1 km

Distances are straight lines from the postcode's centre, in km.
Writes research/data/signals/amenity_postcode.parquet (the AMENITY family).

Usage: python amenity_signals.py
"""
import json
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from scipy.spatial import cKDTree

AM = Path("research/data/amenity")
OSMAP = Path("research/data/osmap/cells")
OUT = Path("research/data/signals/amenity_postcode.parquet")
TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
PARKS = {"Public Park Or Garden", "Playing Field"}


def postcodes():
    g = pd.read_parquet("research/data/geo_postcode.parquet", columns=["postcode", "lat", "lon"]).dropna()
    e, n = TO_BNG.transform(g.lon.to_numpy(), g.lat.to_numpy())
    return g.postcode.astype(str).to_numpy(), np.column_stack([e, n])


def edge_points(geoms, step):
    """Points every `step` metres along the edges of polygons."""
    b = shapely.segmentize(shapely.boundary(geoms), step)
    return shapely.get_coordinates(b)


def fsa(name, pcs, xy):
    rows = pd.DataFrame(json.load(open(AM / "fsa" / f"{name}.json")))
    lat = pd.to_numeric(rows.lat, errors="coerce"); lon = pd.to_numeric(rows.lon, errors="coerce")
    e, n = TO_BNG.transform(lon.fillna(0).to_numpy(), lat.fillna(0).to_numpy())
    ok = lat.notna().to_numpy() & (e > 0) & (e < 700_000) & (n > 0) & (n < 700_000)
    pts = np.column_stack([e, n])
    # no position: use the business's postcode centre
    pc_xy = pd.DataFrame(xy, index=pcs)
    miss = ~ok & rows.postcode.notna().to_numpy()
    look = pc_xy.reindex(rows.postcode[miss].str.upper().str.strip())
    pts[miss] = look.to_numpy()
    ok[np.nonzero(miss)[0][look.notna().all(axis=1).to_numpy()]] = True
    print(f"  {name}: {len(rows):,} registered, {int(ok.sum()):,} placed", flush=True)
    return pts[ok]


def main():
    t0 = time.time()
    pcs, xy = postcodes()
    out = pd.DataFrame({"postcode": pcs})
    # pubs and food
    for name in ("pubs", "takeaways", "restaurants"):
        P = fsa(name, pcs, xy); T = cKDTree(P)
        if name == "pubs":
            out["km_pub"] = (T.query(xy)[0] / 1000).astype("float32")
        out[f"{name}_1km"] = np.array([len(i) for i in T.query_ball_point(xy, 1000)], dtype="int16")
    print(f"food done {time.time() - t0:.0f}s", flush=True)
    # green space
    f = AM / "greenspace" / "Data" / "opgrsp_gb.gpkg"
    sites = gpd.read_file(f, layer="greenspace_site", columns=["id", "function"])
    acc = gpd.read_file(f, layer="access_point", columns=["ref_to_greenspace_site"])
    parks = sites[sites.function.isin(PARKS)]
    ap = acc[acc.ref_to_greenspace_site.isin(set(parks.id))]
    no_ap = parks[~parks.id.isin(set(ap.ref_to_greenspace_site))]
    pts = np.vstack([shapely.get_coordinates(ap.geometry.values), edge_points(no_ap.geometry.values, 50)])
    out["km_park"] = (cKDTree(pts).query(xy)[0] / 1000).astype("float32")
    cen = shapely.get_coordinates(shapely.centroid(parks.geometry.values)); ha = shapely.area(parks.geometry.values) / 1e4
    idx = cKDTree(cen).query_ball_point(xy, 1000)
    out["park_ha_1km"] = np.array([ha[i].sum() for i in idx], dtype="float32")
    play = sites[sites.function == "Play Space"]
    out["km_play"] = (cKDTree(shapely.get_coordinates(shapely.centroid(play.geometry.values))).query(xy)[0] / 1000).astype("float32")
    print(f"green space done {time.time() - t0:.0f}s ({len(parks):,} parks and playing fields)", flush=True)
    # woods and water from OpenMap Local, cell by cell (cells overlap by 1.1 km: points are de-duplicated)
    wood, water, sea = [], [], []
    for k, d in enumerate(sorted(OSMAP.iterdir())):
        for p in d.glob("Woodland_*.parquet"):
            g = gpd.read_parquet(p).geometry.values; g = g[shapely.area(g) >= 1e5]
            if len(g): wood.append(np.round(edge_points(g, 100), -2))
        for p in d.glob("SurfaceWater_Area_*.parquet"):
            g = gpd.read_parquet(p).geometry.values; g = g[shapely.area(g) >= 2e4]
            if len(g): water.append(np.round(edge_points(g, 50), -1))
        for lay in ("TidalWater", "Foreshore"):
            for p in d.glob(f"{lay}_*.parquet"):
                g = gpd.read_parquet(p).geometry.values
                if len(g): sea.append(np.round(edge_points(g, 100), -2))
        if k % 200 == 0:
            print(f"  map cells {k + 1}", flush=True)
    for name, parts in (("km_wood", wood), ("km_water", water), ("km_sea", sea)):
        P = np.unique(np.vstack(parts), axis=0)
        out[name] = (cKDTree(P).query(xy)[0] / 1000).astype("float32")
        print(f"  {name}: {len(P):,} edge points", flush=True)
    out["km_blue"] = np.minimum(out.km_water, out.km_sea)
    out.to_parquet(OUT, index=False)
    print(out.describe().round(2).to_string(), flush=True)
    print(f"wrote {OUT} in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
