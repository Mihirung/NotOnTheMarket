"""What refreshing the scores every month would add: a test, not a change to the product.

notice_refresh.py asked what one extra refresh on 1 July would add. This asks the same of the first
of every month. On that day the homes sold since 1 January leave the ranking, and the target is a
sale completing in the twelve months that follow. Three rankings are compared:

  deployed    the January figure alone
  january     plus a notice step that reads notices to 31 December: the product, scored once a year
  monthly     plus a notice step that reads notices to the end of the month before: refreshed monthly

Everything else is as in notice_step.py: the first step is the deployed model as fitted to 2015, and
each home-year is scored by notice steps fitted on the other folds of homes in the other year. The
first step keeps its January figure in every arm (moved by a constant to the rate of the homes still
there), so the figures show what the notices alone gain from being read sooner. Sales after December
2019 are not on record and 2019 undercounts late registrations; that lowers the later months' rates
in every arm alike.

    python notice_monthly.py            about 40 minutes
    python notice_monthly.py report     the write-up again, from the figures on disk

Writes research/outputs/signals/NOTICE_MONTHLY.json and .md. Counts and rates only.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import local_eval as LE  # noqa: E402
import notice_refresh as NR  # noqa: E402
import notice_signals as NS  # noqa: E402
import notice_step as ST  # noqa: E402
import screen_late as SL  # noqa: E402

OUT = SL.OUT
MONTH = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
BANDS = [b for b in LE.TENURE if b[0] in ("all", "t20p")]


def rows_and_sales():
    """Every home-year of the two years in the stored order: its row, its year and the month its spell ended in a sale (0 if never)."""
    from panel2 import Panel, chunk_rows
    panel = Panel(SL.TX, verbose=False); N = NS.Notices(panel)
    R, Y, E = [], [], []
    for c in range(len(json.load(open(SL.PANEL / "meta.json"))["chunks"])):
        rows, years, _, _, _ = chunk_rows(panel, c)
        m = (years >= ST.YEARS[0]) & (years <= ST.YEARS[1])
        r = rows[m]; nxt = np.minimum(r + 1, len(panel.month) - 1)          # rows are sorted by home, then date
        R.append(r); Y.append(years[m])
        E.append(np.where(panel.sold[r], panel.end_year[r].astype(np.int64) * 12 + panel.month[nxt] - 1, 0))
    return N, np.concatenate(R), np.concatenate(Y), np.concatenate(E)


def moved(lp, w, y, rows):
    """The first step's log-odds moved by a constant so that it expects the sales `rows` had."""
    lo, hi = -3.0, 3.0
    for _ in range(60):
        c = (lo + hi) / 2
        if (w[rows] / (1 + np.exp(-(lp[rows] + c)))).sum() > (w[rows] * y[rows]).sum():
            hi = c
        else:
            lo = c
    return 1 / (1 + np.exp(-(lp + c)))


def main():
    N, rows, years, end = rows_and_sales()
    d, P = ST.load(); p = P[7]
    start = d["year"].astype(np.int64) * 12
    assert len(rows) == len(p) and np.array_equal(years, d["year"]), "the rows are not aligned with the stored ones"
    assert np.array_equal((end >= start) & (end < start + 12), d["y"] == 1), "sale months do not agree with the stored outcome"
    N0 = NR.features_at(N, rows, years, 0)
    kinds = [k for k in NS.KINDS if np.isfinite(N0[:, ST.cols_of(k)[0]]).sum() >= 2000]
    w, lp, test = d["w"].astype(np.float64), ST.logit(p), d["chunk"] < 2
    rng = np.random.default_rng(5); draws = [rng.poisson(1.0, LE.N_BLOCKS).astype("float64") for _ in range(LE.BOOT)]
    j = NS.KINDS.index("dec")
    R = {"years": list(ST.YEARS), "kinds": kinds, "home_years": int(len(p)), "months": []}
    boot = {b[0]: [] for b in BANDS}
    for s in range(12):
        there = ~((end > 0) & (end < start + s))                             # not sold since 1 January
        y = ((end >= start + s) & (end < start + s + 12)).astype(np.float64)
        q = moved(lp, w, y, there)
        Ns = N0 if s == 0 else NR.features_at(N, rows, years, s)
        arms = {"deployed": ST.logit(q), "january": NR.cross({**d, "N": N0, "y": y}, q, kinds, there)}
        arms["monthly"] = arms["january"] if s == 0 else NR.cross({**d, "N": Ns, "y": y}, q, kinds, there)
        m = there[test]
        t = {k: d[k][test][m] for k in ("year", "tenure", "block", "district")}; yy = y[test][m]
        row = {"scored_on_1": MONTH[s], "months_after_1_january": s, "test_home_years_still_there": int(m.sum()), "rate": round(float(yy.mean()), 4), "bands": {}}
        for name, a, b in BANDS:
            band = LE.Local({**t, "y": yy}, a, b)
            tops = {arm: band.top_mask(v[test][m][band.keep]) for arm, v in arms.items()}
            r = {arm: round(band.lift(tp), 4) for arm, tp in tops.items()}
            dd = np.array([band.lift(tops["monthly"], g[band.block]) - band.lift(tops["january"], g[band.block]) for g in draws])
            r["monthly_minus_january"] = [round(r["monthly"] - r["january"], 4)] + [round(float(np.percentile(dd, x)), 4) for x in (2.5, 97.5)]
            row["bands"][name] = r; boot[name].append(dd)
        mo, owned = Ns[test][m][:, 3 * j], Ns[test][m][:, 3 * j + 1]
        fresh = (mo >= 1) & (mo <= s) & (owned >= 0)                         # a deceased-estate notice published since 1 January
        if fresh.sum() >= 30:
            L = LE.Local({**t, "y": yy})
            row["published_since_1_january"] = {
                "homes": int(fresh.sum()), "complete_in_the_next_12_months": round(float(yy[fresh].mean()), 4),
                "best_tenth_january": round(float(L.top_mask(arms["january"][test][m])[fresh].mean()), 3),
                "best_tenth_monthly": round(float(L.top_mask(arms["monthly"][test][m])[fresh].mean()), 3)}
        R["months"].append(row)
        print(json.dumps(row), flush=True)

    R["average_over_the_year"] = {}
    for name, _, _ in BANDS:
        v = {arm: round(float(np.mean([r["bands"][name][arm] for r in R["months"]])), 4) for arm in ("deployed", "january", "monthly")}
        dd = np.mean(boot[name], axis=0)
        v["monthly_minus_january"] = [round(v["monthly"] - v["january"], 4)] + [round(float(np.percentile(dd, x)), 4) for x in (2.5, 97.5)]
        R["average_over_the_year"][name] = v
    print(json.dumps(R["average_over_the_year"]), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(OUT / "NOTICE_MONTHLY.json", "w"), indent=1)
    report(R)


def report(R):
    pc = lambda x: f"{100 * x:.1f}%"                                    # noqa: E731
    ch = lambda v: f"{v[0]:+.3f} ({v[1]:+.3f} to {v[2]:+.3f})"          # noqa: E731
    A, T = R["average_over_the_year"]["all"], R["average_over_the_year"]["t20p"]
    md = ["# What refreshing the scores every month would add", "",
          "A test, not a change to the product. The product scores homes once a year, on 1 January. Here the ranking is looked at on the",
          "first of every month: homes sold since 1 January have left it, and the target is a sale completing in the twelve months that",
          f"follow. The years are {ST.YEARS[0]} and {ST.YEARS[1]}, the homes are the test chunks', and each is scored by notice steps fitted on other",
          "homes in the other year. The first step keeps its January figure throughout, so this is what the notices alone gain from",
          "being read sooner. Figures are sellers found in the best tenth of each postcode district, times random.", "",
          "## Every home", "",
          "| Looked at on 1 | No notices | Notices to 31 December | Notices to the month before | Monthly against yearly (95% range) |", "|---|---|---|---|---|"]
    md += [f"| {r['scored_on_1']} | {r['bands']['all']['deployed']:.3f} | {r['bands']['all']['january']:.3f} | {r['bands']['all']['monthly']:.3f} | "
           f"{ch(r['bands']['all']['monthly_minus_january']) if r['months_after_1_january'] else ''} |" for r in R["months"]]
    md += [f"| **Average over the year** | {A['deployed']:.3f} | {A['january']:.3f} | {A['monthly']:.3f} | {ch(A['monthly_minus_january'])} |", "",
           "## Homes owned for 20 years or more", "",
           "| Looked at on 1 | No notices | Notices to 31 December | Notices to the month before | Monthly against yearly (95% range) |", "|---|---|---|---|---|"]
    md += [f"| {r['scored_on_1']} | {r['bands']['t20p']['deployed']:.3f} | {r['bands']['t20p']['january']:.3f} | {r['bands']['t20p']['monthly']:.3f} | "
           f"{ch(r['bands']['t20p']['monthly_minus_january']) if r['months_after_1_january'] else ''} |" for r in R["months"]]
    md += [f"| **Average over the year** | {T['deployed']:.3f} | {T['january']:.3f} | {T['monthly']:.3f} | {ch(T['monthly_minus_january'])} |", "",
           "## The homes with a deceased-estate notice published since 1 January", "",
           "| Looked at on 1 | Homes | Complete in the next twelve months | In the best tenth scored yearly | Scored monthly |", "|---|---|---|---|---|"]
    md += [f"| {r['scored_on_1']} | {f['homes']:,} | {pc(f['complete_in_the_next_12_months'])} | {100 * f['best_tenth_january']:.0f}% | {100 * f['best_tenth_monthly']:.0f}% |"
           for r in R["months"] for f in [r.get("published_since_1_january")] if f]
    gain_y, gain_m = A["january"] - A["deployed"], A["monthly"] - A["deployed"]
    md += ["", "## Reading it", "",
           f"Averaged over the year, the notices add {gain_y:+.3f} to the best tenth when the product is scored once a year and {gain_m:+.3f} when it is",
           f"refreshed every month: {gain_m / gain_y:.1f} times as much. A notice says most in its first six months, and a yearly score does not",
           "hold the ones published since January.", ""]
    (OUT / "NOTICE_MONTHLY.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    if sys.argv[1:] == ["report"]:                      # the write-up again, from the figures already on disk
        report(json.load(open(OUT / "NOTICE_MONTHLY.json")))
    else:
        main()
