"""What is a signal family worth? One command, the same five tests every time.

    python assess_signal.py <FAMILY> [--pct 100] [--skip-fit]

FAMILY is a place family registered in signals.py (e.g. HOUSE, AREA). The
tests, all on the whole of England and Wales:

  1. Coverage      share of postcodes and of test home-years that have it.
  2. Like for like each column's link with the yearly chance of a sale,
                   holding the kind of home, price, length of ownership and
                   year fixed (a straight-line fit, 2010-2019 home-years of
                   the 10% of homes in the test chunks). Shown for all of the
                   country and region by region, so a link that only holds
                   in one place shows up.
  3. On top        what is left of each column once the current national
                   model's own score is allowed for (2017-2018, years the
                   model never saw).
  4. Adds to the   the current model refitted with the family added, against
     model         the current model refitted the same way: sellers found in
                   the best tenth of each district (the way campaigns are
                   mailed), with a block-bootstrap range, overall and for
                   owners of 20 years or more.
  5. Price         the price premium for one step of each column, like for
                   like (same sector, year, type, new build, tenure), on
                   every sale from 2010 to 2019.

Writes research/outputs/signals/<FAMILY>.json and <FAMILY>.md. The verdict
line says whether to add the family to the deployed model: only if test 4
shows a gain whose range is clear of zero, so the model can never get worse.
The range counts two kinds of chance: which homes fall in the test years (the
bootstrap) and the fit's own randomness (two fits of the same model differ;
measured by seed_noise.py and seed_ensemble.py). Without the second, a lucky
or unlucky fit reads as a real gain or loss.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import local_eval as LE  # noqa: E402
import model_lab as ML  # noqa: E402
import signals as SG  # noqa: E402

PANEL, LAB, OUT = "research/data/panel3", "research/outputs/lab", "research/outputs/signals"
TX = "research/data/transactions.parquet"


def _deployed():
    """The model a new family has to beat: the one deployed (lab_deploy.json)."""
    try:
        d = json.load(open("research/outputs/lab/lab_deploy.json"))
        return d["name"], d["families"]
    except (OSError, KeyError, ValueError):
        return "CURRENT", ["BASE", "HIST", "GEO", "VIEW"]


CUR_NAME, CURRENT = _deployed()
CTRL = ["tenure", "log_price_rel", "leasehold", "is_new", "n_prior", "turnover_3y", "price_rel_nat",
        "ptype_D", "ptype_S", "ptype_T", "ptype_F"]
NB, BOOT = 512, 200
REGION = {  # postcode area -> region, for the region-by-region check
    "London": "E EC N NW SE SW W WC BR CR DA EN HA IG KT RM SM TW UB WD",
    "South East": "BN CT GU HP ME MK OX PO RG RH SL SO TN",
    "East": "AL CB CM CO IP LU NR PE SG SS",
    "South West": "BA BH BS DT EX GL PL SN SP TA TQ TR",
    "Midlands": "B CV DE DY LE LN NG NN ST TF WR WS WV HR",
    "North West": "BB BL CA CH CW FY L LA M OL PR SK WA WN",
    "Yorkshire and North East": "BD DH DL DN HD HG HU HX LS S TS WF YO DN NE SR",
    "Wales": "CF LD LL NP SA SY",
}
AREA2REGION = {a: r for r, s in REGION.items() for a in s.split()}


def _blocks(key, n=NB):
    return (np.abs(key) % n).astype(np.int64)


class LinFit:
    """Least squares by blocks, so any bootstrap re-weighting of blocks is cheap."""

    def __init__(self, X, y, blk):
        order = np.argsort(blk, kind="stable"); cuts = np.searchsorted(blk[order], np.arange(NB + 1))
        self.XtX = np.stack([X[order[cuts[i]:cuts[i + 1]]].T @ X[order[cuts[i]:cuts[i + 1]]] for i in range(NB)])
        self.Xty = np.stack([X[order[cuts[i]:cuts[i + 1]]].T @ y[order[cuts[i]:cuts[i + 1]]] for i in range(NB)])

    def last(self, w=None):
        A = self.XtX.sum(0) if w is None else np.tensordot(w, self.XtX, 1)
        b = self.Xty.sum(0) if w is None else w @ self.Xty
        return np.linalg.lstsq(A, b, rcond=None)[0][-1]

    def ci(self, scale=1.0, seed=1):
        rng = np.random.default_rng(seed)
        bs = [self.last(rng.poisson(1.0, NB).astype(float)) for _ in range(BOOT)]
        return round(scale * float(self.last()), 4), [round(scale * float(np.percentile(bs, q)), 4) for q in (2.5, 97.5)]


def test_rows(ch, years, chunks=(0, 1)):
    """Rows of the test chunks: features for the controls, the family, and keys."""
    out = {k: [] for k in ("c", "r")}
    for c in chunks:
        r = ch.rows(c, years)
        out["c"].append(np.full(len(r), c)); out["r"].append(r)
    return np.concatenate(out["c"]), np.concatenate(out["r"])


def gather(ch, chunks_rows, fams_cols):
    c_all, r_all = chunks_rows
    parts = []
    for c in np.unique(c_all):
        r = r_all[c_all == c]
        parts.append(ch.X(c).take(r, fams_cols))
    return np.vstack(parts)


def col_of(ch, kind, chunks_rows):
    c_all, r_all = chunks_rows
    return np.concatenate([ch.col(kind, c)[r_all[c_all == c]] for c in np.unique(c_all)])


def like_for_like(ch, fam, say):
    cr = test_rows(ch, (2010, 2019))
    ctrl_idx = [ch.names.index(c) for c in CTRL]
    fam_idx, fam_cols = ch.cols([fam])
    C = gather(ch, cr, ctrl_idx); F = gather(ch, cr, fam_idx).astype(np.float32)   # wide families (40 columns) need the room
    y = col_of(ch, "y", cr).astype(float); yr = col_of(ch, "year", cr); blk = _blocks(col_of(ch, "block", cr))
    pc = col_of(ch, "pc", cr); area = pd.Series(ch.postcodes[pc]).str.extract(r"^([A-Z]+)")[0].map(AREA2REGION).to_numpy()
    C = np.nan_to_num((C - np.nanmean(C, 0)) / np.where(np.nanstd(C, 0) > 0, np.nanstd(C, 0), 1))
    ten = C[:, CTRL.index("tenure")]
    Y = (yr[:, None] == np.arange(2011, 2020)[None, :]).astype(float)
    base = np.column_stack([np.ones(len(y)), C, ten ** 2, Y])
    res = {}
    for j, col in enumerate(fam_cols):
        x = F[:, j]; ok = np.isfinite(x)
        if ok.mean() < 0.2 or np.nanstd(x) == 0:
            continue
        sd = float(np.nanstd(x)); z = np.where(ok, (x - np.nanmean(x)) / sd, 0.0)
        est, rng = LinFit(np.column_stack([base, z]), y, blk).ci(100.0)
        reg = {}
        for rname in REGION:
            m = area == rname
            if m.sum() > 200_000:
                reg[rname] = round(100 * float(LinFit(np.column_stack([base[m], z[m]]), y[m], blk[m]).last()), 4)
        signs = [np.sign(v) for v in reg.values() if abs(v) > 1e-9]
        res[col] = {"points_per_step": est, "range": rng, "step": round(sd, 4), "by_region": reg,
                    "regions_same_sign": f"{sum(s == np.sign(est) for s in signs)} of {len(signs)}"}
        say(f"  {col:20s} {est:+.3f} ({rng[0]:+.3f} to {rng[1]:+.3f}) points a year per step; same sign in "
            f"{res[col]['regions_same_sign']} regions")
    return res, int(len(y)), int(y.sum())


def on_top(ch, fam, ref_pred, say):
    _, y, yr, ten, blk = ML.shared_labels(ch)
    cr = test_rows(ch, (2017, 2019))
    fam_idx, fam_cols = ch.cols([fam])
    F = gather(ch, cr, fam_idx)
    m = yr <= 2018
    y, F, p, b = y[m].astype(float), F[m], ref_pred[m].astype(float), _blocks(blk[m].astype(np.int64))
    z = np.log(np.clip(p, 1e-5, 1 - 1e-5) / (1 - np.clip(p, 1e-5, 1 - 1e-5)))
    base = np.column_stack([np.ones(len(y)), z, z ** 2, z ** 3, (yr[m] == 2018).astype(float)])
    res = {}
    for j, col in enumerate(fam_cols):
        x = F[:, j]; ok = np.isfinite(x)
        if ok.mean() < 0.2 or np.nanstd(x) == 0:
            continue
        zz = np.where(ok, (x - np.nanmean(x)) / np.nanstd(x), 0.0)
        est, rng = LinFit(np.column_stack([base, zz]), y, b).ci(100.0)
        res[col] = {"points_per_step": est, "range": rng}
    n_clear = sum(1 for v in res.values() if v["range"][0] > 0 or v["range"][1] < 0)
    say(f"  {n_clear} of {len(res)} columns still have a link clear of zero once the national score is allowed for")
    return res


def fit_noise(group):
    """Spread (standard deviation) of the best-tenth lift across fits of the deployed model, or None if not measured."""
    f = Path(OUT) / "ENSEMBLE.json"
    try:
        R = json.load(open(f))
        return R["results"][group]["seed_sd"] if R.get("deployed") == CUR_NAME else None
    except (OSError, KeyError, ValueError):
        return None


def adds_to_model(ch, fam, pct, threads, say):
    t = LE.load_test(PANEL)
    out = Path(LAB)
    p_cur, _ = ML.predict_cached(ch, out, threads, CUR_NAME, pct, CURRENT)
    name = f"+{fam}" if CUR_NAME == "CURRENT" else f"{CUR_NAME}+{fam}"
    p_new, info = ML.predict_cached(ch, out, threads, name, pct, CURRENT + [fam])
    res = {}
    for name, lo, hi in LE.TENURE:
        L = LE.Local(t, lo, hi)
        ma, mb = L.top_mask(p_cur[L.keep]), L.top_mask(p_new[L.keep])
        a, b = L.lift(ma), L.lift(mb)
        rng = np.random.default_rng(3); da = []
        for _ in range(BOOT):
            w = rng.poisson(1.0, LE.N_BLOCKS).astype(float)[L.block]
            da.append(L.lift(mb, w) - L.lift(ma, w))
        res[name] = {"current": round(a, 4), "with": round(b, 4), "gain": round(b - a, 4),
                     "range": [round(float(np.percentile(da, q)), 4) for q in (2.5, 97.5)]}
        sd = fit_noise(name)
        if sd is not None:                            # both sides are single fits: their difference carries sd * sqrt(2)
            lo_, hi_ = res[name]["range"]
            half = float(np.hypot((hi_ - lo_) / 2, 1.96 * sd * np.sqrt(2)))
            mid = (lo_ + hi_) / 2
            res[name]["range_with_fit_noise"] = [round(mid - half, 4), round(mid + half, 4)]
        r = res[name].get("range_with_fit_noise", res[name]["range"])
        say(f"  {name:6s} best tenth of each district: {a:.3f} -> {b:.3f} times random "
            f"(gain {b - a:+.3f}, range {r[0]:+.3f} to {r[1]:+.3f}{' incl. fit noise' if sd is not None else ''})")
    res["gain_share"] = info.get("gain_by_family")
    return res, p_cur


def price(fam, say, years=(2010, 2019)):
    tx = pd.read_parquet(TX, columns=["year", "price", "ptype", "is_new", "leasehold", "postcode"])
    tx = tx[tx.year.between(*years)]
    tx["postcode"] = tx.postcode.astype(str)
    spec = SG.FAMILIES[fam]
    t = pd.read_parquet(SG.ROOT / spec["table"])
    if spec.get("derive"):
        t = getattr(SG, spec["derive"])(t)
    cols = spec.get("inputs", spec["columns"])           # a home-by-home family: its postcode inputs
    t = t.drop_duplicates("postcode").set_index("postcode")[cols]
    tx = tx.join(t, on="postcode", how="inner")
    sec = tx.postcode.str.slice(0, -2)
    y = np.log(tx.price.to_numpy(float))
    D = pd.get_dummies(tx[["year", "ptype"]].astype(str), drop_first=True, dtype=float)
    Xc = np.column_stack([D.to_numpy(), tx.is_new.to_numpy(float), tx.leasehold.to_numpy(float)])
    g = pd.factorize(sec)[0]
    dm = lambda a: a - (pd.DataFrame(a).groupby(g).transform("mean").to_numpy() if a.ndim > 1
                        else pd.Series(a).groupby(g).transform("mean").to_numpy())
    yd, Xd = dm(y), dm(Xc)                            # within sector: every sector its own price level
    blk = _blocks(pd.factorize(tx.postcode)[0].astype(np.int64) * 2654435761)
    res = {}
    for col in cols:
        x = tx[col].to_numpy(float); ok = np.isfinite(x)
        if ok.mean() < 0.2 or np.nanstd(x) == 0:
            continue
        z = np.where(ok, (x - np.nanmean(x)) / np.nanstd(x), 0.0)
        est, rng = LinFit(np.column_stack([Xd, dm(z)]), yd, blk).ci(1.0)
        pc = lambda v: round(100 * (np.exp(v) - 1), 2)
        res[col] = {"pct_per_step": pc(est), "range": [pc(rng[0]), pc(rng[1])]}
    say(f"  {len(tx):,} sales; {sum(1 for v in res.values() if v['range'][0] > 0 or v['range'][1] < 0)} of {len(res)} "
        f"columns carry a price premium clear of zero")
    return res, int(len(tx))


def free_memory(ch):
    """Hand back what the fit held before the column-by-column tests start."""
    import ctypes
    import gc
    ch.release(); ML._TEST.clear(); gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except OSError:
        pass


def coverage(ch, fam):
    L = ch.lookup(fam)
    have = np.isfinite(L).any(axis=1)
    cr = test_rows(ch, (2017, 2018))
    pc = col_of(ch, "pc", cr)
    return {"postcodes": round(float(have.mean()), 4), "test_home_years": round(float(have[pc].mean()), 4)}


def report(fam, R):
    lines = [f"# {fam}: what it is worth", "", SG.FAMILIES[fam]["about"], "",
             f"**Verdict:** {R['verdict']}", "",
             f"Coverage: {100 * R['coverage']['postcodes']:.1f}% of postcodes, "
             f"{100 * R['coverage']['test_home_years']:.1f}% of the home-years the model is tested on.", ""]
    if "adds" in R:
        lines += ["## Does it make the national model better?", "",
                  "| Owners | Current model | With this family | Gain | 95% range |", "|---|---|---|---|---|"]
        for k, lab in (("all", "All"), ("t0_9", "Under 10 years"), ("t10_19", "10 to 19 years"), ("t20p", "20 years or more")):
            v = R["adds"][k]
            r = v.get("range_with_fit_noise", v["range"])
            lines.append(f"| {lab} | {v['current']:.3f} | {v['with']:.3f} | {v['gain']:+.3f} | {r[0]:+.3f} to {r[1]:+.3f} |")
        lines += ["", "Sellers found in the best tenth of each postcode district, times random, 2017 and 2018. "
                  f"The current model is the deployed one: {' + '.join(R.get('against', {}).get('families', CURRENT))}."
                  + (" The range includes the fit's own randomness (SEED_NOISE.md): two fits of the same model differ "
                     "by up to about 0.02, so a gain smaller than that is not evidence." if "range_with_fit_noise" in R["adds"]["all"] else ""), ""]
    if "lfl" in R:
        lines += ["## Each column: sale timing, what is left on top of the model, and price", "",
                  "| Column | Sale chance, points a year per step | Same sign in regions | Left on top of the model | Price per step |",
                  "|---|---|---|---|---|"]
        for col, v in R["lfl"].items():
            t = R.get("on_top", {}).get(col); p = R.get("price", {}).get(col)
            lines.append(f"| {col} | {v['points_per_step']:+.3f} ({v['range'][0]:+.3f} to {v['range'][1]:+.3f}) | "
                         f"{v['regions_same_sign']} | "
                         + (f"{t['points_per_step']:+.3f} ({t['range'][0]:+.3f} to {t['range'][1]:+.3f})" if t else "") + " | "
                         + (f"{p['pct_per_step']:+.1f}% ({p['range'][0]:+.1f} to {p['range'][1]:+.1f})" if p else "") + " |")
        lines += ["", "A step is one standard deviation of the column across the country. Ranges are 95% block-bootstrap ranges.", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("family"); ap.add_argument("--pct", type=int, default=100)
    ap.add_argument("--threads", type=int, default=4); ap.add_argument("--skip-fit", action="store_true")
    ap.add_argument("--panel", default=PANEL); ap.add_argument("--lab", default=LAB); ap.add_argument("--out", default=OUT)
    ap.add_argument("--tx", default=TX)
    a = ap.parse_args()
    globals().update(PANEL=a.panel, LAB=a.lab, OUT=a.out, TX=a.tx)
    fam = a.family
    out = Path(OUT); out.mkdir(parents=True, exist_ok=True)
    log = open(out / f"{fam}.log", "a")

    def say(msg):
        print(msg, flush=True); log.write(msg + "\n"); log.flush()
    ch = ML.Chunks(PANEL)
    assert fam in ch.place, f"{fam} is not a registered place family with a table on disk"
    R = {"family": fam, "about": SG.FAMILIES[fam]["about"], "when": time.strftime("%Y-%m-%d %H:%M"),
         "against": {"name": CUR_NAME, "families": CURRENT}}
    say(f"== {fam}: coverage"); R["coverage"] = coverage(ch, fam); say(f"  {R['coverage']}")
    if not a.skip_fit:
        say(f"== {fam}: does it improve the national model ({a.pct}% of homes)?")
        R["adds"], p_cur = adds_to_model(ch, fam, a.pct, a.threads, say)
        free_memory(ch)                               # the fit's tables are no longer needed; wide families ran out without this
    else:
        p_cur, _ = ML.predict_cached(ch, Path(LAB), a.threads, CUR_NAME, a.pct, CURRENT)
    say(f"== {fam}: like for like, sale timing"); R["lfl"], R["lfl_rows"], R["lfl_sales"] = like_for_like(ch, fam, say)
    say(f"== {fam}: on top of the national model"); R["on_top"] = on_top(ch, fam, p_cur, say)
    say(f"== {fam}: price"); R["price"], R["price_sales"] = price(fam, say)
    if "adds" in R:
        g = R["adds"]["all"]
        rng = g.get("range_with_fit_noise", g["range"])
        R["verdict"] = ("add it: the model finds more sellers and the range is clear of zero" if rng[0] > 0 else
                        "do not add it to the model: no gain clear of zero" + (
                            "; it stays out of search and pricing too (model ranking only)" if SG.FAMILIES[fam].get("never_shown") else
                            "; measured only: never a search filter or a pricing input" if SG.FAMILIES[fam].get("no_auto_deploy") else
                            "; use it for search and pricing" if any(v["range"][0] > 0 or v["range"][1] < 0
                                                                     for v in R["price"].values()) else ""))
    else:
        R["verdict"] = "not fitted (--skip-fit)"
    json.dump(R, open(out / f"{fam}.json", "w"), indent=1)
    (out / f"{fam}.md").write_text(report(fam, R))
    say(f"== {fam}: {R['verdict']}")


if __name__ == "__main__":
    main()
