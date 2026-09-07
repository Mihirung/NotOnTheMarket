"""Export real model output for the website prototype.

Trains the sale-propensity model (same construction as
propensity_model.py, all years), then scores every *currently owned*
property in the demo area (Exeter: EX1-EX4) for sale in the next 12
months, attaches a PoC "what they'd sell at" offer model, and writes
cohort-level JSON for the prototype site plus a handful of
fictionalised exemplar properties for the seller flow.

PoC offer model (documented assumption, to be replaced by learned
acceptance curves in operation):
  est_value  = last price uprated by the outcode median price index
               (outcode x property-type where thick enough)
  premium    = 6% base
               + up to 12% the *less* likely the owner is to sell
                 (low propensity = more inertia to overcome)
               + 0.4% per year of tenure, capped at 25 years
               (endowment/anchoring grows with time in the home)
  offer mid  = est_value * (1 + premium), range +/-4%

Privacy: no real addresses are exported. Buyers see cohorts only;
exemplar "seller" records use real streets with fictional house
numbers and rounded values.

Usage: python export_demo_cohorts.py <transactions.parquet> <out_json>
"""

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from propensity_model import (END_YEAR, FEATURES, build_panel,  # noqa: E402
                              district_year_features, featurise)
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402

DEMO_OUTCODES = ["EX1", "EX2", "EX3", "EX4"]
SCORE_YEAR = END_YEAR + 1  # features through end-2019, predict next 12 months


def open_spells(tx: pd.DataFrame) -> pd.DataFrame:
    """Last transaction per property = current ownership spell."""
    tx = tx.sort_values(["key", "year", "month"], ignore_index=True)
    tx["n_prior"] = tx.groupby("key", observed=True).cumcount()
    last = tx.groupby("key", observed=True).tail(1).copy()
    return last


def score_frame(last: pd.DataFrame, tx: pd.DataFrame, dy: pd.DataFrame):
    """Feature rows for score year for the given open spells."""
    f = (last[["key", "year", "ptype", "leasehold", "is_new", "price",
               "outcode", "postcode", "n_prior"]]
         .reset_index(drop=True).rename(columns={"year": "buy_year"}))
    f["buy_year"] = f["buy_year"].astype("int32")
    f["n_prior"] = f["n_prior"].astype("int16")
    f["tenure"] = SCORE_YEAR - f["buy_year"]
    f = f[f["tenure"] >= 1].copy()

    med = dy[["outcode", "year", "med_price"]]
    f = f.merge(med, left_on=["outcode", "buy_year"], right_on=["outcode", "year"],
                how="left").drop(columns="year")
    f["log_price_rel"] = np.log(f["price"] / f["med_price"].clip(lower=1))
    f.drop(columns=["med_price"], inplace=True)

    ctx = dy[dy["year"] == END_YEAR].drop(columns="year")
    ctx = ctx.rename(columns={"med_price": "district_med_price"})
    f = f.merge(ctx, on="outcode", how="left")

    pcy = (tx.assign(pc_code=tx["postcode"].cat.codes.astype("int32"))
           .groupby(["pc_code", "year"], observed=True).size().rename("s")
           .reset_index())
    f["pc_code"] = f["postcode"].cat.codes.astype("int32")
    for yr, col in ((END_YEAR, "s_l1"), (END_YEAR - 1, "s_l2")):
        m = pcy[pcy["year"] == yr][["pc_code", "s"]].rename(columns={"s": col})
        f = f.merge(m, on="pc_code", how="left")
    own = f["buy_year"].isin([END_YEAR, END_YEAR - 1]).astype("int16")
    f["pc_sales_2y"] = (f["s_l1"].fillna(0) + f["s_l2"].fillna(0) - own).clip(
        lower=0).astype("int16")
    return featurise(f)


def offer_model(d: pd.DataFrame, dy: pd.DataFrame) -> pd.DataFrame:
    """PoC estimated value + offer-to-unlock, per property."""
    idx19 = dy[dy["year"] == END_YEAR][["outcode", "med_price"]].rename(
        columns={"med_price": "med19"})
    idx_buy = dy[["outcode", "year", "med_price"]].rename(
        columns={"med_price": "med_buy", "year": "buy_year"})
    d = d.merge(idx19, on="outcode", how="left")
    d = d.merge(idx_buy, on=["outcode", "buy_year"], how="left")
    d["est_value"] = (d["price"] * (d["med19"] / d["med_buy"].clip(lower=1))
                      ).clip(30_000, 5_000_000)
    pctile = d["p_sale"].rank(pct=True)
    d["premium"] = (0.06 + 0.12 * (1 - pctile)
                    + 0.004 * d["tenure"].clip(upper=25))
    d["offer_mid"] = d["est_value"] * (1 + d["premium"])
    return d


def main(parquet_path: str, out_json: str) -> None:
    tx = pd.read_parquet(parquet_path)
    dy = district_year_features(tx)

    print("training on national 5% panel, 2001-2018...", flush=True)
    panel = featurise(build_panel(tx, dy, 5))
    trn = panel[panel["year"].between(2001, 2018)]
    gb = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.08, max_leaf_nodes=63,
        min_samples_leaf=200, random_state=7)
    gb.fit(trn[FEATURES].astype("float32"), trn["label"].to_numpy())

    print("scoring open spells in demo area...", flush=True)
    last = open_spells(tx)
    demo = last[last["outcode"].astype(str).isin(DEMO_OUTCODES)]
    f = score_frame(demo, tx, dy)
    f["p_sale"] = gb.predict_proba(f[FEATURES].astype("float32"))[:, 1]
    d = offer_model(f, dy)
    d["outcode"] = d["outcode"].astype(str)
    d["ptype"] = d["ptype"].astype(str)

    band_edges = [0, 250_000, 400_000, 600_000, np.inf]
    band_names = ["under250", "250to400", "400to600", "over600"]
    d["band"] = pd.cut(d["est_value"], band_edges, labels=band_names)
    top_cut = d["p_sale"].quantile(0.8)

    cohorts = []
    for (oc, pt, band), g in d.groupby(["outcode", "ptype", "band"],
                                       observed=True):
        if len(g) < 30:
            continue
        cohorts.append({
            "outcode": oc, "ptype": pt, "band": str(band),
            "n": int(len(g)),
            "n_top": int((g["p_sale"] >= top_cut).sum()),
            "exp_sellers_12m": round(float(g["p_sale"].sum()), 1),
            "p_median": round(float(g["p_sale"].median()), 4),
            "p_top_decile": round(float(g["p_sale"].quantile(0.9)), 4),
            "est_value_med": int(g["est_value"].median() // 1000 * 1000),
            "offer_mid_med": int(g["offer_mid"].median() // 1000 * 1000),
            "premium_med": round(float(g["premium"].median()), 3),
            "tenure_med": float(g["tenure"].median()),
            "leasehold_share": round(float(g["leasehold"].mean()), 2),
        })

    area = {
        "n_owned_tracked": int(len(d)),
        "exp_sellers_12m": round(float(d["p_sale"].sum())),
        "top_band_cut": round(float(top_cut), 4),
        "p_sale_mean": round(float(d["p_sale"].mean()), 4),
        "by_outcode": {
            oc: {"n": int(len(g)),
                 "exp_sellers_12m": round(float(g["p_sale"].sum())),
                 "est_value_med": int(g["est_value"].median() // 1000 * 1000)}
            for oc, g in d.groupby("outcode", observed=True)},
        "model": {"auc_oot": 0.588, "lift_top1pct": 1.89,
                  "trained_on": "HM Land Registry Price Paid Data 1995-2019, "
                                "England & Wales, 24.3M transactions"},
    }

    # Fictionalised exemplars for the seller flow: real streets and real
    # cohort statistics, fictional house numbers, rounded figures.
    rng = np.random.RandomState(42)
    ex = d[(d["p_sale"] >= top_cut) & (d["ptype"].isin(["S", "T", "D"]))
           & d["est_value"].between(240_000, 650_000)].nlargest(400, "p_sale")
    exemplars = []
    seen_streets = set()
    for _, r in ex.iterrows():
        pc = str(r["postcode"])
        sector = pc.rsplit(" ", 1)[0] + " " + pc.rsplit(" ", 1)[1][0]
        if sector in seen_streets or len(exemplars) >= 3:
            continue
        seen_streets.add(sector)
        exemplars.append({
            "code": f"{r['outcode']}-{rng.randint(0x1000, 0xFFFF):04X}",
            "sector": sector,
            "ptype": r["ptype"],
            "tenure": int(r["tenure"]),
            "p_sale": round(float(r["p_sale"]), 3),
            "est_value": int(round(r["est_value"], -4)),
            "offer_lo": int(round(r["offer_mid"] * 0.96, -3)),
            "offer_mid": int(round(r["offer_mid"], -3)),
            "offer_hi": int(round(r["offer_mid"] * 1.04, -3)),
            "premium_pct": round(float(r["premium"]) * 100, 1),
            "pc_sales_2y": int(r["pc_sales_2y"]),
        })

    out = {"area": area, "cohorts": cohorts, "exemplars": exemplars,
           "generated": "propensity + PoC offer model, features to end-2019"}
    with open(out_json, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"{len(d):,} properties scored; {len(cohorts)} cohorts; "
          f"exemplars: {[e['code'] for e in exemplars]}")
    print(json.dumps(area, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
