"""National property-year panel, version 2.

Rebuilt around the specific characteristics of the Price Paid Data
(see docs/06-model-review.md):

  * repeat sales per property      -> the property's own turnover history
  * prices at both ends of a spell -> the owner's paper gain or loss
  * 1.2M postcodes, 9k sectors     -> time-respecting local sale rates at
                                      postcode, sector and district level
  * a strong market cycle          -> market state known at the start of
                                      the year (never the year itself)
  * new-build estates sell in waves -> postcode age and new-build share

Everything is computed with dense [code, year] lookup tables and array
indexing, so the full 24M-transaction history fits comfortably in
memory and any sample size can be written to disk as float16 chunks.

Feature families: BASE (the published 13) and HIST (history, equity,
local rates, market cycle) change from year to year and are stored row
by row. Place signals (GEO, VIEW, HOUSE, AREA and any added later) are
looked up from each row's postcode when a model is trained, so they are
not stored here: see signals.py.

What is written for each chunk c:
  T_c       the year-by-year features, float16
  pc_c      each row's postcode (an index into postcodes.parquet)
  y_c, year_c, tenure_c, block_c, bucket_c, district_c, sector_c
  w_c       row weights, for chunks stored pre-sampled
Chunks 0 and 1 hold every row (they supply the 2016 stopping year and the
2017-2019 test years). Later chunks are only ever used for training,
which keeps every sale and one non-sale in four (model_lab.NEG_KEEP), so
they are stored that way already, with weight 4 on the non-sales kept.

Usage: python panel2.py <transactions.parquet> <out_dir> <n_chunks> [start_chunk]

20 chunks is every home in England and Wales.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

Y0, Y1 = 1995, 2019
NY = Y1 - Y0 + 1
PANEL_FROM = 2001
CHUNK_BUCKETS = 5            # each chunk holds 5% of properties

BASE = ["tenure", "log_price_rel", "leasehold", "is_new", "n_prior", "turnover_3y",
        "price_rel_nat", "price_growth_3y", "pc_sales_2y",
        "ptype_D", "ptype_S", "ptype_T", "ptype_F"]
HIST = ["equity_gain", "gain_ann", "prev_gap", "mean_prev_gap", "prev_ann_ret", "price_pct",
        "ls_band", "pc_sales_1y", "pc_sales_5y", "pc_stock", "pc_rate_5y", "pc_age",
        "pc_new_share", "sec_rate_5y", "sec_rate_1y", "sec_accel", "sec_price_rel",
        "sec_gentrify", "dist_rate_1y", "dist_yoy", "dist_new_share_2y",
        "nat_yoy", "nat_vol_rel5", "nat_price_g1", "buy_price_g1"]
FAMILIES = {"BASE": BASE, "HIST": HIST}
ALL = BASE + HIST                                    # the year-by-year features; place signals are in signals.py
PRESAMPLE_FROM = 2                                   # chunks from here on are stored with every sale + 1 non-sale in NEG_KEEP
NEG_KEEP = 4


def _dense(code, yi, n_codes, weights=None, dtype="int32"):
    idx = code.astype(np.int64) * NY + yi
    return np.bincount(idx, weights=weights, minlength=n_codes * NY).reshape(n_codes, NY).astype(dtype)


def _cs(a):
    """Cumulative sum along years with a leading zero column."""
    out = np.zeros((a.shape[0], a.shape[1] + 1), dtype="int32" if a.dtype.kind in "iu" else "float64")
    np.cumsum(a, axis=1, out=out[:, 1:])
    return out


def _win(cs, code, a, b):
    """Sum over year indices a..b inclusive (clipped to the data)."""
    a = np.clip(a, 0, NY); b = np.clip(b + 1, 0, NY)
    return cs[code, b] - cs[code, a]


def _median_table(codes, yi, price, n_codes):
    g = pd.DataFrame({"c": codes, "y": yi, "p": price}).groupby(["c", "y"], sort=False)["p"].median()
    t = np.full((n_codes, NY), np.nan)
    t[g.index.get_level_values(0).to_numpy(), g.index.get_level_values(1).to_numpy()] = g.to_numpy()
    return pd.DataFrame(t).ffill(axis=1).to_numpy()


class Panel:
    def __init__(self, tx_path, verbose=True):
        say = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
        tx = pd.read_parquet(tx_path, columns=["key", "year", "month", "price", "ptype", "is_new",
                                               "leasehold", "outcode", "postcode"])
        say(f"transactions {len(tx):,}")
        self.key = tx["key"].to_numpy()
        self.year = tx["year"].to_numpy().astype("int32")
        self.price = tx["price"].to_numpy().astype("float64")
        self.ptype = tx["ptype"].astype(str).map({"D": 0, "S": 1, "T": 2, "F": 3}).to_numpy().astype("int8")
        self.is_new = tx["is_new"].to_numpy()
        self.lease = tx["leasehold"].to_numpy()
        self.oc = tx["outcode"].cat.codes.to_numpy().astype("int32")
        self.pc = tx["postcode"].cat.codes.to_numpy().astype("int32")
        self.month = tx["month"].to_numpy().astype("int8")           # for dated events (signals.row_features)
        self.oc_names = np.asarray(tx["outcode"].cat.categories)
        self.pc_names = np.asarray(tx["postcode"].cat.categories)
        n_oc, n_pc = len(self.oc_names), len(self.pc_names)
        del tx
        yi = self.year - Y0

        # sector code per postcode ("EX4 4AB" -> "EX4 4")
        sec_str = pd.Series(self.pc_names).str.slice(0, -2)
        sec_codes, sec_names = pd.factorize(sec_str)
        self.pc2sec = sec_codes.astype("int32"); self.sec_names = np.asarray(sec_names)
        n_sec = len(sec_names)
        sec = self.pc2sec[self.pc]

        # ---- property history (rows are sorted by key, year, month) --------
        same_prev = np.zeros(len(self.key), dtype=bool); same_prev[1:] = self.key[1:] == self.key[:-1]
        first_idx = np.maximum.accumulate(np.where(~same_prev, np.arange(len(self.key)), 0))
        self.n_prior = (np.arange(len(self.key)) - first_idx).astype("int16")
        prev_year = np.empty_like(self.year); prev_year[1:] = self.year[:-1]
        prev_price = np.empty_like(self.price); prev_price[1:] = self.price[:-1]
        gap = (self.year - prev_year).astype("float32")
        self.prev_gap = np.where(same_prev, gap, np.nan).astype("float32")
        self.mean_prev_gap = np.where(same_prev, (self.year - self.year[first_idx]) /
                                      np.maximum(self.n_prior, 1), np.nan).astype("float32")
        with np.errstate(divide="ignore", invalid="ignore"):
            self.prev_ann_ret = np.where(same_prev, np.log(self.price / prev_price) /
                                         np.maximum(gap, 1), np.nan).astype("float32")
        same_next = np.zeros(len(self.key), dtype=bool); same_next[:-1] = same_prev[1:]
        nxt = np.empty_like(self.year); nxt[:-1] = self.year[1:]
        self.sold = same_next
        self.end_year = np.where(same_next, nxt, Y1).astype("int32")
        say(f"properties {int((~same_prev).sum()):,}")

        # ---- dense context tables ------------------------------------------
        first = ~same_prev
        self.d_sales_cs = _cs(_dense(self.oc, yi, n_oc))
        self.d_new_cs = _cs(_dense(self.oc, yi, n_oc, weights=self.is_new.astype("float64")))
        self.d_stock = np.cumsum(_dense(self.oc[first], yi[first], n_oc), axis=1)
        self.s_sales_cs = _cs(_dense(sec, yi, n_sec))
        self.s_stock = np.cumsum(_dense(sec[first], yi[first], n_sec), axis=1)
        p_sales = _dense(self.pc, yi, n_pc, dtype="int16")
        self.p_sales_cs = _cs(p_sales); del p_sales
        self.p_stock = np.cumsum(_dense(self.pc[first], yi[first], n_pc, dtype="int16"), axis=1).astype("int16")
        self.p_new_cs = _cs(_dense(self.pc, yi, n_pc, weights=self.is_new.astype("float64"), dtype="int16"))
        pfy = np.full(n_pc, Y1 + 1, dtype="int32"); np.minimum.at(pfy, self.pc, self.year); self.p_first_year = pfy
        say("medians...")
        self.d_med = _median_table(self.oc, yi, self.price, n_oc)
        self.s_med = _median_table(sec, yi, self.price, n_sec)
        nat = pd.DataFrame({"y": yi, "p": self.price}).groupby("y")["p"]
        self.n_med = nat.median().reindex(range(NY)).to_numpy()
        self.n_sales = np.bincount(yi, minlength=NY).astype("float64")
        say("price percentiles...")
        self.price_pct = (pd.DataFrame({"d": self.oc, "y": yi, "p": self.price})
                          .groupby(["d", "y"], sort=False)["p"].rank(pct=True).to_numpy().astype("float32"))

        self.bucket = (np.abs(self.key) % 100).astype("int8")
        self.block = ((np.abs(self.key) // 100) % 2048).astype("int16")

    # ------------------------------------------------------------------
    def expand(self, spell_idx, y_from=PANEL_FROM, y_to=Y1):
        """Risk rows (spell, year) for the given spells."""
        start = np.maximum(self.year[spell_idx] + 1, y_from)
        stop = np.minimum(self.end_year[spell_idx], y_to)
        n = np.maximum(stop - start + 1, 0)
        keep = n > 0
        spell_idx, start, n = spell_idx[keep], start[keep], n[keep]
        rows = np.repeat(spell_idx, n)
        off = np.arange(n.sum()) - np.repeat(np.concatenate(([0], n.cumsum()[:-1])), n)
        years = (np.repeat(start, n) + off).astype("int32")
        label = (self.sold[rows] & (years == self.end_year[rows])).astype("uint8")
        return rows, years, label

    def features(self, s, t, names=ALL):
        """Feature matrix for spells s evaluated at years t (uses data <= t-1)."""
        p = t - Y0 - 1                                   # index of year t-1
        by = self.year[s]; byi = by - Y0
        d, pc = self.oc[s], self.pc[s]; sec = self.pc2sec[pc]
        ten = (t - by).astype("float32")
        f = {}
        f["tenure"] = ten
        with np.errstate(divide="ignore", invalid="ignore"):
            f["log_price_rel"] = np.log(self.price[s] / self.d_med[d, byi])
            f["leasehold"] = self.lease[s]; f["is_new"] = self.is_new[s]; f["n_prior"] = self.n_prior[s]
            d_stock = np.maximum(self.d_stock[d, np.clip(p, 0, NY - 1)], 1)
            f["turnover_3y"] = _win(self.d_sales_cs, d, p - 2, p) / 3 / d_stock
            f["price_rel_nat"] = self.d_med[d, p] / self.n_med[p]
            f["price_growth_3y"] = np.log(self.d_med[d, p] / self.d_med[d, np.clip(p - 3, 0, NY - 1)])
            own = lambda k: (ten <= k).astype("float32")
            f["pc_sales_2y"] = np.maximum(_win(self.p_sales_cs, pc, p - 1, p) - own(2), 0)
            for i, c in enumerate("DSTF"):
                f[f"ptype_{c}"] = self.ptype[s] == i
            # ---- HIST
            f["equity_gain"] = np.log(self.d_med[d, p] / self.d_med[d, byi])
            f["gain_ann"] = f["equity_gain"] / np.maximum(ten, 1)
            f["prev_gap"] = self.prev_gap[s]; f["mean_prev_gap"] = self.mean_prev_gap[s]
            f["prev_ann_ret"] = self.prev_ann_ret[s]; f["price_pct"] = self.price_pct[s]
            pt, pp = self.ptype[s], self.price_pct[s]
            f["ls_band"] = np.select([(pt >= 2) & (pp < .4), (pt <= 1) & (pp >= .4) & (pp < .9), pp >= .9],
                                     [1, 2, 3], 0)
            f["pc_sales_1y"] = np.maximum(_win(self.p_sales_cs, pc, p, p) - own(1), 0)
            f["pc_sales_5y"] = np.maximum(_win(self.p_sales_cs, pc, p - 4, p) - own(5), 0)
            pstock = np.maximum(self.p_stock[pc, np.clip(p, 0, NY - 1)], 1).astype("float32")
            f["pc_stock"] = pstock
            f["pc_rate_5y"] = f["pc_sales_5y"] / (5 * pstock)
            f["pc_age"] = t - self.p_first_year[pc]
            f["pc_new_share"] = _win(self.p_new_cs, pc, 0, p) / pstock
            sstock = np.maximum(self.s_stock[sec, np.clip(p, 0, NY - 1)], 1)
            f["sec_rate_5y"] = _win(self.s_sales_cs, sec, p - 4, p) / (5 * sstock)
            f["sec_rate_1y"] = _win(self.s_sales_cs, sec, p, p) / sstock
            f["sec_accel"] = f["sec_rate_1y"] / np.maximum(f["sec_rate_5y"], 1e-4)
            f["sec_price_rel"] = self.s_med[sec, p] / self.d_med[d, p]
            p5 = np.clip(p - 5, 0, NY - 1)
            f["sec_gentrify"] = (np.log(self.s_med[sec, p] / self.s_med[sec, p5])
                                 - np.log(self.d_med[d, p] / self.d_med[d, p5]))
            f["dist_rate_1y"] = _win(self.d_sales_cs, d, p, p) / d_stock
            f["dist_yoy"] = np.log(np.maximum(_win(self.d_sales_cs, d, p, p), 1)
                                   / np.maximum(_win(self.d_sales_cs, d, p - 1, p - 1), 1))
            f["dist_new_share_2y"] = (_win(self.d_new_cs, d, p - 1, p)
                                      / np.maximum(_win(self.d_sales_cs, d, p - 1, p), 1))
            pm1 = np.clip(p - 1, 0, NY - 1)
            f["nat_yoy"] = np.log(self.n_sales[p] / self.n_sales[pm1])
            ncs = np.concatenate(([0], np.cumsum(self.n_sales)))
            a = np.clip(p - 5, 0, NY); b = np.clip(p, 0, NY)
            f["nat_vol_rel5"] = self.n_sales[p] / np.maximum((ncs[b] - ncs[a]) / np.maximum(b - a, 1), 1)
            f["nat_price_g1"] = np.log(self.n_med[p] / self.n_med[pm1])
            f["buy_price_g1"] = np.log(self.n_med[byi] / self.n_med[np.clip(byi - 1, 0, NY - 1)])
        X = np.empty((len(s), len(names)), dtype="float32")
        for j, nm in enumerate(names):
            if nm in f:
                X[:, j] = f[nm]
            else:
                raise KeyError(nm)
        X[~np.isfinite(X)] = np.nan
        return X


def full_features(panel, s, t, families, lookups=None):
    """Year-by-year features followed by the place families' signals, looked
    up from each spell's postcode: what a model trained on `families` expects."""
    import signals as SG
    tv = [f for f in families if f in SG.TIME_VARYING]
    X = panel.features(s, t, SG.columns(tv)) if tv else np.zeros((len(s), 0), np.float32)
    parts = [X]
    for f in families:
        if f in SG.TIME_VARYING:
            continue
        if f in SG.ROW_FAMILIES:                      # worked out from dated events for these homes and years
            parts.append(SG.row_features(f, panel, np.asarray(s), np.asarray(t)))
            continue
        if lookups is None or f not in lookups:
            lookups = dict(lookups or {}); lookups[f] = SG.lookup(f, panel.pc_names)
        v = lookups[f][panel.pc[s]]
        if SG.FAMILIES[f].get("rowwise"):             # worked out home by home from the years owned
            v = SG.rowwise(f, v, panel.features(s, t, ["tenure"])[:, 0])
        parts.append(v)
    return np.hstack(parts)


def chunk_rows(panel, c):
    """The rows of chunk c, in the order they are stored: (spell, year, label, weight, rows before sampling)."""
    lo, hi = c * CHUNK_BUCKETS, (c + 1) * CHUNK_BUCKETS
    spells = np.nonzero((panel.bucket >= lo) & (panel.bucket < hi))[0]
    rows, years, label = panel.expand(spells)
    n_all = len(rows)
    w = np.ones(n_all, np.float32)
    if c >= PRESAMPLE_FROM:                           # the same rule model_lab.dataset() applies, on the full row index
        idx = np.arange(n_all, dtype=np.int64)
        keep = (label == 1) | ((((idx + 1) * 2654435761) >> 9) % NEG_KEEP == 0)
        rows, years, label = rows[keep], years[keep], label[keep]
        w = np.where(label == 1, 1.0, float(NEG_KEEP)).astype(np.float32)
    return rows, years, label, w, n_all


def write_row_family(panel, out_dir, family):
    """Store a row family (signals.ROW_FAMILIES) beside every chunk already on disk, row for row."""
    import signals as SG
    out = Path(out_dir); meta = json.load(open(out / "meta.json"))
    for ch in meta["chunks"]:
        c = ch["id"]
        rows, years, label, _, _ = chunk_rows(panel, c)
        assert np.array_equal(label, np.load(out / f"y_{c}.npy")), f"chunk {c}: rows are not in the stored order"
        X = SG.row_features(family, panel, rows, years)
        np.save(out / f"R_{family}_{c}.npy", np.clip(X, -6e4, 6e4).astype("float16"))
        print(f"chunk {c}: {family} for {len(rows):,} rows; {np.isfinite(X).any(axis=1).mean():.0%} with a value", flush=True)


def write_chunks(panel, out_dir, n_chunks, start=0):
    """Write chunks start..n_chunks-1. Chunks already on disk are kept, so a
    table built for part of the country can be extended to all of it."""
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"postcode": pd.Series(panel.pc_names, dtype="string")}).to_parquet(out / "postcodes.parquet", index=False)
    meta = {"features": ALL, "families": FAMILIES, "chunks": [], "neg_keep": NEG_KEEP, "presample_from": PRESAMPLE_FROM}
    if start and (out / "meta.json").exists():
        meta["chunks"] = [c for c in json.load(open(out / "meta.json"))["chunks"] if c["id"] < start]
    for c in range(start, n_chunks):
        lo, hi = c * CHUNK_BUCKETS, (c + 1) * CHUNK_BUCKETS
        rows, years, label, w, n_all = chunk_rows(panel, c)
        n = len(rows)
        X = np.lib.format.open_memmap(out / f"T_{c}.npy", mode="w+", dtype="float16", shape=(n, len(ALL)))
        for a in range(0, n, 2_000_000):
            b = min(a + 2_000_000, n)
            X[a:b] = np.clip(panel.features(rows[a:b], years[a:b]), -6e4, 6e4)
        X.flush(); del X
        np.save(out / f"pc_{c}.npy", panel.pc[rows].astype(np.int32))
        np.save(out / f"y_{c}.npy", label)
        np.save(out / f"w_{c}.npy", w)
        np.save(out / f"year_{c}.npy", years.astype("int16"))
        np.save(out / f"tenure_{c}.npy", (years - panel.year[rows]).astype("int8"))
        np.save(out / f"block_{c}.npy", panel.block[rows])
        np.save(out / f"bucket_{c}.npy", panel.bucket[rows])
        np.save(out / f"district_{c}.npy", panel.oc[rows].astype("int16"))
        np.save(out / f"sector_{c}.npy", panel.pc2sec[panel.pc[rows]].astype("int32"))
        meta["chunks"].append({"id": c, "rows": int(n), "rows_before_sampling": int(n_all), "sales": int(label.sum()),
                               "presampled": bool(c >= PRESAMPLE_FROM)})
        print(f"chunk {c}: buckets {lo}-{hi-1}, {n:,} rows stored of {n_all:,}, {int(label.sum()):,} sales", flush=True)
    json.dump(meta, open(out / "meta.json", "w"))


def write_late_label(panel, out_dir):
    """Store, beside every chunk, whether each home-year's sale completes between July of that year and June of
    the next ("late"). On 1 January such a home was, with few exceptions, not yet on the market; a home whose
    sale completes in January to June mostly was. Needs sales up to June of the year after the row."""
    out = Path(out_dir); meta = json.load(open(out / "meta.json"))
    n = len(panel.month)
    for ch in meta["chunks"]:
        c = ch["id"]
        rows, years, label, _, _ = chunk_rows(panel, c)
        assert np.array_equal(label, np.load(out / f"y_{c}.npy")), f"chunk {c}: rows are not in the stored order"
        end = panel.end_year[rows].astype(np.int64) * 12 + panel.month[np.minimum(rows + 1, n - 1)] - 1   # rows: by home, then date
        t0 = years.astype(np.int64) * 12
        late = (panel.sold[rows] & (end >= t0 + 6) & (end < t0 + 18)).astype("uint8")
        np.save(out / f"late_{c}.npy", late)
        print(f"chunk {c}: {int(late.sum()):,} later sales against {int(label.sum()):,} sales in the year", flush=True)


if __name__ == "__main__":
    tx, out_dir, n_chunks = sys.argv[1:4]
    panel = Panel(tx)
    if n_chunks == "rowfam":                          # python panel2.py <transactions> <out_dir> rowfam <FAMILY>
        write_row_family(panel, out_dir, sys.argv[4])
    elif n_chunks == "late":                          # python panel2.py <transactions> <out_dir> late
        write_late_label(panel, out_dir)
    else:
        write_chunks(panel, out_dir, int(n_chunks), int(sys.argv[4]) if len(sys.argv) > 4 else 0)
