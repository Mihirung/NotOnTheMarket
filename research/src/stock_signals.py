"""The homes around each postcode: when they were built, what kind they are,
how many bedrooms and which council tax bands, from the Valuation Office
Agency's count of every home in each lower-layer area (about 650 homes) in
2016, before every test year.

Why it might matter for sale timing: estates built in one go fill with
buyers at the same stage of life, who then move at the same stage too; old
housing and new housing turn over at different rates; small homes are
outgrown, large ones are downsized from.

Columns (shares of the area's homes, %):
  built_pre1919, built_1919_44, built_1945_64, built_1965_82, built_1983_99,
  built_2000_09, built_2010_16   when built
  one_period                     share in the area's most common build period
                                 (one estate built at once scores high)
  bungalows, flats, terraced, semis, detached
  beds_1_2, beds_4_plus          bedrooms
  band_ab, band_fgh              council tax bands A-B and F-H

Source: Valuation Office Agency, Council Tax: stock of properties 2016,
tables CTSOP 3.1 and 4.1 (Open Government Licence).

Writes research/data/signals/stock_postcode.parquet.
"""
from pathlib import Path

import numpy as np
import pandas as pd

D = Path("research/data/stock")
OUT = Path("research/data/signals/stock_postcode.parquet")
PERIODS = {"built_pre1919": ["BP_PRE_1900", "BP_1900_1918"], "built_1919_44": ["BP_1919_1929", "BP_1930_1939"],
           "built_1945_64": ["BP_1945_1954", "BP_1955_1964"], "built_1965_82": ["BP_1965_1972", "BP_1973_1982"],
           "built_1983_99": ["BP_1983_1992", "BP_1993_1999"], "built_2000_09": ["BP_2000_2009"],
           "built_2010_16": ["BP_2010_2016"]}


def num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", "").replace({"-": "0", "..": "", "nan": ""}), errors="coerce")


def lsoa_table():
    b = pd.read_csv(D / "ctsop4_1_2016.csv", dtype=str, encoding="latin-1")
    b = b[b.GEOGRAPHY.str.upper().eq("LSOA")]
    allb = b[b.BAND == "All"].set_index("ECODE")
    tot = num(allb.ALL_PROPERTIES)
    out = pd.DataFrame(index=allb.index)
    raw = pd.DataFrame({k: sum(num(allb[c]) for c in cs) for k, cs in PERIODS.items()})
    known = raw.sum(axis=1).replace(0, np.nan)
    for k in PERIODS:
        out[k] = 100 * raw[k] / known
    out["one_period"] = 100 * raw.max(axis=1) / known
    bands = b[b.BAND.isin(list("ABCDEFGHI"))].assign(n=lambda t: num(t.ALL_PROPERTIES))
    bp = bands.pivot_table(index="ECODE", columns="BAND", values="n", aggfunc="sum").fillna(0)
    out["band_ab"] = 100 * (bp.get("A", 0) + bp.get("B", 0)) / tot
    out["band_fgh"] = 100 * (bp.get("F", 0) + bp.get("G", 0) + bp.get("H", 0) + bp.get("I", 0)) / tot
    t = pd.read_csv(D / "ctsop3_1_2016.csv", dtype=str, encoding="latin-1")
    t = t[t.GEOGRAPHY.str.upper().eq("LSOA") & (t.BAND == "All")].set_index("ECODE")
    tt = num(t.ALL_PROPERTIES)
    for k, c in (("bungalows", "BUNGALOW"), ("flats", "FLAT_MAIS"), ("terraced", "HOUSE_TERRACED"),
                 ("semis", "HOUSE_SEMI"), ("detached", "HOUSE_DETACHED")):
        out[k] = 100 * num(t[c]) / tt
    one2 = sum(num(t[f"TYPE_{k}_{i}"]) for k in ("BUNGALOW", "FLAT_MAIS", "HOUSE_TERRACED", "HOUSE_SEMI", "HOUSE_DETACHED")
               for i in (1, 2))
    four = sum(num(t[f"TYPE_{k}_4"]) for k in ("BUNGALOW", "FLAT_MAIS", "HOUSE_TERRACED", "HOUSE_SEMI", "HOUSE_DETACHED"))
    out["beds_1_2"] = 100 * one2 / tt
    out["beds_4_plus"] = 100 * four / tt
    return out.astype("float32")


def main():
    L = lsoa_table()
    geo = pd.read_parquet("research/data/geo_postcode.parquet", columns=["postcode", "lsoa"])
    o = geo.join(L, on="lsoa").drop(columns="lsoa")
    print(f"{L.shape[0]:,} lower-layer areas; {o.iloc[:, 1].notna().mean():.1%} of postcodes matched")
    print(o.describe().T[["mean", "50%"]].round(1).to_string())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    o.to_parquet(OUT, index=False)
    print(f"wrote {OUT}: {len(o):,} postcodes, {o.shape[1] - 1} columns")


if __name__ == "__main__":
    main()
