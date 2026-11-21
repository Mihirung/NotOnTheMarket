"""OS OpenMap Local for every 100 km square with homes in England and Wales,
cut into the 10 km cells the national view run works in.

For each square: download the ESRI Shapefile release from the OS Data Hub
(open data, OGL), read the seven layers the view engine uses, and write
each layer's features to every 10 km cell they reach, including a margin
of MARGIN metres around the cell. The zip and shapefiles are then
deleted, so the disk holds only what the run reads.

Usage: python osmap_national.py <positions.npz> <out_dir> [workers]
"""
import shutil
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

LAYERS = ["Building", "ImportantBuilding", "Road", "SurfaceWater_Area", "TidalWater", "Foreshore", "Woodland"]
CELL, MARGIN = 10_000, 1_100
URL = "https://api.os.uk/downloads/v1/products/OpenMapLocal/downloads?area={sq}&format=ESRI%C2%AE+Shapefile&redirect"


def _grid_letters(e, n):
    """OS 100 km square letters for an easting and northing in metres."""
    letters = "ABCDEFGHJKLMNOPQRSTUVWXYZ"
    e100, n100 = int(e // 100_000), int(n // 100_000)
    l1 = (19 - n100) - (19 - n100) % 5 + (e100 + 10) // 5
    l2 = (19 - n100) * 5 % 25 + e100 % 5
    return letters[l1] + letters[l2]


def cell_id(e, n):
    return f"{int(e // CELL)}_{int(n // CELL)}"


def fetch_square(sq, tmp):
    z = tmp / f"opmplc_{sq.lower()}.zip"
    for attempt in range(5):
        r = subprocess.run(["curl", "-sS", "-L", "--max-time", "1800", "-o", str(z), URL.format(sq=sq)], capture_output=True)
        try:
            with zipfile.ZipFile(z) as zf:
                names = [m for m in zf.namelist() if any(m.endswith(f"{sq}_{L}{ext}") for L in LAYERS
                                                       for ext in (".shp", ".shx", ".dbf", ".prj"))]
                zf.extractall(tmp / sq, members=names)
            z.unlink()
            return tmp / sq
        except Exception:
            continue
    raise RuntimeError(f"could not download {sq}: {r.stderr[-300:]}")


def split_square(sq, folder, out, cells):
    n_written = 0
    for L in LAYERS:
        shp = list(folder.rglob(f"{sq}_{L}.shp"))
        if not shp:
            continue
        g = gpd.read_file(shp[0], engine="pyogrio", use_arrow=True)
        keep = [c for c in ("CLASSIFICA", "FEATCODE", "DISTNAME", "ROADNUMBER") if c in g.columns]
        g = g[keep + ["geometry"]]
        if not len(g):
            continue
        b = g.geometry.bounds.to_numpy()
        c0 = np.floor((b[:, 0] - MARGIN) / CELL).astype(int); c1 = np.floor((b[:, 2] + MARGIN) / CELL).astype(int)
        r0 = np.floor((b[:, 1] - MARGIN) / CELL).astype(int); r1 = np.floor((b[:, 3] + MARGIN) / CELL).astype(int)
        span = (c1 - c0 + 1) * (r1 - r0 + 1)
        idx = np.repeat(np.arange(len(g)), span)
        off = np.arange(span.sum()) - np.repeat(np.cumsum(span) - span, span)
        w = np.repeat(c1 - c0 + 1, span)
        cc, rr = np.repeat(c0, span) + off % w, np.repeat(r0, span) + off // w
        key = cc.astype(np.int64) * 1000 + rr
        ok = np.isin(key, cells)
        idx, key = idx[ok], key[ok]
        order = np.argsort(key, kind="stable"); idx, key = idx[order], key[order]
        starts = np.r_[0, np.nonzero(np.diff(key))[0] + 1, len(key)]
        for a, z in zip(starts[:-1], starts[1:]):
            k = int(key[a]); d = out / f"{k // 1000}_{k % 1000}"; d.mkdir(parents=True, exist_ok=True)
            g.iloc[idx[a:z]].to_parquet(d / f"{L}_{sq}.parquet", index=False, compression="zstd")
            n_written += 1
    return n_written


def main(pos_path, out_dir, workers=4):
    P = np.load(pos_path)
    x, y = P["x"], P["y"]
    cells = np.unique((x // CELL).astype(np.int64) * 1000 + y // CELL)
    # every square that holds a cell or the margin of one
    ce, cn = cells // 1000 * CELL, cells % 1000 * CELL
    sqs = sorted({_grid_letters(e, n) for e0, n0 in zip(ce, cn)
                  for e in (e0 - MARGIN, e0 + CELL + MARGIN - 1) for n in (n0 - MARGIN, n0 + CELL + MARGIN - 1)})
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    tmp = out.parent / "osmap_tmp"; tmp.mkdir(exist_ok=True)
    done_f = out.parent / "osmap_done.txt"
    done = set(done_f.read_text().split()) if done_f.exists() else set()
    todo = [s for s in sqs if s not in done]
    print(f"{len(cells)} cells, {len(sqs)} squares, {len(todo)} to do: {' '.join(todo)}", flush=True)

    def one(sq):
        try:
            folder = fetch_square(sq, tmp)
        except RuntimeError as e:
            return sq, str(e)
        n = split_square(sq, folder, out, cells)
        shutil.rmtree(folder, ignore_errors=True)
        with open(done_f, "a") as f:
            f.write(sq + "\n")
        return sq, f"{n} cell files"
    with ThreadPoolExecutor(int(workers)) as ex:
        for sq, msg in ex.map(one, todo):
            print(sq, msg, flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
