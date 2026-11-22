"""Find the houses in England and Wales with the best of any combination of
characteristics, and draw them.

    python find_best.py --want views water quiet_garden evening_sun --top 20
    python find_best.py --all --top 50 --area BA BS --draw best.html
    python find_best.py --want landmarks cathedral --region Wales

Each characteristic is scored for every house as its percentile across the
whole country (0 = lowest, 100 = highest). A house's score is the average
of the percentiles asked for, so a house has to be good at all of them to
come top, and the weakest of them breaks ties. --all asks for every
characteristic at once: the house with the very best of everything.

Postcodes are exact (ONS UPRN Directory). Output: a table in the terminal,
a CSV beside it, and with --draw a page with each house's drawn upstairs
view and garden.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

sys.path.insert(0, str(Path(__file__).parent))

NAT = Path("research/outputs/national")
# name: (column, higher is better?, label)
CHAR = {
    "views": ("u_long", True, "share of the horizon with a long view from upstairs"),
    "far": ("u_longest_km", True, "furthest sight-line"),
    "water": ("u_water", True, "water in view"),
    "sea": ("u_tidal", True, "sea or estuary in view"),
    "hills": ("u_hills", True, "hills on the skyline"),
    "open_outlook": ("u_overlooked", False, "upstairs windows not overlooked"),
    "quiet_garden": ("g_overlooked", False, "garden not overlooked"),
    "garden_room": ("garden_clear", True, "room in the garden"),
    "evening_sun": ("sun_evening_jun", True, "evening sun in the garden at midsummer"),
    "garden_sun": ("sun_equinox", True, "sun in the garden at the equinox"),
    "winter_garden": ("sun_dec", True, "sun in the garden at midwinter"),
    "light": ("light_both", True, "direct sun on the windows, front and back"),
    "winter_light": ("winter_front", True, "midwinter sun on the front windows"),
    "landmarks": ("lm_n", True, "landmarks in sight"),
    "cathedral": ("lm_cathedral", True, "a cathedral or abbey in sight"),
    "castle": ("lm_castle", True, "a castle in sight"),
    "named_hills": ("lm_hill", True, "named hills in sight"),
    # health and surroundings, by postcode (GEO and AMENITY families)
    "clean_air": ("nox", False, "clean air (nitrogen oxides)"),
    "near_gp": ("km_gp", False, "a GP nearby"),
    "near_hospital": ("km_hospital", False, "a hospital nearby"),
    "near_park": ("km_park", False, "a park or playing field nearby"),
    "parkland": ("park_ha_1km", True, "parkland within 1 km"),
    "near_woods": ("km_wood", False, "woodland nearby"),
    "near_water": ("km_blue", False, "a river, lake or the sea nearby"),
    "near_coast": ("km_sea", False, "the coast nearby"),
    "pubs_near": ("km_pub", False, "a pub nearby"),
    "pubs_far": ("km_pub_far", True, "away from pubs"),
    "restaurants": ("restaurants_1km", True, "restaurants and cafes within 1 km"),
    "few_takeaways": ("takeaways_1km", False, "few takeaways nearby"),
    # what could be built without planning permission (permitted_development.py, per house)
    "extension_value": ("add_value", True, "value that could be added without planning permission"),
    "extension_space": ("add_m2", True, "floor space that could be added without planning permission"),
    "loft": ("pd_loft", True, "a loft extension allowed without planning permission"),
    "historic": ("historic", True, "in a conservation area or listed"),
}
# where each column comes from when it is not one of the house's own measures
POSTCODE = {"nox": "GEO", "km_gp": "GEO", "km_hospital": "GEO", "km_park": "AMENITY", "park_ha_1km": "AMENITY",
            "km_wood": "AMENITY", "km_blue": "AMENITY", "km_sea": "AMENITY", "km_pub": "AMENITY", "km_pub_far": "AMENITY",
            "restaurants_1km": "AMENITY", "takeaways_1km": "AMENITY"}
PER_HOUSE_PD = {"add_value", "add_m2", "pd_loft", "historic"}
# "all": every outlook, garden, light and landmark measure, with clean air, health services, green and blue
# space. Pubs (near or far), food and building work are matters of taste: they are chosen by name.
ALL = list(CHAR)[:17] + ["clean_air", "near_gp", "near_hospital", "near_park", "parkland", "near_woods", "near_water"]
REGION_AREAS = {
    "London": "E EC N NW SE SW W WC BR CR DA EN HA IG KT RM SM TW UB WD",
    "South East": "BN CT GU HP ME MK OX PO RG RH SL SO TN",
    "East": "AL CB CM CO IP LU NR PE SG SS",
    "South West": "BA BH BS DT EX GL PL SN SP TA TQ TR",
    "Midlands": "B CV DE DY LE LN NG NN ST TF WR WS WV HR",
    "North West": "BB BL CA CH CW FY L LA M OL PR SK WA WN",
    "Yorkshire and North East": "BD DH DL DN HD HG HU HX LS S TS WF YO NE SR",
    "Wales": "CF LD LL NP SA SY",
}
KEEP = ["postcode", "x", "y", "h3", "storeys", "has_garden", "garden_bearing", "front_bearing", "n_uprn"]


def load(cols):
    """The asked-for columns of every house, read cell by cell into compact
    columns (single precision, postcodes as codes): 28 million houses in a
    few gigabytes. Postcode signals are attached by postcode, and what could
    be built without permission from each cell's permitted development table."""
    from pandas.api.types import union_categoricals
    import signals as SG
    own = [c for c in cols if c not in POSTCODE and c not in PER_HOUSE_PD]
    pdc = [c for c in cols if c in PER_HOUSE_PD]
    import pyarrow.parquet as pq
    files = sorted(str(p) for p in (NAT / "cells").glob("*.parquet") if not p.stem.endswith("_sight")
                   and "h3" in pq.read_schema(p).names)               # cells with no houses are skipped
    parts, pcs = [], []
    for f in files:
        t = pd.read_parquet(f, columns=sorted(set(own + KEEP)))
        if not len(t):
            continue
        if pdc:
            pf = NAT / "pd" / Path(f).name
            if pf.exists():
                q = pd.read_parquet(pf)
                q["historic"] = q["in_conservation"] | q["listed"] if "in_conservation" in q.columns else (q.pd_reason == 2)
                t = t.merge(q[["h3"] + [c for c in pdc if c in q.columns]], on="h3", how="left")
            for c in pdc:
                if c not in t.columns:
                    t[c] = np.nan
        for c in t.columns:
            if t[c].dtype == "float64" or t[c].dtype == bool or t[c].dtype == object and c != "postcode":
                t[c] = pd.to_numeric(t[c], errors="coerce").astype("float32")
        pcs.append(t.pop("postcode").astype("category"))
        parts.append(t)
    df = pd.concat(parts, ignore_index=True); del parts
    df["postcode"] = union_categoricals(pcs); del pcs
    df["cell"] = (df.x // 10_000) * 1000 + df.y // 10_000
    cats = df.postcode.cat.categories; codes = df.postcode.cat.codes.to_numpy()
    for fam in sorted({POSTCODE[c] for c in cols if c in POSTCODE}):
        spec = SG.FAMILIES[fam]
        tab = pd.read_parquet(SG.ROOT / spec["table"])
        if spec.get("derive"):
            tab = getattr(SG, spec["derive"])(tab)
        tab = tab.drop_duplicates("postcode").set_index("postcode")
        if "km_pub" in tab.columns:
            tab["km_pub_far"] = tab.km_pub
        for c in cols:
            if POSTCODE.get(c) == fam:
                v = tab[c].reindex(cats).to_numpy(dtype="float32")
                df[c] = np.where(codes >= 0, v[np.clip(codes, 0, None)], np.nan).astype("float32")
    return df


def score(df, want):
    """Every house's national percentile on each characteristic, kept compact
    (half-precision, about 0.06 of a point near the top) so 28 million
    houses fit in memory: the fair middle rank, used for scoring, and the
    share of homes strictly worse, used for display."""
    ranks, below = {}, {}
    total = np.zeros(len(df), np.float32); weakest = np.full(len(df), np.inf, np.float32)
    n = len(df)
    for w in want:
        col, up, _ = CHAR[w]
        v = df[col].to_numpy(dtype="float32")
        s_ = pd.Series(v if up else -v)
        r = (s_.rank(pct=True, na_option="bottom").to_numpy() * 100).astype("float16")     # ties share the middle rank
        lo = ((s_.rank(method="min", na_option="bottom").to_numpy() - 1) / n * 100).astype("float16")
        ranks[w], below[w] = r, lo
        total += r; weakest = np.minimum(weakest, r)
        del s_
    df["score"] = (total / len(want)).astype("float64").round(2)
    df["weakest"] = weakest.astype("float64").round(1)
    return df, ranks, below


def describe(top, want, ranks, below):
    """Percentiles for the chosen houses only."""
    rows = top["_row"].to_numpy()
    for w in want:
        top[f"pct_{w}"] = ranks[w][rows].astype("float64").round(1)
        top[f"below_{w}"] = np.minimum(below[w][rows].astype("float64"), 99.9).round(1)
    return top


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--want", nargs="*", default=[], help=" ".join(CHAR))
    ap.add_argument("--all", action="store_true", help="every outlook, garden, light and landmark measure, clean air, "
                    "health services, green and blue space at once (add others by name, e.g. --all --want pubs_far)")
    ap.add_argument("--area", nargs="*", default=[], help="postcode areas to search, e.g. BA BS EX")
    ap.add_argument("--region", default=None, help=", ".join(REGION_AREAS))
    ap.add_argument("--houses-only", action="store_true", help="leave out buildings with several addresses (flats)")
    ap.add_argument("--sees", nargs="*", default=[], help="only homes with these landmarks in sight, by name, e.g. 'Exeter Cathedral'")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--every-house", action="store_true", help="allow several homes from one postcode")
    ap.add_argument("--out", default="research/outputs/national/best.csv")
    ap.add_argument("--draw", default=None, help="write a page with the top houses drawn")
    a = ap.parse_args()
    want = (ALL + [w for w in a.want if w not in ALL]) if a.all else a.want
    bad = [w for w in want if w not in CHAR]
    if not want or bad:
        sys.exit(f"choose from: {', '.join(CHAR)}" + (f" (unknown: {bad})" if bad else ""))
    df = load([CHAR[w][0] for w in want])
    df["_row"] = np.arange(len(df))
    df, ranks, below = score(df, want)                # percentiles are national, whatever area is searched
    cats = df.postcode.cat.categories.str.extract(r"^([A-Z]+)")[0].to_numpy()
    codes = df.postcode.cat.codes.to_numpy()
    area = pd.Series(np.where(codes >= 0, cats[np.clip(codes, 0, None)], ""))
    keep = np.ones(len(df), bool)
    areas = set(a.area) | (set(REGION_AREAS[a.region].split()) if a.region else set())
    if areas:
        keep &= area.isin(areas).to_numpy()
    if a.houses_only:
        keep &= (df.n_uprn == 1).to_numpy()
    if a.sees:
        lm = pd.read_parquet("research/data/landmarks/national_landmarks.parquet")
        for name in a.sees:
            lids = lm.lid[lm.name.str.lower() == name.lower()].to_numpy()
            if not len(lids):
                sys.exit(f"no landmark called {name!r}; close matches: "
                         f"{', '.join(lm.name[lm.name.str.lower().str.contains(name.lower()[:6])].head(8))}")
            near = lm[lm.lid.isin(lids)]
            cells_ = {(int(e) // 10_000 + dx) * 1000 + int(n) // 10_000 + dy for e, n in zip(near.e, near.n)
                      for dx in range(-3, 4) for dy in range(-3, 4)}
            seen = []
            for c in cells_:
                f = NAT / "cells" / f"{c // 1000}_{c % 1000}_sight.parquet"
                if f.exists():
                    t = pd.read_parquet(f); t = t[t.lid.isin(lids)]
                    seen.append(pd.DataFrame({"cell": c, "h3": t.hid.to_numpy()}))
            seen = pd.concat(seen) if seen else pd.DataFrame({"cell": [], "h3": []})
            ok = pd.MultiIndex.from_frame(df[["cell", "h3"]]).isin(pd.MultiIndex.from_frame(seen[["cell", "h3"]].astype(int)))
            keep &= ok
            print(f"{int(ok.sum()):,} homes have {name} in sight")
    top = df[keep].sort_values(["score", "weakest"], ascending=False)
    if not a.every_house:                             # one home per postcode, so one block of flats cannot fill the list
        top = top.drop_duplicates("postcode")
    top = top.head(a.top).reset_index(drop=True)
    top = describe(top, want, ranks, below).drop(columns=["_row"])
    cols = ["postcode", "storeys", "score", "weakest"] + [f"pct_{w}" for w in want]
    print(f"{int(keep.sum()):,} houses searched of {len(df):,} in England and Wales; asked for: {', '.join(want)}")
    print("Score = average national percentile of what was asked for; weakest = its lowest one.")
    print(top[cols].to_string(index=True))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    top.to_csv(a.out, index=False)
    if a.draw:
        import national_house_view as NHV
        NHV.write_many(top, a.draw, want=[(w, CHAR[w][2]) for w in want])
        print("drawn:", a.draw)


if __name__ == "__main__":
    main()
