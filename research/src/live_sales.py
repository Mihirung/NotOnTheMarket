"""The sale records brought up to date, for the live site.

The research table (data/transactions.parquet) is the Price Paid Data as it stood in January 2020 and
every test is aligned to it row for row, so it is left alone. This writes a second table beside it,
data/live/transactions.parquet, in the same layout: the research table's sales to 2018, and every year
from 2019 read afresh from HM Land Registry's yearly files. The Land Registry reissues those files
near the end of each month with the sales lodged to the end of the month before, late registrations
included, so the monthly refresh reads the last two years again and leaves the rest.

    python live_sales.py                 every year from 2019 not yet on disk, and the last two again,
                                         if the Land Registry has published since they were last read
    python live_sales.py --force         the same, whether or not it has
    python live_sales.py --status        what is held

Writes data/live/years/pp-<year>.parquet, data/live/transactions.parquet and data/live/sales.json.
Source: HM Land Registry Price Paid Data (Open Government Licence).
"""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from build_dataset import read_ppd  # noqa: E402

URL = "https://price-paid-data.publicdata.landregistry.gov.uk/pp-{y}.csv"
BASE = Path("research/data/transactions.parquet")
LIVE = Path("research/data/live")
FIRST = 2019                                              # the research table is complete to 2018
CATS = ("ptype", "postcode", "outcode", "county")


def registered(ym):
    """The share of each of the last six months' sales that is registered so far, judged against the same month
    a year before: {month (year * 12 + month - 1): share}. A sale reaches the register weeks or months after it
    completes, so the newest months of every file are part empty; export_site_v5.py counts each of their sales
    for the ones still to come (panel2's `late` weights; outputs/signals/LIVE_CHECK.md)."""
    lo, last = int(ym.min()), int(ym.max())
    n = np.bincount(ym - lo)
    return {last - k: round(min(1.0, float(n[last - k - lo] / max(n[last - k - 12 - lo], 1))), 3) for k in range(6)}


def published():
    """When the Land Registry last reissued this year's file (its Last-Modified header)."""
    r = subprocess.run(["curl", "-sS", "--fail", "-I", "-A", "research-client/1.0", URL.format(y=dt.date.today().year)],
                       check=True, capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.lower().startswith("last-modified:"):
            return line.split(":", 1)[1].strip()
    return ""


def fetch(y):
    """One year's file, parsed. The CSV is held on disk only while it is read."""
    tmp = LIVE / f"pp-{y}.csv.part"
    subprocess.run(["curl", "-sS", "--fail", "--retry", "4", "--retry-delay", "20", "-A", "research-client/1.0",
                    "-o", str(tmp), URL.format(y=y)], check=True)
    try:
        with open(tmp, "rb") as fh:
            df = read_ppd(fh)
    finally:
        tmp.unlink(missing_ok=True)
    return df[df.year == y].reset_index(drop=True)


def main():
    years_dir = LIVE / "years"; years_dir.mkdir(parents=True, exist_ok=True)
    info_f = LIVE / "sales.json"
    info = json.load(open(info_f)) if info_f.exists() else {}
    if sys.argv[1:] == ["--status"]:
        print(json.dumps(info, indent=1)); return
    this, stamp = dt.date.today().year, published()
    if stamp and stamp == info.get("published") and "--force" not in sys.argv:
        print(f"nothing new: the Land Registry's files are those of {stamp}, already read", flush=True); return
    for y in range(FIRST, this + 1):
        f = years_dir / f"pp-{y}.parquet"
        if f.exists() and y < this - 1:
            continue
        df = fetch(y)
        if len(df) == 0 and y == this:
            continue
        df.to_parquet(f, index=False)
        print(f"{y}: {len(df):,} standard residential sales", flush=True)
    parts = [pd.read_parquet(BASE)]
    parts[0] = parts[0][parts[0].year < FIRST]
    parts += [pd.read_parquet(f) for f in sorted(years_dir.glob("pp-*.parquet"))]
    for p in parts:
        for c in CATS:
            p[c] = p[c].astype(str)
    allx = pd.concat(parts, ignore_index=True); del parts
    for c in CATS:
        allx[c] = allx[c].astype("category")
    allx.sort_values(["key", "year", "month"], inplace=True, ignore_index=True)
    allx.to_parquet(LIVE / "transactions.parquet", index=False)
    ym = allx.year.astype(int) * 12 + allx.month.astype(int) - 1
    last = int(ym.max()); by = ym.value_counts()
    name = lambda m: f"{m // 12}-{m % 12 + 1:02d}"     # noqa: E731
    info = {"read_on": dt.date.today().isoformat(), "published": stamp, "sales": int(len(allx)), "homes": int(allx.key.nunique()),
            "last_month": name(last),
            "sales_in_each_of_the_last_six_months": {name(m): int(by.get(m, 0)) for m in range(last - 5, last + 1)},
            "registered_share": {name(m): q for m, q in sorted(registered(ym.to_numpy()).items())}}
    json.dump(info, open(info_f, "w"), indent=1)
    print(json.dumps(info), flush=True)


if __name__ == "__main__":
    main()
