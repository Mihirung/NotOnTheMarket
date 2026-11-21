"""Exact postcode and small-area codes for every address in England and Wales,
from the ONS UPRN Directory (open data).

The city runs gave each house the nearest postcode centre, which is
sometimes the next street's. The directory says which postcode each
address (UPRN) actually belongs to, and also its census output area and
LSOA, local authority, rural-urban class, output-area classification and
deprivation rank, which are ready-made signals for the national model.

Usage: python onsud_extract.py <onsud.zip> <out_dir>
"""
import sys
import zipfile
from pathlib import Path

import pandas as pd

COLS = ["UPRN", "PCDS", "LAD26CD", "OA21CD", "LSOA21CD", "MSOA21CD", "RUC21IND", "OAC21IND", "IMD25IND"]


def main(zip_path, out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        names = [m for m in z.namelist() if m.startswith("Data/") and m.endswith(".csv") and not m.endswith("_SC.csv")]
        for name in names:
            region = name.rsplit("_", 1)[1][:-4]
            if (out / f"{region}_done").exists():
                continue
            with z.open(name) as f:
                for k, ch in enumerate(pd.read_csv(f, usecols=COLS, chunksize=2_000_000, encoding="utf-8-sig",
                                                   dtype={c: "string" for c in COLS if c != "UPRN"} | {"UPRN": "int64"})):
                    ch.columns = [c.lower() for c in ch.columns]
                    ch.rename(columns={"pcds": "postcode"}).to_parquet(out / f"{region}_{k:03d}.parquet", index=False)
            (out / f"{region}_done").touch()
            print(region, "done", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:3])
