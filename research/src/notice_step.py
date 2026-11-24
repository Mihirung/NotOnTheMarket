"""Bankruptcy orders and deceased-estate notices: a second step on the deployed model.

The notices (gazette_list.py, notice_signals.py) only reach back to 2012, so the deployed model,
fitted on 2001 to 2015, cannot be refitted with them. Instead the deployed model is kept as it is
and a small second model reads the notice columns alone and learns what to add to the deployed
model's log-odds. A home with no notice has no columns, so its place in the ranking does not move.

The test. Every home-year of 2017 and 2018 is used: the two test chunks (a tenth of homes, never
seen by the deployed model) and the other eighteen (homes it was fitted on up to 2015, here in
later years). The second step is fitted on the eighteen chunks in one year and scored on the test
chunks in the other year, and the reverse: different homes and a different year. It is repeated on
each fit of the deployed model (seeds 7, 8, 9).

Measures, all as sellers found in the best tenth of each postcode district, times random:
  year         the home sells in the calendar year (the deployed model's own target)
  later        the sale completes between July of the year and June of the next
  not_listed   later, and not yet listed on the scoring day (listed_truth.py)

    python notice_step.py first        the deployed model's prediction for every chunk's 2017 and 2018 rows (once)
    python notice_step.py features     the NOTICE columns for the same rows (again whenever more notices arrive)
    python notice_step.py              fit, test and write up

Writes research/outputs/signals/NOTICE_STEP.json and .md (counts and rates only), and the second
step fitted on every chunk and both years to research/outputs/lab/model_second_notice.txt with its
description beside it (lab_second_notice.json), which export_site_v5.py reads.
"""
import json
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import local_eval as LE  # noqa: E402
import notice_signals as NS  # noqa: E402
import screen_late as SL  # noqa: E402

PANEL, LAB, OUT = SL.PANEL, SL.LAB, SL.OUT
D = PANEL / "notice"
YEARS = (2017, 2018)
SEEDS = {7: f"{SL.CUR}@100", 8: f"{SL.CUR}@100~s8", 9: f"{SL.CUR}@100~s9"}
NAMES = [f"notice_{c}" for c in NS.COLS]
PAR = dict(objective="cross_entropy", learning_rate=0.05, num_leaves=8, min_data_in_leaf=100, lambda_l2=5.0, max_bin=63,
           verbose=-1, seed=7, num_threads=4)
ROUNDS = 150
MONTHS = [(1, 6), (7, 12), (13, 24), (25, 36), (37, 48)]
KIND = {"bk": "Bankruptcy order", "dec": "Deceased-estate notice"}
TEN = {"all": "All", "t0_9": "Under 10 years", "t10_19": "10 to 19 years", "t20p": "20 years or more"}
MEAS = {"year": "Sells in the calendar year", "later": "Completes July to June", "not_listed": "Completes July to June, not yet listed"}


def logit(p):
    p = np.clip(np.asarray(p, np.float64), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def first():
    """The deployed model's prediction (each of its fits) for the 2017 and 2018 rows of every chunk."""
    import model_lab as ML
    ch = ML.Chunks(PANEL); D.mkdir(exist_ok=True)
    for seed, name in SEEDS.items():
        if not (LAB / "models" / f"{name}.txt").exists():
            continue
        bst = lgb.Booster(model_file=str(LAB / "models" / f"{name}.txt"))
        cols, names = ch.cols(json.load(open(LAB / "preds" / f"{name}.json"))["families"])
        assert bst.feature_name() == names, "the saved model's columns do not match its families"
        for c in range(ch.n_chunks):
            f = D / f"p{seed}_{c}.npy"
            if not f.exists():
                r = ch.rows(c, YEARS)
                np.save(f, np.concatenate([bst.predict(ch.X(c).take(r[i:i + 250_000], cols), num_threads=4)
                                           for i in range(0, len(r), 250_000)]).astype("float32"))
                print(f"seed {seed} chunk {c}: {len(r):,} rows", flush=True)
        cached = np.load(LAB / "preds" / f"{name}.npy")                       # the lab's own figures for the test chunks
        yr = np.concatenate([ch.col("year", c)[ch.rows(c, (2017, 2019))] for c in (0, 1)])
        mine = np.concatenate([np.load(D / f"p{seed}_{c}.npy") for c in (0, 1)])
        assert np.allclose(cached[yr <= YEARS[1]], mine, atol=1e-5), "predictions differ from the lab's cache"
        print(f"seed {seed}: matches the lab's cache on the test chunks", flush=True)


def features():
    from panel2 import Panel, chunk_rows
    panel = Panel(SL.TX, verbose=False); N = NS.Notices(panel); D.mkdir(exist_ok=True)
    for c in range(len(json.load(open(PANEL / "meta.json"))["chunks"])):
        rows, years, label, _, _ = chunk_rows(panel, c)
        assert np.array_equal(label, np.load(PANEL / f"y_{c}.npy")), f"chunk {c}: rows are not in the stored order"
        m = (years >= YEARS[0]) & (years <= YEARS[1])
        X = N.features(rows[m], years[m]); np.save(D / f"N_{c}.npy", X)
        print(f"chunk {c}: {int(m.sum()):,} rows, with a notice " + ", ".join(
            f"{k} {int(np.isfinite(X[:, 3 * j]).sum()):,}" for j, k in enumerate(NS.KINDS)), flush=True)
    json.dump({"columns": NS.COLS, "window": NS.WINDOW, "when": time.strftime("%Y-%m-%d %H:%M"),
               "notices": {k: json.load(open(NS.DIRS[k] / "linked.json")) for k in NS.KINDS if (NS.DIRS[k] / "linked.json").exists()}},
              open(D / "features.json", "w"), indent=1)


def load():
    d = {k: [] for k in ("y", "late", "year", "tenure", "block", "district", "w", "chunk", "N")}
    n_chunks = len(json.load(open(PANEL / "meta.json"))["chunks"])
    P = {s: [] for s in SEEDS if all((D / f"p{s}_{c}.npy").exists() for c in range(n_chunks))}      # fits scored for every chunk
    for c in range(n_chunks):
        yr = np.load(PANEL / f"year_{c}.npy"); m = (yr >= YEARS[0]) & (yr <= YEARS[1])
        for k in ("y", "late", "year", "tenure", "block", "district", "w"):
            d[k].append(np.load(PANEL / f"{k}_{c}.npy")[m])
        d["chunk"].append(np.full(int(m.sum()), c, np.int8)); d["N"].append(np.load(D / f"N_{c}.npy"))
        for s in P:
            P[s].append(np.load(D / f"p{s}_{c}.npy"))
    d = {k: np.concatenate(v) for k, v in d.items()}
    assert len(d["N"]) == len(d["y"])
    return d, {s: np.concatenate(v).astype(np.float64) for s, v in P.items()}


def what_they_say(d, p, kinds):
    """The sale rate of homes with a notice against what the deployed model expected of the same homes."""
    rows = []
    w, y = d["w"].astype(np.float64), d["y"].astype(np.float64)
    for j, k in enumerate(NS.KINDS):
        if k not in kinds:
            continue
        mo, owned = d["N"][:, 3 * j], d["N"][:, 3 * j + 1]
        sets = [(f"{a} to {b} months before", (mo >= a) & (mo <= b) & (owned >= 0)) for a, b in MONTHS]
        sets.append(("Any time in the window, about an earlier owner", np.isfinite(mo) & (owned < 0)))
        for lab, m in sets:
            if m.sum() < 50:
                continue
            S, E, Nn = (np.bincount(d["block"][m], v[m], LE.N_BLOCKS) for v in (w * y, w * p, w))
            rng = np.random.default_rng(3); g = rng.poisson(1.0, (1000, LE.N_BLOCKS))
            rate, ratio = (g @ S) / (g @ Nn), (g @ S) / (g @ E)
            rows.append({"kind": k, "notice": lab, "rows": int(m.sum()), "home_years": round(float(Nn.sum())), "sold": round(float(S.sum())),
                         "rate": round(float(S.sum() / Nn.sum()), 4), "rate_range": [round(float(np.percentile(rate, q)), 4) for q in (2.5, 97.5)],
                         "model_said": round(float(E.sum() / Nn.sum()), 4), "times": round(float(S.sum() / E.sum()), 2),
                         "times_range": [round(float(np.percentile(ratio, q)), 2) for q in (2.5, 97.5)]})
            print(rows[-1], flush=True)
    return rows


def cols_of(kinds):
    return [3 * j + i for j, k in enumerate(NS.KINDS) if k in kinds for i in range(3)]


def fit(d, p, m, cols):
    return lgb.train(PAR, lgb.Dataset(d["N"][m][:, cols], d["y"][m].astype(np.float64), weight=d["w"][m], init_score=logit(p[m]),
                                      feature_name=[NAMES[i] for i in cols]), ROUNDS)


def cross_fit(d, p, cols):
    """Test chunks of each year scored by a second step fitted on the other chunks in the other year (log-odds)."""
    test = d["chunk"] < 2
    out = logit(p[test]); yt = d["year"][test]
    for a, b in ((2017, 2018), (2018, 2017)):
        bst = fit(d, p, ~test & (d["year"] == a), cols)
        te = yt == b
        out[te] += bst.predict(d["N"][test][te][:, cols], raw_score=True)
    return out


def main():
    d, P = load()
    info = json.load(open(D / "features.json"))
    kinds = [k for j, k in enumerate(NS.KINDS) if np.isfinite(d["N"][:, 3 * j]).sum() >= 500]
    print(f"{len(d['y']):,} rows; kinds with notices: {kinds}; first-step fits: {sorted(P)}", flush=True)
    said = what_they_say(d, P[7], kinds)
    w = d["w"].astype(np.float64)                     # the deployed model against the outcome, test homes and the rest
    calib = {lab: round(float((w[m] * d["y"][m]).sum() / (w[m] * P[7][m]).sum()), 4)
             for lab, m in (("test chunks", d["chunk"] < 2), ("other chunks", d["chunk"] >= 2))}
    print("sold against expected:", calib, flush=True)

    test = d["chunk"] < 2
    t = {k: d[k][test] for k in ("y", "year", "tenure", "block", "district")}
    tall = LE.load_test(PANEL); keep = tall["year"] <= YEARS[1]
    assert np.array_equal(tall["y"][keep], t["y"]) and np.array_equal(tall["block"][keep], t["block"]), "test rows are not aligned"
    ym = SL.end_ym()[keep]; frac = np.load(PANEL / "test_listed_after.npy").astype(np.float64)[keep]
    start = t["year"].astype(np.int64) * 12
    later = ((ym >= start + 6) & (ym < start + 18)).astype(np.float64)
    Y = {"year": t["y"].astype(np.float64), "later": later, "not_listed": later * frac}
    Nt = d["N"][test]

    sets = {"both": kinds} if len(kinds) > 1 else {}
    sets.update({k: [k] for k in kinds})
    main_arm = "both" if "both" in sets else kinds[0]
    arms = {}                                                           # seed -> arm -> score on the test rows
    for s, p in P.items():
        arms[s] = {"deployed": logit(p[test])}
        for a, ks in sets.items():
            if s == 7 or a == main_arm:
                arms[s][a] = cross_fit(d, p, cols_of(ks))
        print(f"seed {s}: second step fitted both ways", flush=True)

    R = {"when": time.strftime("%Y-%m-%d"), "first_step": SL.CUR, "columns": NAMES, "kinds": kinds, "window_months": NS.WINDOW,
         "rounds": ROUNDS, "seeds": sorted(P), "rows_fitted_on": int((~test).sum()), "rows_tested_on": int(test.sum()),
         "notices": info.get("notices"), "sold_against_expected": calib, "what_the_notices_say": said, "bands": {}}
    for nm, lo, hi in LE.TENURE:
        L = LE.Local(t, lo, hi); k = L.keep
        tops = {s: {a: L.top_mask(v[k]) for a, v in A.items()} for s, A in arms.items()}
        res = {}
        for meas, y in Y.items():
            L.y = y[k]
            r = {a: round(L.lift(tops[7][a]), 4) for a in tops[7]}
            for a in sets:
                per_seed = [L.lift(tops[s][a]) - L.lift(tops[s]["deployed"]) for s in tops if a in tops[s]]
                rng = np.random.default_rng(3); dd = []
                for _ in range(SL.BOOT):
                    w = rng.poisson(1.0, LE.N_BLOCKS).astype(float)[L.block]
                    dd.append(L.lift(tops[7][a], w) - L.lift(tops[7]["deployed"], w))
                lo_, hi_ = (float(np.percentile(dd, q)) for q in (2.5, 97.5))
                v = {"gain": round(per_seed[0], 4), "range": [round(lo_, 4), round(hi_, 4)], "by_seed": [round(x, 4) for x in per_seed]}
                if len(per_seed) >= 2:
                    sd = float(np.std(per_seed, ddof=1)); half = float(np.hypot((hi_ - lo_) / 2, 1.96 * sd)); mid = (lo_ + hi_) / 2
                    v["range_with_fit_noise"] = [round(mid - half, 4), round(mid + half, 4)]
                r[f"gain_{a}"] = v
            res[meas] = r
        R["bands"][nm] = res
        g = res["year"][f"gain_{main_arm}"]; n = res["not_listed"][f"gain_{main_arm}"]
        print(f"  {nm:6s} year: {res['year']['deployed']:.3f} to {res['year'][main_arm]:.3f}, {g['gain']:+.4f} "
              f"{g.get('range_with_fit_noise', g['range'])}; not yet listed {n['gain']:+.4f} {n.get('range_with_fit_noise', n['range'])}", flush=True)

    # the homes with a notice among the test homes: where they stood and where they stand now
    L = LE.Local(t); top0, top1 = L.top_mask(arms[7]["deployed"]), L.top_mask(arms[7][main_arm])
    p1 = 1 / (1 + np.exp(-arms[7][main_arm]))
    R["homes_with_a_notice"] = []
    for j, k in enumerate(NS.KINDS):
        if k not in kinds:
            continue
        mo, owned = Nt[:, 3 * j], Nt[:, 3 * j + 1]
        for lab, m in [(f"{a} to {b} months before", (mo >= a) & (mo <= b) & (owned >= 0)) for a, b in MONTHS] + \
                      [("Any, owner bought before it", np.isfinite(mo) & (owned >= 0))]:
            if m.sum() < 30:
                continue
            R["homes_with_a_notice"].append({
                "kind": k, "notice": lab, "home_years": int(m.sum()), "sold_in_year": round(float(Y["year"][m].mean()), 4),
                "sold_later_not_listed": round(float(Y["not_listed"][m].mean()), 4),
                "deployed_said": round(float(P[7][test][m].mean()), 4), "second_step_says": round(float(p1[m].mean()), 4),
                "in_best_tenth_before": round(float(top0[m].mean()), 3), "in_best_tenth_after": round(float(top1[m].mean()), 3)})
            print(R["homes_with_a_notice"][-1], flush=True)

    # is the chance of a sale better stated for the homes with a notice? Log loss on those test homes, before and after
    p0 = np.clip(P[7][test], 1e-6, 1 - 1e-6); yy = Y["year"]
    R["log_loss_with_a_notice"] = {}
    for a in sets:
        cols = cols_of(sets[a]); m = np.isfinite(Nt[:, cols[::3]]).any(axis=1)
        pa = np.clip(1 / (1 + np.exp(-arms[7][a])), 1e-6, 1 - 1e-6)
        ll = lambda p_: -(yy[m] * np.log(p_[m]) + (1 - yy[m]) * np.log(1 - p_[m]))      # noqa: E731
        dlt = ll(pa) - ll(p0); blk = t["block"][m]
        S, Nn = np.bincount(blk, dlt, LE.N_BLOCKS), np.bincount(blk, minlength=LE.N_BLOCKS)
        g = np.random.default_rng(3).poisson(1.0, (1000, LE.N_BLOCKS)); bs = (g @ S) / np.maximum(g @ Nn, 1)
        R["log_loss_with_a_notice"][a] = {
            "home_years": int(m.sum()), "sold": int(yy[m].sum()), "deployed_expected": round(float(p0[m].sum()), 1),
            "second_step_expected": round(float(pa[m].sum()), 1), "before": round(float(ll(p0).mean()), 5), "after": round(float(ll(pa).mean()), 5),
            "change": round(float(dlt.mean()), 5), "range": [round(float(np.percentile(bs, q)), 5) for q in (2.5, 97.5)]}
        print("log loss on homes with a notice,", a, R["log_loss_with_a_notice"][a], flush=True)

    A = R["bands"]["all"]; gy = A["year"][f"gain_{main_arm}"]; gn = A["not_listed"][f"gain_{main_arm}"]
    ry = gy.get("range_with_fit_noise", gy["range"]); LL = R["log_loss_with_a_notice"][main_arm]
    R["clear_of_zero"] = bool(ry[0] > 0)
    # the notices touch a few homes in a thousand, so the test of the step is whether those homes are better scored:
    # their log loss falls (whole range below zero) on homes and a year it was not fitted on, and no list gets worse
    R["passes"] = bool(LL["range"][1] < 0 and gy["gain"] >= 0 and gn["gain"] >= 0)
    R["verdict"] = (("add the notices: homes with a notice are scored better on homes and a year the step was not fitted on, and "
                     + ("the best tenth finds more sellers, clear of zero and of the fit's own noise" if R["clear_of_zero"] else
                        "the best tenth finds no fewer sellers (too few homes carry a notice to move it measurably)")) if R["passes"] else
                    "do not add the notices: homes with a notice are not clearly better scored")

    # the second step for the product: every chunk, both years, first step = the deployed fit
    cols = cols_of(kinds); allrows = np.ones(len(d["y"]), bool)
    bst = fit(d, P[7], allrows, cols)
    bst.save_model(str(LAB / "model_second_notice.txt"))
    g = bst.feature_importance("gain")
    R["gain_share"] = {n: round(float(v / max(g.sum(), 1e-9)), 3) for n, v in sorted(zip([NAMES[i] for i in cols], g), key=lambda kv: -kv[1])}
    blank = float(bst.predict(np.full((1, len(cols)), np.nan), raw_score=True)[0])
    R["shift_without_a_notice"] = round(blank, 4)
    json.dump({"first_step": SL.CUR, "label": "sells in the calendar year", "target": "year",
               "score": "log-odds = the first step's log-odds + this model's raw output",
               "columns": [NAMES[i] for i in cols], "row_families": ["NOTICE"], "kinds": kinds, "window_months": NS.WINDOW,
               "rounds": ROUNDS, "rows": int(len(d["y"])), "fitted_on": "every home-year of 2017 and 2018, first step fitted to 2015",
               "passes": R["passes"], "clear_of_zero": R["clear_of_zero"], "shift_without_a_notice": round(blank, 4),
               "lift_top10": {"deployed": A["year"]["deployed"], "with_notices": A["year"][main_arm]}},
              open(LAB / "lab_second_notice.json", "w"), indent=1)

    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(OUT / "NOTICE_STEP.json", "w"), indent=1)
    f = lambda v: (lambda q: f"{v['gain']:+.3f} ({q[0]:+.3f} to {q[1]:+.3f})")(v.get("range_with_fit_noise", v["range"]))   # noqa: E731
    pc = lambda x: f"{100 * x:.1f}%"                                    # noqa: E731
    md = ["# Notices in The Gazette: bankruptcy orders and deceased estates", "",
          f"**Verdict:** {R['verdict']}", "",
          "Homes are scored on 1 January. The deployed model is kept; a second step reads only the notice columns (months since",
          "the latest notice at the home, how long the home had been owned when it appeared, how many) and adds to the deployed",
          f"model's log-odds. Notices from the {NS.WINDOW} months before the scoring day count. Only the home and the month of",
          "publication are used; no name is held.", "",
          "## What the notices say on their own", "",
          "Every home-year of 2017 and 2018 with a notice, against what the deployed model expected of the same homes.", "",
          "| Notice | Published | Home-years | Sold in the year (95% range) | The model said | Times (95% range) |", "|---|---|---|---|---|---|"]
    md += [f"| {KIND[r['kind']]} | {r['notice']} | {r['home_years']:,} | {pc(r['rate'])} ({pc(r['rate_range'][0])} to {pc(r['rate_range'][1])}) | "
           f"{pc(r['model_said'])} | {r['times']:.2f} ({r['times_range'][0]:.2f} to {r['times_range'][1]:.2f}) |" for r in said]
    md += ["", "## Sellers found in the best tenth of each postcode district, times random", "",
           "Test homes of 2017 and 2018, each year scored by a second step fitted on other homes in the other year. Ranges are 95%",
           f"and include the spread of the gain over {len(P)} fits of the deployed model.", ""]
    for meas, title in MEAS.items():
        md += [f"### {title}", "", "| Owners | Deployed model | With the notices | Gain |" + "".join(f" {KIND[k]}s alone |" for k in kinds if len(kinds) > 1),
               "|---|---|---|---|" + "---|" * (len(kinds) if len(kinds) > 1 else 0)]
        for k_, lab in TEN.items():
            v = R["bands"][k_][meas]
            md.append(f"| {lab} | {v['deployed']:.3f} | {v[main_arm]:.3f} | {f(v[f'gain_{main_arm}'])} |"
                      + "".join(f" {f(v[f'gain_{k}'])} |" for k in kinds if len(kinds) > 1))
        md.append("")
    md += ["## The homes with a notice, among the test homes", "",
           "| Notice | Published | Home-years | Sold in the year | Sold later, not yet listed | Deployed model said | Second step says | "
           "In the best tenth before | After |", "|---|---|---|---|---|---|---|---|---|"]
    md += [f"| {KIND[r['kind']]} | {r['notice']} | {r['home_years']:,} | {pc(r['sold_in_year'])} | {pc(r['sold_later_not_listed'])} | "
           f"{pc(r['deployed_said'])} | {pc(r['second_step_says'])} | {100 * r['in_best_tenth_before']:.0f}% | {100 * r['in_best_tenth_after']:.0f}% |"
           for r in R["homes_with_a_notice"]]
    md += ["", "## Are the homes with a notice better scored?", "",
           "Log loss on the test homes with a notice (lower is better), each scored by a step fitted on other homes in the other year.", "",
           "| Notices | Home-years | Sold | Deployed model expected | Second step expected | Log loss before | After | Change (95% range) |",
           "|---|---|---|---|---|---|---|---|"]
    md += [f"| {'Both' if a == 'both' else KIND[a] + 's'} | {v['home_years']:,} | {v['sold']:,} | {v['deployed_expected']:,.0f} | {v['second_step_expected']:,.0f} | "
           f"{v['before']:.4f} | {v['after']:.4f} | {v['change']:+.4f} ({v['range'][0]:+.4f} to {v['range'][1]:+.4f}) |"
           for a, v in R["log_loss_with_a_notice"].items()]
    md += ["", f"A home with no notice moves by {blank:+.4f} in log-odds, the same for every such home, so its place in the ranking is unchanged.", ""]
    (OUT / "NOTICE_STEP.md").write_text("\n".join(md))
    print("\n".join(md))
    print(f"== {R['verdict']}", flush=True)


if __name__ == "__main__":
    {"first": first, "features": features}.get(sys.argv[1] if len(sys.argv) > 1 else "", main)()
