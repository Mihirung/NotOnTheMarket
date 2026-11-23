"""Basemap for the site's search map, built from open data we already hold.

The published page may not load map tiles from another server, so the map
carries its own: one national file for the zoomed-out view and one file per
50 km square for the detail, drawn in the browser.

Sources (all open, OGL):
  OS OpenMap Local   roads by class, woodland, inland water (research/data/osmap/cells)
  OS Open Built Up Areas   built-up land
  OS Open Names      populated places, for labels
  ONS Countries BGC  coast and land outline (generalised to 20 m)

Coordinates are longitude and latitude in steps of 1/Q degree, each line or
ring delta-encoded from its first point, so the files stay small.

Usage: python basemap.py <download_dir> <out_dir> [square ...]
  download_dir holds ctry_bgc.geojson, bua/os_open_built_up_areas.gpkg and names/Data/*.csv
"""
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer

CELLS = Path("research/data/osmap/cells")
CELL, SQ, Q = 10_000, 50_000, 10_000          # 10 km input cells, 50 km output squares, 1/10000 degree steps (under a pixel at zoom 13)
MARGIN = 2_000                                 # land and built-up areas are clipped a little beyond the square
TO_LL = Transformer.from_crs(27700, 4326, always_xy=True)
TO_BNG = Transformer.from_crs(4326, 27700, always_xy=True)

ROAD_CLASS = {"Motorway": "m", "Primary Road": "p", "A Road": "a", "B Road": "b", "Minor Road": "n"}
ROAD_TOL = {"m": 12, "p": 12, "a": 12, "b": 12, "n": 12}         # simplification in metres
# Local streets are left out: they would treble the files, and at the scale of a postcode
# sector the built-up tint, the through roads and the place names carry the map.
PLACE_RANK = {"City": 1, "Town": 2, "Suburban Area": 3, "Village": 3, "Hamlet": 4, "Other Settlement": 4}


def to_ll(geoms):
    return shapely.transform(geoms, lambda xy: np.column_stack(TO_LL.transform(xy[:, 0], xy[:, 1])))


ORIGIN = np.zeros(2, np.int64)      # each file's coordinates start from its own corner, to keep the numbers short


def enc(coords):
    """Delta-encoded integer steps for one line or ring; None when it collapses to a point."""
    q = np.round(np.asarray(coords) * Q).astype(np.int64) - ORIGIN
    if len(q) > 1:
        keep = np.ones(len(q), bool)
        keep[1:] = np.any(np.diff(q, axis=0) != 0, axis=1)
        q = q[keep]
    if len(q) < 2:
        return None
    return np.vstack([q[:1], np.diff(q, axis=0)]).ravel().tolist()


def lines(geoms):
    out = []
    for g in geoms:
        parts = g.geoms if g.geom_type.startswith("Multi") else [g]
        for p in parts:
            e = enc(p.coords)
            if e:
                out.append(e)
    return out


def polys(geoms, min_ring_m2=0, bng=None):
    """Each polygon as a list of rings; holes smaller than min_ring_m2 dropped."""
    out = []
    for i, g in enumerate(geoms):
        parts = g.geoms if g.geom_type.startswith("Multi") else [g]
        bparts = (bng[i].geoms if bng[i].geom_type.startswith("Multi") else [bng[i]]) if bng is not None else None
        for j, p in enumerate(parts):
            if p.is_empty or p.geom_type != "Polygon":
                continue
            rings = [enc(p.exterior.coords)]
            for k, h in enumerate(p.interiors):
                if bparts is not None and j < len(bparts) and k < len(bparts[j].interiors) \
                        and shapely.Polygon(bparts[j].interiors[k]).area < min_ring_m2:
                    continue
                rings.append(enc(h.coords))
            rings = [r for r in rings if r and len(r) >= 6]
            if rings:
                out.append(rings)
    return out


def core(geoms, cx, cy, line=False):
    """Features whose middle lies in this cell's own 10 km square: cells overlap by a margin, so this keeps each feature once."""
    pt = shapely.line_interpolate_point(geoms, 0.5, normalized=True) if line else shapely.point_on_surface(geoms)
    x, y = shapely.get_x(pt), shapely.get_y(pt)
    return (x >= cx * CELL) & (x < (cx + 1) * CELL) & (y >= cy * CELL) & (y < (cy + 1) * CELL)


def read_cell(cx, cy, layer):
    fs = sorted((CELLS / f"{cx}_{cy}").glob(f"{layer}_*.parquet"))
    if not fs:
        return None
    g = pd.concat([gpd.read_parquet(f) for f in fs], ignore_index=True)
    g = g[~g.geometry.is_empty & g.geometry.notna()]
    if not len(g):
        return None
    if layer != "Road":                                       # polygons can repeat across the 100 km squares a cell spans
        g = g[core(g.geometry.values, cx, cy)]
        return g.drop_duplicates(subset=["geometry"]) if len(g) else None
    lines_only = g[shapely.get_type_id(g.geometry.values) <= 5]
    return lines_only[core(lines_only.geometry.values, cx, cy, line=True)]


def squares_with_cells():
    sq = {}
    for d in CELLS.iterdir():
        if d.is_dir() and "_" in d.name:
            cx, cy = map(int, d.name.split("_"))
            sq.setdefault((cx * CELL // SQ, cy * CELL // SQ), []).append((cx, cy))
    return sq


class Sources:
    def __init__(self, dl):
        dl = Path(dl)
        land = gpd.read_file(dl / "ctry_bgc.geojson").to_crs(27700)
        self.land = land[land.geometry.notna()].geometry.values
        bua = gpd.read_file(dl / "bua/os_open_built_up_areas.gpkg", layer="os_open_built_up_areas",
                            columns=["areahectares"])
        self.bua = bua.geometry.values
        self.bua_ha = bua.areahectares.values
        self.bua_tree = shapely.STRtree(self.bua)
        rows = []
        for f in sorted((dl / "names/Data").glob("*.csv")):
            d = pd.read_csv(f, header=None, usecols=[2, 4, 6, 7, 8, 9], dtype=str, encoding="utf-8")
            d.columns = ["name1", "name2", "type", "local", "x", "y"]
            rows.append(d[(d["type"] == "populatedPlace") & d["local"].isin(PLACE_RANK)])
        n = pd.concat(rows, ignore_index=True)
        n["x"], n["y"] = n.x.astype(float), n.y.astype(float)
        n["rank"] = n["local"].map(PLACE_RANK)
        lon, lat = TO_LL.transform(n.x.values, n.y.values)
        n["lon"], n["lat"] = lon, lat
        self.names = n


def label_rows(n):
    out = []
    for r in n.itertuples():
        name = r.name1 if not isinstance(r.name2, str) else f"{r.name1} / {r.name2}"
        out.append([name, int(round(r.lon * Q)) - int(ORIGIN[0]), int(round(r.lat * Q)) - int(ORIGIN[1]), int(r.rank)])
    return out


def clip_box(geoms, box, tol):
    """Polygons clipped to a box, simplified in metres, then to longitude and latitude."""
    if not len(geoms):
        return [], []
    g = shapely.intersection(geoms, box)
    g = g[~shapely.is_empty(g)]
    g = shapely.simplify(g, tol, preserve_topology=True)
    g = g[~shapely.is_empty(g)]
    return to_ll(g), g


def set_origin(lon, lat):
    ORIGIN[:] = [int(round(lon * Q)), int(round(lat * Q))]
    return ORIGIN.tolist()


def build_square(sx, sy, cells, src):
    x0, y0 = sx * SQ, sy * SQ
    box = shapely.box(x0 - MARGIN, y0 - MARGIN, x0 + SQ + MARGIN, y0 + SQ + MARGIN)
    lon0, lat0 = TO_LL.transform(x0, y0)
    out = {"sq": f"{sx}_{sy}", "o": set_origin(lon0, lat0), "r": {}}
    roads, wood, water = [], [], []
    for cx, cy in cells:
        r = read_cell(cx, cy, "Road")
        if r is not None and len(r):
            roads.append(r[["CLASSIFICA", "geometry"]])
        w = read_cell(cx, cy, "Woodland")
        if w is not None:
            wood.append(w.geometry.values)
        h = read_cell(cx, cy, "SurfaceWater_Area")
        if h is not None:
            water.append(h.geometry.values)
    nat = {}
    if roads:
        R = pd.concat(roads, ignore_index=True)
        cls = R.CLASSIFICA.str.split(",").str[0].map(ROAD_CLASS)
        for k in ROAD_TOL:
            g = R.geometry.values[(cls == k).values]
            if not len(g):
                continue
            merged = shapely.get_parts(shapely.line_merge(shapely.multilinestrings(shapely.get_parts(g))))
            out["r"][k] = lines(to_ll(shapely.simplify(merged, ROAD_TOL[k])))
    if wood:
        W = np.concatenate(wood)
        W = W[shapely.area(W) >= 30_000]                    # three hectares or more
        Wb = shapely.simplify(W, 15, preserve_topology=True)
        out["w"] = polys(to_ll(Wb), 20_000, Wb)
    if water:
        H = np.concatenate(water)
        H = H[shapely.area(H) >= 8_000]
        Hb = shapely.simplify(H, 10, preserve_topology=True)
        out["h"] = polys(to_ll(Hb), 8_000, Hb)
    idx = src.bua_tree.query(box)
    ull, ubng = clip_box(src.bua[idx], box, 20)      # the outlines follow a 25 m grid
    out["u"] = polys(ull, 20_000, ubng)
    lll, lbng = clip_box(src.land, box, 0)
    out["g"] = polys(lll, 50_000, lbng)
    n = src.names
    inside = (n.x >= x0) & (n.x < x0 + SQ) & (n.y >= y0) & (n.y < y0 + SQ)
    out["t"] = label_rows(n[inside])
    return out, nat


def decode_file(obj):
    """Lines and polygons of one written file back to longitude and latitude."""
    o = np.array(obj.get("o", [0, 0]), np.int64)
    dec = lambda a: (np.cumsum(np.array(a, np.int64).reshape(-1, 2), axis=0) + o) / Q
    return {"r": {k: [dec(a) for a in v] for k, v in obj.get("r", {}).items()},
            "h": [[dec(r) for r in p] for p in obj.get("h", [])]}


def square_index(sx, sy):
    """A square's extent in longitude and latitude, with the margin its land and built-up areas reach."""
    x0, y0 = sx * SQ - MARGIN, sy * SQ - MARGIN
    t = np.linspace(0, 1, 9)
    xs = np.concatenate([x0 + t * (SQ + 2 * MARGIN), np.full(9, x0 + SQ + 2 * MARGIN), x0 + t * (SQ + 2 * MARGIN), np.full(9, x0)])
    ys = np.concatenate([np.full(9, y0), y0 + t * (SQ + 2 * MARGIN), np.full(9, y0 + SQ + 2 * MARGIN), y0 + t * (SQ + 2 * MARGIN)])
    lon, lat = TO_LL.transform(xs, ys)
    return [sx, sy, round(float(lon.min()), 4), round(float(lat.min()), 4), round(float(lon.max()), 4), round(float(lat.max()), 4)]


def build_nation(out_dir, src):
    """The zoomed-out map: coast, the largest towns, motorways and trunk roads, large lakes, city and town names.
    Roads and lakes come from the square files already written, merged and simplified again."""
    set_origin(0, 0)
    land = shapely.simplify(src.land, 250, preserve_topology=True)
    parts = shapely.get_parts(land)
    parts = parts[shapely.area(parts) >= 2_000_000]
    out = {"g": polys(to_ll(parts), 20_000_000, parts), "r": {}}
    roads, lakes, index = {"m": [], "p": []}, [], []
    for f in sorted((out_dir / "sq").glob("*.json")):
        sx, sy = map(int, f.stem.split("_"))
        index.append(square_index(sx, sy))
        d = decode_file(json.loads(f.read_text()))
        for k in roads:
            roads[k] += [shapely.LineString(np.column_stack(TO_BNG.transform(a[:, 0], a[:, 1]))) for a in d["r"].get(k, []) if len(a) > 1]
        for p in d["h"]:
            rings = [np.column_stack(TO_BNG.transform(r[:, 0], r[:, 1])) for r in p if len(r) > 3]
            if rings:
                poly = shapely.Polygon(rings[0], rings[1:])
                if poly.is_valid and poly.area >= 500_000:
                    lakes.append(poly)
    for k, tol in (("m", 100), ("p", 150)):
        merged = shapely.get_parts(shapely.line_merge(shapely.multilinestrings(roads[k])))
        merged = shapely.simplify(merged, tol)
        merged = merged[shapely.length(merged) >= (500 if k == "m" else 1500)]
        out["r"][k] = lines(to_ll(merged))
    big = shapely.get_parts(src.bua[src.bua_ha >= 300])
    big = big[shapely.area(big) >= 1_000_000]
    bb = shapely.simplify(big, 150, preserve_topology=True)
    out["u"] = polys(to_ll(bb), 1e12, bb)
    if lakes:
        hb = shapely.simplify(np.array(lakes), 100, preserve_topology=True)
        out["h"] = polys(to_ll(hb), 1e12, hb)
    n = src.names
    out["t"] = label_rows(n[n["rank"] <= 2])
    out["sq"], out["Q"], out["SQ"] = index, Q, SQ
    return out


def write(path, obj):
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
    return path.stat().st_size


def main(dl, out_dir, only=None):
    """only: square names to rebuild, or {"nation"} to rebuild just the national file from the squares on disk."""
    out_dir = Path(out_dir)
    (out_dir / "sq").mkdir(parents=True, exist_ok=True)
    src = Sources(dl)
    if only != {"nation"}:
        sqs = squares_with_cells()
        todo = [k for k in sorted(sqs) if not only or f"{k[0]}_{k[1]}" in only]
        total = 0
        for i, (sx, sy) in enumerate(todo):
            obj, _ = build_square(sx, sy, sqs[(sx, sy)], src)
            size = write(out_dir / "sq" / f"{sx}_{sy}.json", obj)
            total += size
            n_feat = sum(len(v) for v in obj["r"].values()) + len(obj.get("w", [])) + len(obj.get("h", []))
            print(f"{i + 1}/{len(todo)} {sx}_{sy}: {size / 1e6:.2f} MB, {n_feat} features", flush=True)
        print(f"squares {total / 1e6:.1f} MB in {len(todo)} files")
    if not only or only == {"nation"}:
        size = write(out_dir / "gb.json", build_nation(out_dir, src))
        print(f"national file {size / 1e6:.2f} MB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], set(sys.argv[3:]) or None)
