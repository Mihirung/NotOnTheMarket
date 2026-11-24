"""Where the notices fall: do they touch some kinds of neighbourhood more than others?

A notice changes one home's score. Nothing here is about a person: it counts the addresses named in
a notice in each group of postcodes and sets that against the addresses there. Postcodes are put
into fifths (each holding a fifth of all addresses) by deprivation and by the make-up of their
residents in the census, which is published by small area. The same check should be read before
any mail is sent on the back of a notice.

    python notice_fairness.py [score_year]

Writes research/outputs/signals/NOTICE_FAIRNESS.json and .md. Counts and rates only.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import notice_signals as NS  # noqa: E402

OUT = Path("research/outputs/signals")
KIND = {"bk": "Bankruptcy orders", "dec": "Deceased-estate notices"}
GROUPS = [("imd_rank", "Deprivation (most deprived fifth first)", True),
          ("white_british", "White British", False), ("white_other", "Other White", False), ("indian", "Indian", False),
          ("pakistani", "Pakistani", False), ("bangladeshi", "Bangladeshi", False), ("black_african", "Black African", False),
          ("black_caribbean", "Black Caribbean", False), ("christian", "Christian", False), ("muslim", "Muslim", False),
          ("hindu", "Hindu", False), ("sikh", "Sikh", False), ("jewish", "Jewish", False), ("no_religion", "No religion", False)]


def fifths(v, w, low_first):
    """Which fifth of all addresses each postcode falls in when postcodes are ordered by v (0 = the first fifth)."""
    o = np.argsort(v if low_first else -v, kind="stable")
    cum = np.cumsum(w[o]) / w.sum()
    f = np.empty(len(v), np.int64); f[o] = np.minimum((cum * 5 - 1e-9).astype(np.int64), 4)
    return f


def main():
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2020
    t0 = year * 12
    S = NS.SIG
    pc = pd.read_parquet(S / "area_postcode.parquet", columns=["postcode", "imd_rank", "n_addresses"]).drop_duplicates("postcode")
    pc = pc.merge(pd.read_parquet(S / "community_postcode.parquet").drop_duplicates("postcode"), on="postcode", how="left")
    pc = pc[pc.n_addresses > 0].reset_index(drop=True)
    R = {"score_year": year, "window_months": NS.WINDOW, "addresses": int(pc.n_addresses.sum()), "kinds": {}}
    md = ["# Where the notices fall", "",
          f"Addresses named in a notice in the {NS.WINDOW} months before 1 January {year}, per 1,000 addresses, by fifths of postcodes",
          "(each fifth holds a fifth of all addresses). The first table orders postcodes by deprivation. In the second, the highest",
          "fifth is the fifth of addresses in postcodes where the group makes up the largest share of residents, and the figure",
          "is how many times the average rate that fifth sees. 1.00 means no difference. Care and nursing homes are left out.", ""]
    for k in NS.KINDS:
        if not (NS.DIRS[k] / "listing.jsonl").exists():
            continue
        t = NS.linked(k, every=True)
        t = t[(t.ym < t0) & (t.ym >= t0 - NS.WINDOW) & ~t.care & (t.key != 0)].drop_duplicates("key")
        n = pc.postcode.map(t.postcode.value_counts()).fillna(0).to_numpy()
        w = pc.n_addresses.to_numpy(float)
        overall = 1000 * n.sum() / w.sum()
        K = {"addresses_named": int(n.sum()), "per_1000_addresses": round(float(overall), 2), "groups": {}}
        dep, rows = None, []
        for col, label, low_first in GROUPS:
            ok = pc[col].notna().to_numpy()
            f = fifths(pc[col].to_numpy(float)[ok], w[ok], low_first)
            rate = [1000 * n[ok][f == i].sum() / w[ok][f == i].sum() for i in range(5)]
            avg = 1000 * n[ok].sum() / w[ok].sum()
            K["groups"][col] = {"per_1000_by_fifth": [round(float(x), 2) for x in rate], "times_average_by_fifth": [round(float(x / avg), 2) for x in rate]}
            if col == "imd_rank":
                dep = K["groups"][col]
            else:
                rows.append(f"| {label} | {rate[4] / avg:.2f} | {rate[0] / avg:.2f} |")       # fifths run from the highest share down
        R["kinds"][k] = K
        md += [f"## {KIND[k]}", "", f"{int(n.sum()):,} addresses named, {overall:.2f} per 1,000 addresses.", "",
               "| Fifth of addresses by deprivation | Most deprived | Second | Middle | Fourth | Least deprived |", "|---|---|---|---|---|---|",
               "| Per 1,000 addresses | " + " | ".join(f"{x:.2f}" for x in dep["per_1000_by_fifth"]) + " |",
               "| Times the average | " + " | ".join(f"{x:.2f}" for x in dep["times_average_by_fifth"]) + " |", "",
               "| Group (share of the postcode's residents) | Fifth with the lowest share | Fifth with the highest share |", "|---|---|---|", *rows, ""]
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(OUT / "NOTICE_FAIRNESS.json", "w"), indent=1)
    (OUT / "NOTICE_FAIRNESS.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
