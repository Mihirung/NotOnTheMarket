"""House-level outlooks for a whole city.

Builds the city's rasters (1 m surface, ground, land-cover classes,
roads, 30 m far field with water mask), takes every address point from
OS Open UPRN that sits on a building, and computes each house's outlook
with views2. Writes per-house and per-postcode tables, sector summaries
for the prototype, and layered panoramas for representative houses.

Usage: python city_views.py <exeter|bath> <out_dir> [workers] [sample_n | sectors]

"sectors" as the last argument redraws the sector panoramas from the
saved house table without recomputing every house.
"""

import glob
import json
import sqlite3
import sys
from multiprocessing import Pool
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio import features
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from scipy.ndimage import minimum_filter
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
import views2 as V  # noqa: E402
from compute_views import mosaic  # noqa: E402

T = "research/data/terrain"
CITIES = {
    "exeter": dict(
        name="Exeter", grid=(282000, 300000, 85000, 99000), lidar=f"{T}/lidar",
        om=f"{T}/os_openmap", sq="SX", uprn="research/data/uprn/exeter.csv",
        outcodes=["EX1", "EX2", "EX3", "EX4"], centre=(50.7236, -3.5275),
        landmarks=[("Exeter Cathedral", "ll", 50.72253, -3.52985, "tower", 0),
                   ("Haldon Belvedere", "bng", 287550, 86150, "summit", 20),
                   ("Woodbury Common", "bng", 303200, 87400, "summit", 2),
                   ("Haytor, Dartmoor", "bng", 275700, 77000, "summit", 2)]),
    "bath": dict(
        name="Bath", grid=(368000, 382000, 160000, 170000), lidar=f"{T}/lidar_bath",
        om=f"{T}/os_openmap_st", sq="ST", uprn="research/data/uprn/bath.csv",
        outcodes=["BA1", "BA2"], centre=(51.3811, -2.3590),
        landmarks=[("Bath Abbey", "ll", 51.38147, -2.35874, "tower", 0),
                   ("Royal Crescent", "ll", 51.38722, -2.36806, "tower", 0),
                   ("Beckford's Tower", "ll", 51.40611, -2.37917, "tower", 0),
                   ("Sham Castle", "ll", 51.38417, -2.33722, "tower", 0),
                   ("Solsbury Hill", "ll", 51.41000, -2.33440, "summit", 2),
                   ("Kelston Round Hill", "ll", 51.40028, -2.42250, "summit", 8)]),
}
_ll2bng = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
CITY = None          # views2.City, shared with workers by fork
LMK = None           # [(name, e, n, z_top)]
HAS = dict(long=("u_long", ">=", 0.10), water=("u_water", ">=", 0.03), tidal=("u_tidal", ">=", 0.02),
           hills=("u_hills", ">=", 0.05), private=("g_overlooked", "<=", 0.50),
           evening=("sun_evening_jun", ">=", 2.0), sunny=("sun_equinox", ">=", 6.0))


def warp_far(cop_dir, cx, cy, half=36000, res=30.0):
    e0, n1 = cx - half, cy + half
    w = h = int(2 * half / res)
    z = np.full((h, w), np.nan, dtype="float32"); wb = np.zeros((h, w), dtype="uint8")
    tr = from_origin(e0, n1, res, res)
    for kind, dest in (("DEM", z), ("WBM", wb)):
        for p in sorted(glob.glob(f"{cop_dir}/*_{kind}.tif")):
            with rasterio.open(p) as src:
                l, b, r, t = transform_bounds(src.crs, "EPSG:27700", *src.bounds, densify_pts=21)
                if r < e0 or l > e0 + 2 * half or t < n1 - 2 * half or b > n1:
                    continue
                if kind == "DEM":
                    tmp = np.full((h, w), np.nan, dtype="float32")
                    reproject(rasterio.band(src, 1), tmp, dst_crs="EPSG:27700", dst_transform=tr,
                              resampling=Resampling.bilinear, dst_nodata=np.nan)
                    m = np.isfinite(tmp)
                else:
                    tmp = np.full((h, w), 255, dtype="uint8")
                    reproject(rasterio.band(src, 1), tmp, dst_crs="EPSG:27700", dst_transform=tr,
                              resampling=Resampling.nearest, dst_nodata=255)
                    m = tmp != 255
                dest[m] = tmp[m]
    z[~np.isfinite(z)] = 0.0
    return z, wb, e0, n1, res


def rasterise(om, sq, layers, grid, buffer=0.0):
    E0, E1, N0, N1 = grid
    base = glob.glob(f"{om}/*/data/")[0]
    geoms = []
    for L in layers:
        g = gpd.read_file(f"{base}{sq}_{L}.shp", bbox=(E0, N0, E1, N1), engine="pyogrio")
        geoms += list(g.geometry.buffer(buffer).values if buffer else g.geometry.values)
    shape = (N1 - N0, E1 - E0)
    if not geoms:
        return np.zeros(shape, dtype=bool)
    return features.rasterize(((gm, 1) for gm in geoms), out_shape=shape,
                              transform=from_origin(E0, N1, 1.0, 1.0), fill=0, dtype="uint8").astype(bool)


def load_city(cfg, cache):
    E0, E1, N0, N1 = cfg["grid"]
    cache = Path(cache); cache.mkdir(parents=True, exist_ok=True)
    print("mosaicking surface model...", flush=True)
    dsm, tr = mosaic(sorted(glob.glob(f"{cfg['lidar']}/dsm_*.tif")))
    assert dsm.shape == (N1 - N0, E1 - E0), dsm.shape
    proxy = minimum_filter(np.where(np.isnan(dsm), np.inf, dsm), size=11, mode="nearest")
    proxy[~np.isfinite(proxy)] = np.nan
    ground = proxy
    dtm_paths = [p for p in sorted(glob.glob(f"{cfg['lidar']}/dtm_*.tif"))]
    if dtm_paths:
        part, tr2 = mosaic(dtm_paths)
        r0 = int(round((tr.f - tr2.f))); c0 = int(round((tr2.c - tr.c)))
        real = np.full_like(dsm, np.nan); real[r0:r0 + part.shape[0], c0:c0 + part.shape[1]] = part
        print(f"  real terrain model covers {np.isfinite(real).mean()*100:.0f}% of the grid", flush=True)
        ground = np.where(np.isfinite(real), real, proxy); del real, part
    dsm = np.where(np.isnan(dsm), ground, dsm); ground = np.where(np.isnan(ground), dsm, ground)

    def mask(name, layers, buffer=0.0):
        f = cache / f"mask_{name}.npy"
        if f.exists():
            return np.load(f)
        m = rasterise(cfg["om"], cfg["sq"], layers, cfg["grid"], buffer); np.save(f, m); return m
    print("rasterising buildings, water, woodland, roads...", flush=True)
    bld = mask("building", ["Building", "ImportantBuilding"])
    imp = mask("important", ["ImportantBuilding"])
    tidal = mask("tidal", ["TidalWater", "Foreshore"])
    water = mask("water", ["SurfaceWater_Area"])
    wood = mask("woodland", ["Woodland"])
    road = mask("road", ["Road"], buffer=5.0)
    cls = np.full(dsm.shape, V.TERRAIN, dtype="uint8")
    tall = (dsm - ground) > 2.5
    cls[tall | wood] = V.TREE
    # Water only where the surface really is the water: a canopy or a bridge
    # over the river is what you see, not the river.
    cls[water & ~tall] = V.WATER; cls[tidal & ~tall] = V.TIDAL; cls[bld] = V.BUILDING
    del wood, water, tidal, tall
    print("warping far field...", flush=True)
    fz, fwb, fx0, fy0, fres = warp_far("research/data/cop30", (E0 + E1) / 2, (N0 + N1) / 2)
    city = V.City(dsm, ground, cls, road, E0, N1, fz, fwb, fx0, fy0, fres, cfg["centre"][0])
    return city, bld, imp


def landmarks(cfg, city):
    out = []
    for name, kind, a, b, typ, extra in cfg["landmarks"]:
        e, n = (a, b) if kind == "bng" else _ll2bng.transform(b, a)
        out.append((name, float(e), float(n), V.landmark_top(city, e, n, typ, extra)))
    return out


def pano(e, n, eye, skip_own, fixed):
    """Layered panorama plus where each landmark sits in it. A landmark counts
    as in sight only if the sight-line is clear AND the drawing itself shows
    it above everything nearer, so the picture and the label never disagree."""
    p = V.panorama(CITY, e, n, eye, skip_own, fixed, 1.0)
    nb = len(p["bands"][0])
    p["lm"] = []
    for name, le, ln, lz in LMK:
        d = float(np.hypot(le - e, ln - n))
        drop = d ** 2 / (2 * V.R_EARTH) * (1 - V.REFRACTION)
        b = float(np.degrees(np.arctan2(le - e, ln - n)) % 360)
        a = float(np.degrees(np.arctan((lz - drop - eye) / max(d, 1.0))))
        i0 = int(np.floor(b / p["step"])) % nb; i1 = (i0 + 1) % nb
        nearer = [min(band[i0], band[i1]) / 10.0 for band, hi in zip(p["bands"], p["edges"][1:]) if hi <= d]
        drawn = a >= (max(nearer) if nearer else -90.0) - 0.2
        line = bool(V.sees(CITY, np.array([e]), np.array([n]), np.array([eye]), le, ln, lz)[0])
        p["lm"].append({"name": name, "b": round(b, 1), "a": round(a, 2), "km": round(d / 1000, 1),
                        "sees": bool(line and drawn)})
    return p


def work(batch):
    """One batch of houses -> metric columns."""
    e, n, eye, fixed, ge, gn, gz, hasg = batch
    o, (slope, _, _) = V.cast(CITY, e, n, eye, True, own_fixed=fixed)
    res = V.metrics(o, "u")
    for name, le, ln, lz in LMK:
        res["sees_" + name] = (V.sees(CITY, e, n, eye, le, ln, lz)
                               & V.near_clear(slope, o["bearing"], e, n, eye, le, ln, lz))
    del slope
    res["u_hz2"] = o["hz_deg"][:, ::2].round(1); res["u_cls2"] = o["hz_cls"][:, ::2]
    g = np.nonzero(hasg)[0]
    gm = {}
    if len(g):
        og, _ = V.cast(CITY, ge[g], gn[g], gz[g] + 1.6, False)
        gm = V.metrics(og, "g"); gm.update(V.sun_hours(og["hz_deg"], og["bearing"], CITY.lat))
        gm["g_hz2"] = og["hz_deg"][:, ::2].round(1); gm["g_cls2"] = og["hz_cls"][:, ::2]
    for k, v in gm.items():
        full = np.full((len(e),) + v.shape[1:], np.nan if v.dtype.kind == "f" else 0, dtype=v.dtype)
        full[g] = v; res[k] = full
    return res


def closest_to_typical(g, cols):
    """The row nearest the group's medians on several measures at once."""
    z = sum(((g[c] - g[c].median()) / (g[c].std() or 1.0)).fillna(3.0) ** 2 for c in cols)
    return g.loc[z.idxmin()]


def sector_summary(pts, cfg, var, out, city_key):
    """Sector shares for the prototype, and drawn panoramas of a typical upstairs
    view, the best outlook, and a typical garden in each sector."""
    pts = pts.copy(); pts["log_reach"] = np.log10(pts.u_longest_km.clip(lower=0.05))
    sectors = {}
    for sec, g in pts.groupby("sector"):
        if len(g) < 25:
            continue
        wg = g.n_uprn.to_numpy()
        share = lambda col: round(float(np.average(g[col].fillna(False).astype(float), weights=wg)), 2)
        typ = closest_to_typical(g, ["u_long", "u_horizon", "log_reach", "u_hills"])
        score = g.u_long.fillna(0) + 2 * g.u_water.fillna(0) + g.u_hills.fillna(0) + 0.02 * g.u_longest_km.fillna(0)
        for i, (name, *_) in enumerate(LMK):            # prefer a house that shows the landmarks
            score = score + (1.0 if i == 0 else 0.3) * g["sees_" + name].fillna(False).astype(float)
        want = LMK[0][0] if share("sees_" + LMK[0][0]) >= 0.03 else None
        best = pbest = None
        for idx in score.sort_values(ascending=False).index[:15]:
            cand = g.loc[idx]; pc = pano(cand.e, cand.n, cand.eye_up, True, not cand.on_building)
            if best is None:
                best, pbest = cand, pc
            if want is None or any(l["name"] == want and l["sees"] for l in pc["lm"]):
                best, pbest = cand, pc
                break
        ptyp = pano(typ.e, typ.n, typ.eye_up, True, not typ.on_building)
        gard = g[g.has_garden]
        gt = closest_to_typical(gard, ["sun_equinox", "sun_evening_jun", "sun_dec", "g_horizon"]) if len(gard) else None
        entry = {
            "n_houses": int(len(g)), "n_addr": int(wg.sum()),
            "shares": {k: share("has_" + k) for k in list(HAS) + ["swgarden", "garden"]},
            "landmarks": {name: share("sees_" + name) for name, *_ in LMK},
            "typical": {"horizon_deg": round(float(gard.g_horizon.median()), 1) if len(gard) else None,
                        "overlooked": round(float(gard.g_overlooked.median()), 2) if len(gard) else None,
                        "longest_km": round(float(g.u_longest_km.median()), 1),
                        "sun_jun": round(float(gard.sun_jun.median()), 1) if len(gard) else None,
                        "sun_evening_jun": round(float(gard.sun_evening_jun.median()), 1) if len(gard) else None,
                        "sun_equinox": round(float(gard.sun_equinox.median()), 1) if len(gard) else None,
                        "sun_dec": round(float(gard.sun_dec.median()), 1) if len(gard) else None,
                        "storeys": float(g.storeys.median())},
            "pano_typical": ptyp, "pano_best": pbest,
            "best": {"longest_km": round(float(best.u_longest_km), 1), "storeys": int(best.storeys),
                     "facing": round(float(best.u_best_bearing))},
            "typ": {"facing": round(float(typ.u_best_bearing)), "storeys": int(typ.storeys),
                    "longest_km": round(float(typ.u_longest_km), 1)},
        }
        if gt is not None:
            entry["pano_garden"] = pano(gt.g_e, gt.g_n, gt.g_z + 1.6, False, False)
            entry["garden"] = {"bearing": round(float(gt.garden_bearing)), "sun_jun": round(float(gt.sun_jun), 1),
                               "sun_evening_jun": round(float(gt.sun_evening_jun), 1),
                               "sun_equinox": round(float(gt.sun_equinox), 1), "sun_dec": round(float(gt.sun_dec), 1)}
        sectors[sec] = entry
    meta = {"city": cfg["name"], "lat": cfg["centre"][0],
            "landmarks": [{"name": nm, "e": round(e), "n": round(n), "top_m": round(z)} for nm, e, n, z in LMK],
            "n_houses": int(len(pts)), "n_addr": int(pts.n_uprn.sum()), "within_postcode_variance": var}
    json.dump({"meta": meta, "sectors": sectors}, open(Path(out) / f"sectors_{city_key}.json", "w"), separators=(",", ":"))
    return sectors


def main(city_key, out_dir, workers=3, sample_n=0):
    global CITY, LMK
    cfg = CITIES[city_key]; out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    CITY, bld, imp = load_city(cfg, f"research/data/terrain/cache_{city_key}")
    LMK = landmarks(cfg, CITY)
    for name, e, n, z in LMK:
        print(f"  landmark {name}: E{e:.0f} N{n:.0f} top {z:.0f} m", flush=True)
    if sample_n == "sectors":                         # redraw panoramas from the saved house table
        pts = pd.read_parquet(out / f"houses_{city_key}.parquet")
        var = json.load(open(out / f"sectors_{city_key}.json"))["meta"]["within_postcode_variance"]
        sectors = sector_summary(pts, cfg, var, out, city_key)
        print(f"{cfg['name']}: redrew {len(sectors)} sectors")
        return

    # ---- houses: address points on residential-looking buildings -----------
    u = pd.read_csv(cfg["uprn"], usecols=[0, 1, 2]); u.columns = ["uprn", "e", "n"]
    u["ce"], u["cn"] = np.floor(u.e).astype(int), np.floor(u.n).astype(int)
    pts = u.groupby(["ce", "cn"]).size().rename("n_uprn").reset_index()
    pts["e"], pts["n"] = pts.ce + 0.5, pts.cn + 0.5
    r, c = CITY.rc(pts.e.to_numpy(), pts.n.to_numpy())
    inside = (r >= 1100) & (r < CITY.h - 1100) & (c >= 1100) & (c < CITY.w - 1100)
    pts = pts[inside].reset_index(drop=True); r, c = r[inside], c[inside]
    pts = pts[~imp[r, c]].reset_index(drop=True)
    con = sqlite3.connect("/home/user/pc-lookup/database/postcodes_geo_south_west.sqlite")
    like = " or ".join(f"p.postcode like '{o} %'" for o in cfg["outcodes"])
    pc = pd.read_sql_query(f"""select p.postcode, (i.xmin+i.xmax)/2.0 lon, (i.ymin+i.ymax)/2.0 lat
        from postcodes p join idx_postcodes_geom i on i.pkid=p.rowid where {like}""", con)
    pe, pn = _ll2bng.transform(pc.lon.to_numpy(), pc.lat.to_numpy())
    dist, idx = cKDTree(np.column_stack([pe, pn])).query(pts[["e", "n"]].to_numpy(), k=1)
    pts["postcode"] = pc.postcode.to_numpy()[idx]
    pts = pts[dist <= 150].reset_index(drop=True)
    if sample_n:
        pts = pts.sample(int(sample_n), random_state=1).reset_index(drop=True)
    print(f"{len(u):,} address points -> {len(pts):,} candidate house positions", flush=True)

    geo = [V.house_geometry(CITY, e, n, bld) for e, n in zip(pts.e.to_numpy(), pts.n.to_numpy())]
    keep = np.array([g is not None for g in geo])
    pts = pts[keep].reset_index(drop=True)
    pts = pd.concat([pts, pd.DataFrame([g for g in geo if g is not None])], axis=1)
    print(f"  {len(pts):,} houses on buildings ({int(pts.n_uprn.sum()):,} addresses); "
          f"{pts.has_garden.mean()*100:.0f}% with a garden found; storeys "
          f"{pts.storeys.value_counts().sort_index().to_dict()}", flush=True)

    B = 40
    cols = ["e", "n", "eye_up", "on_building", "g_e", "g_n", "g_z", "has_garden"]
    arr = [pts[k].to_numpy() for k in cols]
    arr[3] = ~arr[3].astype(bool)                       # fixed skip where the point is off the footprint
    arr[7] = arr[7].astype(bool)
    jobs = [tuple(a[i:i + B] for a in arr) for i in range(0, len(pts), B)]
    parts = []
    with Pool(int(workers)) as pool:
        for k, res in enumerate(pool.imap(work, jobs, chunksize=4)):
            parts.append(res)
            if k % 100 == 0:
                print(f"  {k * B:,} houses done", flush=True)
    keys = sorted(set().union(*[p.keys() for p in parts]))
    prof = {}
    for k in keys:
        vals = [p[k] if k in p else None for p in parts]
        ref = next(v for v in vals if v is not None)
        vals = [v if v is not None else np.full((len(j[0]),) + ref.shape[1:], np.nan if ref.dtype.kind == "f" else 0,
                                                 dtype=ref.dtype) for v, j in zip(vals, jobs)]
        a = np.concatenate(vals)
        if a.ndim == 2:
            prof[k] = a
        else:
            pts[k] = a
    pts["sector"] = pts.postcode.str.rsplit(" ", n=1).str[0] + " " + pts.postcode.str.rsplit(" ", n=1).str[1].str[0]
    for name, (col, op, thr) in HAS.items():
        pts["has_" + name] = (pts[col] >= thr) if op == ">=" else (pts[col] <= thr)
    pts["has_private"] &= pts.has_garden
    pts["has_swgarden"] = pts.has_garden & pts.garden_bearing.between(135, 315)
    pts.to_parquet(out / f"houses_{city_key}.parquet", index=False)
    np.savez_compressed(out / f"profiles_{city_key}.npz", **{k: v.astype("float16" if v.dtype.kind == "f" else "uint8")
                                                             for k, v in prof.items()})

    # ---- postcode aggregates (address-weighted) ----------------------------
    w = pts.n_uprn.to_numpy()
    num = [c_ for c_ in pts.columns if c_.startswith(("u_", "g_", "sun_")) and c_ not in ("g_e", "g_n", "g_z")]
    flags = [c_ for c_ in pts.columns if c_.startswith(("has_", "sees_"))]
    agg = {}
    grp = pts.groupby("postcode")
    agg["n_houses"] = grp.size(); agg["n_addr"] = grp.n_uprn.sum()
    for c_ in num + ["height", "garden_clear", "plot_open"]:
        agg["m_" + c_] = grp[c_].mean()
    for c_ in flags:
        agg["s_" + c_] = grp[c_].mean()
    for c_ in ("u_long", "u_water", "g_horizon", "sun_evening_jun"):
        agg["sd_" + c_] = grp[c_].std()
    pcagg = pd.DataFrame(agg).reset_index()
    pcagg.to_parquet(out / f"postcodes_{city_key}.parquet", index=False)

    # ---- how much does the view vary between houses on one postcode? -------
    def within_share(col):
        d = pts[[col, "postcode"]].dropna()
        tot = d[col].var(); within = d.groupby("postcode")[col].var().mean()
        return float(within / tot) if tot > 0 else np.nan
    var = {c_: round(within_share(c_), 2) for c_ in ("u_long", "u_water", "u_horizon", "g_horizon",
                                                     "g_overlooked", "sun_evening_jun", "sun_equinox")}
    print("share of house-to-house variance that is WITHIN a postcode:", var, flush=True)

    sectors = sector_summary(pts, cfg, var, out, city_key)

    print(f"\n{cfg['name']}: {len(pts):,} houses, {len(pcagg):,} postcodes, {len(sectors)} sectors")
    show = ["u_horizon", "g_horizon", "g_overlooked", "u_long", "u_longest_km", "u_water", "u_hills",
            "sun_evening_jun", "sun_equinox", "garden_clear", "height"]
    print(pts[show].describe().round(2).loc[["25%", "50%", "75%"]].to_string())
    print("share of addresses with each outlook:")
    for k in flags:
        print(f"  {k:28s} {np.average(pts[k].fillna(False).astype(float), weights=w)*100:5.1f}%")


if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2], a[3] if len(a) > 3 else 3, (a[4] if a[4] == "sectors" else int(a[4])) if len(a) > 4 else 0)
