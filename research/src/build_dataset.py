"""Build a compact property-transaction dataset from HM Land Registry Price Paid Data.

Input:  yearly pp-YYYY.csv.zip files (standard PPD column layout, no header).
Output: research/data/transactions.parquet with one row per residential
        transaction, linked to a stable property key.

Property linkage: PPD carries no property identifier, so we key on
(postcode, PAON, SAON) — the standard approach in the repeat-sales
literature for this dataset. Postcode reallocation and address-format
drift introduce some noise; in production UPRN matching via
AddressBase/EPC would replace this.

Usage: python build_dataset.py <ppd_zip_dir> <out_parquet>
"""

import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

COLS = [
    "tid", "price", "date", "postcode", "ptype", "is_new", "duration",
    "paon", "saon", "street", "locality", "town", "district", "county",
    "ppd_cat", "status",
]
USECOLS = ["price", "date", "postcode", "ptype", "is_new", "duration",
           "paon", "saon", "county", "ppd_cat"]


def load_year(zpath: Path) -> pd.DataFrame:
    with zipfile.ZipFile(zpath) as zf:
        name = zf.namelist()[0]
        with zf.open(name) as fh:
            df = pd.read_csv(
                fh, header=None, names=COLS, usecols=USECOLS,
                dtype={"price": "int64", "postcode": "string",
                       "paon": "string", "saon": "string"},
                keep_default_na=False, na_values=[],
            )
    # Standard residential sales only: category A, known property type,
    # positive price, valid postcode.
    df = df[(df["ppd_cat"] == "A") & (df["ptype"] != "O") & (df["price"] > 0)]
    df = df[df["postcode"].str.len() >= 5]

    pc = df["postcode"].str.strip().str.upper()
    key_str = (pc + "|" + df["paon"].str.strip().str.upper()
               + "|" + df["saon"].str.strip().str.upper())
    ts = pd.to_datetime(df["date"], format="%Y-%m-%d %H:%M", errors="coerce")

    out = pd.DataFrame({
        "key": pd.util.hash_array(key_str.to_numpy(dtype=object)).astype("int64"),
        "year": ts.dt.year.astype("int16"),
        "month": ts.dt.month.astype("int8"),
        "price": df["price"].astype("int64"),
        "ptype": df["ptype"].astype("category"),
        "is_new": (df["is_new"] == "Y"),
        "leasehold": (df["duration"] == "L"),
        # Full postcode (~15 households) and district ("outcode", e.g. SS2).
        "postcode": pc.astype("category"),
        "outcode": pc.str.split(" ").str[0].astype("category"),
        "county": df["county"].astype("category"),
    })
    return out.dropna(subset=["year"])


def main(zip_dir: str, out_path: str) -> None:
    frames = []
    for zpath in sorted(Path(zip_dir).glob("pp-*.csv.zip")):
        df = load_year(zpath)
        frames.append(df)
        print(f"{zpath.name}: {len(df):,} category-A residential rows", flush=True)
    allx = pd.concat(frames, ignore_index=True)
    # Re-unify category dtypes across years.
    for c in ("ptype", "postcode", "outcode", "county"):
        allx[c] = allx[c].astype("category")
    allx.sort_values(["key", "year", "month"], inplace=True, ignore_index=True)
    allx.to_parquet(out_path, index=False)
    print(f"total: {len(allx):,} transactions, "
          f"{allx['key'].nunique():,} unique properties -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
