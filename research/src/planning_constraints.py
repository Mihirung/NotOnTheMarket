"""Planning constraints on every address position in England and Wales.

What may be built at a home without planning permission (permitted
development) depends first on where it stands. This tags every address
position with the designations that limit it:

  conservation area       England: planning.data.gov.uk; Wales: DataMapWales
  listed building         Historic England list entries and outlines; Cadw.
                          A position counts as listed when it stands on a
                          building that carries a list entry, so every house
                          of a terrace listed as one entry is caught. (Works
                          to a building attached to a listed one also need
                          care; the flag is named for that.)
  Article 4 direction     England: areas where the council has removed
                          permitted development rights, sorted by what they
                          remove: householder rights (extensions, roofs,
                          windows, doors, porches, walls), changes to houses
                          in multiple occupation only, or other or unstated
  green belt              England
  protected landscape     Areas of Outstanding Natural Beauty (National
                          Landscapes), England and Wales
  National Park           England (including the Broads) and Wales
  World Heritage Site     England and Wales

Conservation areas, protected landscapes, National Parks and World Heritage
Sites together are 'article 2(3) land', where some permitted development
(side extensions, two-storey rear extensions, cladding, roof extensions) is
not allowed.

Output: research/data/planning/constraints_positions.parquet, one row per
address position in research/data/ew_positions.parquet (same order): its
grid cell and a bit mask (BITS below).

Usage: python planning_constraints.py
"""
import csv
import json
import re
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer

csv.field_size_limit(sys.maxsize)
EN = Path("research/data/planning/constraints")
WA = Path("research/data/planning/constraints_wales")
OSMAP = Path("research/data/osmap/cells")
OUT = Path("research/data/planning/constraints_positions.parquet")
BITS = {"conservation": 0, "listed": 1, "a4_house": 2, "a4_hmo": 3, "a4_other": 4, "green_belt": 5,
        "landscape": 6, "national_park": 7, "world_heritage": 8, "a4_extension": 9, "a4_roof": 10}
ART23 = ("conservation", "landscape", "national_park", "world_heritage")

HMO = re.compile(r"\bHMO|multiple occupation|class l\b|c3.{0,12}c4|\bC4\b", re.I)
HOUSE = re.compile(r"part 1|class [a-h]\b|extension|enlargement|roof|dormer|window|door|porch|chimney|"
                   r"boundar|fence|wall|gate|painting|paint|cladding|render|solar|satellite|hard standing|"
                   r"hardstanding|outbuilding|dwellinghouse|householder|demolition", re.I)


def a4_kinds(row):
    """Which rights an Article 4 area removes. The national data codes them as
    Part and Class of the permitted development order (1A house extensions,
    1B roof additions, 1C other roof alterations, 1D porches, 1E outbuildings,
    ... 3L changes between a house and a small house in multiple occupation);
    where no code is given the text decides."""
    codes = str(row.get("permitted-development-rights") or "")
    found = set(re.findall(r"\b(\d{1,2})([A-Z]{1,2})\b", codes.upper()))
    t = " ".join(str(row.get(k, "")) for k in ("name", "description", "notes"))
    out = set()
    if found:
        part1 = {c for p, c in found if p == "1"}
        if part1:
            out.add("a4_house")
            if "A" in part1:
                out.add("a4_extension")
            if part1 & {"B", "C"}:
                out.add("a4_roof")
        if ("3", "L") in found or HMO.search(t):
            out.add("a4_hmo")
        if not out:
            out.add("a4_other")
        return out
    if HMO.search(t) and not HOUSE.search(t):
        return {"a4_hmo"}
    if HOUSE.search(t) or re.search(r"conservation area", t, re.I):
        return {"a4_house"}                           # rights removed, which classes not stated
    return {"a4_other"}


def england(name, cols=("geometry",)):
    """An England layer: geometries on the national grid (and the columns asked for)."""
    t = pd.read_csv(EN / f"{name}.csv", engine="python", usecols=lambda c: c in set(cols) | {"geometry", "point"})
    wkt = lambda s: np.array([w if isinstance(w, str) and w else None for w in s], dtype=object)
    g = shapely.from_wkt(wkt(t.geometry))
    if "point" in t.columns:                              # entries with no shape but a point
        miss = shapely.is_missing(g)
        g[miss] = shapely.from_wkt(wkt(t.point[miss]))
    ok = ~shapely.is_missing(g)
    t, g = t[ok].reset_index(drop=True), g[ok]
    tr = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
    g = shapely.transform(g, lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1])))
    t["geom"] = shapely.make_valid(g)
    return t


def wales(fname):
    d = gpd.read_file(WA / fname)
    return pd.DataFrame({"geom": shapely.make_valid(d.geometry.values)})


def layers():
    t0 = time.time()
    L = {}
    L["conservation"] = [england("conservation-area").geom.values, wales("geonode_conservation_areas_wales.json").geom.values]
    a4 = england("article-4-direction-area", ("name", "description", "notes", "permitted-development-rights"))
    kinds = [a4_kinds(r) for r in a4.to_dict("records")]
    for k in ("a4_house", "a4_hmo", "a4_other", "a4_extension", "a4_roof"):
        L[k] = [a4.geom.values[[k in ks for ks in kinds]]]
    print("Article 4 areas by what they remove:", {k: int(sum(k in ks for ks in kinds))
          for k in ("a4_house", "a4_extension", "a4_roof", "a4_hmo", "a4_other")}, flush=True)
    L["green_belt"] = [england("green-belt").geom.values]
    L["landscape"] = [england("area-of-outstanding-natural-beauty").geom.values,
                      wales("geonode_GWC21_Area_of_Outstanding_Natural_Beauty.json").geom.values]
    L["national_park"] = [england("national-park").geom.values, wales("inspire-nrw_NRW_NATIONAL_PARK.json").geom.values]
    L["world_heritage"] = [england("world-heritage-site").geom.values, wales("geonode_GWC21_World_Heritage_Site.json").geom.values]
    L = {k: np.concatenate(v) for k, v in L.items()}
    lb = england("listed-building").geom.values
    lbo = england("listed-building-outline").geom.values
    cadw = wales("inspire-wg_Cadw_ListedBuildings.json").geom.values
    listed_pts = np.concatenate([shapely.centroid(lb), shapely.centroid(cadw)])
    print({k: len(v) for k, v in L.items()}, f"listed entries {len(listed_pts):,}, outlines {len(lbo):,}, "
          f"{time.time() - t0:.0f}s", flush=True)
    return {k: shapely.STRtree(v) for k, v in L.items()}, listed_pts, shapely.STRtree(lbo)


def buildings(cell):
    parts = [gpd.read_parquet(p) for p in (OSMAP / cell).glob("Building_*.parquet")]
    if not parts:
        return np.array([], dtype=object)
    return np.concatenate([p.geometry.values for p in parts])


def main(only=(), out_path=OUT):
    pos = pd.read_parquet("research/data/ew_positions.parquet", columns=["x", "y", "cell"])
    if only:                                          # a test on a few cells
        pos = pos[pos.cell.isin([int(a) * 1000 + int(b) for a, b in (c.split("_") for c in only)])].reset_index(drop=True)
    trees, listed_pts, outlines = layers()
    lp_tree = shapely.STRtree(listed_pts)
    bits = np.zeros(len(pos), np.uint16)
    starts = np.r_[0, np.nonzero(np.diff(pos.cell.to_numpy()))[0] + 1, len(pos)]
    t0 = time.time()
    for k in range(len(starts) - 1):
        a, b = starts[k], starts[k + 1]
        c = int(pos.cell.iat[a]); cell = f"{c // 1000}_{c % 1000}"
        pts = shapely.points(pos.x.to_numpy()[a:b] + 0.5, pos.y.to_numpy()[a:b] + 0.5)
        m = np.zeros(b - a, np.uint16)
        for name, tree in trees.items():
            hit = tree.query(pts, predicate="intersects")[0]
            m[np.unique(hit)] |= np.uint16(1 << BITS[name])
        # listed: on a building that carries a list entry, or inside a listed outline
        bld = buildings(cell)
        if len(bld):
            bt = shapely.STRtree(bld)
            x0, y0, x1, y1 = shapely.total_bounds(pts)
            near = lp_tree.query(shapely.box(x0 - 50, y0 - 50, x1 + 50, y1 + 50))
            if len(near):
                lb_hit = bt.query(listed_pts[near], predicate="intersects")[1]
                flagged = np.zeros(len(bld), bool); flagged[lb_hit] = True
                ph, bh = bt.query(pts, predicate="dwithin", distance=3.0)
                m[np.unique(ph[flagged[bh]])] |= np.uint16(1 << BITS["listed"])
        hit = outlines.query(pts, predicate="intersects")[0]
        m[np.unique(hit)] |= np.uint16(1 << BITS["listed"])
        bits[a:b] = m
        if k % 100 == 0:
            print(f"  {k + 1} of {len(starts) - 1} cells, {b:,} positions, {time.time() - t0:.0f}s", flush=True)
    out = pd.DataFrame({"x": pos.x.to_numpy(), "y": pos.y.to_numpy(), "cell": pos.cell.to_numpy(), "bits": bits})
    out.to_parquet(out_path, index=False)
    share = {n: round(float(((bits >> b) & 1).mean()), 4) for n, b in BITS.items()}
    art23 = sum(((bits >> BITS[n]) & 1) for n in ART23) > 0
    share["article_2_3_land"] = round(float(art23.mean()), 4)
    json.dump(share, open(Path(out_path).with_suffix(".json"), "w"), indent=1)
    print("share of address positions:", share, flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--test":       # --test <out.parquet> <cell> [cell...]
        main(sys.argv[3:], sys.argv[2])
    else:
        main()
