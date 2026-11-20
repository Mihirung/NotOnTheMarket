"""Model experiments on the national panel (version 2).

Runs, on float16 chunk files written by panel2.py:

  ladder      feature families added one at a time, fixed sample size
  curve       learning curve: the same models at 1%, 5%, 20%, 40% of
              all properties — does more data unlock bigger effects?
  rolling     refit each year and predict the next (the deployment
              protocol) against the stale fixed-origin model
  tenure      where each family helps, by length of ownership

Evaluation is out-of-time. The headline test window is 2017-2018 (the
2019 file undercounts late registrations); 2017-2019 is reported for
continuity with earlier documents. Uncertainty is from a block
bootstrap over properties (2,048 hash blocks, Poisson weights), since
rows from one property are not independent.

Usage: python model_lab.py <panel_dir> <out_dir> <experiment> [threads]
"""

import json
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np

TRAIN = (2001, 2015)
N_BLOCKS, BOOT = 2048, 300


class Chunks:
    def __init__(self, panel_dir):
        self.dir = Path(panel_dir)
        self.meta = json.load(open(self.dir / "meta.json"))
        self.names = self.meta["features"]; self.fam = self.meta["families"]
        self.n_chunks = len(self.meta["chunks"])
        self._cache = {}

    def col(self, kind, c):
        k = (kind, c)
        if k not in self._cache:
            self._cache[k] = np.load(self.dir / f"{kind}_{c}.npy")
        return self._cache[k]

    def X(self, c):
        return np.load(self.dir / f"X_{c}.npy", mmap_mode="r")

    def rows(self, c, years, max_bucket=None):
        yr = self.col("year", c)
        m = (yr >= years[0]) & (yr <= years[1])
        if max_bucket is not None:
            m &= self.col("bucket", c) < max_bucket
        return np.nonzero(m)[0]

    def cols(self, families):
        want = [f for fam in families for f in self.fam[fam]]
        return [self.names.index(f) for f in want], want


class Seq(lgb.Sequence):
    """Out-of-core rows for LightGBM: float16 on disk -> float32 batches."""

    def __init__(self, X, rows, cols, batch_size=65536):
        self.X, self.rows, self.cols, self.batch_size = X, rows, np.asarray(cols), batch_size

    def __getitem__(self, idx):
        r = self.rows[idx]
        out = np.asarray(self.X[r]).astype(np.float32)
        return out[..., self.cols] if out.ndim == 2 else out[self.cols]

    def __len__(self):
        return len(self.rows)


def pct_to_chunks(pct):
    """(chunk ids, bucket cap for the last partial chunk) for a sample percentage."""
    full, rem = divmod(pct, 5)
    ids = list(range(int(full))) + ([int(full)] if rem else [])
    return ids, (int(full) * 5 + rem if rem else None)


def dataset(ch, pct, families, years):
    ids, cap = pct_to_chunks(pct)
    cols, names = ch.cols(families)
    seqs, ys = [], []
    for c in ids:
        rows = ch.rows(c, years, cap if (cap is not None and c == ids[-1]) else None)
        seqs.append(Seq(ch.X(c), rows, cols)); ys.append(ch.col("y", c)[rows])
    y = np.concatenate(ys)
    return lgb.Dataset(seqs, label=y, feature_name=names, free_raw_data=True,
                       params={"max_bin": 63, "min_data_in_bin": 20, "verbose": -1}), len(y)


def params(n_rows, threads):
    leaves = 31 if n_rows < 2e6 else 63 if n_rows < 8e6 else 127 if n_rows < 3e7 else 255
    return dict(objective="binary", learning_rate=0.08, num_leaves=leaves,
                min_data_in_leaf=int(np.clip(n_rows / 20000, 100, 1500)), max_bin=63,
                feature_fraction=0.8, bagging_fraction=0.5, bagging_freq=1, lambda_l2=5.0,
                num_threads=threads, verbose=-1, seed=7)


def rounds_for(n_rows):
    """Boosting rounds: grows gently with data (calibrated by an early-stopping pilot)."""
    return int(np.clip(140 * (n_rows / 1e6) ** 0.28, 150, 700))


def test_set(ch, families, years, chunks=(0, 1)):
    cols, _ = ch.cols(families)
    Xs, ys, yrs, ten, blk = [], [], [], [], []
    for c in chunks:
        rows = ch.rows(c, years)
        Xs.append(np.asarray(ch.X(c)[rows]).astype(np.float32)[:, cols])
        ys.append(ch.col("y", c)[rows]); yrs.append(ch.col("year", c)[rows])
        ten.append(ch.col("tenure", c)[rows]); blk.append(ch.col("block", c)[rows])
    return np.concatenate(Xs), np.concatenate(ys), np.concatenate(yrs), np.concatenate(ten), np.concatenate(blk)


# ---------------------------------------------------------------- metrics
def auc(y, p, w=None):
    o = np.argsort(p, kind="stable"); y = y[o]
    w = np.ones(len(y)) if w is None else w[o]
    wn, wp = w * (1 - y), w * y
    return float((wp * np.cumsum(wn)).sum() / (wp.sum() * wn.sum()))


def lift(y, p, frac, w=None):
    o = np.argsort(-p, kind="stable"); y = y[o]
    w = np.ones(len(y)) if w is None else w[o]
    cw = np.cumsum(w); k = np.searchsorted(cw, frac * cw[-1])
    return float(((w * y)[:k + 1].sum() / cw[k]) / ((w * y).sum() / cw[-1]))


def summarise(y, p, yr, ten):
    m1718 = yr <= 2018
    r = {"auc": auc(y[m1718], p[m1718]), "auc_1719": auc(y, p),
         "auc_within_year": float(np.mean([auc(y[yr == t], p[yr == t]) for t in (2017, 2018)])),
         "lift1": lift(y[m1718], p[m1718], .01), "lift5": lift(y[m1718], p[m1718], .05),
         "lift10": lift(y[m1718], p[m1718], .10), "lift20": lift(y[m1718], p[m1718], .20),
         "lift10_1719": lift(y, p, .10), "mean_pred": float(p[m1718].mean()), "base_rate": float(y[m1718].mean())}
    for name, lo, hi in (("t0_4", 0, 5), ("t5_9", 5, 10), ("t10_19", 10, 20), ("t20p", 20, 99)):
        m = m1718 & (ten >= lo) & (ten < hi)
        if y[m].sum() > 200:
            r[f"auc_{name}"] = auc(y[m], p[m]); r[f"lift10_{name}"] = lift(y[m], p[m], .10)
            r[f"n_sales_{name}"] = int(y[m].sum())
    return r


def paired_ci(y, pa, pb, blk, mask=None, seed=5):
    """Block-bootstrap interval for (b minus a) in AUC and top-decile lift."""
    if mask is not None:
        y, pa, pb, blk = y[mask], pa[mask], pb[mask], blk[mask]
    rng = np.random.default_rng(seed)
    oa, ob = np.argsort(pa, kind="stable"), np.argsort(pb, kind="stable")
    da, db = np.argsort(-pa, kind="stable"), np.argsort(-pb, kind="stable")
    d_auc, d_lift = [], []
    for _ in range(BOOT):
        w = rng.poisson(1.0, N_BLOCKS).astype("float64")[blk]
        def a_(o):
            yy, ww = y[o], w[o]; wn, wp = ww * (1 - yy), ww * yy
            return (wp * np.cumsum(wn)).sum() / (wp.sum() * wn.sum())
        def l_(o):
            yy, ww = y[o], w[o]; cw = np.cumsum(ww); k = np.searchsorted(cw, .1 * cw[-1])
            return ((ww * yy)[:k + 1].sum() / cw[k]) / ((ww * yy).sum() / cw[-1])
        d_auc.append(a_(ob) - a_(oa)); d_lift.append(l_(db) - l_(da))
    q = lambda v: [round(float(np.percentile(v, x)), 4) for x in (2.5, 50, 97.5)]
    return {"d_auc": q(d_auc), "d_lift10": q(d_lift), "p_better": round(float((np.array(d_auc) > 0).mean()), 3)}


def fit(ch, pct, families, threads, years=TRAIN, n_rounds=None, tag=""):
    t0 = time.time()
    ds, n = dataset(ch, pct, families, years)
    pr = params(n, threads)
    nr = n_rounds or rounds_for(n)
    bst = lgb.train(pr, ds, num_boost_round=nr)
    print(f"  fit {tag or '+'.join(families)} @ {pct}%: {n:,} rows, {nr} rounds, "
          f"{pr['num_leaves']} leaves, {time.time()-t0:.0f}s", flush=True)
    return bst, n


# ---------------------------------------------------------------- experiments
def exp_pilot(ch, out, threads):
    """Early stopping on 2014-15 to calibrate the round budget."""
    res = {}
    for pct in (5, 20):
        ds, n = dataset(ch, pct, ["BASE", "HIST", "GEO", "VIEW"], (2001, 2013))
        cols, _ = ch.cols(["BASE", "HIST", "GEO", "VIEW"])
        rows = ch.rows(0, (2014, 2015))
        Xv = np.asarray(ch.X(0)[rows]).astype(np.float32)[:, cols]; yv = ch.col("y", 0)[rows]
        dv = lgb.Dataset(Xv, label=yv, reference=ds)
        bst = lgb.train(params(n, threads) | {"metric": "auc"}, ds, num_boost_round=1200, valid_sets=[dv],
                        callbacks=[lgb.early_stopping(60, verbose=False)])
        res[pct] = {"rows": n, "best_iter": bst.best_iteration, "valid_auc": bst.best_score["valid_0"]["auc"],
                    "budget": rounds_for(n)}
        print(f"pilot {pct}%: rows {n:,}, best_iter {bst.best_iteration} (budget {rounds_for(n)}), "
              f"valid AUC {bst.best_score['valid_0']['auc']:.4f}", flush=True)
    json.dump(res, open(out / "lab_pilot.json", "w"), indent=1)


def exp_ladder(ch, out, threads, pct=10):
    rungs = [("BASE", ["BASE"]), ("+HIST", ["BASE", "HIST"]), ("+HIST+GEO", ["BASE", "HIST", "GEO"]),
             ("+HIST+VIEW", ["BASE", "HIST", "VIEW"]), ("ALL", ["BASE", "HIST", "GEO", "VIEW"])]
    X, y, yr, ten, blk = test_set(ch, ["BASE", "HIST", "GEO", "VIEW"], (2017, 2019))
    res, preds = {"pct": pct, "test_rows": int(len(y))}, {}
    for name, fams in rungs:
        bst, n = fit(ch, pct, fams, threads)
        cols_all, _ = ch.cols(["BASE", "HIST", "GEO", "VIEW"]); cols, _ = ch.cols(fams)
        p = bst.predict(X[:, [cols_all.index(c) for c in cols]], num_threads=threads)
        preds[name] = p; res[name] = summarise(y, p, yr, ten); res[name]["train_rows"] = n
        if name == "ALL":
            g = bst.feature_importance("gain"); nm = bst.feature_name()
            tot = g.sum()
            res["gain_by_family"] = {f: round(float(sum(g[nm.index(x)] for x in ch.fam[f]) / tot), 3) for f in ch.fam}
            res["top_features"] = [(nm[i], round(float(g[i] / tot), 4)) for i in np.argsort(-g)[:25]]
            bst.save_model(str(out / "model_all.txt"))
        print(f"{name:11s} AUC {res[name]['auc']:.4f}  lift@10 {res[name]['lift10']:.3f}  lift@1 {res[name]['lift1']:.2f}  "
              f"20y+ lift {res[name].get('lift10_t20p', float('nan')):.3f}", flush=True)
    m1718 = yr <= 2018
    pairs = [("BASE", "+HIST"), ("+HIST", "+HIST+GEO"), ("+HIST", "+HIST+VIEW"), ("+HIST+GEO", "ALL"), ("BASE", "ALL")]
    res["ci"] = {f"{b} vs {a}": paired_ci(y, preds[a], preds[b], blk, m1718) for a, b in pairs}
    res["ci_t20p"] = {f"{b} vs {a}": paired_ci(y, preds[a], preds[b], blk, m1718 & (ten >= 20)) for a, b in pairs}
    res["ci_t10_19"] = {f"{b} vs {a}": paired_ci(y, preds[a], preds[b], blk, m1718 & (ten >= 10) & (ten < 20))
                        for a, b in pairs}
    # calibration of ALL: deciles on 2017-18
    p = preds["ALL"][m1718]; yy = y[m1718]
    edges = np.quantile(p, np.linspace(0, 1, 11)); d = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, 9)
    res["calibration_all"] = [[round(float(p[d == i].mean()), 4), round(float(yy[d == i].mean()), 4)] for i in range(10)]
    json.dump(res, open(out / "lab_ladder.json", "w"), indent=1)
    for k, v in res["ci"].items():
        print(f"  {k}: dAUC {v['d_auc']}  dLift10 {v['d_lift10']}  P(better) {v['p_better']}")
    for k, v in res["ci_t20p"].items():
        print(f"  [20y+] {k}: dAUC {v['d_auc']}  dLift10 {v['d_lift10']}")


def exp_curve(ch, out, threads, sizes=(1, 5, 20, 40)):
    sets = [("BASE", ["BASE"]), ("BASE+HIST", ["BASE", "HIST"]), ("ALL", ["BASE", "HIST", "GEO", "VIEW"])]
    X, y, yr, ten, blk = test_set(ch, ["BASE", "HIST", "GEO", "VIEW"], (2017, 2019))
    cols_all, _ = ch.cols(["BASE", "HIST", "GEO", "VIEW"])
    res = {}; preds = {}
    f = out / "lab_curve.json"
    for pct in sizes:
        if pct > ch.n_chunks * 5:
            continue
        for name, fams in sets:
            bst, n = fit(ch, pct, fams, threads)
            cols, _ = ch.cols(fams)
            p = bst.predict(X[:, [cols_all.index(c) for c in cols]], num_threads=threads)
            res[f"{name}@{pct}"] = summarise(y, p, yr, ten) | {"train_rows": n}
            preds[(name, pct)] = p
            print(f"{name:10s} @ {pct:>2}%  AUC {res[f'{name}@{pct}']['auc']:.4f}  lift@10 {res[f'{name}@{pct}']['lift10']:.3f}  "
                  f"20y+ AUC {res[f'{name}@{pct}'].get('auc_t20p', float('nan')):.4f}", flush=True)
            json.dump(res, open(f, "w"), indent=1)
    m1718 = yr <= 2018
    big = max(s for s in sizes if ("ALL", s) in preds)
    res["ci"] = {}
    for name, _ in sets:
        for a, b in zip(sizes[:-1], sizes[1:]):
            if (name, b) in preds:
                res["ci"][f"{name}: {b}% vs {a}%"] = paired_ci(y, preds[(name, a)], preds[(name, b)], blk, m1718)
    res["ci"][f"ALL vs BASE @ {big}%"] = paired_ci(y, preds[("BASE", big)], preds[("ALL", big)], blk, m1718)
    res["ci"][f"ALL vs BASE @ {sizes[0]}%"] = paired_ci(y, preds[("BASE", sizes[0])], preds[("ALL", sizes[0])], blk, m1718)
    res["ci"][f"[20y+] ALL vs BASE @ {big}%"] = paired_ci(y, preds[("BASE", big)], preds[("ALL", big)], blk, m1718 & (ten >= 20))
    json.dump(res, open(f, "w"), indent=1)
    for k, v in res["ci"].items():
        print(f"  {k}: dAUC {v['d_auc']}  dLift10 {v['d_lift10']}")


def exp_rolling(ch, out, threads, pct=10):
    """Refit to the latest year each time versus a model frozen in 2015."""
    fams = ["BASE", "HIST", "GEO", "VIEW"]
    res = {}
    frozen, _ = fit(ch, pct, fams, threads, (2001, 2015), tag="frozen<=2015")
    for test_year in (2017, 2018):
        X, y, yr, ten, blk = test_set(ch, fams, (test_year, test_year))
        fresh, _ = fit(ch, pct, fams, threads, (2001, test_year - 1), tag=f"fresh<={test_year-1}")
        pf, pz = fresh.predict(X, num_threads=threads), frozen.predict(X, num_threads=threads)
        r = {"frozen": {"auc": auc(y, pz), "lift10": lift(y, pz, .1), "mean_pred": float(pz.mean())},
             "fresh": {"auc": auc(y, pf), "lift10": lift(y, pf, .1), "mean_pred": float(pf.mean())},
             "base_rate": float(y.mean()), "ci": paired_ci(y, pz, pf, blk)}
        for name, lo, hi in (("t0_9", 0, 10), ("t10_19", 10, 20), ("t20p", 20, 99)):
            m = (ten >= lo) & (ten < hi)
            r[name] = {"frozen_auc": auc(y[m], pz[m]), "fresh_auc": auc(y[m], pf[m]),
                       "frozen_lift10": lift(y[m], pz[m], .1), "fresh_lift10": lift(y[m], pf[m], .1)}
        r["ci_t20p"] = paired_ci(y, pz, pf, blk, ten >= 20)
        res[str(test_year)] = r
        print(f"{test_year}: frozen AUC {r['frozen']['auc']:.4f} -> fresh {r['fresh']['auc']:.4f}  "
              f"(20y+: {r['t20p']['frozen_auc']:.4f} -> {r['t20p']['fresh_auc']:.4f}); "
              f"mean pred {r['frozen']['mean_pred']:.4f}/{r['fresh']['mean_pred']:.4f} vs actual {r['base_rate']:.4f}", flush=True)
        if test_year == 2018:
            fresh.save_model(str(out / "model_fresh_2017.txt"))
    json.dump(res, open(out / "lab_rolling.json", "w"), indent=1)


if __name__ == "__main__":
    panel_dir, out_dir, exp = sys.argv[1:4]
    threads = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    ch = Chunks(panel_dir)
    {"pilot": exp_pilot, "ladder": exp_ladder, "curve": exp_curve, "rolling": exp_rolling}[exp](ch, out, threads)
