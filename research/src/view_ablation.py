"""Do view features predict when a home sells?

Within Exeter only (the viewshed data covers one city), compare the
published propensity model's features against the same plus outlook
metrics, strictly out-of-time (train 2001-2015, test 2017-2019), with
bootstrap intervals. Then fit a standardised logistic model so the
direction of each view effect can be read off, controlling for tenure,
property type, price and local market.

Hypotheses stated before looking:
  * enclosed / overlooked homes churn faster — but mostly because they
    are terraces and flats; the test is what remains after controls
  * long views and water views are "stay-put" homes: lower hazard
  * a low western horizon (evening sun) and elevation: lower hazard

Usage: python view_ablation.py <transactions_exeter.parquet> <views_postcode.parquet> <out_dir>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).parent))
from propensity_model import (FEATURES as BASE, TEST_YEARS, TRAIN_YEARS,  # noqa: E402
                              build_panel, district_year_features, featurise, lift_at)

VIEW = ["v_horizon", "v_overlooked", "v_open", "v_long", "v_longest_km",
        "v_water", "v_hills", "v_west", "v_south", "v_ground_m"]
VIEW_SRC = {"v_horizon": "g_median_horizon_deg", "v_overlooked": "g_overlooked_share",
            "v_open": "g_open_share", "v_long": "u_long_view_share",
            "v_longest_km": "u_longest_view_km", "v_water": "u_water_share",
            "v_hills": "u_hills_share", "v_west": "g_west_horizon_deg",
            "v_south": "g_south_horizon_deg", "v_ground_m": "ground_m"}
BOOT = 300


def attach_views(panel, views, categories):
    v = views.rename(columns={s: d for d, s in VIEW_SRC.items()}).set_index("postcode")
    v = v.reindex(pd.Index(categories))
    code = panel["pc_code"].to_numpy(); ok = code >= 0
    for c in VIEW:
        vals = v[c].to_numpy(dtype="float32")
        out = np.full(len(panel), np.nan, dtype="float32"); out[ok] = vals[code[ok]]
        panel[c] = out
    return panel


def fit_gb(X, y):
    gb = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.06, max_leaf_nodes=31,
                                        min_samples_leaf=100, random_state=7)
    return gb.fit(X, y)


def main(tx_path, views_path, out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    tx = pd.read_parquet(tx_path); views = pd.read_parquet(views_path)
    dy = district_year_features(tx)
    panel = featurise(build_panel(tx, dy, 100))         # every Exeter property
    panel = attach_views(panel, views, tx["postcode"].cat.categories)
    have = panel["v_horizon"].notna()
    print(f"panel {len(panel):,} rows · view match {have.mean():.1%}", flush=True)
    panel = panel[have]
    tr = panel[panel["year"].between(*TRAIN_YEARS)]; te = panel[panel["year"].between(*TEST_YEARS)]
    y_tr, y_te = tr["label"].to_numpy(), te["label"].to_numpy()
    print(f"train {len(tr):,} ({y_tr.sum():,} sales) · test {len(te):,} ({y_te.sum():,} sales)", flush=True)

    res = {"n_train": int(len(tr)), "n_test": int(len(te)), "sales_test": int(y_te.sum())}
    preds = {}
    for name, feats in (("BASE", BASE), ("BASE+VIEW", BASE + VIEW)):
        gb = fit_gb(tr[feats].astype("float32"), y_tr)
        p = gb.predict_proba(te[feats].astype("float32"))[:, 1]; preds[name] = p
        res[name] = {"auc": round(float(roc_auc_score(y_te, p)), 4),
                     "lift_top10": round(lift_at(y_te, p, .10), 3),
                     "lift_top20": round(lift_at(y_te, p, .20), 3)}
        print(f"{name:10s} AUC {res[name]['auc']:.4f}  lift@10 {res[name]['lift_top10']:.3f}", flush=True)

    rng = np.random.default_rng(3); idx = np.arange(len(y_te)); d_auc, d_lift = [], []
    for _ in range(BOOT):
        s = rng.choice(idx, len(idx), replace=True)
        if y_te[s].sum() < 20: continue
        d_auc.append(roc_auc_score(y_te[s], preds["BASE+VIEW"][s]) - roc_auc_score(y_te[s], preds["BASE"][s]))
        d_lift.append(lift_at(y_te[s], preds["BASE+VIEW"][s], .10) - lift_at(y_te[s], preds["BASE"][s], .10))
    res["delta"] = {"auc": [round(float(np.percentile(d_auc, q)), 4) for q in (2.5, 50, 97.5)],
                    "lift_top10": [round(float(np.percentile(d_lift, q)), 3) for q in (2.5, 50, 97.5)],
                    "p_auc_improves": round(float((np.array(d_auc) > 0).mean()), 3)}
    print("delta AUC [2.5, 50, 97.5]:", res["delta"]["auc"], "· P(improves)", res["delta"]["p_auc_improves"])

    # Interpretable: standardised logistic regression, train years, view terms + controls.
    ctrl = ["tenure", "log_price_rel", "leasehold", "is_new", "n_prior", "turnover_3y",
            "price_rel_nat", "ptype_D", "ptype_S", "ptype_T", "ptype_F"]
    Xl = tr[ctrl + VIEW].astype("float64").fillna(tr[ctrl + VIEW].median())
    Xl["tenure_sq"] = Xl["tenure"] ** 2
    mu, sd = Xl.mean(), Xl.std().replace(0, 1)
    lr = LogisticRegression(max_iter=2000, C=1.0).fit((Xl - mu) / sd, y_tr)
    coefs = dict(zip(Xl.columns, lr.coef_[0]))
    res["logit_view_coefs_per_sd"] = {k: round(float(coefs[k]), 4) for k in VIEW}
    # Raw sale rates by view quartile, for a plain-English read.
    q = {}
    for c in ("v_long", "v_water", "v_overlooked", "v_horizon", "v_west"):
        band = pd.qcut(panel[c].rank(method="first"), 4, labels=["Q1", "Q2", "Q3", "Q4"])
        q[c] = panel.groupby(band, observed=True)["label"].mean().round(4).to_dict()
    res["sale_rate_by_quartile"] = q
    with open(out / "view_ablation.json", "w") as fh:
        json.dump(res, fh, indent=1)
    print("\nlogistic coefficients per 1 SD (positive = sells sooner):")
    for k, v in sorted(res["logit_view_coefs_per_sd"].items(), key=lambda kv: -abs(kv[1])):
        print(f"  {k:14s} {v:+.3f}")
    print("\nannual sale rate by quartile (raw, no controls):")
    for c, d in q.items():
        print(f"  {c:14s} " + "  ".join(f"{k} {100*v:.2f}%" for k, v in d.items()))


if __name__ == "__main__":
    main(*sys.argv[1:4])
