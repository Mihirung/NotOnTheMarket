"""Do planning applications predict a sale, what gets approved, and what does
an approved job add to a home's value?

Uses the applications planning_link.py joined to homes, the sale records,
and the national model. The homes studied are every home with a sale record
in the council areas fetched; years 2006 to 2019.

  1. Timing      the yearly chance of a sale after an application, by what
                 happened to it (approved, refused, withdrawn, still
                 undecided), like for like: the same kind of home, years
                 owned, price band and year
  2. By year     the chance of a sale each year from three years before an
                 approved (or refused) application to six years after it
  3. By job      the chance of a sale in the three years after approval, by
                 the kind of job
  4. On top      whether these add to the national model's own score: a
                 small model with and without them, trained on 2006-2014,
                 judged on 2015-2019
  5. Approval    what predicts approval: the job, where the home stands
                 (conservation area, listed, Article 4 ...), its type and
                 garden, the council and the year
  6. Value       repeat sales across an approved job against neighbours'
                 repeat sales over the same years with no application: the
                 extra growth by kind of job

Writes research/outputs/planning/planning_tests.json and .md.

Usage: python planning_analysis.py
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
OUT = Path("research/outputs/planning")
APPS = Path("research/data/planning/applications.parquet")
Y_FROM, Y_TO = 2006, 2019
NB, BOOT = 256, 200
WORK = ["rear", "two_storey", "loft", "side", "wraparound", "basement", "garage", "outbuilding", "front", "extension"]
JOB_ORDER = ["loft", "two_storey", "rear", "side", "wraparound", "basement", "garage", "outbuilding", "front",
             "extension", "new_home", "split", "listed", "lawful", "alterations", "windows", "boundary", "trees",
             "commercial", "change_of_use",
             "demolition", "other"]


def say(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- like-for-like fits
class Fit:
    """Least squares on block sums, so resampling homes (blocks) is cheap."""

    def __init__(self, X, y, blk, w=None):
        w = np.ones(len(y)) if w is None else w
        order = np.argsort(blk, kind="stable"); cuts = np.searchsorted(blk[order], np.arange(NB + 1))
        X, y, w = X[order], y[order], w[order]
        self.XtX = np.stack([(X[a:b] * w[a:b, None]).T @ X[a:b] for a, b in zip(cuts[:-1], cuts[1:])])
        self.Xty = np.stack([(X[a:b] * w[a:b, None]).T @ y[a:b] for a, b in zip(cuts[:-1], cuts[1:])])

    def coef(self, wb=None):
        A = self.XtX.sum(0) if wb is None else np.tensordot(wb, self.XtX, 1)
        c = self.Xty.sum(0) if wb is None else wb @ self.Xty
        return np.linalg.lstsq(A, c, rcond=None)[0]

    def ci(self, idx, seed=1):
        rng = np.random.default_rng(seed)
        est = self.coef()[idx]
        bs = np.array([self.coef(rng.poisson(1.0, NB).astype(float))[idx] for _ in range(BOOT)])
        return est, np.percentile(bs, 2.5, axis=0), np.percentile(bs, 97.5, axis=0)


def controls(df):
    """Dummies for the kind of home, years owned, price band and year."""
    ten = pd.cut(df.tenure, [-1, 1, 4, 9, 19, 200], labels=False)
    parts = [pd.get_dummies(df.ptype, prefix="pt"), pd.get_dummies(ten, prefix="ten"),
             pd.get_dummies(df.year, prefix="yr"), pd.get_dummies(pd.cut(df.price_pct, 5, labels=False), prefix="pp"),
             df[["leasehold"]].astype(float)]
    return pd.concat(parts, axis=1).astype(float)


def effect(df, cols, w):
    """Each column's change in the yearly chance of a sale (percentage points), like for like."""
    C = controls(df)
    X = np.column_stack([C.to_numpy(), df[cols].to_numpy(float)])
    f = Fit(X, df.y.to_numpy(float), df.blk.to_numpy(), w)
    k = np.arange(C.shape[1], X.shape[1])
    est, lo, hi = f.ci(k)
    base = float(np.average(df.y, weights=w))
    out = {}
    for j, c in enumerate(cols):
        n = int((df[c] > 0).sum())
        out[c] = {"rows": n, "points": round(100 * est[j], 2), "range": [round(100 * lo[j], 2), round(100 * hi[j], 2)],
                  "times_base": round((base + est[j]) / base, 2) if base else None}
    return out, base


# ---------------------------------------------------------------- the study population
def study(apps):
    """Every home with a sale record in the council areas fetched."""
    from export_site_v5 import lad_names
    lad = lad_names()
    a = apps.dropna(subset=["postcode"])
    a = a.assign(lad=lad.reindex(a.postcode).to_numpy())
    area_lad = a.groupby("area_name").lad.agg(lambda s: s.value_counts().index[0] if s.notna().any() else None)
    lads = set(area_lad.dropna())
    pcs = set(lad.index[lad.isin(lads)])
    say(f"study: {len(area_lad)} council areas -> {len(lads)} local authorities, {len(pcs):,} postcodes")
    return pcs, area_lad.to_dict()


def risk_rows(apps, pcs):
    """Home-years at risk of a sale, with the home's planning history as it stood
    at the start of each year."""
    from panel2 import Panel
    P = Panel("research/data/transactions.parquet")
    in_study = np.isin(P.pc_names[P.pc], list(pcs))
    treated_keys = set(apps.key.dropna().astype("int64").tolist())
    k = P.key
    sample = (np.abs(k) // 7) % 5 == 0                    # every home with an application, one in five of the rest
    spells = np.nonzero(in_study & (np.isin(k, list(treated_keys)) | sample))[0]
    rows, years, y = P.expand(spells, y_from=Y_FROM, y_to=Y_TO)
    key = P.key[rows]
    w = np.where(np.isin(key, list(treated_keys)), 1.0, 5.0)
    df = pd.DataFrame({"row": rows, "key": key, "year": years, "y": y, "w": w,
                       "tenure": years - P.year[rows], "ptype": np.array(list("DSTF"))[np.clip(P.ptype[rows], 0, 3)],
                       "leasehold": P.lease[rows], "price_pct": P.price_pct[rows],
                       "blk": ((np.abs(key) // 100) % NB).astype(int)})
    say(f"{len(df):,} home-years ({int((df.w == 1).sum()):,} at homes with an application), sale rate {np.average(df.y, weights=df.w):.4f}")
    return P, df


def history(df, apps):
    """For each home-year: what had happened at the home by the start of that year."""
    a = apps.dropna(subset=["key", "start"]).copy()
    a["key"] = a.key.astype("int64")
    a["sy"] = a.start.dt.year
    a["dy"] = a.decided.dt.year
    a = a[a.job.isin(JOB_ORDER)]
    out = df[["key", "year"]].copy()
    idx = pd.MultiIndex.from_frame(out[["key", "year"]])
    m = out.drop_duplicates().merge(a[["key", "sy", "dy", "state", "job"]], on="key")
    for col, cond in (("applied_1y", m.sy == m.year - 1),
                      ("applied_2_3y", m.sy.between(m.year - 3, m.year - 2)),
                      ("approved_1y", (m.state == "approved") & (m.dy == m.year - 1)),
                      ("approved_2_3y", (m.state == "approved") & m.dy.between(m.year - 3, m.year - 2)),
                      ("refused_1y", (m.state == "refused") & (m.dy == m.year - 1)),
                      ("refused_2_3y", (m.state == "refused") & m.dy.between(m.year - 3, m.year - 2)),
                      ("withdrawn_1y", (m.state == "withdrawn") & (m.dy.fillna(m.sy) == m.year - 1)),
                      ("pending", (m.sy < m.year) & ((m.dy >= m.year) | (m.state == "undecided")))):
        hit = pd.MultiIndex.from_frame(m.loc[cond.to_numpy(), ["key", "year"]])
        out[col] = idx.isin(hit).astype(float)
    # event time from the first approved and the first refused application
    for st in ("approved", "refused"):
        first = a[a.state == st].groupby("key").sy.min()
        out[f"since_{st}"] = out.year - first.reindex(out.key).to_numpy()
    # what any earlier application said about the home itself (era, kind)
    hint_cols = [c for c in a.columns if c.startswith("hint_")]
    if hint_cols:
        hh = a.groupby("key")[hint_cols].max()
        for c in hint_cols:
            out[c] = hh[c].reindex(out.key).fillna(False).to_numpy().astype(float)
    # main job of approvals in the three years before
    mm = m[(m.state == "approved") & m.dy.between(m.year - 3, m.year - 1)]
    for j in JOB_ORDER:
        hit = pd.MultiIndex.from_frame(mm.loc[mm.job == j, ["key", "year"]])
        out[f"job_{j}"] = idx.isin(hit).astype(float)
    return out.drop(columns=["key", "year"])


# ---------------------------------------------------------------- tests
def test_on_top(P, df, H):
    """Do the planning features add to the national model's score?"""
    import lightgbm as lgb
    import signals as SG
    from panel2 import full_features
    dep = json.load(open("research/outputs/lab/lab_deploy.json"))
    fams = dep.get("families") or ["BASE", "HIST", "GEO", "VIEW"]
    bst = lgb.Booster(model_file="research/outputs/lab/model_deploy.txt")
    lookups = {f: SG.lookup(f, P.pc_names) for f in fams if f not in SG.TIME_VARYING}
    score = np.zeros(len(df), np.float32)
    for a in range(0, len(df), 500_000):
        b = min(a + 500_000, len(df))
        score[a:b] = bst.predict(full_features(P, df.row.to_numpy()[a:b], df.year.to_numpy()[a:b], fams, lookups), num_threads=4)
    lg = np.log(np.clip(score, 1e-4, 1 - 1e-4) / (1 - np.clip(score, 1e-4, 1 - 1e-4)))
    feats = [c for c in H.columns if not c.startswith("since_")]
    Z = np.column_stack([lg, H[feats].to_numpy(float)])
    tr = df.year.to_numpy() <= 2014; te = ~tr
    y = df.y.to_numpy(); w = df.w.to_numpy()
    res = {}
    for name, cols in (("model alone", [0]), ("model + planning", list(range(Z.shape[1])))):
        m = lgb.train({"objective": "binary", "learning_rate": 0.05, "num_leaves": 15, "min_data_in_leaf": 200,
                       "verbose": -1, "num_threads": 4}, lgb.Dataset(Z[tr][:, cols], y[tr], weight=w[tr]), 200)
        p = m.predict(Z[te][:, cols])
        res[name] = p
    out = {}
    yt, wt, blk = y[te], w[te], df.blk.to_numpy()[te]
    rng = np.random.default_rng(3)

    def lift(p, wb):
        ww = wt * wb[blk]
        cut = np.quantile(p, 0.9)
        top = p >= cut
        return (np.sum(ww[top] * yt[top]) / np.sum(ww[top])) / (np.sum(ww * yt) / np.sum(ww))
    one = np.ones(NB)
    base_l, new_l = lift(res["model alone"], one), lift(res["model + planning"], one)
    d = [lift(res["model + planning"], b) - lift(res["model alone"], b) for b in (rng.poisson(1.0, NB).astype(float) for _ in range(BOOT))]
    out = {"lift_top10_model": round(base_l, 3), "lift_top10_with_planning": round(new_l, 3),
           "gain": round(new_l - base_l, 3), "gain_range": [round(float(np.percentile(d, 2.5)), 3), round(float(np.percentile(d, 97.5)), 3)],
           "test_home_years": int(te.sum())}
    return out


def test_approval(apps):
    """What predicts approval among decided applications."""
    import lightgbm as lgb
    from pyproj import Transformer
    from sklearn.model_selection import GroupKFold
    a = apps[apps.state.isin(["approved", "refused"]) & apps.job.isin(JOB_ORDER)].copy()
    a["y"] = (a.state == "approved").astype(int)
    # where the application stands: constraints at the nearest address position
    pcon = pd.read_parquet("research/data/planning/constraints_positions.parquet")
    from scipy.spatial import cKDTree
    have = a.location_x.notna()
    e, n = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True).transform(a.location_x[have].to_numpy(), a.location_y[have].to_numpy())
    box = (pcon.x > e.min() - 500) & (pcon.x < e.max() + 500) & (pcon.y > n.min() - 500) & (pcon.y < n.max() + 500)
    pc = pcon[box]
    d, i = cKDTree(np.column_stack([pc.x + 0.5, pc.y + 0.5])).query(np.column_stack([e, n]))
    bits = np.zeros(len(a), np.uint16); bits[have.to_numpy()] = np.where(d < 40, pc.bits.to_numpy()[i], 0)
    from planning_constraints import BITS
    for nm, b in BITS.items():
        a[f"c_{nm}"] = (bits >> b) & 1
    a["year"] = a.start.dt.year
    a["area"] = a.area_name.astype("category")
    a["job_c"] = pd.Categorical(a.job, categories=JOB_ORDER)
    X = pd.concat([pd.get_dummies(a.job_c, prefix="job").astype(float), a[[f"c_{k}" for k in BITS]].astype(float),
                   a[["year"]].astype(float), pd.get_dummies(a.area, prefix="area").astype(float)], axis=1)
    p = np.zeros(len(a))
    for tr, te in GroupKFold(5).split(X, a.y, groups=(a.key.fillna(-1).astype("int64") % 997).to_numpy()):
        m = lgb.train({"objective": "binary", "learning_rate": 0.05, "num_leaves": 31, "verbose": -1, "num_threads": 4},
                      lgb.Dataset(X.iloc[tr], a.y.iloc[tr]), 300)
        p[te] = m.predict(X.iloc[te])
    from sklearn.metrics import roc_auc_score
    auc = roc_auc_score(a.y, p)
    rates = a.groupby("job").y.agg(["mean", "size"]).rename(columns={"mean": "approved", "size": "decided"})
    a["heritage"] = (a.c_conservation | a.c_listed | a.c_world_heritage).astype(bool)
    by_her = a.groupby(["job", "heritage"]).y.mean().unstack()
    by_area = a.groupby("area_name", observed=True).y.mean()
    m = lgb.train({"objective": "binary", "learning_rate": 0.05, "num_leaves": 31, "verbose": -1, "num_threads": 4},
                  lgb.Dataset(X, a.y), 300)
    OUT.mkdir(parents=True, exist_ok=True); m.save_model(str(OUT / "approval_model.txt"))
    json.dump(list(X.columns), open(OUT / "approval_model_columns.json", "w"))
    return {"decided": int(len(a)), "approved_share": round(float(a.y.mean()), 3), "cv_auc": round(float(auc), 3),
            "by_job": {j: {"approved": round(float(r.approved), 3), "decided": int(r.decided)} for j, r in rates.iterrows()},
            "by_job_heritage": {j: {("in heritage area" if k else "not"): round(float(v), 3) for k, v in r.dropna().items()}
                                for j, r in by_her.iterrows()},
            "by_area": {k: round(float(v), 3) for k, v in by_area.items()}}


def test_value(apps):
    """Extra price growth between two sales of a home across an approved job,
    against the same postcode sector's repeat sales over the same years."""
    tx = pd.read_parquet("research/data/transactions.parquet", columns=["key", "year", "month", "price", "postcode", "ptype"])
    a = apps[(apps.state == "approved") & apps.key.notna()].copy()
    a["key"] = a.key.astype("int64")
    keys = set(a.key.tolist())
    tx["postcode"] = tx.postcode.astype(str)
    tx["sector"] = tx.postcode.str[:-2]
    sectors = set(tx.sector[tx.key.isin(keys)])
    tx = tx[tx.sector.isin(sectors)].sort_values(["key", "year", "month"])
    tx["t"] = tx.year + (tx.month - 0.5) / 12
    nxt = tx.groupby("key").shift(-1)
    pairs = tx.assign(t2=nxt.t, p2=nxt.price).dropna(subset=["t2"])
    pairs = pairs[(pairs.t2 - pairs.t).between(1, 15) & (pairs.ptype != "F")]
    pairs["g"] = np.log(pairs.p2 / pairs.price)
    pairs["y1"] = pairs.t.astype(int); pairs["y2"] = pairs.t2.astype(int)
    a["td"] = a.decided.dt.year + (a.decided.dt.month - 0.5) / 12
    a["ts"] = a.start.dt.year + (a.start.dt.month - 0.5) / 12
    m = pairs.reset_index().merge(a[["key", "ts", "td", "job"]], on="key")
    m = m[(m.ts > m.t) & (m.td < m.t2 - 0.25)]          # applied after the first sale, approved before the second
    treated = m.groupby("index").job.first()
    any_app = set(a.key.tolist()) | set(apps.key.dropna().astype("int64").tolist())
    ctrl = pairs[~pairs.key.isin(any_app)]
    norm = ctrl.groupby(["sector", "y1", "y2"]).g.median().rename("g0")
    norm_d = ctrl.assign(d=ctrl.sector.str.split(" ").str[0]).groupby(["d", "y1", "y2"]).g.median().rename("g0d")
    tp = pairs.loc[treated.index].assign(job=treated.to_numpy())
    tp = tp.join(norm, on=["sector", "y1", "y2"])
    tp["d"] = tp.sector.str.split(" ").str[0]
    tp = tp.join(norm_d, on=["d", "y1", "y2"])
    tp["excess"] = tp.g - tp.g0.fillna(tp.g0d)
    tp = tp.dropna(subset=["excess"])
    rng = np.random.default_rng(5)
    out = {}
    for j, g in tp.groupby("job"):
        if len(g) < 40:
            continue
        x = g.excess.to_numpy()
        bs = [np.median(rng.choice(x, len(x))) for _ in range(BOOT)]
        med_price = float(g.price.median())
        out[j] = {"repeat_sales": int(len(g)), "extra_growth_pct": round(100 * (np.exp(np.median(x)) - 1), 1),
                  "range_pct": [round(100 * (np.exp(np.percentile(bs, 2.5)) - 1), 1), round(100 * (np.exp(np.percentile(bs, 97.5)) - 1), 1)],
                  "typical_first_price": round(med_price, -3)}
    ctrl_x = (ctrl.g - ctrl.join(norm, on=["sector", "y1", "y2"]).g0).dropna()
    out["_neighbours_without"] = {"repeat_sales": int(len(ctrl_x)), "extra_growth_pct": round(100 * (np.exp(np.median(ctrl_x)) - 1), 1)}
    return out


def main():
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    apps = pd.read_parquet(APPS)
    R = {"applications": int(len(apps)), "council_areas": int(apps.area_name.nunique()),
         "linked_to_a_home_with_sales": int(apps.on_sale_record.sum()),
         "linked_share": round(float(apps.on_sale_record.mean()), 3)}
    say(R)
    linked = apps[apps.on_sale_record]
    pcs, area_lad = study(apps); R["areas"] = area_lad
    P, df = risk_rows(linked, pcs)
    H = history(df, linked)
    D = pd.concat([df.reset_index(drop=True), H.reset_index(drop=True)], axis=1)
    w = D.w.to_numpy()
    timing = ["applied_1y", "applied_2_3y", "approved_1y", "approved_2_3y", "refused_1y", "refused_2_3y", "withdrawn_1y", "pending"]
    R["timing"], R["base_rate"] = effect(D, timing, w)
    say("timing:", R["timing"])
    ev = {}
    for st in ("approved", "refused"):
        cols = []
        for k in range(-3, 7):
            c = f"ev_{st}_{k}"; D[c] = (D[f"since_{st}"] == k).astype(float); cols.append(c)
        e, _ = effect(D, cols, w)
        ev[st] = {int(c.split("_")[-1]): v for c, v in e.items()}
    R["by_year"] = ev
    say("by year:", ev)
    jobs = [f"job_{j}" for j in JOB_ORDER if D[f"job_{j}"].sum() >= 200]
    R["by_job"], _ = effect(D, jobs, w)
    say("by job:", R["by_job"])
    hints = [c for c in H.columns if c.startswith("hint_") and D[c].sum() >= 200]
    if hints:
        R["by_description_of_home"], _ = effect(D, hints, w)
        say("what the description says about the home:", R["by_description_of_home"])
    R["on_top_of_model"] = test_on_top(P, D, H)
    say("on top:", R["on_top_of_model"])
    del P
    R["approval"] = test_approval(apps)
    say("approval:", {k: v for k, v in R["approval"].items() if k != "by_area"})
    R["value_added"] = test_value(apps)
    say("value:", R["value_added"])
    R["seconds"] = round(time.time() - t0)
    json.dump(R, open(OUT / "planning_tests.json", "w"), indent=1, default=str)
    say(f"wrote {OUT / 'planning_tests.json'}")


if __name__ == "__main__":
    main()
