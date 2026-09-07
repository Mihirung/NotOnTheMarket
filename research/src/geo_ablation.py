"""Does open geographic data improve sale-propensity targeting?

Ablation over three feature sets, all evaluated identically and strictly
out-of-time (train 2001-2015, test 2017-2019):

  BASE      transaction history + local market only (the published model)
  +GEO      adds real AHAH inputs — air quality (NOx/PM10/SO2), distance
            to nearest GP / hospital / dentist / pharmacy — plus built
            density and distance to the nearest town, regional centre and city
  +LIFE     adds life-stage proxies inferred from what the owner bought:
            starter / family / premium purchase bands, tenure in excess
            of the norm for that property type, and the "environment
            mismatch" terms (a family-stage household in dense, poor-air
            surroundings is a downsizing/moving-out candidate)

Reports AUC, lift and gain, and — the number that actually decides the
business — expected postcards per owner conversation.

Caveat carried into the write-up: AHAH air quality and POI locations are
current-vintage applied to a 2001-2019 panel. Geography is persistent, so
this is acceptable for a feasibility read, but a production model should
use vintage-matched environmental data.

Usage: python geo_ablation.py <transactions.parquet> <geo.parquet> <out_dir> [pct]
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
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).parent))
from propensity_model import (FEATURES as BASE_FEATURES, TEST_YEARS,  # noqa: E402
                              TRAIN_YEARS, build_panel, district_year_features,
                              featurise, lift_at)

GEO_FEATURES = ["nox", "pm10", "so2", "km_gp", "km_hospital", "km_dentist",
                "km_pharmacy", "pc_within_1km", "pc_within_5km",
                "km_town", "km_regional", "km_major"]
LIFE_FEATURES = ["ls_band", "excess_tenure", "mismatch_family_urban",
                 "mismatch_starter_remote", "aq_rel_region"]

# Response assumptions for the economics translation (stated, not measured).
BASE_SCAN = 0.024       # share of mailed owners who open their offer page
TALK_GIVEN_SCAN = 0.33  # share of scanners who start a conversation
CARD_COST = 0.72        # £ print + post at volume


def attach_geo(panel: pd.DataFrame, geo: pd.DataFrame,
               categories) -> pd.DataFrame:
    """Join geography by the panel's postcode *code*.

    build_panel carries postcodes as categorical codes, not strings.
    Reindexing the geo table onto the same category order lets us attach
    features by array lookup — far cheaper than a 10M-row string join.
    """
    aligned = geo.set_index("postcode").reindex(pd.Index(categories))
    code = panel["pc_code"].to_numpy()
    valid = code >= 0
    for c in (c for c in GEO_FEATURES if c in aligned.columns):
        vals = aligned[c].to_numpy(dtype="float32")
        out = np.full(len(panel), np.nan, dtype="float32")
        out[valid] = vals[code[valid]]
        panel[c] = out
    # Air quality relative to the surrounding region: people react to how
    # their air compares with the alternatives nearby, not to absolutes.
    reg = panel.groupby("outcode", observed=True)["nox"].transform("median")
    panel["aq_rel_region"] = panel["nox"] - reg
    return panel


def add_life_stage(panel: pd.DataFrame) -> pd.DataFrame:
    """Life-stage proxies inferred from the property the owner bought."""
    # Purchase price percentile within its own district-year market.
    pct = panel.groupby(["outcode", "buy_year"], observed=True)["price"].rank(pct=True)
    flatish = panel["ptype"].isin(["F", "T"]).to_numpy()
    houseish = panel["ptype"].isin(["S", "D"]).to_numpy()
    starter = (flatish & (pct < 0.4).to_numpy())
    family = (houseish & pct.between(0.4, 0.9).to_numpy())
    premium = (pct >= 0.9).to_numpy()
    panel["ls_band"] = np.select([starter, family, premium], [1, 2, 3], default=0
                                 ).astype("int8")

    # How far past the typical holding period for this property type.
    norm = panel.groupby("ptype", observed=True)["tenure"].transform("median")
    panel["excess_tenure"] = (panel["tenure"] - norm).astype("float32")

    # Environment mismatch: the hypothesised push factors.
    dens = panel["pc_within_1km"].fillna(panel["pc_within_1km"].median())
    dens_r = dens.rank(pct=True)
    aq_r = panel["nox"].rank(pct=True)
    panel["mismatch_family_urban"] = (family * (dens_r * 0.5 + aq_r * 0.5)
                                      ).astype("float32")
    panel["mismatch_starter_remote"] = (starter * panel["km_major"].fillna(0)
                                        ).astype("float32")
    return panel


def evaluate(name, feats, tr, te, results, curves):
    Xtr, ytr = tr[feats].astype("float32"), tr["label"].to_numpy()
    Xte, yte = te[feats].astype("float32"), te["label"].to_numpy()
    gb = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.08, max_leaf_nodes=63,
        min_samples_leaf=200, random_state=7)
    gb.fit(Xtr, ytr)
    p = gb.predict_proba(Xte)[:, 1]

    r = {"n_features": len(feats), "auc": float(roc_auc_score(yte, p))}
    for f in (0.01, 0.05, 0.10, 0.20):
        r[f"lift_top{int(f*100)}"] = lift_at(yte, p, f)
    order = np.argsort(-p)
    cum = np.cumsum(yte[order]) / yte.sum()
    r["captured_top10"] = float(cum[int(len(p) * 0.10) - 1])
    r["captured_top20"] = float(cum[int(len(p) * 0.20) - 1])

    m10 = te["tenure"].to_numpy() >= 10
    r["auc_tenure10plus"] = float(roc_auc_score(yte[m10], p[m10]))
    r["lift_top10_tenure10plus"] = lift_at(yte[m10], p[m10], 0.10)
    m20 = te["tenure"].to_numpy() >= 20
    if yte[m20].sum() > 50:
        r["auc_tenure20plus"] = float(roc_auc_score(yte[m20], p[m20]))
        r["lift_top10_tenure20plus"] = lift_at(yte[m20], p[m20], 0.10)

    # Economics: mailing the top decile, what does a conversation cost?
    scan = BASE_SCAN * r["lift_top10"]
    talks_per_1000 = 1000 * scan * TALK_GIVEN_SCAN
    r["scan_rate_top10_pct"] = round(100 * scan, 2)
    r["talks_per_1000_cards"] = round(talks_per_1000, 1)
    r["cost_per_conversation"] = round(1000 * CARD_COST / max(talks_per_1000, 1e-9))

    imp = sorted(zip(feats, gb.feature_importances_ if hasattr(gb, "feature_importances_")
                     else [0] * len(feats)), key=lambda x: -x[1])[:8] \
        if hasattr(gb, "feature_importances_") else []
    if imp:
        r["top_features"] = {k: round(float(v), 4) for k, v in imp}
    results[name] = r
    curves[name] = cum
    print(f"{name:8s} AUC {r['auc']:.4f}  lift@1% {r['lift_top1']:.2f}  "
          f"lift@10% {r['lift_top10']:.2f}  tenure10+ AUC {r['auc_tenure10plus']:.4f}  "
          f"£/conversation {r['cost_per_conversation']}", flush=True)
    return p


def main(tx_path, geo_path, out_dir, pct=5):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    tx = pd.read_parquet(tx_path)
    geo = pd.read_parquet(geo_path)
    print(f"transactions {len(tx):,} · geo postcodes {len(geo):,}", flush=True)

    dy = district_year_features(tx)
    categories = tx["postcode"].cat.categories
    panel = featurise(build_panel(tx, dy, pct))
    panel = attach_geo(panel, geo, categories)
    matched = panel["nox"].notna().mean()
    print(f"panel {len(panel):,} rows · geo match {matched:.1%}", flush=True)
    panel = add_life_stage(panel)

    tr = panel[panel["year"].between(*TRAIN_YEARS)]
    te = panel[panel["year"].between(*TEST_YEARS)]
    print(f"train {len(tr):,} · test {len(te):,} · base rate {te['label'].mean():.4f}",
          flush=True)

    results, curves = {}, {}
    results["_meta"] = {
        "panel_rows": int(len(panel)), "geo_match_rate": round(float(matched), 4),
        "train_years": TRAIN_YEARS, "test_years": TEST_YEARS,
        "test_base_rate": float(te["label"].mean()),
        "assumptions": {"base_scan_rate": BASE_SCAN,
                        "talk_given_scan": TALK_GIVEN_SCAN,
                        "card_cost_gbp": CARD_COST},
    }
    evaluate("BASE", BASE_FEATURES, tr, te, results, curves)
    geo_ok = [f for f in GEO_FEATURES if f in panel.columns]
    evaluate("+GEO", BASE_FEATURES + geo_ok, tr, te, results, curves)
    evaluate("+LIFE", BASE_FEATURES + geo_ok + LIFE_FEATURES, tr, te, results, curves)

    # Chart: gain curves at the sharp end, where mailing actually happens.
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    colours = {"BASE": "#8C8C8C", "+GEO": "#4E9484", "+LIFE": "#275E54"}
    fr = np.linspace(0.002, 0.30, 200)
    for k, cum in curves.items():
        ax[0].plot(100 * fr, [100 * cum[max(int(len(cum) * f) - 1, 0)] for f in fr],
                   color=colours[k], lw=2, label=k)
    ax[0].plot([0, 30], [0, 30], "--", color="#B0B0B0", lw=1.5, label="random")
    ax[0].set_xlabel("% of owned stock mailed (best first)")
    ax[0].set_ylabel("% of next-year sellers reached")
    ax[0].set_title("Where the postcards go: top 30%")
    ax[0].legend(frameon=False); ax[0].grid(alpha=.25)

    names = ["BASE", "+GEO", "+LIFE"]
    xs = np.arange(len(names)); w = 0.35
    ax[1].bar(xs - w/2, [results[n]["lift_top1"] for n in names], w,
              color="#275E54", label="top 1%")
    ax[1].bar(xs + w/2, [results[n]["lift_top10"] for n in names], w,
              color="#8FC3B6", label="top 10%")
    for i, n in enumerate(names):
        ax[1].text(i - w/2, results[n]["lift_top1"] + .02,
                   f'{results[n]["lift_top1"]:.2f}', ha="center", fontsize=9)
        ax[1].text(i + w/2, results[n]["lift_top10"] + .02,
                   f'{results[n]["lift_top10"]:.2f}', ha="center", fontsize=9)
    ax[1].axhline(1.0, color="#B0B0B0", ls="--", lw=1.5)
    ax[1].set_xticks(xs); ax[1].set_xticklabels(names)
    ax[1].set_ylabel("Lift over random mailing")
    ax[1].set_title("Targeting efficiency by feature set")
    ax[1].legend(frameon=False); ax[1].grid(alpha=.25, axis="y")
    fig.tight_layout(); fig.savefig(out / "geo_ablation.png", dpi=140)
    plt.close(fig)

    with open(out / "geo_ablation.json", "w") as fh:
        json.dump(results, fh, indent=1)
    print("\n" + json.dumps(results, indent=1)[:2500])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3],
         int(sys.argv[4]) if len(sys.argv) > 4 else 5)
