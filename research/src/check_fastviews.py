"""Check the compiled engine against the city engine on real houses.

Loads one city's rasters, takes a random sample of its houses, and works
out every measure both ways: the upstairs view from the front and back
walls, the garden view and its sun, the drawing bands, the window sun and
the landmark sight-lines. Prints how often they agree and how long each
takes per house.

Usage: python check_fastviews.py <city> <views2_dir> [n_houses]
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import city_views as CV  # noqa: E402
import fastviews as F  # noqa: E402
import views2 as V  # noqa: E402


def main(city, views_dir, n=300):
    cfg = CV.CITIES[city]
    t = time.time()
    CV.CITY, bld, imp = CV.load_city(cfg, f"research/data/terrain/cache_{city}")
    lmk = CV.landmarks(cfg, CV.CITY)
    print(f"loaded in {time.time() - t:.0f}s", flush=True)
    h = pd.read_parquet(Path(views_dir) / f"houses_{city}.parquet")
    # a neighbourhood's worth of houses in a compact block, as the national run batches them
    c = h.iloc[len(h) // 2]
    h = h.iloc[np.argsort(np.hypot(h.e - c.e, h.n - c.n))[:int(n)]]
    h = h.iloc[np.lexsort((h.e.to_numpy(), (h.n // 50).to_numpy()))].reset_index(drop=True)
    front = h.front_bearing.to_numpy(dtype=float)
    fp = CV.facade_points(h, front, bld, CV.CITY)
    fe, fn, fz, _ = fp["front"]; be, bn, bz, _ = fp["back"]
    eye = h.eye_up.to_numpy()
    zf, zb = np.maximum(eye, fz + 1.6), np.maximum(eye, bz + 1.6)
    F.cast(CV.CITY, fe[:2], fn[:2], zf[:2]); F.skyline(CV.CITY, fe[:2], fn[:2], zf[:2]); F.sightlines(CV.CITY, fe[:2], fn[:2], zf[:2], fe[:2] + 500, fn[:2], zf[:2])

    t = time.time()
    cf = V.cast(CV.CITY, fe, fn, zf, False); cb = V.cast(CV.CITY, be, bn, zb, False)
    o1, (sl, vi, cl) = V.compose(cf, cb, cf[0]["bearing"], front)
    m1 = V.metrics(o1, "u"); a1, c1, w1 = V.bands_from_cast(sl, vi, cl)
    t_old = time.time() - t
    t = time.time()
    o2, b2 = F.compose(F.cast(CV.CITY, fe, fn, zf), F.cast(CV.CITY, be, bn, zb), front)
    m2 = V.metrics(o2, "u")
    t_new = time.time() - t
    print(f"\nupstairs view, {n} houses: city engine {1000 * t_old / n:.1f} ms a house, compiled {1000 * t_new / n:.1f} ms")
    for k in ("hz_deg", "far"):
        d = np.abs(o1[k] - o2[k]); print(f"  per ray {k:8s} max diff {d.max():.4f}, share of rays differing {np.mean(d > 1e-3):.5f}")
    for k in ("hz_cls", "water", "tidal", "hills", "near_bld"):
        print(f"  per ray {k:8s} share of rays agreeing {np.mean(o1[k] == o2[k]):.5f}")
    for k in m1:
        print(f"  measure {k:16s} max diff {np.nanmax(np.abs(m1[k] - m2[k])):.4f}")
    print(f"  drawing angle codes agree {np.mean(a1 == b2['a']):.5f}, classes {np.mean(c1 == b2['c']):.5f}, water {np.mean(w1 == b2['w']):.5f}")

    for name, le, ln, lz in lmk:
        brg = np.degrees(np.arctan2(le - h.e.to_numpy(), ln - h.n.to_numpy())) % 360
        uf = np.abs(((brg - front + 180) % 360) - 180) < 90
        pe, pn, pz = np.where(uf, fe, be), np.where(uf, fn, bn), np.where(uf, zf, zb)
        s1 = V.sees(CV.CITY, pe, pn, pz, le, ln, lz, start=2.0) & V.near_clear(sl, o1["bearing"], pe, pn, pz, le, ln, lz, reach=150.0)
        t = time.time()
        s2 = F.sightlines(CV.CITY, pe, pn, pz, np.full(len(pe), le), np.full(len(pe), ln), np.full(len(pe), lz))
        print(f"  sees {name:24s} agree {np.mean(s1 == s2):.4f}  ({s1.mean():.3f} vs {s2.mean():.3f} in sight)  {1e6 * (time.time() - t) / n:.0f} us a house")

    g = np.nonzero(h.has_garden.to_numpy())[0]
    ge, gn, gz = h.g_e.to_numpy()[g], h.g_n.to_numpy()[g], h.g_z.to_numpy()[g] + 1.6
    t = time.time(); og, _ = V.cast(CV.CITY, ge, gn, gz, False); t_old = time.time() - t
    t = time.time(); og2, _ = F.cast(CV.CITY, ge, gn, gz); t_new = time.time() - t
    s1 = V.sun_hours(og["hz_deg"], og["bearing"], CV.CITY.lat); s2 = V.sun_hours(og2["hz_deg"], og2["bearing"], CV.CITY.lat)
    print(f"\ngarden view: city engine {1000 * t_old / len(g):.1f} ms, compiled {1000 * t_new / len(g):.1f} ms")
    for k in s1:
        print(f"  {k:16s} max diff {np.abs(s1[k] - s2[k]).max():.3f} h")
    t = time.time(); o3, _ = V.cast(CV.CITY, fe, fn, fz + 1.6, False, step_deg=3.0); t_old = time.time() - t
    t = time.time(); b3, hz3 = F.skyline(CV.CITY, fe, fn, fz + 1.6, step_deg=3.0); t_new = time.time() - t
    print(f"\nwindow skyline at 3 degrees: city engine {1000 * t_old / n:.1f} ms, compiled {1000 * t_new / n:.1f} ms; "
          f"max diff {np.abs(o3['hz_deg'] - hz3).max():.4f} deg")
    print(f"top-floor skyline from the 1.5 degree cast, every other ray, max diff from a 3 degree cast: "
          f"{np.abs(V.cast(CV.CITY, fe, fn, zf, False, step_deg=3.0)[0]['hz_deg'] - cf[0]['hz_deg'][:, ::2]).max():.4f} deg")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 300)
