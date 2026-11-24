"""Quick screen: does an energy certificate lodged before a sale predict it?

A home needs a valid energy certificate before it can be marketed. A certificate
lodged "for a marketed sale" with no sale yet is therefore a home on the market.

No address field of the certificate data is used (licence: epc_fetch.py). A
certificate is placed in a postcode by its UPRN, and described by its kind of
home (detached, semi, terraced, flat). So the signal here is at the level of
"homes of this kind in this postcode": how many sale certificates were lodged
there in the months before 1 January, set against the sales already completed
and the number of such homes.

For the test homes (2017 and 2018), a small second model is fitted on one year
from [the deployed model's prediction + these counts] and scored on the other.
A gain says the full build is worth it; it is a screen, not the final test.

    python screen_epc.py

Writes research/outputs/signals/SCREEN_EPC.json and .md.
"""
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import assess_signal as A  # noqa: E402
import local_eval as LE  # noqa: E402
import panel2 as P2  # noqa: E402

TX, EPC = "research/data/transactions.parquet", Path("research/data/epc")
FORM = {"Detached": 0, "Semi-Detached": 1, "Mid-Terrace": 2, "End-Terrace": 2, "Enclosed Mid-Terrace": 2, "Enclosed End-Terrace": 2}
KIND = {"marketed sale": 0, "non marketed sale": 0, "rental (private)": 1, "rental": 1}          # everything else: 2 (other)
SKIP = {"new dwelling", "rental (social)"}                    # after lower-casing: the wording changes from year to year
CANDS = ["cert_sale_3m", "cert_sale_6m", "cert_sale_12m", "cert_sale_24m", "cert_rent_24m", "cert_other_12m",
         "sales_3m", "sales_6m", "sales_12m", "homes_kind", "uprn_pc", "cert_any_24m",
         "unsold_6m", "unsold_12m", "unsold_6m_share", "unsold_12m_share", "months_owned"]


def certificates(pc_names, years):
    """Certificates of those years as (postcode code, kind of home, kind of certificate, month index)."""
    t = pd.concat([pd.read_parquet(EPC / f"certificates_{y}.parquet", columns=["uprn", "lodged", "transaction", "tenure", "ptype", "form"])
                   for y in years], ignore_index=True)
    t["transaction"] = t.transaction.str.lower().str.replace("-", " ").str.strip()
    social = t.tenure.fillna("").str.lower().str.contains("social")            # "Rental" covers council and housing-association lets in later years
    t = t[~t.transaction.isin(SKIP) & ~(social & t.transaction.fillna("").str.startswith("rental"))]
    home = np.where(t.ptype.isin(["Flat", "Maisonette"]), 3, t.form.map(FORM).fillna(-1)).astype(np.int8)
    kind = t.transaction.map(KIND).fillna(2).astype(np.int8).to_numpy()
    u = pd.read_parquet("research/data/onsud/uprn_postcode.parquet")
    code = pd.Index(pc_names).get_indexer(u.postcode.cat.categories)          # ONSUD postcode -> the panel's postcode code
    uu = u.uprn.to_numpy(); o = np.argsort(uu); uu = uu[o]; upc = code[u.postcode.cat.codes.to_numpy()][o]
    n_uprn = np.bincount(upc[upc >= 0], minlength=len(pc_names))               # addresses in each postcode
    del u
    i = np.searchsorted(uu, t.uprn.to_numpy()); i = np.minimum(i, len(uu) - 1)
    ok = (uu[i] == t.uprn.to_numpy())
    pc = np.where(ok, upc[i], -1)
    ym = (t.lodged.dt.year * 12 + t.lodged.dt.month - 1).to_numpy()
    keep = (pc >= 0) & (home >= 0)
    print(f"certificates {len(t):,}; placed in a postcode with sales and a known kind of home: {keep.mean():.1%}", flush=True)
    return pc[keep], home[keep], kind[keep], ym[keep], t.uprn.to_numpy()[keep], n_uprn


def window(key_sorted, base, t0, lo, hi):
    """Events with month in [t0 - hi, t0 - lo) for each row (key = group * 100000 + month)."""
    return np.searchsorted(key_sorted, base + t0 - lo, side="left") - np.searchsorted(key_sorted, base + t0 - hi, side="left")


def main():
    panel = P2.Panel(TX)
    month = pd.read_parquet(TX, columns=["month"]).month.to_numpy().astype(np.int64)
    ym_tx = panel.year.astype(np.int64) * 12 + month - 1
    cpc, chome, ckind, cym, cuprn, n_uprn = certificates(panel.pc_names, (2015, 2016, 2017))
    G = lambda pc, home: pc.astype(np.int64) * 4 + home                         # noqa: E731  (postcode, kind of home)
    ckeys = [np.sort(G(cpc[ckind == k], chome[ckind == k]) * 100_000 + cym[ckind == k]) for k in range(3)]
    skey = np.sort(G(panel.pc, panel.ptype) * 100_000 + ym_tx)
    first = np.ones(len(panel.key), bool); first[1:] = panel.key[1:] != panel.key[:-1]
    # homes of each kind in each postcode with a sale on record before the year scored (nothing from later)
    homes_kind = {T: np.bincount(G(panel.pc[first & (panel.year < T)], panel.ptype[first & (panel.year < T)]),
                                 minlength=len(panel.pc_names) * 4) for T in (2017, 2018, 2019)}
    print({k: int((ckind == k).sum()) for k in range(3)}, "certificates for sale, rental, other", flush=True)

    parts = []
    for c in (0, 1):
        lo, hi = c * P2.CHUNK_BUCKETS, (c + 1) * P2.CHUNK_BUCKETS
        spells = np.nonzero((panel.bucket >= lo) & (panel.bucket < hi))[0]
        rows, years, label = panel.expand(spells)
        m = (years >= 2017) & (years <= 2019)
        assert np.array_equal(label[m], np.load(f"{A.PANEL}/y_{c}.npy")[np.load(f"{A.PANEL}/year_{c}.npy") >= 2017]), "row order"
        rows, years = rows[m], years[m]
        g = G(panel.pc[rows], panel.ptype[rows]); base = g * 100_000; t0 = years.astype(np.int64) * 12
        owned = t0 - ym_tx[rows]
        f = {}
        f["cert_sale_3m"] = window(ckeys[0], base, t0, 0, 3); f["cert_sale_6m"] = window(ckeys[0], base, t0, 0, 6)
        f["cert_sale_12m"] = window(ckeys[0], base, t0, 0, 12); f["cert_sale_24m"] = window(ckeys[0], base, t0, 0, 24)
        f["cert_rent_24m"] = window(ckeys[1], base, t0, 0, 24); f["cert_other_12m"] = window(ckeys[2], base, t0, 0, 12)
        for k in (3, 6, 12):                             # sales already completed there (the home's own purchase is not one)
            f[f"sales_{k}m"] = np.maximum(window(skey, base, t0, 0, k) - (owned <= k), 0)
        f["homes_kind"] = np.select([years == T for T in homes_kind], [homes_kind[T][g] for T in homes_kind])
        f["uprn_pc"] = n_uprn[panel.pc[rows]]
        f["cert_any_24m"] = sum(window(ckeys[k], base, t0, 0, 24) for k in range(3))
        for k in (6, 12):                                # certificates lodged for a sale that has not happened yet
            f[f"unsold_{k}m"] = np.maximum(f[f"cert_sale_{k}m"] - f[f"sales_{k}m"], 0)
            f[f"unsold_{k}m_share"] = f[f"unsold_{k}m"] / np.maximum(f["homes_kind"], 1)
        f["months_owned"] = owned
        parts.append(np.column_stack([np.asarray(f[k], np.float32) for k in CANDS]))
    X = np.vstack(parts); del panel
    t = LE.load_test(A.PANEL)
    p = np.load(Path(A.LAB) / "preds" / f"{A.CUR_NAME}@100.npy").astype(np.float64)
    assert len(p) == len(X) == len(t["y"])
    keep = t["year"] <= 2018
    X, p, y, year, ten = X[keep], p[keep], t["y"][keep], t["year"][keep], t["tenure"][keep]
    tk = {k: v[keep] for k, v in t.items()}

    # the plain picture first: owners of 9 years or more (they need a new certificate to sell), by certificates not yet matched by a sale
    ix = {c: i for i, c in enumerate(CANDS)}
    long_ = ten >= 9
    tab = pd.DataFrame({"unsold": np.minimum(X[long_, ix["unsold_6m"]], 2).astype(int),
                        "homes": pd.cut(X[long_, ix["homes_kind"]], [0, 2, 5, 10, 1e9], labels=["1-2", "3-5", "6-10", "11+"]),
                        "y": y[long_], "p": p[long_]})
    plain = tab.groupby(["unsold", "homes"], observed=True).agg(home_years=("y", "size"), sold=("y", "mean"), model_said=("p", "mean")).round(4)
    print(plain.to_string(), flush=True)

    lp = np.clip(p, 1e-6, 1 - 1e-6); logit = np.log(lp / (1 - lp))
    Z = np.column_stack([logit, ten, X]); names = ["model", "tenure"] + CANDS
    stacked = np.empty(len(y)); base2 = np.empty(len(y))
    par = dict(objective="binary", learning_rate=0.04, num_leaves=31, min_data_in_leaf=1000, feature_fraction=0.9,
               bagging_fraction=0.7, bagging_freq=1, lambda_l2=10, verbose=-1, seed=7, num_threads=4)
    gains = {}
    for a, b in ((2017, 2018), (2018, 2017)):
        tr, te = year == a, year == b
        for cols, dest in ((slice(0, 2), base2), (slice(0, None), stacked)):
            m = lgb.train(par, lgb.Dataset(Z[tr][:, cols], y[tr], feature_name=names[cols]), 250)
            dest[te] = m.predict(Z[te][:, cols])
            if dest is stacked:
                g = m.feature_importance("gain"); gains[a] = {n: round(float(v / g.sum()), 3) for n, v in zip(names, g)}
    R = {"candidates": CANDS, "gain_share": gains, "rows": int(len(y)),
         "plain": [{"unsold_certificates_6m": int(u), "homes_of_this_kind_in_postcode": str(h), **r.to_dict()} for (u, h), r in plain.iterrows()]}
    rows_md = []
    for nm, lo, hi in LE.TENURE:
        Lk = LE.Local(tk, lo, hi)
        res = {k: round(Lk.lift(Lk.top_mask(pp[Lk.keep])), 4) for k, pp in
               (("deployed", p), ("second step, no certificates", base2), ("second step, with certificates", stacked))}
        ma, mb = Lk.top_mask(base2[Lk.keep]), Lk.top_mask(stacked[Lk.keep])
        rng = np.random.default_rng(3); d = []
        for _ in range(A.BOOT):
            w = rng.poisson(1.0, LE.N_BLOCKS).astype(float)[Lk.block]
            d.append(Lk.lift(mb, w) - Lk.lift(ma, w))
        res["gain_from_certificates"] = round(res["second step, with certificates"] - res["second step, no certificates"], 4)
        res["range"] = [round(float(np.percentile(d, q)), 4) for q in (2.5, 97.5)]
        R[nm] = res
        rows_md.append(f"| {nm} | {res['deployed']:.3f} | {res['second step, no certificates']:.3f} | {res['second step, with certificates']:.3f} | "
                       f"{res['gain_from_certificates']:+.3f} | {res['range'][0]:+.3f} to {res['range'][1]:+.3f} |")
        print(nm, res, flush=True)
    print("gain share", gains, flush=True)
    json.dump(R, open(Path(A.OUT) / "SCREEN_EPC.json", "w"), indent=1)
    md = ["# Screen: energy certificates lodged before a sale", "",
          "Certificates are placed by UPRN in a postcode and by kind of home; no address field is used. Sellers found in the best tenth of each district, times random, 2017 and 2018.", "",
          "| Owners | Deployed model | Second step without | Second step with certificates | Gain | 95% range |", "|---|---|---|---|---|---|", *rows_md, "",
          "## Owners of 9 years or more: certificates lodged for a sale in the last 6 months and not yet matched by a sale", "",
          "| Unmatched certificates | Homes of this kind in the postcode | Home-years | Sold in the year | The model said |", "|---|---|---|---|---|",
          *[f"| {'2 or more' if u == 2 else u} | {h} | {int(r.home_years):,} | {100 * r.sold:.1f}% | {100 * r.model_said:.1f}% |" for (u, h), r in plain.iterrows()], ""]
    (Path(A.OUT) / "SCREEN_EPC.md").write_text("\n".join(md))


if __name__ == "__main__":
    main()
