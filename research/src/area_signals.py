"""AREA signals by postcode, and each address's exact postcode, from the ONS
UPRN Directory extract (onsud_extract.py).

  imd_rank   deprivation rank of the address's LSOA as a share of the
             country's LSOAs (0 = most deprived, 1 = least), England's IMD
             2025 and Wales's WIMD on the same 0-1 scale; postcode average
  rural      share of the postcode's addresses in a rural area (RUC 2021)
  oac_1..8   share of the postcode's addresses in each census output-area
             classification supergroup (2021)

Usage: python area_signals.py <parts_dir> <out_area.parquet> <out_uprn_postcode.parquet>
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def main(parts, out_area, out_map):
    files = sorted(Path(parts).glob("*.parquet"))
    sums, maps, maxrank = [], [], {"E": 0, "W": 0}
    for f in files:                                   # first pass: the largest rank in each country
        d = pd.read_parquet(f, columns=["lsoa21cd", "imd25ind"])
        r = pd.to_numeric(d.imd25ind, errors="coerce")
        for k in maxrank:
            m = d.lsoa21cd.str.startswith(k).fillna(False).to_numpy()
            if m.any():
                maxrank[k] = max(maxrank[k], float(np.nanmax(r[m])))
    print("largest deprivation rank:", maxrank, flush=True)
    for f in files:
        d = pd.read_parquet(f)
        d = d[d.postcode.notna()]
        r = pd.to_numeric(d.imd25ind, errors="coerce").to_numpy(dtype=float)
        top = np.where(d.lsoa21cd.str.startswith("W").fillna(False).to_numpy(), maxrank["W"], maxrank["E"])
        x = pd.DataFrame({"postcode": d.postcode.astype(str).to_numpy(), "n": 1.0,
                          "imd": r / top, "imd_n": np.isfinite(r).astype(float),
                          "rural": d.ruc21ind.str.startswith("R").fillna(False).to_numpy(dtype=float)})
        sg = pd.to_numeric(d.oac21ind.str[0], errors="coerce").to_numpy()
        for k in range(1, 9):
            x[f"oac_{k}"] = (sg == k).astype(float)
        x["imd"] = np.nan_to_num(x.imd)
        sums.append(x.groupby("postcode").sum())
        maps.append(pd.DataFrame({"uprn": d.uprn.to_numpy(dtype=np.int64), "postcode": d.postcode.astype(str).to_numpy()}))
        print(f.name, len(d), flush=True)
    s = pd.concat(sums).groupby(level=0).sum()
    out = pd.DataFrame(index=s.index)
    out["imd_rank"] = s.imd / s.imd_n.replace(0, np.nan)
    out["rural"] = s.rural / s.n
    for k in range(1, 9):
        out[f"oac_{k}"] = s[f"oac_{k}"] / s.n
    out["n_addresses"] = s.n.astype(int)
    out.reset_index().to_parquet(out_area, index=False)
    m = pd.concat(maps, ignore_index=True)
    m["postcode"] = m.postcode.astype("category")
    m.sort_values("uprn").to_parquet(out_map, index=False)
    print(f"{len(out):,} postcodes; {len(m):,} addresses with an exact postcode")


if __name__ == "__main__":
    main(*sys.argv[1:4])
