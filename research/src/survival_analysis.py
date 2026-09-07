"""Descriptive survival analysis of UK property holding periods.

Questions this answers, from 25 years of real Land Registry data:
 1. How long do owners hold properties before selling (Kaplan-Meier)?
 2. What is the discrete-time hazard of a sale at each year of tenure —
    and does it behave differently by property type and price band?
 3. What share of each year's sales come from owners we have never seen
    buy (pre-1995 purchasers — the long-tenure / lifecycle cohort)?

Usage: python survival_analysis.py <transactions.parquet> <out_dir>
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

END_YEAR = 2019  # last complete year in the dataset


def build_spells(tx: pd.DataFrame) -> pd.DataFrame:
    """One row per ownership spell: purchase year -> next sale year (or censored)."""
    tx = tx.sort_values(["key", "year", "month"], ignore_index=True)
    same_next = tx["key"].shift(-1) == tx["key"]
    next_year = tx["year"].shift(-1)
    spells = pd.DataFrame({
        "key": tx["key"],
        "buy_year": tx["year"],
        "ptype": tx["ptype"],
        "leasehold": tx["leasehold"],
        "is_new": tx["is_new"],
        "price": tx["price"],
        "outcode": tx["outcode"],
        "sold": same_next.to_numpy(),
        "end_year": np.where(same_next, next_year, END_YEAR).astype("int32"),
    })
    spells["tenure"] = (spells["end_year"] - spells["buy_year"]).astype("int32")
    # Drop same-year flips (tenure 0) from tenure analysis but count them.
    return spells


def discrete_hazard(spells: pd.DataFrame, max_t: int = 24):
    """Empirical hazard h(t) = P(sell in tenure-year t | still owned at t)."""
    at_risk, events = [], []
    for t in range(1, max_t + 1):
        risk = ((spells["tenure"] >= t)
                # spell must be old enough for tenure t to be observable
                & (spells["buy_year"] + t <= END_YEAR)).sum()
        ev = ((spells["tenure"] == t) & spells["sold"]).sum()
        at_risk.append(int(risk))
        events.append(int(ev))
    h = np.array(events) / np.maximum(np.array(at_risk), 1)
    return h, np.array(at_risk), np.array(events)


def main(parquet_path: str, out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tx = pd.read_parquet(parquet_path)
    results = {}

    # --- Volume + linkage overview -------------------------------------
    n_tx = len(tx)
    n_props = tx["key"].nunique()
    sales_per_prop = tx.groupby("key").size()
    results["n_transactions"] = int(n_tx)
    results["n_unique_properties"] = int(n_props)
    results["sales_per_property"] = {
        str(k): int(v) for k, v in
        sales_per_prop.value_counts().sort_index().head(8).items()
    }

    # --- First-appearance share: sales by never-seen-buying owners ------
    first_year = tx.groupby("key")["year"].min()
    tx = tx.merge(first_year.rename("first_year"), on="key")
    fa = {}
    for y in range(2000, END_YEAR + 1):
        yr = tx[tx["year"] == y]
        fa[y] = float((yr["first_year"] == y).mean())
    results["first_appearance_share_by_year"] = fa

    # --- Ownership spells ----------------------------------------------
    spells = build_spells(tx)
    obs = spells[spells["tenure"] >= 1]  # exclude same-year flips
    results["n_spells"] = int(len(spells))
    results["n_completed_spells"] = int(spells["sold"].sum())
    comp = spells[spells["sold"] & (spells["tenure"] >= 1)]
    results["median_completed_tenure_years"] = float(comp["tenure"].median())
    results["mean_completed_tenure_years"] = float(comp["tenure"].mean())

    # --- Hazard by tenure year ------------------------------------------
    h, risk, ev = discrete_hazard(obs)
    results["hazard_by_tenure"] = {str(t + 1): float(x) for t, x in enumerate(h)}
    surv = np.cumprod(1 - h)  # KM-style survival from the hazard

    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    t = np.arange(1, len(h) + 1)
    ax[0].plot(t, 100 * h, marker="o", ms=3)
    ax[0].set_xlabel("Years since purchase")
    ax[0].set_ylabel("Annual probability of sale (%)")
    ax[0].set_title("Sale hazard by tenure (E&W, 1995-2019)")
    ax[0].grid(alpha=0.3)
    ax[1].plot(t, 100 * surv)
    ax[1].set_xlabel("Years since purchase")
    ax[1].set_ylabel("Still owned (%)")
    ax[1].set_title("Ownership survival curve")
    ax[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "hazard_survival.png", dpi=140)
    plt.close(fig)

    # --- Hazard heterogeneity: property type and price quartile ---------
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for pt, label in [("D", "Detached"), ("S", "Semi"), ("T", "Terraced"),
                      ("F", "Flat")]:
        hh, _, _ = discrete_hazard(obs[obs["ptype"] == pt])
        ax[0].plot(np.arange(1, len(hh) + 1), 100 * hh, label=label)
        results[f"hazard_ptype_{pt}"] = [float(x) for x in hh]
    ax[0].legend()
    ax[0].set_title("Hazard by property type")
    ax[0].set_xlabel("Years since purchase")
    ax[0].set_ylabel("Annual sale probability (%)")
    ax[0].grid(alpha=0.3)

    # price quartile within purchase year (national)
    obs = obs.copy()
    obs["pq"] = obs.groupby("buy_year")["price"].transform(
        lambda s: pd.qcut(s, 4, labels=False, duplicates="drop"))
    for q, label in [(0, "Q1 cheapest"), (1, "Q2"), (2, "Q3"), (3, "Q4 dearest")]:
        hh, _, _ = discrete_hazard(obs[obs["pq"] == q])
        ax[1].plot(np.arange(1, len(hh) + 1), 100 * hh, label=label)
    ax[1].legend()
    ax[1].set_title("Hazard by purchase-price quartile")
    ax[1].set_xlabel("Years since purchase")
    ax[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "hazard_heterogeneity.png", dpi=140)
    plt.close(fig)

    # --- Local turnover dispersion: do districts differ enough to target?
    d = tx[tx["year"].between(2014, 2018)].groupby("outcode", observed=True).size()
    stock = tx.groupby("outcode", observed=True)["key"].nunique()
    tor = (d / 5 / stock).dropna()
    tor = tor[stock >= 500]
    results["district_turnover_pct"] = {
        "p10": float(tor.quantile(0.10)), "p50": float(tor.quantile(0.50)),
        "p90": float(tor.quantile(0.90)), "n_districts": int(len(tor)),
    }

    with open(out / "survival_results.json", "w") as fh:
        json.dump(results, fh, indent=2)
    print(json.dumps(results, indent=2)[:3000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
