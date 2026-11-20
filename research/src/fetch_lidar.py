"""Fetch Environment Agency 1 m LIDAR composite tiles over a study area
via the Defra Data Services Platform WCS, as 2 km GeoTIFF tiles.

Both the last-return DSM (buildings and trees) and the DTM (bare ground)
are OGL open data. Requests are retried with backoff: the service is
reliable but returns the odd transient 500.

Usage: python fetch_lidar.py <dsm|dtm> <out_dir> <E0> <E1> <N0> <N1> [workers]
"""

import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import rasterio

BASE = "https://environment.data.gov.uk/spatialdata/{slug}/wcs?service=WCS&version=2.0.1&request=GetCoverage&coverageId={cid}&format=image/tiff&subset=E({e0},{e1})&subset=N({n0},{n1})"
LAYERS = {
    "dsm": ("lidar-composite-digital-surface-model-last-return-dsm-1m",
            "9ba4d5ac-d596-445a-9056-dae3ddec0178__Lidar_Composite_Elevation_LZ_DSM_1m"),
    "dtm": ("lidar-composite-digital-terrain-model-dtm-1m-2022",
            "13787b9a-26a4-4775-8523-806d13af58fc__Lidar_Composite_Elevation_DTM_1m"),
}
TILE = 2000


def valid(path):
    try:
        with rasterio.open(path) as r:
            return r.count == 1 and r.width == TILE and r.height == TILE
    except Exception:
        return False


def fetch(layer, out_dir, e0, n0):
    slug, cid = LAYERS[layer]
    out = out_dir / f"{layer}_{e0}_{n0}.tif"
    if out.exists() and valid(out):
        return f"skip {out.name}"
    url = BASE.format(slug=slug, cid=cid, e0=e0, e1=e0 + TILE, n0=n0, n1=n0 + TILE)
    for attempt in range(5):
        t = time.time()
        subprocess.run(["curl", "-sS", "--max-time", "600", "-o", str(out), url],
                       capture_output=True)
        if valid(out):
            return f"ok   {out.name} {time.time()-t:.0f}s"
        time.sleep(5 * (attempt + 1))
    return f"FAIL {out.name}"


def main(layer, out_dir, E0, E1, N0, N1, workers=3):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    jobs = [(e, n) for e in range(E0, E1, TILE) for n in range(N0, N1, TILE)]
    print(f"{layer}: {len(jobs)} tiles, {workers} workers", flush=True)
    with ThreadPoolExecutor(workers) as ex:
        for msg in ex.map(lambda j: fetch(layer, out_dir, *j), jobs):
            print(msg, flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], *map(int, sys.argv[3:7]),
         int(sys.argv[7]) if len(sys.argv) > 7 else 3)
