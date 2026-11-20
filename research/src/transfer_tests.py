"""Does what is learned in one city hold in the other?

travel_tests.py measures each city on its own and finds the same pattern
twice. This is stricter. A score is built from one city's data alone and
then has to explain the other city, where none of that city's sales were
used to build it. If the score still works there, the views mean the
same thing in both places.

Two outcomes are tested with the same three groups of measures:

  outlook       long views, furthest sight-line, hills, water, and the
                cathedral or the Abbey in sight, from the upper windows
  garden_light  how overlooked and enclosed the garden is, sun in the
                garden, and direct sun on the front and back windows
  all           both groups together

1. Price. In the source city, log price is fitted on year, type,
   new-build, leasehold and neighbourhood plus the measures. The fitted
   weights make a score for every home in the target city. Target prices
   are then fitted on the same controls plus that one score. A slope of 1
   means the premium learned in the source city is paid in full in the
   target; 0 means it does not carry at all.
   The test is run a second time holding stand-ins for the size of the
   home fixed as well, since sale records carry no floor area.

2. Sale timing. The same, with the yearly chance of a sale in place of
   price, holding type, price, length of ownership and year fixed.

A third check asks the practical question: does adding the measures to
the published sale-timing model improve who it picks, on later years
and in the other city?

Ranges re-sample whole postcodes (price) or whole properties (timing) in
both cities at once, so they carry the uncertainty of building the score
as well as of testing it. Sale records join houses at the postcode.

Usage: python transfer_tests.py <transactions.parquet> <views2_dir>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from city_views import CITIES  # noqa: E402
from light import CTRL, postcode_table  # noqa: E402
from propensity_model import (FEATURES as BASE, TEST_YEARS, TRAIN_YEARS,  # noqa: E402
                              build_panel, district_year_features, featurise)
from view_ablation2 import compare  # noqa: E402

MAIN = {"exeter": "Exeter Cathedral", "bath": "Bath Abbey"}
SETS = {"outlook": ["m_u_long", "log_reach", "m_u_hills", "s_has_water", "s_main"],
        "garden_light": ["m_g_overlooked", "m_g_horizon", "m_sun_evening_jun", "m_sun_equinox",
                         "light_front", "light_back"]}
SETS["all"] = SETS["outlook"] + SETS["garden_light"]
COLS = SETS["all"]
NAMES = {"outlook": "the outlook from the upper windows", "garden_light": "the garden and sunlight", "all": "all of them"}
SIZE = ["storeys", "depth_m", "log_addr", "plot_open", "has_garden"]     # stand-ins for the size of the home
NB, BOOT = 400, 300


def view_table(city, views_dir):
    v = pd.read_parquet(Path(views_dir) / f"postcodes_{city}.parquet").set_index("postcode")
    v = v.join(postcode_table(pd.read_parquet(Path(views_dir) / f"light_{city}.parquet"))[["light_front", "light_back"]])
    v["log_reach"] = np.log(v.m_u_longest_km.clip(lower=0.05))
    v["s_main"] = v["s_sees_" + MAIN[city]]
    h = pd.read_parquet(Path(views_dir) / f"houses_{city}.parquet",
                        columns=["postcode", "storeys", "depth_m", "n_uprn", "plot_open", "has_garden"])
    h["log_addr"] = np.log(h.n_uprn.clip(lower=1)); h["has_garden"] = h.has_garden.astype(float)
    return v[COLS].join(h.groupby("postcode")[SIZE].mean())


class Design:
    """Controls, measures and outcome, summed in blocks so that any re-sample
    and any score can be fitted without touching the rows again."""

    def __init__(self, base, V, y, blk):
        X = np.column_stack([base, V]).astype("float64"); y = y.astype("float64")
        self.k = base.shape[1]; self.n = len(y); self.V = V
        order = np.argsort(blk, kind="stable"); cuts = np.searchsorted(blk[order], np.arange(NB + 1))
        parts = [order[cuts[i]:cuts[i + 1]] for i in range(NB)]
        self.XtX = np.stack([X[p].T @ X[p] for p in parts])
        self.Xty = np.stack([X[p].T @ y[p] for p in parts])
        self.yy = np.array([y[p] @ y[p] for p in parts])

    def sums(self, w):
        return np.tensordot(w, self.XtX, 1), w @ self.Xty, w @ self.yy

    def weights(self, w, cols):
        """Weights on the measures in `cols`, fitted with the controls."""
        A, g, _ = self.sums(w)
        idx = list(range(self.k)) + [self.k + j for j in cols]
        return np.linalg.lstsq(A[np.ix_(idx, idx)], g[idx], rcond=None)[0][self.k:]

    def slope(self, w, cols, b):
        """Slope on the score (measures in `cols` times weights `b`), fitted
        with the controls, and the unexplained variation with and without it."""
        A, g, yy = self.sums(w); k = self.k; vc = [k + j for j in cols]
        ABB, gB = A[:k, :k], g[:k]
        ABV = A[:k][:, vc] @ b
        M = np.block([[ABB, ABV[:, None]], [ABV[None, :], np.array([[b @ A[np.ix_(vc, vc)] @ b]])]])
        r = np.concatenate([gB, [b @ g[vc]]])
        sol = np.linalg.lstsq(M, r, rcond=None)[0]
        ssr_base = yy - gB @ np.linalg.lstsq(ABB, gB, rcond=None)[0]
        idx = list(range(k)) + vc
        ssr_own = yy - g[idx] @ np.linalg.lstsq(A[np.ix_(idx, idx)], g[idx], rcond=None)[0]
        return sol[-1], ssr_base, yy - r @ sol, ssr_own


def price_design(tx_all, city, V, size=False):
    """With `size`, the controls also hold fixed the postcode's typical number
    of storeys, depth of house front to back, addresses per building, open
    share of the plot and share of homes with a garden: the nearest thing open
    data has to floor area."""
    cfg = CITIES[city]
    tx = tx_all[tx_all.outcode.astype(str).isin(cfg["outcodes"]) & tx_all.year.between(2010, 2019)].copy()
    tx["postcode"] = tx.postcode.astype(str)
    tx = tx[tx.postcode.isin(V.index)]
    part = tx.postcode.str.rsplit(" ", n=1)
    tx["sector"] = part.str[0] + " " + part.str[1].str[0]
    D = pd.get_dummies(tx[["year", "ptype", "sector"]].astype(str), drop_first=True, dtype="float64")
    base = np.column_stack([np.ones(len(tx)), tx.is_new.to_numpy(dtype="float64"),
                            tx.leasehold.to_numpy(dtype="float64"), D.to_numpy()])
    rows = V.reindex(tx.postcode)
    if size:
        base = np.column_stack([base, rows[SIZE].to_numpy()])
    blk = pd.factorize(tx.postcode)[0] % NB
    return Design(base, rows[COLS].to_numpy(), np.log(tx.price.to_numpy(dtype="float64")), blk), len(tx)


def timing_panel(tx_all, city, V):
    tx = tx_all[tx_all.outcode.astype(str).isin(CITIES[city]["outcodes"])].copy()
    for c in ("postcode", "outcode", "ptype"):
        tx[c] = tx[c].astype(str).astype("category")
    tx = tx.sort_values(["key", "year", "month"], ignore_index=True)
    panel = featurise(build_panel(tx, district_year_features(tx), 100))
    v = V.reindex(pd.Index(tx["postcode"].cat.categories))
    code = panel["pc_code"].to_numpy(); ok = code >= 0
    for c in COLS:
        col = np.full(len(panel), np.nan); col[ok] = v[c].to_numpy()[code[ok]]; panel[c] = col
    seen = np.zeros(len(panel), bool); seen[ok] = v[COLS[0]].notna().to_numpy()[code[ok]]
    panel = panel[seen].copy()
    panel["block"] = (np.abs(panel["key"].to_numpy()) // 7) % 1024
    return panel


def timing_design(panel):
    C = panel[CTRL].astype("float64"); C = C.fillna(C.median()); C["tenure_sq"] = C["tenure"] ** 2
    C = (C - C.mean()) / C.std().replace(0, 1)
    yr = pd.get_dummies(panel["year"].astype(int), drop_first=True, dtype="float64")
    base = np.column_stack([np.ones(len(panel)), C.to_numpy(), yr.to_numpy()])
    blk = ((np.abs(panel["key"].to_numpy()) // 7) % NB).astype(int)
    return Design(base, panel[COLS].to_numpy(dtype="float64"), panel["label"].to_numpy(), blk)


def transfer(S, T, cols, rng, scale=1.0):
    """Build the score in S, test it in T. `scale` turns the quarter gap into
    reported units."""
    one = np.ones(NB)
    b = S.weights(one, cols)
    g, ssr_base, ssr_idx, ssr_own = T.slope(one, cols, b)
    score = T.V[:, cols] @ b
    q = np.quantile(score, [.25, .75])
    gap = score[score >= q[1]].mean() - score[score <= q[0]].mean()      # top quarter against bottom quarter
    draws = []
    for _ in range(BOOT):
        bb = S.weights(rng.poisson(1.0, NB).astype("float64"), cols)
        draws.append(T.slope(rng.poisson(1.0, NB).astype("float64"), cols, bb)[0])
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"slope": round(float(g), 2), "range": [round(float(lo), 2), round(float(hi), 2)],
            "p_positive": round(float((np.array(draws) > 0).mean()), 3),
            "share_of_own_fit": round(float((ssr_base - ssr_idx) / max(ssr_base - ssr_own, 1e-12)), 2),
            "top_vs_bottom_quarter": round(float(scale(g * gap) if callable(scale) else scale * g * gap), 2)}


def main(tx_path, views_dir):
    tx = pd.read_parquet(tx_path)
    V = {c: view_table(c, views_dir) for c in CITIES}
    both = pd.concat(V.values())
    mu, sd = both.mean(), both.std()
    known = {c: v[COLS[0]].notna() for c, v in V.items()}
    V = {c: ((v - mu) / sd).fillna(0.0)[known[c]] for c, v in V.items()}  # one scale for both cities
    rng = np.random.default_rng(11)
    res = {"price": {}, "timing": {}, "picking": {}}
    pairs = (("exeter", "bath"), ("bath", "exeter"))
    col_idx = {name: [COLS.index(c) for c in cols] for name, cols in SETS.items()}

    P = {}
    for c in CITIES:
        P[c], n = price_design(tx, c, V[c]); res["price"][f"sales_{c}"] = int(n)
    print("\nPRICE. A score built from one city's sales, tested on the other's.")
    print("  slope 1 = the premium is paid in full in the other city; 0 = it does not carry")
    print(f"  {'built in -> tested in':24s} {'measures':14s} {'slope (95% range)':>24s} {'share of own fit':>17s} {'top v bottom quarter':>21s}")
    for a, b in pairs:
        for name in SETS:
            r = transfer(P[a], P[b], col_idx[name], rng, scale=lambda x: 100 * (np.exp(x) - 1))
            res["price"][f"{a}_to_{b}_{name}"] = r
            print(f"  {a + ' -> ' + b:24s} {name:14s} {r['slope']:+7.2f} ({r['range'][0]:+.2f} to {r['range'][1]:+.2f}) "
                  f"{100 * r['share_of_own_fit']:15.0f}% {r['top_vs_bottom_quarter']:+19.1f}%", flush=True)

    print("\nPRICE, ALSO HOLDING THE SIZE OF THE HOME FIXED (storeys, depth, addresses per building, plot, garden)")
    Pz = {c: price_design(tx, c, V[c], size=True)[0] for c in CITIES}
    for a, b in pairs:
        for name in SETS:
            r = transfer(Pz[a], Pz[b], col_idx[name], rng, scale=lambda x: 100 * (np.exp(x) - 1))
            res["price"][f"{a}_to_{b}_{name}_size"] = r
            print(f"  {a + ' -> ' + b:24s} {name:14s} {r['slope']:+7.2f} ({r['range'][0]:+.2f} to {r['range'][1]:+.2f}) "
                  f"{100 * r['share_of_own_fit']:15.0f}% {r['top_vs_bottom_quarter']:+19.1f}%", flush=True)

    panels = {c: timing_panel(tx, c, V[c]) for c in CITIES}
    Tm = {c: timing_design(panels[c]) for c in CITIES}
    for c in CITIES:
        res["timing"][f"home_years_{c}"] = int(len(panels[c])); res["timing"][f"sales_{c}"] = int(panels[c].label.sum())
    print("\nSALE TIMING. A score built from one city's sales, tested on the other's.")
    print("  the score is the change in the yearly chance of a sale that the measures predict")
    print(f"  {'built in -> tested in':24s} {'measures':14s} {'slope (95% range)':>24s} {'share of own fit':>17s} {'top v bottom quarter':>21s}")
    for a, b in pairs:
        for name in SETS:
            r = transfer(Tm[a], Tm[b], col_idx[name], rng, scale=100.0)
            b_w = Tm[a].weights(np.ones(NB), col_idx[name])
            sc = panels[b][COLS].to_numpy()[:, col_idx[name]] @ b_w
            band = pd.qcut(pd.Series(sc).rank(method="first"), 4, labels=False)
            r["sale_rate_by_quarter_of_score"] = [round(float(x), 4) for x in panels[b].label.groupby(band.to_numpy()).mean()]
            res["timing"][f"{a}_to_{b}_{name}"] = r
            q = r["sale_rate_by_quarter_of_score"]
            print(f"  {a + ' -> ' + b:24s} {name:14s} {r['slope']:+7.2f} ({r['range'][0]:+.2f} to {r['range'][1]:+.2f}) "
                  f"{100 * r['share_of_own_fit']:15.0f}% {r['top_vs_bottom_quarter']:+16.2f} pts   "
                  f"raw yearly sale rate by quarter of score: {100*q[0]:.2f}% {100*q[1]:.2f}% {100*q[2]:.2f}% {100*q[3]:.2f}%", flush=True)

    print("\nPICKING DOORS. The published 13-signal model with and without the measures, on later years.")
    for name in ("garden_light", "outlook"):
        cols = SETS[name]
        for a, b in (("exeter", "exeter"), ("bath", "bath")) + pairs:
            tr = panels[a][panels[a]["year"].between(*TRAIN_YEARS)]
            te = panels[b][panels[b]["year"].between(*TEST_YEARS)]
            res["picking"][f"{a}_to_{b}_{name}"] = compare(tr, te, f"{name}: {a} -> {b}", view=cols)
    json.dump(res, open(Path(views_dir) / "transfer_tests.json", "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:3])
