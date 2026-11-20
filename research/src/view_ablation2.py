"""Does the view predict when a home sells? House-level version, two cities.

For each city: every property with sale history, the published 13
features against the same plus house-level outlook averaged over the
houses on its postcode (the finest join available without licensed
address data). Out-of-time (train 2001-2015, test 2017-2019), block
bootstrap by property. Then both cities pooled, and each city's model
tested on the other — the replication test: if the view effect is real
it should carry from Exeter to Bath and back.

Usage: python view_ablation2.py <transactions.parquet> <views2_dir> <out_dir>
"""
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).parent))
from propensity_model import (FEATURES as BASE, TEST_YEARS, TRAIN_YEARS,  # noqa: E402
                              build_panel, district_year_features, featurise)

CITY_OUTCODES = {"exeter": ["EX1", "EX2", "EX3", "EX4"], "bath": ["BA1", "BA2"]}
VIEW = ["m_u_horizon", "m_u_open", "m_u_long", "m_u_long5", "m_u_longest_km", "m_u_water", "m_u_hills",
        "m_u_overlooked", "m_g_horizon", "m_g_overlooked", "m_g_hz_s", "m_g_hz_w",
        "m_sun_evening_jun", "m_sun_equinox", "m_sun_dec", "m_height", "m_garden_clear",
        "m_plot_open", "s_has_garden", "s_has_swgarden"]
READ = ["m_u_long", "m_u_water", "m_u_hills", "m_g_horizon", "m_g_overlooked", "m_sun_evening_jun",
        "m_sun_equinox", "m_garden_clear", "m_height"]
BOOT = 300


def city_panel(tx_all, views_dir, city):
    tx = tx_all[tx_all["outcode"].astype(str).isin(CITY_OUTCODES[city])].copy()
    for c in ("postcode", "outcode", "ptype"):
        tx[c] = tx[c].astype(str).astype("category")
    tx = tx.sort_values(["key", "year", "month"], ignore_index=True)
    dy = district_year_features(tx)
    panel = featurise(build_panel(tx, dy, 100))
    v = pd.read_parquet(f"{views_dir}/postcodes_{city}.parquet").set_index("postcode")
    v = v.reindex(pd.Index(tx["postcode"].cat.categories))
    code = panel["pc_code"].to_numpy(); ok = code >= 0
    for c in VIEW:
        vals = v[c].to_numpy(dtype="float32"); out = np.full(len(panel), np.nan, dtype="float32")
        out[ok] = vals[code[ok]]; panel[c] = out
    panel = panel[panel[VIEW[0]].notna()].copy()
    panel["city"] = city
    panel["block"] = (np.abs(panel["key"].to_numpy()) // 7) % 1024
    return panel


def fit(X, y, seed=7):
    return lgb.train(dict(objective="binary", learning_rate=0.05, num_leaves=31, min_data_in_leaf=150,
                          feature_fraction=0.8, bagging_fraction=0.7, bagging_freq=1, lambda_l2=5.0,
                          verbose=-1, seed=seed, num_threads=3),
                     lgb.Dataset(X, label=y), num_boost_round=350)


def lift10(y, p, w=None):
    o = np.argsort(-p, kind="stable"); y = y[o]; w = np.ones(len(y)) if w is None else w[o]
    cw = np.cumsum(w); k = np.searchsorted(cw, .1 * cw[-1])
    return float(((w * y)[:k + 1].sum() / cw[k]) / ((w * y).sum() / cw[-1]))


def wauc(y, o, w):
    yy, ww = y[o], w[o]; wn, wp = ww * (1 - yy), ww * yy
    return (wp * np.cumsum(wn)).sum() / (wp.sum() * wn.sum())


def compare(tr, te, label, view=None):
    view = VIEW if view is None else list(view)
    ytr, yte = tr["label"].to_numpy(), te["label"].to_numpy()
    pa = fit(tr[BASE].astype("float32"), ytr).predict(te[BASE].astype("float32"))
    pb = fit(tr[BASE + view].astype("float32"), ytr).predict(te[BASE + view].astype("float32"))
    blk = te["block"].to_numpy(); rng = np.random.default_rng(3)
    oa, ob = np.argsort(pa, kind="stable"), np.argsort(pb, kind="stable"); d = []
    for _ in range(BOOT):
        w = rng.poisson(1.0, 1024).astype("float64")[blk]
        d.append(wauc(yte, ob, w) - wauc(yte, oa, w))
    r = {"train_sales": int(ytr.sum()), "test_sales": int(yte.sum()),
         "auc_base": round(float(roc_auc_score(yte, pa)), 4), "auc_view": round(float(roc_auc_score(yte, pb)), 4),
         "lift10_base": round(lift10(yte, pa), 3), "lift10_view": round(lift10(yte, pb), 3),
         "d_auc": [round(float(np.percentile(d, q)), 4) for q in (2.5, 50, 97.5)],
         "p_improves": round(float((np.array(d) > 0).mean()), 3)}
    print(f"{label:28s} AUC {r['auc_base']:.4f} -> {r['auc_view']:.4f}  d {r['d_auc']}  "
          f"P(improves) {r['p_improves']:.2f}  lift@10 {r['lift10_base']:.2f} -> {r['lift10_view']:.2f}", flush=True)
    return r


def directions(panel):
    """Sale-rate by quartile and controlled logistic coefficients."""
    q = {}
    for c in READ:
        band = pd.qcut(panel[c].rank(method="first"), 4, labels=["Q1", "Q2", "Q3", "Q4"])
        q[c] = [round(float(x), 4) for x in panel.groupby(band, observed=True)["label"].mean()]
    ctrl = ["tenure", "log_price_rel", "leasehold", "is_new", "n_prior", "turnover_3y",
            "price_rel_nat", "ptype_D", "ptype_S", "ptype_T", "ptype_F"]
    coefs = {}
    for c in READ:                                    # one view term at a time: they are collinear
        X = panel[ctrl + [c]].astype("float64"); X = X.fillna(X.median()); X["tenure_sq"] = X["tenure"] ** 2
        lr = LogisticRegression(max_iter=2000).fit((X - X.mean()) / X.std().replace(0, 1), panel["label"])
        coefs[c] = round(float(lr.coef_[0][list(X.columns).index(c)]), 4)
    return {"sale_rate_by_quartile": q, "logit_per_sd_one_at_a_time": coefs}


def main(tx_path, views_dir, out_dir):
    tx = pd.read_parquet(tx_path)
    res, panels = {}, {}
    for city in CITY_OUTCODES:
        if not Path(f"{views_dir}/postcodes_{city}.parquet").exists():
            continue
        p = city_panel(tx, views_dir, city); panels[city] = p
        tr = p[p["year"].between(*TRAIN_YEARS)]; te = p[p["year"].between(*TEST_YEARS)]
        res[city] = compare(tr, te, city) | directions(p)
    if len(panels) == 2:
        allp = pd.concat(panels.values(), ignore_index=True)
        tr = allp[allp["year"].between(*TRAIN_YEARS)]; te = allp[allp["year"].between(*TEST_YEARS)]
        res["pooled"] = compare(tr, te, "pooled, both cities") | directions(allp)
        for a, b in (("exeter", "bath"), ("bath", "exeter")):   # train in one city, test in the other
            tr = panels[a][panels[a]["year"].between(*TRAIN_YEARS)]
            te = panels[b][panels[b]["year"].between(*TEST_YEARS)]
            res[f"train_{a}_test_{b}"] = compare(tr, te, f"train {a} -> test {b}")
    json.dump(res, open(Path(out_dir) / "view_ablation2.json", "w"), indent=1)
    for city in panels:
        print(f"\n{city}: annual sale rate, lowest -> highest quartile; controlled coefficient per SD")
        for c in READ:
            q = res[city]["sale_rate_by_quartile"][c]
            print(f"  {c:20s} {100*q[0]:.2f}%  {100*q[1]:.2f}%  {100*q[2]:.2f}%  {100*q[3]:.2f}%   "
                  f"coef {res[city]['logit_per_sd_one_at_a_time'][c]:+.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
