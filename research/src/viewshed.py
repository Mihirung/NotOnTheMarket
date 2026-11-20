"""Viewshed and horizon-profile engine for property outlooks.

Two passes per viewpoint, combined per compass bearing:

  LOCAL   1-2 m LIDAR surface model (buildings and trees included),
          out to ~1 km. Decides enclosure, overlooking, what blocks the
          garden, and the horizon in the near field.
  DISTANT 30 m terrain out to ~30 km, with earth-curvature and
          refraction correction, seeded with the local horizon so a
          hill only counts as visible if it clears the neighbour's roof.

For every bearing (1 degree steps) we record the horizon angle, what
defines it (building / tree / terrain / water / sky), how far the eye
can see, and which landmarks are in line of sight. From that we derive
the plain-English outlook a buyer actually asks about: long views,
water, hills, overlooked, sun.

Ray sampling uses nearest-cell lookup along each bearing; the running
maximum of the elevation angle along the ray gives visibility exactly
as in the classic R2 viewshed algorithm.
"""

import numpy as np
import rasterio
from rasterio import features

R_EARTH = 6_371_000.0
REFRACTION = 0.13          # standard atmospheric refraction coefficient
SKY, BUILDING, TREE, TERRAIN, WATER, HILL = 0, 1, 2, 3, 4, 5
CLASS_NAMES = {SKY: "open", BUILDING: "building", TREE: "trees",
               TERRAIN: "land", WATER: "water", HILL: "hills"}


class Surface:
    """A raster with a transform, plus optional class mask (uint8)."""

    def __init__(self, z, transform, cls=None, nodata_fill=-50.0):
        self.z = np.where(np.isfinite(z), z, nodata_fill).astype("float32")
        self.t = transform
        self.res = float(transform.a)
        self.x0, self.y0 = transform.c, transform.f   # top-left corner
        self.h, self.w = self.z.shape
        self.cls = cls

    def rc(self, e, n):
        col = np.floor((e - self.x0) / self.res).astype(np.int64)
        row = np.floor((self.y0 - n) / self.res).astype(np.int64)
        return row, col

    def inside(self, row, col):
        return (row >= 0) & (row < self.h) & (col >= 0) & (col < self.w)

    def sample(self, e, n, fill=-50.0):
        row, col = self.rc(e, n)
        ok = self.inside(row, col)
        out = np.full(e.shape, fill, dtype="float32")
        out[ok] = self.z[row[ok], col[ok]]
        c = None
        if self.cls is not None:
            c = np.zeros(e.shape, dtype="uint8")
            c[ok] = self.cls[row[ok], col[ok]]
        return out, c, ok

    def at(self, e, n):
        row, col = self.rc(np.asarray([e]), np.asarray([n]))
        if not self.inside(row, col)[0]:
            return np.nan
        return float(self.z[row[0], col[0]])


def bearings(step_deg=1.0):
    b = np.arange(0, 360, step_deg, dtype="float64")
    rad = np.radians(b)
    return b, np.sin(rad), np.cos(rad)        # east, north components


def cast(surface, e0, n0, z_eye, max_dist, step=None, curvature=False,
         seed_slope=None, bearing_step=1.0):
    """Cast rays on every bearing; return per-ray horizon information.

    Returns dict of arrays (n_bearings,): horizon_slope, horizon_dist,
    horizon_class, horizon_z, far_dist (furthest visible sample),
    plus per-ray booleans for water and hill visibility, and the full
    (n_bearings, n_steps) visibility/class grids for landmark tests.
    """
    step = step or surface.res
    b, dx, dy = bearings(bearing_step)
    d = np.arange(1, int(max_dist / step) + 1, dtype="float64") * step
    E = e0 + dx[:, None] * d[None, :]
    N = n0 + dy[:, None] * d[None, :]
    z, cls, ok = surface.sample(E, N)
    z = z.astype("float64")
    if curvature:
        z = z - (d[None, :] ** 2) / (2 * R_EARTH) * (1 - REFRACTION)
    slope = (z - z_eye) / d[None, :]
    slope[~ok] = -np.inf
    run = np.maximum.accumulate(slope, axis=1)
    prev = np.concatenate([np.full((slope.shape[0], 1),
                                   -np.inf if seed_slope is None else 0), run[:, :-1]], axis=1)
    if seed_slope is not None:
        prev = np.maximum(prev, seed_slope[:, None])
    visible = slope > prev
    visible &= ok
    # horizon = the sample with the maximum slope on each ray
    hz_i = np.argmax(np.where(ok, slope, -np.inf), axis=1)
    rows = np.arange(slope.shape[0])
    hz_slope = slope[rows, hz_i]
    hz_slope = np.where(seed_slope is not None, np.maximum(hz_slope, seed_slope if seed_slope is not None else -np.inf), hz_slope)
    hz_dist = d[hz_i]
    hz_cls = cls[rows, hz_i] if cls is not None else np.zeros(len(rows), dtype="uint8")
    hz_z = z[rows, hz_i]
    far_i = np.where(visible.any(axis=1), visible.shape[1] - 1 - np.argmax(visible[:, ::-1], axis=1), -1)
    far_dist = np.where(far_i >= 0, d[np.clip(far_i, 0, None)], 0.0)
    out = dict(bearing=b, horizon_slope=hz_slope, horizon_dist=hz_dist,
               horizon_class=hz_cls, horizon_z=hz_z, far_dist=far_dist,
               visible=visible, cls=cls, z=z, d=d, ok=ok)
    return out


def line_of_sight(surface, e0, n0, z_eye, e1, n1, z_target_extra=0.0,
                  curvature=True, local=None, local_max_dist=0.0):
    """Can the eye see a target point? Optionally check the near field
    against the local (high-resolution) surface first."""
    dist = float(np.hypot(e1 - e0, n1 - n0))
    if dist < 1:
        return True, 0.0
    step = surface.res
    d = np.arange(step, dist, step)
    ux, uy = (e1 - e0) / dist, (n1 - n0) / dist
    E, N = e0 + ux * d, n0 + uy * d
    z, _, ok = surface.sample(E, N)
    z = z.astype("float64")
    if curvature:
        z -= d ** 2 / (2 * R_EARTH) * (1 - REFRACTION)
    z_t = surface.at(e1, n1)
    if not np.isfinite(z_t):
        return False, dist
    z_t = z_t + z_target_extra - (dist ** 2 / (2 * R_EARTH) * (1 - REFRACTION) if curvature else 0)
    target_slope = (z_t - z_eye) / dist
    blocked = (z - z_eye) / d
    blocked[~ok] = -np.inf
    if local is not None and local_max_dist > 0:
        dl = np.arange(local.res, min(dist, local_max_dist), local.res)
        zl, _, okl = local.sample(e0 + ux * dl, n0 + uy * dl)
        bl = (zl.astype("float64") - z_eye) / dl
        bl[~okl] = -np.inf
        if bl.size and bl.max() >= target_slope:
            return False, dist
    return bool(blocked.max() < target_slope), dist


def rasterise(geoms, transform, shape, value=1):
    if len(geoms) == 0:
        return np.zeros(shape, dtype="uint8")
    return features.rasterize(((g, value) for g in geoms), out_shape=shape,
                              transform=transform, fill=0, dtype="uint8")


def classify(dsm, dtm, buildings, water, woodland):
    """Class raster at the local resolution: building > water > tree > land."""
    cls = np.full(dsm.shape, TERRAIN, dtype="uint8")
    ndsm = dsm - dtm
    tree = (ndsm > 2.5) & (buildings == 0)
    cls[tree | (woodland == 1)] = TREE
    cls[water == 1] = WATER
    cls[buildings == 1] = BUILDING
    return cls


def outlook_metrics(local, distant, e, n, z_ground, eye_height, local_dist,
                    distant_dist, hill_min_z=250.0, water_cls=WATER):
    """Full two-pass profile and derived outlook metrics for one viewpoint."""
    z_eye = z_ground + eye_height
    L = cast(local, e, n, z_eye, local_dist)
    D = cast(distant, e, n, z_eye, distant_dist, curvature=True,
             seed_slope=L["horizon_slope"])

    # Combined horizon per bearing: distant wins only if it rises above local.
    use_far = D["horizon_slope"] > L["horizon_slope"] + 1e-9
    hz_slope = np.where(use_far, D["horizon_slope"], L["horizon_slope"])
    hz_dist = np.where(use_far, D["horizon_dist"], L["horizon_dist"])
    hz_z = np.where(use_far, D["horizon_z"], L["horizon_z"])
    hz_cls = np.where(use_far, np.where(hz_z >= hill_min_z, HILL, TERRAIN),
                      L["horizon_class"])
    # A near horizon that is just flat ground at the ray's end is "open".
    at_edge = (~use_far) & (L["horizon_dist"] >= local_dist - local.res * 2)
    hz_cls = np.where(at_edge & (hz_cls == TERRAIN), SKY, hz_cls)
    hz_deg = np.degrees(np.arctan(hz_slope))

    far_dist = np.where(D["far_dist"] > 0, D["far_dist"], L["far_dist"])
    vis_water_local = (L["visible"] & (L["cls"] == water_cls)).any(axis=1)
    vis_sea = (D["visible"] & (D["z"] <= 0.5) & (D["ok"])).any(axis=1)
    vis_hill = (D["visible"] & (D["z"] >= hill_min_z)).any(axis=1)

    # Enclosure within 40 m by buildings (privacy / overlooked proxy).
    near = L["d"] <= 40
    near_bld = (L["cls"][:, near] == BUILDING) & ((L["z"][:, near] - z_eye) > 0.5)
    overlooked_share = near_bld.any(axis=1).mean()

    def sector_mean(lo, hi):
        b = L["bearing"]
        m = (b >= lo) & (b < hi)
        return float(hz_deg[m].mean())

    return dict(
        horizon_deg=hz_deg.astype("float32"),
        horizon_dist=hz_dist.astype("float32"),
        horizon_class=hz_cls.astype("uint8"),
        far_dist=far_dist.astype("float32"),
        median_horizon_deg=float(np.median(hz_deg)),
        open_share=float((hz_deg < 5).mean()),
        long_view_share=float((far_dist >= 2000).mean()),
        longest_view_km=float(far_dist.max() / 1000),
        water_share=float((vis_water_local | vis_sea).mean()),
        sea_share=float(vis_sea.mean()),
        hills_share=float(vis_hill.mean()),
        overlooked_share=float(overlooked_share),
        south_horizon_deg=sector_mean(150, 210),
        west_horizon_deg=sector_mean(240, 300),
        east_horizon_deg=sector_mean(60, 120),
    )
