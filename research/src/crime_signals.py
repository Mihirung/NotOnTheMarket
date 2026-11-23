"""Crime around each postcode: recorded crime and anti-social behaviour in its
lower-layer area (about 1,500 residents), per 1,000 residents a year, over the
three years February 2014 to January 2017, before every test year.

Columns: crime_all, burglary, antisocial, violence, vehicle, damage, drugs,
theft (other theft and bicycle theft).

Police-recorded crime is placed at an anonymised point near where it
happened, and is counted in that point's area. Town centres have many
crimes and few residents, so their rates are high; the model sees the rate
as it is.

Source: data.police.uk street-level crime, archive of January 2017 (Open
Government Licence); resident population from the 2011 Census (KS102EW).

Writes research/data/signals/crime_postcode.parquet.
"""
import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ZIP = Path("research/data/crime/archive_2017-01.zip")
OUT = Path("research/data/signals/crime_postcode.parquet")
TYPES = {"Burglary": "burglary", "Anti-social behaviour": "antisocial", "Violence and sexual offences": "violence",
         "Violent crime": "violence", "Vehicle crime": "vehicle", "Criminal damage and arson": "damage",
         "Drugs": "drugs", "Other theft": "theft", "Bicycle theft": "theft"}
YEARS = 3.0


def counts():
    z = zipfile.ZipFile(ZIP)
    parts = []
    for f in z.namelist():
        if not f.endswith("-street.csv"):
            continue
        t = pd.read_csv(io.BytesIO(z.read(f)), usecols=["Month", "LSOA code", "Crime type"])
        t = t[(t.Month >= "2014-02") & (t.Month <= "2017-01")].dropna(subset=["LSOA code"])
        parts.append(t.groupby(["LSOA code", "Crime type"]).size())
    c = pd.concat(parts).groupby(level=[0, 1]).sum().rename("n").reset_index()
    c["kind"] = c["Crime type"].map(TYPES)
    allc = c.groupby("LSOA code").n.sum().rename("crime_all")
    kinds = c.dropna(subset=["kind"]).pivot_table(index="LSOA code", columns="kind", values="n", aggfunc="sum").fillna(0)
    return kinds.join(allc, how="outer").fillna(0)


def population():
    import sys
    sys.path.insert(0, "research/src")
    import people_signals as P
    t = P.table("ks102ew", {"KS102EW0001": "residents"})
    return t[t.index.str.match(r"^[EW]01")].residents


def main():
    c = counts()
    pop = population()
    rate = c.div(pop.reindex(c.index), axis=0) * 1000 / YEARS
    rate = rate[np.isfinite(rate.crime_all)].astype("float32")
    geo = pd.read_parquet("research/data/geo_postcode.parquet", columns=["postcode", "lsoa"])
    o = geo.join(rate, on="lsoa").drop(columns="lsoa")
    print(f"{len(rate):,} lower-layer areas with crime counts; {o.crime_all.notna().mean():.1%} of postcodes matched")
    print(o.describe().T[["mean", "50%"]].round(1).to_string())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    o.to_parquet(OUT, index=False)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
