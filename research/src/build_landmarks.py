"""A national list of landmarks to look for from every house.

The city runs used a hand-picked list for each city. For the whole
country the list is built by rule from open data:

  structures   Wikidata items in England and Wales with an English
               Wikipedia article that are a cathedral, an abbey, a castle,
               a lighthouse, a folly or a tower, or a church listed at
               Grade I. Their top is the highest point of the 1 m laser
               surface within 30 m, as in the city runs.
  hills        Every hill in England and Wales in the Database of British
               and Irish Hills with at least 30 m of prominence. Its top is
               the surveyed summit height plus 2 m, or the 30 m terrain's
               highest point nearby if that is higher.
  city lists   The ten hand-picked Exeter and Bath landmarks, so nothing
               those cities had is lost.

Each kind is looked for out to a set distance: hills with 100 m or more
of prominence and cathedrals furthest, Grade I churches nearest.

Usage: python build_landmarks.py <dobih.csv> <geo_postcode.parquet> <out.parquet>
"""
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
import tiles as T  # noqa: E402

RANGE = {"cathedral": 25_000, "abbey": 20_000, "tower": 20_000, "lighthouse": 20_000, "folly": 20_000,
         "castle": 15_000, "church": 8_000, "hill": 15_000, "big hill": 30_000, "city list": 30_000}
CLASSES = {"cathedral": "wd:Q2977", "abbey": "wd:Q160742", "castle": "wd:Q23413", "lighthouse": "wd:Q39715",
           "folly": "wd:Q1144661", "tower": "wd:Q12518"}
CITY_LISTS = [("Exeter Cathedral", "ll", 50.72253, -3.52985, "tower", 0),
              ("Haldon Belvedere", "bng", 287550, 86150, "summit", 20),
              ("Woodbury Common", "bng", 303200, 87400, "summit", 2),
              ("Haytor, Dartmoor", "bng", 275700, 77000, "summit", 2),
              ("Bath Abbey", "ll", 51.38147, -2.35874, "tower", 0),
              ("Royal Crescent", "ll", 51.38722, -2.36806, "tower", 0),
              ("Beckford's Tower", "ll", 51.40611, -2.37917, "tower", 0),
              ("Sham Castle", "ll", 51.38417, -2.33722, "tower", 0),
              ("Solsbury Hill", "ll", 51.41000, -2.33440, "summit", 2),
              ("Kelston Round Hill", "ll", 51.40028, -2.42250, "summit", 8)]
_ll = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)


def sparql(q):
    for attempt in range(5):
        r = subprocess.run(["curl", "-sS", "-m", "300", "-G", "https://query.wikidata.org/sparql", "--data-urlencode",
                            f"query={q}", "-H", "Accept: application/sparql-results+json", "-A", "research-script/1.0"],
                           capture_output=True, text=True)
        try:
            return json.loads(r.stdout)["results"]["bindings"]
        except Exception:
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("Wikidata query failed")


def wikidata():
    rows = []
    for kind, cls in CLASSES.items():
        q = f"""SELECT DISTINCT ?c ?cLabel ?loc WHERE {{ ?c wdt:P31/wdt:P279* {cls}; wdt:P17 wd:Q145; wdt:P625 ?loc .
                ?a schema:about ?c; schema:isPartOf <https://en.wikipedia.org/> .
                SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }}"""
        for b in sparql(q):
            rows.append((kind, b["c"]["value"].rsplit("/", 1)[1], b["cLabel"]["value"], b["loc"]["value"]))
        print(f"  {kind}: {sum(1 for r in rows if r[0] == kind)}", flush=True)
    q = """SELECT DISTINCT ?c ?cLabel ?loc WHERE { ?c wdt:P31/wdt:P279* wd:Q16970; wdt:P1435 wd:Q15700818; wdt:P625 ?loc .
           ?a schema:about ?c; schema:isPartOf <https://en.wikipedia.org/> .
           SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }"""
    for b in sparql(q):
        rows.append(("church", b["c"]["value"].rsplit("/", 1)[1], b["cLabel"]["value"], b["loc"]["value"]))
    print(f"  church (Grade I): {sum(1 for r in rows if r[0] == 'church')}", flush=True)
    t = pd.DataFrame(rows, columns=["kind", "qid", "name", "wkt"])
    ll = t.wkt.str.extract(r"Point\(([-0-9.eE]+) ([-0-9.eE]+)\)").astype(float)
    t["e"], t["n"] = _ll.transform(ll[0].to_numpy(), ll[1].to_numpy())
    # one row per item: the most specific kind wins
    pri = {k: i for i, k in enumerate(["cathedral", "abbey", "lighthouse", "folly", "tower", "castle", "church"])}
    t["p"] = t.kind.map(pri)
    return t.sort_values("p").drop_duplicates("qid").drop(columns=["p", "wkt"])


def hills(path):
    d = pd.read_csv(path, encoding="latin-1", low_memory=False); d.columns = [c.strip() for c in d.columns]
    d = d[d.Country.isin(["E", "W", "ES"]) & (d.Drop >= 30)]
    return pd.DataFrame({"kind": np.where(d.Drop >= 100, "big hill", "hill"), "qid": "dobih:" + d.Number.astype(str),
                         "name": d.Name.str.strip(), "e": d.Xcoord.astype(float), "n": d.Ycoord.astype(float),
                         "summit_m": d.Metres.astype(float), "prominence_m": d.Drop.astype(float)})


def far_max(e, n, cop_dir="research/data/cop30"):
    """Highest 30 m terrain point within about 100 m, from the Copernicus tiles."""
    import rasterio
    lat_lon = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    out = np.full(len(e), np.nan)
    lon, lat = lat_lon.transform(e, n)
    for key, idx in pd.Series(range(len(e))).groupby([np.floor(lat).astype(int), np.floor(lon).astype(int)]):
        la, lo = key
        name = f"Copernicus_DSM_COG_10_N{la:02d}_00_{'W' if lo < 0 else 'E'}{abs(lo):03d}_00_DEM.tif"
        p = Path(cop_dir) / name
        if not p.exists():
            continue
        with rasterio.open(p) as src:
            a = src.read(1)
            for i in idx.to_numpy():
                r, c = src.index(lon[i], lat[i])
                out[i] = a[max(r - 3, 0):r + 4, max(c - 3, 0):c + 4].max()
    return out


def main(dobih, geo_path, out):
    print("Wikidata structures:", flush=True)
    s = wikidata()
    h = hills(dobih)
    cl = []
    for name, kind, a, b, typ, extra in CITY_LISTS:
        e, n = (a, b) if kind == "bng" else _ll.transform(b, a)
        cl.append({"kind": "city list", "qid": "city:" + name, "name": name, "e": e, "n": n,
                   "city_type": typ, "extra_m": extra})
    t = pd.concat([s, h, pd.DataFrame(cl)], ignore_index=True)
    # England and Wales only: within 3 km of an England or Wales postcode
    geo = pd.read_parquet(geo_path, columns=["lon", "lat"])
    pe, pn = _ll.transform(geo.lon.to_numpy(), geo.lat.to_numpy())
    d, _ = cKDTree(np.column_stack([pe, pn])).query(t[["e", "n"]].to_numpy(), k=1)
    t = t[(d <= 3000) | (t.kind == "city list")].reset_index(drop=True)
    # the same structure listed twice (a castle that is also a folly): keep one within 40 m
    keep = np.ones(len(t), bool); tree = cKDTree(t[["e", "n"]].to_numpy())
    for i, j in sorted(tree.query_pairs(40)):
        if keep[i] and keep[j] and t.kind[i] not in ("hill", "big hill") and t.kind[j] not in ("hill", "big hill"):
            keep[i if t.kind[j] == "city list" and t.kind[i] != "city list" else j] = False   # the city lists win
    t = t[keep].reset_index(drop=True)
    print(t.kind.value_counts().to_dict(), flush=True)

    # tops
    t["top_m"] = np.nan
    fm = far_max(t.e.to_numpy(), t.n.to_numpy())
    hl = t.kind.isin(["hill", "big hill"]).to_numpy()
    t.loc[hl, "top_m"] = np.fmax(t.summit_m[hl].to_numpy(), fm[hl]) + 2.0
    city_summit = (t.kind == "city list") & (t.city_type == "summit")
    t.loc[city_summit, "top_m"] = fm[city_summit.to_numpy()] + t.extra_m[city_summit]
    struct = np.nonzero(np.isnan(t.top_m.to_numpy()))[0]
    for d_ in ["tmp", "wa_dsm"]:
        (T.ROOT / d_).mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    # group the structures by the 2 km tile they sit in; fetch each tile once, read every top in it, delete it
    groups = pd.Series(struct).groupby([(t.e[struct] // 2000).astype(int).to_numpy(), (t.n[struct] // 2000).astype(int).to_numpy()])

    def tops_in(key, idx):
        res = [(i, T.point_max(t.e[i], t.n[i])) for i in idx]
        e0, n0 = key[0] * 2000, key[1] * 2000              # this group's own tile is not needed again
        T.ea_path("dsm", e0, n0).unlink(missing_ok=True)
        return res
    with ThreadPoolExecutor(24) as ex:
        tops = [x for part in ex.map(lambda g: tops_in(g[0], g[1].to_numpy()), groups) for x in part]
    for i, v in tops:
        t.loc[i, "top_m"] = np.nan if v is None else v
    for d_ in T.ROOT.glob("*_dsm"):                   # the run fetches its own tiles; free the disk
        for p in d_.glob("*.*"):
            p.unlink(missing_ok=True)
    print(f"tower tops from the 1 m surface for {len(struct)} structures in {time.time() - t0:.0f}s; "
          f"{int(np.isnan(t.top_m).sum())} without survey data, which use the 30 m terrain + 10 m", flush=True)
    miss = np.isnan(t.top_m.to_numpy())
    t.loc[miss, "top_m"] = fm[miss] + 10.0
    t = t[np.isfinite(t.top_m)].reset_index(drop=True)
    t["range_m"] = t.kind.map(RANGE).astype(float)
    t["lid"] = np.arange(len(t), dtype=np.int32)
    t[["lid", "kind", "qid", "name", "e", "n", "top_m", "range_m", "prominence_m"]].to_parquet(out, index=False)
    print(f"{len(t):,} landmarks written to {out}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
