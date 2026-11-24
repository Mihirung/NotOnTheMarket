"""Screen: transfers the model has never seen (Price Paid "category B").

The model is built on standard sales only (category A). Since late 2013 the Land Registry
also publishes category B entries: repossessions and sales under a power of sale, purchases
by companies and other non-private buyers, and buy-to-let purchases it can identify from the
mortgage. A home that has passed to a company or a lender is often back on the market within
a year or two, and the transfer comes well before the listing, so unlike an energy
certificate it is an early sign.

For every test home-year, as of 1 January and using nothing dated after it:
  b_since      category B entries on the home since its last standard sale
  b_age        months since the latest of them
  b_ratio      that entry's price over the last standard sale's price
  b_before     category B entries on the home in the 24 months up to its last standard sale
  b_pc_24m     category B entries on other homes in the postcode in the last 24 months

The test is the one in screen_late.py: a small second model on the deployed model's
prediction, aimed at sales completing between July of the year and June of the next (homes
not yet on the market on the scoring day), fitted on one test year and scored on the other.

    python screen_catb.py <ppd_zip_dir>

Writes research/outputs/signals/SCREEN_CATB.json and .md. Addresses are hashed to the same
home key the transactions use and are not kept.
"""
import json
import sys
import zipfile
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

import epc_signals as ES
import local_eval as LE
import screen_late as SL

PANEL, LAB, OUT = SL.PANEL, SL.LAB, SL.OUT
COLS = ["tid", "price", "date", "postcode", "ptype", "is_new", "duration", "paon", "saon", "street", "locality",
        "town", "district", "county", "ppd_cat", "status"]
BCOLS = ["b_since", "b_age", "b_ratio", "b_before", "b_pc_24m"]
M = 100_000


def load_b(zip_dir, years=range(2013, 2020)):
    """Category B entries on homes: (home key, postcode, month, price)."""
    out = []
    for y in years:
        with zipfile.ZipFile(Path(zip_dir) / f"pp-{y}.csv.zip") as zf:
            with zf.open(zf.namelist()[0]) as fh:
                df = pd.read_csv(fh, header=None, names=COLS, keep_default_na=False, na_values=[],
                                 usecols=["price", "date", "postcode", "ptype", "paon", "saon", "ppd_cat"],
                                 dtype={"price": "int64", "postcode": "string", "paon": "string", "saon": "string"})
        df = df[(df.ppd_cat == "B") & (df.ptype != "O") & (df.price > 0) & (df.postcode.str.len() >= 5)]
        pc = df.postcode.str.strip().str.upper()
        key = pc + "|" + df.paon.str.strip().str.upper() + "|" + df.saon.str.strip().str.upper()     # as build_dataset.py
        ts = pd.to_datetime(df.date, format="%Y-%m-%d %H:%M", errors="coerce")
        out.append(pd.DataFrame({"key": pd.util.hash_array(key.to_numpy(dtype=object)).astype("int64"), "postcode": pc.astype(str),
                                 "ym": (ts.dt.year * 12 + ts.dt.month - 1).to_numpy(), "price": df.price.to_numpy()}).dropna())
    return pd.concat(out, ignore_index=True)


def test_rows():
    """The transaction row behind each test home-year (its spell's opening sale)."""
    f = PANEL / "test_rows.npy"
    if f.exists():
        return np.load(f)
    from panel2 import Panel, chunk_rows
    panel = Panel(SL.TX, verbose=False)
    out = []
    for c in (0, 1):
        rows, years, _, _, _ = chunk_rows(panel, c)
        out.append(rows[(years >= 2017) & (years <= 2019)])
    out = np.concatenate(out).astype("int64")
    np.save(f, out)
    return out


def features(b, key, pc, bought, price, t0):
    """The category B columns for homes `key` in postcodes `pc`, bought in month `bought`, scored at month t0."""
    b = b.sort_values(["key", "ym"])
    bk, bym, bpr = b.key.to_numpy(), b.ym.to_numpy(dtype=np.int64), b.price.to_numpy(dtype=np.float64)
    uk, first = np.unique(bk, return_index=True)                    # each home's entries are bk[first[j] : first[j + 1]]
    last = np.r_[first[1:], len(bk)]
    j = np.minimum(np.searchsorted(uk, key), len(uk) - 1); has = uk[j] == key
    out = np.full((len(key), len(BCOLS)), np.nan, np.float32); out[:, 0] = 0; out[:, 3] = 0
    idx = np.nonzero(has)[0]
    for i in idx:                                                    # few homes have any entry: a plain loop is enough
        s = slice(first[j[i]], last[j[i]]); ym, pr = bym[s], bpr[s]
        after = (ym > bought[i]) & (ym < t0[i])
        out[i, 0] = after.sum()
        if after.any():
            k = np.nonzero(after)[0][-1]
            out[i, 1] = t0[i] - ym[k]; out[i, 2] = pr[k] / max(price[i], 1.0)
        out[i, 3] = ((ym <= bought[i]) & (ym >= bought[i] - 24)).sum()
    pcs, pcode = np.unique(b.postcode.to_numpy(), return_inverse=True)
    pkey = np.sort(pcode.astype(np.int64) * M + b.ym.to_numpy(dtype=np.int64))
    q = np.minimum(np.searchsorted(pcs, pc), len(pcs) - 1); hp = pcs[q] == pc
    n = np.searchsorted(pkey, q * M + t0, side="left") - np.searchsorted(pkey, q * M + t0 - 24, side="left")
    own = np.nan_to_num(out[:, 1], nan=1e9) <= 24                    # the home's own entries are not its neighbours'
    out[:, 4] = np.where(hp, n, 0) - np.where(own, 1, 0)
    return out


def main():
    b = load_b(sys.argv[1])
    print(f"category B entries on homes, 2013 to 2019: {len(b):,}", flush=True)
    rows = test_rows()
    tx = pd.read_parquet(SL.TX, columns=["key", "year", "month", "price", "postcode"])
    key = tx.key.to_numpy()[rows]; price = tx.price.to_numpy(dtype=np.float64)[rows]
    bought = (tx.year.to_numpy(dtype=np.int64) * 12 + tx.month.to_numpy(dtype=np.int64) - 1)[rows]
    pc = tx.postcode.astype(str).to_numpy()[rows]
    del tx
    t = LE.load_test(PANEL); ym = SL.end_ym()
    E = np.vstack([np.load(PANEL / f"R_EPC_{c}.npy")[np.load(PANEL / f"year_{c}.npy") >= 2017] for c in (0, 1)]).astype("float32")
    p = np.load(LAB / "preds" / f"{SL.CUR}@100.npy").astype(np.float64)
    keep = t["year"] <= 2018
    tk = {k: v[keep] for k, v in t.items()}
    year, ten, y = tk["year"].astype(np.int64), tk["tenure"], tk["y"]
    start = year * 12
    B = features(b, key[keep], pc[keep], bought[keep], price[keep], start)
    E, p, ym = E[keep], p[keep], ym[keep]
    late = ((ym >= start + 6) & (ym < start + 18)).astype(np.float64)

    d = pd.DataFrame({"g": np.where(B[:, 0] > 0, "an entry since the last standard sale", "none"), "late": late, "year_sale": y, "p": p})
    tab = d.groupby("g").agg(home_years=("late", "size"), sells_later=("late", "mean"), sells_in_year=("year_sale", "mean"), model_said=("p", "mean"))
    print(tab.round(4).to_string(), flush=True)
    rec = B[:, 1] <= 24
    d2 = pd.DataFrame({"g": np.where(rec, "an entry in the last 24 months", "none or older"), "late": late, "year_sale": y, "p": p})
    tab2 = d2.groupby("g").agg(home_years=("late", "size"), sells_later=("late", "mean"), sells_in_year=("year_sale", "mean"), model_said=("p", "mean"))
    print(tab2.round(4).to_string(), flush=True)

    lp = np.clip(p, 1e-6, 1 - 1e-6)
    Z = np.column_stack([np.log(lp / (1 - lp)), ten, E, B]); names = ["model", "tenure"] + ES.COLS + BCOLS
    nE = 2 + len(ES.COLS)
    sets = {"second step": list(range(2)), "with certificates": list(range(nE)),
            "with category B": [0, 1] + list(range(nE, nE + len(BCOLS))), "with both": list(range(nE + len(BCOLS)))}
    pred = {k: np.empty(len(y)) for k in sets}
    par = dict(objective="binary", learning_rate=0.04, num_leaves=31, min_data_in_leaf=1000, feature_fraction=0.9,
               bagging_fraction=0.7, bagging_freq=1, lambda_l2=10, verbose=-1, seed=7, num_threads=4)
    for a, c in ((2017, 2018), (2018, 2017)):
        tr, te = year == a, year == c
        for k, cols in sets.items():
            m = lgb.train(par, lgb.Dataset(Z[tr][:, cols], late[tr], feature_name=[names[i] for i in cols]), 250)
            pred[k][te] = m.predict(Z[te][:, cols])
    R = {"entries": int(len(b)), "rows": int(len(y)), "with_entry_since": int((B[:, 0] > 0).sum()),
         "since": tab.reset_index().to_dict("records"), "recent": tab2.reset_index().to_dict("records"), "bands": {}}
    md = ["# Screen: transfers the model has never seen (Price Paid category B)", "",
          "Later sellers (completing July of the year to June of the next) found in the best tenth of each postcode",
          "district, times random, test years 2017 and 2018. Ranges are 95% and cover sampling only.", "",
          "| Owners | Deployed | Second step | With category B | Gain | With certificates | With both | Gain over certificates |",
          "|---|---|---|---|---|---|---|---|"]
    for nm, lo, hi in LE.TENURE:
        L = LE.Local(tk, lo, hi); L.y = late[L.keep]
        tops = {k: L.top_mask(v[L.keep]) for k, v in pred.items()}; tops["deployed"] = L.top_mask(p[L.keep])
        res = {k: round(L.lift(v), 4) for k, v in tops.items()}
        for nmg, a, c in (("gain", "second step", "with category B"), ("gain_over_certificates", "with certificates", "with both")):
            rng = np.random.default_rng(3); dd = []
            for _ in range(SL.BOOT):
                w = rng.poisson(1.0, LE.N_BLOCKS).astype(float)[L.block]
                dd.append(L.lift(tops[c], w) - L.lift(tops[a], w))
            res[nmg] = [round(res[c] - res[a], 4)] + [round(float(np.percentile(dd, q)), 4) for q in (2.5, 97.5)]
        R["bands"][nm] = res
        g1, g2 = res["gain"], res["gain_over_certificates"]
        md.append(f"| {nm} | {res['deployed']:.3f} | {res['second step']:.3f} | {res['with category B']:.3f} | {g1[0]:+.3f} ({g1[1]:+.3f} to {g1[2]:+.3f}) | "
                  f"{res['with certificates']:.3f} | {res['with both']:.3f} | {g2[0]:+.3f} ({g2[1]:+.3f} to {g2[2]:+.3f}) |")
        print(nm, res, flush=True)
    fmt = lambda tb: [f"| {r.g} | {int(r.home_years):,} | {100 * r.sells_later:.1f}% | {100 * r.sells_in_year:.1f}% | {100 * r.model_said:.1f}% |"   # noqa: E731
                      for r in tb.reset_index().itertuples()]
    md += ["", "## How often homes with an entry go on to sell", "",
           "| Home on 1 January | Home-years | Sells July to June | Sells in the calendar year | The model said (calendar year) |", "|---|---|---|---|---|",
           *fmt(tab), *fmt(tab2), ""]
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(OUT / "SCREEN_CATB.json", "w"), indent=1, default=str)
    (OUT / "SCREEN_CATB.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
