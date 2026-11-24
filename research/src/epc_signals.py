"""Energy certificates as signals for a sale in the next 12 months.

A home needs a valid energy certificate before it can be marketed, so a
certificate lodged "for a marketed sale" with no sale yet is a home on the
market. The certificate data is used without its address fields (licence:
epc_fetch.py): a certificate carries a UPRN, the ONS UPRN Directory places the
UPRN in a postcode, and the certificate says what kind of home it is.

Two levels, both worked out as of 1 January of the year scored and using
nothing lodged or sold after it:

  Exact. When a home is sold and exactly one UPRN had a sale certificate
  lodged in its postcode, for its kind of home, since the previous sale
  there, that UPRN is the home ("anchored"). From then on every later
  certificate on that UPRN belongs to the home. The match looks only
  backwards from each sale, so it never knows a future sale.

  Pool. A certificate that belongs to no anchored home could be any of
  the homes of that kind in the postcode that are not anchored. Each such
  home shares the certificates still unexplained by a sale.

Columns (the EPC family):
  months_owned       months from purchase to 1 January
  anchored           1 if the home's UPRN is known
  own_sale_12m/24m   sale certificates on the home's own UPRN since it was bought
  own_rent           private-rental certificates on it since it was bought
  own_other_12m      other certificates on it (grant schemes, assessments)
  own_cert_age       months since the latest certificate of any kind on it
  pool_sale_3m/6m/12m/24m   unexplained sale certificates, this kind of home, this postcode
  pool_sales_6m/12m  sales there by homes that were not anchored (they explain pool certificates)
  pool_homes         homes of this kind there that are not anchored
  pool_share_6m/12m  certificates left after those sales, per unanchored home
  homes_kind         homes of this kind in the postcode with a sale on record
  uprn_pc            addresses in the postcode
  cert_rent_24m, cert_other_12m   rental and other certificates there, any home of this kind

Certificates begin in October 2008, so years before 2010 are left blank.
"""
from pathlib import Path

import numpy as np
import pandas as pd

EPC = Path("research/data/epc")
ONSUD = "research/data/onsud/uprn_postcode.parquet"
FORM = {"Detached": 0, "Semi-Detached": 1, "Mid-Terrace": 2, "End-Terrace": 2, "Enclosed Mid-Terrace": 2, "Enclosed End-Terrace": 2}
CK = {"marketed sale": 0, "non marketed sale": 0, "rental (private)": 1, "rental": 1, "new dwelling": 3}     # else 2 (other)
COLS = ["months_owned", "anchored", "own_sale_12m", "own_sale_24m", "own_rent", "own_other_12m", "own_cert_age",
        "pool_sale_3m", "pool_sale_6m", "pool_sale_12m", "pool_sale_24m", "pool_sales_6m", "pool_sales_12m",
        "pool_homes", "pool_share_6m", "pool_share_12m", "homes_kind", "uprn_pc", "cert_rent_24m", "cert_other_12m"]
FIRST_YEAR = 2010
M = 100_000                                             # month indices are below this


def _win(key_sorted, base, a, b):
    """Events with month in [a, b) for each row (key = group * M + month)."""
    return np.searchsorted(key_sorted, base + b, side="left") - np.searchsorted(key_sorted, base + a, side="left")


class Epc:
    def __init__(self, panel, month, years=range(2008, 2020), say=print):
        self.panel = panel
        n_pc = len(panel.pc_names); self.ng = n_pc * 4
        self.ym = panel.year.astype(np.int64) * 12 + month.astype(np.int64) - 1          # month of every sale
        self.g = panel.pc.astype(np.int64) * 4 + panel.ptype                             # (postcode, kind of home) of every sale

        # ---- certificates, placed by UPRN -------------------------------------------------
        t = pd.concat([pd.read_parquet(EPC / f"certificates_{y}.parquet",
                                       columns=["uprn", "lodged", "transaction", "tenure", "ptype", "form"])
                       for y in years if (EPC / f"certificates_{y}.parquet").exists()], ignore_index=True)
        tr = t.transaction.str.lower().str.replace("-", " ").str.strip()
        tr = tr.fillna("")
        social = (tr.eq("rental (social)") | (tr.str.startswith("rental") & t.tenure.fillna("").str.lower().str.contains("social"))).to_numpy(dtype=bool)
        home = np.where(t.ptype.isin(["Flat", "Maisonette"]), 3, t.form.map(FORM).fillna(-1)).astype(np.int8)
        ck = tr.map(CK).fillna(2).astype(np.int8).to_numpy()
        u = pd.read_parquet(ONSUD)
        code = pd.Index(panel.pc_names).get_indexer(u.postcode.cat.categories)
        uu = u.uprn.to_numpy(); o = np.argsort(uu); uu = uu[o]; upc = code[u.postcode.cat.codes.to_numpy()][o]
        self.n_uprn = np.bincount(upc[upc >= 0], minlength=n_pc).astype(np.float32)
        del u
        cu = t.uprn.to_numpy()
        i = np.minimum(np.searchsorted(uu, cu), len(uu) - 1)
        pc = np.where(uu[i] == cu, upc[i], -1)
        cym = (t.lodged.dt.year * 12 + t.lodged.dt.month - 1).to_numpy(dtype=np.float64)
        keep = (pc >= 0) & (home >= 0) & ~social & np.isfinite(cym)
        say(f"certificates {len(t):,}; used (placed in a postcode with sales, kind of home known, not social rent): {keep.mean():.1%}")
        del t, uu, upc
        self.keep = keep                                                      # which certificates are used, in file order (epc2_signals.py)
        self.c_g = pc[keep].astype(np.int64) * 4 + home[keep]; self.c_k = ck[keep]; self.c_ym = cym[keep].astype(np.int64); self.c_u = cu[keep]
        self.last_month = int(self.c_ym.max())
        self._anchor(say)
        self._tables = {}

    # ---------------------------------------------------------------- which UPRN is which home
    def _anchor(self, say):
        p = self.panel; n = len(p.key)
        # sale and new-dwelling certificates, sorted by (group, month)
        sel = (self.c_k == 0) | (self.c_k == 3)
        o = np.lexsort((self.c_ym[sel], self.c_g[sel]))
        sg, sym, su, sk = self.c_g[sel][o], self.c_ym[sel][o], self.c_u[sel][o], self.c_k[sel][o]
        skey = sg * M + sym
        # runs of one UPRN in that order: a window holds one UPRN only if its run reaches the window's end
        brk = np.nonzero(np.r_[su[1:] != su[:-1], True])[0]
        run_end = brk[np.searchsorted(brk, np.arange(len(su)))] + 1
        # every sale: the previous sale's month in the same (postcode, kind), and whether another sale shares its month
        so = np.lexsort((self.ym, self.g)); gs, ys = self.g[so], self.ym[so]
        same_prev = np.r_[False, (gs[1:] == gs[:-1])]
        prev = np.where(same_prev, np.r_[0, ys[:-1]], -10**6)
        dup = np.zeros(n, bool); d = same_prev & (np.r_[0, ys[:-1]] == ys); dup[1:] |= d[1:]; dup[:-1] |= d[1:]
        # the month of the previous sale strictly before this one (ties share it)
        first_of_month = ~d
        prev_strict = np.maximum.accumulate(np.where(first_of_month, np.arange(n), 0))
        prev_ym = prev[prev_strict]
        new = p.is_new[so].astype(bool)
        lo_m = np.maximum(prev_ym + 1, ys - np.where(new, 30, 18))
        lo = np.searchsorted(skey, gs * M + lo_m, side="left"); hi = np.searchsorted(skey, gs * M + ys + 1, side="left")
        one = (hi > lo) & (run_end[np.minimum(lo, len(su) - 1)] >= hi) & ~dup & (ys >= 2008 * 12 + 9)
        uprn_sorted = np.where(one, su[np.minimum(lo, len(su) - 1)], -1)
        spell_u = np.full(n, -1, np.int64); spell_u[so] = uprn_sorted
        self.matched = spell_u >= 0                                   # this sale itself was matched
        # a home keeps its UPRN through its later sales (rows are sorted by home, then time)
        first = np.r_[True, p.key[1:] != p.key[:-1]]
        idx = np.where(spell_u >= 0, np.arange(n), -1)
        start = np.maximum.accumulate(np.where(first, np.arange(n), 0))
        last = np.maximum.accumulate(idx)                                      # latest matched row so far ...
        last = np.where(last >= start, last, -1)                               # ... if it is the same home
        self.spell_u = np.where(last >= 0, spell_u[np.maximum(last, 0)], -1)
        say(f"sales since October 2008 matched to one UPRN: {self.matched[self.ym >= 2008 * 12 + 9].mean():.1%}; "
            f"spells with a known UPRN: {(self.spell_u >= 0).mean():.1%}")
        # each UPRN's first anchoring month, and every matched sale of it
        mu, mym = spell_u[self.matched], self.ym[self.matched]
        o2 = np.lexsort((mym, mu)); mu, mym = mu[o2], mym[o2]
        self.m_key = mu * M + mym                                              # (UPRN, month of a matched sale), sorted
        fa = pd.Series(mym).groupby(mu).min()
        self.anchor_u = fa.index.to_numpy(); self.anchor_ym = fa.to_numpy()
        # every certificate: when its UPRN was first anchored, and the first matched sale at or after it
        j = np.minimum(np.searchsorted(self.anchor_u, self.c_u), len(self.anchor_u) - 1)
        a = np.where(self.anchor_u[j] == self.c_u, self.anchor_ym[j], 10**7)
        self.c_exact = a < self.c_ym                                           # lodged while the home was already known
        self.c_gone = np.where(~self.c_exact & (a < 10**7), a, 10**7)          # leaves the pool when its UPRN is anchored
        # certificates by UPRN, for the exact features
        o3 = np.lexsort((self.c_ym, self.c_k, self.c_u))
        self.u_key = (self.c_u[o3] * 4 + self.c_k[o3]) * M + self.c_ym[o3]
        o4 = np.lexsort((self.c_ym, self.c_u)); self.ua_u = self.c_u[o4]; self.ua_ym = self.c_ym[o4]
        self.ua_key = self.ua_u * M + self.ua_ym

    # ---------------------------------------------------------------- tables for one year
    def _year(self, T):
        if T not in self._tables:
            p = self.panel; t0 = T * 12; tab = {}
            pool = ~self.c_exact & (self.c_ym < t0) & (self.c_gone >= t0)       # unexplained as of 1 January
            for k in (3, 6, 12, 24):
                m = pool & (self.c_k == 0) & (self.c_ym >= t0 - k)
                tab[f"pool_sale_{k}m"] = np.bincount(self.c_g[m], minlength=self.ng).astype(np.float32)
            m = (self.c_k == 1) & (self.c_ym < t0) & (self.c_ym >= t0 - 24)
            tab["cert_rent_24m"] = np.bincount(self.c_g[m], minlength=self.ng).astype(np.float32)
            m = (self.c_k == 2) & (self.c_ym < t0) & (self.c_ym >= t0 - 12)
            tab["cert_other_12m"] = np.bincount(self.c_g[m], minlength=self.ng).astype(np.float32)
            unk = self.spell_u < 0                                            # sales by homes with no UPRN: they explain pool certificates
            for k in (6, 12):
                m = unk & (self.ym < t0) & (self.ym >= t0 - k)
                tab[f"pool_sales_{k}m"] = np.bincount(self.g[m], minlength=self.ng).astype(np.float32)
            cur = (p.year < T) & (~p.sold | (p.end_year >= T))                # the spell that holds each home on 1 January
            tab["pool_homes"] = np.bincount(self.g[cur & unk], minlength=self.ng).astype(np.float32)
            tab["homes_kind"] = np.bincount(self.g[cur], minlength=self.ng).astype(np.float32)
            self._tables = {T: tab}                                           # one year held at a time
        return self._tables[T]

    def features(self, rows, years):
        """The EPC columns for spells `rows` scored at `years`."""
        p = self.panel
        out = np.full((len(rows), len(COLS)), np.nan, np.float32); ix = {c: i for i, c in enumerate(COLS)}
        t0s = years.astype(np.int64) * 12
        out[:, ix["months_owned"]] = t0s - self.ym[rows]
        for T in np.unique(years):
            if T < FIRST_YEAR:
                continue
            sel = np.nonzero(years == T)[0]; r = rows[sel]; t0 = int(T) * 12
            tab = self._year(int(T)); g = self.g[r]
            for c in ("pool_sale_3m", "pool_sale_6m", "pool_sale_12m", "pool_sale_24m", "pool_sales_6m", "pool_sales_12m",
                      "pool_homes", "homes_kind", "cert_rent_24m", "cert_other_12m"):
                out[sel, ix[c]] = tab[c][g]
            unk = self.spell_u[r] < 0                                        # the home's own purchase is not a neighbour's sale
            for k in (6, 12):
                s = np.maximum(tab[f"pool_sales_{k}m"][g] - (unk & ((t0 - self.ym[r]) <= k)), 0)
                out[sel, ix[f"pool_sales_{k}m"]] = s
                out[sel, ix[f"pool_share_{k}m"]] = np.maximum(tab[f"pool_sale_{k}m"][g] - s, 0) / np.maximum(tab["pool_homes"][g], 1)
            out[sel, ix["uprn_pc"]] = self.n_uprn[p.pc[r]]
            u = self.spell_u[r]; anc = u >= 0
            out[sel, ix["anchored"]] = anc
            if anc.any():
                ua = u[anc]; bought = self.ym[r][anc]; sa = sel[anc]
                since = bought + 1                                          # lodged after the month of purchase
                for k, col in ((12, "own_sale_12m"), (24, "own_sale_24m")):
                    out[sa, ix[col]] = _win(self.u_key, (ua * 4 + 0) * M, np.maximum(since, t0 - k), np.full(len(ua), t0))
                out[sa, ix["own_rent"]] = _win(self.u_key, (ua * 4 + 1) * M, since, np.full(len(ua), t0))
                out[sa, ix["own_other_12m"]] = _win(self.u_key, (ua * 4 + 2) * M, np.maximum(since, t0 - 12), np.full(len(ua), t0))
                j = np.searchsorted(self.ua_key, ua * M + t0, side="left") - 1  # the latest certificate before 1 January
                ok = (j >= 0) & (self.ua_u[np.maximum(j, 0)] == ua)
                out[sa, ix["own_cert_age"]] = np.where(ok, t0 - self.ua_ym[np.maximum(j, 0)], np.nan)
        return out
