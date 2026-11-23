"""Does the deployed model treat communities fairly?

The model never sees ethnicity or religion. But it sees things that go with
them (where homes are, prices, how often streets change hands), so it could
still pick some communities' homes more or less often than their real
chance of selling warrants. This checks, on the 2017 and 2018 test years:

  for each fifth of homes by an area's community make-up (2011 Census output
  area: share White British, ethnic mix, share Muslim, share Christian,
  share with no religion), and by deprivation for comparison,
    homes         share of all test home-years
    picked        share of the group's homes in the best tenth of their district
    sold          the group's actual yearly sale rate
    hit rate      sellers among the group's picked homes (precision)
    found         share of the group's sellers that were picked (recall)
    picked / sold how much more often the group is picked than its sale rate
                  alone would suggest, relative to all homes

A fair model picks each group in step with how often it really sells, and
its picks are right about as often in every group.

Writes research/outputs/lab/fairness_audit.json and .md.

Usage: python audit_fairness.py [model name, default the deployed one]
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "research/src")
import local_eval as LE  # noqa: E402
import model_lab as ML  # noqa: E402
import signals as SG  # noqa: E402

PANEL, LAB = "research/data/panel3", Path("research/outputs/lab")
GROUPS = [("COMMUNITY", "white_british", "Share White British"), ("COMMUNITY", "ethnic_mix", "Ethnic mix"),
          ("COMMUNITY", "muslim", "Share Muslim"), ("COMMUNITY", "christian", "Share Christian"),
          ("COMMUNITY", "no_religion", "Share no religion"), ("AREA15", "imd_score_15", "Deprivation (2015)")]


def main(name=None):
    name = name or json.load(open(LAB / "lab_deploy.json"))["name"]
    p = np.load(LAB / "preds" / f"{name}@100.npy")
    t = LE.load_test(PANEL)
    pc = np.concatenate([np.load(Path(PANEL) / f"pc_{c}.npy")[(lambda y: (y >= 2017) & (y <= 2019))(np.load(Path(PANEL) / f"year_{c}.npy"))]
                         for c in (0, 1)])
    L = LE.Local(t)
    keep = L.keep
    top = np.zeros(len(p), bool); top[np.nonzero(keep)[0]] = L.top_mask(p[keep])
    y = t["y"].astype(float); base_pick, base_sold = top[keep].mean(), y[keep].mean()
    ch = ML.Chunks(PANEL)
    out, lines = {"model": name, "rows": int(keep.sum())}, [f"# Fairness audit: {name}", "",
                                                           "Test home-years 2017 and 2018, picked = in the best tenth of their district.", ""]
    for fam, col, label in GROUPS:
        if fam not in ch.place:
            continue
        v = ch.lookup(fam)[:, SG.FAMILIES[fam]["columns"].index(col)][pc]
        ok = keep & np.isfinite(v)
        q = pd.qcut(pd.Series(v[ok]).rank(method="first"), 5, labels=False).to_numpy()
        rows = []
        for k in range(5):
            m = np.zeros(len(p), bool); m[np.nonzero(ok)[0][q == k]] = True
            picked, sold = top[m].mean(), y[m].mean()
            hit = y[m & top].mean() if (m & top).any() else np.nan
            found = (y[m] * top[m]).sum() / max(y[m].sum(), 1)
            rows.append({"fifth": k + 1, "range": [round(float(np.nanmin(v[m])), 3), round(float(np.nanmax(v[m])), 3)],
                         "homes": round(float(m.sum() / ok.sum()), 3), "picked": round(float(picked), 4),
                         "sold": round(float(sold), 4), "hit_rate": round(float(hit), 4), "found": round(float(found), 3),
                         "picked_vs_sold": round(float((picked / base_pick) / (sold / base_sold)), 3)})
        out[col] = rows
        lines += [f"## {label}", "", "| Fifth | Range | Picked | Sold a year | Hit rate | Sellers found | Picked relative to selling |",
                  "|---|---|---|---|---|---|---|"]
        lines += [f"| {r['fifth']} | {r['range'][0]} to {r['range'][1]} | {100 * r['picked']:.1f}% | {100 * r['sold']:.2f}% | "
                  f"{100 * r['hit_rate']:.1f}% | {100 * r['found']:.0f}% | {r['picked_vs_sold']:.2f} |" for r in rows]
        lines.append("")
    json.dump(out, open(LAB / "fairness_audit.json", "w"), indent=1)
    (LAB / "fairness_audit.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main(*sys.argv[1:2])
