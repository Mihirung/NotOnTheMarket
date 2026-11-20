"""Compute the outlook from every Exeter postcode.

Inputs: 1 m LIDAR DSM/DTM tiles, OS land-cover masks on the same grid,
30 m Copernicus terrain for the far field, postcode centroids.

For each postcode we take the nearest non-building cell to the centroid
(the garden or street in front) and compute two outlooks:
  garden    eye 1.6 m above ground, own house left in place
  upstairs  eye 5.0 m above ground, the nearest building (the owner's
            own) flattened to ground, since you may stand at whichever
            window faces the view

Writes per-postcode metrics, full 360-degree horizon profiles for every
postcode (compact, uint8/float16), and landmark line-of-sight flags.

Usage: python compute_views.py <terrain_dir> <postcodes.parquet> <out_dir>
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.merge import merge
from scipy.ndimage import distance_transform_edt, label, minimum_filter

sys.path.insert(0, str(Path(__file__).parent))
from viewshed import (BUILDING, Surface, classify, line_of_sight,  # noqa: E402
                      outlook_metrics)

LOCAL_DIST, DISTANT_DIST = 1000, 30000
LANDMARKS = {  # BNG eastings/northings, height added above the surface
    "Exe estuary":      (297300, 86800, 0.5),
    "the sea at Exmouth": (300200, 80200, 0.5),
    "Haldon Hills":     (287550, 86150, 2.0),
    "Dartmoor (Haytor)": (275750, 77050, 2.0),
    "Woodbury Common":  (303100, 87000, 2.0),
    "Exeter Cathedral": (292090, 92560, 20.0),
}


def mosaic(paths):
    srcs = [rasterio.open(p) for p in paths]
    arr, tr = merge(srcs, nodata=-3.4028234663852886e+38)
    for s in srcs:
        s.close()
    a = arr[0].astype("float32")
    a[a < -1000] = np.nan
    return a, tr


def main(terrain_dir, pc_path, out_dir):
    T, out = Path(terrain_dir), Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    print("mosaicking LIDAR...", flush=True)
    dsm, tr = mosaic(sorted(T.glob("lidar/dsm_*.tif")))
    # Ground: the EA DTM where we have it; elsewhere a ground proxy from the
    # surface model (minimum over a 25 m window — streets and gardens are
    # never further than that from anywhere in a town). Used for the eye
    # height and for telling trees from land, so a proxy is adequate.
    print("  ground proxy (25 m minimum filter)...", flush=True)
    proxy = minimum_filter(np.where(np.isnan(dsm), np.inf, dsm), size=25, mode="nearest")
    proxy[~np.isfinite(proxy)] = np.nan
    dtm_paths = sorted(T.glob("lidar/dtm_*.tif"))
    if dtm_paths:
        dtm_part, tr2 = mosaic(dtm_paths)
        dtm = np.full_like(dsm, np.nan)
        # place the partial DTM mosaic into the DSM grid
        r0 = int(round((tr.f - tr2.f) / tr.a)); c0 = int(round((tr2.c - tr.c) / tr.a))
        hh = min(dtm_part.shape[0], dsm.shape[0] - r0); ww = min(dtm_part.shape[1], dsm.shape[1] - c0)
        dtm[r0:r0+hh, c0:c0+ww] = dtm_part[:hh, :ww]
        real = np.isfinite(dtm).mean()
        print(f"  real DTM covers {real*100:.0f}% of grid; proxy fills the rest", flush=True)
        dtm = np.where(np.isnan(dtm), proxy, dtm)
    else:
        dtm = proxy
    dsm = np.where(np.isnan(dsm), dtm, dsm)
    dtm = np.where(np.isnan(dtm), dsm, dtm)
    masks = {}
    for k in ("building", "water", "woodland"):
        with rasterio.open(T / f"mask_{k}.tif") as r:
            m = r.read(1)
            # masks were built on the nominal grid; align by window if the mosaic is smaller
            win = rasterio.windows.from_bounds(*rasterio.transform.array_bounds(*dsm.shape, tr), r.transform)
            masks[k] = r.read(1, window=win, boundless=True, fill_value=0)
    print(f"  grid {dsm.shape} at {tr.a} m · building {masks['building'].mean()*100:.1f}%", flush=True)
    cls = classify(dsm, dtm, masks["building"], masks["water"], masks["woodland"])
    local = Surface(dsm, tr, cls=cls)
    ground = Surface(dtm, tr)

    with rasterio.open(T / "cop30_exeter_bng.tif") as r:
        distant = Surface(r.read(1), r.transform)

    # Nearest non-building cell lookup (indices of nearest open cell).
    print("computing nearest open cell map...", flush=True)
    _, idx = distance_transform_edt(masks["building"] == 1, return_indices=True)
    bld_lab, _ = label(masks["building"] == 1)

    pcs = pd.read_parquet(pc_path)
    rows, profiles = [], {}
    print(f"computing outlooks for {len(pcs):,} postcodes...", flush=True)
    for i, p in enumerate(pcs.itertuples()):
        r0, c0 = local.rc(np.array([p.e]), np.array([p.n]))
        r0, c0 = int(r0[0]), int(c0[0])
        if not (0 <= r0 < local.h and 0 <= c0 < local.w):
            continue
        rr, cc = int(idx[0, r0, c0]), int(idx[1, r0, c0])   # nearest open cell
        e, n = tr.c + (cc + 0.5) * tr.a, tr.f - (rr + 0.5) * tr.a
        zg = float(dtm[rr, cc])
        if not np.isfinite(zg):
            continue
        garden = outlook_metrics(local, distant, e, n, zg, 1.6, LOCAL_DIST, DISTANT_DIST)

        # Upstairs: flatten the owner's own building (the one containing the
        # centroid, or nearest within 20 m) and look from 5 m.
        own = bld_lab[r0, c0]
        if own == 0:
            sub = bld_lab[max(0, r0-20):r0+21, max(0, c0-20):c0+21]
            vals = sub[sub > 0]
            own = int(np.bincount(vals).argmax()) if vals.size else 0
        if own:
            ys, xs = np.where(bld_lab[max(0, r0-80):r0+81, max(0, c0-80):c0+81] == own)
            ys += max(0, r0-80); xs += max(0, c0-80)
            saved = local.z[ys, xs].copy()
            local.z[ys, xs] = dtm[ys, xs] + 0.3
        upstairs = outlook_metrics(local, distant, e, n, zg, 5.0, LOCAL_DIST, DISTANT_DIST)
        lm = {}
        for name, (le, ln, extra) in LANDMARKS.items():
            ok, dist = line_of_sight(distant, e, n, zg + 5.0, le, ln, extra,
                                     local=local, local_max_dist=LOCAL_DIST)
            lm[name] = bool(ok)
        if own:
            local.z[ys, xs] = saved

        rec = dict(postcode=p.postcode, e=round(e), n=round(n), ground_m=round(zg, 1),
                   own_building=bool(own))
        for k, v in garden.items():
            if not isinstance(v, np.ndarray):
                rec["g_" + k] = round(v, 4)
        for k, v in upstairs.items():
            if not isinstance(v, np.ndarray):
                rec["u_" + k] = round(v, 4)
        for name, ok in lm.items():
            rec["sees_" + name] = ok
        rows.append(rec)
        profiles[p.postcode] = dict(
            g_deg=np.round(garden["horizon_deg"], 1).tolist(),
            g_cls=garden["horizon_class"].tolist(),
            g_dist=np.round(garden["horizon_dist"]).astype(int).tolist(),
            u_deg=np.round(upstairs["horizon_deg"], 1).tolist(),
            u_cls=upstairs["horizon_class"].tolist(),
            u_dist=np.round(upstairs["horizon_dist"]).astype(int).tolist(),
        )
        if i % 400 == 0:
            print(f"  {i:,} done", flush=True)

    df = pd.DataFrame(rows)
    df.to_parquet(out / "views_postcode.parquet", index=False)
    with open(out / "views_profiles.json", "w") as fh:
        json.dump(profiles, fh, separators=(",", ":"))
    print(f"\n{len(df):,} postcodes computed -> {out}")
    print(df[["g_median_horizon_deg", "g_overlooked_share", "u_long_view_share",
              "u_longest_view_km", "u_water_share", "u_sea_share", "u_hills_share"]]
          .describe().round(3).to_string())
    print("\nlandmark visibility (upstairs), share of postcodes:")
    for name in LANDMARKS:
        print(f"  {name:22s} {df['sees_' + name].mean()*100:5.1f}%")


if __name__ == "__main__":
    main(*sys.argv[1:4])
