"""Later life around each home: the inputs for the LIFE family, whose columns
are worked out home by home and year by year (signals.life_rows).

Many homes are sold because the last person living there has died or moved
into care or to family. Who lives in a home is not public, but two things
narrow it down: how long the owner has had the home (from the sale records,
year by year) and the ages of the people living in its census output area.
An owner of 35 years is unlikely to be under 60; in an area where many
people are over 75, an owner of 35 years is likely to be one of them.

Static inputs, per postcode:
  ab_20_24 ... ab_90_plus   share of the output area's adults (20 and over) in each age band,
                            2011 Census KS102EW, before every test year
  alone_65, couple_65       households of one person aged 65+, and of older couples only (KS105EW)
  le65                      life expectancy at 65 in the local authority, men and women averaged,
                            2014-2016 (ONS)
  health_dep                health deprivation and disability score of the lower-layer area
                            (English Indices of Deprivation 2015; England only)
  older_income_dep          income deprivation affecting older people, rate (IDAOPI 2015; England only)

The family's columns, from these and each home's years of ownership in the
year in question:
  owner_age        expected age of the owner, given that they bought at 25 or older
  p_owner_75, p_owner_85   chance the owner is 75 or older, 85 or older
  p_exit           chance in the year that an owner of that age dies or moves into care,
                   from national death rates by age (a Gompertz curve through the 2014-2016
                   England and Wales life tables), moved by the local life expectancy at 65,
                   with moves into care taken as half as common as deaths at each age
  p_exit_alone     the same, times the share of older households that are one person
                   (a couple's home is usually sold only after the second of them)
  le65, health_dep, older_income_dep, alone_share   passed through

This family is for the sale-timing model's ranking only. It is not shown in
the search, on any page, or in anything sent to an owner.

Sources: ONS Census 2011 (Nomis); ONS life expectancy at birth and at 65 by
local areas, 2001-2003 to 2016-2018; MHCLG English Indices of Deprivation
2015 (all Open Government Licence).

Writes research/data/signals/life_postcode.parquet.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "research/src")
import people_signals as PS  # noqa: E402

D = Path("research/data/life")
OUT = Path("research/data/signals/life_postcode.parquet")
BANDS = ["ab_20_24", "ab_25_29", "ab_30_44", "ab_45_59", "ab_60_64", "ab_65_74", "ab_75_84", "ab_85_89", "ab_90_plus"]


def census():
    p = "KS102EW00"
    a = PS.table("ks102ew", {f"{p}{i}": b for i, b in zip(range(27, 36), BANDS)})
    a = a.div(a.sum(axis=1).replace(0, np.nan), axis=0)              # shares of adults 20+
    h = PS.table("ks105ew", {"KS105EW0017": "alone_65", "KS105EW0019": "couple_a", "KS105EW0030": "couple_b"})
    a["alone_65"] = h.alone_65 / 100
    a["couple_65"] = (h.couple_a + h.couple_b) / 100
    return a.astype("float32")


def le65():
    x = pd.ExcelFile(D / "le_la_201618.xlsx")
    out = []
    for s in ("LE at age 65 - Males", "LE at age 65 - Females"):
        t = pd.read_excel(x, s, header=None)
        hdr = t.index[t.iloc[:, 0].astype(str).str.strip() == "Area Codes"][0]
        cols = t.iloc[hdr].astype(str).str.strip().tolist()
        t = t.iloc[hdr + 1:]; t.columns = cols
        out.append(pd.to_numeric(t.set_index("Area Codes")["2014-2016"], errors="coerce"))
    return ((out[0] + out[1]) / 2).dropna().rename("le65")


def imd():
    t = pd.read_csv(D / "imd2015_file7.csv")
    c = {k: [x for x in t.columns if x.startswith(k)][0] for k in
         ("LSOA code", "Local Authority District code", "Health Deprivation and Disability Score",
          "Income Deprivation Affecting Older People (IDAOPI) Score")}
    return t.rename(columns={c["LSOA code"]: "lsoa", c["Local Authority District code"]: "lad13",
                             c["Health Deprivation and Disability Score"]: "health_dep",
                             c["Income Deprivation Affecting Older People (IDAOPI) Score"]: "older_income_dep"}
                    )[["lsoa", "lad13", "health_dep", "older_income_dep"]]


def main():
    c = census()
    oa, lsoa = c[c.index.str.match(r"^[EW]00")], c[c.index.str.match(r"^[EW]01")]
    pc = PS.postcode_areas()
    geo = pd.read_parquet("research/data/geo_postcode.parquet", columns=["postcode", "lsoa"]).merge(pc, on="postcode", how="left")
    vals = np.full((len(geo), c.shape[1]), np.nan, np.float32); done = np.zeros(len(geo), bool)
    for code, tab in (("oa21cd", oa), ("lsoa21cd", lsoa), ("lsoa", lsoa)):
        idx = tab.index.get_indexer(geo[code].where(~done).fillna(""))
        ok = ~done & (idx >= 0); vals[ok] = tab.to_numpy()[idx[ok]]; done |= ok
    o = pd.DataFrame(vals, columns=c.columns); o.insert(0, "postcode", geo.postcode.to_numpy())
    dep = imd()
    o = o.join(geo[["lsoa"]].merge(dep, on="lsoa", how="left")[["lad13", "health_dep", "older_income_dep"]])
    # local authority: from the 2015 deprivation file in England; Welsh postcodes take theirs from the address directory
    lad = o.lad13.copy()
    if lad.isna().any():
        import glob
        w = pd.concat([pd.read_parquet(f, columns=["postcode", "lad26cd"]) for f in glob.glob("research/data/onsud/parts/*.parquet")
                       ]).dropna().drop_duplicates("postcode").set_index("postcode").lad26cd
        lad = lad.fillna(o.postcode.map(w))
    o["le65"] = lad.map(le65()).astype("float32")
    o = o.drop(columns="lad13")
    num = o.columns.drop("postcode")
    o[num] = o[num].astype("float32")
    print(f"{done.mean():.1%} of postcodes have census ages; le65 for {o.le65.notna().mean():.1%}; "
          f"health_dep for {o.health_dep.notna().mean():.1%}")
    print(o[num].describe().T[["mean", "50%"]].round(3).to_string())
    o.to_parquet(OUT, index=False)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
