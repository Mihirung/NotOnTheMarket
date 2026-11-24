"""Aim the model at homes that are not yet on the market, and see whether certificates help there.

The deployed model is asked, on 1 January, which homes will sell in the calendar year. About
a fifth of those sales complete by March and were already on the market that day (late_sale.py).
Here the same model is refitted on a later target, a sale completing between July of the year
and June of the next, first with the deployed families and then with the certificate family
added. All three rankings are then scored on the later sellers:

    the deployed model (aimed at the calendar year)
    the deployed families, aimed at later sales
    the deployed families and certificates, aimed at later sales

The range on each gain counts the test homes (bootstrap over blocks of homes) and the fit's own
randomness, measured on this target from the three seeds of the deployed model.

    QM_LABEL=late python assess_late.py [pct]

Writes research/outputs/signals/LATE_MODEL.json and .md.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import assess_signal as A  # noqa: E402
import local_eval as LE  # noqa: E402
import model_lab as ML  # noqa: E402
import screen_late as SL  # noqa: E402

BANDS = {"all": "All", "t0_9": "Under 10 years", "t10_19": "10 to 19 years", "t20p": "20 years or more"}


def main():
    assert ML.LABEL == "late", "run with QM_LABEL=late"
    pct = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    say = lambda *a: print(*a, flush=True)                # noqa: E731
    ch = ML.Chunks(A.PANEL); out = Path(A.LAB)
    assert "EPC" in ch.rowfam
    preds = out / "preds"
    p_dep = np.load(preds / f"{A.CUR_NAME}@{pct}.npy")
    seeds = [np.load(f) for f in sorted(preds.glob(f"{A.CUR_NAME}@{pct}~s[0-9]*.npy")) if "~late" not in f.name]
    p_l, i_l = ML.predict_cached(ch, out, 4, A.CUR_NAME, pct, A.CURRENT)
    p_le, i_le = ML.predict_cached(ch, out, 4, f"{A.CUR_NAME}+EPC", pct, A.CURRENT + ["EPC"])
    ML._TEST.clear(); ch.release()

    t = LE.load_test(A.PANEL); ym = SL.end_ym()
    start = t["year"].astype(np.int64) * 12
    late = ((ym >= start + 6) & (ym < start + 18)).astype(np.float64)
    early = ((ym >= start) & (ym < start + 6)).astype(np.float64)
    arms = {"deployed": p_dep, "aimed": p_l, "aimed_epc": p_le}
    R = {"when": time.strftime("%Y-%m-%d"), "deployed": A.CUR_NAME, "families": A.CURRENT, "pct": pct,
         "rounds": {"aimed": i_l.get("rounds"), "aimed_epc": i_le.get("rounds")},
         "gain_share_epc": (i_le.get("gain_by_family") or {}).get("EPC"), "seeds_for_noise": 1 + len(seeds), "bands": {}}
    for nm, lo, hi in LE.TENURE:
        L = LE.Local(t, lo, hi); y_year = L.y.copy(); k = L.keep
        tops = {a: L.top_mask(p[k]) for a, p in arms.items()}
        res = {}
        for a, top in tops.items():
            L.y = late[k]; res[a] = {"later": round(L.lift(top), 4)}
            L.y = y_year; res[a]["calendar_year"] = round(L.lift(top), 4)
            res[a]["later_share_of_list"] = round(float((late[k] * top).sum() / top.sum()), 4)
            res[a]["under_way_share_of_list"] = round(float((early[k] * top).sum() / top.sum()), 4)
        L.y = late[k]
        sd = float(np.std([L.lift(L.top_mask(p[k])) for p in [p_dep] + seeds], ddof=1)) if len(seeds) >= 2 else None
        for g, a, b in (("re_aim", "deployed", "aimed"), ("certificates", "aimed", "aimed_epc"), ("both", "deployed", "aimed_epc")):
            rng = np.random.default_rng(3); d = []
            for _ in range(A.BOOT):
                w = rng.poisson(1.0, LE.N_BLOCKS).astype(float)[L.block]
                d.append(L.lift(tops[b], w) - L.lift(tops[a], w))
            lo_, hi_ = (float(np.percentile(d, q)) for q in (2.5, 97.5))
            v = {"gain": round(res[b]["later"] - res[a]["later"], 4), "range": [round(lo_, 4), round(hi_, 4)]}
            if sd is not None:                           # both sides are single fits: their difference carries sd * sqrt(2)
                half = float(np.hypot((hi_ - lo_) / 2, 1.96 * sd * np.sqrt(2))); mid = (lo_ + hi_) / 2
                v["range_with_fit_noise"] = [round(mid - half, 4), round(mid + half, 4)]
            res[g] = v
        res["seed_sd"] = None if sd is None else round(sd, 4)
        R["bands"][nm] = res
        say(f"  {nm:6s} later sellers found: deployed {res['deployed']['later']:.3f}, aimed {res['aimed']['later']:.3f}, "
            f"aimed with certificates {res['aimed_epc']['later']:.3f}; both {res['both']['gain']:+.3f} "
            f"({res['both'].get('range_with_fit_noise', res['both']['range'])})")
    r = R["bands"]["all"]["both"]; rr = r.get("range_with_fit_noise", r["range"])
    R["verdict"] = ("deploy the model aimed at later sales, with certificates: it finds more homes not yet on the market and the "
                    "range is clear of zero and of the fit's own noise" if rr[0] > 0 else
                    "do not deploy: no gain in finding homes not yet on the market that is clear of zero and of the fit's own noise")
    o = Path(A.OUT)
    json.dump(R, open(o / "LATE_MODEL.json", "w"), indent=1)
    f = lambda v: (lambda r: f"{v['gain']:+.3f} ({r[0]:+.3f} to {r[1]:+.3f})")(v.get("range_with_fit_noise", v["range"]))   # noqa: E731
    md = ["# The model aimed at homes not yet on the market", "", f"**Verdict:** {R['verdict']}", "",
          "Homes are scored on 1 January. A later seller completes between July of that year and June of the next, so",
          "was, with few exceptions, not yet listed on the scoring day. Figures are later sellers found in the best tenth",
          "of each postcode district, times random, test years 2017 and 2018. Ranges are 95% and include the fit's own",
          "randomness.", "",
          "| Owners | Deployed model | Aimed at later sales | Aimed, with certificates | Gain from the aim | Gain from certificates | Both |",
          "|---|---|---|---|---|---|---|"]
    for k, lab in BANDS.items():
        v = R["bands"][k]
        md.append(f"| {lab} | {v['deployed']['later']:.3f} | {v['aimed']['later']:.3f} | {v['aimed_epc']['later']:.3f} | "
                  f"{f(v['re_aim'])} | {f(v['certificates'])} | {f(v['both'])} |")
    v = R["bands"]["all"]
    md += ["", "## What the list is made of (all owners)", "",
           "| Ranking | Sells later | Sale already under way | Sellers in the calendar year, times random |", "|---|---|---|---|"]
    for a, lab in (("deployed", "Deployed model"), ("aimed", "Aimed at later sales"), ("aimed_epc", "Aimed, with certificates")):
        md.append(f"| {lab} | {100 * v[a]['later_share_of_list']:.1f}% | {100 * v[a]['under_way_share_of_list']:.1f}% | {v[a]['calendar_year']:.3f} |")
    md.append("")
    (o / "LATE_MODEL.md").write_text("\n".join(md))
    say(f"== {R['verdict']}")


if __name__ == "__main__":
    main()
