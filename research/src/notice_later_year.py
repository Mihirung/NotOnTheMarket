"""The ranking with notices against a later year that no part of it was fitted on.

The deployed model was fitted on 2001 to 2018 and the notice steps on 2017 and 2018 (notice_step.py).
This scores the homes of the test chunks on 1 January 2019 with both, exactly as the product does, and
sets the ranking against the sales of 2019. The 2019 sale records undercount late registrations, so
every rate runs low; that falls on every arm alike and leaves the comparison between them standing.

    python notice_later_year.py

Writes research/outputs/signals/NOTICE_LATER_YEAR.json and .md. Counts and rates only.
"""
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import local_eval as LE  # noqa: E402
import notice_signals as NS  # noqa: E402
import notice_step as ST  # noqa: E402
import screen_late as SL  # noqa: E402

YEAR = 2019
PANEL, LAB, OUT = SL.PANEL, SL.LAB, SL.OUT
ARM = {"with_notices": "With notices", "dec": "Deceased-estate notices alone", "bk": "Bankruptcy orders alone"}


def rows_of_the_year():
    """The test chunks' homes on 1 January of YEAR: outcome, place, the deployed model's figure and the notices."""
    import model_lab as ML
    from panel2 import Panel, chunk_rows
    ch = ML.Chunks(PANEL)
    bst = lgb.Booster(model_file=str(LAB / "model_deploy.txt"))
    cols, names = ch.cols(json.load(open(LAB / "lab_deploy.json"))["families"])
    assert bst.feature_name() == names, "the deployed model's columns do not match its families"
    panel = Panel(SL.TX, verbose=False); N = NS.Notices(panel)
    parts = {k: [] for k in ("y", "district", "block", "tenure", "p", "N")}
    for c in (0, 1):
        rows, years, label, _, _ = chunk_rows(panel, c)
        assert np.array_equal(label, np.load(PANEL / f"y_{c}.npy")), f"chunk {c}: rows are not in the stored order"
        m = years == YEAR
        r = ch.rows(c, (YEAR, YEAR))
        assert np.array_equal(np.nonzero(m)[0], r)
        parts["N"].append(N.features(rows[m], years[m]))
        parts["p"].append(np.concatenate([bst.predict(ch.X(c).take(r[i:i + 250_000], cols), num_threads=4)
                                          for i in range(0, len(r), 250_000)]))
        for k in ("y", "district", "block", "tenure"):
            parts[k].append(np.load(PANEL / f"{k}_{c}.npy")[m])
        print(f"chunk {c}: {int(m.sum()):,} homes", flush=True)
    return {k: np.concatenate(v) for k, v in parts.items()}


def top_mask(score, district, frac=0.10):
    """True for the homes in the best `frac` of their own district."""
    _, g = np.unique(district, return_inverse=True)
    size = np.bincount(g); start = np.concatenate(([0], np.cumsum(size)[:-1]))
    o = np.lexsort((-score, g)); gs = g[o]
    top = np.zeros(len(o), bool); top[o] = np.arange(len(o)) - start[gs] < np.round(frac * size[gs])
    return top


def lifts(d, y, keep, arms):
    """Sellers found in the best tenth, times random, for each arm, and each arm's change on the deployed model
    with a 95% range from resampling blocks of homes."""
    yy, blk, g = y[keep], d["block"][keep].astype(np.int64), d["district"][keep]
    G = np.random.default_rng(3).poisson(1.0, (1000, LE.N_BLOCKS)).astype(np.float64)
    Sy, Sn = np.bincount(blk, yy, LE.N_BLOCKS), np.bincount(blk, minlength=LE.N_BLOCKS).astype(float)
    out, boot = {"homes": int(keep.sum())}, {}
    for name, lp in arms.items():
        top = top_mask(lp[keep], g)
        Sty, St = np.bincount(blk, yy * top, LE.N_BLOCKS), np.bincount(blk, top.astype(float), LE.N_BLOCKS)
        out[name] = round(float((Sty.sum() / St.sum()) / (Sy.sum() / Sn.sum())), 4)
        boot[name] = ((G @ Sty) / (G @ St)) / ((G @ Sy) / (G @ Sn))
    for name in arms:
        if name != "deployed":
            diff = boot[name] - boot["deployed"]
            out[name + "_change"] = [round(out[name] - out["deployed"], 4)] + [round(float(np.percentile(diff, q)), 4) for q in (2.5, 97.5)]
    return out


def main():
    d = rows_of_the_year()
    y, lp0 = d["y"].astype(np.float64), ST.logit(d["p"])
    sec = json.load(open(LAB / "lab_second_notice.json"))
    arms = {"deployed": lp0, "with_notices": lp0.copy()}
    for part in sec["parts"]:
        k = part["kind"]
        X = d["N"][:, ST.cols_of(k)]; m = np.isfinite(X[:, 0])
        add = np.zeros(len(y)); add[m] = lgb.Booster(model_file=str(LAB / part["file"])).predict(X[m], raw_score=True)
        arms["with_notices"] += add; arms[k] = lp0 + add
    R = {"year": YEAR, "homes": int(len(y)), "sold": round(float(y.mean()), 4), "deployed_expected": round(float(d["p"].mean()), 4),
         "kinds": [p["kind"] for p in sec["parts"]], "bands": {}, "homes_with_a_notice": []}
    for name, lo, hi in LE.TENURE:
        R["bands"][name] = lifts(d, y, (d["tenure"] >= lo) & (d["tenure"] < hi), arms)
        print(name, R["bands"][name], flush=True)
    top0, top1 = top_mask(arms["deployed"], d["district"]), top_mask(arms["with_notices"], d["district"])
    p0, p1 = 1 / (1 + np.exp(-arms["deployed"])), 1 / (1 + np.exp(-arms["with_notices"]))
    for j, k in enumerate(NS.KINDS):
        if k not in R["kinds"]:
            continue
        mo, owned = d["N"][:, 3 * j], d["N"][:, 3 * j + 1]
        sets = [(f"{a} to {b} months before", (mo >= a) & (mo <= b) & (owned >= 0)) for a, b in ST.MONTHS]
        sets += [("Any time in the window, about an earlier owner", np.isfinite(mo) & (owned < 0)), ("Every home with one", np.isfinite(mo))]
        for lab, m in sets:
            if m.sum() >= 30:
                R["homes_with_a_notice"].append({
                    "kind": k, "notice": lab, "homes": int(m.sum()), "sold": round(float(y[m].mean()), 4),
                    "deployed_said": round(float(p0[m].mean()), 4), "with_the_step": round(float(p1[m].mean()), 4),
                    "best_tenth_before": round(float(top0[m].mean()), 3), "best_tenth_after": round(float(top1[m].mean()), 3)})
                print(R["homes_with_a_notice"][-1], flush=True)
    m = np.isfinite(d["N"][:, [3 * j for j in range(len(NS.KINDS))]]).any(axis=1)
    ll = lambda q: float(-(y[m] * np.log(np.clip(q[m], 1e-6, 1)) + (1 - y[m]) * np.log(np.clip(1 - q[m], 1e-6, 1))).mean())   # noqa: E731
    R["log_loss_homes_with_a_notice"] = {"homes": int(m.sum()), "before": round(ll(p0), 5), "after": round(ll(p1), 5)}

    pc = lambda x: f"{100 * x:.1f}%"                                    # noqa: E731
    ch = lambda v: f"{v[0]:+.3f} ({v[1]:+.3f} to {v[2]:+.3f})"          # noqa: E731
    others = [k for k in R["kinds"] if len(R["kinds"]) > 1]
    md = [f"# The ranking with notices against {YEAR}", "",
          f"The deployed model was fitted on 2001 to 2018 and the notice steps on 2017 and 2018. Here both score the {len(y):,} homes of",
          f"the test chunks on 1 January {YEAR}, as the product does, and the ranking is set against the sales of {YEAR}: a year no part",
          f"of it was fitted on. The {YEAR} sale records undercount late registrations ({pc(R['sold'])} sold against {pc(R['deployed_expected'])} expected),",
          "which lowers every rate alike and leaves the comparison standing.", "",
          "## Sellers found in the best tenth of each postcode district, times random", "",
          "| Owned for | Homes | Deployed model | With notices | Change (95% range) | " + " | ".join(ARM[k] for k in others) + " |",
          "|---|---|---|---|---|" + "---|" * len(others)]
    for name, v in R["bands"].items():
        md.append(f"| {ST.TEN[name]} | {v['homes']:,} | {v['deployed']:.3f} | {v['with_notices']:.3f} | {ch(v['with_notices_change'])} | "
                  + " | ".join(ch(v[k + "_change"]) for k in others) + (" |" if others else ""))
    md += ["", "## The homes with a notice", "",
           f"| Notice | Published | Homes | Sold in {YEAR} | Deployed model said | With the step | In the best tenth before | After |", "|---|---|---|---|---|---|---|---|"]
    md += [f"| {ST.KIND[r['kind']]} | {r['notice']} | {r['homes']:,} | {pc(r['sold'])} | {pc(r['deployed_said'])} | {pc(r['with_the_step'])} | "
           f"{100 * r['best_tenth_before']:.0f}% | {100 * r['best_tenth_after']:.0f}% |" for r in R["homes_with_a_notice"]]
    q = R["log_loss_homes_with_a_notice"]
    md += ["", f"Log loss on the {q['homes']:,} homes with a notice: {q['before']:.5f} before, {q['after']:.5f} with the step.", ""]
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(OUT / "NOTICE_LATER_YEAR.json", "w"), indent=1)
    (OUT / "NOTICE_LATER_YEAR.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
