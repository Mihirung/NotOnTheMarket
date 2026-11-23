"""Schools and transport around every postcode in England and Wales.

SCHOOLS (England; Welsh schools are inspected by Estyn without grades, so
Welsh postcodes are left blank and the model treats them as unknown):
  km_primary_good, km_primary_outstanding, km_secondary_good,
  km_secondary_outstanding   to the nearest state school of that phase rated
                             good or outstanding (or outstanding), by Ofsted
                             as at 31 August 2016, before every test year
  good_primaries_2km         state primaries rated good or better within 2 km
  km_primary, km_secondary   to the nearest state school of that phase, any grade
  km_grammar                 to the nearest selective state school
  km_independent             to the nearest independent school
Schools count only if they were open on 1 September 2016.

ACCESS (England and Wales):
  km_rail        to the nearest railway station (NaPTAN, rail access nodes)
  km_metro       to the nearest underground, metro or tram stop
  bus_stops_500m bus and coach stops within 500 m
  km_motorway    to the nearest motorway
  km_a_road      to the nearest A road or primary route (traffic, noise, reach)

Sources: Ofsted, Maintained schools and academies inspections and outcomes as
at 31 August 2016 (OGL); Department for Education, Get Information about
Schools (OGL); Department for Transport, NaPTAN (OGL); Ordnance Survey
OpenMap Local roads (OGL).

Writes research/data/signals/schools_postcode.parquet and access_postcode.parquet.

Usage: python schools_access_signals.py [schools|access|both]
"""
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

SIG = Path("research/data/signals")
OPEN_ON = pd.Timestamp("2016-09-01")


def postcodes():
    from pyproj import Transformer
    g = pd.read_parquet("research/data/geo_postcode.parquet", columns=["postcode", "lon", "lat", "lsoa"]).dropna(subset=["lon", "lat"])
    x, y = Transformer.from_crs(4326, 27700, always_xy=True).transform(g.lon.to_numpy(), g.lat.to_numpy())
    postcodes.wales = g.lsoa.astype(str).str.startswith("W").to_numpy()      # Welsh lower-layer areas
    return g.postcode.to_numpy(), np.column_stack([x, y])


def nearest_km(points, xy, cap_km=50.0):
    if not len(points):
        return np.full(len(xy), np.nan, np.float32)
    d, _ = cKDTree(points).query(xy, distance_upper_bound=cap_km * 1000)
    return np.where(np.isfinite(d), d / 1000, cap_km).astype("float32")


def count_within(points, xy, r):
    if not len(points):
        return np.zeros(len(xy), np.float32)
    return np.array([len(v) for v in cKDTree(points).query_ball_point(xy, r)], dtype="float32")


def schools():
    pcs, xy = postcodes()
    g = pd.read_csv("research/data/schools/gias.csv", encoding="latin-1", low_memory=False,
                    usecols=["URN", "TypeOfEstablishment (name)", "EstablishmentTypeGroup (name)", "OpenDate", "CloseDate",
                             "PhaseOfEducation (name)", "AdmissionsPolicy (name)", "Easting", "Northing"])
    g = g.dropna(subset=["Easting", "Northing"])
    od = pd.to_datetime(g.OpenDate, dayfirst=True, errors="coerce"); cd = pd.to_datetime(g.CloseDate, dayfirst=True, errors="coerce")
    g = g[(od.isna() | (od <= OPEN_ON)) & (cd.isna() | (cd > OPEN_ON))]
    o = pd.read_csv("research/data/schools/ofsted_2016.csv", encoding="latin-1", low_memory=False,
                    usecols=["URN", "Phase of education", "Overall effectiveness"])
    s = o.merge(g[["URN", "Easting", "Northing"]], on="URN", how="inner")
    E = lambda m: s.loc[m, ["Easting", "Northing"]].to_numpy(float)          # noqa: E731
    prim, sec = s["Phase of education"] == "Primary", s["Phase of education"] == "Secondary"
    good, outst = s["Overall effectiveness"] <= 2, s["Overall effectiveness"] == 1
    out = pd.DataFrame({"postcode": pcs})
    out["km_primary_good"] = nearest_km(E(prim & good), xy)
    out["km_primary_outstanding"] = nearest_km(E(prim & outst), xy)
    out["km_secondary_good"] = nearest_km(E(sec & good), xy)
    out["km_secondary_outstanding"] = nearest_km(E(sec & outst), xy)
    out["good_primaries_2km"] = count_within(E(prim & good), xy, 2000)
    state = g["EstablishmentTypeGroup (name)"].isin(["Local authority maintained schools", "Academies", "Free Schools"])
    ph = g["PhaseOfEducation (name)"]
    G = lambda m: g.loc[m, ["Easting", "Northing"]].to_numpy(float)          # noqa: E731
    out["km_primary"] = nearest_km(G(state & ph.isin(["Primary", "Middle deemed primary", "All-through"])), xy)
    out["km_secondary"] = nearest_km(G(state & ph.isin(["Secondary", "Middle deemed secondary", "All-through"])), xy)
    out["km_grammar"] = nearest_km(G(state & (g["AdmissionsPolicy (name)"] == "Selective")), xy)
    out["km_independent"] = nearest_km(G(g["EstablishmentTypeGroup (name)"] == "Independent schools"), xy)
    wales = postcodes.wales                                       # no Ofsted grades in Wales
    for c in ("km_primary_good", "km_primary_outstanding", "km_secondary_good", "km_secondary_outstanding",
              "good_primaries_2km", "km_grammar"):
        out.loc[wales, c] = np.nan
    print(f"schools: {len(s):,} graded by Ofsted in 2016, {len(g):,} open; " +
          ", ".join(f"{c} median {out[c].median():.2f}" for c in out.columns[1:]), flush=True)
    out.to_parquet(SIG / "schools_postcode.parquet", index=False)


def access():
    import geopandas as gpd
    import shapely
    pcs, xy = postcodes()
    n = pd.read_csv("research/data/access/naptan.csv", usecols=["StopType", "Status", "Easting", "Northing"], low_memory=False)
    n = n[(n.Status == "active") & n.Easting.notna()]
    P = lambda types: n.loc[n.StopType.isin(types), ["Easting", "Northing"]].to_numpy(float)   # noqa: E731
    out = pd.DataFrame({"postcode": pcs})
    out["km_rail"] = nearest_km(P(["RLY", "RSE"]), xy)
    out["km_metro"] = nearest_km(P(["MET", "TMU", "PLT"]), xy)
    out["bus_stops_500m"] = count_within(P(["BCT", "BCS"]), xy, 500)
    lines = {"km_motorway": [], "km_a_road": []}
    for f in glob.glob("research/data/osmap/cells/*/Road_*.parquet"):
        r = gpd.read_parquet(f, columns=["CLASSIFICA", "geometry"])
        lines["km_motorway"].append(r.geometry.values[(r.CLASSIFICA == "Motorway").to_numpy()])
        lines["km_a_road"].append(r.geometry.values[r.CLASSIFICA.isin(["A Road", "Primary Road", "Motorway"]).to_numpy()])
    pts = shapely.points(xy)
    for k, parts in lines.items():
        geoms = np.concatenate(parts)
        tree = shapely.STRtree(geoms)
        d = np.full(len(pts), 50_000.0)
        for a in range(0, len(pts), 200_000):                # nearest line within 50 km, in batches
            ii, jj = tree.query_nearest(pts[a:a + 200_000], max_distance=50_000, return_distance=False)
            dist = shapely.distance(pts[a:a + 200_000][ii], geoms[jj])
            np.minimum.at(d, a + ii, dist)
        out[k] = (d / 1000).astype("float32")
    print("access: " + ", ".join(f"{c} median {out[c].median():.2f}" for c in out.columns[1:]), flush=True)
    out.to_parquet(SIG / "access_postcode.parquet", index=False)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "both"
    if what in ("schools", "both"):
        schools()
    if what in ("access", "both"):
        access()
