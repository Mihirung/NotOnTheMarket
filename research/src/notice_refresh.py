"""What reading notices mid-year would add: a test, not a change to the product.

The product scores homes once a year, on 1 January, so a notice waits up to twelve months to be read
and notice_timing.py shows most of its worth is gone by then. Here the scores are refreshed once, on
1 July. Homes sold January to June leave the ranking (the sale is on record by then) and the target
is a sale completing July to June. Everything else is as in notice_step.py: the first step is the
deployed model as fitted to 2015 with its January figure, and each home-year is scored by notice
steps fitted on the other folds of homes in the other year. The arms:

  deployed          the January figure alone
  january_as_now    plus the notice step as deployed: notices to 31 December, fitted to calendar-year sales
  january           plus a notice step on notices to 31 December, fitted to July-to-June sales
  july              plus a notice step on notices to 30 June, fitted to July-to-June sales

A second measure counts only sales completing October to June, three months or more after the
refresh, which leaves out most homes already under offer on 1 July.

    python notice_refresh.py

Writes research/outputs/signals/NOTICE_REFRESH.json and .md. Counts and rates only.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import local_eval as LE  # noqa: E402
import notice_signals as NS  # noqa: E402
import notice_step as ST  # noqa: E402
import screen_late as SL  # noqa: E402

OUT = SL.OUT
SHIFT = 6                                               # months after 1 January that the scores are refreshed
LABELS = {"july_to_june": "Completes July to June", "october_to_june": "Completes October to June"}


def features_at(N, rows, years, shift):
    """notice_signals.Notices.features, read `shift` months after 1 January of each year."""
    p = N.panel
    t0 = np.asarray(years, np.int64) * 12 + shift
    bought = p.year[rows].astype(np.int64) * 12 + p.month[rows] - 1
    out = np.full((len(rows), len(NS.COLS)), np.nan, np.float32)
    for j, k in enumerate(NS.KINDS):
        if k not in N.ev:
            continue
        homes, comp = N.ev[k]
        g = np.searchsorted(homes, p.key[rows]); g[g == len(homes)] = 0
        has = homes[g] == p.key[rows]
        base = g.astype(np.int64) * NS.M
        hi = np.searchsorted(comp, base + t0, side="left")
        lo = np.searchsorted(comp, base + t0 - NS.WINDOW, side="left")
        n = np.where(has, hi - lo, 0); ok = n > 0
        last = comp[np.maximum(hi - 1, 0)] - base
        out[ok, 3 * j] = (t0 - last)[ok]; out[ok, 3 * j + 1] = (last - bought)[ok]; out[ok, 3 * j + 2] = n[ok]
    return out


def both_readings():
    """The notices at every home-year of the two years, read on 1 January and on 1 July, from the same notices on disk."""
    from panel2 import Panel, chunk_rows
    panel = Panel(SL.TX, verbose=False); N = NS.Notices(panel)
    a, b = [], []
    for c in range(len(json.load(open(SL.PANEL / "meta.json"))["chunks"])):
        rows, years, _, _, _ = chunk_rows(panel, c)
        m = (years >= ST.YEARS[0]) & (years <= ST.YEARS[1])
        a.append(features_at(N, rows[m], years[m], 0)); b.append(features_at(N, rows[m], years[m], SHIFT))
        print(f"chunk {c}: {int(m.sum()):,} rows", flush=True)
    return np.concatenate(a), np.concatenate(b)


def cross(d, p, kinds, ok):
    """notice_step.cross_fit, fitted only on the rows in `ok`."""
    out = ST.logit(p); fold = d["chunk"] % ST.FOLDS
    for f in range(ST.FOLDS):
        for a, b in ((ST.YEARS[0], ST.YEARS[1]), (ST.YEARS[1], ST.YEARS[0])):
            models = {k: ST.fit(d, p, (fold != f) & (d["year"] == a) & ok, k) for k in kinds}
            te = (fold == f) & (d["year"] == b)
            out[te] += ST.add(d, models, te)
    return out


def main():
    N0, N6 = both_readings()
    d, P = ST.load(); p = P[7]
    assert len(N0) == len(d["y"]), "the notices are not aligned with the stored rows"
    kinds = [k for k in NS.KINDS if np.isfinite(N0[:, ST.cols_of(k)[0]]).sum() >= 2000]
    late, w = d["late"].astype(np.float64), d["w"].astype(np.float64)
    there = ~((d["y"] == 1) & (d["late"] == 0))                 # not sold January to June: still there on 1 July
    lo, hi = -3.0, 3.0                                          # move the first step to the July-to-June rate of those homes
    for _ in range(60):
        c = (lo + hi) / 2
        if (w[there] / (1 + np.exp(-(ST.logit(p[there]) + c)))).sum() > (w[there] * late[there]).sum():
            hi = c
        else:
            lo = c
    pc_ = 1 / (1 + np.exp(-(ST.logit(p) + c)))
    arms = {"deployed": ST.logit(pc_),
            "january_as_now": ST.cross_fit({**d, "N": N0}, p, kinds)[0],
            "january": cross({**d, "N": N0, "y": late}, pc_, kinds, there),
            "july": cross({**d, "N": N6, "y": late}, pc_, kinds, there)}
    print("steps fitted", flush=True)

    test = d["chunk"] < 2
    tall = LE.load_test(SL.PANEL); keep = tall["year"] <= ST.YEARS[1]
    assert np.array_equal(tall["y"][keep], d["y"][test]), "test rows are not aligned"
    ym = SL.end_ym()[keep]; start = d["year"][test].astype(np.int64) * 12
    assert np.array_equal((ym >= start + 6) & (ym < start + 18), d["late"][test].astype(bool))
    m = there[test]
    Y = {"july_to_june": late[test][m], "october_to_june": ((ym >= start + 9) & (ym < start + 18))[m].astype(np.float64)}
    R = {"years": list(ST.YEARS), "refreshed_months_after_1_january": SHIFT, "kinds": kinds, "home_years": int(len(p)),
         "test_home_years": int(test.sum()), "test_home_years_still_there_on_1_july": int(m.sum()), "measures": {}, "homes_with_a_notice_on_1_july": []}
    rng = np.random.default_rng(5); draws = [rng.poisson(1.0, LE.N_BLOCKS).astype("float64") for _ in range(LE.BOOT)]
    t = {k: d[k][test][m] for k in ("year", "tenure", "block", "district")}
    for lab, yy in Y.items():
        R["measures"][lab] = {}
        for name, a, b in LE.TENURE:
            band = LE.Local({**t, "y": yy}, a, b)
            tops = {arm: band.top_mask(v[test][m][band.keep]) for arm, v in arms.items()}
            row = {arm: round(band.lift(tp), 4) for arm, tp in tops.items()}
            for arm, base in (("july", "january"), ("july", "deployed"), ("january", "deployed")):
                dd = [band.lift(tops[arm], g[band.block]) - band.lift(tops[base], g[band.block]) for g in draws]
                row[f"{arm}_minus_{base}"] = [round(row[arm] - row[base], 4)] + [round(float(np.percentile(dd, q)), 4) for q in (2.5, 97.5)]
            R["measures"][lab][name] = row
            print(lab, name, row, flush=True)

    L = LE.Local({**t, "y": Y["july_to_june"]}); top = {arm: L.top_mask(v[test][m]) for arm, v in arms.items()}
    said = {arm: 1 / (1 + np.exp(-arms[arm][test][m])) for arm in ("deployed", "july")}
    X = N6[test][m]
    for j, k in enumerate(NS.KINDS):
        if k not in kinds:
            continue
        mo, owned = X[:, 3 * j], X[:, 3 * j + 1]
        sets = [(f"{a} to {b} months before", (mo >= a) & (mo <= b) & (owned >= 0)) for a, b in ST.MONTHS]
        sets += [("Any time in the window, about an earlier owner", np.isfinite(mo) & (owned < 0)), ("Every home with one", np.isfinite(mo))]
        for lab, s in sets:
            if s.sum() >= 30:
                R["homes_with_a_notice_on_1_july"].append({
                    "kind": k, "notice": lab, "homes": int(s.sum()), "completes_july_to_june": round(float(Y["july_to_june"][s].mean()), 4),
                    "completes_october_to_june": round(float(Y["october_to_june"][s].mean()), 4),
                    "deployed_said": round(float(said["deployed"][s].mean()), 4), "july_step_says": round(float(said["july"][s].mean()), 4),
                    "best_tenth_january": round(float(top["january"][s].mean()), 3), "best_tenth_july": round(float(top["july"][s].mean()), 3)})
                print(R["homes_with_a_notice_on_1_july"][-1], flush=True)

    pc = lambda x: f"{100 * x:.1f}%"                                    # noqa: E731
    ch = lambda v: f"{v[0]:+.3f} ({v[1]:+.3f} to {v[2]:+.3f})"          # noqa: E731
    md = ["# What reading notices mid-year would add", "",
          "A test, not a change to the product. The product scores homes once a year, on 1 January. Here the scores are refreshed",
          "once, on 1 July: homes sold January to June leave the ranking and the notice step reads notices published up to 30 June.",
          f"The years are {ST.YEARS[0]} and {ST.YEARS[1]}, the homes are the test chunks' ({R['test_home_years_still_there_on_1_july']:,} home-years still",
          "there on 1 July), and each is scored by notice steps fitted on other homes in the other year. Figures are sellers found in",
          "the best tenth of each postcode district, times random.", ""]
    for lab, name in LABELS.items():
        md += [f"## {name}", "",
               "| Owned for | No notices | Notices to 31 December | Notices to 30 June | June against December (95% range) | June against none |",
               "|---|---|---|---|---|---|"]
        md += [f"| {ST.TEN[tn]} | {v['deployed']:.3f} | {v['january']:.3f} | {v['july']:.3f} | {ch(v['july_minus_january'])} | {ch(v['july_minus_deployed'])} |"
               for tn, v in R["measures"][lab].items()]
        md.append("")
    md += ["## The homes with a notice on 1 July", "",
           "| Notice | Published before 1 July | Homes | Completes July to June | Completes October to June | Deployed model said | "
           "July step says | In the best tenth on January's notices | On June's |", "|---|---|---|---|---|---|---|---|---|"]
    md += [f"| {ST.KIND[r['kind']]} | {r['notice']} | {r['homes']:,} | {pc(r['completes_july_to_june'])} | {pc(r['completes_october_to_june'])} | "
           f"{pc(r['deployed_said'])} | {pc(r['july_step_says'])} | {100 * r['best_tenth_january']:.0f}% | {100 * r['best_tenth_july']:.0f}% |"
           for r in R["homes_with_a_notice_on_1_july"]]
    md += ["", "## Reading it", "",
           "A notice published January to June is invisible to a January score until the next January. Read on 1 July it is one to",
           "six months old, which is when it says most. One refresh a year is the least that could be tested here; a monthly refresh",
           "would read every notice within a month of publication.", ""]
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(OUT / "NOTICE_REFRESH.json", "w"), indent=1)
    (OUT / "NOTICE_REFRESH.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
