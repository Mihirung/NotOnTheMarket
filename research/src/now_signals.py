"""Crime and schools as they are now, for search. Not for the model.

The model's CRIME and SCHOOLS families are frozen before the test years
(crime 2014-2017, Ofsted grades at August 2016) so that the model cannot see
the future. A buyer choosing where to live wants today's picture, so search
uses this file instead:

  crime_all, burglary   recorded crime and anti-social behaviour (all) and
                        burglary per 1,000 residents a year in the postcode's
                        lower-layer area, over the 36 months in the latest
                        police archive. Months a force did not publish are left
                        out of its rate, and an area with no records at all is
                        left blank rather than read as crime-free.
  km_primary_good,      to the nearest state primary or secondary rated good
  km_secondary_good     or better at its latest inspection
  good_primaries_2km    state primaries rated good or better within 2 km
  n_addr                addresses in the postcode (for weighting sectors)

"Good or better" for a school inspected under the report cards that began in
November 2025: no area judged "needs attention" or "urgent improvement".
For one last inspected before then: an overall grade of good or outstanding,
or, where no overall grade was given (September 2024 to November 2025),
quality of education good or outstanding. For one last graded before
September 2019, the outcome of its later ungraded visits (still good or
outstanding, standards maintained, or improved). Welsh schools are inspected by
Estyn without grades, so Welsh postcodes are left blank.

Sources: data.police.uk archive (Open Government Licence); Census 2021 usual
residents by lower-layer area (TS001, ONS); Ofsted, state-funded schools
management information, latest inspections (OGL); Department for Education,
Get Information about Schools (OGL); ONS UPRN Directory.

    python now_signals.py <police_archive.zip> <ofsted_latest.csv>

Writes research/data/signals/now_postcode.parquet.
"""
import io
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from schools_access_signals import count_within, nearest_km, postcodes  # noqa: E402

OUT = Path("research/data/signals/now_postcode.parquet")
BAD = {"Needs attention", "Urgent improvement"}
AREAS = ["Inclusion", "Curriculum and teaching", "Achievement", "Attendance and behaviour",
         "Personal development and wellbeing", "Leadership and governance"]


def lsoa_of_postcode():
    """Each postcode's lower-layer area (2021) and address count, from the UPRN directory."""
    parts = []
    for f in sorted(Path("research/data/onsud/parts").glob("*.parquet")):
        t = pd.read_parquet(f, columns=["postcode", "lsoa21cd"])
        parts.append(t.groupby(["postcode", "lsoa21cd"], observed=True).size())
    c = pd.concat(parts).groupby(level=[0, 1]).sum().rename("n").reset_index()
    n_addr = c.groupby("postcode").n.sum()
    top = c.sort_values("n", ascending=False).drop_duplicates("postcode").set_index("postcode").lsoa21cd
    return pd.DataFrame({"lsoa21": top, "n_addr": n_addr.reindex(top.index)})


def crime(archive):
    z = zipfile.ZipFile(archive)
    files = [f for f in z.namelist() if f.endswith("-street.csv")]
    months = sorted({f.split("/")[0] for f in files})
    force_months = {}
    parts = []
    for f in files:
        force = re.sub(r"^\d{4}-\d{2}-", "", Path(f).stem).removesuffix("-street")
        force_months.setdefault(force, set()).add(f.split("/")[0])
        t = pd.read_csv(io.BytesIO(z.read(f)), usecols=["LSOA code", "Crime type"]).dropna(subset=["LSOA code"])
        if len(t):
            g = t.groupby(["LSOA code", "Crime type"]).size().rename("n").reset_index()
            g["force"] = force
            parts.append(g)
    c = pd.concat(parts)
    # each area's months: those its main force published (areas on a border take their main force)
    main = c.groupby(["LSOA code", "force"]).n.sum().reset_index().sort_values("n", ascending=False).drop_duplicates("LSOA code")
    nm = main.set_index("LSOA code").force.map({k: len(v) for k, v in force_months.items()})
    allc = c.groupby("LSOA code").n.sum()
    burg = c[c["Crime type"] == "Burglary"].groupby("LSOA code").n.sum().reindex(allc.index).fillna(0)
    z2 = zipfile.ZipFile("research/data/census/2021/census2021-ts001.zip")
    pop = pd.read_csv(z2.open("census2021-ts001-lsoa.csv"))
    pop = pop.set_index("geography code")[[c_ for c_ in pop.columns if "Total" in c_][0]]
    years = nm.reindex(allc.index) / 12
    rate = pd.DataFrame({"crime_all": allc / years / pop.reindex(allc.index) * 1000,
                         "burglary": burg / years / pop.reindex(allc.index) * 1000})
    rate = rate[np.isfinite(rate.crime_all)].astype("float32")
    short = {k: len(v) for k, v in force_months.items() if len(v) < len(months)}
    print(f"crime: {months[0]} to {months[-1]}, {len(force_months)} forces; forces with missing months: {short or 'none'}; "
          f"{len(rate):,} areas with a rate", flush=True)
    return rate


def schools(ofsted):
    o = pd.read_csv(ofsted, encoding="latin-1", low_memory=False)
    o.columns = [c.replace("ï»¿", "") for c in o.columns]
    card = o[AREAS].notna().any(axis=1)
    card_ok = ~o[AREAS].isin(BAD).any(axis=1)
    oe = pd.to_numeric(o["Latest OEIF overall effectiveness"], errors="coerce")
    qe = pd.to_numeric(o["Latest OEIF quality of education"], errors="coerce")
    old_ok = oe.le(2) | (oe.isna() & qe.le(2))
    graded = oe.notna() | qe.notna()
    # schools last graded before September 2019 carry only the outcome of their later ungraded visits
    ung = o["Ungraded inspection overall outcome"].fillna("")
    ung_ok = ung.str.startswith("School remains") | ung.isin(["Standards maintained", "Improved significantly", "Some aspects not as strong"])
    o["good"] = np.where(card, card_ok, np.where(graded, old_ok, ung_ok))
    o["basis"] = np.where(card, "report card", np.where(graded, "graded", np.where(ung != "", "ungraded", "none")))
    print(o.groupby("basis").good.agg(["size", "mean"]).round(2).to_string(), flush=True)
    g = pd.read_csv("research/data/schools/gias.csv", encoding="latin-1", low_memory=False,
                    usecols=["URN", "EstablishmentStatus (name)", "Easting", "Northing"])
    s = o.merge(g[g["EstablishmentStatus (name)"].str.startswith("Open")], on="URN", how="inner").dropna(subset=["Easting", "Northing"])
    pcs, xy = postcodes()
    E = lambda m: s.loc[m, ["Easting", "Northing"]].to_numpy(float)          # noqa: E731
    prim, sec, good = s["Ofsted phase"] == "Primary", s["Ofsted phase"] == "Secondary", s.good.astype(bool)
    out = pd.DataFrame({"postcode": pcs})
    out["km_primary_good"] = nearest_km(E(prim & good), xy)
    out["km_secondary_good"] = nearest_km(E(sec & good), xy)
    out["good_primaries_2km"] = count_within(E(prim & good), xy, 2000)
    for c in ("km_primary_good", "km_secondary_good", "good_primaries_2km"):
        out.loc[postcodes.wales, c] = np.nan
    print(f"schools: {len(s):,} open and inspected; good or better: {good[prim].mean():.0%} of primaries, "
          f"{good[sec].mean():.0%} of secondaries; {card.mean():.0%} have a report card", flush=True)
    return out


def main(archive, ofsted):
    lk = lsoa_of_postcode()
    out = schools(ofsted).set_index("postcode")
    out = out.join(lk, how="left")
    out = out.join(crime(archive), on="lsoa21").drop(columns="lsoa21").reset_index()
    out["n_addr"] = out.n_addr.fillna(0).astype("int32")
    print(f"{len(out):,} postcodes; crime matched for {out.crime_all.notna().mean():.1%}", flush=True)
    print(out.describe().T[["mean", "25%", "50%", "75%"]].round(2).to_string(), flush=True)
    out.to_parquet(OUT, index=False)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
