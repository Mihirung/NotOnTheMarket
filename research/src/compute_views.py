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
from scipy.ndimage import distance_transform_edt, label, minimum_filter

sys.path.insert(0, str(Path(__file__).parent))
from viewshed import (BUILDING, Surface, classify, line_of_sight,  # noqa: E402
                      outlook_metrics)

LOCAL_DIST, DISTANT_DIST = 1000, 30000
HILL_MIN_Z = 180.0   # Haldon ridge ~200-250 m, Woodbury Common ~180 m, Dartmoor higher
LANDMARKS = {  # BNG eastings/northings, height added above the surface
    "Exe estuary":      (297300, 86800, 0.5),
    "the sea at Exmouth": (300200, 80200, 0.5),
    "Haldon Hills":     (287550, 86150, 2.0),
    "Dartmoor (Haytor)": (275750, 77050, 2.0),
    "Woodbury Common":  (303100, 87000, 2.0),
    "Exeter Cathedral": (292090, 92560, 20.0),
}


def mosaic(paths):
    """Place aligned tiles into one grid by their bounds. (rasterio.merge
    mishandles the EA tiles' float32 nodata and silently returns zeros.)"""
    metas = []
    for p in paths:
        with rasterio.open(p) as r:
            metas.append((p, r.transform, r.width, r.height))
    res = metas[0][1].a
    west = min(m[1].c for m in metas); north = max(m[1].f for m in metas)
    east = max(m[1].c + m[2] * res for m in metas)
    south = min(m[1].f - m[3] * res for m in metas)
    H, W = int(round((north - south) / res)), int(round((east - west) / res))
    out = np.full((H, W), np.nan, dtype="float32")
    for p, t, w, h in metas:
        with rasterio.open(p) as r:
            a = r.read(1).astype("float32")
        a[a < -1000] = np.nan
        r0 = int(round((north - t.f) / res)); c0 = int(round((t.c - west) / res))
        out[r0:r0 + h, c0:c0 + w] = a
    from rasterio.transform import from_origin
    return out, from_origin(west, north, res, res)


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
        del dtm_part
    else:
        dtm = proxy
    del proxy
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

    bmask = masks["building"] == 1
    del masks, cls
    # Local helpers: the grid is 252M cells, so nearest-open-cell and
    # building labelling are done in a window round each postcode rather
    # than once for the whole city (a full distance transform needs ~4 GB).
    def nearest_open(r0, c0, half=25):
        """The middle of the nearest open space: within 25 m of the postcode
        centre, the ground-level cell (not building, not under canopy)
        furthest from any building — a garden or street centre, not the
        pavement against a wall."""
        for h in (half, half * 3, half * 8):
            r1, r2 = max(0, r0 - h), min(local.h, r0 + h + 1)
            c1, c2 = max(0, c0 - h), min(local.w, c0 + h + 1)
            b = bmask[r1:r2, c1:c2]
            ground = (~b) & ((local.z[r1:r2, c1:c2] - dtm[r1:r2, c1:c2]) < 1.0)
            if ground.any():
                dist = distance_transform_edt(~b)          # metres from a building
                score = np.where(ground, dist, -1.0)
                # prefer open space, but not so far that it is a different street
                near = (np.add.outer((np.arange(r1, r2) - r0) ** 2,
                                     (np.arange(c1, c2) - c0) ** 2) <= h * h)
                score = np.where(near, score, -1.0)
                k = np.argmax(score)
                if score.flat[k] >= 0:
                    return int(r1 + k // b.shape[1]), int(c1 + k % b.shape[1])
        return r0, c0

    def own_building(r0, c0, half=80):
        r1, r2 = max(0, r0 - half), min(local.h, r0 + half + 1)
        c1, c2 = max(0, c0 - half), min(local.w, c0 + half + 1)
        lab, _ = label(bmask[r1:r2, c1:c2])
        own = lab[r0 - r1, c0 - c1]
        if own == 0:   # nearest labelled building within 20 m
            win = lab[max(0, r0-r1-20):r0-r1+21, max(0, c0-c1-20):c0-c1+21]
            vals = win[win > 0]
            own = int(np.bincount(vals).argmax()) if vals.size else 0
        if own == 0:
            return None
        ys, xs = np.nonzero(lab == own)
        return ys + r1, xs + c1

    pcs = pd.read_parquet(pc_path)
    rows, profiles = [], {}
    print(f"computing outlooks for {len(pcs):,} postcodes...", flush=True)
    for i, p in enumerate(pcs.itertuples()):
        r0, c0 = local.rc(np.array([p.e]), np.array([p.n]))
        r0, c0 = int(r0[0]), int(c0[0])
        if not (0 <= r0 < local.h and 0 <= c0 < local.w):
            continue
        rr, cc = nearest_open(r0, c0)
        e, n = tr.c + (cc + 0.5) * tr.a, tr.f - (rr + 0.5) * tr.a
        zg = float(dtm[rr, cc])
        if not np.isfinite(zg):
            continue
        garden = outlook_metrics(local, distant, e, n, zg, 1.6, LOCAL_DIST, DISTANT_DIST,
                                 hill_min_z=HILL_MIN_Z)

        # Upstairs: flatten the owner's own building (the one containing the
        # centroid, or nearest within 20 m) and look from 5 m.
        own = own_building(r0, c0)
        if own is not None:
            ys, xs = own
            saved = local.z[ys, xs].copy()
            local.z[ys, xs] = dtm[ys, xs] + 0.3
        upstairs = outlook_metrics(local, distant, e, n, zg, 5.0, LOCAL_DIST, DISTANT_DIST,
                                   hill_min_z=HILL_MIN_Z)
        lm = {}
        for name, (le, ln, extra) in LANDMARKS.items():
            ok, dist = line_of_sight(distant, e, n, zg + 5.0, le, ln, extra,
                                     local=local, local_max_dist=LOCAL_DIST)
            lm[name] = bool(ok)
        if own is not None:
            local.z[ys, xs] = saved

        rec = dict(postcode=p.postcode, e=round(e), n=round(n), ground_m=round(zg, 1),
                   own_building=own is not None)
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
