"""How soon after a notice in The Gazette a home is sold.

The model scores homes once a year, on 1 January, so a notice is anything from one to twelve months
old before it is read. This asks the question the product would ask if it read notices as they are
published: of the addresses first named in a notice, what share complete a sale in each stretch of
months after it?

Addresses first named in 2015 to 2017 are followed in the sale records to their end. Care and
nursing homes are left out. An address with no sale on record at all counts as not sold, so the
shares are lower bounds. Only counts and shares are written out.

    python notice_timing.py
    python notice_timing.py live <first year> <last year>     the same for recent notices, on the up-to-date sale
                                                              records (live_sales.py); writes NOTICE_TIMING_LIVE

Writes research/outputs/signals/NOTICE_TIMING.json and .md.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import notice_signals as NS  # noqa: E402

OUT = Path("research/outputs/signals")
FIRST, LAST = 2015, 2017                                # notices first published in these years
NAME = "NOTICE_TIMING"
SPANS = [(0, 2), (3, 5), (6, 11), (12, 23), (24, 35)]   # months after the notice
KIND = {"bk": "Bankruptcy orders", "dec": "Deceased-estate notices"}


def shares(g, end):
    """Shares of the addresses in g completing a sale in each span, using only notices with the whole span on record."""
    out = {"addresses": int(len(g))}
    for a, b in SPANS:
        gg = g[g.ym + b <= end]
        out[f"{a}_to_{b}"] = round(float(((gg.next >= a) & (gg.next <= b)).mean()), 4) if len(gg) else None
    for m in (12, 24, 36):
        gg = g[g.ym + m - 1 <= end]
        out[f"within_{m}"] = round(float((gg.next < m).mean()), 4) if len(gg) else None
    return out


def main():
    tx = NS.sales(columns=("key", "year", "month"))
    end = int(tx.ym.max())
    R = {"notices_first_published": [FIRST, LAST], "sales_to": f"{end // 12}-{end % 12 + 1:02d}", "kinds": {}}
    pc = lambda x: "" if x is None else f"{100 * x:.1f}%"               # noqa: E731
    md = ["# How soon after a notice a home is sold", "",
          f"Addresses first named in a notice in {FIRST} to {LAST}, care and nursing homes apart, followed in the sale records to",
          f"{R['sales_to']}. Each figure is the share of addresses completing a sale in that stretch of months after the notice.",
          "The three-year figure uses only the notices with three years of sales after them. A home with a sale on record sells",
          "at about 4% a year, so about 4% within 12 months, 8% within 24 and 12% within 36.", ""]
    if NS.LIVE:
        md[-1:] = ["The last six months of these sale records are only part registered (live_sales.py), so the figures that reach",
                   "into them are low.", ""]
    for k in NS.KINDS:
        if not (NS.DIRS[k] / "listing.jsonl").exists():
            continue
        t = NS.linked(k, every=True)
        t = t[~t.care & (t.key != 0)].sort_values("ym").drop_duplicates("key", keep="first")            # the first notice at each address
        t = t[(t.ym >= FIRST * 12) & (t.ym < (LAST + 1) * 12)].reset_index(drop=True)
        if len(t) < 1000:
            continue
        s = tx[tx.key.isin(set(t.key[t.has]))][["key", "ym"]].merge(t[["key", "ym"]].rename(columns={"ym": "n_ym"}), on="key")
        s["d"] = s.ym - s.n_ym
        t["next"] = t.key.map(s[s.d >= 0].groupby("key").d.min())      # months to the next sale (blank: none on record)
        t["prev"] = t.key.map(s[s.d < 0].groupby("key").d.max())       # months since the last sale before it (negative)
        on = t.prev.notna()
        groups = [("Every address", t), ("A sale on record before the notice", t[on]),
                  ("The same, not sold in the 12 months before it", t[on & ~(t.prev >= -12)]),
                  ("No sale on record before the notice", t[~on]),
                  ("The same, not a flat or a named block", t[~on & (t.flat == 0)])]
        rows = [{"homes": name, **shares(g, end)} for name, g in groups]
        r = t[on & ~(t.prev >= -12)]
        by_month = np.bincount(r.next.dropna().astype(int).clip(upper=24), minlength=25)[:24] / max(len(r), 1)
        R["kinds"][k] = {"rows": rows, "sold_in_the_12_months_before": round(float((t.prev[on] >= -12).mean()), 4),
                         "share_by_month_after_on_record_not_just_sold": [round(float(x), 4) for x in by_month]}
        md += [f"## {KIND[k]}", "",
               "| Addresses | Number | 0 to 2 months | 3 to 5 | 6 to 11 | 12 to 23 | 24 to 35 | Within 12 months | Within 24 | Within 36 |",
               "|---|---|---|---|---|---|---|---|---|---|",
               *[f"| {q['homes']} | {q['addresses']:,} | " + " | ".join(pc(q[c]) for c in
                 [f"{a}_to_{b}" for a, b in SPANS] + ["within_12", "within_24", "within_36"]) + " |" for q in rows], "",
               f"Of the addresses with a sale on record before the notice, {pc(R['kinds'][k]['sold_in_the_12_months_before'])} had been sold in "
               "the 12 months before it: the notice came after the sale.", ""]
        for q in rows:
            print(k, q, flush=True)
    md += ["## Reading it", "",
           "A sale takes about three to four months from an accepted offer to completion. So a sale that completes within three",
           "months of the notice was under offer when the notice appeared, and one that completes in months three to five was",
           "probably already listed. Sales completing six months or more after the notice are the ones a letter sent on the day",
           "of the notice could still reach before the home is listed.", ""]
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(OUT / f"{NAME}.json", "w"), indent=1)
    (OUT / f"{NAME}.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    if sys.argv[1:2] == ["live"]:
        NS.go_live(); FIRST, LAST, NAME = int(sys.argv[2]), int(sys.argv[3]), "NOTICE_TIMING_LIVE"
    main()
