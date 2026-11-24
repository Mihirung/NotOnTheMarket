"""Homes named in a notice that the sale records do not hold: no sale since 1995 when the year began.

The model scores only homes with a sale on record. A deceased estate is very often a home held for
decades, so most of those notices point to homes the model cannot see at all. This measures how
often such a home is sold (its first sale on record) in the year after 1 January, by how long
before that day the notice appeared. The product can then count these homes in, each at the rate
measured here (export_site_v5.py).

Rates are lower bounds: an address that fails to match its later sale record counts as not sold.
Only counts and rates are written out.

    python notice_unseen.py

Writes research/outputs/signals/NOTICE_UNSEEN.json and .md, and the rates the product uses to
research/outputs/lab/notice_unseen.json.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import notice_signals as NS  # noqa: E402

OUT, LAB = Path("research/outputs/signals"), Path("research/outputs/lab")
YEARS = (2017, 2018)
MONTHS = [(1, 6), (7, 12), (13, 24), (25, 36), (37, 48)]
KIND = {"bk": "Bankruptcy order", "dec": "Deceased-estate notice"}
MIN_HOMES = 300                                         # a band needs this many homes before the product uses its rate


def main():
    tx = pd.read_parquet(NS.TX, columns=["key", "year", "month", "postcode"])
    ew = set(tx.postcode.cat.categories.astype(str))    # postcodes with a sale on record: England and Wales
    tx["ym"] = tx.year.astype(np.int64) * 12 + tx.month.astype(np.int64) - 1
    R, rates, md_rows = {"years": list(YEARS), "kinds": {}}, {}, []
    for k in NS.KINDS:
        if not (NS.DIRS[k] / "listing.jsonl").exists():
            continue
        t = NS.linked(k, every=True)
        t = t[t.postcode.isin(ew)].reset_index(drop=True)
        first = tx[tx.key.isin(set(t.key[t.has]))].groupby("key").ym.min()
        f = np.where(t.has, t.key.map(first).fillna(10**9).to_numpy(), 10**9).astype(np.int64)   # month of the first sale on record
        res, got = [], {}
        for a, b in MONTHS:
            n = s = late = 0
            blocks = []
            for T in YEARS:
                t0 = T * 12
                m = (t.ym.to_numpy() <= t0 - a) & (t.ym.to_numpy() >= t0 - b) & (f >= t0)          # no sale on record when the year began
                sold = (f[m] >= t0) & (f[m] < t0 + 12)
                n += int(m.sum()); s += int(sold.sum()); late += int(((f[m] >= t0 + 6) & (f[m] < t0 + 18)).sum())
                blocks.append(sold)
            if n < 50:
                continue
            sold = np.concatenate(blocks)
            rng = np.random.default_rng(3); bs = [sold[rng.integers(0, len(sold), len(sold))].mean() for _ in range(1000)]
            r = {"published": f"{a} to {b} months before", "homes": n, "first_sold_in_the_year": s, "rate": round(s / n, 4),
                 "range": [round(float(np.percentile(bs, q)), 4) for q in (2.5, 97.5)], "completes_july_to_june": round(late / n, 4)}
            res.append(r)
            if n >= MIN_HOMES:
                got[f"{a}-{b}"] = r["rate"]
            md_rows.append(f"| {KIND[k]} | {r['published']} | {n:,} | {100 * r['rate']:.1f}% ({100 * r['range'][0]:.1f} to {100 * r['range'][1]:.1f}) | "
                           f"{100 * r['completes_july_to_june']:.1f}% |")
            print(k, r, flush=True)
        R["kinds"][k] = {"notices_in_england_and_wales": int(len(t)), "share_with_no_home_on_record": round(float((~t.has).mean()), 3), "bands": res}
        rates[k] = got
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(OUT / "NOTICE_UNSEEN.json", "w"), indent=1)
    json.dump({"what": "share first sold in the calendar year, by months from the notice to 1 January; homes with no sale on record",
               "years": list(YEARS), "min_homes": MIN_HOMES, "rates": rates}, open(LAB / "notice_unseen.json", "w"), indent=1)
    md = ["# Homes named in a notice that the sale records do not hold", "",
          "The model scores only homes with a sale on record since 1995. These are the others: homes named in a notice with no",
          f"sale on record when the year began, {YEARS[0]} and {YEARS[1]} together. A home with no notice and no sale on record",
          "cannot be measured the same way; homes that do have a record sell at about 4.4% a year.", "",
          "| Notice | Published | Homes | First sold in the year (95% range) | Completes July to June |", "|---|---|---|---|---|", *md_rows, "",
          "Lower bounds: an address that fails to match its later sale record counts as not sold.", ""]
    (OUT / "NOTICE_UNSEEN.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
