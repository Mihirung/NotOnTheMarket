"""National terrain-scale outlook for every England & Wales postcode.

A 1 m surface model of the whole country is ~500 GB and out of reach
here, so this layer answers the terrain-scale questions only, from the
Copernicus GLO-30 surface model (30 m) and its water-body mask:

  how far can you see, and on how much of the compass
  is the sea, a lake or a wide river in view
  are there hills on the skyline
  how high, how exposed, how steep, which way the slope faces
  how rough the immediate surface is (buildings and trees, smoothed)

It cannot see a neighbour's roof. That is what the 1 m city pipeline is
for; `view_fidelity.py` measures how much of the 1 m truth this layer
recovers.

Method: all tiles are warped into one British National Grid raster at
30 m. For each postcode, 120 rays (3 degree steps) are cast to 30 km
with step lengths growing with distance, earth curvature and refraction
applied, eye 3 m above the surface cell, starting two cells out.

Usage: python build_view30.py <cop30_dir> <pc_db_dir> <out_parquet> [workers]
"""

import glob
import sqlite3
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from scipy.ndimage import distance_transform_edt, uniform_filter

RES = 30.0
E0, E1, N0, N1 = 80_000.0, 660_000.0, 0.0, 660_000.0
W, H = int((E1 - E0) / RES), int((N1 - N0) / RES)
R_EARTH, REFRACTION = 6_371_000.0, 0.13
EYE = 3.0
BEAR = np.radians(np.arange(0, 360, 3.0))
DX, DY = np.sin(BEAR).astype("float32"), np.cos(BEAR).astype("float32")
DIST = np.concatenate([np.arange(60, 1500, 30), np.arange(1500, 6000, 60),
                       np.arange(6000, 30001, 150)]).astype("float32")
CURV = (DIST ** 2 / (2 * R_EARTH) * (1 - REFRACTION)).astype("float32")
REGIONS = ["east_midlands", "east_of_england", "london", "north_east", "north_west",
           "south_east", "south_west", "wales", "west_midlands", "yorkshire_and_the_humber"]
FEATS = ["v30_elev", "v30_horizon", "v30_hz_s", "v30_hz_w", "v30_hz_e", "v30_hz_n",
         "v30_long2", "v30_long5", "v30_long10", "v30_longest_km", "v30_logreach",
         "v30_sea", "v30_water", "v30_water_near", "v30_hills", "v30_skyview"]

Z = None      # float32 (H, W) surface heights, shared with workers by fork
WB = None     # uint8 water-body mask: 0 none, 1 ocean, 2 lake, 3 river


def warp_tiles(cop_dir):
    z = np.full((H, W), np.nan, dtype="float32")
    wb = np.zeros((H, W), dtype="uint8")
    for kind, dest, res in (("DEM", z, Resampling.bilinear), ("WBM", wb, Resampling.nearest)):
        for p in sorted(glob.glob(f"{cop_dir}/*_{kind}.tif")):
            with rasterio.open(p) as src:
                l, b, r, t = transform_bounds(src.crs, "EPSG:27700", *src.bounds, densify_pts=21)
                c0, c1 = max(0, int(np.floor((l - E0) / RES))), min(W, int(np.ceil((r - E0) / RES)))
                r0, r1 = max(0, int(np.floor((N1 - t) / RES))), min(H, int(np.ceil((N1 - b) / RES)))
                if c1 <= c0 or r1 <= r0:
                    continue
                if kind == "DEM":
                    tmp = np.full((r1 - r0, c1 - c0), np.nan, dtype="float32")
                    reproject(rasterio.band(src, 1), tmp, dst_crs="EPSG:27700",
                              dst_transform=from_origin(E0 + c0 * RES, N1 - r0 * RES, RES, RES),
                              resampling=res, dst_nodata=np.nan)
                    m = np.isfinite(tmp)
                else:
                    tmp = np.full((r1 - r0, c1 - c0), 255, dtype="uint8")
                    reproject(rasterio.band(src, 1), tmp, dst_crs="EPSG:27700",
                              dst_transform=from_origin(E0 + c0 * RES, N1 - r0 * RES, RES, RES),
                              resampling=res, dst_nodata=255)
                    m = tmp != 255
                dest[r0:r1, c0:c1][m] = tmp[m]
        print(f"  {kind}: {len(glob.glob(f'{cop_dir}/*_{kind}.tif'))} tiles warped", flush=True)
    z[~np.isfinite(z)] = 0.0
    return z, wb


def load_postcodes(db_dir):
    frames = []
    for reg in REGIONS:
        con = sqlite3.connect(Path(db_dir) / f"postcodes_geo_{reg}.sqlite")
        frames.append(pd.read_sql_query(
            """select p.postcode as postcode, (i.xmin+i.xmax)/2.0 as lon, (i.ymin+i.ymax)/2.0 as lat
               from postcodes p join idx_postcodes_geom i on i.pkid = p.rowid""", con))
        con.close()
    pc = pd.concat(frames, ignore_index=True)
    pc["postcode"] = pc["postcode"].str.strip().str.upper()
    pc = pc.drop_duplicates("postcode").reset_index(drop=True)
    t = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
    pc["e"], pc["n"] = t.transform(pc["lon"].to_numpy(), pc["lat"].to_numpy())
    return pc


def outlook_batch(args):
    e, n = args
    B = len(e)
    col0 = ((e - E0) / RES).astype(np.int64).clip(0, W - 1)
    row0 = ((N1 - n) / RES).astype(np.int64).clip(0, H - 1)
    z_eye = Z[row0, col0] + EYE
    E = e[:, None, None].astype("float32") + DX[None, :, None] * DIST[None, None, :]
    N = n[:, None, None].astype("float32") + DY[None, :, None] * DIST[None, None, :]
    col = ((E - E0) / RES).astype(np.int32); row = ((N1 - N) / RES).astype(np.int32)
    del E, N
    ok = (col >= 0) & (col < W) & (row >= 0) & (row < H)
    np.clip(col, 0, W - 1, out=col); np.clip(row, 0, H - 1, out=row)
    z = Z[row, col]; wb = WB[row, col]
    del row, col
    rel = z - CURV[None, None, :] - z_eye[:, None, None]
    slope = rel / DIST[None, None, :]
    slope[~ok] = -np.inf
    run = np.maximum.accumulate(slope, axis=2)
    prev = np.concatenate([np.full((B, len(BEAR), 1), -np.inf, dtype="float32"), run[:, :, :-1]], axis=2)
    vis = (slope > prev) & ok
    del prev
    hz = np.degrees(np.arctan(run[:, :, -1]))                       # (B, rays)
    far = np.where(vis, DIST[None, None, :], 0).max(axis=2)          # furthest visible sample per ray
    sea = (vis & (wb == 1)).any(axis=2)
    water = (vis & (wb > 0)).any(axis=2)
    water_near = (vis & (wb > 0) & (DIST[None, None, :] <= 1500)).any(axis=2)
    hills = (vis & (rel >= 75) & (DIST[None, None, :] >= 3000)).any(axis=2)
    b = np.degrees(BEAR)
    sec = lambda lo, hi: hz[:, (b >= lo) & (b < hi)].mean(axis=1)
    hz_n = hz[:, (b >= 330) | (b < 30)].mean(axis=1)
    out = np.column_stack([
        z_eye - EYE, np.median(hz, axis=1), sec(150, 210), sec(240, 300), sec(60, 120), hz_n,
        (far >= 2000).mean(axis=1), (far >= 5000).mean(axis=1), (far >= 10000).mean(axis=1),
        far.max(axis=1) / 1000, np.log10(np.maximum(far, 60)).mean(axis=1),
        sea.mean(axis=1), water.mean(axis=1), water_near.mean(axis=1), hills.mean(axis=1),
        (np.cos(np.radians(np.clip(hz, 0, 90))) ** 2).mean(axis=1),
    ]).astype("float32")
    return out


def main(cop_dir, db_dir, out_path, workers=4):
    global Z, WB
    print("warping Copernicus tiles to British National Grid at 30 m...", flush=True)
    Z, WB = warp_tiles(cop_dir)
    print(f"  grid {Z.shape}, land cells {(Z > 0.5).mean()*100:.0f}%, ocean {(WB == 1).mean()*100:.0f}%, "
          f"inland water {(WB >= 2).mean()*100:.2f}%", flush=True)

    pc = load_postcodes(db_dir)
    inside = pc["e"].between(E0 + 100, E1 - 100) & pc["n"].between(N0 + 100, N1 - 100)
    pc = pc[inside].reset_index(drop=True)
    e, n = pc["e"].to_numpy(), pc["n"].to_numpy()
    col = ((e - E0) / RES).astype(np.int64); row = ((N1 - n) / RES).astype(np.int64)
    print(f"{len(pc):,} postcodes", flush=True)

    # Point terrain attributes from filters over the grid, sampled then freed.
    print("relief, roughness, slope, coast distance...", flush=True)
    m150 = uniform_filter(Z, size=5, mode="nearest")
    resid = Z - m150
    np.square(resid, out=resid)
    rough = uniform_filter(resid, size=5, mode="nearest"); del resid
    pc["v30_rough"] = np.sqrt(rough[row, col]).astype("float32"); del rough, m150
    m1k = uniform_filter(Z, size=67, mode="nearest")
    pc["v30_tpi1k"] = (Z[row, col] - m1k[row, col]).astype("float32"); del m1k
    gx = (Z[row, np.clip(col + 1, 0, W - 1)] - Z[row, np.clip(col - 1, 0, W - 1)]) / (2 * RES)
    gy = (Z[np.clip(row - 1, 0, H - 1), col] - Z[np.clip(row + 1, 0, H - 1), col]) / (2 * RES)
    slope = np.hypot(gx, gy)
    pc["v30_slope"] = np.degrees(np.arctan(slope)).astype("float32")
    # Downhill direction components: +1 southness = ground falls to the south.
    pc["v30_south"] = np.where(slope > 0.01, gy / np.maximum(slope, 1e-6), 0).astype("float32")
    pc["v30_west"] = np.where(slope > 0.01, gx / np.maximum(slope, 1e-6), 0).astype("float32")
    ocean = (WB == 1)[: H // 5 * 5, : W // 5 * 5].reshape(H // 5, 5, W // 5, 5).any(axis=(1, 3))
    dcoast = distance_transform_edt(~ocean) * (RES * 5) / 1000
    pc["v30_km_coast"] = dcoast[np.clip(row // 5, 0, H // 5 - 1), np.clip(col // 5, 0, W // 5 - 1)].astype("float32")
    del dcoast, ocean

    print(f"casting rays with {workers} workers...", flush=True)
    B = 300
    jobs = [(e[i:i + B], n[i:i + B]) for i in range(0, len(pc), B)]
    out = np.empty((len(pc), len(FEATS)), dtype="float32")
    with Pool(int(workers)) as pool:
        for k, res in enumerate(pool.imap(outlook_batch, jobs, chunksize=8)):
            out[k * B:k * B + len(res)] = res
            if k % 500 == 0:
                print(f"  {k * B:,} done", flush=True)
    for j, f in enumerate(FEATS):
        pc[f] = out[:, j]
    pc.drop(columns=["lon", "lat"]).to_parquet(out_path, index=False)
    print(f"wrote {len(pc):,} postcodes -> {out_path}")
    print(pc[["v30_elev", "v30_horizon", "v30_long2", "v30_long10", "v30_longest_km", "v30_sea",
              "v30_water", "v30_hills", "v30_rough", "v30_tpi1k", "v30_km_coast"]]
          .describe().round(2).loc[["mean", "25%", "50%", "75%", "max"]].to_string())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else 4)
