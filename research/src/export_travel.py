"""Data for searching by where people need to get to, beside the site's
other files (research/outputs/site5):

  stations.json   every railway, underground, metro and tram station in
                  England and Wales: [name, lat, lon, kind] (NaPTAN access
                  areas; kind 1 rail, 2 underground, metro or tram)
  places.json     names a person might type: every station, every local
                  authority (at the centre of its homes), every postcode
                  district (e.g. "BA2") and sector (e.g. "BA2 4")
  pc/<AREA>.json  every postcode in the postcode area and its position
                  (fetched only when someone types a postcode there)
  nation.json     each sector's row gains its nearest station and how far
                  away it is, so travel by public transport can be estimated

Usage: python export_travel.py research/outputs/site5
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree


def stations():
    n = pd.read_csv("research/data/access/naptan.csv", usecols=["CommonName", "StopType", "Status", "Longitude", "Latitude"],
                    low_memory=False)
    n = n[(n.Status == "active") & n.StopType.isin(["RLY", "MET"]) & n.Latitude.notna()]
    n["kind"] = np.where(n.StopType == "RLY", 1, 2)
    n["name"] = (n.CommonName.str.replace(r"\s+(Rail|Railway|Underground|Metro|Tram|DLR)\s+Station$", "", regex=True)
                 .str.replace(r"\s+(Rail Station|Station)$", "", regex=True).str.strip())
    n = n.sort_values("kind").drop_duplicates(["name", "kind"])
    return n[["name", "Latitude", "Longitude", "kind"]].reset_index(drop=True)


def main(site):
    site = Path(site)
    st = stations()
    json.dump([[r.name, round(r.Latitude, 5), round(r.Longitude, 5), int(r.kind)] for r in st.itertuples()],
              open(site / "stations.json", "w"), separators=(",", ":"))
    print(f"{len(st):,} stations")

    g = pd.read_parquet("research/data/geo_postcode.parquet", columns=["postcode", "lat", "lon"]).dropna()
    g = g[g.postcode.str.contains(" ")]
    g["area"] = g.postcode.str.extract(r"^([A-Z]+)")[0]
    g["district"] = g.postcode.str.split(" ").str[0]
    g["sector"] = g.postcode.str[:-2]
    areas = {p.stem for p in (site / "areas").glob("*.json")}
    (site / "pc").mkdir(exist_ok=True)
    for a, t in g[g.area.isin(areas)].groupby("area"):
        d = {}
        for pc, la, lo in zip(t.postcode, t.lat.round(5), t.lon.round(5)):
            d[pc] = [float(la), float(lo)]
        json.dump(d, open(site / "pc" / f"{a}.json", "w"), separators=(",", ":"))
    print(f"postcode positions for {g.area.isin(areas).sum():,} postcodes in {len(areas)} areas")

    places = [[r.name + (" station" if r.kind == 1 else " (underground, metro or tram)"), round(r.Latitude, 5),
               round(r.Longitude, 5)] for r in st.itertuples()]
    for col in ("district", "sector"):
        c = g.groupby(col)[["lat", "lon"]].mean().round(5)
        places += [[k, float(v.lat), float(v.lon)] for k, v in c.iterrows()]
    lad = pd.read_parquet("research/data/onsud/postcode_lad.parquet")
    c = g.merge(lad, on="postcode").groupby("lad")[["lat", "lon"]].mean().round(5)
    places += [[k, float(v.lat), float(v.lon)] for k, v in c.iterrows()]
    json.dump(places, open(site / "places.json", "w"), separators=(",", ":"))
    print(f"{len(places):,} place names")

    nat = json.load(open(site / "nation.json"))
    tree = cKDTree(np.column_stack([st.Latitude.to_numpy(), st.Longitude.to_numpy() * np.cos(np.radians(52.5))]))
    rail = st.kind.to_numpy() == 1
    trail = cKDTree(np.column_stack([st.Latitude[rail], st.Longitude[rail] * np.cos(np.radians(52.5))]))
    ridx = np.nonzero(rail)[0]
    for r in nat["rows"]:
        lat, lon = r[4], r[5]
        if lat is None or lon is None:
            r.append(None); continue
        _, i = tree.query([lat, lon * np.cos(np.radians(52.5))])
        _, j = trail.query([lat, lon * np.cos(np.radians(52.5))])
        km = lambda k: round(float(np.hypot(st.Latitude[k] - lat, (st.Longitude[k] - lon) * np.cos(np.radians(lat))) * 111.2), 2)  # noqa: E731
        r.append([int(i), km(i), int(ridx[j]), km(ridx[j])])          # nearest station of any kind, nearest rail station
    nat["row_cols"] = ["sector", "area", "lad", "homes", "lat", "lon", "vm", "lm_share", "climate", "stations"]
    json.dump(nat, open(site / "nation.json", "w"), separators=(",", ":"))
    print(f"nation.json: {len(nat['rows']):,} sectors with their nearest stations")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "research/outputs/site5")
