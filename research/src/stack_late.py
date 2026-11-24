"""A second step on the deployed model, aimed at homes that are not yet on the market.

Refitting the whole model on the later target (assess_late.py) loses more than it gains, and a
model given fresh sale certificates fills its lists with homes that are already listed and slow
to sell. So the deployed model is kept as it is, and a small second model reads its prediction,
the years owned and the certificate columns. It is aimed at the homes the product is for:

  not yet listed   the sale completes between July of the year and June of the next, and the
                   certificate for it had not been lodged on the scoring day (listed_truth.py)

A fresh sale certificate then counts against a home (it is on the market already) and older
signs of intent count for it. Three other measures are reported beside it, none of which the
second step is fitted on: every sale completing July to June, sales completing October to June
(nine months out or more, where a listing before the scoring day is rare, and which owes
nothing to the certificates), and the share of the list whose sale was already under way.

The test. The second step is fitted on one test year and scored on the other, and the reverse,
so no home is scored by a model that saw its outcome. It is repeated on each fit of the
deployed model (seeds 7, 8, 9): the spread of the gains is the fit's own noise.

    python stack_late.py [facts]        "facts" adds the columns of epc2_signals.py

Writes research/outputs/signals/STACK_LATE[_FACTS].json and .md, and the second step fitted on
both test years to research/outputs/lab/model_second[_facts].txt with its description beside it.
"""
import json
import sys
import time

import lightgbm as lgb
import numpy as np

import epc_signals as ES
import local_eval as LE
import screen_late as SL

PANEL, LAB, OUT = SL.PANEL, SL.LAB, SL.OUT
PAR = dict(objective="cross_entropy", learning_rate=0.04, num_leaves=31, min_data_in_leaf=1000, feature_fraction=0.9,
           bagging_fraction=0.7, bagging_freq=1, lambda_l2=10, verbose=-1, seed=7, num_threads=4)
ROUNDS = 250
BANDS = {"all": "All", "t0_9": "Under 10 years", "t10_19": "10 to 19 years", "t20p": "20 years or more"}
MEASURES = {"not_listed": "Not yet listed", "later": "Completes July to June", "far": "Completes October to June"}


def logit(p):
    p = np.clip(np.asarray(p, np.float64), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def cross_fit(Z, y, year, cols):
    """Each test year scored by a second step fitted on the other."""
    out = np.empty(len(y))
    for a, b in ((2017, 2018), (2018, 2017)):
        tr, te = year == a, year == b
        out[te] = lgb.train(PAR, lgb.Dataset(Z[tr][:, cols], y[tr]), ROUNDS).predict(Z[te][:, cols])
    return out


def main():
    facts = len(sys.argv) > 1 and sys.argv[1] == "facts"
    sfx = "_facts" if facts else ""
    t = LE.load_test(PANEL); ym = SL.end_ym(); frac = np.load(PANEL / "test_listed_after.npy").astype(np.float64)
    X = np.vstack([np.load(PANEL / f"R_EPC_{c}.npy")[np.load(PANEL / f"year_{c}.npy") >= 2017] for c in (0, 1)]).astype("float32")
    names = ["first_step", "tenure"] + [f"epc_{c}" for c in ES.COLS]
    if facts:
        import epc2_signals as E2
        assert json.load(open(PANEL / "test_EPC2.json")) == E2.COLS, "run listed_truth.py first"
        N = np.clip(np.load(PANEL / "test_EPC2.npy"), -6e4, 6e4).astype("float16").astype("float32")     # as a stored row family
        X = np.hstack([X, N]); names += [f"epc2_{c}" for c in E2.COLS]
    keep = t["year"] <= 2018
    tk = {k: v[keep] for k, v in t.items()}
    X, ym, frac = X[keep], ym[keep], frac[keep]
    year, ten, y_year = tk["year"].astype(np.int64), tk["tenure"].astype(np.float64), tk["y"].astype(np.float64)
    start = year * 12
    later = ((ym >= start + 6) & (ym < start + 18)).astype(np.float64)
    Y = {"not_listed": later * frac, "later": later, "far": ((ym >= start + 9) & (ym < start + 18)).astype(np.float64)}
    early = ((ym >= start) & (ym < start + 6)).astype(np.float64)
    target = Y["not_listed"]
    preds = LAB / "preds"
    first = {7: np.load(preds / f"{SL.CUR}@100.npy")[keep]}
    for f in sorted(preds.glob(f"{SL.CUR}@100~s[0-9]*.npy")):
        if "~late" not in f.name:
            first[int(f.stem.split("~s")[1])] = np.load(f)[keep]
    arms = {}                                                     # seed -> {"deployed", "aimed", "second"}
    for s, p in first.items():
        Z = np.column_stack([logit(p), ten, X])
        arms[s] = {"deployed": p, "aimed": cross_fit(Z, target, year, [0, 1]), "second": cross_fit(Z, target, year, list(range(Z.shape[1])))}
        print(f"seed {s}: second step fitted both ways", flush=True)

    R = {"when": time.strftime("%Y-%m-%d"), "first_step": SL.CUR, "columns": names, "rounds": ROUNDS, "seeds": sorted(first),
         "rows": int(len(later)), "later_sellers": int(later.sum()), "of_them_not_yet_listed": round(float(target.sum() / later.sum()), 4),
         "bands": {}}
    for nm, lo, hi in LE.TENURE:
        L = LE.Local(tk, lo, hi); k = L.keep
        tops = {s: {a: L.top_mask(v[k]) for a, v in A.items()} for s, A in arms.items()}
        res = {}
        for meas, y in Y.items():
            L.y = y[k]
            r = {a: round(L.lift(tops[7][a]), 4) for a in ("deployed", "aimed", "second")}
            for g, a, b in (("aim", "deployed", "aimed"), ("certificates", "aimed", "second"), ("both", "deployed", "second")):
                per_seed = [L.lift(tops[s][b]) - L.lift(tops[s][a]) for s in tops]
                rng = np.random.default_rng(3); d = []
                for _ in range(SL.BOOT):
                    w = rng.poisson(1.0, LE.N_BLOCKS).astype(float)[L.block]
                    d.append(L.lift(tops[7][b], w) - L.lift(tops[7][a], w))
                lo_, hi_ = (float(np.percentile(d, q)) for q in (2.5, 97.5))
                v = {"gain": round(per_seed[0], 4), "range": [round(lo_, 4), round(hi_, 4)], "by_seed": [round(x, 4) for x in per_seed]}
                if len(per_seed) >= 2:                           # the same first step on both sides: only the gain's own spread counts
                    sd = float(np.std(per_seed, ddof=1)); half = float(np.hypot((hi_ - lo_) / 2, 1.96 * sd)); mid = (lo_ + hi_) / 2
                    v["seed_sd"] = round(sd, 4); v["range_with_fit_noise"] = [round(mid - half, 4), round(mid + half, 4)]
                r[g] = v
            res[meas] = r
        res["list"] = {}
        for a in ("deployed", "second"):
            top = tops[7][a]; L.y = y_year[k]; n_top = top.sum()
            res["list"][a] = {"not_yet_listed": round(float((target[k] * top).sum() / n_top), 4),
                              "sells_later_already_listed": round(float(((later[k] - target[k]) * top).sum() / n_top), 4),
                              "under_way": round(float((early[k] * top).sum() / n_top), 4), "calendar_year": round(L.lift(top), 4)}
        R["bands"][nm] = res
        b = res["not_listed"]["both"]
        print(f"  {nm:6s} not yet listed: deployed {res['not_listed']['deployed']:.3f}, second step without certificates "
              f"{res['not_listed']['aimed']:.3f}, with {res['not_listed']['second']:.3f}; both {b['gain']:+.3f} "
              f"{b.get('range_with_fit_noise', b['range'])} by seed {b['by_seed']}; far {res['far']['both']['gain']:+.3f} "
              f"{res['far']['both'].get('range_with_fit_noise')}; under way {res['list']['deployed']['under_way']:.3f} to "
              f"{res['list']['second']['under_way']:.3f}", flush=True)
    # the forward direction alone: fitted on 2017, scored on 2018
    m18 = year == 2018
    L = LE.Local({k_: v[m18] for k_, v in tk.items()}); L.y = target[m18][L.keep]
    R["forward_2018"] = {a: round(L.lift(L.top_mask(arms[7][a][m18][L.keep])), 4) for a in ("deployed", "aimed", "second")}
    print("  forward (2018 scored by a second step fitted on 2017):", R["forward_2018"], flush=True)

    A = R["bands"]["all"]; r = A["not_listed"]["both"]; rr = r.get("range_with_fit_noise", r["range"])
    far = A["far"]["both"]; fr = far.get("range_with_fit_noise", far["range"])
    R["passes"] = bool(rr[0] > 0 and fr[1] > 0 and A["list"]["second"]["under_way"] <= A["list"]["deployed"]["under_way"])
    R["verdict"] = ("add the second step: it finds more homes that are not yet on the market, the range is clear of zero and of the "
                    "fit's own noise, it is no worse nine months out or more, and its lists hold fewer homes whose sale is already "
                    "under way" if R["passes"] else
                    "do not add the second step: it does not clearly find more homes that are not yet on the market")
    # the second step for the product: fitted on both test years, first step = the deployed fit
    Z = np.column_stack([logit(first[7]), ten, X])
    bst = lgb.train(PAR, lgb.Dataset(Z, target, feature_name=names), ROUNDS)
    bst.save_model(str(LAB / f"model_second{sfx}.txt"))
    g = bst.feature_importance("gain"); R["gain_share"] = {n: round(float(v / g.sum()), 3) for n, v in sorted(zip(names, g), key=lambda kv: -kv[1])}
    json.dump({"first_step": SL.CUR, "label": "not yet listed: completes July to June, certificate not lodged by the scoring day",
               "columns": names, "rounds": ROUNDS, "rows": int(len(later)),
               "fitted_on": "test homes of 2017 and 2018 (a tenth of homes), first step fitted to 2015", "passes": R["passes"],
               "rate": round(float(target.mean()), 5)}, open(LAB / f"lab_second{sfx}.json", "w"), indent=1)

    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(OUT / f"STACK_LATE{sfx.upper()}.json", "w"), indent=1)
    f = lambda v: (lambda q: f"{v['gain']:+.3f} ({q[0]:+.3f} to {q[1]:+.3f})")(v.get("range_with_fit_noise", v["range"]))   # noqa: E731
    md = ["# A second step aimed at homes not yet on the market" + (" (with past intent and home facts)" if facts else ""), "",
          f"**Verdict:** {R['verdict']}", "",
          "Homes are scored on 1 January. The deployed model is kept; the second step reads its prediction, the years owned and",
          "the certificate columns, and is aimed at homes that sell later and were not yet listed on the scoring day. Figures",
          "are sellers found in the best tenth of each postcode district, times random, test years 2017 and 2018, each year",
          f"scored by a second step fitted on the other. Ranges are 95% and include the spread of the gain over {len(first)} fits",
          "of the deployed model.", ""]
    for meas, title in MEASURES.items():
        md += [f"## {title}", "",
               "| Owners | Deployed model | Second step, no certificates | Second step, with certificates | Gain from certificates | Gain in all |",
               "|---|---|---|---|---|---|"]
        for k_, lab in BANDS.items():
            v = R["bands"][k_][meas]
            md.append(f"| {lab} | {v['deployed']:.3f} | {v['aimed']:.3f} | {v['second']:.3f} | {f(v['certificates'])} | {f(v['both'])} |")
        md.append("")
    fw = R["forward_2018"]
    md += [f"Gain in all (not yet listed, all owners) by fit of the deployed model: {', '.join(f'{x:+.3f}' for x in r['by_seed'])}.",
           f"Forward direction only (2018 scored by a second step fitted on 2017): {fw['deployed']:.3f} to {fw['second']:.3f}.", "",
           "## What the list is made of (all owners)", "",
           "| Ranking | Sells later, not yet listed | Sells later, already listed | Sale already under way | Sellers in the calendar year, times random |",
           "|---|---|---|---|---|"]
    for a, lab in (("deployed", "Deployed model"), ("second", "With the second step")):
        w = A["list"][a]
        md.append(f"| {lab} | {100 * w['not_yet_listed']:.1f}% | {100 * w['sells_later_already_listed']:.1f}% | {100 * w['under_way']:.1f}% | {w['calendar_year']:.3f} |")
    md += ["", "## What the second step leans on", "", "| Column | Share of gain |", "|---|---|"]
    md += [f"| {n} | {100 * s:.1f}% |" for n, s in list(R["gain_share"].items())[:12]] + [""]
    (OUT / f"STACK_LATE{sfx.upper()}.md").write_text("\n".join(md))
    print(f"== {R['verdict']}", flush=True)


if __name__ == "__main__":
    main()
