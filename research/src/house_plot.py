"""The room around each house, from Ordnance Survey building outlines.

For every house of the national run (docs/08) this measures, along the
direction the house faces:

  back_wall_m   how far behind the address point the house's own outline ends
  rear_gap_m    open ground from the back wall to the next building behind
                (capped at 60 m: open country or a long garden)
  side_gap_l_m, side_gap_r_m
                open ground from each side wall to the next building (capped
                at 15 m); zero for a house joined on that side
  footprint_m2  the house's own share of its building outline: the outline's
                area divided by the address points standing on it (a pair of
                semis or a terrace is often one outline in OpenMap Local)
  n_on_outline  address points on the same outline

Rear gardens meet back to back, so the rear garden is taken as roughly half
the rear gap; permitted_development.py uses these to decide what could be
built without planning permission. Property boundaries themselves are not
in open map data, so these are estimates.

Writes research/outputs/national/plots/<cell>.parquet (h3 row key + measures).

Usage: python house_plot.py [cells...]     (default: every finished cell not yet measured)
"""
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

NAT = Path("research/outputs/national")
OSMAP = Path("research/data/osmap/cells")
REAR_MAX, SIDE_MAX = 60.0, 15.0


def ray_gap(pts, own_idx, bearing_deg, reach, bld, tree):
    """Distance along a ray from each point to where its own outline ends, and
    from there to the next building."""
    th = np.radians(bearing_deg)
    x, y = shapely.get_x(pts), shapely.get_y(pts)
    ends = shapely.points(x + reach * np.sin(th), y + reach * np.cos(th))
    lines = shapely.linestrings(np.stack([np.column_stack([x, y]), np.column_stack([shapely.get_x(ends), shapely.get_y(ends)])], 1))
    n = len(pts)
    wall = np.zeros(n)
    has = own_idx >= 0
    if has.any():                                    # where the ray leaves the house's own outline
        seg = shapely.intersection(lines[has], bld[own_idx[has]])
        far = shapely.get_coordinates(seg, return_index=True)
        if len(far[0]):
            d = np.hypot(far[0][:, 0] - x[has][far[1]], far[0][:, 1] - y[has][far[1]])
            mx = np.zeros(has.sum()); np.maximum.at(mx, far[1], d)
            wall[has] = mx
    gap = np.full(n, reach)
    li, bi = tree.query(lines, predicate="intersects")
    keep = bi != own_idx[li]
    li, bi = li[keep], bi[keep]
    if len(li):
        inter = shapely.intersection(lines[li], bld[bi])
        d = shapely.distance(pts[li], inter)
        np.minimum.at(gap, li, d)
    return wall, np.clip(gap - wall, 0, reach)


def measure(cell):
    c = cell.split("_")
    cid = int(c[0]) * 1000 + int(c[1])
    h = pd.read_parquet(NAT / "cells" / f"{cell}.parquet", columns=["x", "y", "h3", "front_bearing"])
    if not len(h):
        return pd.DataFrame()
    parts = [gpd.read_parquet(p).geometry.values for p in (OSMAP / cell).glob("Building_*.parquet")]
    bld = np.concatenate(parts) if parts else np.array([], dtype=object)
    pts = shapely.points(h.x.to_numpy() + 0.5, h.y.to_numpy() + 0.5)
    out = pd.DataFrame({"h3": h.h3.to_numpy().astype("int32")})
    if not len(bld):
        for k in ("back_wall_m", "rear_gap_m", "side_gap_l_m", "side_gap_r_m", "footprint_m2", "n_on_outline"):
            out[k] = np.nan
        return out
    tree = shapely.STRtree(bld)
    own = np.full(len(pts), -1)
    pi, bi = tree.query(pts, predicate="intersects")
    own[pi] = bi
    miss = np.nonzero(own < 0)[0]
    if len(miss):                                     # address points just outside their outline (snapped as the run did)
        mi, mb = tree.query_nearest(pts[miss], max_distance=3.0, return_distance=False)
        own[miss[mi]] = mb
    # every address position on each outline, flats and all, to share the outline's area fairly
    pos = pd.read_parquet("research/data/ew_positions.parquet", columns=["x", "y", "cell"],
                          filters=[("cell", "==", cid)])
    pp = shapely.points(pos.x.to_numpy() + 0.5, pos.y.to_numpy() + 0.5)
    _, pb = tree.query(pp, predicate="intersects")
    on = np.bincount(pb, minlength=len(bld))
    area = shapely.area(bld)
    fb = h.front_bearing.to_numpy(float)
    fb = np.where(np.isfinite(fb), fb, 0.0)
    wall, rear = ray_gap(pts, own, fb + 180, REAR_MAX, bld, tree)
    _, left = ray_gap(pts, own, fb - 90, SIDE_MAX, bld, tree)
    _, right = ray_gap(pts, own, fb + 90, SIDE_MAX, bld, tree)
    n_on = np.where(own >= 0, np.maximum(on[np.clip(own, 0, None)], 1), 0)
    out["back_wall_m"] = np.round(wall, 1).astype("float32")
    out["rear_gap_m"] = np.round(rear, 1).astype("float32")
    out["side_gap_l_m"] = np.round(left, 1).astype("float32")
    out["side_gap_r_m"] = np.round(right, 1).astype("float32")
    out["footprint_m2"] = np.where(own >= 0, area[np.clip(own, 0, None)] / np.maximum(n_on, 1), np.nan).astype("float32")
    out["n_on_outline"] = n_on.astype("int32")
    return out


def main(cells):
    (NAT / "plots").mkdir(exist_ok=True)
    if not cells:
        done = {p.stem for p in (NAT / "plots").glob("*.parquet")}
        cells = sorted(p.stem for p in (NAT / "cells").glob("*_*.parquet")
                       if not p.stem.endswith("_sight") and p.stem not in done)
    t0 = time.time()
    for k, cell in enumerate(cells):
        out = measure(cell)
        tmp = NAT / "plots" / f"{cell}.tmp"
        out.to_parquet(tmp, index=False); tmp.replace(NAT / "plots" / f"{cell}.parquet")
        if k % 50 == 0:
            print(f"  {k + 1} of {len(cells)} cells, {time.time() - t0:.0f}s", flush=True)
    print(f"{len(cells)} cells measured in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
