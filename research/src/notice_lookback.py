"""Would a longer look-back on notices help: a test, not a change to the product.

The product reads notices published in the 48 months before the scoring day. The bankruptcy listings
reach back to January 2012, so the home-years of 2017 and 2018 can also be read with a 60-month
look-back. Everything else is as in notice_step.py: the first step is the deployed model as fitted to
2015, and each home-year is scored by notice steps fitted on the other folds of homes in the other
year. The arms:

  deployed    the first step alone
  months_48   plus the notice steps as deployed, every kind on a 48-month look-back
  months_60   the same, with the kind under test on a 60-month look-back

    python notice_lookback.py [kind]        kind: bk (default) or dec, if its listings reach back far enough

Writes research/outputs/signals/NOTICE_LOOKBACK.json and .md. Counts and rates only.
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
WIDE = 60


def wide_reading(kind):
    """The notices at every home-year of the two years on a WIDE-month look-back, and the first month the listing holds."""
    from panel2 import Panel, chunk_rows
    panel = Panel(SL.TX, verbose=False); N = NS.Notices(panel)
    first = int(np.min(N.ev[kind][1] % NS.M))
    out = []
    for c in range(len(json.load(open(SL.PANEL / "meta.json"))["chunks"])):
        rows, years, _, _, _ = chunk_rows(panel, c)
        m = (years >= ST.YEARS[0]) & (years <= ST.YEARS[1])
        out.append(NR.features_at(N, rows[m], years[m], 0, WIDE))
        print(f"chunk {c}: {int(m.sum()):,} rows", flush=True)
    return np.concatenate(out), first


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "bk"
    Nw, first = wide_reading(kind)
    need = ST.YEARS[0] * 12 - WIDE
    assert first <= need, f"the {kind} listing starts in month {first % 12 + 1} of {first // 12}: too late for a {WIDE}-month look-back"
    d, P = ST.load(); p = P[7]
    assert len(Nw) == len(d["y"]), "the notices are not aligned with the stored rows"
    cols = ST.cols_of(kind)
    N60 = d["N"].copy(); N60[:, cols] = Nw[:, cols]
    kinds = [k for k in NS.KINDS if np.isfinite(d["N"][:, ST.cols_of(k)[0]]).sum() >= 2000]
    arms = {"deployed": ST.logit(p), "months_48": ST.cross_fit(d, p, kinds)[0], "months_60": ST.cross_fit({**d, "N": N60}, p, kinds)[0]}
    print("steps fitted", flush=True)

    R = {"years": list(ST.YEARS), "kind": kind, "look_back_months": [NS.WINDOW, WIDE], "home_years": int(len(p)), "older_notices": [], "bands": {}}
    w, y = d["w"].astype(np.float64), d["y"].astype(np.float64)
    mo, owned = N60[:, cols[0]], N60[:, cols[1]]
    said = {a: 1 / (1 + np.exp(-v)) for a, v in arms.items()}
    G = np.random.default_rng(3).poisson(1.0, (1000, LE.N_BLOCKS))
    sets = [(f"{a} to {b} months before", (mo >= a) & (mo <= b) & (owned >= 0)) for a, b in ST.MONTHS[-2:] + [(NS.WINDOW + 1, WIDE)]]
    sets.append((f"{NS.WINDOW + 1} to {WIDE} months before, about an earlier owner", (mo > NS.WINDOW) & (owned < 0)))
    for lab, m in sets:
        if m.sum() < 50:
            continue
        S, E, E60, Nn = (np.bincount(d["block"][m], v[m], LE.N_BLOCKS) for v in (w * y, w * said["deployed"], w * said["months_60"], w))
        ratio = (G @ S) / (G @ E)
        R["older_notices"].append({"notice": lab, "rows": int(m.sum()), "home_years": round(float(Nn.sum())), "sold": round(float(S.sum())),
                                   "rate": round(float(S.sum() / Nn.sum()), 4), "deployed_said": round(float(E.sum() / Nn.sum()), 4),
                                   "times": round(float(S.sum() / E.sum()), 2), "times_range": [round(float(np.percentile(ratio, q)), 2) for q in (2.5, 97.5)],
                                   "step_says": round(float(E60.sum() / Nn.sum()), 4)})
        print(R["older_notices"][-1], flush=True)

    test = d["chunk"] < 2
    t = {k: d[k][test] for k in ("year", "tenure", "block", "district", "y")}
    rng = np.random.default_rng(5); draws = [rng.poisson(1.0, LE.N_BLOCKS).astype("float64") for _ in range(LE.BOOT)]
    for name, a, b in LE.TENURE:
        band = LE.Local(t, a, b)
        tops = {arm: band.top_mask(v[test][band.keep]) for arm, v in arms.items()}
        row = {arm: round(band.lift(tp), 4) for arm, tp in tops.items()}
        dd = [band.lift(tops["months_60"], g[band.block]) - band.lift(tops["months_48"], g[band.block]) for g in draws]
        row["months_60_minus_48"] = [round(row["months_60"] - row["months_48"], 4)] + [round(float(np.percentile(dd, q)), 4) for q in (2.5, 97.5)]
        R["bands"][name] = row
        print(name, row, flush=True)
    m = test & np.isfinite(mo)
    ll = lambda q: float(-(w[m] * (y[m] * np.log(np.clip(q[m], 1e-6, 1)) + (1 - y[m]) * np.log(np.clip(1 - q[m], 1e-6, 1)))).sum() / w[m].sum())   # noqa: E731
    R["log_loss_test_homes_with_one"] = {"rows": int(m.sum()), **{a: round(ll(v), 5) for a, v in said.items()}}
    v = R["bands"]["all"]["months_60_minus_48"]
    R["helps"] = bool(v[1] > 0)

    pc = lambda x: f"{100 * x:.1f}%"                                    # noqa: E731
    ch = lambda v: f"{v[0]:+.3f} ({v[1]:+.3f} to {v[2]:+.3f})"          # noqa: E731
    name = ST.KIND[kind].lower() + "s"
    md = [f"# A {WIDE}-month look-back for {name}", "",
          f"A test, not a change to the product. The product reads notices published in the {NS.WINDOW} months before the scoring day.",
          f"Here {name} are read {WIDE} months back for the home-years of {ST.YEARS[0]} and {ST.YEARS[1]}, with every other notice as deployed.", "",
          "## The homes with an older notice", "",
          "| Latest notice | Home-years | Sold in the year | Deployed model said | Times (95% range) | Step says |", "|---|---|---|---|---|---|"]
    md += [f"| {r['notice']} | {r['home_years']:,} | {pc(r['rate'])} | {pc(r['deployed_said'])} | {r['times']:.2f} ({r['times_range'][0]:.2f} to {r['times_range'][1]:.2f}) | "
           f"{pc(r['step_says'])} |" for r in R["older_notices"]]
    md += ["", "## Sellers found in the best tenth of each postcode district, times random", "",
           f"| Owned for | No notices | {NS.WINDOW} months | {WIDE} months | {WIDE} against {NS.WINDOW} (95% range) |", "|---|---|---|---|---|"]
    md += [f"| {ST.TEN[tn]} | {v['deployed']:.3f} | {v['months_48']:.3f} | {v['months_60']:.3f} | {ch(v['months_60_minus_48'])} |" for tn, v in R["bands"].items()]
    q = R["log_loss_test_homes_with_one"]
    md += ["", f"Log loss on the {q['rows']:,} test home-years with one in {WIDE} months: {q['deployed']:.5f} with no notices, "
           f"{q['months_48']:.5f} on {NS.WINDOW} months, {q['months_60']:.5f} on {WIDE}.", "",
           "## Reading it", "",
           ("The longer look-back finds more sellers, clear of zero." if R["helps"] else
            f"The longer look-back does not find more sellers: the change is not clear of zero. The product keeps {NS.WINDOW} months."), ""]
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(OUT / "NOTICE_LOOKBACK.json", "w"), indent=1)
    (OUT / "NOTICE_LOOKBACK.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
