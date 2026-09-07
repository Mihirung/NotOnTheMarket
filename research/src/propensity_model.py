"""Sale-propensity feasibility experiment on real Land Registry data.

Frames "which homes will sell?" as discrete-time hazard prediction:
one row per (property, year) while owned, label = property sells that
year. Features use only information available before the year starts.
Trained on 2001-2015, evaluated out-of-time on 2017-2019.

The point is not a production model — it is to measure how much signal
exists in transaction history + local-market context alone, before any
EPC / demographic / listing enrichment.

Usage: python propensity_model.py <transactions.parquet> <out_dir> [sample_pct]
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
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score

END_YEAR = 2019
TRAIN_YEARS = (2001, 2015)
TEST_YEARS = (2017, 2019)


def district_year_features(tx: pd.DataFrame):
    """Per (outcode, year): sales count, median price, cumulative stock seen."""
    g = tx.groupby(["outcode", "year"], observed=True)
    dy = g.agg(n_sales=("price", "size"), med_price=("price", "median"))
    dy = dy.reset_index()

    first = tx.groupby("key", observed=True).agg(
        outcode=("outcode", "first"), first_year=("year", "min"))
    new_props = first.groupby(["outcode", "first_year"], observed=True).size()
    new_props = new_props.rename("n_new").reset_index()
    new_props.columns = ["outcode", "year", "n_new"]

    years = np.arange(1995, END_YEAR + 1)
    outcodes = tx["outcode"].cat.categories
    full = pd.MultiIndex.from_product([outcodes, years],
                                      names=["outcode", "year"]).to_frame(index=False)
    full = full.merge(dy, how="left").merge(new_props, how="left")
    full[["n_sales", "n_new"]] = full[["n_sales", "n_new"]].fillna(0)
    full.sort_values(["outcode", "year"], inplace=True, ignore_index=True)
    full["stock_seen"] = full.groupby("outcode", observed=True)["n_new"].cumsum()
    full["med_price"] = full.groupby("outcode", observed=True)["med_price"].ffill()

    nat = tx.groupby("year")["price"].median().rename("nat_med").reset_index()
    full = full.merge(nat, on="year", how="left")

    # Trailing-window features, indexed for lookup at panel year t
    # (values below describe years <= t-1 when merged on shifted year).
    full["sales_3y"] = (full.groupby("outcode", observed=True)["n_sales"]
                        .transform(lambda s: s.rolling(3, min_periods=1).sum()))
    full["turnover_3y"] = full["sales_3y"] / 3 / full["stock_seen"].clip(lower=1)
    full["price_rel_nat"] = full["med_price"] / full["nat_med"]
    med4 = full.groupby("outcode", observed=True)["med_price"].shift(3)
    full["price_growth_3y"] = np.log(full["med_price"] / med4)
    return full[["outcode", "year", "med_price", "turnover_3y",
                 "price_rel_nat", "price_growth_3y"]]


def build_panel(tx: pd.DataFrame, dy: pd.DataFrame, sample_pct: int):
    tx = tx.sort_values(["key", "year", "month"], ignore_index=True)
    tx["n_prior"] = tx.groupby("key", observed=True).cumcount()
    same_next = (tx["key"].shift(-1) == tx["key"]).to_numpy()
    next_year = tx["year"].shift(-1).to_numpy()

    spells = pd.DataFrame({
        "key": tx["key"], "buy_year": tx["year"].astype("int32"),
        "ptype": tx["ptype"], "leasehold": tx["leasehold"],
        "is_new": tx["is_new"], "price": tx["price"],
        "outcode": tx["outcode"], "n_prior": tx["n_prior"].astype("int16"),
        "sold": same_next,
        "end_year": np.where(same_next, next_year, END_YEAR).astype("int32"),
    })
    spells = spells[(np.abs(spells["key"]) % 100) < sample_pct]
    # Price relative to district median in purchase year.
    spells = spells.merge(
        dy[["outcode", "year", "med_price"]],
        left_on=["outcode", "buy_year"], right_on=["outcode", "year"],
        how="left").drop(columns="year")
    spells["log_price_rel"] = np.log(
        spells["price"] / spells["med_price"].clip(lower=1))
    spells.drop(columns=["med_price"], inplace=True)

    # Expand each spell into risk years buy_year+1 .. min(end_year, END_YEAR-?):
    start = spells["buy_year"].to_numpy() + 1
    stop = np.minimum(spells["end_year"].to_numpy(), END_YEAR)  # inclusive
    n_rows = np.maximum(stop - start + 1, 0)
    keep = n_rows > 0
    spells = spells[keep].reset_index(drop=True)
    start, stop, n_rows = start[keep], stop[keep], n_rows[keep]

    idx = np.repeat(np.arange(len(spells)), n_rows)
    offsets = np.arange(n_rows.sum()) - np.repeat(
        np.concatenate(([0], n_rows.cumsum()[:-1])), n_rows)
    panel = spells.iloc[idx].reset_index(drop=True)
    panel["year"] = (start[idx] + offsets).astype("int32")
    panel["label"] = (panel["sold"] & (panel["year"] == panel["end_year"])).astype(
        "int8")
    panel["tenure"] = (panel["year"] - panel["buy_year"]).astype("int16")

    # District context from year t-1 (shift merge year by +1).
    ctx = dy.copy()
    ctx["year"] = ctx["year"] + 1
    ctx = ctx.rename(columns={"med_price": "district_med_price"})
    panel = panel.merge(ctx, on=["outcode", "year"], how="left")
    return panel


FEATURES = ["tenure", "log_price_rel", "leasehold", "is_new", "n_prior",
            "turnover_3y", "price_rel_nat", "price_growth_3y",
            "ptype_D", "ptype_S", "ptype_T", "ptype_F"]


def featurise(panel: pd.DataFrame) -> pd.DataFrame:
    for pt in "DSTF":
        panel[f"ptype_{pt}"] = (panel["ptype"] == pt)
    return panel


def lift_at(y_true, score, frac):
    n = max(int(len(score) * frac), 1)
    top = np.argsort(-score)[:n]
    return float(y_true[top].mean() / y_true.mean())


def main(parquet_path: str, out_dir: str, sample_pct: int = 5) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tx = pd.read_parquet(parquet_path)
    print(f"transactions: {len(tx):,}", flush=True)

    dy = district_year_features(tx)
    panel = build_panel(tx, dy, sample_pct)
    panel = featurise(panel)
    print(f"panel rows: {len(panel):,}  base rate: {panel['label'].mean():.4f}",
          flush=True)

    tr = panel[panel["year"].between(*TRAIN_YEARS)]
    te = panel[panel["year"].between(*TEST_YEARS)]
    Xtr, ytr = tr[FEATURES].astype("float32"), tr["label"].to_numpy()
    Xte, yte = te[FEATURES].astype("float32"), te["label"].to_numpy()
    print(f"train: {len(tr):,} rows ({ytr.mean():.4f} base)  "
          f"test: {len(te):,} rows ({yte.mean():.4f} base)", flush=True)

    results = {
        "sample_pct": sample_pct,
        "panel_rows": int(len(panel)),
        "train_rows": int(len(tr)), "test_rows": int(len(te)),
        "train_years": TRAIN_YEARS, "test_years": TEST_YEARS,
        "base_rate_train": float(ytr.mean()), "base_rate_test": float(yte.mean()),
    }

    # Logistic baseline (linear signal only).
    logit = LogisticRegression(max_iter=1000)
    med = np.nanmedian(Xtr, axis=0)
    Xtr_f, Xte_f = np.nan_to_num(Xtr - med), np.nan_to_num(Xte - med)
    sd = Xtr_f.std(axis=0) + 1e-9
    logit.fit(Xtr_f / sd, ytr)
    p_log = logit.predict_proba(Xte_f / sd)[:, 1]
    results["logit_auc"] = float(roc_auc_score(yte, p_log))

    # Gradient boosting (handles NaN natively).
    gb = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.08, max_depth=None, max_leaf_nodes=63,
        min_samples_leaf=200, random_state=7)
    gb.fit(Xtr, ytr)
    p = gb.predict_proba(Xte)[:, 1]

    results["gb_auc"] = float(roc_auc_score(yte, p))
    results["gb_pr_auc"] = float(average_precision_score(yte, p))
    for f in (0.01, 0.05, 0.10, 0.20):
        results[f"gb_lift_top{int(f*100)}pct"] = lift_at(yte, p, f)
    # Share of all actual sales captured by contacting top X% of stock.
    order = np.argsort(-p)
    cum_sales = np.cumsum(yte[order]) / yte.sum()
    for f in (0.10, 0.20, 0.30):
        results[f"gb_sales_captured_top{int(f*100)}pct"] = float(
            cum_sales[int(len(p) * f) - 1])
    for y in range(TEST_YEARS[0], TEST_YEARS[1] + 1):
        m = te["year"].to_numpy() == y
        results[f"gb_auc_{y}"] = float(roc_auc_score(yte[m], p[m]))
    # Long-tenure sub-population (10+ years owned) — the hardest cohort.
    m10 = te["tenure"].to_numpy() >= 10
    results["gb_auc_tenure10plus"] = float(roc_auc_score(yte[m10], p[m10]))
    results["base_rate_tenure10plus"] = float(yte[m10].mean())
    results["gb_lift_top10pct_tenure10plus"] = lift_at(yte[m10], p[m10], 0.10)

    # Calibration by predicted-probability decile.
    dec = pd.qcut(p, 10, labels=False, duplicates="drop")
    cal = pd.DataFrame({"dec": dec, "p": p, "y": yte}).groupby("dec").agg(
        pred=("p", "mean"), actual=("y", "mean"))
    results["calibration"] = {
        str(i): {"pred": float(r.pred), "actual": float(r.actual)}
        for i, r in cal.iterrows()}

    # Permutation importance on a manageable subsample.
    sub = np.random.RandomState(0).choice(len(Xte), size=min(300_000, len(Xte)),
                                          replace=False)
    imp = permutation_importance(gb, Xte.iloc[sub], yte[sub], n_repeats=3,
                                 random_state=0, scoring="roc_auc")
    results["permutation_importance"] = {
        f: float(v) for f, v in
        sorted(zip(FEATURES, imp.importances_mean), key=lambda x: -x[1])}

    # --- Charts ----------------------------------------------------------
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    fracs = np.linspace(0.005, 1.0, 200)
    ax[0].plot(100 * fracs, [100 * cum_sales[int(len(p) * f) - 1] for f in fracs])
    ax[0].plot([0, 100], [0, 100], "--", color="grey", lw=1, label="random")
    ax[0].set_xlabel("% of owned stock contacted (ranked by model)")
    ax[0].set_ylabel("% of next-year sellers reached")
    ax[0].set_title(f"Gain curve, out-of-time {TEST_YEARS[0]}-{TEST_YEARS[1]}")
    ax[0].legend()
    ax[0].grid(alpha=0.3)
    ax[1].plot(100 * cal["pred"], 100 * cal["actual"], marker="o")
    lim = max(cal["actual"].max(), cal["pred"].max()) * 110
    ax[1].plot([0, lim], [0, lim], "--", color="grey", lw=1)
    ax[1].set_xlabel("Predicted sale probability (%)")
    ax[1].set_ylabel("Actual sale rate (%)")
    ax[1].set_title("Calibration by decile")
    ax[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "model_performance.png", dpi=140)
    plt.close(fig)

    with open(out / "model_results.json", "w") as fh:
        json.dump(results, fh, indent=2)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    pct = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    main(sys.argv[1], sys.argv[2], pct)
