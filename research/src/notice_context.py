"""Would the notice step rank better if it also read facts about the home: a test, not a change to the product.

The deployed step reads three columns for each kind of notice: months since the latest one, months the
home had been owned when it appeared, and how many there were. Here the step is also given the home's
type, price and years owned, the 2011 make-up of its output area, the later-life figures (LIFE, ranking
only) and the first step's own figure. Everything else is as in notice_step.py: each home-year is scored
by a step fitted on the other folds of homes in the other year, and the other kind of notice is as deployed.

    python notice_context.py [kind]         kind: dec (default) or bk

Writes research/outputs/signals/NOTICE_CONTEXT.json and .md. Counts and rates only.
"""
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import local_eval as LE  # noqa: E402
import model_lab as ML  # noqa: E402
import notice_signals as NS  # noqa: E402
import notice_step as ST  # noqa: E402
import screen_late as SL  # noqa: E402

KIND = sys.argv[1] if len(sys.argv) > 1 else "dec"
HOME = ["tenure", "ptype_D", "ptype_S", "ptype_T", "ptype_F", "leasehold", "n_prior", "log_price_rel", "price_pct", "pc_stock"]
AREA = ["own_outright", "own_mortgage", "social_rent", "private_rent", "hh_alone_65", "hh_couple_65", "age_65_74", "age_75_84",
        "age_85_plus", "widowed", "retired", "bungalows", "flats", "imd_rank"]
LIFE = ["owner_age", "p_owner_75", "p_owner_85", "p_exit", "p_exit_alone"]
SETS = {"home": HOME, "home_area": HOME + AREA, "home_area_life": HOME + AREA + LIFE}
OUT = SL.OUT
READS = {"step": "The notice alone, as deployed", "home": "The notice and the home", "home_area": "The notice, the home and its area",
         "home_area_life": "The notice, the home, its area and later life"}
PLAIN = {"notice_owned": "months owned when the notice appeared", "notice_months": "months since the notice", "notice_n": "the number of notices",
         "first_step": "the first step's figure"}


def extras(has, names):
    ch = ML.Chunks(SL.PANEL)
    ci = [ch.names.index(n) for n in names]
    out, start = [], 0
    for c in range(ch.n_chunks):
        r = ch.rows(c, ST.YEARS)
        sel = np.nonzero(has[start:start + len(r)])[0]
        out.append(ch.X(c).take(r[sel], ci).astype(np.float32)); start += len(r)
        print(f"chunk {c}: {len(sel):,} homes with one", flush=True)
    assert start == len(has)
    return np.concatenate(out)


def main():
    d, P = ST.load(); p = P[7]
    cols = ST.cols_of(KIND)
    has = np.isfinite(d["N"][:, cols[0]]); idx = np.nonzero(has)[0]
    names = HOME + AREA + LIFE
    E = extras(has, names)
    X3 = d["N"][idx][:, cols].astype(np.float32)
    y, w, init = d["y"][idx].astype(np.float64), d["w"][idx].astype(np.float64), ST.logit(p[idx])
    block, fold, year = d["block"][idx].astype(np.int64), d["chunk"][idx] % ST.FOLDS, d["year"][idx]
    feats = {"step": (X3, [f"notice_{c}" for c in ("months", "owned", "n")])}
    for lab, cs in SETS.items():
        j = [names.index(c) for c in cs]
        feats[lab] = (np.hstack([X3, E[:, j]]), feats["step"][1] + cs)
        feats[lab + "_first"] = (np.hstack([X3, E[:, j], init[:, None].astype(np.float32)]), feats["step"][1] + cs + ["first_step"])

    def fit(X, rows):
        if rows.sum() < 1000:
            return None
        n = ST.rounds_for(X[rows], y[rows], w[rows], init[rows], block[rows])
        return lgb.train(ST.PAR, lgb.Dataset(X[rows], y[rows], weight=w[rows], init_score=init[rows]), n) if n else None

    def cross(X):
        add, used = np.zeros(len(idx)), []
        for f in range(ST.FOLDS):
            for a, b in ((ST.YEARS[0], ST.YEARS[1]), (ST.YEARS[1], ST.YEARS[0])):
                m = fit(X, (fold != f) & (year == a)); te = (fold == f) & (year == b)
                used.append(m.num_trees() if m is not None else 0)
                if m is not None:
                    add[te] = m.predict(X[te], raw_score=True)
        return add, used

    others = [k for k in NS.KINDS if k != KIND and np.isfinite(d["N"][:, ST.cols_of(k)[0]]).sum() >= 2000]
    base = ST.cross_fit(d, p, others)[0] if others else ST.logit(p)
    arms, R = {"deployed": ST.logit(p)}, {"kind": KIND, "rows_with_one": int(len(idx)), "arms": {}, "bands": {}}
    for lab, (X, _) in feats.items():
        add, used = cross(X)
        lp = base.copy(); lp[idx] += add
        arms[lab] = lp; R["arms"][lab] = {"columns": X.shape[1], "rounds": used}
        print(lab, X.shape[1], "columns, rounds", used, flush=True)

    test = d["chunk"] < 2
    t = {k: d[k][test] for k in ("year", "tenure", "block", "district", "y")}
    rng = np.random.default_rng(5); draws = [rng.poisson(1.0, LE.N_BLOCKS).astype("float64") for _ in range(LE.BOOT)]
    for name, a, b in LE.TENURE:
        band = LE.Local(t, a, b)
        tops = {arm: band.top_mask(v[test][band.keep]) for arm, v in arms.items()}
        row = {arm: round(band.lift(tp), 4) for arm, tp in tops.items()}
        for arm in feats:
            if arm != "step":
                dd = [band.lift(tops[arm], g[band.block]) - band.lift(tops["step"], g[band.block]) for g in draws]
                row[arm + "_minus_step"] = [round(row[arm] - row["step"], 4)] + [round(float(np.percentile(dd, q)), 4) for q in (2.5, 97.5)]
        R["bands"][name] = row
        print(name, json.dumps(row), flush=True)

    m = test[idx]
    yy, ww = y[m], w[m]
    ll = lambda lp: float(-(ww * (yy * np.log(np.clip(1 / (1 + np.exp(-lp)), 1e-6, 1)) + (1 - yy) * np.log(np.clip(1 - 1 / (1 + np.exp(-lp)), 1e-6, 1)))).sum() / ww.sum())   # noqa: E731
    R["log_loss_test_homes_with_one"] = {"rows": int(m.sum()), **{a: round(ll(v[idx][m]), 5) for a, v in arms.items()}}
    print("log loss", R["log_loss_test_homes_with_one"], flush=True)

    best = "home_area_life_first"
    X, nm = feats[best]
    full = fit(X, np.ones(len(idx), bool))
    if full is not None:
        g = full.feature_importance("gain"); o = np.argsort(-g)
        R["gain_share"] = {nm[i]: round(float(g[i] / g.sum()), 3) for i in o[:15]}
        print("gain share", R["gain_share"], flush=True)
    R["helps"] = bool(max(v[1] for k, v in R["bands"]["all"].items() if k.endswith("_minus_step")) > 0)

    ch = lambda v: f"{v[0]:+.4f} ({v[1]:+.4f} to {v[2]:+.4f})"          # noqa: E731
    q, al, lt = R["log_loss_test_homes_with_one"], R["bands"]["all"], R["bands"]["t20p"]
    md = [f"# Would the {ST.KIND[KIND].lower()} step rank better with facts about the home?", "",
          "A test, not a change to the product. The deployed step reads three columns: months since the latest notice, months the home",
          "had been owned when it appeared, and how many there were. Here it is also given the home's type, price and years owned",
          f"({len(HOME)} columns), the 2011 make-up of its output area ({len(AREA)}), the later-life figures ({len(LIFE)}) and, in the second row of",
          f"each pair, the first step's own figure. {R['rows_with_one']:,} home-years of {ST.YEARS[0]} and {ST.YEARS[1]} have one; each is scored by a step fitted",
          "on other homes in the other year. Figures are sellers found in the best tenth of each postcode district, times random.", "",
          "| The step reads | Columns | All homes | Against the deployed step (95% range) | Owned 20 years or more | Log loss, test homes with one |",
          "|---|---|---|---|---|---|",
          f"| No notices | 0 | {al['deployed']:.4f} |  | {lt['deployed']:.4f} | {q['deployed']:.5f} |"]
    for arm in feats:
        lab = READS[arm.replace("_first", "")] + (", with the first step's figure" if arm.endswith("_first") else "")
        md.append(f"| {lab} | {R['arms'][arm]['columns']} | {al[arm]:.4f} | {ch(al[arm + '_minus_step']) if arm != 'step' else ''} | {lt[arm]:.4f} | {q[arm]:.5f} |")
    if "gain_share" in R:
        top = list(R["gain_share"].items())[:4]
        md += ["", "In the widest step, " + ", ".join(f"{PLAIN.get(k, '`' + k + '`')} carries {100 * v:.0f}%" for k, v in top) + " of what the trees gain."]
    md += ["", "## Reading it", "",
           ("At least one wider step finds more sellers, clear of zero." if R["helps"] else
            "No wider step finds more sellers: every change is within its own range of zero. When the notice appeared and how long the home "
            "had been owned say what there is to say; the step stays as it is."), ""]
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(OUT / "NOTICE_CONTEXT.json", "w"), indent=1)
    (OUT / "NOTICE_CONTEXT.md").write_text("\n".join(md))
    print("\n".join(md))

if __name__ == "__main__":
    main()
