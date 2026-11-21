"""Turn the finished national cells into the tables the rest uses.

  1. Exact postcodes. Each house keeps its lowest UPRN; the ONS UPRN
     Directory says which postcode that address belongs to. Where it has
     no entry the nearest postcode centre (as in the city runs) stays.
     The cell files are rewritten with `postcode` exact and
     `postcode_nearest` kept beside it.
  2. HOUSE signals by postcode (signals.py): every house-level measure
     averaged over the postcode's addresses, plus how much they vary
     between its houses. This is the family the national model is offered.
  3. Every postcode sector in England and Wales, as the city runs
     summarised theirs: the share of addresses with each outlook (long
     views, water, hills, a private garden, evening sun, a sunny garden,
     a south or west-facing garden), the share with a landmark in sight,
     and two real houses to draw, the typical one and the best outlook.
  4. A summary of the whole run: houses, coverage, timing.

Usage: python national_tables.py <national_dir> <uprn_postcode.parquet> <out_house_postcode.parquet>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from signals import HOUSE_COLS  # noqa: E402

MEAN_COLS = [c for c in HOUSE_COLS if not c.startswith("sd_") and c != "garden"]


def cells(nat):
    return sorted(p for p in (Path(nat) / "cells").glob("*.parquet") if not p.stem.endswith("_sight"))


def exact_postcodes(nat, map_path):
    m = pd.read_parquet(map_path)
    up = m.uprn.to_numpy(); pcs = m.postcode.cat.categories.to_numpy(); code = m.postcode.cat.codes.to_numpy()
    n_exact = n_all = 0
    for p in cells(nat):
        h = pd.read_parquet(p)
        if "postcode_nearest" in h.columns:
            n_exact += int((h.postcode != h.postcode_nearest).sum()); n_all += len(h)
            continue
        i = np.searchsorted(up, h.uprn.to_numpy())
        i = np.clip(i, 0, len(up) - 1)
        hit = up[i] == h.uprn.to_numpy()
        exact = np.where(hit, pcs[code[i]], h.postcode.to_numpy())
        h["postcode_nearest"] = h.postcode
        h["postcode"] = exact
        part = h.postcode.str.rsplit(" ", n=1)
        h["sector"] = part.str[0] + " " + part.str[1].str[0]
        h["postcode_source"] = np.where(hit, "ONS directory", "nearest centre")
        h.to_parquet(str(p) + ".tmp", index=False)
        Path(str(p) + ".tmp").replace(p)
        n_exact += int((h.postcode != h.postcode_nearest).sum()); n_all += len(h)
    print(f"exact postcodes: {n_all:,} houses, {n_exact:,} ({n_exact / max(n_all, 1):.1%}) moved off the nearest postcode centre",
          flush=True)


def house_signals(nat, out):
    rows = []
    for p in cells(nat):
        h = pd.read_parquet(p, columns=["postcode", "n_uprn", "has_garden"] + MEAN_COLS)
        w = h.n_uprn.astype(float)
        h["garden"] = h.has_garden.astype(float)
        g = h.assign(_w=w)
        num = g[MEAN_COLS + ["garden"]].multiply(w, axis=0)
        num["_w"] = w
        for c in MEAN_COLS + ["garden"]:
            num[f"_n_{c}"] = w * g[c].notna()
        num = num.fillna(0.0)
        num["postcode"] = h.postcode.to_numpy()
        num["_sq_u_long"] = w * h.u_long.fillna(0) ** 2
        num["_sq_light_both"] = w * h.light_both.fillna(0) ** 2
        num["_houses"] = 1
        rows.append(num.groupby("postcode").sum())
    s = pd.concat(rows).groupby(level=0).sum()
    t = pd.DataFrame(index=s.index)
    for c in MEAN_COLS + ["garden"]:
        t[c] = (s[c] / s[f"_n_{c}"].replace(0, np.nan)).astype("float32")
    for c in ("u_long", "light_both"):
        var = s[f"_sq_{c}"] / s._w - (s[c] / s._w) ** 2
        t[f"sd_{c}"] = np.sqrt(np.clip(var, 0, None)).where(s._houses >= 2).astype("float32")
    t["n_houses"] = s._houses.astype(int); t["n_addresses"] = s._w.astype(int)
    t = t.reset_index()
    t.to_parquet(out, index=False)
    print(f"HOUSE signals: {len(t):,} postcodes from {int(s._houses.sum()):,} houses", flush=True)
    return t


def sectors(nat, out):
    flags = ["has_long", "has_water", "has_tidal", "has_hills", "has_private", "has_evening", "has_sunny",
             "has_swgarden", "has_garden"]
    rows = []
    for p in cells(nat):
        h = pd.read_parquet(p, columns=["sector", "x", "y", "n_uprn", "u_long", "u_water", "u_hills", "u_longest_km",
                                        "u_horizon", "sun_equinox", "sun_evening_jun", "lm_n", "lm_cathedral"] + flags)
        h["lm_any"] = h.lm_n > 0; h["lm_cathedral_any"] = h.lm_cathedral > 0
        h["outlook"] = h.u_long.fillna(0) + 2 * h.u_water.fillna(0) + h.u_hills.fillna(0) + 0.02 * h.u_longest_km.fillna(0) \
            + 0.3 * h.lm_n.clip(upper=5) / 5
        for sec, g in h.groupby("sector"):
            w = g.n_uprn.to_numpy(float)
            r = {"sector": sec, "houses": len(g), "addresses": int(w.sum())}
            for f in flags + ["lm_any", "lm_cathedral_any"]:
                name = {"lm_any": "share_landmark", "lm_cathedral_any": "share_cathedral"}.get(f, f.replace("has_", "share_"))
                r[name] = float(np.average(g[f].fillna(False).astype(float), weights=w))
            z = sum(((g[c] - g[c].median()) / (g[c].std() or 1.0)).fillna(3.0) ** 2
                    for c in ("u_long", "u_horizon", "sun_equinox", "sun_evening_jun"))
            t = g.loc[z.idxmin()]; b = g.loc[g.outlook.idxmax()]
            r.update(typical_x=int(t.x), typical_y=int(t.y), best_x=int(b.x), best_y=int(b.y),
                     best_outlook_km=float(b.u_longest_km))
            rows.append(r)
    t = pd.DataFrame(rows)
    # a sector can straddle two cells: keep the row with more houses
    t = t.sort_values("houses", ascending=False).drop_duplicates("sector").sort_values("sector")
    t.to_parquet(out, index=False)
    print(f"sectors: {len(t):,} postcode sectors summarised", flush=True)


def summary(nat):
    info = [json.load(open(p)) for p in (Path(nat) / "cells").glob("*.json")]
    S = {"cells": len(info), "houses": int(sum(i.get("houses", 0) for i in info)),
         "positions": int(sum(i.get("positions", 0) for i in info)),
         "landmark_pairs": int(sum(i.get("pairs", 0) for i in info)),
         "in_sight": int(sum(i.get("in_sight", 0) for i in info)),
         "surveyed_share_mean": round(float(np.mean([i.get("surveyed", 1) for i in info])), 4),
         "compute_hours": round(sum(i.get("load_s", 0) + i.get("geometry_s", 0) + i.get("views_s", 0) for i in info) / 3600, 1)}
    json.dump(S, open(Path(nat) / "summary.json", "w"), indent=1)
    print(S)


if __name__ == "__main__":
    nat, map_path, out = sys.argv[1:4]
    exact_postcodes(nat, map_path)
    house_signals(nat, out)
    sectors(nat, Path(nat) / "sectors.parquet")
    summary(nat)
