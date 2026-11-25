"""The notice step for the model aimed at homes not yet on the market.

notice_step.py fits the step that adds the Gazette notices to the model of sales in the calendar year.
This fits the same step for the model the site scores with once it is aimed at later sales: the first
step is the later-sales model with energy certificates (LATE_MODEL.md), and the step is fitted to the
same target, a sale completing between July of the year and June of the next. Everything else is as in
notice_step.py: one small stiff model for each kind of notice, added to the first step's log-odds for
the homes that have one, each home-year scored by steps fitted on the other folds of homes in the other
year.

    python notice_step_late.py first      the first step's figure for every home-year of 2017 and 2018 (once)
    python notice_step_late.py            fit, test and write up

Writes research/outputs/signals/NOTICE_STEP_LATE.json and .md (counts and rates only), and for the
product research/outputs/lab/model_second_notice_late_<kind>.txt and lab_second_notice_late.json.
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
import notice_step as ST  # noqa: E402
import screen_late as SL  # noqa: E402

PANEL, LAB, OUT, D = SL.PANEL, SL.LAB, SL.OUT, ST.D
FIRST = f"{SL.CUR}+EPC@100~late"                         # the later-sales model with certificates, fitted to 2015
MEAS = {"later": "Completes July to June", "not_listed": "Completes July to June, not yet listed", "year": "Sells in the calendar year"}


def first():
    """The first step's prediction for the 2017 and 2018 rows of every chunk."""
    import model_lab as ML
    ch = ML.Chunks(PANEL); D.mkdir(exist_ok=True)
    bst = lgb.Booster(model_file=str(LAB / "models" / f"{FIRST}.txt"))
    cols, names = ch.cols(json.load(open(LAB / "preds" / f"{FIRST}.json"))["families"])
    assert bst.feature_name() == names, "the saved model's columns do not match its families"
    for c in range(ch.n_chunks):
        f = D / f"pl_{c}.npy"
        if not f.exists():
            r = ch.rows(c, ST.YEARS)
            np.save(f, np.concatenate([bst.predict(ch.X(c).take(r[i:i + 250_000], cols), num_threads=4)
                                       for i in range(0, len(r), 250_000)]).astype("float32"))
            print(f"chunk {c}: {len(r):,} rows", flush=True)
    cached = np.load(LAB / "preds" / f"{FIRST}.npy")                          # the lab's own figures for the test chunks
    yr = np.concatenate([ch.col("year", c)[ch.rows(c, (2017, 2019))] for c in (0, 1)])
    mine = np.concatenate([np.load(D / f"pl_{c}.npy") for c in (0, 1)])
    assert np.allclose(cached[yr <= ST.YEARS[1]], mine, atol=1e-5), "predictions differ from the lab's cache"
    print("matches the lab's cache on the test chunks", flush=True)


def auc(y, p):
    o = np.argsort(p, kind="stable"); r = np.empty(len(p)); r[o] = np.arange(1, len(p) + 1)
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def main():
    d, _ = ST.load()
    n_chunks = len(json.load(open(PANEL / "meta.json"))["chunks"])
    p = np.concatenate([np.load(D / f"pl_{c}.npy") for c in range(n_chunks)]).astype(np.float64)
    assert len(p) == len(d["y"]), "run `python notice_step_late.py first`"
    d = {**d, "cal": d["y"], "y": d["late"]}                                 # every fit below is to the later sale
    kinds = [k for k in NS.KINDS if np.isfinite(d["N"][:, ST.cols_of(k)[0]]).sum() >= 2000]
    w = d["w"].astype(np.float64)
    calib = round(float((w * d["y"]).sum() / (w * p).sum()), 4)
    print(f"{len(p):,} rows; kinds {kinds}; sold later against expected {calib}", flush=True)

    test = d["chunk"] < 2
    t = {k: d[k][test] for k in ("year", "tenure", "block", "district")}
    tall = LE.load_test(PANEL); keep = tall["year"] <= ST.YEARS[1]
    assert np.array_equal(tall["y"][keep], d["cal"][test]) and np.array_equal(tall["block"][keep], t["block"]), "test rows are not aligned"
    frac = np.load(PANEL / "test_listed_after.npy").astype(np.float64)[keep]
    later = d["late"][test].astype(np.float64)
    Y = {"later": later, "not_listed": later * frac, "year": d["cal"][test].astype(np.float64)}

    sets = {"both": kinds} if len(kinds) > 1 else {}
    sets.update({k: [k] for k in kinds})
    main_arm = "both" if "both" in sets else kinds[0]
    arms, rounds = {"first_step": ST.logit(p)}, {}
    for a, ks in sets.items():
        arms[a], rounds[a] = ST.cross_fit(d, p, ks)
    print("steps fitted for every fold and year", flush=True)
    R = {"when": time.strftime("%Y-%m-%d"), "first_step": FIRST, "target": "late", "kinds": kinds, "window_months": NS.WINDOW,
         "rows": int(len(p)), "sold_later_against_expected": calib,
         "rounds_chosen": {k: sorted(u[k] for u in rounds[main_arm]) for k in kinds}, "log_loss_with_a_notice": {}, "bands": {}}
    for a, ks in sets.items():
        m = np.zeros(len(p), bool)
        for k in ks:
            m |= np.isfinite(d["N"][:, ST.cols_of(k)[0]])
        R["log_loss_with_a_notice"][a] = ST.log_loss_change(d, p, arms[a], m)
        print("log loss on homes with a notice,", a, R["log_loss_with_a_notice"][a], flush=True)

    rng = np.random.default_rng(3); draws = [rng.poisson(1.0, LE.N_BLOCKS).astype(float) for _ in range(SL.BOOT)]
    for nm, lo, hi in LE.TENURE:
        res = {}
        for meas, y in Y.items():
            L = LE.Local({**t, "y": y}, lo, hi)
            tops = {a: L.top_mask(v[test][L.keep]) for a, v in arms.items()}
            r = {a: round(L.lift(tp), 4) for a, tp in tops.items()}
            for a in sets:
                dd = [L.lift(tops[a], g[L.block]) - L.lift(tops["first_step"], g[L.block]) for g in draws]
                r[f"gain_{a}"] = [round(r[a] - r["first_step"], 4)] + [round(float(np.percentile(dd, q)), 4) for q in (2.5, 97.5)]
            res[meas] = r
        R["bands"][nm] = res
        print(nm, json.dumps(res["later"]), flush=True)
    A = R["bands"]["all"]
    R["auc_later"] = {"first_step": round(auc(later, arms["first_step"][test]), 4), "with_notices": round(auc(later, arms[main_arm][test]), 4)}

    # the homes with a notice: what happened and what each ranking said (every home), and where they stand (test chunks)
    L = LE.Local({**t, "y": later}); top0, top1 = L.top_mask(arms["first_step"][test]), L.top_mask(arms[main_arm][test])
    p1 = 1 / (1 + np.exp(-arms[main_arm])); R["homes_with_a_notice"] = []
    for k in kinds:
        j = ST.cols_of(k)[0]; mo, owned = d["N"][:, j], d["N"][:, j + 1]
        for lab, m in [(f"{a} to {b} months before", (mo >= a) & (mo <= b) & (owned >= 0)) for a, b in ST.MONTHS] + \
                      [("Any, owner bought before it", np.isfinite(mo) & (owned >= 0)), ("Any, about an earlier owner", np.isfinite(mo) & (owned < 0))]:
            if m.sum() < 100:
                continue
            mt = m[test]; ww = w[m]
            R["homes_with_a_notice"].append({
                "kind": k, "notice": lab, "home_years": round(float(ww.sum())), "sold_later": round(float((ww * d["y"][m]).sum() / ww.sum()), 4),
                "first_step_said": round(float((ww * p[m]).sum() / ww.sum()), 4), "with_the_step": round(float((ww * p1[m]).sum() / ww.sum()), 4),
                "in_best_tenth_before": round(float(top0[mt].mean()), 3) if mt.sum() else None,
                "in_best_tenth_after": round(float(top1[mt].mean()), 3) if mt.sum() else None})
            print(R["homes_with_a_notice"][-1], flush=True)

    g = A["later"][f"gain_{main_arm}"]; gn = A["not_listed"][f"gain_{main_arm}"]
    R["clear_of_zero"] = bool(g[1] > 0)
    R["passes_by_kind"] = {k: bool(R["log_loss_with_a_notice"][k]["range"][1] < 0) for k in kinds}
    # as in notice_step.py: the homes with a notice are better scored, and neither list gets clearly worse
    R["passes"] = bool(R["log_loss_with_a_notice"][main_arm]["range"][1] < 0 and g[2] > 0 and gn[2] > 0)
    everyone = np.ones(len(p), bool); parts = []
    for k in kinds:
        f = LAB / f"model_second_notice_late_{k}.txt"
        bst = ST.fit(d, p, everyone, k) if R["passes_by_kind"][k] else None
        if bst is None:
            f.unlink(missing_ok=True)
            continue
        bst.save_model(str(f)); parts.append({"kind": k, "file": f.name, "columns": [ST.NAMES[i] for i in ST.cols_of(k)], "rounds": bst.num_trees()})
    R["product"] = parts
    # what the product's ranking is: the arm with exactly the kinds that passed
    passed = [q["kind"] for q in parts]
    prod = main_arm if passed == kinds else passed[0] if len(passed) == 1 else None
    if prod:
        R["auc_later"]["with_notices"] = round(auc(later, arms[prod][test]), 4)
    R["product_ranking"] = {"kinds": passed, "later": A["later"][prod] if prod else A["later"]["first_step"],
                            "gain": A["later"][f"gain_{prod}"] if prod else None}
    json.dump({"first_step": FIRST, "label": "the sale completes six to eighteen months after the scoring day", "target": "late",
               "score": "log-odds = the first step's log-odds + each part's raw output, for homes where the part's first column is present",
               "parts": parts, "columns": [c for q in parts for c in q["columns"]], "row_families": ["NOTICE"], "kinds": [q["kind"] for q in parts],
               "window_months": NS.WINDOW, "rows": int(len(p)), "fitted_on": "every home-year of 2017 and 2018 with a notice, first step fitted to 2015",
               "passes": bool(R["passes"] and parts), "clear_of_zero": R["clear_of_zero"], "auc_later": R["auc_later"],
               "lift_top10": {"deployed": A["later"]["first_step"], "with_notices": R["product_ranking"]["later"]}},
              open(LAB / "lab_second_notice_late.json", "w"), indent=1)

    pc = lambda x: "" if x is None else f"{100 * x:.1f}%"               # noqa: E731
    whole = lambda x: "" if x is None else f"{100 * x:.0f}%"            # noqa: E731
    ch = lambda v: f"{v[0]:+.3f} ({v[1]:+.3f} to {v[2]:+.3f})"          # noqa: E731
    name = lambda a: "Both" if a == "both" else ST.KIND[a] + "s"        # noqa: E731
    md = ["# The notice step for the model aimed at homes not yet on the market", "",
          "**Verdict:** " + ("add the notices: homes with a notice are scored better on homes and a year the step was not fitted on"
                             + (", and the best tenth finds more later sellers, clear of zero" if R["clear_of_zero"] else
                                ", and the best tenth is no worse") if R["passes"] else "do not add the notices to this model"), "",
          "Homes are scored on 1 January by the later-sales model with energy certificates (LATE_MODEL.md). A later seller completes",
          "between July of that year and June of the next. For each kind of notice a small second step reads the months since the",
          "latest notice at the home, how long the home had been owned when it appeared, and how many there were, and adds to the",
          f"first step's log-odds. Test homes of {ST.YEARS[0]} and {ST.YEARS[1]}; each home-year is scored by a step fitted on other homes in the other year.", "",
          "## Are the homes with a notice better scored?", "",
          "| Notices | Home-years | Sold later | First step expected | With the step | Log loss before | After | Change (95% range) |", "|---|---|---|---|---|---|---|---|"]
    md += [f"| {name(a)} | {v['home_years']:,} | {v['sold']:,} | {v['deployed_expected']:,} | {v['second_step_expected']:,} | "
           f"{v['before']:.4f} | {v['after']:.4f} | {v['change']:+.4f} ({v['range'][0]:+.4f} to {v['range'][1]:+.4f}) |"
           for a, v in R["log_loss_with_a_notice"].items()]
    md += ["", "## Sellers found in the best tenth of each postcode district, times random", ""]
    for meas, title in MEAS.items():
        md += [f"### {title}", "", "| Owners | First step | With the notices | Gain (95% range) |" + "".join(f" {ST.KIND[k]}s alone |" for k in kinds if len(kinds) > 1),
               "|---|---|---|---|" + "---|" * (len(kinds) if len(kinds) > 1 else 0)]
        for k_, lab in ST.TEN.items():
            v = R["bands"][k_][meas]
            md.append(f"| {lab} | {v['first_step']:.3f} | {v[main_arm]:.3f} | {ch(v[f'gain_{main_arm}'])} |"
                      + "".join(f" {ch(v[f'gain_{k}'])} |" for k in kinds if len(kinds) > 1))
        md.append("")
    md += ["## The homes with a notice", "",
           "| Notice | Published | Home-years | Sold later | First step said | With the step | In the best tenth before | After |", "|---|---|---|---|---|---|---|---|"]
    md += [f"| {ST.KIND[r['kind']]} | {r['notice']} | {r['home_years']:,} | {pc(r['sold_later'])} | {pc(r['first_step_said'])} | {pc(r['with_the_step'])} | "
           f"{whole(r['in_best_tenth_before'])} | {whole(r['in_best_tenth_after'])} |" for r in R["homes_with_a_notice"]]
    left = [ST.KIND[k].lower() + "s" for k in kinds if k not in passed]
    md += ["", "In the product: " + (", ".join(f"{ST.KIND[q['kind']].lower()}s ({q['rounds']} rounds)" for q in parts) or "none") + "."
           + (f" Left out, because the homes that have one are not better scored on this target: {', '.join(left)}." if left else "")
           + (f" With what is in, the best tenth finds {R['product_ranking']['later']:.3f} times random." if prod else ""), ""]
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(OUT / "NOTICE_STEP_LATE.json", "w"), indent=1)
    (OUT / "NOTICE_STEP_LATE.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    {"first": first}.get(sys.argv[1] if len(sys.argv) > 1 else "", main)()
