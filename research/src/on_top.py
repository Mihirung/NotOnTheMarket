"""Do the house-level measures add anything to the national model?

The national model was trained on every home in England and Wales but
never saw the house-level measures, which exist only for the cities run
through city_views.py and light.py. This asks what those measures would
add if they were given to it.

score   Every home-year of 2017 and 2018 in those cities, scored by the
        every-home national model. That model was trained on sales up to
        2015, so these are years it has not seen.

test    Three questions, all on those unseen years.
        1. How well does the national model already rank homes inside a
           district here?
        2. Once the national model's own score is allowed for, is there
           anything left in each measure? The change in the yearly chance
           of a sale for one more hour of sun, or one typical step.
        3. Does it pick better doors? Weights for combining the national
           score with the measures are learned in every city but one and
           applied to the city left out. Reported as the change in the
           share of sellers found in the best tenth of each district.

Ranges re-sample whole properties.

Usage:
  python on_top.py score <transactions.parquet> <geo.parquet> <view30.parquet> <model_all_100.txt> <scored.parquet>
  python on_top.py test <scored.parquet> <views2_dir>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from city_views import CITIES as ALL_CITIES  # noqa: E402

YEARS = (2017, 2018)
NBLK, BOOT = 1024, 300


def score(tx_path, geo_path, view_path, model_path, out_path):
    import lightgbm as lgb
    from panel2 import ALL, Panel
    cities = list(ALL_CITIES)
    panel = Panel(tx_path, geo_path, view_path)
    bst = lgb.Booster(model_file=model_path)
    assert bst.feature_name() == ALL, "model features do not match the panel"
    oc_of = panel.oc_names[panel.oc]
    parts = []
    for city in cities:
        s = np.nonzero(np.isin(oc_of, ALL_CITIES[city]["outcodes"]))[0]
        rows, years, label = panel.expand(s, *YEARS)
        X = np.clip(panel.features(rows, years), -6e4, 6e4).astype("float16").astype("float64")   # as the model was trained
        parts.append(pd.DataFrame({"city": city, "postcode": panel.pc_names[panel.pc[rows]], "district": oc_of[rows],
                                   "year": years, "label": label, "p_nat": bst.predict(X, num_threads=2),
                                   "key": panel.key[rows], "tenure": years - panel.year[rows]}))
        print(f"{ALL_CITIES[city]['name']}: {len(rows):,} home-years, {int(label.sum()):,} sales", flush=True)
    pd.concat(parts, ignore_index=True).to_parquet(out_path, index=False)


def top_mask(score, group, frac=0.10):
    """The best `frac` of each group by score."""
    order = np.lexsort((-score, group))
    g = group[order]
    start = np.r_[0, np.nonzero(np.diff(g))[0] + 1]; size = np.diff(np.r_[start, len(g)])
    pos = np.arange(len(g)) - np.repeat(start, size)
    keep = pos < np.repeat(np.ceil(frac * size), size)
    m = np.zeros(len(g), bool); m[order] = keep
    return m


def lift(y, mask, w):
    return float(((w * y)[mask].sum() / w[mask].sum()) / ((w * y).sum() / w.sum()))


def wauc(y, order, w):
    yy, ww = y[order], w[order]; wn, wp = ww * (1 - yy), ww * yy
    return float((wp * np.cumsum(wn)).sum() / (wp.sum() * wn.sum()))


def test(scored_path, views_dir):
    from sklearn.linear_model import LogisticRegression
    from scale_tests import COLS, IDX, SETS, SINGLE, view_table
    d = pd.read_parquet(scored_path)
    cities = [c for c in d.city.unique() if (Path(views_dir) / f"light_{c}.parquet").exists()]
    d = d[d.city.isin(cities)].reset_index(drop=True)
    V = {c: view_table(c, views_dir) for c in cities}
    both = pd.concat(V.values()); mu, sd = both.mean(), both.std()
    M = np.full((len(d), len(COLS)), np.nan)
    for c in cities:
        m = (d.city == c).to_numpy()
        M[m] = ((V[c][COLS] - mu[COLS]) / sd[COLS]).reindex(d.postcode[m]).to_numpy()
    known = np.isfinite(M[:, 0])
    d, M = d[known].reset_index(drop=True), np.nan_to_num(M[known])
    y = d.label.to_numpy(dtype="float64")
    z = np.log(d.p_nat.clip(1e-5, 1 - 1e-5) / (1 - d.p_nat.clip(1e-5, 1 - 1e-5))).to_numpy()
    blk = ((np.abs(d.key.to_numpy()) // 7) % NBLK).astype(int)
    grp = pd.factorize(d.district + "_" + d.year.astype(str))[0]
    city = d.city.to_numpy()
    rng = np.random.default_rng(5); W = rng.poisson(1.0, (BOOT, NBLK)).astype("float64")
    res = {"home_years": {c: int((city == c).sum()) for c in cities}, "sales": {c: int(y[city == c].sum()) for c in cities}}
    print("home-years in 2017 and 2018:", res["home_years"], " sales:", res["sales"], flush=True)

    # 1. the national model on its own
    res["national"] = {}
    print("\n1. THE NATIONAL MODEL ON ITS OWN, on years it has not seen")
    for c in cities + ["all"]:
        m = np.ones(len(d), bool) if c == "all" else city == c
        tm = top_mask(z[m], grp[m])
        res["national"][c] = {"lift_best_tenth_of_district": round(lift(y[m], tm, np.ones(m.sum())), 3),
                              "auc": round(wauc(y[m], np.argsort(z[m], kind="stable"), np.ones(m.sum())), 4)}
        print(f"  {c:10s} sellers in the best tenth of a district: {res['national'][c]['lift_best_tenth_of_district']:.2f} times random; "
              f"ranking score {res['national'][c]['auc']:.4f}", flush=True)

    # 2. what is left in each measure once the national score is allowed for
    cy = pd.get_dummies(d.city + "_" + d.year.astype(str), dtype="float64").to_numpy()
    base = np.column_stack([cy, z, z ** 2, z ** 3])
    order = np.argsort(blk, kind="stable"); cuts = np.searchsorted(blk[order], np.arange(NBLK + 1))
    res["left_over"] = {}
    print("\n2. WHAT IS LEFT ONCE THE NATIONAL MODEL'S SCORE IS ALLOWED FOR")
    print("   change in the yearly chance of a sale, percentage points (95% range)")
    for col, label, unit in SINGLE:
        X = np.column_stack([base, M[:, IDX[col]]]); k = 100.0 / (sd[col] if unit == "hour" else 1.0)
        XtX = np.stack([X[order[cuts[i]:cuts[i + 1]]].T @ X[order[cuts[i]:cuts[i + 1]]] for i in range(NBLK)])
        Xty = np.stack([X[order[cuts[i]:cuts[i + 1]]].T @ y[order[cuts[i]:cuts[i + 1]]] for i in range(NBLK)])
        est = k * np.linalg.lstsq(XtX.sum(0), Xty.sum(0), rcond=None)[0][-1]
        bs = [k * np.linalg.lstsq(np.tensordot(w, XtX, 1), w @ Xty, rcond=None)[0][-1] for w in W]
        res["left_over"][col] = {"label": label, "unit": unit, "est": round(float(est), 3),
                                 "range": [round(float(np.percentile(bs, 2.5)), 3), round(float(np.percentile(bs, 97.5)), 3)]}
        r = res["left_over"][col]
        print(f"   one more {unit} of {label:42s} {r['est']:+.3f} ({r['range'][0]:+.3f} to {r['range'][1]:+.3f})", flush=True)

    # 3. does it pick better doors in a city it has not seen?
    res["picking"] = {}
    print("\n3. PICKING DOORS IN A CITY LEFT OUT. National score alone against national score plus the measures.")
    print("   weights learned in the other cities; sellers in the best tenth of each district, times random")
    for name, cols in SETS.items():
        j = [IDX[c] for c in cols]
        gains = []
        for held in cities:
            tr, te = city != held, city == held
            F = np.column_stack([z, M[:, j]])
            lr = LogisticRegression(C=1e4, max_iter=500).fit(F[tr], y[tr])
            s = F[te] @ lr.coef_[0]
            yt, zt, gt, bt = y[te], z[te], grp[te], blk[te]
            ma, mb = top_mask(zt, gt), top_mask(s, gt)
            oa, ob = np.argsort(zt, kind="stable"), np.argsort(s, kind="stable")
            one = np.ones(te.sum())
            dl = [lift(yt, mb, w[bt]) - lift(yt, ma, w[bt]) for w in W]
            da = [wauc(yt, ob, w[bt]) - wauc(yt, oa, w[bt]) for w in W]
            r = {"lift_national": round(lift(yt, ma, one), 3), "lift_with": round(lift(yt, mb, one), 3),
                 "lift_change_range": [round(float(np.percentile(dl, 2.5)), 3), round(float(np.percentile(dl, 97.5)), 3)],
                 "auc_change": round(wauc(yt, ob, one) - wauc(yt, oa, one), 4),
                 "auc_change_range": [round(float(np.percentile(da, 2.5)), 4), round(float(np.percentile(da, 97.5)), 4)]}
            res["picking"][f"{held}_{name}"] = r; gains.append((r["lift_with"] - r["lift_national"], te.sum()))
            print(f"   {name:13s} left out {held:9s} {r['lift_national']:.3f} -> {r['lift_with']:.3f}  "
                  f"change range ({r['lift_change_range'][0]:+.3f} to {r['lift_change_range'][1]:+.3f})   "
                  f"ranking score change {r['auc_change']:+.4f} ({r['auc_change_range'][0]:+.4f} to {r['auc_change_range'][1]:+.4f})", flush=True)
        res["picking"][f"average_{name}"] = round(float(np.average([g for g, _ in gains], weights=[n for _, n in gains])), 4)
        print(f"   {name:13s} average change in lift across cities: {res['picking'][f'average_{name}']:+.4f}", flush=True)
    json.dump(res, open(Path(views_dir) / "on_top.json", "w"), indent=1)


if __name__ == "__main__":
    if sys.argv[1] == "score":
        score(*sys.argv[2:7])
    else:
        test(*sys.argv[2:4])
