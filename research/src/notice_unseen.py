"""Homes named in a notice that the sale records do not hold: no sale since 1995 when the year began.

The model scores only homes with a sale on record. A deceased estate is very often a home held for
decades, so most of those notices point to homes the model cannot see at all. This measures how
often such a home is sold (its first sale on record) in the year after 1 January, and fits the small
model the product scores them with (notice_signals.unseen_homes, read by export_site_v5.py).

What the model reads (notice_signals.UNSEEN_COLS): months since the notice, notices at the address,
whether the address is a flat or a named block, and facts about the postcode: how its homes are
owned or rented, how old its residents are, what kinds of home it has, and what share of its
addresses have a sale on record. Care and nursing homes are left out before anything is measured.

The test: homes are split into five folds. Each fold in one year is scored by a model fitted on the
other folds in the other year, so no home and no year scores itself. The model is set against the
plain alternative, one rate for each band of months.

The product's model is then set against a later year it never saw (LATER): how many homes it counts
in, how many first sales it expected, and how many there were.

Rates are lower bounds: an address that fails to match its later sale record counts as not sold.
Only counts and rates are written out.

    python notice_unseen.py

Writes research/outputs/signals/NOTICE_UNSEEN.json and .md, and for the product
research/outputs/lab/notice_unseen.json and model_unseen_<kind>.txt.
"""
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import notice_signals as NS  # noqa: E402

OUT, LAB = Path("research/outputs/signals"), Path("research/outputs/lab")
YEARS = (2017, 2018)
MONTHS = [(1, 6), (7, 12), (13, 24), (25, 36), (37, 48)]
KIND = {"bk": "Bankruptcy order", "dec": "Deceased-estate notice"}
MIN_ROWS = 5000                                         # a kind needs this many homes before it gets a model
PANEL = Path("research/data/panel3")
PAR = dict(objective="binary", learning_rate=0.05, num_leaves=6, min_data_in_leaf=200, lambda_l2=20.0, max_bin=63,
           verbose=-1, seed=7, num_threads=4)
MAX_ROUNDS = 400
FOLDS = 5
BLOCKS = 2048
LATER = 2019                                            # a year after both, never fitted on


def rounds_for(X, y, block):
    """How many rounds predict homes held out of the fit best (four folds of homes)."""
    total = np.zeros(MAX_ROUNDS)
    for f in range(4):
        va = block % 4 == f
        tr, ev = lgb.Dataset(X[~va], y[~va]), {}
        lgb.train({**PAR, "metric": "binary_logloss"}, tr, MAX_ROUNDS, valid_sets=[lgb.Dataset(X[va], y[va], reference=tr)],
                  valid_names=["v"], callbacks=[lgb.record_evaluation(ev)])
        total += np.array(ev["v"]["binary_logloss"]) * va.sum()
    return int(np.argmin(total)) + 1


def fit(X, y, block):
    return lgb.train(PAR, lgb.Dataset(X, y, feature_name=NS.UNSEEN_COLS), rounds_for(X, y, block))


def band_of(months):
    b = np.full(len(months), -1)
    for i, (lo, hi) in enumerate(MONTHS):
        b[(months >= lo) & (months <= hi)] = i
    return b


def by_band(months_tr, y_tr, months_te):
    """The plain alternative: the share sold in each band of months, read off the homes fitted on."""
    btr, bte = band_of(months_tr), band_of(months_te)
    out = np.full(len(months_te), y_tr.mean())
    for i in range(len(MONTHS)):
        if (btr == i).sum() >= 200:
            out[bte == i] = y_tr[btr == i].mean()
    return out


def loss(y, p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def spread(block, *vals):
    """A 95% range for mean(vals[0]) (or the ratio of sums of two) from resampling blocks of homes."""
    sums = [np.bincount(block, v, BLOCKS) for v in vals] + [np.bincount(block, minlength=BLOCKS).astype(float)]
    rng, out = np.random.default_rng(3), []
    for _ in range(1000):
        i = rng.integers(0, BLOCKS, BLOCKS)
        out.append(sums[0][i].sum() / sums[1][i].sum())
    return [float(np.percentile(out, q)) for q in (2.5, 97.5)]


def test(r):
    """Cross-fitted predictions for every row: the model's and the plain alternative's."""
    X, y, year = r[NS.UNSEEN_COLS].to_numpy(np.float32), r.sold.to_numpy(float), r.year.to_numpy()
    block = r.block.to_numpy(); fold = block % FOLDS
    pm, pb, rounds = np.full(len(r), np.nan), np.full(len(r), np.nan), []
    for f in range(FOLDS):
        for a, b in ((YEARS[0], YEARS[1]), (YEARS[1], YEARS[0])):
            tr, te = (fold != f) & (year == a), (fold == f) & (year == b)
            m = fit(X[tr], y[tr], block[tr]); rounds.append(m.num_trees())
            pm[te] = m.predict(X[te], num_threads=4)
            pb[te] = by_band(X[tr][:, 0], y[tr], X[te][:, 0])
    return pm, pb, rounds


def later_year(k, tx, model, min_p):
    """The product's model set against a later year it never saw: the homes it counts in, what it expected, what sold."""
    if int(tx.ym.max()) < LATER * 12 + 11:
        return None
    r = NS.unseen_rows(k, LATER, tx)
    if len(r) < 1000:
        return None
    p = model.predict(r[NS.UNSEEN_COLS].to_numpy(np.float32), num_threads=4)
    y, keep = r.sold.to_numpy(float), p >= min_p
    return {"year": LATER, "homes": int(len(r)), "counted_in": int(keep.sum()), "model_expected": round(float(p[keep].sum())),
            "sold": int(y[keep].sum()), "rate": round(float(y[keep].mean()), 4) if keep.any() else None,
            "left_out": int((~keep).sum()), "left_out_rate": round(float(y[~keep].mean()), 4) if (~keep).any() else None}


def main():
    tx = NS.sales()
    import local_eval as LE
    te = LE.load_test(PANEL, years=YEARS)
    base = float(te["y"].mean())                        # what a home with a sale on record sells at in those years
    del te
    R = {"years": list(YEARS), "homes_on_record_sell_at": round(base, 4), "kinds": {}}
    spec, md = {}, []
    for k in NS.KINDS:
        if not (NS.DIRS[k] / "listing.jsonl").exists():
            continue
        t = NS.linked(k, every=True)
        r = pd.concat([NS.unseen_rows(k, T, tx).assign(year=T) for T in YEARS], ignore_index=True)
        r["block"] = (pd.util.hash_array(r.key.to_numpy(np.int64)) % BLOCKS).astype(np.int64)
        y, block = r.sold.to_numpy(float), r.block.to_numpy()
        bands = []
        for name, m in ([("all", np.ones(len(r), bool))] + [(f"{a} to {b} months before", ((r.months >= a) & (r.months <= b)).to_numpy()) for a, b in MONTHS]
                        + [("a flat or a named block", (r.flat > 0).to_numpy()), ("any other address", (r.flat == 0).to_numpy())]):
            if m.sum() < 50:
                continue
            bands.append({"homes": name, "n": int(m.sum()), "first_sold_in_the_year": int(y[m].sum()), "rate": round(float(y[m].mean()), 4),
                          "range": [round(v, 4) for v in spread(block[m], y[m])], "completes_july_to_june": round(float(r.late[m].mean()), 4)})
            print(k, bands[-1], flush=True)
        K = {"notices": int(len(t)), "share_with_no_home_on_record": round(float((~t.has).mean()), 3),
             "care_or_nursing_homes_left_out": int(t.care.sum()), "home_years": int(len(r)), "bands": bands}
        md += [f"## {KIND[k]}", "",
               f"{len(t):,} notices with an address; {100 * (~t.has).mean():.0f}% name a home with no sale on record at all. "
               f"{int(t.care.sum()):,} at care or nursing homes are left out. Measured on {len(r):,} home-years.", "",
               "| Homes | Number | First sold in the year (95% range) | Completes July to June |", "|---|---|---|---|",
               *[f"| {b['homes'].capitalize()} | {b['n']:,} | {100 * b['rate']:.1f}% ({100 * b['range'][0]:.1f} to {100 * b['range'][1]:.1f}) | "
                 f"{100 * b['completes_july_to_june']:.1f}% |" for b in bands], ""]
        worth = bool(bands) and bands[0]["range"][0] > base and len(r) >= MIN_ROWS and all((r.year == T).sum() >= 1000 for T in YEARS)
        K["counted_in"] = worth
        if not worth:
            md += [f"Not counted in: these homes do not clearly sell more often than a home on record ({100 * base:.1f}% a year), "
                   "or there are too few to tell.", ""]
            R["kinds"][k] = K
            continue
        pm, pb, rounds = test(r)
        lm, lb = loss(y, pm), loss(y, pb)
        K["test"] = {"log_loss_one_rate_per_band": round(float(lb.mean()), 5), "log_loss_model": round(float(lm.mean()), 5),
                     "change": round(float((lm - lb).mean()), 5), "change_range": [round(v, 5) for v in spread(block, lm - lb)],
                     "sold": int(y.sum()), "model_expected": round(float(pm.sum())), "rounds": [int(min(rounds)), int(max(rounds))]}
        q = pd.qcut(pd.Series(pm).rank(method="first"), 5, labels=False).to_numpy()
        K["test"]["fifths"] = [{"fifth": int(i + 1), "homes": int((q == i).sum()), "model_expected": round(float(pm[q == i].mean()), 4),
                                "sold": round(float(y[q == i].mean()), 4)} for i in range(5)]
        K["test"]["scored_below_a_home_on_record"] = {"homes": int((pm < base).sum()), "sold": round(float(y[pm < base].mean()), 4) if (pm < base).any() else None}
        K["test"]["better_than_bands"] = K["test"]["change_range"][1] < 0
        T_ = K["test"]
        md += [f"The model against one rate per band of months, each home scored by a model that never saw it or its year: log loss "
               f"{T_['log_loss_one_rate_per_band']:.5f} with bands, {T_['log_loss_model']:.5f} with the model, a change of {T_['change']:+.5f} "
               f"({T_['change_range'][0]:+.5f} to {T_['change_range'][1]:+.5f}). The model expected {T_['model_expected']:,} first sales; there were {T_['sold']:,}.", "",
               "| Fifth of homes, by the model's score | Homes | Model expected | Sold in the year |", "|---|---|---|---|",
               *[f"| {['Lowest', 'Second', 'Middle', 'Fourth', 'Highest'][f['fifth'] - 1]} | {f['homes']:,} | {100 * f['model_expected']:.1f}% | {100 * f['sold']:.1f}% |"
                 for f in T_["fifths"]], ""]
        X = r[NS.UNSEEN_COLS].to_numpy(np.float32)
        final = fit(X, y, block)                          # the product's model: both years, every home
        final.save_model(str(LAB / f"model_unseen_{k}.txt"))
        gain = final.feature_importance("gain"); gain = gain / max(gain.sum(), 1e-9)
        K["model"] = {"rounds": final.num_trees(), "share_of_gain": {c: round(float(g), 3) for c, g in sorted(zip(NS.UNSEEN_COLS, gain), key=lambda v: -v[1])}}
        spec[k] = {"file": f"model_unseen_{k}.txt", "columns": NS.UNSEEN_COLS, "min_p": round(base, 4), "rounds": final.num_trees()}
        md += ["What the product's model leans on, by share of its gain: "
               + ", ".join(f"{c} {100 * g:.0f}%" for c, g in list(K["model"]["share_of_gain"].items())[:6]) + ".", ""]
        L = K["later_year"] = later_year(k, tx, final, spec[k]["min_p"])
        if L and L["counted_in"] and L["left_out"]:
            md += [f"Set against {L['year']}, a year the model never saw: it counts in {L['counted_in']:,} of {L['homes']:,} homes and expected "
                   f"{L['model_expected']:,} first sales; there were {L['sold']:,} ({100 * L['rate']:.1f}%). The {L['left_out']:,} homes it "
                   f"leaves out sold at {100 * L['left_out_rate']:.1f}%.", ""]
        R["kinds"][k] = K
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(OUT / "NOTICE_UNSEEN.json", "w"), indent=1)
    json.dump({"what": "models for homes named in a notice with no sale on record: the chance of a first sale in the calendar year",
               "years": list(YEARS), "homes_on_record_sell_at": round(base, 4), "kinds": spec}, open(LAB / "notice_unseen.json", "w"), indent=1)
    head = ["# Homes named in a notice that the sale records do not hold", "",
            "The model scores only homes with a sale on record since 1995. These are the others: homes named in a notice with no",
            f"sale on record when the year began, {YEARS[0]} and {YEARS[1]} together. Homes that do have a record sell at {100 * base:.1f}% a year.",
            "The product counts in a kind of notice only where the whole range is above that, and then only the homes its model",
            "scores above that.", ""]
    foot = ["Lower bounds: an address that fails to match its later sale record counts as not sold.", ""]
    (OUT / "NOTICE_UNSEEN.md").write_text("\n".join(head + md + foot))
    print("\n".join(head + md + foot))


if __name__ == "__main__":
    main()
