"""Extract the Exeter (EX1-EX4) slice of the Price Paid Data into the
same linked-transaction format as build_dataset.py, for local experiments.

Usage: python build_exeter_tx.py <ppd_zip_dir> <out_parquet>
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from build_dataset import load_year  # noqa: E402

OUTCODES = ("EX1", "EX2", "EX3", "EX4")


def main(zip_dir, out_path):
    frames = []
    for z in sorted(Path(zip_dir).glob("pp-*.csv.zip")):
        df = load_year(z)
        df = df[df["outcode"].astype(str).isin(OUTCODES)]
        frames.append(df)
        print(f"{z.name}: {len(df):,} Exeter rows", flush=True)
    allx = pd.concat(frames, ignore_index=True)
    for c in ("ptype", "postcode", "outcode", "county"):
        allx[c] = allx[c].astype(str).astype("category")
    allx.sort_values(["key", "year", "month"], inplace=True, ignore_index=True)
    allx.to_parquet(out_path, index=False)
    print(f"total {len(allx):,} transactions, {allx['key'].nunique():,} properties -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
