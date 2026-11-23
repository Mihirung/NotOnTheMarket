"""AREA15: the area family rebuilt from sources dated before every test year,
and without the census area classification.

The AREA family the model was deployed with used the 2025 deprivation rank
and the 2021 census output-area classification. Both come after the
2017-2019 test years, and the classification is built partly from ethnic
make-up, which should not decide whom a buyer writes to. This family keeps
what is wanted and drops the rest:

  imd_score_15         Index of Multiple Deprivation 2015 score
  income_15, employment_15, education_15, health_15, crime_15,
  barriers_15, living_env_15   its seven domain scores
  idaci_15, idaopi_15  income deprivation affecting children, and older people
  rural                share of the postcode's addresses in a rural area (kept from AREA:
                       a settlement's form, not its people)

England only for the 2015 scores (Wales has its own index on a different
scale); Welsh postcodes are left blank for them.

Source: MHCLG English Indices of Deprivation 2015, file 7 (OGL).

Writes research/data/signals/area15_postcode.parquet.
"""
from pathlib import Path

import pandas as pd

COLS = {"Index of Multiple Deprivation (IMD) Score": "imd_score_15", "Income Score (rate)": "income_15",
        "Employment Score (rate)": "employment_15", "Education, Skills and Training Score": "education_15",
        "Health Deprivation and Disability Score": "health_15", "Crime Score": "crime_15",
        "Barriers to Housing and Services Score": "barriers_15", "Living Environment Score": "living_env_15",
        "Income Deprivation Affecting Children Index (IDACI) Score (rate)": "idaci_15",
        "Income Deprivation Affecting Older People (IDAOPI) Score (rate)": "idaopi_15"}
OUT = Path("research/data/signals/area15_postcode.parquet")


def main():
    t = pd.read_csv("research/data/life/imd2015_file7.csv")
    t.columns = [c.strip().replace("\n", " ") for c in t.columns]
    ren = {c: COLS[k] for c in t.columns for k in COLS if c.replace('"', "").strip() == k}
    lsoa = [c for c in t.columns if c.startswith("LSOA code")][0]
    t = t.rename(columns=ren).rename(columns={lsoa: "lsoa"}).set_index("lsoa")[list(COLS.values())]
    geo = pd.read_parquet("research/data/geo_postcode.parquet", columns=["postcode", "lsoa"])
    o = geo.join(t, on="lsoa").drop(columns="lsoa")
    area = pd.read_parquet("research/data/signals/area_postcode.parquet", columns=["postcode", "rural"])
    o = o.merge(area, on="postcode", how="left")
    o[o.columns[1:]] = o[o.columns[1:]].astype("float32")
    print(f"{o.imd_score_15.notna().mean():.1%} of postcodes have 2015 scores; rural for {o.rural.notna().mean():.1%}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    o.to_parquet(OUT, index=False)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
