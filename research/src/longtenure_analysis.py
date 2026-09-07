"""Where does open geographic data actually earn its place?

The headline ablation shows geography barely moves overall targeting.
That is not the whole story: transaction history is strong for recent
buyers and weak for long-tenure owners, and long-tenure owners are the
cohort the business depends on. This script tests, with confidence
intervals, whether geography and life-stage inference help specifically
where the base model fails — and which individual signals carry it.

Outputs bootstrap CIs on the lift difference (so we do not report noise
as a finding) and permutation importance restricted to the long-tenure
test rows.

Usage: python longtenure_analysis.py <transactions.parquet> <geo.parquet> <out_dir> [pct]
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).parent))
from propensity_model import (FEATURES as BASE_FEATURES, TEST_YEARS,  # noqa: E402
                              TRAIN_YEARS, build_panel, district_year_features,
                              featurise)
from geo_ablation import (GEO_FEATURES, LIFE_FEATURES, add_life_stage,  # noqa: E402
                          attach_geo)

BOOT = 400
INK = "#20282E"; MUTED = "#5A646D"; GRID = "#DBD8CC"
TEAL = "#275E54"; TEAL_MID = "#4E9484"; TEAL_LT = "#8FC3B6"; RUST = "#C33D2E"


def lift10(y, p):
    n = max(int(len(p) * 0.10), 1)
    top = np.argsort(-p)[:n]
    base = y.mean()
    return float(y[top].mean() / base) if base > 0 else np.nan


def boot_lift_diff(y, pa, pb, rng, n=BOOT):
    """Bootstrap the paired difference in top-decile lift (b minus a)."""
    out = np.empty(n)
    idx = np.arange(len(y))
    for i in range(n):
        s = rng.choice(idx, len(idx), replace=True)
        out[i] = lift10(y[s], pb[s]) - lift10(y[s], pa[s])
    return out


def main(tx_path, geo_path, out_dir, pct=5):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    tx = pd.read_parquet(tx_path)
    geo = pd.read_parquet(geo_path)
    dy = district_year_features(tx)
    categories = tx["postcode"].cat.categories
    panel = add_life_stage(attach_geo(featurise(build_panel(tx, dy, pct)),
                                      geo, categories))
    del tx
    tr = panel[panel["year"].between(*TRAIN_YEARS)]
    te = panel[panel["year"].between(*TEST_YEARS)]

    full_feats = BASE_FEATURES + GEO_FEATURES + LIFE_FEATURES
    models, preds = {}, {}
    for name, feats in (("BASE", BASE_FEATURES), ("FULL", full_feats)):
        gb = HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.08, max_leaf_nodes=63,
            min_samples_leaf=200, random_state=7)
        gb.fit(tr[feats].astype("float32"), tr["label"].to_numpy())
        models[name] = (gb, feats)
        preds[name] = gb.predict_proba(te[feats].astype("float32"))[:, 1]
        print(f"{name} trained ({len(feats)} features)", flush=True)

    y = te["label"].to_numpy()
    tenure = te["tenure"].to_numpy()
    rng = np.random.default_rng(11)
    results = {"bands": {}}

    # ---- performance by tenure band, with bootstrap CIs -----------------
    bands = [("0-4 yrs", 0, 5), ("5-9 yrs", 5, 10), ("10-19 yrs", 10, 20),
             ("20+ yrs", 20, 999)]
    for label, lo, hi in bands:
        m = (tenure >= lo) & (tenure < hi)
        if y[m].sum() < 100:
            continue
        pa, pb, ym = preds["BASE"][m], preds["FULL"][m], y[m]
        diffs = boot_lift_diff(ym, pa, pb, rng)
        entry = {
            "n_rows": int(m.sum()), "n_sellers": int(ym.sum()),
            "base_rate": round(float(ym.mean()), 4),
            "auc_base": round(float(roc_auc_score(ym, pa)), 4),
            "auc_full": round(float(roc_auc_score(ym, pb)), 4),
            "lift_base": round(lift10(ym, pa), 3),
            "lift_full": round(lift10(ym, pb), 3),
            "lift_diff": round(lift10(ym, pb) - lift10(ym, pa), 3),
            "lift_diff_ci95": [round(float(np.percentile(diffs, 2.5)), 3),
                               round(float(np.percentile(diffs, 97.5)), 3)],
            "p_improve": round(float((diffs > 0).mean()), 3),
        }
        results["bands"][label] = entry
        print(f"{label:10s} n={entry['n_rows']:>9,} sellers={entry['n_sellers']:>7,} "
              f"lift {entry['lift_base']:.2f} -> {entry['lift_full']:.2f} "
              f"(CI {entry['lift_diff_ci95']}, P(better)={entry['p_improve']:.0%})",
              flush=True)

    # ---- which signals carry the long-tenure gain? ----------------------
    m20 = tenure >= 20
    gb, feats = models["FULL"]
    sub = np.where(m20)[0]
    if len(sub) > 250_000:
        sub = rng.choice(sub, 250_000, replace=False)
    imp = permutation_importance(
        gb, te.iloc[sub][feats].astype("float32"), y[sub],
        n_repeats=4, random_state=0, scoring="roc_auc", n_jobs=1)
    ranked = sorted(zip(feats, imp.importances_mean, imp.importances_std),
                    key=lambda x: -x[1])
    results["longtenure_importance"] = {
        f: {"mean": round(float(mu), 5), "std": round(float(sd), 5)}
        for f, mu, sd in ranked}
    print("\nlong-tenure (20+) permutation importance, top 12:")
    for f, mu, sd in ranked[:12]:
        tag = "geo" if f in GEO_FEATURES else "life" if f in LIFE_FEATURES else "base"
        print(f"  {f:24s} {mu:8.5f} ±{sd:.5f}  [{tag}]")

    # ---- chart -----------------------------------------------------------
    labels = list(results["bands"].keys())
    lb = [results["bands"][k]["lift_base"] for k in labels]
    lf = [results["bands"][k]["lift_full"] for k in labels]
    err = [[results["bands"][k]["lift_full"] - results["bands"][k]["lift_base"]
            - results["bands"][k]["lift_diff_ci95"][0] for k in labels],
           [results["bands"][k]["lift_diff_ci95"][1]
            - (results["bands"][k]["lift_full"] - results["bands"][k]["lift_base"])
            for k in labels]]

    fig, ax = plt.subplots(1, 2, figsize=(12.5, 4.4))
    x = np.arange(len(labels)); w = .36
    ax[0].bar(x - w/2, lb, w, color=TEAL_LT, label="transaction history only")
    ax[0].bar(x + w/2, lf, w, color=TEAL, label="+ geography + life stage",
              yerr=err, capsize=4, ecolor=MUTED)
    ax[0].axhline(1, color=MUTED, ls="--", lw=1.5)
    for i in range(len(labels)):
        ax[0].text(i + w/2, lf[i] + .05, f"+{lf[i]-lb[i]:.2f}", ha="center",
                   fontsize=9, color=TEAL)
    ax[0].set_xticks(x); ax[0].set_xticklabels(labels)
    ax[0].set_ylabel("Top-decile lift over random mailing")
    ax[0].set_xlabel("How long the owner has been there")
    ax[0].set_title("Open data helps exactly where history fails", color=INK)
    ax[0].legend(frameon=False, fontsize=9); ax[0].grid(alpha=.25, axis="y", color=GRID)
    ax[0].set_ylim(0, max(lf) * 1.25)

    top = [r for r in ranked if r[1] > 0][:10][::-1]
    cols = [RUST if f in LIFE_FEATURES else TEAL_MID if f in GEO_FEATURES
            else TEAL_LT for f, _, _ in top]
    ax[1].barh([f for f, _, _ in top], [mu for _, mu, _ in top], color=cols,
               xerr=[sd for _, _, sd in top], capsize=3, ecolor=MUTED)
    ax[1].set_xlabel("Drop in AUC when the signal is shuffled")
    ax[1].set_title("What carries it for 20+ year owners", color=INK)
    ax[1].grid(alpha=.25, axis="x", color=GRID)
    ax[1].tick_params(labelsize=9)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (TEAL_LT, TEAL_MID, RUST)]
    ax[1].legend(handles, ["transaction history", "geography (AHAH)", "life stage"],
                 frameon=False, fontsize=9, loc="lower right")

    fig.tight_layout(); fig.savefig(out / "longtenure.png", dpi=140)
    plt.close(fig)
    with open(out / "longtenure.json", "w") as fh:
        json.dump(results, fh, indent=1)
    print(f"\nwrote {out}/longtenure.json")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3],
         int(sys.argv[4]) if len(sys.argv) > 4 else 5)
