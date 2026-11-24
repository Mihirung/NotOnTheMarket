"""More from the energy certificates: intent shown in past years, and facts about the home.

epc_signals.py reads a fresh sale certificate as a home that is on the market. That is a
marker of a listing, not a warning of one (late_sale.py). This family looks for what comes
before a listing, and uses the certificate's own facts about the home. As there, no address
field is read: a certificate is placed by its UPRN, and everything is worked out as of
1 January of the year scored from certificates lodged before it.

Intent, on the home's own UPRN (homes whose UPRN is known):
  own_sale_n        sale certificates lodged six months or more after the purchase: the owner
                    prepared a sale and did not complete one (a withdrawn listing)
  own_sale_age      months since the latest of them
  own_rent_age      months since the latest private-rental certificate since the purchase
  own_rent_before   rental certificates on the home before this owner bought it
  own_grant_n       certificates for a grant or improvement scheme since the purchase (insulation,
                    solar panels, a heat pump): an owner investing in the home
  own_grant_age     months since the latest of them
  own_none_age      months since the latest certificate lodged for no stated reason

Facts, from the latest certificate on the home's UPRN:
  own_score, own_area, own_rooms, own_built, own_bungalow, own_let
                    energy score (1 to 100), floor area (m2), habitable rooms, year built (middle
                    of the age band), bungalow or not, and let privately or not when assessed

Intent among the homes of that kind in the postcode whose UPRN is not known (the pool):
  pool_sale_60m     sale certificates lodged 24 to 60 months ago that belong to no known home
  pool_sales_60m    sales there since by homes with no known UPRN (they explain such certificates)
  pool_share_60m    certificates left over, per home in the pool
  pool_share_old    the same for certificates older than 60 months
  pool_rent_share   homes with a rental certificate, per home in the pool
  pool_grant_60m    grant-scheme certificates in the last 60 months

Facts for that kind of home in the postcode (every certificate lodged so far):
  pk_score, pk_area, pk_rooms, pk_built, pk_bungalow, pk_let, pk_certs
"""
import re

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

import epc_signals as ES

M = ES.M
GRANT = {"eco assessment", "assessment for green deal", "following green deal", "fit application", "rhi application"}
SALE, RENT, NEW, GRANT_K, NONE_K = 0, 1, 3, 4, 5
FACTS = ["score", "area", "rooms", "built", "bungalow", "let"]
OWN_EVENTS = ["own_sale_n", "own_sale_age", "own_rent_age", "own_rent_before", "own_grant_n", "own_grant_age", "own_none_age"]
OWN_FACTS = [f"own_{f}" for f in FACTS]
POOL = ["pool_sale_60m", "pool_sales_60m", "pool_share_60m", "pool_share_old", "pool_rent_share", "pool_grant_60m"]
PK = [f"pk_{f}" for f in FACTS] + ["pk_certs"]
COLS = OWN_EVENTS + OWN_FACTS + POOL + PK
GROUPS = {"intent on the home": OWN_EVENTS, "facts about the home": OWN_FACTS, "intent in the pool": POOL,
          "facts for the postcode": PK}
START = 2008 * 12 + 9                                    # certificates begin in October 2008


def _built(s):
    """The middle year of a construction age band ("England and Wales: 1950-1966", "before 1900", "2016")."""
    s = str(s).lower()
    y = [int(v) for v in re.findall(r"(?<!\d)(1[6-9]\d\d|20[0-2]\d)(?!\d)", s)]
    if not y:
        return np.nan
    if "before" in s:
        return y[0] - 20.0
    if "onwards" in s:
        return y[0] + 2.0
    return float(np.mean(y[:2]))


def _latest(key, base, lo, hi):
    """The month of the latest event in [lo, hi) for each row (key = group * M + month), or -1."""
    j = np.searchsorted(key, base + hi, side="left") - 1
    k = key[np.maximum(j, 0)]
    return np.where((j >= 0) & (k >= base + lo), k - base, -1)


class Epc2:
    def __init__(self, epc, years=range(2008, 2020), say=print):
        e = self.e = epc
        files = [ES.EPC / f"certificates_{y}.parquet" for y in years if (ES.EPC / f"certificates_{y}.parquet").exists()]
        cat = ["transaction", "tenure", "ptype", "age"]
        t = pa.concat_tables([pq.read_table(f, columns=cat + ["score", "area", "rooms"], read_dictionary=cat) for f in files])
        t = t.unify_dictionaries().to_pandas()
        assert len(t) == len(e.keep), "the certificate files changed since they were placed"
        t = t[e.keep].reset_index(drop=True)

        def by_category(col, fn, dtype):
            """A value per certificate, worked out once per distinct string."""
            v = np.array([fn(c) for c in t[col].cat.categories] + [fn(None)], dtype=dtype)
            return v[t[col].cat.codes.to_numpy()]                              # a missing value has code -1: the last entry

        tr = by_category("transaction", lambda c: GRANT_K if str(c).lower().replace("-", " ").strip() in GRANT else NONE_K, np.int8)
        self.kind = np.where(e.c_k == 2, tr, e.c_k).astype(np.int64)           # sale, rental and new as in epc_signals
        let = by_category("tenure", lambda c: 1.0 if "private" in str(c).lower() else 0.0 if "owner" in str(c).lower() else np.nan, np.float32)
        bung = by_category("ptype", lambda c: np.nan if c is None else float(str(c) == "Bungalow"), np.float32)
        built = by_category("age", _built, np.float32)
        score, area, rooms = (t[c].to_numpy(np.float32, copy=True) for c in ("score", "area", "rooms"))
        score[(score < 1) | (score > 100)] = np.nan; area[(area < 10) | (area > 2000)] = np.nan; rooms[(rooms < 1) | (rooms > 30)] = np.nan
        del t
        self.f = np.column_stack([score, area, rooms, built, bung, let])       # in certificate order, for the postcode means
        say("certificates by purpose: " + ", ".join(f"{n} {np.mean(self.kind == k):.1%}" for n, k in
                                                      (("sale", SALE), ("rental", RENT), ("new home", NEW), ("grant scheme", GRANT_K), ("no reason", NONE_K))))
        # events by (UPRN, purpose, month)
        o = np.lexsort((e.c_ym, self.kind, e.c_u))
        self.k_key = (e.c_u[o] * 8 + self.kind[o]) * M + e.c_ym[o]
        # the first rental certificate of each UPRN (so homes are counted, not certificates)
        ru = e.c_u[o]; rk = self.kind[o]
        first = np.zeros(len(o), bool); first[o] = (rk == RENT) & np.r_[True, (ru[1:] != ru[:-1]) | (rk[1:] != rk[:-1])]
        self.first_rent = first
        # facts by (UPRN, month), each carried forward from the latest certificate that states it
        o4 = np.lexsort((e.c_ym, e.c_u))                                       # the order of epc.ua_key
        fu = self.f[o4].copy(); u = e.c_u[o4]; n = len(u)
        start = np.maximum.accumulate(np.where(np.r_[True, u[1:] != u[:-1]], np.arange(n), 0))
        for j in range(fu.shape[1]):
            last = np.maximum.accumulate(np.where(np.isfinite(fu[:, j]), np.arange(n), -1))
            fu[:, j] = np.where(last >= start, fu[np.maximum(last, 0), j], np.nan)
        self.fu = fu
        say(f"facts stated on the latest certificate: " + ", ".join(f"{c} {np.isfinite(fu[:, i]).mean():.0%}" for i, c in enumerate(FACTS)))
        self._tables = {}

    def _year(self, T):
        if T not in self._tables:
            e = self.e; t0 = T * 12; tab = {}
            before = e.c_ym < t0
            pool = ~e.c_exact & before & (e.c_gone >= t0)                      # belongs to no known home as of 1 January
            cnt = lambda m: np.bincount(e.c_g[m], minlength=e.ng).astype(np.float32)   # noqa: E731
            tab["pool_sale_60m"] = cnt(pool & (self.kind == SALE) & (e.c_ym >= t0 - 60) & (e.c_ym < t0 - 24))
            tab["pool_sale_old"] = cnt(pool & (self.kind == SALE) & (e.c_ym < t0 - 60))
            tab["pool_rent_homes"] = cnt(pool & self.first_rent)
            tab["pool_grant_60m"] = cnt(pool & (self.kind == GRANT_K) & (e.c_ym >= t0 - 60))
            unk = e.spell_u < 0                                               # sales by homes with no UPRN; a sale follows its certificate by some months
            sal = lambda a, b: np.bincount(e.g[unk & (e.ym >= a) & (e.ym < b)], minlength=e.ng).astype(np.float32)   # noqa: E731
            tab["pool_sales_60m"] = sal(t0 - 60, t0 - 18)
            tab["pool_sales_old"] = sal(START, t0 - 54)
            tab["pool_homes"] = e._year(T)["pool_homes"]
            n_all = np.bincount(e.c_g[before], minlength=e.ng)
            tab["pk_certs"] = n_all.astype(np.float32)
            for j, f in enumerate(FACTS):
                v = self.f[:, j]; ok = before & np.isfinite(v)
                s = np.bincount(e.c_g[ok], weights=v[ok], minlength=e.ng); k = np.bincount(e.c_g[ok], minlength=e.ng)
                tab[f"pk_{f}"] = np.where(k > 0, s / np.maximum(k, 1), np.nan).astype(np.float32)
            self._tables = {T: tab}                                           # one year held at a time
        return self._tables[T]

    def features(self, rows, years):
        """The columns for spells `rows` scored at `years`."""
        e = self.e
        out = np.full((len(rows), len(COLS)), np.nan, np.float32); ix = {c: i for i, c in enumerate(COLS)}
        for T in np.unique(years):
            if T < ES.FIRST_YEAR:
                continue
            sel = np.nonzero(years == T)[0]; r = rows[sel]; t0 = int(T) * 12
            tab = self._year(int(T)); g = e.g[r]; homes = np.maximum(tab["pool_homes"][g], 1)
            for c in ("pool_sale_60m", "pool_sales_60m", "pool_grant_60m", "pk_certs", *[f"pk_{f}" for f in FACTS]):
                out[sel, ix[c]] = tab[c][g]
            out[sel, ix["pool_share_60m"]] = np.maximum(tab["pool_sale_60m"][g] - tab["pool_sales_60m"][g], 0) / homes
            out[sel, ix["pool_share_old"]] = np.maximum(tab["pool_sale_old"][g] - tab["pool_sales_old"][g], 0) / homes
            out[sel, ix["pool_rent_share"]] = tab["pool_rent_homes"][g] / homes
            u = e.spell_u[r]; anc = u >= 0
            if not anc.any():
                continue
            ua = u[anc]; bought = e.ym[r][anc]; sa = sel[anc]; end = np.full(len(ua), t0)
            age = lambda k, lo: (lambda m: np.where(m >= 0, t0 - m, np.nan))(_latest(self.k_key, (ua * 8 + k) * M, lo, end))   # noqa: E731
            out[sa, ix["own_sale_n"]] = ES._win(self.k_key, (ua * 8 + SALE) * M, bought + 6, end)
            out[sa, ix["own_sale_age"]] = age(SALE, bought + 6)
            out[sa, ix["own_rent_age"]] = age(RENT, bought + 1)
            out[sa, ix["own_rent_before"]] = ES._win(self.k_key, (ua * 8 + RENT) * M, np.zeros(len(ua), np.int64), bought)
            out[sa, ix["own_grant_n"]] = ES._win(self.k_key, (ua * 8 + GRANT_K) * M, bought + 1, end)
            out[sa, ix["own_grant_age"]] = age(GRANT_K, bought + 1)
            out[sa, ix["own_none_age"]] = age(NONE_K, bought + 1)
            j = np.searchsorted(e.ua_key, ua * M + t0, side="left") - 1          # the latest certificate before 1 January
            ok = (j >= 0) & (e.ua_u[np.maximum(j, 0)] == ua)
            for i, f in enumerate(FACTS):
                out[sa, ix[f"own_{f}"]] = np.where(ok, self.fu[np.maximum(j, 0), i], np.nan)
        return out
