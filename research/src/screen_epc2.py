"""Screen, second version: energy certificates tied to exact homes where the sale records allow it.

The same test as screen_epc.py (a small second model on the deployed model's
prediction, fitted on one test year and scored on the other), with the EPC
family of epc_signals.py: certificates on a home's own UPRN where it is known,
and a share of the unexplained certificates where it is not.

    python screen_epc2.py

Writes research/outputs/signals/SCREEN_EPC2.json and .md.
"""
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import assess_signal as A  # noqa: E402
import epc_signals as ES  # noqa: E402
import local_eval as LE  # noqa: E402
import panel2 as P2  # noqa: E402

TX = "research/data/transactions.parquet"


def main():
    panel = P2.Panel(TX)
    month = pd.read_parquet(TX, columns=["month"]).month.to_numpy()
    epc = ES.Epc(panel, month, say=lambda *a: print(*a, flush=True))
    parts = []
    for c in (0, 1):
        lo, hi = c * P2.CHUNK_BUCKETS, (c + 1) * P2.CHUNK_BUCKETS
        spells = np.nonzero((panel.bucket >= lo) & (panel.bucket < hi))[0]
        rows, years, label = panel.expand(spells)
        m = (years >= 2017) & (years <= 2019)
        assert np.array_equal(label[m], np.load(f"{A.PANEL}/y_{c}.npy")[np.load(f"{A.PANEL}/year_{c}.npy") >= 2017]), "row order"
        parts.append(epc.features(rows[m], years[m]))
    X = np.vstack(parts); del panel, epc
    t = LE.load_test(A.PANEL)
    p = np.load(Path(A.LAB) / "preds" / f"{A.CUR_NAME}@100.npy").astype(np.float64)
    assert len(p) == len(X) == len(t["y"])
    keep = t["year"] <= 2018
    X, p, y, year, ten = X[keep], p[keep], t["y"][keep], t["year"][keep], t["tenure"][keep]
    tk = {k: v[keep] for k, v in t.items()}
    ix = {c: i for i, c in enumerate(ES.COLS)}

    def table(mask, groups, labels):
        d = pd.DataFrame({"g": pd.Categorical.from_codes(groups[mask], labels), "y": y[mask], "p": p[mask]})
        return d.groupby("g", observed=True).agg(home_years=("y", "size"), sold=("y", "mean"), model_said=("p", "mean"))

    anc = X[:, ix["anchored"]] == 1
    own = np.minimum(np.nan_to_num(X[:, ix["own_sale_12m"]]), 1).astype(int)
    t_own = table(anc, own, ["no sale certificate on the home in the last 12 months", "a sale certificate on the home in the last 12 months"])
    sh = X[:, ix["pool_share_6m"]]
    bins = np.digitize(np.nan_to_num(sh), [1e-9, 0.1, 0.2, 0.34, 0.5, 1.0])
    t_pool = table(~anc, bins, ["none", "under 0.1", "0.1 to 0.2", "0.2 to 0.34", "0.34 to 0.5", "0.5 to 1", "1 or more"])
    print(f"homes with a known UPRN: {anc.mean():.1%}", flush=True); print(t_own.round(4).to_string()); print(t_pool.round(4).to_string(), flush=True)

    lp = np.clip(p, 1e-6, 1 - 1e-6); logit = np.log(lp / (1 - lp))
    Z = np.column_stack([logit, ten, X]); names = ["model", "tenure"] + ES.COLS
    stacked = np.empty(len(y)); base2 = np.empty(len(y))
    par = dict(objective="binary", learning_rate=0.04, num_leaves=31, min_data_in_leaf=1000, feature_fraction=0.9,
               bagging_fraction=0.7, bagging_freq=1, lambda_l2=10, verbose=-1, seed=7, num_threads=4)
    gains = {}
    for a, b in ((2017, 2018), (2018, 2017)):
        tr, te = year == a, year == b
        for cols, dest in ((slice(0, 2), base2), (slice(0, None), stacked)):
            m = lgb.train(par, lgb.Dataset(Z[tr][:, cols], y[tr], feature_name=names[cols]), 250)
            dest[te] = m.predict(Z[te][:, cols])
            if dest is stacked:
                g = m.feature_importance("gain"); gains[a] = {n: round(float(v / g.sum()), 3) for n, v in zip(names, g)}
    R = {"columns": ES.COLS, "gain_share": gains, "rows": int(len(y)), "known_uprn_share": round(float(anc.mean()), 4),
         "own": t_own.reset_index().to_dict("records"), "pool": t_pool.reset_index().to_dict("records")}
    rows_md = []
    for nm, lo, hi in LE.TENURE:
        Lk = LE.Local(tk, lo, hi)
        res = {k: round(Lk.lift(Lk.top_mask(pp[Lk.keep])), 4) for k, pp in
               (("deployed", p), ("second step, no certificates", base2), ("second step, with certificates", stacked))}
        ma, mb = Lk.top_mask(base2[Lk.keep]), Lk.top_mask(stacked[Lk.keep])
        rng = np.random.default_rng(3); d = []
        for _ in range(A.BOOT):
            w = rng.poisson(1.0, LE.N_BLOCKS).astype(float)[Lk.block]
            d.append(Lk.lift(mb, w) - Lk.lift(ma, w))
        res["gain_from_certificates"] = round(res["second step, with certificates"] - res["second step, no certificates"], 4)
        res["range"] = [round(float(np.percentile(d, q)), 4) for q in (2.5, 97.5)]
        R[nm] = res
        rows_md.append(f"| {nm} | {res['deployed']:.3f} | {res['second step, no certificates']:.3f} | {res['second step, with certificates']:.3f} | "
                       f"{res['gain_from_certificates']:+.3f} | {res['range'][0]:+.3f} to {res['range'][1]:+.3f} |")
        print(nm, res, flush=True)
    print("gain share", gains, flush=True)
    json.dump(R, open(Path(A.OUT) / "SCREEN_EPC2.json", "w"), indent=1, default=str)
    fmt = lambda tb: [f"| {r.g} | {int(r.home_years):,} | {100 * r.sold:.1f}% | {100 * r.model_said:.1f}% |" for r in tb.reset_index().itertuples()]   # noqa: E731
    md = ["# Screen 2: energy certificates, tied to exact homes where the sale records allow", "",
          "No address field is used. Sellers found in the best tenth of each district, times random, 2017 and 2018.", "",
          "| Owners | Deployed model | Second step without | Second step with certificates | Gain | 95% range |", "|---|---|---|---|---|---|", *rows_md, "",
          f"## Homes whose UPRN is known ({100 * anc.mean():.0f}% of home-years)", "",
          "| | Home-years | Sold in the year | The model said |", "|---|---|---|---|", *fmt(t_own), "",
          "## Other homes: unexplained sale certificates in the last 6 months, per home of that kind in the postcode", "",
          "| Certificates per home | Home-years | Sold in the year | The model said |", "|---|---|---|---|", *fmt(t_pool), ""]
    (Path(A.OUT) / "SCREEN_EPC2.md").write_text("\n".join(md))


if __name__ == "__main__":
    main()
