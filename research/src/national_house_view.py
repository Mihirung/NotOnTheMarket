"""Draw any house in England and Wales from the national run's stored arrays:
its upstairs view with the landmarks in sight, its garden with the sun's
path, and its facts. The same drawing code as the prototype site.

    python national_house_view.py <easting> <northing> <out.html>

Also used by find_best.py to draw the top houses on one page.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import views2 as V  # noqa: E402
from national_views import load_panos  # noqa: E402

NAT = Path("research/outputs/national")
LMK = "research/data/landmarks/national_landmarks.parquet"
TEMPLATE = Path(__file__).parent.parent.parent / "web" / "template.html"
COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
comp = lambda b: COMPASS[int(round(b / 45)) % 8]
hrs = lambda x: "none" if not np.isfinite(x) or x < 0.25 else f"{round(x * 2) / 2:g} h"
_text = lambda codes, none=None: "".join(" " if (none is not None and c == none) else V.ALPH[c] for c in codes.tolist())
_cell = lambda x, y: f"{int(x) // 10_000}_{int(y) // 10_000}"


def view_dict(a, c, w, row=None, lms=()):
    out = {"a": [_text(x) for x in a], "c": ["".join(map(str, x.tolist())) for x in c],
           "wl": _text(w[0], 255), "wh": _text(w[1], 255), "lm": []}
    if row is not None:
        deg = V.decode_angles(a); R = a.shape[1]
        for name, le, ln, lz in lms:
            d = float(np.hypot(le - row.e, ln - row.n))
            drop = d ** 2 / (2 * V.R_EARTH) * (1 - V.REFRACTION)
            brg = float(np.degrees(np.arctan2(le - row.e, ln - row.n)) % 360)
            ang = float(np.degrees(np.arctan((lz - drop - row.eye_up) / max(d, 1.0))))
            i0 = int(np.floor(brg / 360 * R)) % R; i1 = (i0 + 1) % R
            nearer = [min(deg[k, i0], deg[k, i1]) for k, hi in enumerate(V.PANO_EDGES[1:]) if hi <= d]
            drawn = ang >= (max(nearer) if nearer else -90.0) - 0.3
            out["lm"].append({"name": name, "b": round(brg, 1), "a": round(ang, 2), "km": round(d / 1000, 1), "sees": bool(drawn)})
    return out


def house(x, y):
    """Everything needed to draw the house at grid cell (x, y): its row, both views, its landmarks."""
    cell = _cell(x, y)
    h = pd.read_parquet(NAT / "cells" / f"{cell}.parquet")
    i = int(np.argmin(np.hypot(h.x - x, h.y - y)))
    row = h.iloc[i]
    P = load_panos(NAT, int(cell.split("_")[0]) * 1000 + int(cell.split("_")[1]))
    j = int(row.h3)
    seen = pd.read_parquet(NAT / "cells" / f"{cell}_sight.parquet")
    seen = seen[seen.hid == j].sort_values("dist_m")
    lm = pd.read_parquet(LMK).set_index("lid").loc[seen.lid.to_numpy()]
    lms = [(n, e, n_, z) for n, e, n_, z in zip(lm.name, lm.e, lm.n, lm.top_m)][:12]
    up = view_dict(P["pu_a"][j], P["pu_c"][j], P["pu_w"][j], row, lms)
    garden = view_dict(P["pg_a"][j], P["pg_c"][j], P["pg_w"][j]) if bool(row.has_garden) else None
    return row, up, garden


EXTRA = {"nox": ("Nitrogen oxides in the air", lambda v: f"{v:.0f} µg/m³"),
         "km_gp": ("Nearest GP", lambda v: f"{v:.1f} km"), "km_hospital": ("Nearest hospital", lambda v: f"{v:.1f} km"),
         "km_park": ("Nearest park or playing field", lambda v: f"{v * 1000:.0f} m"),
         "park_ha_1km": ("Parkland within 1 km", lambda v: f"{v:.0f} ha"),
         "km_wood": ("Nearest woodland", lambda v: f"{v:.1f} km"),
         "km_blue": ("Nearest river, lake or sea", lambda v: f"{v:.1f} km"), "km_sea": ("Coast", lambda v: f"{v:.1f} km"),
         "km_pub": ("Nearest pub", lambda v: f"{v * 1000:.0f} m"), "km_pub_far": ("Nearest pub", lambda v: f"{v * 1000:.0f} m"),
         "restaurants_1km": ("Restaurants and cafes within 1 km", lambda v: f"{v:.0f}"),
         "takeaways_1km": ("Takeaways within 1 km", lambda v: f"{v:.0f}"),
         "add_m2": ("Floor space that could be added without planning permission (estimate)", lambda v: f"about {v:.0f} m²"),
         "add_value": ("Value that could add, at 2019 prices (estimate)", lambda v: f"about £{v:,.0f}")}


def facts(row, want=()):
    f = [["Postcode", f"{row.postcode}"], ["Storeys, estimated from roof height", str(int(row.storeys))],
         ["Front faces", comp(row.front_bearing)],
         ["Furthest you can see from the top floor", f"{row.u_longest_km:.0f} km"],
         ["Share of the horizon with a view beyond 2 km", f"{row.u_long * 100:.0f}%"],
         ["Landmarks in sight from the top floor", str(int(row.lm_n))],
         ["Direct sun on the windows, front and back together", f"{hrs(row.light_both)} a day, averaged over the year"]]
    if bool(row.has_garden):
        f += [["Garden lies to the", comp(row.garden_bearing)],
              ["Garden overlooked from", f"{row.g_overlooked * 100:.0f}% of directions"],
              ["Evening sun in the garden at midsummer", hrs(row.sun_evening_jun)]]
    seen = set()
    for k, (label, fmt) in EXTRA.items():
        v = row.get(k) if hasattr(row, "get") else None
        if v is not None and np.isfinite(v) and label not in seen:
            f.append([label, fmt(float(v))]); seen.add(label)
    for w, label in want:
        if f"below_{w}" in row:
            b = row[f'below_{w}']
            f.append([f"Nationally, {label}", f"better than {b:.1f}% of homes" if b >= 99 else f"better than {b:.0f}% of homes"])
    return f


def page(items, title):
    tpl = TEMPLATE.read_text()
    css = re.search(r"<style>(.*?)</style>", tpl, re.S).group(1)
    js = tpl[tpl.index("const _dec = new WeakMap();"):tpl.index("const andList")]
    sun = tpl[tpl.index("function sunBoxes(p, city){"):tpl.index("const HOME_TITLE")]
    payload = json.dumps({"alph": V.ALPH, "a_lo": round(float(V.A_LO), 4), "a_span": round(float(V.A_SPAN), 4),
                          "items": items, "title": title}, separators=(",", ":")).replace("</", "<\\/")
    return """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Best houses</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,800&family=Spectral:ital,wght@0,400;0,500;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>""" + css + """ h2{font-size:24px;margin:40px 0 6px} h3{font-size:16px;margin:18px 0 6px}</style>
<div class="wrap" style="max-width:980px;padding-bottom:50px"><div id="app"></div></div>
<script>
const DATA = """ + payload + """;
const esc = s => String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
""" + js + sun + """
document.getElementById("app").innerHTML = `
  <div class="eyebrow" style="margin-top:26px">Quiet Market · every house in England and Wales</div>
  <h1 style="font-size:34px;margin:8px 0 10px">${esc(DATA.title)}</h1>
  ${DATA.items.map((h,k)=>`${h.section?`<div class="eyebrow" style="margin-top:52px">${esc(h.section)}</div>
  ${h.blurb?`<p class="note" style="margin:6px 0 0">${esc(h.blurb)}</p>`:""}`:""}
  <h2>${h.rank||k+1}. ${esc(h.headline)}</h2>
  <div class="panel">${h.facts.map(f=>`<div class="kv"><span class="k">${esc(f[0])}</span><span class="v">${esc(f[1])}</span></div>`).join("")}</div>
  <h3>The view from the top floor</h3>
  <div class="pano panoscroll">${panoSVG(h.up,{label:"Drawn view from the top floor"})}</div>
  ${h.garden?`<h3>The garden and the sun's path</h3>
  <div class="pano panoscroll">${panoSVG(h.garden,{sun:true,lat:h.lat,lon:h.lon,label:"Drawn view from the garden"})}</div>${sunBoxes(h.garden,{lat:h.lat,lon:h.lon})}`:""}`).join("")}
  ${HZ_LEGEND}
  <p class="note" style="margin-top:26px">From the Environment Agency's and Natural Resources Wales's 1 metre laser surveys, Ordnance Survey
  building outlines and address points, and the ONS UPRN Directory. Not a photograph, and nobody has visited.</p>`;
</script>"""


def item(row, want=()):
    from pyproj import Transformer
    lon, lat = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True).transform(float(row.x), float(row.y))
    r, up, garden = house(row.x, row.y)
    r = r.copy()
    for w, _ in want:
        for k in (f"pct_{w}", f"below_{w}"):
            if k in row:
                r[k] = row[k]
    for k in EXTRA:                                   # postcode and building-work measures the search attached
        if k in row and k not in r:
            r[k] = row[k]
    head = f"A {int(r.storeys)}-storey home in {r.postcode}"
    return {"headline": head, "facts": facts(r, want), "up": up, "garden": garden, "lat": lat, "lon": lon}


def write_many(top, out, want=(), title="The best homes in England and Wales"):
    items = [item(top.iloc[i], want) for i in range(len(top))]
    Path(out).write_text(page(items, title))


if __name__ == "__main__":
    x, y, out = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
    r, up, garden = house(x, y)
    write_many(pd.DataFrame([r]), out, title=f"One home in {r.postcode}")
    print("wrote", out)
