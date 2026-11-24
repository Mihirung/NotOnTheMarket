"""How much of a family's gain is early warning, and how much is a sale already under way.

The model is asked on 1 January which homes will sell during the year. A home whose sale
completes in January to March was almost certainly on the market, or under offer, on the
day it was scored: a buyer could already find it on a portal. A sale that completes in the
second half of the year was mostly not yet listed. A signal such as an energy certificate
lodged for a sale could win simply by spotting homes that are already listed, which is
worth little to a product about homes that are not on the market.

This check keeps each model's ranking as it is (the best tenth of each postcode district)
and counts the sellers found there separately by the quarter in which the sale completed,
for the deployed model and for the deployed model with one more family.

    python late_sale.py <FAMILY>          writes research/outputs/signals/LATE_<FAMILY>.json and .md
"""
import json
import sys
from pathlib import Path

import numpy as np

import local_eval as LE

PANEL, LAB, OUT = "research/data/panel3", Path("research/outputs/lab"), Path("research/outputs/signals")
TX = "research/data/transactions.parquet"
CUR = "+HOUSE+AREA+PD"
BOOT = 300
PERIODS = [("January to March", 1, 3), ("April to June", 4, 6), ("July to September", 7, 9),
           ("October to December", 10, 12), ("July to December", 7, 12), ("Whole year", 1, 12)]


def end_months():
    """The month in which each test row's sale completed (0 where the home did not sell that year)."""
    f = Path(PANEL) / "test_end_month.npy"
    if f.exists():
        return np.load(f)
    from panel2 import Panel, chunk_rows
    panel = Panel(TX, verbose=False)
    out = []
    for c in (0, 1):
        rows, years, label, _, _ = chunk_rows(panel, c)
        m = (years >= 2017) & (years <= 2019)
        rows, label = rows[m], label[m]
        nxt = np.minimum(rows + 1, len(panel.month) - 1)          # rows are sorted by home, then date
        out.append(np.where(label == 1, panel.month[nxt], 0).astype("int8"))
    out = np.concatenate(out)
    np.save(f, out)
    return out


def main():
    fam = sys.argv[1]
    t = LE.load_test(PANEL)
    em = end_months()
    assert len(em) == len(t["y"]) and np.array_equal(em > 0, t["y"] == 1), "test rows are not in the stored order"
    p_cur = np.load(LAB / "preds" / f"{CUR}@100.npy")
    p_new = np.load(LAB / "preds" / f"{CUR}+{fam}@100.npy")
    res = {}
    for band, lo, hi in LE.TENURE:
        L = LE.Local(t, lo, hi)
        ma, mb = L.top_mask(p_cur[L.keep]), L.top_mask(p_new[L.keep])
        month = em[L.keep]
        res[band] = {}
        for name, a, b in PERIODS:
            y = ((month >= a) & (month <= b)).astype("float64")

            def lift(top, w=None, y=y):
                w = np.ones(len(y)) if w is None else w
                return float(((w * y * top).sum() / (w * top).sum()) / ((w * y).sum() / w.sum()))
            rng = np.random.default_rng(3); d = []
            for _ in range(BOOT):
                w = rng.poisson(1.0, LE.N_BLOCKS).astype(float)[L.block]
                d.append(lift(mb, w) - lift(ma, w))
            res[band][name] = {"sellers": int(y.sum()), "current": round(lift(ma), 3), "with": round(lift(mb), 3),
                               "gain": round(lift(mb) - lift(ma), 3),
                               "range": [round(float(np.percentile(d, q)), 3) for q in (2.5, 97.5)],
                               "share_of_top_current": round(float((y * ma).sum() / max((L.y * ma).sum(), 1)), 3),
                               "share_of_top_with": round(float((y * mb).sum() / max((L.y * mb).sum(), 1)), 3)}
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump({"family": fam, "deployed": CUR, "bands": res}, open(OUT / f"LATE_{fam}.json", "w"), indent=1)
    md = [f"# {fam}: early warning, or a sale already under way?", "",
          "Each model's best tenth of every postcode district, scored on 1 January, test years 2017 and 2018.",
          "Sellers are split by the quarter in which the sale completed. A sale completing in January to March",
          "was almost certainly already on the market when the home was scored; one completing in July to",
          "December mostly was not. The figures are sellers found, times random. Ranges are 95% and cover",
          "sampling only (one fit each side).", ""]
    for band, r in res.items():
        md += [f"## Owners: {band}", "", "| Sale completed | Sellers | Deployed | With " + fam + " | Gain (95% range) |",
               "|---|---|---|---|---|"]
        for name, _, _ in PERIODS:
            v = r[name]
            md.append(f"| {name} | {v['sellers']:,} | {v['current']:.3f} | {v['with']:.3f} | "
                      f"{v['gain']:+.3f} ({v['range'][0]:+.3f} to {v['range'][1]:+.3f}) |")
        md.append("")
    (OUT / f"LATE_{fam}.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
