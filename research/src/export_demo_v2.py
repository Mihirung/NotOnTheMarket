"""Export scored Exeter stock at postcode-sector level, with geography.

Version 2 of the prototype's data. Rather than pre-baked cohorts, this
emits one row per (postcode sector x property type x value band) with
the real model's propensity, the PoC offer, and the geographic
attributes a buyer actually chooses on: air quality, openness of
surroundings, distance to a GP, and approximate drive time to a town,
regional centre and major city.

That lets the prototype filter the way people really search — "clean
air, green surroundings, twenty minutes from a centre, under £450k" —
and count the matching latent supply live.

Drive time is approximated from straight-line distance at 50 km/h. It is
labelled as an approximation everywhere it appears; a production build
would call a routing engine for true isochrones.

Usage: python export_demo_v2.py <transactions.parquet> <geo.parquet> <out_json>
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

sys.path.insert(0, str(Path(__file__).parent))
from propensity_model import (FEATURES, build_panel,  # noqa: E402
                              district_year_features, featurise)
from export_demo_cohorts import (DEMO_OUTCODES, SCORE_YEAR,  # noqa: E402
                                 offer_model, open_spells, score_frame)

KMH = 50.0  # assumed average road speed for the drive-time approximation
BANDS = [(0, 250_000, "under250"), (250_000, 400_000, "250to400"),
         (400_000, 600_000, "400to600"), (600_000, np.inf, "over600")]


def band_of(v):
    for lo, hi, name in BANDS:
        if lo <= v < hi:
            return name
    return "over600"


def main(tx_path, geo_path, out_json):
    tx = pd.read_parquet(tx_path)
    geo = pd.read_parquet(geo_path)
    dy = district_year_features(tx)

    print("training national model (2001-2018)...", flush=True)
    panel = featurise(build_panel(tx, dy, 5))
    trn = panel[panel["year"].between(2001, 2018)]
    gb = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.08, max_leaf_nodes=63,
        min_samples_leaf=200, random_state=7)
    gb.fit(trn[FEATURES].astype("float32"), trn["label"].to_numpy())
    del panel, trn

    print("scoring Exeter stock...", flush=True)
    last = open_spells(tx)
    demo = last[last["outcode"].astype(str).isin(DEMO_OUTCODES)]
    f = score_frame(demo, tx, dy)
    f["p_sale"] = gb.predict_proba(f[FEATURES].astype("float32"))[:, 1]
    d = offer_model(f, dy)
    d["outcode"] = d["outcode"].astype(str)
    d["ptype"] = d["ptype"].astype(str)
    d["postcode"] = d["postcode"].astype(str)

    # Attach geography, then reduce to sector level.
    gcols = ["postcode", "nox", "pm10", "pc_within_1km", "km_gp", "km_hospital",
             "km_town", "km_regional", "km_major", "lat", "lon"]
    d = d.merge(geo[gcols], on="postcode", how="left")
    matched = d["nox"].notna().mean()
    print(f"  geo match {matched:.1%} of {len(d):,} properties", flush=True)
    d = d[d["nox"].notna()].copy()

    d["sector"] = d["postcode"].str.rsplit(" ", n=1).str[0] + " " + \
        d["postcode"].str.rsplit(" ", n=1).str[1].str[0]
    d["band"] = d["est_value"].apply(band_of)
    top_cut = float(d["p_sale"].quantile(0.80))

    # National reference points so the prototype can express air quality
    # and openness as percentiles a person can reason about.
    nox_ref = geo["nox"].quantile([.1, .25, .5, .75, .9]).round(2).to_dict()
    dens_ref = geo["pc_within_1km"].quantile([.1, .25, .5, .75, .9]).round(0).to_dict()

    rows = []
    for (sec, pt, band), g in d.groupby(["sector", "ptype", "band"], observed=True):
        if len(g) < 12:
            continue
        rows.append({
            "sector": sec, "outcode": sec.split(" ")[0], "ptype": pt, "band": band,
            "n": int(len(g)),
            "n_top": int((g["p_sale"] >= top_cut).sum()),
            "exp_sellers": round(float(g["p_sale"].sum()), 2),
            "p_med": round(float(g["p_sale"].median()), 4),
            "value_med": int(g["est_value"].median() // 1000 * 1000),
            "offer_med": int(g["offer_mid"].median() // 1000 * 1000),
            "premium_med": round(float(g["premium"].median()), 3),
            "tenure_med": float(g["tenure"].median()),
            # geography (sector medians)
            "nox": round(float(g["nox"].median()), 1),
            "density": int(g["pc_within_1km"].median()),
            "km_gp": round(float(g["km_gp"].median()), 2),
            "min_town": int(round(g["km_town"].median() / KMH * 60)),
            "min_regional": int(round(g["km_regional"].median() / KMH * 60)),
            "min_major": int(round(g["km_major"].median() / KMH * 60)),
            "lat": round(float(g["lat"].median()), 4),
            "lon": round(float(g["lon"].median()), 4),
        })

    # Exemplars for the seller flow: highest-propensity homes, fictionalised.
    rng = np.random.RandomState(42)
    ex_pool = d[(d["p_sale"] >= top_cut) & d["ptype"].isin(["S", "T", "D"])
                & d["est_value"].between(240_000, 650_000)].nlargest(400, "p_sale")
    exemplars, seen = [], set()
    for _, r in ex_pool.iterrows():
        if r["sector"] in seen or len(exemplars) >= 3:
            continue
        seen.add(r["sector"])
        exemplars.append({
            "code": f"{r['outcode']}-{rng.randint(0x1000, 0xFFFF):04X}",
            "sector": r["sector"], "ptype": r["ptype"],
            "tenure": int(r["tenure"]), "p_sale": round(float(r["p_sale"]), 3),
            "est_value": int(round(r["est_value"], -4)),
            "offer_lo": int(round(r["offer_mid"] * 0.96, -3)),
            "offer_mid": int(round(r["offer_mid"], -3)),
            "offer_hi": int(round(r["offer_mid"] * 1.04, -3)),
            "premium_pct": round(float(r["premium"]) * 100, 1),
            "nox": round(float(r["nox"]), 1),
            "min_regional": int(round(r["km_regional"] / KMH * 60)),
        })

    out = {
        "area": {
            "name": "Exeter", "n_owned_tracked": int(len(d)),
            "exp_sellers_12m": round(float(d["p_sale"].sum())),
            "top_band_cut": round(top_cut, 4),
            "p_sale_mean": round(float(d["p_sale"].mean()), 4),
            "nox_national": {str(k): v for k, v in nox_ref.items()},
            "density_national": {str(k): v for k, v in dens_ref.items()},
            "model": {"auc_oot": 0.588, "lift_top10": 1.59,
                      "trained_on": "HM Land Registry Price Paid Data "
                                    "1995-2019, 24.3M transactions"},
            "geo_sources": "AHAH v4 air quality & health POIs; ONS postcode "
                           "centroids via Geovation; drive time approximated "
                           f"from straight-line distance at {KMH:.0f} km/h",
        },
        "cells": rows,
        "exemplars": exemplars,
    }
    with open(out_json, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"{len(rows)} sector cells, {len(exemplars)} exemplars -> {out_json}")
    print(f"  NOx range across cells: "
          f"{min(r['nox'] for r in rows)}-{max(r['nox'] for r in rows)}")
    print(f"  drive to regional centre: "
          f"{min(r['min_regional'] for r in rows)}-"
          f"{max(r['min_regional'] for r in rows)} min")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
