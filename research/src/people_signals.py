"""Who lives around each postcode, from the 2011 Census: life stage, household
type, tenure, spare bedrooms, work and cars.

Why 2011 and not 2021: the model is tested on sales in 2017 to 2019. A 2021
census already shows who moved in after those sales, so it would hand the
test its own answers. The 2011 Census was taken before every test year.

Each postcode takes its census output area (about 125 households) from the
ONS UPRN Directory: the output area most of its addresses are in. Output
areas whose 2021 code is new (split or merged since 2011) fall back to their
2011 lower-layer area (about 650 households), and then to the postcode's
lower-layer area in the AHAH table.

Marital status and area health are included (a separation or a death is a
common reason to sell). Ethnicity and religion are written to a separate
family, COMMUNITY (community_postcode.parquet), which is measured but never
deployed automatically: using them to choose whom to approach needs legal
sign-off first, and its main use is to check the model treats communities
fairly (audit_fairness.py).

Source: Office for National Statistics, Census 2011 key and quick statistics
tables KS102EW, KS105EW, KS402EW, QS412EW, KS601EW, KS403EW, KS404EW, KS103EW,
KS301EW, KS201EW, KS209EW, from
Nomis bulk downloads (Open Government Licence).

Writes research/data/signals/people_postcode.parquet and community_postcode.parquet.

Usage: python people_signals.py
"""
import glob
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

D = Path("research/data/census/2011")
ONSUD = "research/data/onsud/parts"
OUT = Path("research/data/signals/people_postcode.parquet")


def table(name, cols):
    """{column code: our name} from one census table, for every output area and lower-layer area."""
    z = zipfile.ZipFile(D / f"{name}.zip")
    names = [i.filename for i in z.infolist()]
    whole = [f for f in names if f.upper().endswith(f"{name.upper()}DATA.CSV")]
    files = whole or [f for f in names if re.search(r"DATA\d+(_[A-Z])?\.CSV$", f.upper())]   # split by kind of area
    t = pd.concat([pd.read_csv(z.open(f), usecols=["GeographyCode"] + list(cols), encoding="latin-1") for f in files])
    t = t[t.GeographyCode.str.match(r"^[EW]0[01]")].drop_duplicates("GeographyCode")
    return t.set_index("GeographyCode").rename(columns=cols).astype("float32")


def census():
    p = "KS102EW00"
    age = table("ks102ew", {f"{p}{i:02d}": n for i, n in [(20, "a0"), (21, "a5"), (22, "a8"), (23, "a10"), (24, "a15"),
                                                          (27, "a20"), (28, "a25"), (29, "a30"), (30, "a45"),
                                                          (31, "a60"), (32, "age_65_74"), (33, "age_75_84"),
                                                          (34, "a85"), (35, "a90"), (19, "median_age")]})
    out = pd.DataFrame(index=age.index)
    out["children"] = age[["a0", "a5", "a8", "a10", "a15"]].sum(axis=1)
    out["age_20_29"] = age.a20 + age.a25
    out["age_30_44"] = age.a30
    out["age_45_59"] = age.a45
    out["age_60_64"] = age.a60
    out["age_65_74"] = age.age_65_74
    out["age_75_84"] = age.age_75_84
    out["age_85_plus"] = age.a85 + age.a90
    out["median_age"] = age.median_age
    q = "KS105EW00"
    hh = table("ks105ew", {f"{q}{i}": f"h{i}" for i in range(17, 32)})
    out["hh_alone_65"] = hh.h17
    out["hh_alone_under_65"] = hh.h18
    out["hh_couple_65"] = hh.h19 + hh.h30
    out["hh_couple_no_children"] = hh.h20 + hh.h23
    out["hh_young_children"] = hh.h21 + hh.h24 + hh.h26 + hh.h28            # dependent children
    out["hh_grown_children"] = hh.h22 + hh.h25 + hh.h27                     # children all grown up: the nest about to empty
    out["hh_lone_parent"] = hh.h26
    out["hh_students"] = hh.h29
    r = "KS402EW00"
    ten = table("ks402ew", {f"{r}10": "own_outright", f"{r}11": "own_mortgage", f"{r}12": "shared",
                            f"{r}13": "council", f"{r}14": "housing_assoc", f"{r}15": "private_let", f"{r}16": "other_let"})
    out["own_outright"] = ten.own_outright
    out["own_mortgage"] = ten.own_mortgage
    out["social_rent"] = ten.council + ten.housing_assoc
    out["private_rent"] = ten.private_let + ten.other_let
    occ = table("qs412ew", {f"QS412EW000{i}": f"o{i}" for i in range(1, 7)})
    out["spare_2_bedrooms"] = 100 * occ.o2 / occ.o1                          # two or more bedrooms more than needed
    out["overcrowded"] = 100 * (occ.o5 + occ.o6) / occ.o1
    w = "KS601EW00"
    work = table("ks601ew", {f"{w}21": "retired", f"{w}18": "self_employed", f"{w}19": "unemployed",
                             f"{w}24": "long_term_sick", f"{w}20": "ft_student", f"{w}22": "student_inactive"})
    out["retired"] = work.retired
    out["self_employed"] = work.self_employed
    out["unemployed"] = work.unemployed
    out["students"] = work.ft_student + work.student_inactive
    rooms = table("ks403ew", {"KS403EW0006": "hh_size", "KS403EW0007": "rooms", "KS403EW0008": "bedrooms",
                              "KS403EW0009": "no_central_heating"})
    out = out.join(rooms)
    cars = table("ks404ew", {"KS404EW0001": "households", "KS404EW0007": "cars", "KS404EW0008": "no_car"})
    out["no_car"] = cars.no_car
    out["cars_per_household"] = cars.cars / cars.households
    m = "KS103EW00"
    mar = table("ks103ew", {f"{m}08": "single", f"{m}09": "married", f"{m}11": "separated", f"{m}12": "divorced",
                            f"{m}13": "widowed"})
    out["married"] = mar.married
    out["separated_divorced"] = mar.separated + mar.divorced
    out["widowed"] = mar.widowed
    out["never_married"] = mar.single
    h = "KS301EW00"
    hl = table("ks301ew", {f"{h}17": "limited_lot", f"{h}26": "bad", f"{h}27": "very_bad", f"{h}30": "care20",
                           f"{h}31": "care50"})
    out["bad_health"] = hl.bad + hl.very_bad
    out["limited_a_lot"] = hl.limited_lot
    out["carers_20h"] = hl.care20 + hl.care50
    return out.astype("float32")


def community():
    """Ethnicity and religion shares, and how mixed the area is (COMMUNITY family)."""
    e = "KS201EW00"
    eth = table("ks201ew", {f"{e}{i}": f"e{i}" for i in range(20, 38)})
    o = pd.DataFrame(index=eth.index)
    o["white_british"] = eth.e20
    o["white_other"] = eth.e21 + eth.e22 + eth.e23
    o["mixed"] = eth[["e24", "e25", "e26", "e27"]].sum(axis=1)
    o["indian"] = eth.e28
    o["pakistani"] = eth.e29
    o["bangladeshi"] = eth.e30
    o["chinese"] = eth.e31
    o["other_asian"] = eth.e32
    o["black_african"] = eth.e33
    o["black_caribbean"] = eth.e34 + eth.e35
    o["other_ethnic"] = eth.e36 + eth.e37
    sh = eth.div(100)
    o["ethnic_mix"] = 1 - (sh ** 2).sum(axis=1)                              # chance two residents differ
    r = "KS209EW00"
    rel = table("ks209ew", {f"{r}{i}": n for i, n in zip(range(11, 20), ["christian", "buddhist", "hindu", "jewish",
                                                                         "muslim", "sikh", "other_religion",
                                                                         "no_religion", "religion_not_stated"])})
    return o.join(rel).astype("float32")


def postcode_areas():
    """Each postcode's main output area and lower-layer area (2021 codes, mostly the same as 2011)."""
    parts = []
    for f in sorted(glob.glob(f"{ONSUD}/*.parquet")):
        t = pd.read_parquet(f, columns=["postcode", "oa21cd", "lsoa21cd"]).dropna()
        parts.append(t.groupby(["postcode", "oa21cd", "lsoa21cd"]).size().rename("n").reset_index())
    t = pd.concat(parts).groupby(["postcode", "oa21cd", "lsoa21cd"]).n.sum().reset_index()
    return t.sort_values("n", ascending=False).drop_duplicates("postcode")[["postcode", "oa21cd", "lsoa21cd"]]


def main():
    pc = postcode_areas()
    geo = pd.read_parquet("research/data/geo_postcode.parquet", columns=["postcode", "lsoa"])
    pc = geo.merge(pc, on="postcode", how="left")
    write(census(), pc, OUT)
    write(community(), pc, OUT.with_name("community_postcode.parquet"))


def write(c, pc, out_path):
    oa = c[c.index.str.match(r"^[EW]00")]; lsoa = c[c.index.str.match(r"^[EW]01")]
    cols = list(c.columns)
    vals = np.full((len(pc), len(cols)), np.nan, np.float32)
    how = np.zeros(len(pc), np.int8)
    for code, table_, tag in (("oa21cd", oa, 1), ("lsoa21cd", lsoa, 2), ("lsoa", lsoa, 3)):
        todo = how == 0
        hit = pc[code].where(todo).map(lambda k: k if isinstance(k, str) else None)
        idx = table_.index.get_indexer(hit.fillna(""))
        ok = todo & (idx >= 0)
        vals[ok] = table_.to_numpy()[idx[ok]]
        how[ok] = tag
    o = pd.DataFrame(vals, columns=cols)
    o.insert(0, "postcode", pc.postcode.to_numpy())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    o.to_parquet(out_path, index=False)
    share = {1: "2011 output area", 2: "2011 lower-layer area (output area changed)", 3: "lower-layer area from AHAH", 0: "none"}
    for k, v in share.items():
        print(f"  {v}: {(how == k).mean():.1%} of postcodes")
    print(o[cols].describe().T[["mean", "50%"]].round(2).to_string())
    print(f"wrote {out_path}: {len(o):,} postcodes, {len(cols)} columns")


if __name__ == "__main__":
    main()
