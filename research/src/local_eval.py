"""Judge every fitted model the way a campaign would use it: locally.

A buyer chooses an area and we choose which doors in it to write to. So
the ranking that matters is within a postcode district in a given year,
not across the whole country. National AUC rewards a model for knowing
that one town turns over faster than another, which is no help once the
town has been chosen, and punishes it when regional markets shift.

For each cached set of test predictions (model_lab.py, outputs/lab/preds)
this computes, on 2017 and 2018:

  local lift@10   mail the top tenth of each district-year: how many
                  times more sellers than a random tenth?
  local AUC       ranking skill inside a district-year, averaged with
                  weight by number of sales

and block-bootstrap intervals (by property) for the comparisons the
write-up quotes.

Usage: python local_eval.py <panel_dir> <lab_dir>
"""
import json
import sys
from pathlib import Path

import numpy as np

N_BLOCKS, BOOT = 2048, 300
PAIRS = [("BASE@10", "+HIST@10"), ("+HIST@10", "+HIST+GEO@10"), ("+HIST@10", "+HIST+VIEW@10"), ("+HIST@10", "ALL@10"),
         ("BASE@10", "ALL@10"), ("BASE@1", "ALL@1"), ("BASE@5", "ALL@5"), ("BASE@20", "ALL@20"), ("BASE@40", "ALL@40"),
         ("BASE@5", "ALL@40"), ("ALL@1", "ALL@5"), ("ALL@5", "ALL@10"), ("ALL@10", "ALL@20"), ("ALL@20", "ALL@40"),
         ("ALL@1", "ALL@40"), ("ALL@5", "ALL@40"), ("BASE@1", "BASE@40"), ("BASE@5", "BASE@40"),
         ("no_VIEW@20", "ALL@20"), ("no_GEO@20", "ALL@20"),
         ("BASE@100", "ALL@100"), ("BASE@5", "ALL@100"), ("ALL@40", "ALL@100"), ("ALL@5", "ALL@100"),
         ("ALL@1", "ALL@100"), ("BASE@1", "BASE@100"), ("no_VIEW@100", "ALL@100"),
         ("CURRENT@100", "+HOUSE@100"), ("CURRENT@100", "+AREA@100"), ("CURRENT@100", "+HOUSE+AREA@100"),
         ("ALL@100", "CURRENT@100"), ("CURRENT@100", "NOVIEW30+HOUSE@100"),
         ("ALL@100", "+HOUSE@100"), ("ALL@100", "+AREA@100"), ("ALL@100", "+HOUSE+AREA@100"),
         ("CURRENT@100", "+AMENITY@100"), ("CURRENT@100", "+PD@100"), ("CURRENT@100", "+ALLNEW@100"),
         ("ALL@100", "+ALLNEW@100"), ("+HOUSE+AREA@100", "+ALLNEW@100"),
         ("CURRENT@100", "+HOUSE+AREA+PD@100"), ("ALL@100", "+HOUSE+AREA+PD@100"),
         ("+HOUSE+AREA@100", "+HOUSE+AREA+PD@100"), ("+HOUSE+AREA+PD@100", "+ALLNEW@100"),
         ("+HOUSE+AREA+PD@100", "+HOUSE+AREA+PD+CLIMATE@100"), ("CURRENT@100", "+HOUSE+AREA+PD+CLIMATE@100"),
         ("+HOUSE+AREA+PD+CLIMATE@100", "+ALLNEW@100")]
TENURE = [("all", 0, 99), ("t0_9", 0, 10), ("t10_19", 10, 20), ("t20p", 20, 99)]


def load_test(panel_dir, chunks=(0, 1), years=(2017, 2019)):
    d = Path(panel_dir); out = {k: [] for k in ("y", "year", "tenure", "block", "district")}
    for c in chunks:
        yr = np.load(d / f"year_{c}.npy"); m = (yr >= years[0]) & (yr <= years[1])
        for k in out:
            out[k].append(np.load(d / f"{k}_{c}.npy")[m])
    return {k: np.concatenate(v) for k, v in out.items()}


class Local:
    """Test rows of one tenure band, grouped by district-year and pre-sorted
    so that each model costs one sort."""

    def __init__(self, t, lo=0, hi=99):
        self.keep = (t["year"] <= 2018) & (t["tenure"] >= lo) & (t["tenure"] < hi)
        self.y = t["y"][self.keep].astype("float64"); self.block = t["block"][self.keep]
        g = t["district"][self.keep].astype(np.int64) * 4 + (t["year"][self.keep] - 2017)
        _, self.g = np.unique(g, return_inverse=True)
        self.size = np.bincount(self.g)
        self.start = np.concatenate(([0], np.cumsum(self.size)[:-1]))

    def top_mask(self, p, frac=0.10):
        """True for rows in the top `frac` of their own district-year."""
        o = np.lexsort((-p, self.g)); gs = self.g[o]
        pos = np.arange(len(o)) - self.start[gs]
        top = np.zeros(len(o), dtype=bool); top[o] = pos < np.round(frac * self.size[gs])
        return top

    def lift(self, top, w=None):
        w = np.ones(len(self.y)) if w is None else w
        return float(((w * self.y * top).sum() / (w * top).sum()) / ((w * self.y).sum() / w.sum()))

    def auc(self, p):
        o = np.lexsort((p, self.g)); gs = self.g[o]; ys = self.y[o]
        rank = np.arange(len(o)) - self.start[gs] + 1
        npos = np.bincount(gs, weights=ys, minlength=len(self.size)); nneg = self.size - npos
        srank = np.bincount(gs, weights=rank * ys, minlength=len(self.size))
        ok = (npos > 0) & (nneg > 0)
        a = (srank[ok] - npos[ok] * (npos[ok] + 1) / 2) / (npos[ok] * nneg[ok])
        return float(np.average(a, weights=npos[ok]))


def main(panel_dir, lab_dir):
    lab = Path(lab_dir); preds_dir = lab / "preds"
    t = load_test(panel_dir)
    bands = {tn: Local(t, lo, hi) for tn, lo, hi in TENURE}
    L = bands["all"]
    names = sorted(f.stem for f in preds_dir.glob("*.npy"))
    res = {"n_rows": int(len(L.y)), "n_sales": int(L.y.sum()), "n_district_years": int(len(L.size)),
           "sales_by_band": {tn: int(b.y.sum()) for tn, b in bands.items()}}
    tops = {}
    print(f"{len(L.y):,} test home-years, {int(L.y.sum()):,} sales, {len(L.size):,} district-years; sales by band {res['sales_by_band']}")
    print(f"{'model':16s} {'local AUC':>9s} {'lift@10':>8s} {'lift@5':>7s} {'lift@20':>8s}   lift@10 within band: 0-9y  10-19y  20y+")
    for n in names:
        full = np.load(preds_dir / f"{n}.npy")
        tops[n] = {tn: b.top_mask(full[b.keep]) for tn, b in bands.items()}
        p = full[L.keep]
        r = {"local_auc": round(L.auc(p), 4), "local_lift10": round(L.lift(tops[n]["all"]), 3),
             "local_lift5": round(L.lift(L.top_mask(p, .05)), 3), "local_lift20": round(L.lift(L.top_mask(p, .20)), 3)}
        for tn, b in bands.items():
            if tn != "all":
                r[f"local_lift10_{tn}"] = round(b.lift(tops[n][tn]), 3)
                r[f"local_auc_{tn}"] = round(b.auc(full[b.keep]), 4)
        res[n] = r
        print(f"{n:16s} {r['local_auc']:9.4f} {r['local_lift10']:8.3f} {r['local_lift5']:7.3f} {r['local_lift20']:8.3f}   "
              f"{r['local_lift10_t0_9']:.3f}  {r['local_lift10_t10_19']:.3f}  {r['local_lift10_t20p']:.3f}")
    rng = np.random.default_rng(5)
    draws = [rng.poisson(1.0, N_BLOCKS).astype("float64") for _ in range(BOOT)]
    res["ci"] = {}
    print("\ndifference in local lift@10 (second minus first), 95% interval by block bootstrap over properties")
    for a, b in PAIRS:
        if a in tops and b in tops:
            entry = {}
            for tn, band in bands.items():
                d = [band.lift(tops[b][tn], w[band.block]) - band.lift(tops[a][tn], w[band.block]) for w in draws]
                entry[tn] = [round(float(np.percentile(d, q)), 3) for q in (2.5, 50, 97.5)] + [round(float((np.array(d) > 0).mean()), 3)]
            res["ci"][f"{b} vs {a}"] = entry
            print(f"  {b:14s} vs {a:14s} all {entry['all'][:3]} P {entry['all'][3]:.2f} | 10-19y {entry['t10_19'][:3]} "
                  f"| 20y+ {entry['t20p'][:3]} P {entry['t20p'][3]:.2f}")
    json.dump(res, open(lab / "lab_local.json", "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:3])
