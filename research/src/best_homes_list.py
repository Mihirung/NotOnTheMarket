"""The very best homes in England and Wales, with postcodes, positions and the
addresses in each postcode, overall and at a value of £2m or less.

"Best" is find_best.py's "very best of everything": the average national
percentile across every outlook, garden, light, landmark, health,
green and blue space and climate measure it scores as near-universally
wanted (find_best.ALL). One home per postcode.

The value of each home: what the same type of home in its postcode is worth
(the sale-record estimate at 2019 prices used by the site), brought up to
date with the UK House Price Index for its local authority and property
type, to the latest month published. The house's type comes from its
building outline: alone on it, detached; two addresses, semi-detached; more,
terraced; several addresses in the one building, a flat.

Open data does not link a mapped building to its house number, so each home
is given with its exact position (a map link that opens on it) and the
addresses in its postcode from the Land Registry sale records, the same type
of home first.

For the user's own research: the output stays on this machine and is never
published (research/outputs/national/best_homes* is ignored by git).

Usage: python best_homes_list.py [top] [max_value]
"""
import glob
import html
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "research/src")
import find_best as FB  # noqa: E402

NAT = Path("research/outputs/national")
PPD = "/home/user/dmaso01/ppd/pp-*.csv.zip"
PPD_COLS = ["tid", "price", "date", "postcode", "ptype", "new", "tenure", "paon", "saon", "street", "locality", "town",
            "district", "county", "cat", "status"]
TYPE_NAME = {"D": "detached house", "S": "semi-detached house", "T": "terraced house", "F": "flat"}
HPI_COL = {"D": "DetachedIndex", "S": "SemiDetachedIndex", "T": "TerracedIndex", "F": "FlatIndex"}


def house_types(top):
    """D, S, T or F for each chosen house, from its building outline."""
    out = pd.Series("D", index=top.index)
    for cell, g in top.groupby("cell"):
        f = NAT / "plots" / f"{int(cell) // 1000}_{int(cell) % 1000}.parquet"
        if f.exists():
            p = pd.read_parquet(f, columns=["h3", "n_on_outline"]).set_index("h3").n_on_outline
            n = g.h3.map(p).fillna(1)
            out.loc[g.index] = np.where(n >= 3, "T", np.where(n == 2, "S", "D"))
    out[top.n_uprn.to_numpy() > 1] = "F"
    return out


def hpi_ratio(postcodes, types):
    """Latest House Price Index over its 2019 average, by local authority and property type."""
    h = pd.read_csv("research/data/hpi/hpi.csv", usecols=["Date", "AreaCode"] + list(HPI_COL.values()))
    h["Date"] = pd.to_datetime(h.Date, dayfirst=True)
    last = h.dropna(subset=["DetachedIndex"]).Date.max()
    base = h[h.Date.dt.year == 2019].groupby("AreaCode")[list(HPI_COL.values())].mean()
    now = h[h.Date == last].set_index("AreaCode")[list(HPI_COL.values())]
    ratio = now / base
    lad = pd.concat([pd.read_parquet(f, columns=["postcode", "lad26cd"], filters=[("postcode", "in", list(set(postcodes)))])
                     for f in glob.glob("research/data/onsud/parts/*.parquet")]).drop_duplicates("postcode")
    lad = lad.set_index("postcode").lad26cd
    nat = ratio.loc["K04000001"] if "K04000001" in ratio.index else ratio.median()
    out = []
    for pc, t in zip(postcodes, types):
        code = lad.get(pc)
        r = ratio.loc[code, HPI_COL[t]] if code in ratio.index else np.nan
        out.append(r if np.isfinite(r) else nat[HPI_COL[t]])
    return np.array(out), last


def values(top, types):
    s = pd.read_parquet("research/outputs/site5_cache/scored_all.parquet", columns=["postcode", "ptype", "est_value"])
    s = s[s.postcode.astype(str).isin(set(top.postcode.astype(str)))]
    s["postcode"] = s.postcode.astype(str)
    by_type = s.groupby(["postcode", "ptype"]).est_value.median()
    houses = s[s.ptype != "F"].groupby("postcode").est_value.median()
    v = []
    for pc, t in zip(top.postcode.astype(str), types):
        x = by_type.get((pc, t), np.nan)
        if not np.isfinite(x) and t != "F":
            x = houses.get(pc, np.nan)
        v.append(x)
    return np.array(v, float)


def addresses(postcodes):
    want = set(postcodes)
    rows = []
    for f in sorted(glob.glob(PPD)):
        z = zipfile.ZipFile(f)
        t = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])), header=None, names=PPD_COLS, dtype=str,
                        usecols=["price", "date", "postcode", "ptype", "paon", "saon", "street", "locality", "town"])
        rows.append(t[t.postcode.isin(want)])
    a = pd.concat(rows).sort_values("date")
    a["addr"] = (a.saon.fillna("") + " " + a.paon.fillna("") + " " + a.street.fillna("")).str.split().str.join(" ").str.title()
    last = a.groupby(["postcode", "addr"]).agg(ptype=("ptype", "last"), date=("date", "last"), price=("price", "last"),
                                                town=("town", "last"), locality=("locality", "last")).reset_index()
    return last


def main(n_top=25, cap=2_000_000):
    want = FB.ALL
    df = FB.load([FB.CHAR[w][0] for w in want])
    df["_row"] = np.arange(len(df))
    df, ranks, below = FB.score(df, want)
    cand = df.sort_values(["score", "weakest"], ascending=False).drop_duplicates("postcode").head(4000).copy()
    cand = FB.describe(cand, want, ranks, below)
    del df, ranks, below
    cand["type"] = house_types(cand).to_numpy()
    v19 = values(cand, cand.type)
    ratio, last = hpi_ratio(cand.postcode.astype(str).tolist(), cand.type.tolist())
    cand["value_2019"] = v19
    cand["value_now"] = v19 * ratio
    from pyproj import Transformer
    lon, lat = Transformer.from_crs(27700, 4326, always_xy=True).transform(cand.x.to_numpy() + 0.5, cand.y.to_numpy() + 0.5)
    cand["lat"], cand["lon"] = np.round(lat, 6), np.round(lon, 6)
    best = cand.head(n_top).assign(list="The very best homes in England and Wales")
    under = cand[cand.value_now <= cap].head(n_top).assign(list=f"The very best at £{cap / 1e6:g}m or less")
    sel = pd.concat([best, under])
    addr = addresses(sel.postcode.astype(str).unique().tolist())
    write(sel, addr, want, last, cap)


def write(sel, addr, want, last, cap):
    label = {w: FB.CHAR[w][2] for w in want}
    rows, parts = [], []
    for lst, g in sel.groupby("list", sort=False):
        parts.append(f"<h2>{html.escape(lst)}</h2>")
        for i, (_, r) in enumerate(g.iterrows(), 1):
            pcs = [(w, r[f"pct_{w}"]) for w in want]
            strong = sorted(pcs, key=lambda t: -t[1])[:6]
            weak = min(pcs, key=lambda t: t[1])
            a = addr[addr.postcode == r.postcode].copy()
            a["match"] = (a.ptype == r.type).astype(int)
            a = a.sort_values(["match", "date"], ascending=False)
            town = (a.town.mode().iloc[0].title() if len(a) else "")
            val = f"about £{r.value_now:,.0f}" if np.isfinite(r.value_now) else "no sale record of this type"
            maps = f"https://www.google.com/maps?q={r.lat},{r.lon}"
            alist = "".join(f"<li>{html.escape(x.addr)}{', ' + html.escape(x.locality.title()) if isinstance(x.locality, str) else ''}"
                            f" <span class=n>({TYPE_NAME.get(x.ptype, x.ptype)}, last sold {x.date[:4]} for £{int(x.price):,})</span></li>"
                            for x in a.head(12).itertuples())
            parts.append(f"""<div class=home><h3>{i}. {html.escape(r.postcode)} <span class=n>{html.escape(town)}</span></h3>
<p><b>Score {r.score:.1f}</b> (average national percentile across {len(want)} measures; weakest {r.weakest:.0f}, on
{html.escape(label[weak[0]])}). A {TYPE_NAME[r.type]}, {int(r.storeys)} storey{'s' if int(r.storeys) != 1 else ''}. Value today: <b>{val}</b>.</p>
<p>Best at: {'; '.join(f'{html.escape(label[w])} ({p:.1f})' for w, p in strong)}.</p>
<p><a href="{maps}">The house on a map</a> ({r.lat}, {r.lon})</p>
<p class=n>Addresses in {html.escape(r.postcode)} from the sale records, the same type first:</p><ul>{alist or '<li>none on record</li>'}</ul></div>""")
            rows.append({"list": lst, "rank": i, "postcode": r.postcode, "town": town, "type": TYPE_NAME[r.type],
                         "storeys": int(r.storeys), "score": r.score, "weakest": r.weakest, "value_now": round(r.value_now, -3)
                         if np.isfinite(r.value_now) else None, "lat": r.lat, "lon": r.lon, "map": maps,
                         "addresses_same_type": " | ".join(a[a.match == 1].addr.head(8)),
                         **{f"pct_{w}": r[f"pct_{w}"] for w in want}})
    css = ("body{font:15px/1.5 Georgia,serif;max-width:900px;margin:30px auto;padding:0 16px;color:#222}"
           "h2{margin-top:40px;font-family:Helvetica,Arial,sans-serif}.home{border-top:1px solid #ccc;padding:8px 0}"
           ".n{color:#666;font-size:13px}h3{margin:10px 0 4px;font-family:Helvetica,Arial,sans-serif}")
    page = (f"<!doctype html><meta charset=utf-8><title>The very best homes</title><style>{css}</style>"
            f"<h1>The very best homes in England and Wales</h1><p class=n>Scored on {len(want)} measures for every one of "
            f"24 million houses. Values are the same type of home in the postcode, from sale records, brought to "
            f"{last:%B %Y} with the House Price Index. Not published; for research.</p>" + "".join(parts))
    (NAT / "best_homes_addresses.html").write_text(page)
    pd.DataFrame(rows).to_csv(NAT / "best_homes_addresses.csv", index=False)
    print(pd.DataFrame(rows)[["list", "rank", "postcode", "town", "type", "score", "value_now"]].to_string())


if __name__ == "__main__":
    main(*(int(float(x)) for x in sys.argv[1:3]))
