"""Build a postcode-level geographic feature table for England & Wales.

Sources (all open):
  * Postcode centroids — Geovation postcode-lookup-sqlite, built from the
    ONS Postcode Directory (OGL). Coordinates recovered from the spatial
    index bounding boxes, which for point geometries are the point.
  * Air quality — AHAH v4 inputs (GeographicDataService/ahah): modelled
    NOx, PM10 and SO2 per LSOA, 2024 vintage. Joined to postcodes by
    nearest LSOA centroid (LSOAs hold ~1,500 residents, so this is tight).
  * Health access — AHAH v4 POI sets: GPs, hospitals, dentists,
    pharmacies. We compute straight-line distance to the nearest of each,
    the quantity AHAH's health domain measures by road network.

Derived from postcode geography itself:
  * Built density — postcodes within 1km and 5km. Low density is the
    rural/green end. This proxies AHAH's greenspace domain, which the
    repository does not publish, and is labelled a proxy wherever used.
  * Settlement gravity — distance to the nearest town, regional centre
    and major city, each defined by a postcode-density floor calibrated
    against known places. A crude stand-in for a travel-time isochrone,
    there being no routing engine available here.

All geometry is computed in EPSG:27700 (British National Grid) metres,
which is what the AHAH boundary data uses and what GB distances want.

Usage: python build_geo_features.py <pc_db_dir> <ahah_dir> <out_parquet>
"""

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely import wkb

# England & Wales only — the Price Paid Data's coverage.
REGIONS = ["east_midlands", "east_of_england", "london", "north_east",
           "north_west", "south_east", "south_west", "wales",
           "west_midlands", "yorkshire_and_the_humber"]
AQ_FILES = {"nox": ("no2.parquet", "nox2024_weighted_mean"),
            "pm10": ("pm10.parquet", "pm102024g_weighted_mean"),
            "so2": ("so2.parquet", "so22024_weighted_mean")}
# Settlement tiers, calibrated against known places by postcodes within
# 5km: rural Wales ~140, Torquay ~2.4k, Exeter ~3.6k, York ~4.2k,
# Bristol ~8.8k, Manchester ~11.8k, central London ~37k.
SETTLEMENT_TIERS = {"town": 1500, "regional": 3500, "major": 10000}

_to_bng = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)


def to_bng(lat, lon):
    """WGS84 degrees -> British National Grid metres."""
    x, y = _to_bng.transform(np.asarray(lon), np.asarray(lat))
    return np.column_stack([x, y])


def load_postcodes(db_dir: Path) -> pd.DataFrame:
    frames = []
    for reg in REGIONS:
        p = db_dir / f"postcodes_geo_{reg}.sqlite"
        if not p.exists():
            print(f"  ! missing {p.name}")
            continue
        con = sqlite3.connect(p)
        df = pd.read_sql_query(
            """select p.postcode as postcode,
                      (i.xmin+i.xmax)/2.0 as lon, (i.ymin+i.ymax)/2.0 as lat
               from postcodes p join idx_postcodes_geom i on i.pkid = p.rowid""",
            con)
        con.close()
        frames.append(df)
        print(f"  {reg}: {len(df):,}", flush=True)
    pc = pd.concat(frames, ignore_index=True)
    pc["postcode"] = pc["postcode"].str.strip().str.upper()
    return pc.drop_duplicates("postcode").reset_index(drop=True)


def lsoa_centroids(path: Path, valcol: str, name: str) -> pd.DataFrame:
    """LSOA polygon centroids (already EPSG:27700) plus the measure."""
    g = pd.read_parquet(path)
    cent = g["geometry"].apply(lambda b: wkb.loads(bytes(b)).centroid)
    return pd.DataFrame({
        "lsoa": g["LSOA_DZ_SDZ_21_22"].to_numpy(),
        "e": cent.apply(lambda p: p.x).to_numpy(),
        "n": cent.apply(lambda p: p.y).to_numpy(),
        name: g[valcol].to_numpy()})


def main(pc_dir: str, ahah_dir: str, out_path: str) -> None:
    pc_dir, ahah = Path(pc_dir), Path(ahah_dir)

    print("loading postcode centroids...", flush=True)
    pc = load_postcodes(pc_dir)
    print(f"  total {len(pc):,} postcodes", flush=True)
    P = to_bng(pc["lat"].to_numpy(), pc["lon"].to_numpy())
    print(f"  BNG extent: E {P[:,0].min():,.0f}-{P[:,0].max():,.0f}  "
          f"N {P[:,1].min():,.0f}-{P[:,1].max():,.0f}", flush=True)

    # ---- air quality via nearest LSOA centroid --------------------------
    print("joining AHAH air quality by nearest LSOA...", flush=True)
    aq = None
    for name, (fname, valcol) in AQ_FILES.items():
        g = lsoa_centroids(ahah / "airquality" / fname, valcol, name)
        aq = g if aq is None else aq.merge(g[["lsoa", name]], on="lsoa", how="outer")
    L = np.column_stack([aq["e"].to_numpy(), aq["n"].to_numpy()])
    _, idx = cKDTree(L).query(P, k=1, workers=-1)
    for name in AQ_FILES:
        pc[name] = aq[name].to_numpy()[idx].astype("float32")
    pc["lsoa"] = aq["lsoa"].to_numpy()[idx]
    print(f"  {len(aq):,} LSOAs · distinct LSOAs matched "
          f"{pd.Series(pc['lsoa']).nunique():,} · "
          f"NOx {pc['nox'].min():.1f}-{pc['nox'].max():.1f}", flush=True)

    # ---- health access ---------------------------------------------------
    print("computing health-access distances...", flush=True)
    for fname, name in [("GP.parquet", "gp"), ("hospital.parquet", "hospital"),
                        ("dentist.parquet", "dentist"),
                        ("pharmacy.parquet", "pharmacy")]:
        h = pd.read_parquet(ahah / "health" / fname).dropna(
            subset=["Latitude", "Longitude"])
        h = h[h["Latitude"].between(49, 61) & h["Longitude"].between(-9, 3)]
        H = to_bng(h["Latitude"].to_numpy(), h["Longitude"].to_numpy())
        d, _ = cKDTree(H).query(P, k=1, workers=-1)
        pc[f"km_{name}"] = (d / 1000).astype("float32")
        print(f"  {name}: {len(h):,} sites, median {np.median(d)/1000:.2f} km",
              flush=True)

    # ---- density and settlement gravity ----------------------------------
    print("computing density and settlement gravity...", flush=True)
    tree = cKDTree(P)
    pc["pc_within_1km"] = tree.query_ball_point(
        P, r=1000, workers=-1, return_length=True).astype("int32")
    pc["pc_within_5km"] = tree.query_ball_point(
        P, r=5000, workers=-1, return_length=True).astype("int32")

    # Absolute thresholds, not percentiles: a percentile cut is swamped by
    # London and leaves the rest of the country "hundreds of km from a city".
    dens = pc["pc_within_5km"].to_numpy()
    for label, floor in SETTLEMENT_TIERS.items():
        centres = P[dens >= floor]
        if len(centres) == 0:
            pc[f"km_{label}"] = np.nan
            continue
        d, _ = cKDTree(centres).query(P, k=1, workers=-1)
        pc[f"km_{label}"] = (d / 1000).astype("float32")
        print(f"  {label} centres (>={floor:,} in 5km): {len(centres):,} postcodes, "
              f"median distance {np.median(d)/1000:.1f} km", flush=True)

    pc["outcode"] = pc["postcode"].str.split(" ").str[0]
    pc.to_parquet(out_path, index=False)
    print(f"\nwrote {len(pc):,} postcodes -> {out_path}")
    cols = ["nox", "pm10", "so2", "km_gp", "km_hospital", "pc_within_1km",
            "km_town", "km_regional", "km_major"]
    print(pc[cols].describe().round(2).to_string())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
