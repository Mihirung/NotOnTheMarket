"""House-level outlook engine.

One viewpoint per address point rather than per postcode. For each
house it works out:

  * the house itself: ground level, roof height, storeys, eye level at
    the highest habitable floor
  * the garden: the largest open, non-road, ground-level space beside
    the house, which way it lies from the house (its aspect), how much
    room it has
  * two outlooks, each a 240-ray horizon profile classified by what
    forms the skyline: from the upper windows (rays start where they
    leave the house's own footprint, so party walls block and facades
    do not) and from the middle of the garden
  * hours of direct sun in the garden at midsummer, the equinox and
    midwinter, from the horizon profile and the sun's path
  * line of sight from the upper windows to named landmarks, judged on
    the 1 m surface all the way when the landmark is in the city
  * for chosen houses, a layered panorama: the skyline of each distance
    band, so the view can be drawn

Near field: 1 m LIDAR surface (buildings and trees) to 1 km, with step
length growing with distance. Far field: 30 m terrain to 30 km with
curvature and refraction. Both in one running-maximum pass per ray.
"""

import numpy as np
from scipy.ndimage import distance_transform_edt

R_EARTH, REFRACTION = 6_371_000.0, 0.13
SKY, BUILDING, TREE, TERRAIN, WATER, HILL, TIDAL = 0, 1, 2, 3, 4, 5, 6
CLASS_NAMES = {SKY: "open", BUILDING: "buildings", TREE: "trees", TERRAIN: "land",
               WATER: "water", HILL: "hills", TIDAL: "sea or estuary"}

D_LOC = np.concatenate([np.arange(1, 150, 1.0), np.arange(150, 500, 2.0),
                        np.arange(500, 1000.1, 4.0)]).astype("float32")
D_FAR = np.concatenate([np.arange(1000, 3000, 30.0), np.arange(3000, 10000, 60.0),
                        np.arange(10000, 30001, 150.0)]).astype("float32")
D_ALL = np.concatenate([D_LOC, D_FAR])
N_LOC = len(D_LOC)
CURV = (D_ALL.astype("float64") ** 2 / (2 * R_EARTH) * (1 - REFRACTION)).astype("float32")
OWN_CAP = 14                       # max metres of own footprint a ray may pass through
PANO_EDGES = [0, 25, 80, 250, 800, 2500, 8000, 30001]


class City:
    """Rasters for one city. All arrays are read-only after construction."""

    def __init__(self, dsm, ground, cls, road, x0, y0, far_z, far_wb, far_x0, far_y0, far_res, lat):
        self.dsm, self.ground, self.cls, self.road = dsm, ground, cls, road
        self.x0, self.y0 = float(x0), float(y0)            # top-left corner, 1 m cells
        self.h, self.w = dsm.shape
        self.far_z, self.far_wb = far_z, far_wb
        self.fx0, self.fy0, self.fres = float(far_x0), float(far_y0), float(far_res)
        self.fh, self.fw = far_z.shape
        self.lat = lat

    def rc(self, e, n):
        return np.floor(self.y0 - n).astype(np.int64), np.floor(e - self.x0).astype(np.int64)

    def sample(self, E, N, local_part):
        """Height and class at points. Local raster where inside it, far raster elsewhere."""
        fr = np.floor((self.fy0 - N) / self.fres).astype(np.int32)
        fc = np.floor((E - self.fx0) / self.fres).astype(np.int32)
        ok = (fr >= 0) & (fr < self.fh) & (fc >= 0) & (fc < self.fw)
        np.clip(fr, 0, self.fh - 1, out=fr); np.clip(fc, 0, self.fw - 1, out=fc)
        z = self.far_z[fr, fc]
        wb = self.far_wb[fr, fc]
        cls = np.where(wb == 1, TIDAL, np.where(wb >= 2, WATER, TERRAIN)).astype("uint8")
        if local_part:
            r = np.floor(self.y0 - N).astype(np.int32); c = np.floor(E - self.x0).astype(np.int32)
            ins = (r >= 0) & (r < self.h) & (c >= 0) & (c < self.w)
            np.clip(r, 0, self.h - 1, out=r); np.clip(c, 0, self.w - 1, out=c)
            z = np.where(ins, self.dsm[r, c], z)
            cls = np.where(ins, self.cls[r, c], cls)
            ok = ok | ins
        return z, cls, ok


def _dirs(step_deg):
    b = np.arange(0, 360, step_deg)
    return b, np.sin(np.radians(b)).astype("float32"), np.cos(np.radians(b)).astype("float32")


def cast(city, e, n, z_eye, skip_own, step_deg=1.5, own_fixed=None):
    """Batch ray cast. e, n, z_eye: (B,). Returns per-ray arrays (B, rays)
    and the per-sample slope/visibility/class needed for panoramas."""
    b, dx, dy = _dirs(step_deg)
    B, R = len(e), len(b)
    e32, n32 = e.astype("float64"), n.astype("float64")
    parts = []
    for local_part, D in ((True, D_LOC), (False, D_FAR)):
        E = e32[:, None, None] + dx[None, :, None].astype("float64") * D[None, None, :]
        N = n32[:, None, None] + dy[None, :, None].astype("float64") * D[None, None, :]
        parts.append(city.sample(E, N, local_part))
        del E, N
    z = np.concatenate([parts[0][0], parts[1][0]], axis=2)
    cls = np.concatenate([parts[0][1], parts[1][1]], axis=2)
    ok = np.concatenate([parts[0][2], parts[1][2]], axis=2)
    del parts
    rel = z - CURV[None, None, :] - z_eye[:, None, None].astype("float32")
    slope = rel / D_ALL[None, None, :]
    slope[~ok] = -np.inf
    if skip_own:
        # Rays leave the house where its own footprint ends (plus a 2 m eaves
        # margin), but never ignore more than OWN_CAP metres: beyond that a
        # merged terrace polygon is a neighbour, and neighbours block.
        isb = cls[:, :, :OWN_CAP] == BUILDING
        first_open = np.where(isb.all(axis=2), OWN_CAP, np.argmax(~isb, axis=2))
        skip = np.minimum(first_open + 2, OWN_CAP)
        if own_fixed is not None:
            skip = np.where(own_fixed[:, None], 6, skip)
        slope[:, :, :OWN_CAP][np.arange(OWN_CAP)[None, None, :] < skip[:, :, None]] = -np.inf
    run = np.maximum.accumulate(slope, axis=2)
    prev = np.empty_like(run); prev[:, :, 0] = -np.inf; prev[:, :, 1:] = run[:, :, :-1]
    vis = (slope > prev) & ok
    del prev
    hz_i = np.argmax(slope, axis=2)
    bi, ri = np.ogrid[:B, :R]
    hz_slope = slope[bi, ri, hz_i]
    hz_deg = np.degrees(np.arctan(hz_slope))
    hz_d = D_ALL[hz_i]
    hz_cls = cls[bi, ri, hz_i]
    hz_rel = rel[bi, ri, hz_i]
    hz_cls = np.where((hz_i >= N_LOC) & (hz_rel >= 75) & (hz_d >= 3000), HILL, hz_cls)
    hz_cls = np.where((hz_cls == TERRAIN) & (hz_deg < 1.0), SKY, hz_cls)
    far = np.where(vis, D_ALL[None, None, :], 0).max(axis=2)
    near = D_ALL[None, None, :N_LOC] <= 40
    out = dict(
        bearing=b, hz_deg=hz_deg.astype("float32"), hz_cls=hz_cls.astype("uint8"),
        hz_dist=hz_d.astype("float32"), far=far.astype("float32"),
        water=(vis & ((cls == WATER) | (cls == TIDAL))).any(axis=2),
        tidal=(vis & (cls == TIDAL)).any(axis=2),
        hills=(vis & (rel >= 75) & (D_ALL[None, None, :] >= 3000)).any(axis=2),
        near_bld=((cls[:, :, :N_LOC] == BUILDING) & near & (rel[:, :, :N_LOC] > 0.5)
                  & np.isfinite(slope[:, :, :N_LOC])).any(axis=2),
    )
    return out, (slope, vis, cls)


def metrics(o, prefix):
    """Scalar outlook metrics per viewpoint from a cast() result."""
    b, hz, far = o["bearing"], o["hz_deg"], o["far"]
    sec = lambda lo, hi: hz[:, (b >= lo) & (b < hi)].mean(axis=1)
    lf = np.log10(np.maximum(far, 1.0))
    k = int(round(90 / (b[1] - b[0])))                          # rays in a 90 degree window
    ext = np.concatenate([lf, lf[:, :k]], axis=1)
    cs = np.cumsum(np.concatenate([np.zeros((len(lf), 1)), ext], axis=1), axis=1)
    win = (cs[:, k:k + len(b)] - cs[:, :len(b)]) / k            # mean over [i, i+k)
    best = np.argmax(win, axis=1)
    m = {
        "horizon": np.median(hz, axis=1), "open": (hz < 5).mean(axis=1),
        "long": (far >= 2000).mean(axis=1), "long5": (far >= 5000).mean(axis=1),
        "longest_km": far.max(axis=1) / 1000, "water": o["water"].mean(axis=1),
        "tidal": o["tidal"].mean(axis=1), "hills": o["hills"].mean(axis=1),
        "overlooked": o["near_bld"].mean(axis=1),
        "hz_s": sec(135, 225), "hz_w": sec(225, 315), "hz_e": sec(45, 135),
        "hz_n": hz[:, (b >= 315) | (b < 45)].mean(axis=1),
        "best_bearing": (b[best] + 45) % 360,
        "best_reach_km": 10 ** win[np.arange(len(best)), best] / 1000,
    }
    return {f"{prefix}_{k_}": v.astype("float32") for k_, v in m.items()}


# ---------------------------------------------------------------- sun
def sun_path(lat_deg, day_of_year, step_min=10):
    """Solar time (h), azimuth (deg from north) and elevation (deg) through a day."""
    t = np.arange(3.0, 21.01, step_min / 60.0)
    phi = np.radians(lat_deg)
    dec = np.radians(23.44) * np.sin(2 * np.pi * (284 + day_of_year) / 365.0)
    H = np.radians(15.0 * (t - 12.0))
    el = np.arcsin(np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.cos(H))
    az = np.degrees(np.arctan2(np.sin(H), np.cos(H) * np.sin(phi) - np.tan(dec) * np.cos(phi))) + 180.0
    return t, az % 360, np.degrees(el)


SUN_DAYS = {"jun": 172, "equinox": 80, "dec": 355}


def sun_hours(hz_deg, bearing, lat_deg, step_min=10):
    """Hours of direct sun at a viewpoint, from its horizon profile."""
    out = {}
    stepb = bearing[1] - bearing[0]
    for name, doy in SUN_DAYS.items():
        t, az, el = sun_path(lat_deg, doy, step_min)
        idx = (np.round(az / stepb).astype(int)) % len(bearing)
        lit = (el[None, :] > 0.5) & (el[None, :] > hz_deg[:, idx])
        out[f"sun_{name}"] = lit.sum(axis=1) * step_min / 60.0
        if name == "jun":
            out["sun_evening_jun"] = (lit & (t[None, :] >= 17.0)).sum(axis=1) * step_min / 60.0
            out["sun_morning_jun"] = (lit & (t[None, :] < 10.0)).sum(axis=1) * step_min / 60.0
    return {k: v.astype("float32") for k, v in out.items()}


# ---------------------------------------------------------------- landmarks
def landmark_top(city, e, n, kind, extra):
    """Height of the thing to look at: the top of a structure, or a summit."""
    r, c = city.rc(np.array([e]), np.array([n])); r, c = int(r[0]), int(c[0])
    if kind == "tower" and 30 <= r < city.h - 30 and 30 <= c < city.w - 30:
        return float(city.dsm[r - 30:r + 31, c - 30:c + 31].max())
    fr = int((city.fy0 - n) / city.fres); fc = int((e - city.fx0) / city.fres)
    return float(city.far_z[max(fr - 3, 0):fr + 4, max(fc - 3, 0):fc + 4].max()) + extra


def sees(city, e, n, z_eye, te, tn, tz, K=700):
    """Can each viewpoint see the target point? Judged on the 1 m surface
    wherever the sight-line is inside the city, on 30 m terrain beyond."""
    dist = np.hypot(te - e, tn - n)
    ux, uy = (te - e) / np.maximum(dist, 1), (tn - n) / np.maximum(dist, 1)
    span = np.maximum(dist - 60.0 - OWN_CAP, 1.0)
    d = OWN_CAP + span[:, None] * np.linspace(0, 1, K)[None, :]
    z, _, ok = city.sample(e[:, None] + ux[:, None] * d, n[:, None] + uy[:, None] * d, True)
    curv = d ** 2 / (2 * R_EARTH) * (1 - REFRACTION)
    path = np.where(ok, (z - curv - z_eye[:, None]) / d, -np.inf).max(axis=1)
    target = (tz - dist ** 2 / (2 * R_EARTH) * (1 - REFRACTION) - z_eye) / np.maximum(dist, 1)
    return (path < target) | (dist < 150)


def near_clear(slope, bearing, e, n, z_eye, te, tn, tz):
    """Is the target clear of everything in the first few metres beyond the
    house's own walls (a hedge, a neighbour's gable)? sees() starts its
    sight-line OWN_CAP metres out so that the house cannot block itself; this
    closes the gap using the ray already cast in the target's direction."""
    dist = np.hypot(te - e, tn - n)
    target = (tz - dist ** 2 / (2 * R_EARTH) * (1 - REFRACTION) - z_eye) / np.maximum(dist, 1)
    step = bearing[1] - bearing[0]
    j = np.round((np.degrees(np.arctan2(te - e, tn - n)) % 360) / step).astype(int) % len(bearing)
    near = slope[np.arange(len(e)), j, :OWN_CAP].max(axis=1)
    return (near < target) | (dist < 150)


# ---------------------------------------------------------------- per-house geometry
def house_geometry(city, e, n, bld):
    """Ground level, roof height, eye level and garden for one address point."""
    r, c = int(np.floor(city.y0 - n)), int(np.floor(e - city.x0))
    h = 20
    if not (h <= r < city.h - h and h <= c < city.w - h):
        return None
    sl = (slice(r - h, r + h + 1), slice(c - h, c + h + 1))
    b = bld[sl]; z = city.dsm[sl]; g = city.ground[sl]; road = city.road[sl]
    yy, xx = np.mgrid[-h:h + 1, -h:h + 1]
    rad = np.hypot(yy, xx)
    on_building = bool(b[h, h])
    if not on_building:                               # snap to a building within 3 m
        near = b & (rad <= 3)
        if not near.any():
            return None
    ground_open = (~b) & ((z - g) < 1.5)
    cand = ground_open & (rad <= 12)
    if cand.any():
        dd = rad[cand]; zz = z[cand]
        ground = float(np.median(zz[dd <= np.quantile(dd, 0.3)]))
    else:
        ground = float(g[h, h])
    roof = z[b & (rad <= 4)]
    height = float(np.percentile(roof, 90) - ground) if roof.size else 0.0
    if height < 2.2:
        return None
    storeys = 1 if height < 5.0 else 2 if height < 8.5 else 3 if height < 11.5 else 4
    eye_up = ground + (1.6 if storeys == 1 else 4.3 if storeys == 2 else 7.0 if storeys == 3
                       else min(height - 1.5, 12.0))
    # Garden: open, ground-level, not road, 3-15 m from the point; prefer room
    # (distance from any building) and nearness; must not lie across a road.
    clear = distance_transform_edt(~b)
    ok = ground_open & (~road) & (rad >= 3) & (rad <= 15)
    garden = None
    for _ in range(3):
        if not ok.any():
            break
        score = np.where(ok, clear - 0.35 * rad, -1e9)
        k = int(np.argmax(score)); gy, gx = divmod(k, 2 * h + 1)
        t = np.linspace(0.15, 1, 10)
        py = np.round(h + (gy - h) * t).astype(int); px = np.round(h + (gx - h) * t).astype(int)
        if road[py, px].any():                        # across the street: rule out that side
            ang = np.arctan2(xx, -yy); a0 = np.arctan2(gx - h, -(gy - h))
            ok &= np.abs(np.angle(np.exp(1j * (ang - a0)))) > np.radians(60)
            continue
        garden = (gy, gx, float(clear[gy, gx]))
        break
    out = dict(ground=ground, height=height, storeys=storeys, eye_up=eye_up,
               on_building=on_building, plot_open=int((ground_open & ~road & (rad <= 12)).sum()))
    if garden:
        gy, gx, cl = garden
        out.update(has_garden=True, g_e=city.x0 + (c - h + gx) + 0.5, g_n=city.y0 - (r - h + gy) - 0.5,
                   g_z=float(z[gy, gx]), garden_clear=cl,
                   garden_bearing=float(np.degrees(np.arctan2(gx - h, -(gy - h))) % 360))
    else:
        out.update(has_garden=False, g_e=np.nan, g_n=np.nan, g_z=np.nan, garden_clear=0.0,
                   garden_bearing=np.nan)
    return out


# ---------------------------------------------------------------- panorama
def panorama(city, e, n, z_eye, skip_own, own_fixed=False, step_deg=1.5):
    """Layered skyline for drawing: per bearing, the highest angle reached in
    each distance band and what it is, plus the visible water's angle range."""
    o, (slope, vis, cls) = cast(city, np.array([e]), np.array([n]), np.array([z_eye]),
                                skip_own, step_deg, np.array([own_fixed]) if skip_own else None)
    slope, vis, cls = slope[0], vis[0], cls[0]
    ang = np.degrees(np.arctan(slope))
    bands, classes = [], []
    for lo, hi in zip(PANO_EDGES[:-1], PANO_EDGES[1:]):
        m = (D_ALL >= max(lo, 1)) & (D_ALL < hi)
        a = np.where(np.isfinite(ang[:, m]), ang[:, m], -90.0)
        i = np.argmax(a, axis=1)
        bands.append(np.round(np.clip(a[np.arange(len(i)), i], -30, 60) * 10).astype(int).tolist())
        classes.append(cls[:, m][np.arange(len(i)), i].astype(int).tolist())
    wat = vis & ((cls == WATER) | (cls == TIDAL))
    wang = np.where(wat, ang, np.nan)
    with np.errstate(all="ignore"):
        wlo = np.nanmin(wang, axis=1); whi = np.nanmax(wang, axis=1)
    water = [[int(round(a * 10)), int(round(b * 10))] if np.isfinite(a) else None
             for a, b in zip(wlo, whi)]
    return dict(step=step_deg, edges=PANO_EDGES, bands=bands, cls=classes, water=water,
                hz=np.round(o["hz_deg"][0] * 10).astype(int).tolist(),
                far=np.round(o["far"][0]).astype(int).tolist())
