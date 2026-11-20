"""Draw any one house: its view from the upper windows, its garden with the
sun's path, and the hours of direct sun on its windows.

Every house in a city has its panorama stored by city_views.py, so this
needs no terrain data and takes a second. The page it writes uses the
same drawing code as the prototype site. It prints no address: open data
has none. The house is chosen by its row in the house table, or as the
house nearest a British National Grid easting and northing.

Usage:
  python house_view.py <exeter|bath> <views2_dir> <out_html> <row>
  python house_view.py <exeter|bath> <views2_dir> <out_html> <easting> <northing>
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import city_views as CV  # noqa: E402
from views2 import ALPH, A_LO, A_SPAN  # noqa: E402

TEMPLATE = Path(__file__).parent.parent.parent / "web" / "template.html"
COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
hrs = lambda x: "none" if x < 0.25 else f"{round(x * 2) / 2:g} h"
comp = lambda b: COMPASS[int(round(b / 45)) % 8]


def build(city, views_dir, row):
    cfg = CV.CITIES[city]; vd = Path(views_dir)
    h = pd.read_parquet(vd / f"houses_{city}.parquet")
    P = np.load(vd / f"panos_{city}.npz")
    meta = json.load(open(vd / f"sectors_{city}.json"))["meta"]
    lmk = [(l["name"], l["e"], l["n"], l["top_m"]) for l in meta["landmarks"]]
    r = h.loc[row]
    pct = lambda col, v: int(round(float((h[col] < v).mean() * 100)))
    home = CV.home_entry({k: P[k][row:row + 1] for k in P.files}, 0, r, lmk, "other")
    seen = [x["name"] for x in home["up"]["lm"] if x["sees"]]
    facts = [["Storeys, estimated from roof height", str(int(r.storeys))],
             ["Front faces", comp(r.front_bearing)],
             ["Furthest you can see from the top floor", f"{r.u_longest_km:.0f} km ({cfg['name']} typical: {h.u_longest_km.median():.0f} km)"],
             ["Share of the horizon with a view beyond 2 km", f"{r.u_long * 100:.0f}%, more than {pct('u_long', r.u_long)}% of homes"],
             ["Landmarks in sight from the top floor", ", ".join(seen) if seen else "none"]]
    if bool(r.has_garden):
        facts += [["Garden lies to the", comp(r.garden_bearing)],
                  ["Garden overlooked from", f"{r.g_overlooked * 100:.0f}% of directions ({cfg['name']} typical: {h.g_overlooked.median() * 100:.0f}%)"],
                  ["Evening sun in the garden at midsummer", f"{hrs(r.sun_evening_jun)}, more than {pct('sun_evening_jun', r.sun_evening_jun)}% of gardens"]]
    light = None
    if (vd / f"light_{city}.parquet").exists():
        L = pd.read_parquet(vd / f"light_{city}.parquet"); l = L.loc[row]
        light = {"rows": [[f"{floor} {side} windows"] + [hrs(l[f"{f}_{side}_{k}"]) for k in ("year", "jun", "equinox", "dec")]
                          for floor, f in (("Downstairs", "down"), ("Top-floor", "top")) for side in ("front", "back")],
                 "pct": int(round(float((L.light_best < l.light_best).mean() * 100))), "best": hrs(l.light_best),
                 "side": "front" if l.light_front >= l.light_back else "back"}
    return {"alph": ALPH, "a_lo": round(float(A_LO), 4), "a_span": round(float(A_SPAN), 4),
            "city": cfg["name"], "lat": cfg["centre"][0], "lon": cfg["centre"][1], "row": int(row), "n": int(len(h)),
            "sector": r.sector, "facts": facts, "light": light, "home": home}


def page(data):
    tpl = TEMPLATE.read_text()
    css = re.search(r"<style>(.*?)</style>", tpl, re.S).group(1)
    js = tpl[tpl.index("const _dec = new WeakMap();"):tpl.index("const andList")]
    sun = tpl[tpl.index("function sunBoxes(p, city){"):tpl.index("const HOME_TITLE")]
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>One house</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,800&family=Spectral:ital,wght@0,400;0,500;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>""" + css + """
table.lt{border-collapse:collapse;width:100%;font-size:14.5px;margin-top:8px} table.lt th,table.lt td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line)}
table.lt th{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:500}
h3{font-size:17px;margin:24px 0 6px}</style>
<div class="wrap" style="max-width:980px;padding-bottom:50px"><div id="app"></div></div>
<script>
const DATA = """ + payload + """;
const esc = s => String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
""" + js + sun + """
const city = {lat: DATA.lat, lon: DATA.lon}, h = DATA.home;
document.getElementById("app").innerHTML = `
  <div class="eyebrow" style="margin-top:26px">Quiet Market · one house in ${esc(DATA.sector)}, ${esc(DATA.city)}</div>
  <h1 style="font-size:34px;margin:8px 0 10px">House ${(DATA.row+1).toLocaleString()} of ${DATA.n.toLocaleString()}</h1>
  <div class="panel">${DATA.facts.map(f=>`<div class="kv"><span class="k">${esc(f[0])}</span><span class="v">${esc(f[1])}</span></div>`).join("")}</div>
  <h3>The view from the top floor, front and back windows together</h3>
  <div class="pano panoscroll">${panoSVG(h.up,{label:"Drawn view from the top floor"})}</div>${HZ_LEGEND}
  ${DATA.light?`<h3>Direct sun on the windows, hours a day</h3>
  <table class="lt"><tr><th></th><th>Year average</th><th>Midsummer</th><th>Equinox</th><th>Midwinter</th></tr>
    ${DATA.light.rows.map(r=>`<tr>${r.map(c=>`<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</table>
  <p class="note">The sunnier side downstairs is the <b>${DATA.light.side}</b>, at ${DATA.light.best} a day averaged over the year: lighter than ${DATA.light.pct}% of homes in ${esc(DATA.city)}.</p>`:""}
  ${h.garden?`<h3>The garden and the sun's path</h3>
  <div class="pano panoscroll">${panoSVG(h.garden,{sun:true,lat:city.lat,lon:city.lon,label:"Drawn view from the garden"})}</div>${sunBoxes(h.garden,city)}`:""}
  <p class="note" style="margin-top:26px">From the Environment Agency's 1 metre laser survey, Ordnance Survey building outlines and address points.
  Not a photograph, and nobody has visited.</p>`;
</script>"""


if __name__ == "__main__":
    city, views_dir, out = sys.argv[1:4]
    if len(sys.argv) > 5:
        h = pd.read_parquet(Path(views_dir) / f"houses_{city}.parquet", columns=["e", "n"])
        row = int(np.hypot(h.e - float(sys.argv[4]), h.n - float(sys.argv[5])).idxmin())
    else:
        row = int(sys.argv[4])
    Path(out).write_text(page(build(city, views_dir, row)))
    print(f"wrote {out} for house {row}")
