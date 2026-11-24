"""Screen: intent shown in past years, and facts about the home, from the energy certificates.

The columns are those of epc2_signals.py. The test is the one in stack_late.py: a small second
model on the deployed model's prediction, aimed at homes that sell later and were not yet listed
on the scoring day (listed_truth.py), fitted on one test year and scored on the other. Both
sides have the first certificate family, so a gain here is a gain over the certificates already
in the second step. It is also given for sales completing nine months out or more, a measure
that owes nothing to the certificates.

    python screen_facts.py

Writes research/outputs/signals/SCREEN_FACTS.json and .md. The columns for the test homes are
kept in research/data/panel3/test_EPC2.npy so the screen can be rerun without the certificates.
"""
import gc
import json

import lightgbm as lgb
import numpy as np
import pandas as pd

import epc2_signals as E2
import epc_signals as ES
import local_eval as LE
import screen_catb as SC
import screen_late as SL

PANEL, LAB, OUT = SL.PANEL, SL.LAB, SL.OUT
FIRST = [f"{SL.CUR}@100.npy"]                                    # the first step: the deployed model


def columns(rows, years):
    f = PANEL / "test_EPC2.npy"; names = PANEL / "test_EPC2.json"
    if f.exists() and names.exists() and json.load(open(names)) == E2.COLS:
        return np.load(f)
    from panel2 import Panel
    panel = Panel(SL.TX, verbose=False)
    X = E2.Epc2(ES.Epc(panel, panel.month)).features(rows, years)
    np.save(f, X); json.dump(E2.COLS, open(names, "w"))
    del panel; gc.collect()
    return X


def main():
    t = LE.load_test(PANEL); rows = SC.test_rows(); ym = SL.end_ym()
    assert len(rows) == len(t["y"]) == len(ym)
    N = columns(rows, t["year"])
    E = np.vstack([np.load(PANEL / f"R_EPC_{c}.npy")[np.load(PANEL / f"year_{c}.npy") >= 2017] for c in (0, 1)]).astype("float32")
    first = next(f for f in FIRST if (LAB / "preds" / f).exists())
    p = np.load(LAB / "preds" / first).astype(np.float64)
    keep = t["year"] <= 2018
    tk = {k: v[keep] for k, v in t.items()}
    N, E, p, ym = N[keep], E[keep], p[keep], ym[keep]
    year, ten = tk["year"].astype(np.int64), tk["tenure"]
    start = year * 12
    frac = np.load(PANEL / "test_listed_after.npy").astype(np.float64)[keep]
    later = ((ym >= start + 6) & (ym < start + 18)).astype(np.float64)
    late = later * frac                                           # sells later and was not yet listed on the scoring day
    far = ((ym >= start + 9) & (ym < start + 18)).astype(np.float64)
    ix = {c: i for i, c in enumerate(E2.COLS)}

    # what the columns say on their own
    anc = E[:, ES.COLS.index("anchored")] > 0
    tabs = []
    for lab, m in (("UPRN known", anc), ("UPRN known, a sale certificate over a year old and no sale", anc & (N[:, ix["own_sale_n"]] > 0)),
                   ("UPRN known, that certificate over 24 months old", anc & (N[:, ix["own_sale_age"]] > 24)),
                   ("UPRN known, a sale certificate in the last 12 months", anc & (E[:, ES.COLS.index("own_sale_12m")] > 0)),
                   ("UPRN known, a rental certificate since buying", anc & np.isfinite(N[:, ix["own_rent_age"]])),
                   ("UPRN known, a grant-scheme certificate since buying", anc & (N[:, ix["own_grant_n"]] > 0)),
                   ("UPRN known, let privately when last assessed", anc & (N[:, ix["own_let"]] > 0)),
                   ("UPRN known, a bungalow", anc & (N[:, ix["own_bungalow"]] > 0)),
                   ("UPRN not known", ~anc), ("UPRN not known, left-over sale certificates 24 to 60 months old", ~anc & (N[:, ix["pool_share_60m"]] > 0)),
                   ("UPRN not known, at least one for every four homes", ~anc & (N[:, ix["pool_share_60m"]] >= 0.25))):
        tabs.append({"homes": lab, "home_years": int(m.sum()), "sells_later": round(float(late[m].mean()), 4) if m.any() else None,
                     "nine_months_out": round(float(far[m].mean()), 4) if m.any() else None,
                     "first_step_said": round(float(p[m].mean()), 4) if m.any() else None})
        print(tabs[-1], flush=True)

    lp = np.clip(p, 1e-6, 1 - 1e-6)
    Z = np.column_stack([np.log(lp / (1 - lp)), ten, E, N]); names = ["model", "tenure"] + ES.COLS + E2.COLS
    nb = 2 + len(ES.COLS)
    sets = {"second step": list(range(nb)), "with all": list(range(Z.shape[1]))}
    for gname, cols in E2.GROUPS.items():
        sets[f"with {gname}"] = list(range(nb)) + [nb + ix[c] for c in cols]
    pred = {k: np.empty(len(late)) for k in sets}
    par = dict(objective="cross_entropy", learning_rate=0.04, num_leaves=31, min_data_in_leaf=1000, feature_fraction=0.9,
               bagging_fraction=0.7, bagging_freq=1, lambda_l2=10, verbose=-1, seed=7, num_threads=4)
    gains = {}
    for a, c in ((2017, 2018), (2018, 2017)):
        tr, te = year == a, year == c
        for k, cols in sets.items():
            m = lgb.train(par, lgb.Dataset(Z[tr][:, cols], late[tr], feature_name=[names[i] for i in cols]), 250)
            pred[k][te] = m.predict(Z[te][:, cols])
            if k == "with all":
                g = m.feature_importance("gain"); gains[a] = {names[i]: round(float(v / g.sum()), 3) for i, v in zip(cols, g)}
    R = {"first_step": first, "rows": int(len(late)), "later_sellers": int(late.sum()), "what_the_columns_say": tabs,
         "gain_share": gains, "bands": {}}
    f = lambda v: f"{v[0]:+.3f} ({v[1]:+.3f} to {v[2]:+.3f})"       # noqa: E731
    md = ["# Screen: past intent and home facts from the energy certificates", "",
          f"First step: `{first}`. Homes that sell later and were not yet listed on the scoring day, found in the best",
          "tenth of each postcode district, times random, test years 2017 and 2018. Each gain is against the same second",
          "step (which has the first certificate family) without the new columns. Ranges are 95% and cover sampling only.", "",
          "| Owners | First step | Second step | With all new columns | Gain | Gain, nine months out or more | "
          + " | ".join(g.capitalize() for g in E2.GROUPS) + " |",
          "|---|---|---|---|---|---|" + "---|" * len(E2.GROUPS)]
    for nm, lo, hi in LE.TENURE:
        L = LE.Local(tk, lo, hi); L.y = late[L.keep]
        tops = {k: L.top_mask(v[L.keep]) for k, v in pred.items()}; tops["first step"] = L.top_mask(p[L.keep])
        res = {k: round(L.lift(v), 4) for k, v in tops.items()}
        res["gain"] = {}

        def gain(k):
            rng = np.random.default_rng(3); dd = []
            for _ in range(SL.BOOT):
                w = rng.poisson(1.0, LE.N_BLOCKS).astype(float)[L.block]
                dd.append(L.lift(tops[k], w) - L.lift(tops["second step"], w))
            return [round(L.lift(tops[k]) - L.lift(tops["second step"]), 4)] + [round(float(np.percentile(dd, q)), 4) for q in (2.5, 97.5)]
        for k in sets:
            if k != "second step":
                res["gain"][k] = gain(k)
        L.y = far[L.keep]; res["gain_nine_months_out"] = gain("with all")
        R["bands"][nm] = res
        md.append(f"| {nm} | {res['first step']:.3f} | {res['second step']:.3f} | {res['with all']:.3f} | {f(res['gain']['with all'])} | "
                  f"{f(res['gain_nine_months_out'])} | " + " | ".join(f(res["gain"][f"with {g}"]) for g in E2.GROUPS) + " |")
        print(nm, res, flush=True)
    md += ["", "## What the columns say on their own", "",
           "| Homes on 1 January | Home-years | Sell later, not yet listed | Complete nine months out or more | The model said (calendar year) |",
           "|---|---|---|---|---|"]
    md += [f"| {r['homes']} | {r['home_years']:,} | {100 * (r['sells_later'] or 0):.1f}% | {100 * (r['nine_months_out'] or 0):.1f}% | "
           f"{100 * (r['first_step_said'] or 0):.1f}% |" for r in tabs]
    md.append("")
    print("gain share", {a: sorted(g.items(), key=lambda kv: -kv[1])[:12] for a, g in gains.items()}, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(OUT / "SCREEN_FACTS.json", "w"), indent=1)
    (OUT / "SCREEN_FACTS.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    main()
