"""1 metre laser-survey tiles for anywhere in England and Wales.

England: the Environment Agency's LIDAR composite (surface and ground
models), 2 km tiles requested from its WCS service.
Wales: Natural Resources Wales / Welsh Government 2020-23 national survey,
1 km tiles from DataMapWales cloud storage.

Tiles are stored losslessly at whole centimetres (int32, zstd), a quarter
of their download size, and assembled into any window on request. Where
neither survey has data the window holds NaN, which the caller fills
from the 30 m terrain model.

Usage (fetch everything a list of windows needs):
  python tiles.py wales-catalogue <wfs.json> <out.parquet>
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

ROOT = Path("research/data/tiles")
EA_TILE, WA_TILE = 2000, 1000
NODATA = -2147483648
EA = {"dsm": ("lidar-composite-digital-surface-model-last-return-dsm-1m",
              "9ba4d5ac-d596-445a-9056-dae3ddec0178__Lidar_Composite_Elevation_LZ_DSM_1m"),
      "dtm": ("lidar-composite-digital-terrain-model-dtm-1m-2022",
              "13787b9a-26a4-4775-8523-806d13af58fc__Lidar_Composite_Elevation_DTM_1m")}
EA_URL = ("https://environment.data.gov.uk/spatialdata/{slug}/wcs?service=WCS&version=2.0.1&request=GetCoverage"
          "&coverageId={cid}&format=image/tiff&geotiff:compression=LZW&subset=E({e0},{e1})&subset=N({n0},{n1})")
WA_BASE = "https://"
LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"
_WALES = None


def grid_ref_to_en(ref):
    """'SH2281' -> (222000, 381000): south-west corner of a 1 km square."""
    a, b = LETTERS.index(ref[0]), LETTERS.index(ref[1])
    e100 = (a % 5) * 5 + (b % 5) - 10
    n100 = 19 - (a // 5) * 5 - (b // 5)
    k = (len(ref) - 2) // 2
    e = int(ref[2:2 + k]) * 10 ** (5 - k); n = int(ref[2 + k:]) * 10 ** (5 - k)
    return e100 * 100_000 + e, n100 * 100_000 + n


def wales_catalogue():
    global _WALES
    if _WALES is None:
        p = Path("research/data/wales_lidar_tiles.parquet")
        _WALES = pd.read_parquet(p).set_index(["e0", "n0"]) if p.exists() else pd.DataFrame()
    return _WALES


def _store(arr, path, e0, n1):
    """Write metres as whole centimetres, losslessly compressed."""
    a = np.where(np.isfinite(arr) & (arr > -1000), np.round(arr * 100), NODATA).astype(np.int32)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.part"     # several threads may store the same tile
    with rasterio.open(tmp, "w", driver="GTiff", width=a.shape[1], height=a.shape[0], count=1, dtype="int32",
                       crs="EPSG:27700", transform=from_origin(e0, n1, 1.0, 1.0), nodata=NODATA,
                       compress="zstd", zstd_level=1, predictor=2, tiled=True, blockxsize=512, blockysize=512) as w:
        w.write(a, 1)
    os.replace(tmp, path)


class Refused(Exception):
    """The service answered and said no (outside its coverage): not worth retrying."""


def _download(url, timeout=300):
    fd, tmp = tempfile.mkstemp(suffix=".tif", dir=ROOT / "tmp"); os.close(fd)
    try:
        try:                                          # curl's own limit, and a hard one in case it hangs on exit
            r = subprocess.run(["curl", "-sS", "--max-time", str(timeout), "-o", tmp, "-w", "%{http_code}", url],
                               capture_output=True, text=True, timeout=timeout + 60)
        except subprocess.TimeoutExpired:
            return None
        code = r.stdout.strip()
        if r.returncode == 0 and code in ("400", "404"):     # outside the service's extent; busy (429) or blocked is retried
            raise Refused(code)
        if r.returncode != 0 or not code.startswith("2"):
            return None
        with rasterio.open(tmp) as src:
            return src.read(1).astype(np.float32), src.transform, src.nodata
    except Refused:
        raise
    except Exception:
        return None
    finally:
        os.unlink(tmp)


def ea_path(kind, e0, n0):
    return ROOT / f"ea_{kind}" / f"{e0}_{n0}.tif"


def wa_path(kind, e0, n0):
    return ROOT / f"wa_{kind}" / f"{e0}_{n0}.tif"


class Unavailable(Exception):
    """The service did not answer properly after every retry. Nothing is marked
    as missing: the caller tries the whole window again later."""


def _backoff(attempt):
    import time
    time.sleep(min(60, 5 * 2 ** attempt))


def fetch_ea(kind, e0, n0, tries=7):
    """One 2 km England tile. Writes the tile, or an empty marker when the
    service says it has nothing there. A tile is only ever marked missing on
    a definite answer (outside the service's extent); a busy, failing or
    silent service raises Unavailable instead, so a short outage can never
    pass for a gap in the survey."""
    p = ea_path(kind, e0, n0)
    if p.exists() or p.with_suffix(".none").exists():
        return "skip"
    slug, cid = EA[kind]
    url = EA_URL.format(slug=slug, cid=cid, e0=e0, e1=e0 + EA_TILE, n0=n0, n1=n0 + EA_TILE)
    for attempt in range(tries):
        try:
            got = _download(url)
        except Refused:
            p.with_suffix(".none").touch()
            return "none"
        if got is not None:
            a, tr, nd = got
            if a.shape == (EA_TILE, EA_TILE):
                if nd is not None:
                    a[a == nd] = np.nan
                _store(a, p, e0, n0 + EA_TILE)
                return "ok"
        _backoff(attempt)
    raise Unavailable(f"England {kind} tile {e0},{n0}")


def fetch_wa(kind, e0, n0, tries=7):
    p = wa_path(kind, e0, n0)
    cat = wales_catalogue()
    if p.exists() or p.with_suffix(".none").exists() or (e0, n0) not in cat.index:
        return "skip"
    url = WA_BASE + cat.loc[(e0, n0), f"{kind}_link"]
    for attempt in range(tries):
        try:
            got = _download(url)
        except Refused:                               # listed in the catalogue but not there
            p.with_suffix(".none").touch()
            return "none"
        if got is not None:
            a, tr, nd = got
            if nd is not None:
                a[a == nd] = np.nan
            full = np.full((WA_TILE, WA_TILE), np.nan, np.float32)     # place by its own transform
            r0 = int(round((n0 + WA_TILE - tr.f))); c0 = int(round((tr.c - e0)))
            h, w = min(a.shape[0], WA_TILE - r0), min(a.shape[1], WA_TILE - c0)
            if h > 0 and w > 0:
                full[r0:r0 + h, c0:c0 + w] = a[:h, :w]
            _store(full, p, e0, n0 + WA_TILE)
            return "ok"
        _backoff(attempt)
    raise Unavailable(f"Wales {kind} tile {e0},{n0}")


def tiles_for(E0, N0, E1, N1):
    """Every England and Wales tile a window [E0,E1) x [N0,N1) touches."""
    cat = wales_catalogue()
    ea = [(e, n) for e in range(E0 // EA_TILE * EA_TILE, E1, EA_TILE) for n in range(N0 // EA_TILE * EA_TILE, N1, EA_TILE)
          if not (len(cat) and all((e + a, n + b) in cat.index for a in (0, WA_TILE) for b in (0, WA_TILE)))]
    wa = [(e, n) for e in range(E0 // WA_TILE * WA_TILE, E1, WA_TILE) for n in range(N0 // WA_TILE * WA_TILE, N1, WA_TILE)
          if len(cat) and (e, n) in cat.index]
    return ea, wa


def fetch_window(E0, N0, E1, N1, kinds=("dsm", "dtm"), workers=None, ea_workers=12, wa_workers=48):
    """Fetch every tile a window needs. England's service is asked a dozen
    tiles at a time (more makes it fail); Wales's cloud storage takes more.
    Raises Unavailable if any tile could not be fetched or definitely ruled out."""
    for d in ["tmp"] + [f"{s}_{k}" for s in ("ea", "wa") for k in kinds]:
        (ROOT / d).mkdir(parents=True, exist_ok=True)
    if workers is not None:
        ea_workers = wa_workers = workers
    ea, wa = tiles_for(E0, N0, E1, N1)
    out = []
    for fn, tiles, w in ((fetch_ea, ea, ea_workers), (fetch_wa, wa, wa_workers)):
        jobs = [(k, e, n) for k in kinds for e, n in tiles]
        if jobs:
            with ThreadPoolExecutor(max(1, min(w, len(jobs)))) as ex:
                out += list(ex.map(lambda j: fn(*j), jobs))
    return out


def _paste(out, path, e0, n0, size, E0, N1):
    if not path.exists():
        return 0
    with rasterio.open(path) as src:
        a = src.read(1)
    H, W = out.shape
    r0 = N1 - (n0 + size); c0 = e0 - E0
    rs, cs = max(r0, 0), max(c0, 0); re, ce = min(r0 + size, H), min(c0 + size, W)
    if rs >= re or cs >= ce:
        return 0
    blk = a[rs - r0:re - r0, cs - c0:ce - c0]
    ok = blk != NODATA
    view = out[rs:re, cs:ce]
    view[ok] = blk[ok].astype(np.float32) / 100.0
    return int(ok.sum())


def window(kind, E0, N0, E1, N1):
    """Heights in metres over [E0,E1) x [N0,N1), north up, 1 m cells; NaN where
    neither survey has data. Wales overrides England where it has data:
    the England composite holds zeros, not gaps, over Wales."""
    out = np.full((N1 - N0, E1 - E0), np.nan, np.float32)
    ea, wa = tiles_for(E0, N0, E1, N1)
    for e, n in ea:
        _paste(out, ea_path(kind, e, n), e, n, EA_TILE, E0, N1)
    for e, n in wa:
        _paste(out, wa_path(kind, e, n), e, n, WA_TILE, E0, N1)
    return out


def release(keep):
    """Delete stored tiles not in `keep` (a set of (prefix, kind, e0, n0))."""
    n = 0
    for d in ROOT.glob("*_d?m"):
        prefix, kind = d.name.split("_")
        for p in d.glob("*.*"):
            e0, n0 = map(int, p.stem.split("_"))
            if (prefix, kind, e0, n0) not in keep:
                p.unlink(missing_ok=True); n += 1
    return n


def point_max(e, n, r=30):
    """Highest surface point within r metres of (e, n): the top of a tower or
    spire, as views2.landmark_top() takes it, from the same stored tiles the
    run uses. None where neither survey has data."""
    e, n = int(round(e)), int(round(n))
    E0, N0, E1, N1 = e - r, n - r, e + r + 1, n + r + 1
    fetch_window(E0, N0, E1, N1, kinds=("dsm",), workers=1)
    a = window("dsm", E0, N0, E1, N1)
    a = a[np.isfinite(a)]
    return float(a.max()) if a.size and a.max() != 0 else None


def stored_bytes():
    n = 0
    for p in ROOT.rglob("*.tif"):
        try:
            n += p.stat().st_size
        except FileNotFoundError:                     # deleted by the run while we counted
            pass
    return n


def build_wales_catalogue(wfs_json, out):
    d = json.load(open(wfs_json))
    rows = []
    for f in d["features"]:
        p = f["properties"]
        if p.get("british_gr"):
            e0, n0 = grid_ref_to_en(p["british_gr"])
        else:                                         # the file name carries the square: ..._288169_... = E288 km, N169 km
            k = p["dsm_link"].split("/")[-1].split("_")[3]
            e0, n0 = int(k[:3]) * 1000, int(k[3:]) * 1000
        rows.append({"e0": e0, "n0": n0, "ref": p["british_gr"], "year": p.get("year"),
                     "dsm_link": p["dsm_link"], "dtm_link": p["dtm_link"]})
    t = pd.DataFrame(rows).sort_values("year").drop_duplicates(["e0", "n0"], keep="last")
    t.to_parquet(out, index=False)
    print(f"{len(t):,} Wales tiles")


if __name__ == "__main__":
    if sys.argv[1] == "wales-catalogue":
        build_wales_catalogue(sys.argv[2], sys.argv[3])
