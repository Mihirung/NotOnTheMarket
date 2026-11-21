"""Every house in England and Wales: the same measures the city runs made,
with the same method, one 10 km cell at a time.

For each cell the 1 m laser surface and ground model are assembled for the
cell plus 1.1 km all round (rays reach 1 km beyond the house), Ordnance
Survey buildings, water, woodland and roads are burned in as in the city
runs, and the 30 m terrain is sliced from the national grid. Then, for
every house position in the cell:

  the house      ground level, height, storeys, upper-window eye level,
                 the garden and which way it lies, which way the front faces
  upstairs       the all-round view from 1 m outside the front and back
                 walls at the top floor, joined (views2.compose)
  garden         the all-round view from the garden, and its sun through
                 the year
  windows        hours of direct sun on the front and back windows,
                 downstairs and at the top floor (light.py)
  landmarks      which landmarks on the national list are in sight from the
                 upper windows (build_landmarks.py)
  drawing        the layered panorama of both views, stored at 3 degree
                 steps (fastviews.halve) so every house in the country fits

Work is shared across processes cell by cell. A cell's results are written
when it is finished, so the run can be stopped and restarted at any time.
Survey tiles are downloaded ahead of the cells that need them and deleted
when no unfinished cell needs them.

Usage: python national_views.py <positions.parquet> <landmarks.parquet> <out_dir> [workers] [cells...]
"""
import io
import json
import os
import sys
import threading
import time
from collections import defaultdict
from multiprocessing import get_context
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import zstandard
from rasterio import features
from rasterio.transform import from_origin
from scipy.ndimage import minimum_filter
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
import far_national as FN  # noqa: E402
import fastviews as F  # noqa: E402
import tiles as T  # noqa: E402
import views2 as V  # noqa: E402
from city_views import HAS, facade_points  # noqa: E402
from light import facade_sun  # noqa: E402

CELL, MARGIN, BATCH = 10_000, 1_100, 96
OSMAP = Path("research/data/osmap/cells")
GROUP = {"cathedral": "cathedral", "abbey": "cathedral", "castle": "castle", "tower": "tower", "folly": "tower",
         "lighthouse": "tower", "church": "church", "hill": "hill", "big hill": "hill"}
LM_GROUPS = ["cathedral", "castle", "tower", "church", "hill"]
G_COLS = [f"g_{k}" for k in ("horizon", "open", "long", "long5", "longest_km", "water", "tidal", "hills", "overlooked",
                             "hz_s", "hz_w", "hz_e", "hz_n", "best_bearing", "best_reach_km")] + \
         ["sun_jun", "sun_evening_jun", "sun_morning_jun", "sun_equinox", "sun_dec"]
_tll = None


def lat_of(e, n):
    global _tll
    if _tll is None:
        from pyproj import Transformer
        _tll = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    return float(_tll.transform(e, n)[1])


def bounds(cid):
    E0, N0 = (cid // 1000) * CELL, (cid % 1000) * CELL
    return E0, N0, E0 - MARGIN, N0 - MARGIN, E0 + CELL + MARGIN, N0 + CELL + MARGIN


def cell_name(cid):
    return f"{cid // 1000}_{cid % 1000}"


# ---------------------------------------------------------------- map layers
def layer(cid, name):
    fs = sorted((OSMAP / cell_name(cid)).glob(f"{name}_*.parquet"))
    if not fs:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:27700")
    return pd.concat([gpd.read_parquet(f) for f in fs], ignore_index=True)


def burn(geoms, shape, WE0, WN1, buffer=0.0):
    out = np.zeros(shape, np.uint8)
    geoms = [g.buffer(buffer) if buffer else g for g in geoms if g is not None and not g.is_empty]
    if geoms:
        features.rasterize(((g, 1) for g in geoms), out=out, transform=from_origin(WE0, WN1, 1.0, 1.0), fill=0)
    return out.view(bool)                             # 0/1 bytes read as booleans: no second copy


def load_cell(cid):
    """The rasters for one cell, built exactly as city_views.load_city() builds a city's."""
    E0, N0, WE0, WN0, WE1, WN1 = bounds(cid)
    shape = (WN1 - WN0, WE1 - WE0)
    fz, fwb, fx0, fy0, fres = FN.window(E0 + CELL / 2, N0 + CELL / 2)
    dsm = T.window("dsm", WE0, WN0, WE1, WN1)
    real = T.window("dtm", WE0, WN0, WE1, WN1)
    has_dsm = np.isfinite(dsm)
    surveyed = float(has_dsm.mean())
    if surveyed < 1.0:                                # no survey (sea, or a gap): the 30 m terrain fills in
        fc = np.clip(((WE0 + np.arange(shape[1]) + 0.5 - fx0) / fres).astype(np.int32), 0, fz.shape[1] - 1)
        for a in range(0, shape[0], 1024):           # in strips: a half-sea cell would otherwise need gigabytes of indices
            b = min(a + 1024, shape[0])
            miss = ~has_dsm[a:b]
            if miss.any():
                fr = np.clip(((fy0 - (WN1 - np.arange(a, b) - 0.5)) / fres).astype(np.int32), 0, fz.shape[0] - 1)
                dsm[a:b][miss] = fz[np.ix_(fr, fc)][miss]
        del fc
    ground = real
    gap = ~np.isfinite(real)
    if gap.any():
        # Where the surface was surveyed but the ground model has a hole, the city runs used the lowest
        # surface point within 5 m; that is done here only around such holes. Elsewhere (sea, no
        # survey at all) the ground is the filled surface itself, which is what the city runs got too.
        ground[gap] = dsm[gap]
        hole = gap & has_dsm
        if hole.any():
            r_, c_ = np.nonzero(hole)
            r0, r1 = max(r_.min() - 6, 0), min(r_.max() + 7, shape[0]); c0, c1 = max(c_.min() - 6, 0), min(c_.max() + 7, shape[1])
            proxy = minimum_filter(dsm[r0:r1, c0:c1], size=11, mode="nearest")
            sub = hole[r0:r1, c0:c1]
            ground[r0:r1, c0:c1][sub] = proxy[sub]
            del proxy, r_, c_
    del gap, has_dsm
    bld = burn(list(layer(cid, "Building").geometry) + list(layer(cid, "ImportantBuilding").geometry), shape, WE0, WN1)
    imp = burn(list(layer(cid, "ImportantBuilding").geometry), shape, WE0, WN1)
    tidal = burn(list(layer(cid, "TidalWater").geometry) + list(layer(cid, "Foreshore").geometry), shape, WE0, WN1)
    water = burn(list(layer(cid, "SurfaceWater_Area").geometry), shape, WE0, WN1)
    wood = burn(list(layer(cid, "Woodland").geometry), shape, WE0, WN1)
    roads = layer(cid, "Road")
    road = burn(list(roads.geometry), shape, WE0, WN1, buffer=5.0)
    cls = np.full(shape, V.TERRAIN, dtype="uint8")
    for a in range(0, shape[0], 1024):               # in strips, so no full-size float temporary
        b = min(a + 1024, shape[0])
        tall = (dsm[a:b] - ground[a:b]) > 2.5
        c_ = cls[a:b]
        c_[tall | wood[a:b]] = V.TREE
        c_[water[a:b] & ~tall] = V.WATER; c_[tidal[a:b] & ~tall] = V.TIDAL; c_[bld[a:b]] = V.BUILDING
    del wood, water, tidal
    city = V.City(dsm, ground, cls, road, WE0, WN1, fz, fwb, fx0, fy0, fres, lat_of(E0 + CELL / 2, N0 + CELL / 2))
    return city, bld, imp, roads, surveyed


def front_bearing(h, roads):
    """city_views.front_bearing() with the cell's roads."""
    if not len(roads):
        return (h.garden_bearing.to_numpy() + 180) % 360, np.full(len(h), np.nan)
    tree = shapely.STRtree(roads.geometry.values)
    pts = shapely.points(h.e.to_numpy(), h.n.to_numpy())
    near = roads.geometry.values[tree.nearest(pts)]
    xy = shapely.get_coordinates(shapely.shortest_line(pts, near)).reshape(-1, 2, 2)
    de, dn = xy[:, 1, 0] - xy[:, 0, 0], xy[:, 1, 1] - xy[:, 0, 1]
    dist = np.hypot(de, dn)
    front = np.degrees(np.arctan2(de, dn)) % 360
    from_garden = (h.garden_bearing.to_numpy() + 180) % 360
    use_garden = (dist > 60) | (dist < 1)
    return np.where(use_garden & np.isfinite(from_garden), from_garden, front), dist


def morton(x, y):
    """Interleave bits so that houses next to each other in a batch are next to each other on the ground."""
    def spread(v):
        v = v.astype(np.uint64) & np.uint64(0xFFFF)
        v = (v | (v << np.uint64(8))) & np.uint64(0x00FF00FF)
        v = (v | (v << np.uint64(4))) & np.uint64(0x0F0F0F0F)
        v = (v | (v << np.uint64(2))) & np.uint64(0x33333333)
        return (v | (v << np.uint64(1))) & np.uint64(0x55555555)
    return spread(x) | (spread(y) << np.uint64(1))


# ---------------------------------------------------------------- one cell
def run_cell(args):
    cid, pos, lmk, out_dir = args
    out = Path(out_dir); t0 = time.time()
    E0, N0, WE0, WN0, WE1, WN1 = bounds(cid)
    city, bld, imp, roads, surveyed = load_cell(cid)
    t_load = time.time() - t0

    # houses: address positions on buildings, not on important buildings (as the city runs)
    pos = pos.reset_index(drop=True)
    e, n = pos.x.to_numpy() + 0.5, pos.y.to_numpy() + 0.5
    r, c = city.rc(e, n)
    pos = pos[~imp[r, c]].reset_index(drop=True)
    pos["e"], pos["n"] = pos.x + 0.5, pos.y + 0.5
    geo = [V.house_geometry(city, a, b, bld) for a, b in zip(pos.e.to_numpy(), pos.n.to_numpy())]
    keep = np.array([g is not None for g in geo], bool)
    h = pd.concat([pos[keep].reset_index(drop=True), pd.DataFrame([g for g in geo if g is not None])], axis=1)
    if not len(h):
        _write(out, cid, h, None, None, {"houses": 0, "load_s": t_load, "surveyed": surveyed})
        return cid, 0, time.time() - t0
    h = h.iloc[np.argsort(morton(h.x.to_numpy() // 16, h.y.to_numpy() // 16), kind="stable")].reset_index(drop=True)
    t_geo = time.time() - t0 - t_load

    front, road_m = front_bearing(h, roads)
    fp = facade_points(h, front, bld, city)
    h["front_bearing"] = np.round(front, 0); h["road_m"] = np.round(road_m, 1)
    h["depth_m"] = np.round(fp["front"][3] + fp["back"][3] - 2, 0)
    fe, fn, fz, _ = fp["front"]; be, bn, bz, _ = fp["back"]
    eye = h.eye_up.to_numpy()
    zf, zb = np.maximum(eye, fz + 1.6), np.maximum(eye, bz + 1.6)
    hasg = h.has_garden.to_numpy().astype(bool)
    ge, gn, gz = h.g_e.to_numpy(), h.g_n.to_numpy(), h.g_z.to_numpy() + 1.6

    # landmarks in range of each house
    lt = cKDTree(lmk[["e", "n"]].to_numpy())
    near = lt.query_ball_point(np.column_stack([h.e, h.n]), r=float(lmk.range_m.max()))
    hi = np.repeat(np.arange(len(h)), [len(x) for x in near]); li = np.concatenate([np.asarray(x, int) for x in near]) if len(hi) else np.zeros(0, int)
    le, ln, lz, lr = (lmk[k].to_numpy() for k in ("e", "n", "top_m", "range_m"))
    dist = np.hypot(le[li] - h.e.to_numpy()[hi], ln[li] - h.n.to_numpy()[hi])
    ok = dist <= lr[li]; hi, li, dist = hi[ok], li[ok], dist[ok]

    cols, draw = defaultdict(list), {k: [] for k in ("pu", "pg")}
    sight = np.zeros(len(hi), bool)
    lat = city.lat
    for s in range(0, len(h), BATCH):
        sl = slice(s, s + BATCH)
        cf = F.cast(city, fe[sl], fn[sl], zf[sl]); cb = F.cast(city, be[sl], bn[sl], zb[sl])
        o, bu = F.compose(cf, cb, front[sl])
        for k, v in V.metrics(o, "u").items():
            cols[k].append(v)
        # window sun: top floor from the upstairs casts (every other ray = the 3 degree rays), downstairs cast here
        for side, oc, (pe, pn, pz) in (("front", cf[0], (fe, fn, fz)), ("back", cb[0], (be, bn, bz))):
            normal = front[sl] if side == "front" else (front[sl] + 180) % 360
            for floor, hz in (("top", oc["hz_deg"][:, ::2]),
                              ("down", F.skyline(city, pe[sl], pn[sl], pz[sl] + 1.6, step_deg=3.0)[1])):
                for k, v in facade_sun(hz, normal, lat).items():
                    cols[f"{floor}_{side}_{k}"].append(np.round(v, 2).astype(np.float32))
        draw["pu"].append(F.halve(bu))
        # garden
        gi = np.nonzero(hasg[sl])[0]; nb_ = len(fe[sl])
        gm = {}
        bg = {"a": np.zeros((nb_, 7, 120), np.uint8), "c": np.zeros((nb_, 4, 120), np.uint8),
              "w": np.full((nb_, 2, 120), 255, np.uint8)}
        if len(gi):
            og, bgi = F.cast(city, ge[sl][gi], gn[sl][gi], gz[sl][gi])
            gm = V.metrics(og, "g"); gm.update(V.sun_hours(og["hz_deg"], og["bearing"], lat))
            hv = F.halve(bgi)
            for k in bg:
                bg[k][gi] = hv[k]
        draw["pg"].append(bg)
        for k in G_COLS:                              # NaN where a house has no garden
            full = np.full(nb_, np.nan, np.float32)
            if k in gm:
                full[gi] = gm[k]
            cols[k].append(full)
        # landmarks: from the wall that faces each one, as in the city runs
        m = (hi >= s) & (hi < s + BATCH)
        if m.any():
            j = hi[m]
            brg = np.degrees(np.arctan2(le[li[m]] - h.e.to_numpy()[j], ln[li[m]] - h.n.to_numpy()[j])) % 360
            uf = np.abs(((brg - front[j] + 180) % 360) - 180) < 90
            sight[m] = F.sightlines(city, np.where(uf, fe[j], be[j]), np.where(uf, fn[j], bn[j]), np.where(uf, zf[j], zb[j]),
                                    le[li[m]], ln[li[m]], lz[li[m]])
    t_views = time.time() - t0 - t_load - t_geo

    for k, v in cols.items():
        h[k] = np.concatenate(v)
    h["light_front"], h["light_back"] = h.down_front_year, h.down_back_year
    h["top_front"], h["top_back"] = h.top_front_year, h.top_back_year
    h["winter_front"], h["winter_back"] = h.down_front_dec, h.down_back_dec
    h["summer_evening_back"] = h.down_back_evening_jun
    h["light_best"] = h[["light_front", "light_back"]].max(axis=1)
    h["light_both"] = h.light_front + h.light_back
    for name, (col, op, thr) in HAS.items():
        h["has_" + name] = (h[col] >= thr) if op == ">=" else (h[col] <= thr)
    h["has_private"] &= h.has_garden
    h["has_swgarden"] = h.has_garden & h.garden_bearing.between(135, 315)
    part = h.postcode.str.rsplit(" ", n=1)
    h["sector"] = part.str[0] + " " + part.str[1].str[0]
    # landmark summaries
    grp = lmk.kind.map(GROUP).fillna(lmk.name.map(_city_group)).to_numpy()
    hs, ls_, ds = hi[sight], li[sight], dist[sight]
    h["lm_n"] = np.bincount(hs, minlength=len(h)).astype(np.int16)
    for g in LM_GROUPS:
        sel = grp[ls_] == g
        h[f"lm_{g}"] = np.bincount(hs[sel], minlength=len(h)).astype(np.int16)
    h["h3"] = np.arange(len(h), dtype=np.int32)       # row within the cell, the key for drawings and sight-lines
    seen = pd.DataFrame({"hid": hs.astype(np.int32), "lid": lmk.lid.to_numpy()[ls_].astype(np.int32),
                         "dist_m": np.round(ds).astype(np.int32)})
    pano = {f"{v}_{k}": np.concatenate([d[k] for d in draw[v]]) for v in draw for k in ("a", "c", "w")}
    _write(out, cid, h, seen, pano, {"houses": int(len(h)), "positions": int(len(pos)), "pairs": int(len(hi)),
                                     "in_sight": int(sight.sum()), "surveyed": surveyed, "load_s": round(t_load, 1),
                                     "geometry_s": round(t_geo, 1), "views_s": round(t_views, 1)})
    return cid, len(h), time.time() - t0


def _city_group(name):
    if "Cathedral" in name or "Abbey" in name:
        return "cathedral"
    if name in ("Haldon Belvedere", "Beckford's Tower", "Sham Castle", "Royal Crescent"):
        return "tower"
    return "hill"


def _write(out, cid, h, seen, pano, info):
    name = cell_name(cid)
    (out / "cells").mkdir(parents=True, exist_ok=True); (out / "panos").mkdir(exist_ok=True)
    if pano is not None:
        buf = io.BytesIO(); np.savez(buf, **pano)
        (out / "panos" / f"{name}.npz.zst").write_bytes(zstandard.ZstdCompressor(level=9).compress(buf.getvalue()))
        seen.to_parquet(out / "cells" / f"{name}_sight.parquet", index=False)
    h.to_parquet(out / "cells" / f"{name}.parquet.part", index=False)
    (out / "cells" / f"{name}.json").write_text(json.dumps(info))
    os.replace(out / "cells" / f"{name}.parquet.part", out / "cells" / f"{name}.parquet")   # last: marks the cell done


def load_panos(out_dir, cid):
    raw = zstandard.ZstdDecompressor().decompress((Path(out_dir) / "panos" / f"{cell_name(cid)}.npz.zst").read_bytes())
    return dict(np.load(io.BytesIO(raw)))


# ---------------------------------------------------------------- the run
def order(cells):
    """Cells square by square (100 km), serpentine, so the tiles one cell
    shares with its neighbours are still on disk when the neighbours run."""
    e, n = cells // 1000, cells % 1000
    se, sn = e // 10, n // 10
    sq_e = np.where(sn % 2 == 0, se, -se)
    ce, cn = e % 10, n % 10
    in_e = np.where(cn % 2 == 0, ce, 9 - ce)
    return cells[np.lexsort((in_e, cn, sq_e, sn))]


def main(pos_path, lmk_path, out_dir, workers=4, *only):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    pos = pd.read_parquet(pos_path)
    lmk = pd.read_parquet(lmk_path)
    # compact columns, shared by every worker without copying; a cell's rows are cut out when it is sent
    P = {k: pos[k].to_numpy() for k in ("x", "y", "uprn", "n_uprn", "cell")}
    P["pc"], pc_names = pd.factorize(pos.postcode)
    del pos
    cut = np.r_[0, np.nonzero(np.diff(P["cell"]))[0] + 1, len(P["cell"])]
    span = {int(P["cell"][a]): (a, b) for a, b in zip(cut[:-1], cut[1:])}
    cells = order(np.array(sorted(span)))
    if only:
        cells = np.array([int(c) for c in only])
    done = {_cid(p.stem) for p in (out / "cells").glob("*.parquet") if not p.stem.endswith("_sight")} \
        if (out / "cells").exists() else set()
    todo = [int(c) for c in cells if int(c) not in done]
    print(f"{len(cells)} cells, {len(done)} done, {len(todo)} to do", flush=True)
    if not todo:
        return
    def rows(c):
        a, b = span[c]
        return pd.DataFrame({"x": P["x"][a:b], "y": P["y"][a:b], "uprn": P["uprn"][a:b], "n_uprn": P["n_uprn"][a:b],
                             "postcode": pc_names[P["pc"][a:b]], "cell": P["cell"][a:b]})
    # which unfinished cells need each tile, so a tile can go once its last cell is done
    need = defaultdict(set)
    for c in todo:
        _, _, a, b, c1, d = bounds(c)
        ea, wa = T.tiles_for(a, b, c1, d)
        for k in ("dsm", "dtm"):
            for t in ea:
                need[("ea", k) + t].add(c)
            for t in wa:
                need[("wa", k) + t].add(c)
    # a restarted run: drop tiles no unfinished cell needs, and forget which cells were ready
    T.release({k for k in need})
    for p in (T.ROOT / "ready").glob("*") if (T.ROOT / "ready").exists() else []:
        p.unlink()
    lock = threading.Lock(); started = set(); finished = set()
    stop = threading.Event()

    def prefetch():
        """Download tiles for the next cells, a few ahead of the work."""
        for i, c in enumerate(todo):
            while not stop.is_set():
                with lock:
                    ahead = i - len(finished)
                try:
                    if ahead < 3 * int(workers) and T.stored_bytes() < 8e9:
                        break
                except Exception:
                    pass
                time.sleep(2)
            if stop.is_set():
                return
            _, _, a, b, c1, d = bounds(c)
            for attempt in range(5):                  # never let one bad download stop the downloads for every later cell
                try:
                    T.fetch_window(a, b, c1, d, workers=24)
                    break
                except Exception as err:
                    print(f"download problem for cell {cell_name(c)}: {err!r}; retrying", flush=True)
                    time.sleep(30)
            (T.ROOT / "ready").mkdir(exist_ok=True); (T.ROOT / "ready" / str(c)).touch()

    th = threading.Thread(target=prefetch, daemon=True); th.start()

    def tasks():
        for c in todo:
            while not (T.ROOT / "ready" / str(c)).exists():
                time.sleep(1)
            yield (c, rows(c), lmk, str(out))

    t0 = time.time(); n_h = 0
    ctx = get_context("fork")
    with ctx.Pool(int(workers), maxtasksperchild=8) as pool:
        for k, (c, nh, secs) in enumerate(pool.imap_unordered(run_cell, tasks())):
            n_h += nh
            with lock:
                finished.add(c)
            gone = [t for t, cs in need.items() if c in cs and not (cs - finished)]
            for t in gone:
                p = (T.ea_path if t[0] == "ea" else T.wa_path)(t[1], t[2], t[3])
                p.unlink(missing_ok=True); p.with_suffix(".none").unlink(missing_ok=True)
                del need[t]
            (T.ROOT / "ready" / str(c)).unlink(missing_ok=True)
            el = time.time() - t0
            print(f"[{k + 1}/{len(todo)}] cell {cell_name(c)}: {nh:,} houses in {secs:.0f}s | {n_h:,} houses, "
                  f"{el / 3600:.2f} h, {n_h / max(el, 1):.0f} houses/s | tiles on disk {T.stored_bytes() / 1e9:.1f} GB",
                  flush=True)
    stop.set()


def _cid(stem):
    a, b = stem.split("_")[:2]
    return int(a) * 1000 + int(b)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], *(sys.argv[4:]))
