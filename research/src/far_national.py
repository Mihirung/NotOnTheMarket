"""One 30 m terrain and water grid for all of England and Wales, plus a 40 km
border, on the British National Grid.

The city runs warped the Copernicus GLO-30 tiles to a 72 km square around
each city. The national run needs that square for every 10 km cell, so the
warp is done once here, the same way (bilinear for heights, nearest for
the water mask), and each cell slices its square from the stored grid.

Heights are stored as whole decimetres (int16), water as the Copernicus
water-body codes (uint8).

Usage: python far_national.py <cop30_dir> <out_dir>
"""
import glob
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

E0, E1, N0, N1, RES = 40_000, 700_000, -40_000, 700_000, 30.0
W, H = int((E1 - E0) / RES), int((N1 - N0) / RES)


def main(cop_dir, out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    z = np.lib.format.open_memmap(out / "far30_z.npy", mode="w+", dtype=np.int16, shape=(H, W))
    wb = np.lib.format.open_memmap(out / "far30_wb.npy", mode="w+", dtype=np.uint8, shape=(H, W))
    z[:] = 0; wb[:] = 0
    S = 2000                                                   # warp in strips to keep memory small
    for r0 in range(0, H, S):
        h = min(S, H - r0)
        tr = from_origin(E0, N1 - r0 * RES, RES, RES)
        zs = np.full((h, W), np.nan, np.float32); ws = np.full((h, W), 255, np.uint8)
        for kind, dest in (("DEM", zs), ("WBM", ws)):
            for p in sorted(glob.glob(f"{cop_dir}/*_{kind}.tif")):
                with rasterio.open(p) as src:
                    l, b, r, t = transform_bounds(src.crs, "EPSG:27700", *src.bounds, densify_pts=21)
                    if r < E0 or l > E1 or t < N1 - (r0 + h) * RES or b > N1 - r0 * RES:
                        continue
                    if kind == "DEM":
                        tmp = np.full((h, W), np.nan, np.float32)
                        reproject(rasterio.band(src, 1), tmp, dst_crs="EPSG:27700", dst_transform=tr,
                                  resampling=Resampling.bilinear, dst_nodata=np.nan)
                        m = np.isfinite(tmp)
                    else:
                        tmp = np.full((h, W), 255, np.uint8)
                        reproject(rasterio.band(src, 1), tmp, dst_crs="EPSG:27700", dst_transform=tr,
                                  resampling=Resampling.nearest, dst_nodata=255)
                        m = tmp != 255
                    dest[m] = tmp[m]
        z[r0:r0 + h] = np.round(np.nan_to_num(zs, nan=0.0) * 10).astype(np.int16)
        wb[r0:r0 + h] = np.where(ws == 255, 0, ws)
        print(f"rows {r0}-{r0 + h} of {H}", flush=True)
    z.flush(); wb.flush()
    (out / "far30.txt").write_text(f"{E0} {E1} {N0} {N1} {RES}\n")


def window(cx, cy, half=36_000, root="research/data/far30"):
    """The 72 km square around (cx, cy) in the same form as
    city_views.warp_far(): heights (m), water codes, west edge, north edge, cell size."""
    z = np.load(Path(root) / "far30_z.npy", mmap_mode="r"); wb = np.load(Path(root) / "far30_wb.npy", mmap_mode="r")
    c0 = int(np.floor((cx - half - E0) / RES)); r0 = int(np.floor((N1 - (cy + half)) / RES))
    n = int(2 * half / RES)
    zz = np.zeros((n, n), np.float32); ww = np.zeros((n, n), np.uint8)
    rs, cs = max(r0, 0), max(c0, 0); re, ce = min(r0 + n, H), min(c0 + n, W)
    zz[rs - r0:re - r0, cs - c0:ce - c0] = z[rs:re, cs:ce].astype(np.float32) / 10.0
    ww[rs - r0:re - r0, cs - c0:ce - c0] = wb[rs:re, cs:ce]
    return zz, ww, E0 + c0 * RES, N1 - r0 * RES, RES


if __name__ == "__main__":
    main(*sys.argv[1:3])
