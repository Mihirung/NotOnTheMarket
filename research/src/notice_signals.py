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


def linked(kind, tx_keys=None, refresh=False, every=False):
    """(home key, month published) for every notice whose address is a home with a sale record. With `every`,
    the notices that match no such home are returned too (has = False, with their postcode).
    Kept in <dir>/linked.parquet and rebuilt when the listing has grown."""
    from planning_link import key_of, readings
    d = DIRS[kind]; src, out, info = d / "listing.jsonl", d / "linked.parquet", d / "linked.json"
    n_lines = sum(1 for _ in open(src))
    if not (out.exists() and info.exists() and json.load(open(info))["notices"] == n_lines and not refresh):
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
        r = r[r.key.isin(tx_keys)].sort_values(["i", "rank"]).drop_duplicates("i")    # the first reading that is a known home
        key = np.zeros(len(n), np.int64); has = np.zeros(len(n), bool)
        key[r.i.to_numpy()] = r.key.to_numpy(); has[r.i.to_numpy()] = True
        t = pd.DataFrame({"key": key, "has": has, "ym": (n.pub.dt.year * 12 + n.pub.dt.month - 1).to_numpy().astype("int32"),
                          "postcode": n.postcode.to_numpy()})
        t.to_parquet(out, index=False)
        by = pd.DataFrame({"y": n.pub.dt.year.to_numpy(), "got": has}).groupby("y").got.agg(["size", "sum"])
        json.dump({"notices": n_lines, "with_an_address": int(len(n)), "linked_to_a_home": int(has.sum()),
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


if __name__ == "__main__":
    for k in KINDS:
        if (DIRS[k] / "listing.jsonl").exists():
            t = linked(k, refresh=True)
            print(k, json.dumps(json.load(open(DIRS[k] / "linked.json"))))
