"""Bankruptcy orders and deceased-estate notices: a second step on the deployed model.

The notices (gazette_list.py, notice_signals.py) only reach back to 2012, so the deployed model,
fitted on 2001 to 2015, cannot be refitted with them. Instead the deployed model is kept as it is
and a small second model for each kind of notice reads that kind's columns and learns what to add
to the deployed model's log-odds. It is fitted only on homes with a notice and applied only to
them, so a home with no notice keeps its score exactly.

A notice touches a few homes in a thousand and the effect of a bankruptcy order is modest, so the
step is kept deliberately stiff (shallow trees, large leaves) and the number of rounds is chosen on
homes held out of the fit. Where held-out homes are not better predicted, it chooses none and the
kind adds nothing.

The test. Every home-year of 2017 and 2018 is used: the two test chunks (a tenth of homes, never
seen by the deployed model) and the other eighteen (homes it was fitted on up to 2015, here in
later years). Homes are split into five folds. Each fold in each year is scored by a step fitted on
the other four folds in the other year: different homes and a different year. Two questions:

  Are the homes with a notice better scored? Log loss on every home-year with a notice.
  Does the best tenth of each postcode district find more sellers? On the test chunks, on three
  measures: the calendar year (the deployed model's own target), sales completing between July and
  June, and those of them not yet listed on the scoring day (listed_truth.py).

    python notice_step.py first        the deployed model's prediction for every chunk's 2017 and 2018 rows (once)
    python notice_step.py features     the NOTICE columns for the same rows (again whenever more notices arrive)
    python notice_step.py              fit, test and write up

Writes research/outputs/signals/NOTICE_STEP.json and .md (counts and rates only), and the step
fitted on every home and both years to research/outputs/lab/model_second_notice_<kind>.txt with
its description (lab_second_notice.json), which export_site_v5.py reads.
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
PAR = dict(objective="cross_entropy", learning_rate=0.05, num_leaves=4, min_data_in_leaf=300, lambda_l2=20.0, max_bin=63,
           verbose=-1, seed=7, num_threads=4)
MAX_ROUNDS = 400
FOLDS = 5                                               # homes are split by chunk: fold = chunk % FOLDS
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


def cols_of(kind):
    j = NS.KINDS.index(kind)
    return [3 * j, 3 * j + 1, 3 * j + 2]


def rounds_for(X, y, w, init, block):
    """How many rounds predict homes held out of the fit best (four folds of homes). 0: none helps."""
    total = np.zeros(MAX_ROUNDS + 1)
    for f in range(4):
        va = block % 4 == f
        if va.sum() < 200 or y[va].sum() < 5:
            return 0
        tr = lgb.Dataset(X[~va], y[~va], weight=w[~va], init_score=init[~va])
        ev = {}
        lgb.train({**PAR, "metric": "cross_entropy"}, tr, MAX_ROUNDS,
                  valid_sets=[lgb.Dataset(X[va], y[va], weight=w[va], init_score=init[va], reference=tr)], valid_names=["v"],
                  callbacks=[lgb.record_evaluation(ev)])
        p0 = 1 / (1 + np.exp(-init[va]))
        base = float((w[va] * -(y[va] * np.log(p0) + (1 - y[va]) * np.log(1 - p0))).sum())
        total += np.concatenate([[base], np.array(ev["v"]["cross_entropy"]) * w[va].sum()])
    return int(np.argmin(total))


def fit(d, p, rows, kind):
    """The step for one kind of notice, fitted on the homes among `rows` that have one. None if it would not help."""
    cols = cols_of(kind)
    m = rows & np.isfinite(d["N"][:, cols[0]])
    if m.sum() < 1000:
        return None
    X, y, w, init = d["N"][m][:, cols], d["y"][m].astype(np.float64), d["w"][m].astype(np.float64), logit(p[m])
    n = rounds_for(X, y, w, init, d["block"][m].astype(np.int64))
    if n == 0:
        return None
    return lgb.train(PAR, lgb.Dataset(X, y, weight=w, init_score=init, feature_name=[NAMES[i] for i in cols]), n)


def add(d, models, rows):
    """What the steps add to the log-odds of `rows` (zero for a home with no notice)."""
    raw = np.zeros(int(rows.sum()))
    for kind, bst in models.items():
        if bst is None:
            continue
        X = d["N"][rows][:, cols_of(kind)]; m = np.isfinite(X[:, 0])
        if m.any():
            raw[m] += bst.predict(X[m], raw_score=True)
    return raw


def cross_fit(d, p, kinds):
    """Every home-year scored by steps fitted on the other folds of homes in the other year (log-odds)."""
    out = logit(p); fold = d["chunk"] % FOLDS; used = []
    for f in range(FOLDS):
        for a, b in ((2017, 2018), (2018, 2017)):
            models = {k: fit(d, p, (fold != f) & (d["year"] == a), k) for k in kinds}
            used.append({k: (m.num_trees() if m is not None else 0) for k, m in models.items()})
            te = (fold == f) & (d["year"] == b)
            out[te] += add(d, models, te)
    return out, used


def log_loss_change(d, p0, lp1, m):
    """Weighted log loss on rows m before and after, with a range from resampling blocks of homes."""
    y, w = d["y"][m].astype(np.float64), d["w"][m].astype(np.float64)
    a = np.clip(p0[m], 1e-6, 1 - 1e-6); b = np.clip(1 / (1 + np.exp(-lp1[m])), 1e-6, 1 - 1e-6)
    ll = lambda q: -(y * np.log(q) + (1 - y) * np.log(1 - q))            # noqa: E731
    blk = d["block"][m]
    S, W = np.bincount(blk, w * (ll(b) - ll(a)), LE.N_BLOCKS), np.bincount(blk, w, LE.N_BLOCKS)
    g = np.random.default_rng(3).poisson(1.0, (1000, LE.N_BLOCKS)); bs = (g @ S) / np.maximum(g @ W, 1)
    return {"rows": int(m.sum()), "home_years": round(float(w.sum())), "sold": round(float((w * y).sum())),
            "deployed_expected": round(float((w * a).sum())), "second_step_expected": round(float((w * b).sum())),
            "before": round(float((w * ll(a)).sum() / w.sum()), 5), "after": round(float((w * ll(b)).sum() / w.sum()), 5),
            "change": round(float(S.sum() / W.sum()), 5), "range": [round(float(np.percentile(bs, q)), 5) for q in (2.5, 97.5)]}


def main():
    d, P = load()
    info = json.load(open(D / "features.json"))
    kinds = [k for k in NS.KINDS if np.isfinite(d["N"][:, cols_of(k)[0]]).sum() >= 2000]
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

    sets = {"both": kinds} if len(kinds) > 1 else {}
    sets.update({k: [k] for k in kinds})
    main_arm = "both" if "both" in sets else kinds[0]
    arms, rounds = {}, {}                                               # seed -> arm -> score on every row
    for s, p in P.items():
        arms[s] = {"deployed": logit(p)}
        for a, ks in sets.items():
            if s == 7 or a == main_arm:
                arms[s][a], used = cross_fit(d, p, ks)
                if s == 7:
                    rounds[a] = used
        print(f"seed {s}: steps fitted for every fold and year", flush=True)
    R = {"when": time.strftime("%Y-%m-%d"), "first_step": SL.CUR, "columns": NAMES, "kinds": kinds, "window_months": NS.WINDOW,
         "seeds": sorted(P), "rows": int(len(d["y"])), "rows_in_test_chunks": int(test.sum()),
         "notices": info.get("notices"), "sold_against_expected": calib, "what_the_notices_say": said,
         "rounds_chosen": {k: sorted(u[k] for u in rounds[main_arm]) for k in kinds}, "bands": {}}
    print("rounds chosen in each fit:", R["rounds_chosen"], flush=True)

    # are the homes with a notice better scored?
    R["log_loss_with_a_notice"] = {}
    for a, ks in sets.items():
        m = np.zeros(len(d["y"]), bool)
        for k in ks:
            m |= np.isfinite(d["N"][:, cols_of(k)[0]])
        v = log_loss_change(d, P[7], arms[7][a], m)
        v["by_seed"] = [round(log_loss_change(d, P[s], arms[s][a], m)["change"], 5) for s in P if a in arms[s]]
        R["log_loss_with_a_notice"][a] = v
        print("log loss on homes with a notice,", a, v, flush=True)

    # the best tenth of each district, on the test chunks
    for nm, lo, hi in LE.TENURE:
        L = LE.Local(t, lo, hi); k = L.keep
        tops = {s: {a: L.top_mask(v[test][k]) for a, v in A.items()} for s, A in arms.items()}
        res = {}
        for meas, y in Y.items():
            L.y = y[k]
            r = {a: round(L.lift(tops[7][a]), 4) for a in tops[7]}
            for a in sets:
                per_seed = [L.lift(tops[s][a]) - L.lift(tops[s]["deployed"]) for s in tops if a in tops[s]]
                rng = np.random.default_rng(3); dd = []
                for _ in range(SL.BOOT):
                    wb = rng.poisson(1.0, LE.N_BLOCKS).astype(float)[L.block]
                    dd.append(L.lift(tops[7][a], wb) - L.lift(tops[7]["deployed"], wb))
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

    # the homes with a notice: what happened, what each ranking said (every home), and where they stand (test chunks)
    L = LE.Local(t); top0, top1 = L.top_mask(arms[7]["deployed"][test]), L.top_mask(arms[7][main_arm][test])
    p1 = 1 / (1 + np.exp(-arms[7][main_arm])); Nt = d["N"][test]
    R["homes_with_a_notice"] = []
    for k in kinds:
        j = cols_of(k)[0]
        mo, owned = d["N"][:, j], d["N"][:, j + 1]
        for lab, m in [(f"{a} to {b} months before", (mo >= a) & (mo <= b) & (owned >= 0)) for a, b in MONTHS] + \
                      [("Any, owner bought before it", np.isfinite(mo) & (owned >= 0)), ("Any, about an earlier owner", np.isfinite(mo) & (owned < 0))]:
            if m.sum() < 100:
                continue
            mt = m[test]; ww = w[m]
            R["homes_with_a_notice"].append({
                "kind": k, "notice": lab, "home_years": round(float(ww.sum())), "sold_in_year": round(float((ww * d["y"][m]).sum() / ww.sum()), 4),
                "deployed_said": round(float((ww * P[7][m]).sum() / ww.sum()), 4), "second_step_says": round(float((ww * p1[m]).sum() / ww.sum()), 4),
                "test_home_years": int(mt.sum()),
                "sold_later_not_listed": round(float(Y["not_listed"][mt].mean()), 4) if mt.sum() else None,
                "in_best_tenth_before": round(float(top0[mt].mean()), 3) if mt.sum() else None,
                "in_best_tenth_after": round(float(top1[mt].mean()), 3) if mt.sum() else None})
            print(R["homes_with_a_notice"][-1], flush=True)

    A = R["bands"]["all"]; gy = A["year"][f"gain_{main_arm}"]; gn = A["not_listed"][f"gain_{main_arm}"]
    ry = gy.get("range_with_fit_noise", gy["range"]); rn = gn.get("range_with_fit_noise", gn["range"])
    R["clear_of_zero"] = bool(ry[0] > 0)
    R["passes_by_kind"] = {k: bool(R["log_loss_with_a_notice"][k]["range"][1] < 0) for k in kinds}
    # the notices touch a few homes in a thousand, so the test of the step is whether those homes are better scored:
    # their log loss falls (whole range below zero) on homes and a year it was not fitted on, and no list gets clearly worse
    R["passes"] = bool(R["log_loss_with_a_notice"][main_arm]["range"][1] < 0 and ry[1] > 0 and rn[1] > 0)
    R["verdict"] = (("add the notices: homes with a notice are scored better on homes and a year the step was not fitted on, and "
                     + ("the best tenth finds more sellers, clear of zero and of the fit's own noise" if R["clear_of_zero"] else
                        "the best tenth is no worse (too few homes carry a notice to move it measurably)")) if R["passes"] else
                    "do not add the notices: homes with a notice are not clearly better scored")

    # the steps for the product: every home, both years, first step = the deployed fit; only the kinds that pass
    everyone = np.ones(len(d["y"]), bool); parts = []
    for k in kinds:
        f = LAB / f"model_second_notice_{k}.txt"
        bst = fit(d, P[7], everyone, k) if R["passes_by_kind"][k] else None
        if bst is None:
            f.unlink(missing_ok=True)
            continue
        bst.save_model(str(f)); parts.append({"kind": k, "file": f.name, "columns": [NAMES[i] for i in cols_of(k)], "rounds": bst.num_trees()})
    R["product"] = parts
    json.dump({"first_step": SL.CUR, "label": "sells in the calendar year", "target": "year",
               "score": "log-odds = the first step's log-odds + each part's raw output, for homes where the part's first column is present",
               "parts": parts, "columns": [c for q in parts for c in q["columns"]], "row_families": ["NOTICE"], "kinds": [q["kind"] for q in parts],
               "window_months": NS.WINDOW, "rows": int(len(d["y"])), "fitted_on": "every home-year of 2017 and 2018 with a notice, first step fitted to 2015",
               "passes": bool(R["passes"] and parts), "clear_of_zero": R["clear_of_zero"],
               "lift_top10": {"deployed": A["year"]["deployed"], "with_notices": A["year"][main_arm]}},
              open(LAB / "lab_second_notice.json", "w"), indent=1)

    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(OUT / "NOTICE_STEP.json", "w"), indent=1)
    f = lambda v: (lambda q: f"{v['gain']:+.3f} ({q[0]:+.3f} to {q[1]:+.3f})")(v.get("range_with_fit_noise", v["range"]))   # noqa: E731
    pc = lambda x: "" if x is None else f"{100 * x:.1f}%"               # noqa: E731
    whole = lambda x: "" if x is None else f"{100 * x:.0f}%"            # noqa: E731
    name = lambda a: "Both" if a == "both" else KIND[a] + "s"           # noqa: E731
    md = ["# Notices in The Gazette: bankruptcy orders and deceased estates", "",
          f"**Verdict:** {R['verdict']}", "",
          "Homes are scored on 1 January. The deployed model is kept; for each kind of notice a small second step reads the months",
          "since the latest notice at the home, how long the home had been owned when it appeared, and how many there were, and adds",
          f"to the deployed model's log-odds. Notices from the {NS.WINDOW} months before the scoring day count. Only the home and the",
          "month of publication are used; no name is held. A home with no notice keeps its score exactly.", "",
          "## What the notices say on their own", "",
          "Every home-year of 2017 and 2018 with a notice, against what the deployed model expected of the same homes.", "",
          "| Notice | Published | Home-years | Sold in the year (95% range) | The model said | Times (95% range) |", "|---|---|---|---|---|---|"]
    md += [f"| {KIND[r['kind']]} | {r['notice']} | {r['home_years']:,} | {pc(r['rate'])} ({pc(r['rate_range'][0])} to {pc(r['rate_range'][1])}) | "
           f"{pc(r['model_said'])} | {r['times']:.2f} ({r['times_range'][0]:.2f} to {r['times_range'][1]:.2f}) |" for r in said]
    md += ["", "## Are the homes with a notice better scored?", "",
           "Log loss on every home-year with a notice (lower is better), each scored by a step fitted on other homes in the other year.", "",
           "| Notices | Home-years | Sold | Deployed model expected | Second step expected | Log loss before | After | Change (95% range) |",
           "|---|---|---|---|---|---|---|---|"]
    md += [f"| {name(a)} | {v['home_years']:,} | {v['sold']:,} | {v['deployed_expected']:,} | {v['second_step_expected']:,} | "
           f"{v['before']:.4f} | {v['after']:.4f} | {v['change']:+.4f} ({v['range'][0]:+.4f} to {v['range'][1]:+.4f}) |"
           for a, v in R["log_loss_with_a_notice"].items()]
    md += ["", "## Sellers found in the best tenth of each postcode district, times random", "",
           f"Test homes of 2017 and 2018. Ranges are 95% and include the spread of the gain over {len(P)} fits of the deployed model.", ""]
    for meas, title in MEAS.items():
        md += [f"### {title}", "", "| Owners | Deployed model | With the notices | Gain |" + "".join(f" {KIND[k]}s alone |" for k in kinds if len(kinds) > 1),
               "|---|---|---|---|" + "---|" * (len(kinds) if len(kinds) > 1 else 0)]
        for k_, lab in TEN.items():
            v = R["bands"][k_][meas]
            md.append(f"| {lab} | {v['deployed']:.3f} | {v[main_arm]:.3f} | {f(v[f'gain_{main_arm}'])} |"
                      + "".join(f" {f(v[f'gain_{k}'])} |" for k in kinds if len(kinds) > 1))
        md.append("")
    md += ["## The homes with a notice", "",
           "The first four columns are every home; the last three are the test homes alone.", "",
           "| Notice | Published | Home-years | Sold in the year | Deployed model said | Second step says | Sold later, not yet listed | "
           "In the best tenth before | After |", "|---|---|---|---|---|---|---|---|---|"]
    md += [f"| {KIND[r['kind']]} | {r['notice']} | {r['home_years']:,} | {pc(r['sold_in_year'])} | {pc(r['deployed_said'])} | {pc(r['second_step_says'])} | "
           f"{pc(r['sold_later_not_listed'])} | {whole(r['in_best_tenth_before'])} | {whole(r['in_best_tenth_after'])} |"
           for r in R["homes_with_a_notice"]]
    md += ["", "Rounds chosen for each fit (0 means the kind added nothing in that fit): "
           + "; ".join(f"{KIND[k].lower()}s {', '.join(str(x) for x in v)}" for k, v in R["rounds_chosen"].items()) + ".",
           "In the product: " + (", ".join(f"{KIND[q['kind']].lower()}s ({q['rounds']} rounds)" for q in parts) or "none") + ".", ""]
    (OUT / "NOTICE_STEP.md").write_text("\n".join(md))
    print("\n".join(md))
    print(f"== {R['verdict']}", flush=True)


if __name__ == "__main__":
    {"first": first, "features": features}.get(sys.argv[1] if len(sys.argv) > 1 else "", main)()
