"""Quick screen: is there anything left in the sale records at month level?

The model counts ownership in whole calendar years and counts neighbours'
sales by calendar year. The sale records carry the month. This screen works
out month-level candidates for the test homes (2017 and 2018, the tenth of
homes held out in full) and asks whether they improve on the deployed model's
own prediction, without refitting it:

  months_owned       months from purchase to 1 January of the year scored
  buy_month          month of purchase
  prev_gap_m         months between the last two sales of the home
  pc_last_m          months since the latest other sale in the postcode
  pc_sales_3m/6m     other sales in the postcode in the last 3 / 6 months
  sec_q4_share       share of the sector's sales last year that fell in its last quarter

A small second model is fitted on one test year from [the deployed model's
prediction + the candidates] and scored on the other year, and the reverse.
It is a screen: a gain here says the full refit is worth its hours; no gain
says it is not.

    python screen_monthly.py

Writes research/outputs/signals/SCREEN_MONTHLY.json.
"""
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import assess_signal as A  # noqa: E402
import local_eval as LE  # noqa: E402
import panel2 as P2  # noqa: E402

TX = "research/data/transactions.parquet"
CANDS = ["months_owned", "buy_month", "prev_gap_m", "pc_last_m", "pc_sales_3m", "pc_sales_6m", "sec_q4_share"]


def candidates(panel, month, rows, years):
    """Month-level features for spells `rows` scored at `years`, using sales before 1 January of that year."""
    ym = panel.year.astype(np.int64) * 12 + (month.astype(np.int64) - 1)          # month index of every sale
    t0 = years.astype(np.int64) * 12                                              # 1 January of the year scored
    f = {}
    f["months_owned"] = (t0 - ym[rows]).astype(np.float32)
    f["buy_month"] = month[rows].astype(np.float32)
    same_prev = np.zeros(len(panel.key), bool); same_prev[1:] = panel.key[1:] == panel.key[:-1]
    gap = np.full(len(panel.key), np.nan, np.float32); gap[1:] = (ym[1:] - ym[:-1])
    f["prev_gap_m"] = np.where(same_prev, gap, np.nan)[rows]
    # other sales in the postcode: every sale's month, sorted within postcode
    o = np.lexsort((ym, panel.pc)); pcs, yms = panel.pc[o], ym[o]
    key = pcs.astype(np.int64) * 100_000 + yms
    q = panel.pc[rows].astype(np.int64) * 100_000
    hi = np.searchsorted(key, q + t0, side="left")                               # sales in the postcode before t0
    lo0 = np.searchsorted(key, q, side="left")
    own = lambda m: ((t0 - ym[rows]) <= m).astype(np.int64)                        # the home's own purchase is not a neighbour's sale
    for m in (3, 6):
        f[f"pc_sales_{m}m"] = np.maximum(hi - np.searchsorted(key, q + t0 - m, side="left") - own(m), 0).astype(np.float32)
    last = np.where(hi > lo0, yms[np.maximum(hi - 1, 0)], -10**6)                  # latest sale before t0
    own_last = last == ym[rows]                                                   # ...which may be the home's own purchase
    prev = np.where(hi - 1 > lo0, yms[np.maximum(hi - 2, 0)], -10**6)
    last = np.where(own_last, prev, last)
    f["pc_last_m"] = np.where(last > -10**5, t0 - last, np.nan).astype(np.float32)
    sec = panel.pc2sec[panel.pc]
    n_sec = len(panel.sec_names); yi = panel.year - P2.Y0
    tot = np.zeros((n_sec, P2.NY)); np.add.at(tot, (sec, yi), 1.0)
    q4 = np.zeros((n_sec, P2.NY)); np.add.at(q4, (sec, yi), (month >= 10).astype(float))
    pi = np.clip(years - P2.Y0 - 1, 0, P2.NY - 1)
    f["sec_q4_share"] = (q4[sec[rows], pi] / np.maximum(tot[sec[rows], pi], 1)).astype(np.float32)
    return np.column_stack([f[c] for c in CANDS])


def main():
    panel = P2.Panel(TX)
    month = pd.read_parquet(TX, columns=["month"]).month.to_numpy().astype(np.int8)
    parts = []
    for c in (0, 1):                                   # the two chunks stored in full: the same rows, in the same order
        lo, hi = c * P2.CHUNK_BUCKETS, (c + 1) * P2.CHUNK_BUCKETS
        spells = np.nonzero((panel.bucket >= lo) & (panel.bucket < hi))[0]
        rows, years, label = panel.expand(spells)
        m = (years >= 2017) & (years <= 2019)
        assert np.array_equal(label[m], np.load(f"{A.PANEL}/y_{c}.npy")[np.load(f"{A.PANEL}/year_{c}.npy") >= 2017]), "row order"
        parts.append(candidates(panel, month, rows[m], years[m]))
    X = np.vstack(parts); del panel
    t = LE.load_test(A.PANEL)
    p = np.load(Path(A.LAB) / "preds" / f"{A.CUR_NAME}@100.npy").astype(np.float64)
    assert len(p) == len(X) == len(t["y"])
    keep = t["year"] <= 2018
    X, p, y, year, ten = X[keep], p[keep], t["y"][keep], t["year"][keep], t["tenure"][keep]
    logit = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
    Z = np.column_stack([logit, ten, X]); names = ["model", "tenure"] + CANDS
    stacked = np.empty(len(y)); base2 = np.empty(len(y))
    par = dict(objective="binary", learning_rate=0.05, num_leaves=63, min_data_in_leaf=500, feature_fraction=0.9,
               bagging_fraction=0.7, bagging_freq=1, lambda_l2=5, verbose=-1, seed=7, num_threads=4)
    gains = {}
    for a, b in ((2017, 2018), (2018, 2017)):
        tr, te = year == a, year == b
        for cols, dest in ((slice(0, 2), base2), (slice(0, None), stacked)):   # the same second step with and without the candidates
            d = lgb.Dataset(Z[tr][:, cols], y[tr], feature_name=names[cols])
            m = lgb.train(par, d, 300)
            dest[te] = m.predict(Z[te][:, cols])
            if dest is stacked:
                g = m.feature_importance("gain"); gains[a] = {n: round(float(v / g.sum()), 3) for n, v in zip(names, g)}
    R = {"candidates": CANDS, "gain_share": gains, "rows": int(len(y))}
    for nm, lo, hi in LE.TENURE:
        Lk = LE.Local({k: v[keep] for k, v in t.items()}, lo, hi)
        res = {}
        for k, pp in (("deployed", p), ("second step, no candidates", base2), ("second step, with candidates", stacked)):
            res[k] = round(Lk.lift(Lk.top_mask(pp[Lk.keep])), 4)
        ma, mb = Lk.top_mask(base2[Lk.keep]), Lk.top_mask(stacked[Lk.keep])
        rng = np.random.default_rng(3); d = []
        for _ in range(A.BOOT):
            w = rng.poisson(1.0, LE.N_BLOCKS).astype(float)[Lk.block]
            d.append(Lk.lift(mb, w) - Lk.lift(ma, w))
        res["gain_from_candidates"] = round(res["second step, with candidates"] - res["second step, no candidates"], 4)
        res["range"] = [round(float(np.percentile(d, q)), 4) for q in (2.5, 97.5)]
        R[nm] = res
        print(nm, res, flush=True)
    print("gain share", gains, flush=True)
    json.dump(R, open(Path(A.OUT) / "SCREEN_MONTHLY.json", "w"), indent=1)


if __name__ == "__main__":
    main()
