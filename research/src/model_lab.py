"""Model experiments on the national panel (version 2).

Runs, on float16 chunk files written by panel2.py:

  ladder      feature families added one at a time, fixed sample size
  curve       learning curve: the same models at 1%, 5%, 10%, 20%, 40%
              and 100% of all homes: does more data unlock bigger effects?
  rolling     refit each year and predict the next (the deployment
              protocol) against the stale fixed-origin model
  ablate      at the largest sample, leave geography or outlook out
  deploy      the model the prototype scores with (trained to 2018)

Boosting rounds are chosen by early stopping on 2016, a year no
experiment trains or tests on.

Sales are rare (about 4 home-years in 100). Training keeps every sale
and one non-sale in four, each weighted by four, which leaves
probabilities unbiased and makes the largest fits about four times
cheaper. Test and validation rows are never sampled.

Evaluation is out-of-time. The headline test window is 2017-2018 (the
2019 file undercounts late registrations); 2017-2019 is reported for
continuity with earlier documents. Uncertainty is from a block
bootstrap over properties (2,048 hash blocks, Poisson weights), since
rows from one property are not independent.

Usage: python model_lab.py <panel_dir> <out_dir> <experiment> [threads] [sample_pct]
"""

import json
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np

TRAIN = (2001, 2015)
VALID_YEAR = 2016            # the gap year: used only to decide when to stop boosting
MAX_ROUNDS = 800
NEG_KEEP = 4                 # keep every sale and one non-sale home-year in four, weighted back
N_BLOCKS, BOOT = 2048, 300


class Chunks:
    """The training table: year-by-year features stored per row, place
    signals looked up from each row's postcode (signals.py)."""

    def __init__(self, panel_dir):
        import pandas as pd
        import signals as SG
        self.dir = Path(panel_dir)
        self.meta = json.load(open(self.dir / "meta.json"))
        self.tv = self.meta["features"]
        self.place = SG.available()
        self.fam = {k: v for k, v in self.meta["families"].items()}
        for f in self.place:
            self.fam[f] = SG.FAMILIES[f]["columns"]
        # row families: worked out from dated events and stored beside each chunk (panel2.write_row_family)
        self.rowfam = [f for f in SG.ROW_FAMILIES
                       if all((self.dir / f"R_{f}_{c['id']}.npy").exists() for c in self.meta["chunks"])]
        for f in self.rowfam:
            self.fam[f] = SG.ROW_FAMILIES[f]["columns"]
        self.names = self.tv + [c for f in self.place + self.rowfam for c in self.fam[f]]
        self.n_chunks = len(self.meta["chunks"])
        self.presampled = {c["id"]: c.get("presampled", False) for c in self.meta["chunks"]}
        self.postcodes = pd.read_parquet(self.dir / "postcodes.parquet").postcode.to_numpy()
        self._L = {}
        self._cache = {}

    def lookup(self, f):
        if f not in self._L:
            import signals as SG
            self._L[f] = SG.lookup(f, self.postcodes)
        return self._L[f]

    def col(self, kind, c):
        k = (kind, c)
        if k not in self._cache:
            self._cache[k] = np.load(self.dir / f"{kind}_{c}.npy")
        return self._cache[k]

    def X(self, c):
        return View(self, c)

    def release(self):
        """Drop cached columns and place lookups; they reload when next asked for."""
        import gc
        self._cache.clear(); self._L.clear(); gc.collect()

    def rows(self, c, years, max_bucket=None):
        yr = self.col("year", c)
        m = (yr >= years[0]) & (yr <= years[1])
        if max_bucket is not None:
            m &= self.col("bucket", c) < max_bucket
        return np.nonzero(m)[0]

    def cols(self, families):
        want = [f for fam in families for f in self.fam[fam]]
        return [self.names.index(f) for f in want], want


def SG_rowwise(f):
    import signals as SG
    return bool(SG.FAMILIES.get(f, {}).get("rowwise"))


class View:
    """Rows of one chunk with every feature, in Chunks.names order."""

    def __init__(self, ch, c):
        self.ch, self.c = ch, c
        self.T = np.load(ch.dir / f"T_{c}.npy", mmap_mode="r")
        self.R = {f: np.load(ch.dir / f"R_{f}_{c}.npy", mmap_mode="r") for f in ch.rowfam}
        self.pc = ch.col("pc", c)

    def take(self, r, cols):
        cols = np.asarray(cols); ntv = len(self.ch.tv)
        out = np.empty((len(r), len(cols)), np.float64)
        tvc = cols < ntv
        if tvc.any():
            out[:, tvc] = np.asarray(self.T[r])[:, cols[tvc]]
        if (~tvc).any():
            pc = self.pc[r]; off = ntv
            for f in self.ch.place:
                k = len(self.ch.fam[f])
                sel = (cols >= off) & (cols < off + k)
                if sel.any():
                    v = self.ch.lookup(f)[pc]
                    if SG_rowwise(f):                 # worked out home by home from the years owned
                        import signals as SG
                        v = SG.rowwise(f, v, np.asarray(self.T[r, self.ch.tv.index("tenure")], np.float32))
                    out[:, sel] = v[:, cols[sel] - off]
                off += k
            for f in self.ch.rowfam:                  # stored row for row
                k = len(self.ch.fam[f])
                sel = (cols >= off) & (cols < off + k)
                if sel.any():
                    out[:, sel] = np.asarray(self.R[f][r])[:, cols[sel] - off]
                off += k
        return out

    def __getitem__(self, r):
        return self.take(np.asarray(r), np.arange(len(self.ch.names))).astype(np.float32)


class Seq(lgb.Sequence):
    """Out-of-core rows for LightGBM: float16 on disk plus place lookups ->
    float64 batches (the library samples rows through this interface and
    insists on doubles)."""

    def __init__(self, X, rows, cols, batch_size=65536):
        self.X, self.rows, self.cols, self.batch_size = X, rows, np.asarray(cols), batch_size

    def __getitem__(self, idx):
        r = self.rows[idx]
        if np.ndim(r) == 0:
            return self.X.take(np.array([r]), self.cols)[0]
        return self.X.take(np.asarray(r), self.cols)

    def __len__(self):
        return len(self.rows)


def pct_to_chunks(pct):
    """(chunk ids, bucket cap for the last partial chunk) for a sample percentage."""
    full, rem = divmod(pct, 5)
    ids = list(range(int(full))) + ([int(full)] if rem else [])
    return ids, (int(full) * 5 + rem if rem else None)


def dataset(ch, pct, families, years, neg_keep=None):
    neg_keep = NEG_KEEP if neg_keep is None else neg_keep
    ids, cap = pct_to_chunks(pct)
    cols, names = ch.cols(families)
    seqs, ys, ws = [], [], []
    for c in ids:
        rows = ch.rows(c, years, cap if (cap is not None and c == ids[-1]) else None)
        y = ch.col("y", c)[rows]
        if ch.presampled.get(c):                      # stored already sampled by the same rule, with its weights
            w = ch.col("w", c)[rows]
        else:
            if neg_keep > 1:                          # deterministic per row, so every model sees the same sample
                keep = (y == 1) | ((((rows + 1) * 2654435761) >> 9) % neg_keep == 0)
                rows, y = rows[keep], y[keep]
            w = np.where(y == 1, 1.0, float(neg_keep)).astype("float32")
        if LABEL != "y":                              # another target on the same rows, sample and weights
            y = ch.col(LABEL, c)[rows]
        seqs.append(Seq(ch.X(c), rows, cols)); ys.append(y); ws.append(w)
    y = np.concatenate(ys); w = np.concatenate(ws).astype("float32")
    return lgb.Dataset(seqs, label=y, weight=w, feature_name=names, free_raw_data=True,
                       params={"max_bin": 63, "min_data_in_bin": 20, "verbose": -1}), len(y)


# The fit's own randomness (row and column sampling). QM_SEED refits with another seed to measure how much
# two fits of the same model differ; cached results for any other seed are kept apart (~s<seed>).
SEED = int(__import__("os").environ.get("QM_SEED", 7))
# What the model is asked. "y": the home sells in the calendar year. "late" (QM_LABEL=late): the sale completes
# between July of the year and June of the next, so the home was not yet on the market on the scoring day
# (panel2.write_late_label). Fits for another target are cached apart (~<label>).
LABEL = __import__("os").environ.get("QM_LABEL", "y")


def params(n_rows, threads):
    # force_col_wise: left to choose, the library builds a second, row-wise copy
    # of the whole table to time both ways, which does not fit in memory once the
    # house signals are added for every home. Column-wise gives the same trees.
    leaves = 31 if n_rows < 1e6 else 63 if n_rows < 3e6 else 127 if n_rows < 1e7 else 255
    return dict(objective="binary", learning_rate=0.08, num_leaves=leaves,
                min_data_in_leaf=int(np.clip(n_rows / 8000, 80, 1200)), max_bin=63,
                feature_fraction=0.8, bagging_fraction=0.7, bagging_freq=1, lambda_l2=5.0,
                num_threads=threads, verbose=-1, seed=SEED, force_col_wise=True)


def valid_set(ch, cols, chunks=(0, 1), batch=262_144):
    """2016 rows: later than every training year, earlier than every test year.
    Filled in batches straight into one float32 table, so no float64 copy of
    the whole set is ever held."""
    rows = [ch.rows(c, (VALID_YEAR, VALID_YEAR)) for c in chunks]
    X = np.empty((sum(len(r) for r in rows), len(cols)), np.float32); at = 0
    for c, r in zip(chunks, rows):
        V = ch.X(c)
        for i in range(0, len(r), batch):
            b = r[i:i + batch]; X[at:at + len(b)] = V.take(b, cols); at += len(b)
    return X, np.concatenate([ch.col(LABEL, c)[r] for c, r in zip(chunks, rows)])


def test_set(ch, families, years, chunks=(0, 1)):
    cols, _ = ch.cols(families)
    Xs, ys, yrs, ten, blk = [], [], [], [], []
    for c in chunks:
        rows = ch.rows(c, years)
        Xs.append(ch.X(c).take(rows, cols).astype(np.float32))
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


def fit(ch, pct, families, threads, years=TRAIN, n_rounds=None, tag="", neg_keep=None):
    """Train one model. With n_rounds=None the number of boosting rounds is
    chosen by early stopping on 2016, which no experiment tests on."""
    t0 = time.time()
    ds, n = dataset(ch, pct, families, years, neg_keep)
    pr = params(n, threads)
    ds.params.update(pr); ds.construct()
    if n_rounds is None:
        cols, _ = ch.cols(families)
        Xv, yv = valid_set(ch, cols)
        dv = lgb.Dataset(Xv, label=yv, reference=ds); dv.construct(); del Xv   # binned; the float copy is not kept
    ch.release()                                      # the binned copies are all training needs from here
    if n_rounds is None:
        bst = lgb.train(pr | {"metric": "auc"}, ds, num_boost_round=MAX_ROUNDS, valid_sets=[dv],
                        callbacks=[lgb.early_stopping(40, verbose=False)])
        nr = bst.best_iteration
    else:
        bst = lgb.train(pr, ds, num_boost_round=n_rounds); nr = n_rounds
    print(f"  fit {tag or '+'.join(families)} @ {pct}%: {n:,} rows, {nr} rounds, "
          f"{pr['num_leaves']} leaves, {time.time()-t0:.0f}s", flush=True)
    bst.n_rounds_used = nr
    return bst, n


FULL = ["BASE", "HIST", "GEO", "VIEW"]                  # the model as it stood before the house-level signals


def everything(ch):
    """Every family the table and the register can supply."""
    return ["BASE", "HIST"] + ch.place
_TEST = {}


def shared_test(ch):
    if "t" not in _TEST:
        _TEST["t"] = test_set(ch, everything(ch), (2017, 2019))
    return _TEST["t"]


def shared_labels(ch):
    """Outcome, year, tenure and block of every test row, without the
    features: holding every feature of the test set while a model is fitted
    on every home does not fit in memory."""
    if "l" not in _TEST:
        _TEST["l"] = (None,) + test_set(ch, ["BASE"], (2017, 2019))[1:]
    return _TEST["l"]


def predict_cached(ch, out, threads, name, pct, fams):
    """Test-set predictions for one (feature set, sample size), fitted once and
    kept on disk so that later experiments can compare against it."""
    cache = out / "preds"; cache.mkdir(exist_ok=True)
    key = f"{name.replace(' ', '_')}@{pct}" + (f"~s{SEED}" if SEED != 7 else "") + (f"~{LABEL}" if LABEL != "y" else "")
    fp, fj = cache / f"{key}.npy", cache / f"{key}.json"
    if fp.exists() and fj.exists():
        return np.load(fp), json.load(open(fj))
    _TEST.pop("t", None)                             # the fit needs the memory more than a cached test set
    bst, n = fit(ch, pct, fams, threads)
    X = test_set(ch, fams, (2017, 2019))[0]           # same rows in the same order as shared_test
    p = bst.predict(X, num_threads=threads).astype("float32"); del X
    info = {"train_rows": n, "rounds": bst.n_rounds_used, "families": list(fams)}
    (out / "models").mkdir(exist_ok=True); bst.save_model(str(out / "models" / f"{key}.txt"))
    g = bst.feature_importance("gain"); nm = bst.feature_name(); tot = g.sum()
    info["gain_by_family"] = {f: round(float(sum(g[nm.index(x)] for x in ch.fam[f]) / tot), 3) for f in fams}
    if fams == FULL:
        info["top_features"] = [(nm[i], round(float(g[i] / tot), 4)) for i in np.argsort(-g)[:25]]
        bst.save_model(str(out / f"model_all_{pct}.txt"))
    np.save(fp, p); json.dump(info, open(fj, "w"))
    return p, info


# ---------------------------------------------------------------- experiments
def exp_smoke(ch, out, threads):
    """Small end-to-end run to check the pipeline and time it."""
    X, y, yr, ten, blk = test_set(ch, ["BASE", "HIST", "GEO", "VIEW"], (2017, 2019), chunks=(0,))
    cols_all, _ = ch.cols(["BASE", "HIST", "GEO", "VIEW"])
    for fams in (["BASE"], ["BASE", "HIST", "GEO", "VIEW"]):
        bst, n = fit(ch, 1, fams, threads)
        cols, _ = ch.cols(fams)
        p = bst.predict(X[:, [cols_all.index(c) for c in cols]], num_threads=threads)
        r = summarise(y, p, yr, ten)
        print(f"{'+'.join(fams):22s} AUC {r['auc']:.4f} lift@10 {r['lift10']:.3f} mean pred {r['mean_pred']:.4f} "
              f"vs {r['base_rate']:.4f}", flush=True)


def exp_ladder(ch, out, threads, pct=10):
    rungs = [("BASE", ["BASE"]), ("+HIST", ["BASE", "HIST"]), ("+HIST+GEO", ["BASE", "HIST", "GEO"]),
             ("+HIST+VIEW", ["BASE", "HIST", "VIEW"]), ("ALL", FULL)]
    _, y, yr, ten, blk = shared_labels(ch)
    res, preds = {"pct": pct, "test_rows": int(len(y)), "neg_keep": NEG_KEEP}, {}
    for name, fams in rungs:
        p, info = predict_cached(ch, out, threads, name, pct, fams)
        preds[name] = p; res[name] = summarise(y, p, yr, ten) | {k: info[k] for k in ("train_rows", "rounds")}
        if name == "ALL":
            res["gain_by_family"], res["top_features"] = info["gain_by_family"], info["top_features"]
        print(f"{name:11s} AUC {res[name]['auc']:.4f}  lift@10 {res[name]['lift10']:.3f}  lift@1 {res[name]['lift1']:.2f}  "
              f"20y+ lift {res[name].get('lift10_t20p', float('nan')):.3f}", flush=True)
        json.dump(res, open(out / "lab_ladder.json", "w"), indent=1)
    m1718 = yr <= 2018
    pairs = [("BASE", "+HIST"), ("+HIST", "+HIST+GEO"), ("+HIST", "+HIST+VIEW"), ("+HIST+GEO", "ALL"), ("BASE", "ALL")]
    res["ci"] = {f"{b} vs {a}": paired_ci(y, preds[a], preds[b], blk, m1718) for a, b in pairs}
    res["ci_t20p"] = {f"{b} vs {a}": paired_ci(y, preds[a], preds[b], blk, m1718 & (ten >= 20)) for a, b in pairs}
    res["ci_t10_19"] = {f"{b} vs {a}": paired_ci(y, preds[a], preds[b], blk, m1718 & (ten >= 10) & (ten < 20))
                        for a, b in pairs}
    p = preds["ALL"][m1718]; yy = y[m1718]
    edges = np.quantile(p, np.linspace(0, 1, 11)); d = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, 9)
    res["calibration_all"] = [[round(float(p[d == i].mean()), 4), round(float(yy[d == i].mean()), 4)] for i in range(10)]
    json.dump(res, open(out / "lab_ladder.json", "w"), indent=1)
    for k, v in res["ci"].items():
        print(f"  {k}: dAUC {v['d_auc']}  dLift10 {v['d_lift10']}  P(better) {v['p_better']}")
    for k, v in res["ci_t20p"].items():
        print(f"  [20y+] {k}: dAUC {v['d_auc']}  dLift10 {v['d_lift10']}")


def exp_curve(ch, out, threads, sizes=(1, 5, 10, 20, 40, 100)):
    sets = [("BASE", ["BASE"]), ("ALL", FULL)]
    _, y, yr, ten, blk = shared_test(ch)
    res, preds = {"neg_keep": NEG_KEEP}, {}
    f = out / "lab_curve.json"
    sizes = [s_ for s_ in sizes if s_ <= ch.n_chunks * 5]
    for pct in sizes:
        for name, fams in sets:
            p, info = predict_cached(ch, out, threads, name, pct, fams)
            res[f"{name}@{pct}"] = summarise(y, p, yr, ten) | {k: info[k] for k in ("train_rows", "rounds")}
            preds[(name, pct)] = p
            print(f"{name:10s} @ {pct:>2}%  AUC {res[f'{name}@{pct}']['auc']:.4f}  lift@10 {res[f'{name}@{pct}']['lift10']:.3f}  "
                  f"20y+ AUC {res[f'{name}@{pct}'].get('auc_t20p', float('nan')):.4f}", flush=True)
            json.dump(res, open(f, "w"), indent=1)
    m1718 = yr <= 2018
    big, small = sizes[-1], sizes[0]
    res["ci"] = {}
    for name, _ in sets:
        for a, b in zip(sizes[:-1], sizes[1:]):
            res["ci"][f"{name}: {b}% vs {a}%"] = paired_ci(y, preds[(name, a)], preds[(name, b)], blk, m1718)
        res["ci"][f"{name}: {big}% vs {small}%"] = paired_ci(y, preds[(name, small)], preds[(name, big)], blk, m1718)
    for s_ in sizes:
        res["ci"][f"ALL vs BASE @ {s_}%"] = paired_ci(y, preds[("BASE", s_)], preds[("ALL", s_)], blk, m1718)
    res["ci"][f"[20y+] ALL vs BASE @ {big}%"] = paired_ci(y, preds[("BASE", big)], preds[("ALL", big)], blk, m1718 & (ten >= 20))
    res["ci"][f"[20y+] ALL: {big}% vs {small}%"] = paired_ci(y, preds[("ALL", small)], preds[("ALL", big)], blk, m1718 & (ten >= 20))
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
        fresh, _ = fit(ch, pct, fams, threads, (2001, test_year - 1), n_rounds=frozen.n_rounds_used,
                       tag=f"fresh<={test_year-1}")
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
    res["rounds"] = frozen.n_rounds_used
    json.dump(res, open(out / "lab_rolling.json", "w"), indent=1)


def exp_ablate(ch, out, threads, pct=40, drop=("VIEW", "GEO")):
    """At a large sample: what do geography and outlook each add on top of
    everything else? (Leave one family out, compare with the full model.)"""
    _, y, yr, ten, blk = shared_labels(ch)
    res, preds = {"pct": pct}, {}
    rungs = [("ALL", FULL)] + [(f"no {d}", [f for f in FULL if f != d]) for d in drop]
    for name, fams in rungs:
        preds[name], info = predict_cached(ch, out, threads, name, pct, fams)
        res[name] = summarise(y, preds[name], yr, ten) | {k: info[k] for k in ("train_rows", "rounds")}
        print(f"{name:15s} AUC {res[name]['auc']:.4f}  lift@10 {res[name]['lift10']:.3f}  "
              f"20y+ lift {res[name].get('lift10_t20p', float('nan')):.3f}", flush=True)
        json.dump(res, open(out / f"lab_ablate_{pct}.json", "w"), indent=1)
    m = yr <= 2018
    res["ci"] = {f"ALL vs {k}": paired_ci(y, preds[k], preds["ALL"], blk, m) for k in preds if k != "ALL"}
    res["ci_t20p"] = {f"ALL vs {k}": paired_ci(y, preds[k], preds["ALL"], blk, m & (ten >= 20)) for k in preds if k != "ALL"}
    json.dump(res, open(out / f"lab_ablate_{pct}.json", "w"), indent=1)
    for k, v in res["ci"].items():
        print(f"  {k}: dAUC {v['d_auc']}  dLift10 {v['d_lift10']}  P(better) {v['p_better']}")


def exp_sampling(ch, out, threads, pct=5):
    """Does keeping one non-sale in four cost anything? Same model, both ways."""
    _, y, yr, ten, blk = shared_test(ch)
    X = shared_test(ch)[0]; res = {"pct": pct}
    preds = {}
    for name, k in (("every row", 1), ("one non-sale in four", NEG_KEEP)):
        bst, n = fit(ch, pct, FULL, threads, neg_keep=k, tag=name)
        preds[name] = bst.predict(X, num_threads=threads)
        res[name] = summarise(y, preds[name], yr, ten) | {"train_rows": n, "rounds": bst.n_rounds_used}
        print(f"{name:22s} AUC {res[name]['auc']:.4f} lift@10 {res[name]['lift10']:.3f} mean pred {res[name]['mean_pred']:.4f} "
              f"vs {res[name]['base_rate']:.4f}", flush=True)
    res["ci"] = paired_ci(y, preds["every row"], preds["one non-sale in four"], blk, yr <= 2018)
    print("  sampled minus full:", res["ci"])
    json.dump(res, open(out / "lab_sampling.json", "w"), indent=1)


def exp_fitset(ch, out, threads, name, fams, pct=100):
    """Fit one named set of families (e.g. CURRENT, +HOUSE) and report it on 2017-2019."""
    _, y, yr, ten, blk = shared_labels(ch)
    p, info = predict_cached(ch, out, threads, name, pct, fams)
    r = summarise(y, p, yr, ten) | info
    json.dump(r, open(out / f"lab_fit_{name.replace(' ', '_')}@{pct}.json", "w"), indent=1)
    print(f"{name}@{pct}: AUC {r['auc']:.4f}  lift@10 {r['lift10']:.3f}  20y+ lift {r.get('lift10_t20p', float('nan')):.3f}", flush=True)


def exp_deploy(ch, out, threads, pct=20, fams=None, ref_name="ALL"):
    """The model the prototype scores with, trained on 2001-2018 (2019 is
    left out because its file undercounts late registrations)."""
    fams = fams or ["BASE", "HIST", "GEO", "VIEW"]
    ref = out / "preds" / f"{ref_name}@{pct}.json"
    if not ref.exists():                              # a smaller sample than any tested: rounds from the full fit
        ref = out / "preds" / f"{ref_name}@100.json"
    nr = int((json.load(open(ref))["rounds"] if ref.exists() else 350) * 1.1)
    bst, n = fit(ch, pct, fams, threads, (2001, 2018), n_rounds=nr, tag="deploy<=2018")
    bst.save_model(str(out / "model_deploy.txt"))
    json.dump({"name": ref_name, "pct": pct, "train_rows": n, "rounds": nr, "families": fams, "features": bst.feature_name()},
              open(out / "lab_deploy.json", "w"), indent=1)


if __name__ == "__main__":
    panel_dir, out_dir, exp = sys.argv[1:4]
    threads = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    ch = Chunks(panel_dir)
    if exp in ("fitset", "deploy_set"):               # <name> <FAM+FAM+...> [pct]
        name, fams = sys.argv[5], sys.argv[6].split("+")
        pct = int(sys.argv[7]) if len(sys.argv) > 7 else 100
        if exp == "fitset":
            exp_fitset(ch, out, threads, name, fams, pct)
        else:
            exp_deploy(ch, out, threads, pct, fams, ref_name=name)
        sys.exit(0)
    fn = {"smoke": exp_smoke, "ladder": exp_ladder, "curve": exp_curve, "rolling": exp_rolling,
          "ablate": exp_ablate, "deploy": exp_deploy, "sampling": exp_sampling,
          "ablate_view": lambda c, o, t, pct=100: exp_ablate(c, o, t, pct, drop=("VIEW",))}[exp]
    if len(sys.argv) > 5:                             # optional sample percentage
        fn(ch, out, threads, int(sys.argv[5]))
    else:
        fn(ch, out, threads)
