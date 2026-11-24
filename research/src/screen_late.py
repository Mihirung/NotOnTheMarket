"""Screen: do energy certificates help find homes that are NOT yet on the market?

late_sale.py showed that almost all of the gain from certificates, measured on "sells in
the calendar year", is homes whose sale was already under way on the day they were scored.
The product is about homes that are not on the market, so the question here is narrower:
scored on 1 January, which homes will complete a sale between July of that year and June
of the next? A sale takes about four to six months from listing to completion, so those
homes were, with few exceptions, not yet listed on the scoring day.

A small second model is fitted on the deployed model's prediction, the years owned and the
certificate columns, aimed at that later window. It is fitted on one test year and scored
on the other, and compared with the same second model without the certificate columns, so
the gain is the certificates' own and not the change of aim.

    python screen_late.py

Writes research/outputs/signals/SCREEN_LATE.json and .md.
"""
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np

import epc_signals as ES
import local_eval as LE

PANEL, LAB, OUT = Path("research/data/panel3"), Path("research/outputs/lab"), Path("research/outputs/signals")
TX = "research/data/transactions.parquet"
CUR = "+HOUSE+AREA+PD"
BOOT = 300


def end_ym():
    """For each test row, the month its spell ended in a sale, as year * 12 + month - 1 (0 if it never did)."""
    f = PANEL / "test_end_ym.npy"
    if f.exists():
        return np.load(f)
    from panel2 import Panel, chunk_rows
    panel = Panel(TX, verbose=False)
    out = []
    for c in (0, 1):
        rows, years, _, _, _ = chunk_rows(panel, c)
        rows = rows[(years >= 2017) & (years <= 2019)]
        nxt = np.minimum(rows + 1, len(panel.month) - 1)          # rows are sorted by home, then date
        out.append(np.where(panel.sold[rows], panel.end_year[rows].astype(np.int64) * 12 + panel.month[nxt] - 1, 0))
    out = np.concatenate(out).astype("int32")
    np.save(f, out)
    return out


def main():
    t = LE.load_test(PANEL)
    ym = end_ym()
    X = np.vstack([np.load(PANEL / f"R_EPC_{c}.npy")[np.load(PANEL / f"year_{c}.npy") >= 2017] for c in (0, 1)]).astype("float32")
    p = np.load(LAB / "preds" / f"{CUR}@100.npy").astype(np.float64)
    p_epc = np.load(LAB / "preds" / f"{CUR}+EPC@100.npy").astype(np.float64)
    assert len(ym) == len(X) == len(p) == len(t["y"])
    keep = t["year"] <= 2018
    X, p, p_epc, ym = X[keep], p[keep], p_epc[keep], ym[keep]
    tk = {k: v[keep] for k, v in t.items()}
    year, ten, y = tk["year"].astype(np.int64), tk["tenure"], tk["y"]
    start = year * 12                                              # January of the scoring year
    assert np.array_equal((ym >= start) & (ym < start + 12), y == 1), "test rows are not in the stored order"
    late = ((ym >= start + 6) & (ym < start + 18)).astype(np.float64)       # July of the year to June of the next
    early = ((ym >= start) & (ym < start + 6)).astype(np.float64)           # January to June: sale already under way
    quarters = [("July to September", 6, 9), ("October to December", 9, 12), ("January to March, next year", 12, 15),
                ("April to June, next year", 15, 18)]

    lp = np.clip(p, 1e-6, 1 - 1e-6)
    Z = np.column_stack([np.log(lp / (1 - lp)), ten, X]); names = ["model", "tenure"] + ES.COLS
    base2, with2 = np.empty(len(y)), np.empty(len(y))
    par = dict(objective="binary", learning_rate=0.04, num_leaves=31, min_data_in_leaf=1000, feature_fraction=0.9,
               bagging_fraction=0.7, bagging_freq=1, lambda_l2=10, verbose=-1, seed=7, num_threads=4)
    gains = {}
    for a, b in ((2017, 2018), (2018, 2017)):
        tr, te = year == a, year == b
        for cols, dest in ((slice(0, 2), base2), (slice(0, None), with2)):
            m = lgb.train(par, lgb.Dataset(Z[tr][:, cols], late[tr], feature_name=names[cols]), 250)
            dest[te] = m.predict(Z[te][:, cols])
            if dest is with2:
                g = m.feature_importance("gain"); gains[a] = {n: round(float(v / g.sum()), 3) for n, v in zip(names, g)}
    arms = [("deployed model", p), ("deployed model refitted with certificates", p_epc),
            ("second step aimed at later sales, no certificates", base2),
            ("second step aimed at later sales, with certificates", with2)]
    R = {"rows": int(len(y)), "later_sellers": int(late.sum()), "gain_share": gains, "bands": {}}
    md = ["# Screen: do energy certificates help find homes not yet on the market?", "",
          "Homes are scored on 1 January. A later seller completes between July of that year and June of the next,",
          "so was, with few exceptions, not yet listed on the scoring day. Figures are later sellers found in the best",
          "tenth of each postcode district, times random, test years 2017 and 2018. The gain is the second step with",
          "certificates against the same second step without them. Ranges are 95% and cover sampling only.", ""]
    for nm, lo, hi in LE.TENURE:
        L = LE.Local(tk, lo, hi)
        y_all = L.y.copy()
        tops = {k: L.top_mask(v[L.keep]) for k, v in arms}
        res = {}
        L.y = late[L.keep]
        for k, top in tops.items():
            res[k] = {"later": round(L.lift(top), 4)}
        ma, mb = tops[arms[2][0]], tops[arms[3][0]]
        rng = np.random.default_rng(3); d = []
        for _ in range(BOOT):
            w = rng.poisson(1.0, LE.N_BLOCKS).astype(float)[L.block]
            d.append(L.lift(mb, w) - L.lift(ma, w))
        gain = {"gain": round(res[arms[3][0]]["later"] - res[arms[2][0]]["later"], 4),
                "range": [round(float(np.percentile(d, q)), 4) for q in (2.5, 97.5)]}
        for qn, a, b in quarters:
            L.y = ((ym >= start + a) & (ym < start + b)).astype(np.float64)[L.keep]
            for k, top in tops.items():
                res[k][qn] = round(L.lift(top), 4)
        e = early[L.keep]
        for k, top in tops.items():                                # how much of the list is a sale already under way
            res[k]["under_way_share_of_list"] = round(float((e * top).sum() / top.sum()), 4)
            res[k]["later_share_of_list"] = round(float((late[L.keep] * top).sum() / top.sum()), 4)
        L.y = y_all
        R["bands"][nm] = {"arms": res, "certificates": gain}
        md += [f"## Owners: {nm}", "", "| Ranking | Later sellers found | Share of list that sells later | Share of list already under way |",
               "|---|---|---|---|"]
        md += [f"| {k} | {v['later']:.3f} | {100 * v['later_share_of_list']:.1f}% | {100 * v['under_way_share_of_list']:.1f}% |"
               for k, v in res.items()]
        md += ["", f"Gain from certificates: {gain['gain']:+.3f} ({gain['range'][0]:+.3f} to {gain['range'][1]:+.3f}).", ""]
        print(nm, json.dumps(res, indent=0)[:900], gain, flush=True)
    print("gain share", gains, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(OUT / "SCREEN_LATE.json", "w"), indent=1)
    (OUT / "SCREEN_LATE.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
