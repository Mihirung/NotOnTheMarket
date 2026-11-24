"""Notices in The Gazette at a home, as signals for a sale.

Two kinds of notice (gazette_list.py), each joined to the home whose sales we
know by postcode, house number or name, and flat, the same key as the sale
records:

  Bankruptcy orders. A trustee has three years to deal with the bankrupt's
  home, so a sale tends to come one to three years after the order.

  Deceased estates. Executors advertise for claims before they share out an
  estate. The home is very often sold within a year or two.

Columns (the NOTICE family), all as of 1 January of the year scored and using
nothing published after it:

  bk_months, dec_months   months since the latest notice of that kind at the home (blank if none in WINDOW months)
  bk_owned, dec_owned     months the home had been owned when that notice appeared (negative: it was bought after
                          the notice, so the notice is about an earlier owner)
  bk_n, dec_n             notices of that kind at the home in the window

Only the home key and the month of publication are used. No name is ever held
(gazette_list.py drops them on reading) and nothing here is written out by
address: the family is for ranking only and is never shown as a reason.

    python notice_signals.py            link the notices on disk and print the counts
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

DIRS = {"bk": Path("research/data/gazette_bankruptcy"), "dec": Path("research/data/gazette")}
KINDS = list(DIRS)
COLS = [f"{k}_{c}" for k in KINDS for c in ("months", "owned", "n")]
WINDOW = 48
M = 100_000                                             # month indices are below this
TX = "research/data/transactions.parquet"
LINK_VERSION = 2
# two facts read off the address and kept beside the link: a care or nursing home, and a flat or a named block
CARE = r"nursing|care home|care centre|residential home|rest home|hospice|hospital|\bcare\b"
FLAT = r"\bflat\b|\bapartment\b|\bcourt\b|\bhouse,"
SIG = Path("research/data/signals")
# what a home with no sale on record is scored on (notice_unseen.py): the notice, the address, and its postcode
UNSEEN_COLS = ["months", "n", "flat", "own_outright", "own_mortgage", "social_rent", "private_rent", "hh_alone_65",
               "age_75_84", "age_85_plus", "flats", "bungalows", "detached", "n_addr", "on_record"]


def linked(kind, tx_keys=None, refresh=False, every=False):
    """(home key, month published) for every notice whose address is a home with a sale record. With `every`,
    the notices that match no such home are returned too (has = False, with their postcode; key is then the key
    of the likeliest reading of the address, which tells two notices for one home apart from two homes).
    Kept in <dir>/linked.parquet and rebuilt when the listing has grown."""
    from planning_link import key_of, readings
    d = DIRS[kind]; src, out, info = d / "listing.jsonl", d / "linked.parquet", d / "linked.json"
    n_lines = sum(1 for _ in open(src))
    old = json.load(open(info)) if out.exists() and info.exists() else {}
    if not (old.get("notices") == n_lines and old.get("version") == LINK_VERSION and not refresh):
        n = pd.DataFrame([json.loads(l) for l in open(src)]).drop_duplicates("id")
        n["pub"] = pd.to_datetime(n.published, errors="coerce")
        n = n.dropna(subset=["pub", "postcode", "address"]).reset_index(drop=True)
        if tx_keys is None:
            tx_keys = pd.read_parquet(TX, columns=["key"]).key.unique()
        rows = []
        for i, (addr, pc) in enumerate(zip(n.address, n.postcode)):
            for rank, (paon, saon) in enumerate(readings(addr, pc)):
                rows.append((i, rank, pc, paon, saon))
        r = pd.DataFrame(rows, columns=["i", "rank", "pc", "paon", "saon"])
        r["key"] = key_of(r.pc, r.paon, r.saon)
        r0 = r.sort_values(["i", "rank"]).drop_duplicates("i")                        # the likeliest reading, a known home or not
        key = np.zeros(len(n), np.int64); has = np.zeros(len(n), bool)
        key[r0.i.to_numpy()] = r0.key.to_numpy()
        r = r[r.key.isin(tx_keys)].sort_values(["i", "rank"]).drop_duplicates("i")    # the first reading that is a known home
        key[r.i.to_numpy()] = r.key.to_numpy(); has[r.i.to_numpy()] = True
        low = n.address.str.lower()
        care = low.str.contains(CARE, regex=True).to_numpy()
        t = pd.DataFrame({"key": key, "has": has, "ym": (n.pub.dt.year * 12 + n.pub.dt.month - 1).to_numpy().astype("int32"),
                          "postcode": n.postcode.to_numpy(), "care": care,
                          "flat": low.str.contains(FLAT, regex=True).to_numpy() & ~care})
        t.to_parquet(out, index=False)
        by = pd.DataFrame({"y": n.pub.dt.year.to_numpy(), "got": has}).groupby("y").got.agg(["size", "sum"])
        json.dump({"version": LINK_VERSION, "notices": n_lines, "with_an_address": int(len(n)), "linked_to_a_home": int(has.sum()),
                   "by_year": {int(y): [int(a), int(b)] for y, a, b in zip(by.index, by["size"], by["sum"])}},
                  open(info, "w"), indent=1)
    t = pd.read_parquet(out)
    return t if every else t[t.has][["key", "ym"]].reset_index(drop=True)


class Notices:
    """The notices at each home, ready to be read off for any homes and years."""

    def __init__(self, panel):
        self.panel = panel
        self.ev = {}
        keys = np.unique(panel.key)
        for k in KINDS:
            if not (DIRS[k] / "listing.jsonl").exists():
                continue
            t = linked(k, keys)
            homes = np.unique(t.key.to_numpy())                      # sorted home keys with a notice
            comp = np.sort(np.searchsorted(homes, t.key.to_numpy()).astype(np.int64) * M + t.ym.to_numpy())
            self.ev[k] = (homes, comp)

    def features(self, rows, years):
        p = self.panel
        t0 = np.asarray(years, np.int64) * 12                       # January of the year scored
        bought = p.year[rows].astype(np.int64) * 12 + p.month[rows] - 1
        out = np.full((len(rows), len(COLS)), np.nan, np.float32)
        for j, k in enumerate(KINDS):
            if k not in self.ev:
                continue
            homes, comp = self.ev[k]
            g = np.searchsorted(homes, p.key[rows]); g[g == len(homes)] = 0
            has = homes[g] == p.key[rows]
            base = g.astype(np.int64) * M
            hi = np.searchsorted(comp, base + t0, side="left")       # notices published before January of the year
            lo = np.searchsorted(comp, base + t0 - WINDOW, side="left")
            n = np.where(has, hi - lo, 0)
            ok = n > 0
            last = comp[np.maximum(hi - 1, 0)] - base                # the month of the latest one
            out[ok, 3 * j] = (t0 - last)[ok]
            out[ok, 3 * j + 1] = (last - bought)[ok]
            out[ok, 3 * j + 2] = n[ok]
        return out


def sales(columns=("key", "year", "month", "postcode")):
    """The sale records as the functions below read them: one row per sale, with its month index."""
    tx = pd.read_parquet(TX, columns=list(columns))
    tx["ym"] = tx.year.astype(np.int64) * 12 + tx.month.astype(np.int64) - 1
    return tx


def unseen_rows(kind, year, tx):
    """Homes named in a notice in the WINDOW months before 1 January of `year` that had no sale on record on that
    day: one row per address, with UNSEEN_COLS and whether its first sale on record came in that year (`sold`) or
    between July and the next June (`late`). Care and nursing homes are left out: they are not sold with the estate.
    `tx` is sales(). Everything about the postcode uses only sales before that day."""
    t0 = year * 12
    t = linked(kind, every=True)
    first = tx[tx.key.isin(set(t.key[t.has]))].groupby("key").ym.min()
    f = np.where(t.has, t.key.map(first).fillna(10**9).to_numpy(), 10**9).astype(np.int64)     # month of the first sale on record
    ew = set(tx.postcode.cat.categories.astype(str))                                         # England and Wales
    m = ((t.ym < t0) & (t.ym >= t0 - WINDOW) & (f >= t0) & (t.key != 0) & ~t.care & t.postcode.isin(ew)).to_numpy()
    w = t[m].assign(f=f[m])
    w["n"] = w.groupby("key").key.transform("size").astype("float32")
    w = w.sort_values("ym").drop_duplicates("key", keep="last").reset_index(drop=True)
    w["months"] = (t0 - w.ym).astype("float32")
    w["sold"] = (w.f >= t0) & (w.f < t0 + 12); w["late"] = (w.f >= t0 + 6) & (w.f < t0 + 18)
    w["flat"] = w.flat.astype("float32")
    before = tx[tx.ym < t0]
    on_record = before.groupby("postcode", observed=True).key.nunique()                      # homes with a sale by then
    on_record.index = on_record.index.astype(str)
    for name, cols in (("people", ["own_outright", "own_mortgage", "social_rent", "private_rent", "hh_alone_65", "age_75_84", "age_85_plus"]),
                       ("stock", ["flats", "bungalows", "detached"]), ("now", ["n_addr"])):
        w = w.merge(pd.read_parquet(SIG / f"{name}_postcode.parquet", columns=["postcode"] + cols).drop_duplicates("postcode"),
                    on="postcode", how="left")
    w["on_record"] = (w.postcode.map(on_record).fillna(0) / w.n_addr.clip(lower=1)).clip(upper=2).astype("float32")
    return w[["key", "postcode", "ym", "sold", "late"] + UNSEEN_COLS]


def unseen_homes(score_year, scored, spec_json="research/outputs/lab/notice_unseen.json"):
    """Homes named in a notice in the window before 1 January of `score_year` that have no sale on record, as rows
    like `scored` (export_site_v5.score). Each is scored by the model notice_unseen.py fitted for its kind of notice
    and kept only if that is above what a home on record sells at; it is given the commonest kind of home and the
    median value of its postcode."""
    import lightgbm as lgb
    if not Path(spec_json).exists():
        return scored.iloc[:0]
    spec = json.load(open(spec_json)).get("kinds", {})
    parts, tx = [], None
    for k in KINDS:
        q = spec.get(k)
        if not q or not q.get("file") or not (DIRS[k] / "listing.jsonl").exists():
            continue
        tx = sales() if tx is None else tx
        r = unseen_rows(k, score_year, tx)
        b = lgb.Booster(model_file=str(Path(spec_json).parent / q["file"]))
        assert b.feature_name() == q["columns"] == UNSEEN_COLS, "the model for homes with no sale on record does not match its columns"
        r["p_sale"] = b.predict(r[UNSEEN_COLS].to_numpy(np.float32), num_threads=4)
        parts.append(r.loc[r.p_sale >= q["min_p"], ["key", "postcode", "p_sale"]])
    if not parts:
        return scored.iloc[:0]
    u = pd.concat(parts).sort_values("p_sale").drop_duplicates("key", keep="last")       # both kinds at one home: the higher figure
    place = pd.DataFrame({"postcode": scored.postcode.astype(str).to_numpy(), "ptype": scored.ptype.to_numpy(),
                          "est_value": scored.est_value.to_numpy()})
    kind = place.groupby("postcode").ptype.agg(lambda v: v.mode().iloc[0])
    value = place.groupby(["postcode", "ptype"]).est_value.median()
    u = u[u.postcode.isin(kind.index)].copy()                                           # a postcode with no scored home cannot be placed
    u["ptype"] = u.postcode.map(kind).to_numpy()
    u["est_value"] = value.reindex(pd.MultiIndex.from_arrays([u.postcode, u.ptype])).to_numpy().astype("float32")
    u["tenure"] = np.int16(score_year - 1995)                                           # no sale since the records began
    u["price"] = np.int32(0); u["p_sale"] = u.p_sale.astype("float32"); u["p_year"] = u.p_sale; u["notice"] = True; u["unseen"] = True
    return u.drop(columns="key")


if __name__ == "__main__":
    for k in KINDS:
        if (DIRS[k] / "listing.jsonl").exists():
            t = linked(k, refresh=True)
            print(k, json.dumps(json.load(open(DIRS[k] / "linked.json"))))
