"""Compiled version of the house-level view engine in views2.py.

The city runs used numpy arrays of every sample on every ray, which costs
about a tenth of a second per house. This walks each ray once in compiled
code and keeps only what the measures and drawings need, about twenty
times faster, so every house in England and Wales can be done.

It reproduces views2.cast() sample for sample: the same distances, the
same 1 m surface to 1 km and 30 m terrain beyond, the same curvature and
refraction, the same rules for what is visible and what forms the
skyline. check_fastviews.py compares the two on real houses.

  cast(city, e, n, z)        all-round view: per-ray skyline, reach, water,
                             hills, near buildings, and the drawing bands
  skyline(city, e, n, z)     per-ray skyline angle only (for window sun)
  sightlines(...)            can each viewpoint see each of its landmarks
"""
import math

import numba as nb
import numpy as np

import views2 as V

D_ALL = V.D_ALL.astype(np.float32)
CURV = V.CURV.astype(np.float32)
N_LOC = V.N_LOC
EDGES = np.array(V.PANO_EDGES, dtype=np.float32)
BAND = (np.searchsorted(EDGES, D_ALL, side="right") - 1).astype(np.int8)   # distance band of each sample
N_BANDS = len(EDGES) - 1
N_CLS_BANDS = 4
BUILDING, TERRAIN, WATER, HILL, TIDAL, SKY = V.BUILDING, V.TERRAIN, V.WATER, V.HILL, V.TIDAL, V.SKY


@nb.njit(cache=True, nogil=True)
def _sample(dsm, cls, x0, y0, far_z, far_wb, fx0, fy0, fres, E, N, local):
    """Height, class and validity at one point, as City.sample() does."""
    FH, FW = far_z.shape
    fr = int(math.floor((fy0 - N) / fres)); fc = int(math.floor((E - fx0) / fres))
    ok = 0 <= fr < FH and 0 <= fc < FW
    fr = min(max(fr, 0), FH - 1); fc = min(max(fc, 0), FW - 1)
    z = far_z[fr, fc]; wb = far_wb[fr, fc]
    c = TIDAL if wb == 1 else (WATER if wb >= 2 else TERRAIN)
    if local:
        H, W = dsm.shape
        r = int(math.floor(y0 - N)); q = int(math.floor(E - x0))
        if 0 <= r < H and 0 <= q < W:
            z = dsm[r, q]; c = cls[r, q]; ok = True
    return z, c, ok


@nb.njit(cache=True, nogil=True, boundscheck=False)
def _cast(dsm, cls, x0, y0, far_z, far_wb, fx0, fy0, fres, e, n, zeye, sx, sy, D, CU, n_loc, band, n_bands, n_cb,
          hz_slope, hz_cls, hz_d, far, flags, b_slope, b_cls, w_lo, w_hi, full):
    # Ray by ray, and along each ray step by step for every house in the batch
    # at once: neighbouring houses read neighbouring parts of the surface, so
    # what one house's ray loads is still in the cache for the next. With
    # full=False only the skyline angle is kept (for the sun on windows).
    B = e.shape[0]; R = sx.shape[0]; K = D.shape[0]
    H, W = dsm.shape; FH, FW = far_z.shape
    lx = e - x0; ly = y0 - n                      # position in the 1 m grid, columns and rows
    fxl = (e - fx0) / fres; fyl = (fy0 - n) / fres # position in the 30 m grid
    run = np.empty(B); best = np.empty(B); bk = np.empty(B, np.int32); bc = np.empty(B, np.uint8)
    brel = np.empty(B); fv = np.empty(B, np.float32); f = np.empty(B, np.uint8); lo = np.empty(B); hi = np.empty(B)
    bs = np.empty((B, n_bands)); bcl = np.zeros((B, n_cb), np.uint8)
    for r in range(R):
        for i in range(B):
            run[i] = -np.inf; best[i] = -np.inf; bk[i] = 0; bc[i] = 0; brel[i] = 0.0
            fv[i] = 0.0; f[i] = 0; lo[i] = np.inf; hi[i] = -np.inf
        for k in range(K):
            d = D[k]; cu = CU[k]; bnd = band[k]
            first = k == 0 or band[k - 1] != bnd
            ox = sx[r] * d; oy = sy[r] * d
            local = k < n_loc
            fox = ox / fres; foy = oy / fres
            for i in range(B):
                ok = False; z = np.float32(0.0); c = np.uint8(TERRAIN)
                if local:
                    yy = ly[i] - oy; xx = lx[i] + ox
                    if yy >= 0.0 and xx >= 0.0 and yy < H and xx < W:
                        z = dsm[int(yy), int(xx)]; c = cls[int(yy), int(xx)]; ok = True
                if not ok:
                    fr = int(math.floor(fyl[i] - foy)); fc = int(math.floor(fxl[i] + fox))
                    ok = 0 <= fr < FH and 0 <= fc < FW
                    fr = min(max(fr, 0), FH - 1); fc = min(max(fc, 0), FW - 1)
                    z = far_z[fr, fc]; wb = far_wb[fr, fc]
                    c = np.uint8(TIDAL) if wb == 1 else (np.uint8(WATER) if wb >= 2 else np.uint8(TERRAIN))
                rel = z - cu - zeye[i]
                if ok:
                    s = rel / d
                    if s > best[i]:
                        best[i] = s; bk[i] = k; bc[i] = c; brel[i] = rel
                    if full:
                        if s > run[i]:
                            run[i] = s
                            fv[i] = d
                            if c == WATER or c == TIDAL:
                                f[i] |= 1
                                if s < lo[i]:
                                    lo[i] = s
                                if s > hi[i]:
                                    hi[i] = s
                            if c == TIDAL:
                                f[i] |= 2
                            if rel >= 75.0 and d >= 3000.0:
                                f[i] |= 4
                        if local and c == BUILDING and d <= 40.0 and rel > 0.5:
                            f[i] |= 8
                        if first or s > bs[i, bnd]:
                            bs[i, bnd] = s
                            if bnd < n_cb:
                                bcl[i, bnd] = c
                elif full and first:
                    bs[i, bnd] = -10.0
                    if bnd < n_cb:
                        bcl[i, bnd] = c
                elif full and -10.0 > bs[i, bnd]:
                    bs[i, bnd] = -10.0
                    if bnd < n_cb:
                        bcl[i, bnd] = c
        for i in range(B):
            hz_slope[i, r] = best[i]
            if not full:
                continue
            if best[i] == -np.inf:                    # nothing valid on the ray: argmax is the first sample
                bk[i] = 0
                yy = ly[i] - sy[r] * D[0]; xx = lx[i] + sx[r] * D[0]
                if yy >= 0.0 and xx >= 0.0 and yy < H and xx < W:
                    bc[i] = cls[int(yy), int(xx)]; brel[i] = dsm[int(yy), int(xx)] - CU[0] - zeye[i]
                else:
                    fr = min(max(int(math.floor(fyl[i] - sy[r] * D[0] / fres)), 0), FH - 1)
                    fc = min(max(int(math.floor(fxl[i] + sx[r] * D[0] / fres)), 0), FW - 1)
                    wb = far_wb[fr, fc]
                    bc[i] = TIDAL if wb == 1 else (WATER if wb >= 2 else TERRAIN)
                    brel[i] = far_z[fr, fc] - CU[0] - zeye[i]
            hc = bc[i]
            hd = math.degrees(math.atan(best[i])) if best[i] > -np.inf else -90.0
            if bk[i] >= n_loc and brel[i] >= 75.0 and D[bk[i]] >= 3000.0:
                hc = HILL
            if hc == TERRAIN and hd < 1.0:
                hc = SKY
            hz_cls[i, r] = hc; hz_d[i, r] = D[bk[i]]; far[i, r] = fv[i]; flags[i, r] = f[i]
            w_lo[i, r] = lo[i]; w_hi[i, r] = hi[i]
            for q in range(n_bands):
                b_slope[i, r, q] = bs[i, q]
            for q in range(n_cb):
                b_cls[i, r, q] = bcl[i, q]


@nb.njit(cache=True, nogil=True)
def _sightlines(dsm, cls, x0, y0, far_z, far_wb, fx0, fy0, fres, pe, pn, pz, te, tn, tz, K, start, reach, out):
    """One sight-line per (viewpoint, target) pair, as views2.sees() and
    near_clear() together: K samples evenly from `start` to 60 m short of the
    target, plus every metre out to `reach` in the target's exact direction."""
    Rk = (1.0 - 0.13) / (2.0 * 6_371_000.0)
    for j in range(pe.shape[0]):
        dx = te[j] - pe[j]; dy = tn[j] - pn[j]
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 150.0:
            out[j] = True
            continue
        ux = dx / dist; uy = dy / dist
        target = (tz[j] - dist * dist * Rk - pz[j]) / dist
        span = max(dist - 60.0 - start, 1.0)
        blocked = False
        for k in range(K):
            d = start + span * k / (K - 1)
            z, c, ok = _sample(dsm, cls, x0, y0, far_z, far_wb, fx0, fy0, fres, pe[j] + ux * d, pn[j] + uy * d, True)
            if ok and (z - d * d * Rk - pz[j]) / d >= target:
                blocked = True
                break
        if not blocked:
            d = 1.0
            while d <= reach and d < dist - 60.0:
                z, c, ok = _sample(dsm, cls, x0, y0, far_z, far_wb, fx0, fy0, fres, pe[j] + ux * d, pn[j] + uy * d, True)
                if ok and (z - d * d * Rk - pz[j]) / d >= target:
                    blocked = True
                    break
                d += 1.0
        out[j] = not blocked


def _args(city):
    return (city.dsm, city.cls, city.x0, city.y0, city.far_z, city.far_wb, city.fx0, city.fy0, city.fres)


def _dirs(step_deg):
    b = np.arange(0, 360, step_deg)
    # float32 directions widened to float64, exactly as views2 does, so every sample lands in the same cell
    return b, np.sin(np.radians(b)).astype(np.float32).astype(np.float64), np.cos(np.radians(b)).astype(np.float32).astype(np.float64)


def cast(city, e, n, z, step_deg=1.5):
    """Same outputs as views2.cast(...)[0], plus the drawing bands that
    views2.bands_from_cast() makes, without keeping the samples."""
    b, sx, sy = _dirs(step_deg)
    B, R = len(e), len(b)
    hz_slope = np.empty((B, R), np.float64); hz_cls = np.empty((B, R), np.uint8)
    hz_d = np.empty((B, R), np.float32); far = np.empty((B, R), np.float32); flags = np.empty((B, R), np.uint8)
    b_slope = np.empty((B, R, N_BANDS), np.float64); b_cls = np.zeros((B, R, N_CLS_BANDS), np.uint8)
    w_lo = np.empty((B, R), np.float64); w_hi = np.empty((B, R), np.float64)
    _cast(*_args(city), np.ascontiguousarray(e, np.float64), np.ascontiguousarray(n, np.float64),
          np.ascontiguousarray(z, np.float32), sx, sy, D_ALL, CURV, N_LOC, BAND, N_BANDS, N_CLS_BANDS,
          hz_slope, hz_cls, hz_d, far, flags, b_slope, b_cls, w_lo, w_hi, True)
    hz_deg = np.degrees(np.arctan(hz_slope)).astype(np.float32)
    out = dict(bearing=b, hz_deg=hz_deg, hz_cls=hz_cls, hz_dist=hz_d, far=far,
               water=(flags & 1) > 0, tidal=(flags & 2) > 0, hills=(flags & 4) > 0, near_bld=(flags & 8) > 0)
    ang = np.degrees(np.arctan(b_slope))                                      # (B, R, bands)
    any_w = np.isfinite(w_lo)
    bands = dict(
        a=np.moveaxis(V.encode_angles(ang), 2, 1),                            # (B, 7, R)
        c=np.moveaxis(b_cls, 2, 1),                                           # (B, 4, R)
        w=np.stack([np.where(any_w, V.encode_angles(np.degrees(np.arctan(np.where(any_w, w_lo, 0)))), 255),
                    np.where(any_w, V.encode_angles(np.degrees(np.arctan(np.where(any_w, w_hi, 0)))), 255)],
                   axis=1).astype(np.uint8))                                  # (B, 2, R)
    return out, bands


def skyline(city, e, n, z, step_deg=1.5):
    """Skyline angle in degrees on each ray: views2.cast(...)[0]["hz_deg"]."""
    b, sx, sy = _dirs(step_deg)
    B, R = len(e), len(b)
    hz = np.empty((B, R), np.float64)
    u8 = np.empty((1, 1), np.uint8); f32 = np.empty((1, 1), np.float32); f64 = np.empty((1, 1), np.float64)
    _cast(*_args(city), np.ascontiguousarray(e, np.float64), np.ascontiguousarray(n, np.float64),
          np.ascontiguousarray(z, np.float32), sx, sy, D_ALL, CURV, N_LOC, BAND, N_BANDS, N_CLS_BANDS,
          hz, u8, f32, f32, u8, np.empty((1, 1, 1)), np.empty((1, 1, 1), np.uint8), f64, f64, False)
    return b, np.degrees(np.arctan(hz)).astype(np.float32)


def sightlines(city, pe, pn, pz, te, tn, tz, K=700, start=2.0, reach=150.0):
    """True where the viewpoint can see the target. All arrays the same length."""
    out = np.empty(len(pe), np.bool_)
    f = lambda a: np.ascontiguousarray(a, np.float64)
    _sightlines(*_args(city), f(pe), f(pn), f(pz), f(te), f(tn), f(tz), int(K), float(start), float(reach), out)
    return out


def compose(front, back, normal):
    """Join a front-wall and a back-wall cast() into one all-round view, as
    views2.compose() does: the front for bearings within 90 degrees of the way
    the front faces, the back for the rest."""
    (of, bf), (ob, bb) = front, back
    b = of["bearing"]
    use = np.abs(((b[None, :] - normal[:, None] + 180) % 360) - 180) < 90
    o = {"bearing": b}
    for k in of:
        if k != "bearing":
            o[k] = np.where(use, of[k], ob[k])
    m = use[:, None, :]
    return o, {k: np.where(m, bf[k], bb[k]) for k in bf}


def halve(bands):
    """Drawing bands at half the bearings (3 degrees instead of 1.5) for
    storing every house in the country: the higher of each pair of angles, so
    nothing that stands above the skyline is lost, and what tops it."""
    a, c, w = bands["a"], bands["c"], bands["w"]
    a0, a1 = a[..., 0::2], a[..., 1::2]
    pick = a1 > a0
    ah = np.where(pick, a1, a0)
    ch = np.where(pick[:, :c.shape[1]], c[..., 1::2], c[..., 0::2])
    lo = np.minimum(w[:, 0, 0::2], w[:, 0, 1::2])                        # 255 means no water, so min keeps water
    hi_ = np.where(w[:, 1, 0::2] == 255, w[:, 1, 1::2],
                   np.where(w[:, 1, 1::2] == 255, w[:, 1, 0::2], np.maximum(w[:, 1, 0::2], w[:, 1, 1::2])))
    return {"a": ah, "c": ch, "w": np.stack([lo, hi_], axis=1).astype(np.uint8)}
