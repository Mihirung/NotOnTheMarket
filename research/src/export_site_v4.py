"""Prototype data, version 4: two cities, house-level views, national model v2.

Two stages, so the heavy national tables are only built once:

  score   build the national panel, score every currently owned home in
          each city for a sale in the next 12 months with the deployed
          model, and cache one small table per city
  export  join geography and house-level outlooks, reduce to cells
          (postcode sector x property type x value band), attach the
          drawn panoramas, and write the JSON the site inlines

How views reach a cell. Sale records and address points share no address
key in open data, so they meet at the postcode: each owned home takes its
postcode's house-level distribution of view combinations (which share of
its address points can see the cathedral AND have evening sun, and so
on). A cell therefore carries a small histogram over combinations of
view flags, and the site can count homes matching any set of flags
jointly rather than multiplying averages.

Privacy: no address, postcode or coordinate of an individual home is
exported. Panoramas are drawn from unnamed positions inside a sector.

Usage:
  python export_site_v4.py score  <transactions.parquet> <geo.parquet> <view30.parquet> <model.txt> <cache_dir>
  python export_site_v4.py export <cache_dir> <geo.parquet> <views2_dir> <lab_dir> <out_json>
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

SCORE_YEAR = 2020
KMH_URBAN = 30.0
BANDS = [(0, 250_000, "under250"), (250_000, 400_000, "250to400"),
         (400_000, 600_000, "400to600"), (600_000, np.inf, "over600")]
CITIES = {
    "exeter": dict(
        name="Exeter", outcodes=["EX1", "EX2", "EX3", "EX4"], centre=(50.7236, -3.5275), lon=-3.53,
        centre_name="the Cathedral", frank="EX",
        areas={"EX1": "City centre & St James", "EX2": "St Leonard's & Alphington",
               "EX3": "Topsham & Countess Wear", "EX4": "St David's, Pennsylvania & Whipton"},
        water="The Exe, the canal, the estuary or the sea somewhere in the upstairs view.",
        hills="Haldon, Dartmoor or Woodbury Common on the skyline.",
        lm_label={"Exeter Cathedral": "Can see the cathedral", "Haldon Belvedere": "Can see Haldon Belvedere",
                  "Woodbury Common": "Can see Woodbury Common", "Haytor, Dartmoor": "Can see Dartmoor (Haytor)"}),
    "bath": dict(
        name="Bath", outcodes=["BA1", "BA2"], centre=(51.3811, -2.3590), lon=-2.36,
        centre_name="the Abbey", frank="BA",
        areas={"BA1": "City centre, Lansdown, Weston & Larkhall",
               "BA2": "Bathwick, Widcombe, Combe Down & Odd Down"},
        water="The Avon or the canal somewhere in the upstairs view.",
        hills="The Cotswold edge, Lansdown or the Mendips on the skyline.",
        lm_label={"Bath Abbey": "Can see the Abbey", "Royal Crescent": "Can see the Royal Crescent",
                  "Beckford's Tower": "Can see Beckford's Tower", "Sham Castle": "Can see Sham Castle",
                  "Solsbury Hill": "Can see Solsbury Hill", "Kelston Round Hill": "Can see Kelston Round Hill"}),
}
GENERIC = [("long", "Long views", "Can see 2 km or more from an upstairs window, across a good part of the horizon."),
           ("water", "Water in view", None),
           ("hills", "Hills on the horizon", None),
           ("private", "Not overlooked", "Neighbouring buildings look into the garden from fewer than half the directions around it."),
           ("evening", "Evening sun in the garden", "Two hours or more of direct sun in the garden after 6pm in June, allowing for every roof, tree and hill."),
           ("swgarden", "South or west-facing garden", "The garden lies to the south or west of the house.")]
# Light indoors: direct sun on the downstairs windows, from light.py.
LIGHT = [("lightback", "Sunny back rooms", "Five hours or more of direct sun a day on the downstairs back windows, averaged over the year.",
          lambda L: L.light_back >= 5.0),
         ("lightfront", "Sunny front rooms", "Five hours or more of direct sun a day on the downstairs front windows, averaged over the year.",
          lambda L: L.light_front >= 5.0),
         ("wintersun", "Winter sun indoors", "Two hours or more of direct sun on the downstairs windows, front or back, on the shortest day.",
          lambda L: np.maximum(L.winter_front, L.winter_back) >= 2.0)]

# 87 characters that are safe inside JSON inside a <script> block.
ALPH = ("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        "!#$%()*+,-./:;=?@[]^_{|}~")
A_LO, A_SPAN = -np.sqrt(8.0), np.sqrt(8.0) + np.sqrt(50.0)


def enc_angles(a10):
    """Angles (tenths of a degree) -> one character each on a square-root scale,
    fine near the horizon where distant hills live, coarse high up."""
    a = np.clip(np.asarray(a10, dtype="float64") / 10.0, -8, 50)
    v = np.sign(a) * np.sqrt(np.abs(a))
    i = np.round((v - A_LO) / A_SPAN * (len(ALPH) - 1)).astype(int)
    return "".join(ALPH[k] for k in i)


def enc_pano(p):
    lo = [w[0] if w else None for w in p["water"]]
    hi = [w[1] if w else None for w in p["water"]]
    wat = lambda v: "".join(" " if x is None else enc_angles([x]) for x in v)
    return {"step": p["step"], "edges": p["edges"],
            "a": [enc_angles(b) for b in p["bands"]],
            "c": ["".join(str(int(x)) for x in c) for c in p["cls"][:4]],     # far bands are drawn as country
            "wl": wat(lo), "wh": wat(hi), "lm": p.get("lm", [])}


def band_of(v):
    for lo, hi, name in BANDS:
        if lo <= v < hi:
            return name
    return "over600"


# ---------------------------------------------------------------- stage 1
def score(tx_path, geo_path, view_path, model_path, cache_dir):
    import lightgbm as lgb
    from panel2 import ALL, Panel, Y0, NY
    cache = Path(cache_dir); cache.mkdir(parents=True, exist_ok=True)
    panel = Panel(tx_path, geo_path, view_path)
    bst = lgb.Booster(model_file=model_path)
    assert bst.feature_name() == ALL, "model features do not match the panel"
    oc_of = panel.oc_names[panel.oc]
    for key, cfg in CITIES.items():
        s = np.nonzero(~panel.sold & np.isin(oc_of, cfg["outcodes"]))[0]
        t = np.full(len(s), SCORE_YEAR, dtype="int32")
        X = panel.features(s, t)
        p = bst.predict(X, num_threads=3)
        d, byi = panel.oc[s], panel.year[s] - Y0
        est = panel.price[s] * panel.d_med[d, NY - 1] / np.maximum(panel.d_med[d, byi], 1)
        out = pd.DataFrame({
            "postcode": panel.pc_names[panel.pc[s]], "outcode": oc_of[s],
            "ptype": np.array(list("DSTF"))[np.clip(panel.ptype[s], 0, 3)],
            "tenure": SCORE_YEAR - panel.year[s], "price": panel.price[s],
            "p_sale": p, "est_value": np.clip(est, 30_000, 5_000_000)})
        out = out[panel.ptype[s] >= 0]
        out.to_parquet(cache / f"scored_{key}.parquet", index=False)
        print(f"{cfg['name']}: {len(out):,} owned homes scored, mean p {out.p_sale.mean():.4f}, "
              f"expected sellers {out.p_sale.sum():.0f}", flush=True)


# ---------------------------------------------------------------- stage 2
def mask_tables(houses, flagcols):
    bits = np.zeros(len(houses), dtype=np.int64)
    for i, col in enumerate(flagcols):
        bits |= houses[col].fillna(False).astype(bool).to_numpy().astype(np.int64) << i
    h = pd.DataFrame({"postcode": houses.postcode.to_numpy(), "sector": houses.sector.to_numpy(),
                      "mask": bits, "w": houses.n_uprn.to_numpy().astype(float)})
    def dist(key):
        g = h.groupby([key, "mask"], as_index=False).w.sum()
        g["w"] = g.w / g.groupby(key).w.transform("sum")
        return g
    return dist("postcode"), dist("sector")


def export_city(key, cfg, cache, geo, views_dir, model_meta):
    d = pd.read_parquet(Path(cache) / f"scored_{key}.parquet")
    gcols = ["postcode", "nox", "pc_within_1km", "km_gp", "lat", "lon"]
    d = d.merge(geo[gcols], on="postcode", how="left")
    d = d[d.nox.notna()].copy()
    part = d.postcode.str.rsplit(" ", n=1)
    d["sector"] = part.str[0] + " " + part.str[1].str[0]
    d["band"] = d.est_value.apply(band_of)
    pct = d.p_sale.rank(pct=True)
    d["premium"] = 0.06 + 0.12 * (1 - pct) + 0.004 * d.tenure.clip(upper=25)
    d["offer_mid"] = d.est_value * (1 + d.premium)
    top_cut = float(d.p_sale.quantile(0.80))
    d["top"] = d.p_sale >= top_cut
    dlat = (d.lat - cfg["centre"][0]) * 111.19
    dlon = (d.lon - cfg["centre"][1]) * 111.19 * np.cos(np.radians(cfg["centre"][0]))
    d["mins"] = np.hypot(dlat, dlon) / KMH_URBAN * 60

    # ---- house-level outlooks ------------------------------------------
    sec_json = json.load(open(Path(views_dir) / f"sectors_{key}.json"))
    houses = pd.read_parquet(Path(views_dir) / f"houses_{key}.parquet")
    lm_names = [l["name"] for l in sec_json["meta"]["landmarks"]]
    flags = [{"key": k, "label": lab, "why": why or cfg[k], "group": "view"} for k, lab, why in GENERIC]
    generic_cols = ["has_" + k for k, *_ in GENERIC]
    light_file = Path(views_dir) / f"light_{key}.parquet"
    if light_file.exists():                              # rows are in the same order as the house table
        L = pd.read_parquet(light_file)
        assert len(L) == len(houses)
        for k, lab, why, rule in LIGHT:
            houses["has_" + k] = rule(L).to_numpy()
            flags.append({"key": k, "label": lab, "why": why, "group": "light"})
            generic_cols.append("has_" + k)
    flags += [{"key": f"lm{i}", "label": cfg["lm_label"][nm], "lm": nm, "group": "lm",
               "why": f"A clear line of sight from the upper windows to {nm}, checked against every roof and tree in between."}
              for i, nm in enumerate(lm_names)]
    flagcols = generic_cols + ["sees_" + nm for nm in lm_names]
    sec_share = {c[4:]: houses.groupby("sector").apply(lambda g, c=c: float(np.average(g[c].fillna(False).astype(float), weights=g.n_uprn)))
                 for c in generic_cols}
    pc_dist, sec_dist = mask_tables(houses, flagcols)

    d["cell"] = d.sector + "|" + d.ptype + "|" + d.band
    a = d[["cell", "postcode", "sector"]].merge(pc_dist, on="postcode", how="left")
    miss = a["mask"].isna()
    b = a.loc[miss, ["cell", "sector"]].merge(sec_dist, on="sector", how="left")
    a = pd.concat([a.loc[~miss, ["cell", "mask", "w"]], b[["cell", "mask", "w"]]])
    a["mask"] = a["mask"].fillna(0).astype(int); a["w"] = a.w.fillna(1.0)
    hist = a.groupby(["cell", "mask"]).w.sum()
    print(f"  {cfg['name']}: {1 - miss.mean():.0%} of owned homes matched to a postcode with house-level views", flush=True)

    cells = []
    for cell, g in d.groupby("cell"):
        if len(g) < 12:
            continue
        sec, pt, band = cell.split("|")
        hm = hist.loc[cell]
        vm = []
        for m_, w_ in hm.items():
            if w_ >= 0.05:
                vm += [int(m_), round(float(w_), 1)]
        cells.append({
            "sector": sec, "outcode": sec.split(" ")[0], "ptype": pt, "band": band, "n": int(len(g)),
            "n_top": int(g.top.sum()), "exp_sellers": round(float(g.p_sale.sum()), 2),
            "p_med": round(float(g.p_sale.median()), 4),
            "value_med": int(g.est_value.median() // 1000 * 1000),
            "offer_med": int(g.offer_mid.median() // 1000 * 1000),
            "premium_med": round(float(g.premium.median()), 3), "tenure_med": float(g.tenure.median()),
            "nox": round(float(g.nox.median()), 1), "density": int(g.pc_within_1km.median()),
            "km_gp": round(float(g.km_gp.median()), 2), "min_centre": int(round(g.mins.median())),
            "lat": round(float(g.lat.median()), 4), "lon": round(float(g.lon.median()), 4), "vm": vm})

    views = {}
    for sec, e in sec_json["sectors"].items():
        v = {k: e[k] for k in ("n_houses", "n_addr", "shares", "landmarks", "typical", "best", "typ") if k in e}
        v["shares"] = {k: round(float(sv.get(sec, 0.0)), 2) for k, sv in sec_share.items()}
        v["garden"] = e.get("garden")
        for k in ("pano_typical", "pano_best", "pano_garden"):
            if k in e:
                v[k] = enc_pano(e[k])
        views[sec] = v

    rng = np.random.RandomState(42 if key == "exeter" else 7)
    pool = d[d.top & d.ptype.isin(["S", "T", "D"]) & d.est_value.between(240_000, 650_000)
             & d.sector.isin(list(views))].nlargest(400, "p_sale")
    exemplars, seen = [], set()
    for _, r in pool.iterrows():
        if r.sector in seen or len(exemplars) >= 3 or "pano_garden" not in views[r.sector]:
            continue
        seen.add(r.sector)
        exemplars.append({
            "code": f"{r.outcode}-{rng.randint(0x1000, 0xFFFF):04X}", "city": key, "sector": r.sector,
            "ptype": r.ptype, "tenure": int(r.tenure), "p_sale": round(float(r.p_sale), 3),
            "est_value": int(round(r.est_value, -4)), "offer_lo": int(round(r.offer_mid * 0.96, -3)),
            "offer_mid": int(round(r.offer_mid, -3)), "offer_hi": int(round(r.offer_mid * 1.04, -3)),
            "premium_pct": round(float(r.premium) * 100, 1), "nox": round(float(r.nox), 1),
            "min_centre": int(round(r.mins))})

    return {
        "name": cfg["name"], "centre_name": cfg["centre_name"], "frank": cfg["frank"], "areas": cfg["areas"],
        "lat": cfg["centre"][0], "lon": cfg["lon"],
        "area": {"n_owned_tracked": int(len(d)), "exp_sellers_12m": round(float(d.p_sale.sum())),
                 "top_band_cut": round(top_cut, 4), "p_sale_mean": round(float(d.p_sale.mean()), 4),
                 "n_houses_viewed": sec_json["meta"]["n_houses"], "n_addr_viewed": sec_json["meta"]["n_addr"]},
        "flags": flags, "landmarks": sec_json["meta"]["landmarks"],
        "within_postcode_variance": sec_json["meta"]["within_postcode_variance"],
        "cells": cells, "exemplars": exemplars, "views": views}


def export(cache, geo_path, views_dir, lab_dir, out_json):
    geo = pd.read_parquet(geo_path)
    lab = Path(lab_dir)
    load = lambda f: json.load(open(lab / f)) if (lab / f).exists() else {}
    curve, deploy, ladder = load("lab_curve.json"), load("lab_deploy.json"), load("lab_ladder.json")
    pct = deploy.get("pct", 10)
    best = curve.get(f"ALL@{pct}") or (ladder.get("ALL") if ladder.get("pct") == pct else None) or {}
    local = load("lab_local.json").get(f"ALL@{pct}", {})      # ranking inside a district: what a campaign uses
    model = {"auc_oot": round(best.get("auc", 0), 3),
             "lift_top10": round(local.get("local_lift10") or best.get("lift10", 0), 2),
             "lift_top10_national": round(best.get("lift10", 0), 2),
             "lift_top1": round(best.get("lift1", 0), 2), "train_rows": deploy.get("train_rows"),
             "sample_pct": pct, "n_signals": len(deploy.get("features", [])),
             "trained_on": "HM Land Registry Price Paid Data 1995-2019, 24.3M transactions"}
    out = {"model": model,
           "nox_national": {str(k): v for k, v in geo.nox.quantile([.1, .25, .5, .75, .9]).round(2).to_dict().items()},
           "density_national": {str(k): v for k, v in geo.pc_within_1km.quantile([.1, .25, .5, .75, .9]).round(0).to_dict().items()},
           "alph": ALPH, "a_lo": round(float(A_LO), 4), "a_span": round(float(A_SPAN), 4),
           "cities": {k: export_city(k, cfg, cache, geo, views_dir, model) for k, cfg in CITIES.items()
                      if (Path(views_dir) / f"sectors_{k}.json").exists()}}
    with open(out_json, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    for k, c in out["cities"].items():
        print(f"{c['name']}: {len(c['cells'])} cells, {len(c['views'])} sectors with views, "
              f"{len(c['exemplars'])} exemplars, {len(c['flags'])} view flags")
    print(f"wrote {out_json} ({Path(out_json).stat().st_size / 1024:.0f} KB); model {model}")


if __name__ == "__main__":
    {"score": score, "export": export}[sys.argv[1]](*sys.argv[2:])
