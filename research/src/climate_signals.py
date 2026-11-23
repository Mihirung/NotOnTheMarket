"""Climate at every postcode in England and Wales: sun, cloud, rain, warmth,
frost and wind now, and how fast and which way each is changing.

Sources, all open:

  Met Office HadUK-Grid 1991-2020 averages, from the Met Office Climate Data
  Portal (OGL): monthly mean temperature and rainfall, and the yearly counts
  of air-frost days, icing days, summer days (above 25 C) and days of 10 mm
  of rain or more, on a 2 km grid; monthly mean daily maximum and minimum
  temperature on a 12 km grid.

  UKCP18 regional projections on the 12 km grid, from the same portal (OGL):
  how much each square has already warmed (2001-2020 against 1981-2000), and
  the change in annual, summer-maximum and winter-minimum temperature,
  summer and winter rainfall, hot summer days (above 30 C) and frost days
  once the world is 2 C warmer than before industry (around the 2050s on
  present policies). Medians of the projection ensemble.

  CHELSA V2.1 1981-2010 climatologies (CC BY 4.0; Karger et al. 2017, 2021):
  monthly cloud cover on a 0.025 degree grid, and monthly solar energy
  reaching the ground and wind speed on a 30 arc-second (about 1 km) grid.

  Met Office historic station data (OGL): monthly sunshine hours at the
  long-running stations, used to turn solar energy and cloud into sunshine
  hours (a fit checked station by station, leaving each station out in turn).

The Met Office's research archive (CEDA), which holds HadUK-Grid at 1 km and
its sunshine grids, refuses connections from this machine, hence the portal,
CHELSA and the station calibration.

Writes research/data/signals/climate_postcode.parquet and
research/data/climate/sunshine_fit.json.

Usage: python climate_signals.py [fetch|build|all]
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

D = Path("research/data/climate")
OUT = Path("research/data/signals/climate_postcode.parquet")
PORTAL = "https://services.arcgis.com/Lq3V5RFuTBC9I7kv/arcgis/rest/services"
CHELSA = "/vsicurl/https://os.zhdk.cloud.switch.ch/chelsav2/GLOBAL/climatologies/1981-2010"
STATIONS = "https://www.metoffice.gov.uk/pub/data/weather/uk/climate/stationdata/{}data.txt"
UA = {"User-Agent": "QuietMarketResearch/0.1 (housing research)"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SUMMER, WINTER = [5, 6, 7], [11, 0, 1]                     # Jun-Aug, Dec-Feb (0-based months)
GB = (-6.6, 49.8, 2.0, 55.95)                              # lon/lat window around England and Wales

# (service, layer, fields): None means every field starting with the given prefix
LAYERS = {
    "tas": ("Monthly_Temperature_Observations_1991_2020", 0, [f"tas{m}" for m in MONTHS]),
    "pr": ("Monthly_Precipitation_Observations_1991_2020", 0, [f"pr{m}" for m in MONTHS]),
    "tasmax": ("Monthly_Max_Temperature_Observations_1991_2020", 8, None),
    "tasmin": ("Monthly_Min_Temperature_Observations_1991_2020", 6, None),
    "frost": ("Annual_Count_of_Airfrost_Days_1991_2020", 0, ["airfrostDays"]),
    "icing": ("Annual_Count_of_Icing_Days_1991_2020", 0, None),
    "summer_days": ("Annual_Count_of_Summer_Days_1991_2020", 0, ["SummerDays"]),
    "rain10": ("Annual_Count_of_10mm_Rain_Days_1991_2020", 0, None),
    "p_tas": ("Annual_Average_Temperature_Change___Projections_12km_grid", 334,
              ["tas_annual_change_01_20_median", "tas_annual_change_20_median"]),
    "p_tasmax": ("Summer_Maximum_Temperature_Change___Projections_12km_grid", 336, ["tasmax_summer_change_20_median"]),
    "p_tasmin": ("Winter_Minimum_Temperature_Change___Projections_12km_grid", 337, ["tasmin_winter_change_20_median"]),
    "p_prs": ("Summer_Precipitation_Change___Projections_12km_grid", 339,
              ["pr_summer_change_01_20_median", "pr_summer_change_20_median"]),
    "p_prw": ("Winter_Precipitation_Change___Projections_12km_grid", 340,
              ["pr_winter_change_01_20_median", "pr_winter_change_20_median"]),
    "p_hot": ("Annual_Count_of_Hot_Days___Projections__12km_grid_", 310,
              ["HSD_baseline_01_20_median", "HSD_20_median"]),
    "p_frost": ("Annual_Count_of_Frost_Days_Projections_12km_Grid_070223", 93,
                ["FrostDays_baseline_01_20_median", "FrostDays_20_median"]),
}
STATION_NAMES = ["aberporth", "armagh", "ballypatrick", "bradford", "braemar", "camborne", "cambridge", "cardiff",
                 "chivenor", "cwmystwyth", "dunstaffnage", "durham", "eastbourne", "eskdalemuir", "heathrow", "hurn",
                 "lerwick", "leuchars", "lowestoft", "manston", "nairn", "newtonrigg", "oxford", "paisley", "ringway",
                 "rossonwye", "shawbury", "sheffield", "southampton", "stornoway", "suttonbonington", "tiree",
                 "valley", "waddington", "whitby", "wickairport", "yeovilton"]


def get(url, tries=5):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except Exception as e:                                  # noqa: BLE001
            if k == tries - 1:
                raise
            print(f"  retry {k + 1}: {e!r}", flush=True); time.sleep(5 * 2 ** k)


# ---------------------------------------------------------------- fetch
def fetch_layer(key):
    out = D / f"{key}.parquet"
    if out.exists():
        return pd.read_parquet(out)
    service, layer, fields = LAYERS[key]
    base = f"{PORTAL}/{service}/FeatureServer/{layer}"
    meta = json.loads(get(base + "?f=json"))
    names = [f["name"] for f in meta["fields"]]
    if fields is None:
        fields = [n for n in names if n not in ("OBJECTID", "Shape__Area", "Shape__Length", "Latitude", "Longitude",
                                                "Projection_x_coordinate", "Projection_y_coordinate")]
    rows, off = [], 0
    while True:
        q = {"where": "1=1", "outFields": ",".join(["OBJECTID"] + fields), "returnGeometry": "false",
             "returnCentroid": "true", "outSR": "27700", "orderByFields": "OBJECTID", "resultOffset": off,
             "resultRecordCount": 2000, "f": "json"}
        d = json.loads(get(base + "/query?" + urllib.parse.urlencode(q)))
        feats = d.get("features", [])
        rows += [{"x": f["centroid"]["x"], "y": f["centroid"]["y"], **f["attributes"]} for f in feats]
        off += len(feats)
        if not feats or not d.get("exceededTransferLimit"):
            break
        time.sleep(0.5)
    t = pd.DataFrame(rows).drop(columns="OBJECTID")
    t.to_parquet(out, index=False)
    print(f"  {key}: {len(t):,} squares, {len(fields)} fields", flush=True)
    return t


def fetch_chelsa():
    import rasterio
    from rasterio.windows import from_bounds
    out = D / "chelsa_gb.npz"
    if out.exists():
        return dict(np.load(out))
    res = {}
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="5"):
        for var, name in (("clt", "CHELSA_clt_{m:02d}_1981-2010_V.2.1.tif"), ("rsds", "CHELSA_rsds_1981-2010_{m:02d}_V.2.1.tif"),
                          ("sfcWind", "CHELSA_sfcWind_{m:02d}_1981-2010_V.2.1.tif")):
            stack = []
            for m in range(1, 13):
                with rasterio.open(f"{CHELSA}/{var}/{name.format(m=m)}") as r:
                    w = from_bounds(*GB, r.transform).round_offsets().round_lengths()
                    a = r.read(1, window=w).astype("float32")
                    a[a == r.nodata] = np.nan
                    stack.append(a * r.scales[0] + r.offsets[0])
                    tr = r.window_transform(w)
            res[var] = np.stack(stack)
            res[var + "_transform"] = np.array(tr)[:6]
            print(f"  CHELSA {var}: {res[var].shape}", flush=True)
    np.savez_compressed(out, **res)
    return res


def fetch_stations():
    out = D / "stations.parquet"
    if out.exists():
        return pd.read_parquet(out)
    rows = []
    for s in STATION_NAMES:
        txt = get(STATIONS.format(s)).decode("latin-1")
        m = re.search(r"Lat\s*([-\d.]+)\s*Lon\s*([-\d.]+)", txt)
        if not m:
            print(f"  {s}: no position, skipped", flush=True); continue
        lat, lon = float(m.group(1)), float(m.group(2))
        for line in txt.splitlines():
            p = line.split()
            if len(p) >= 7 and re.fullmatch(r"\d{4}", p[0]) and re.fullmatch(r"\d{1,2}", p[1]):
                sun = re.sub(r"[*#$]", "", p[6])
                if re.fullmatch(r"[\d.]+", sun):
                    rows.append((s, lat, lon, int(p[0]), int(p[1]), float(sun)))
        time.sleep(0.5)
    t = pd.DataFrame(rows, columns=["station", "lat", "lon", "year", "month", "sun"])
    t.to_parquet(out, index=False)
    print(f"  stations: {t.station.nunique()} with sunshine records", flush=True)
    return t


# ---------------------------------------------------------------- sunshine from solar energy and cloud
def daylight(lat, month):
    """Possible daylight hours (FAO-56) and top-of-atmosphere radiation, MJ/m2/day, mid-month."""
    J = np.array([17, 47, 75, 105, 135, 162, 198, 228, 258, 288, 318, 344])[month]
    phi = np.radians(lat)
    dr = 1 + 0.033 * np.cos(2 * np.pi * J / 365)
    dec = 0.409 * np.sin(2 * np.pi * J / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(dec), -1, 1))
    ra = 24 * 60 / np.pi * 0.0820 * dr * (ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws))
    return 24 / np.pi * ws, ra


DAYS = np.array([31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
# Fitted on stations south of 56 N only: with the far north of Scotland in, the fit bends to its long summer days
# and northern cloud, and stations in England and Wales left out in turn are missed by 5.3% a year on average
# rather than 4.1% (research/outputs/climate/sunshine_fit.json).
LAT_MAX = 56.0


class Grid:
    """Nearest valid value of a CHELSA stack at any lon/lat."""

    def __init__(self, arr, transform):
        from scipy.spatial import cKDTree
        a, b, c, d, e, f = transform
        self.arr = arr
        ok = np.isfinite(arr).all(0)
        r, k = np.nonzero(ok)
        self.r, self.k = r, k
        self.tree = cKDTree(np.column_stack([c + (k + 0.5) * a, f + (r + 0.5) * e]) * [np.cos(np.radians(52.5)), 1])

    def at(self, lon, lat):
        _, i = self.tree.query(np.column_stack([np.asarray(lon) * np.cos(np.radians(52.5)), lat]))
        return self.arr[:, self.r[i], self.k[i]].T                      # (points, 12)


def fit_sunshine(st, ch):
    """Monthly sunshine fraction from the clearness of the sky (solar energy at the ground over the
    energy at the top of the atmosphere) and cloud cover, fitted on 1991-2020 station months."""
    norm = st[(st.year >= 1991) & (st.year <= 2020)].groupby(["station", "lat", "lon", "month"]).sun.mean().reset_index()
    norm = norm[norm.lat < LAT_MAX]                              # stations at England and Wales latitudes
    pos = norm.drop_duplicates("station")[["station", "lat", "lon"]].reset_index(drop=True)
    rs = Grid(ch["rsds"], ch["rsds_transform"]).at(pos.lon, pos.lat)
    cl = Grid(ch["clt"], ch["clt_transform"]).at(pos.lon, pos.lat)
    X, y, g, tgt = [], [], [], []
    for i, p in pos.iterrows():
        for m in range(12):
            r = norm[(norm.station == p.station) & (norm.month == m + 1)]
            if not len(r):
                continue
            N, ra = daylight(p.lat, m)
            X.append([1.0, rs[i, m] / ra, cl[i, m] / 100]); y.append(r.sun.iloc[0] / (N * DAYS[m])); g.append(i)
            tgt.append((p.station, m, N * DAYS[m], r.sun.iloc[0]))
    X, y, g = np.array(X), np.array(y), np.array(g)
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    err = []                                                     # each station left out in turn: its yearly total
    for i in np.unique(g):
        b = np.linalg.lstsq(X[g != i], y[g != i], rcond=None)[0]
        pred = sum(np.clip(X[j] @ b, 0, 1) * tgt[j][2] for j in np.nonzero(g == i)[0])
        obs = sum(tgt[j][3] for j in np.nonzero(g == i)[0])
        if (g == i).sum() == 12:
            err.append((pos.station[i], round(obs), round(pred)))
    e = np.array([p - o for _, o, p in err])
    rep = {"coefficients": [round(float(v), 4) for v in beta], "stations": len(err),
           "annual_mean_abs_error_hours": round(float(np.abs(e).mean()), 1),
           "annual_mean_abs_error_share": round(float(np.mean(np.abs(e) / np.array([o for _, o, _ in err]))), 4),
           "by_station": err}
    json.dump(rep, open(D / "sunshine_fit.json", "w"), indent=1)
    Path("research/outputs/climate").mkdir(parents=True, exist_ok=True)
    json.dump(rep, open("research/outputs/climate/sunshine_fit.json", "w"), indent=1)
    print(f"  sunshine: fitted on {len(err)} stations; left-out yearly error {rep['annual_mean_abs_error_hours']} hours "
          f"({100 * rep['annual_mean_abs_error_share']:.1f}%)", flush=True)
    return beta


# ---------------------------------------------------------------- per postcode
def nearest(t, px, py, cols):
    from scipy.spatial import cKDTree
    t = t.dropna(subset=cols, how="all")
    _, i = cKDTree(t[["x", "y"]].to_numpy()).query(np.column_stack([px, py]))
    return t[cols].to_numpy()[i]


def build():
    from pyproj import Transformer
    g = pd.read_parquet("research/data/geo_postcode.parquet", columns=["postcode", "lon", "lat"]).dropna()
    px, py = Transformer.from_crs(4326, 27700, always_xy=True).transform(g.lon.to_numpy(), g.lat.to_numpy())
    o = pd.DataFrame({"postcode": g.postcode.to_numpy()})
    L = {k: fetch_layer(k) for k in LAYERS}

    tas = nearest(L["tas"], px, py, [f"tas{m}" for m in MONTHS])
    pr = nearest(L["pr"], px, py, [f"pr{m}" for m in MONTHS])
    mx_cols = [c for c in L["tasmax"].columns if c not in ("x", "y")]
    mn_cols = [c for c in L["tasmin"].columns if c not in ("x", "y")]
    mx = nearest(L["tasmax"], px, py, mx_cols); mn = nearest(L["tasmin"], px, py, mn_cols)
    o["temp_year"] = tas.mean(1)
    o["temp_summer"] = tas[:, SUMMER].mean(1)
    o["temp_winter"] = tas[:, WINTER].mean(1)
    o["temp_range"] = tas.max(1) - tas.min(1)                    # how continental: warmest month less coldest
    o["warmest_days"] = mx[:, [i for i, c in enumerate(mx_cols) if any(m in c for m in ("Jun", "Jul", "Aug"))]].mean(1)
    o["coldest_nights"] = mn[:, [i for i, c in enumerate(mn_cols) if any(m in c for m in ("Dec", "Jan", "Feb"))]].mean(1)
    o["rain_year"] = pr.sum(1)
    o["rain_summer"] = pr[:, SUMMER].sum(1)
    o["rain_winter"] = pr[:, WINTER].sum(1)
    o["heavy_rain_days"] = nearest(L["rain10"], px, py, [c for c in L["rain10"].columns if c not in ("x", "y")])[:, 0]
    o["frost_days"] = nearest(L["frost"], px, py, ["airfrostDays"])[:, 0]
    o["icing_days"] = nearest(L["icing"], px, py, [c for c in L["icing"].columns if c not in ("x", "y")])[:, 0]
    o["summer_days"] = nearest(L["summer_days"], px, py, ["SummerDays"])[:, 0]

    ch = fetch_chelsa()
    beta = fit_sunshine(fetch_stations(), ch)
    lon, lat = g.lon.to_numpy(), g.lat.to_numpy()
    cl = Grid(ch["clt"], ch["clt_transform"]).at(lon, lat)
    rs = Grid(ch["rsds"], ch["rsds_transform"]).at(lon, lat)
    wd = Grid(ch["sfcWind"], ch["sfcWind_transform"]).at(lon, lat)
    sun = np.zeros_like(rs)
    for m in range(12):
        N, ra = daylight(lat, m)
        sun[:, m] = np.clip(beta[0] + beta[1] * rs[:, m] / ra + beta[2] * cl[:, m] / 100, 0, 1) * N * DAYS[m]
    o["sun_hours_year"] = sun.sum(1)
    o["sun_hours_summer"] = sun[:, SUMMER].sum(1)
    o["sun_hours_winter"] = sun[:, WINTER].sum(1)
    o["cloud_year"] = cl.mean(1)
    o["cloud_winter"] = cl[:, WINTER].mean(1)
    o["solar_year"] = rs.mean(1) * 365.25                        # MJ per square metre per year
    o["wind"] = wd.mean(1)

    P = lambda k, c: nearest(L[k], px, py, [c])[:, 0]           # noqa: E731
    o["warming_so_far"] = P("p_tas", "tas_annual_change_01_20_median")
    o["warming_2c"] = P("p_tas", "tas_annual_change_20_median")
    o["summer_heat_2c"] = P("p_tasmax", "tasmax_summer_change_20_median")
    o["winter_nights_2c"] = P("p_tasmin", "tasmin_winter_change_20_median")
    o["summer_rain_so_far"] = P("p_prs", "pr_summer_change_01_20_median")
    o["summer_rain_2c"] = P("p_prs", "pr_summer_change_20_median")
    o["winter_rain_so_far"] = P("p_prw", "pr_winter_change_01_20_median")
    o["winter_rain_2c"] = P("p_prw", "pr_winter_change_20_median")
    hot0, hot2 = P("p_hot", "HSD_baseline_01_20_median"), P("p_hot", "HSD_20_median")
    o["hot_days_now"], o["hot_days_2c"] = hot0, hot2
    o["frost_days_lost_2c"] = P("p_frost", "FrostDays_baseline_01_20_median") - P("p_frost", "FrostDays_20_median")
    num = o.columns.drop("postcode")
    o[num] = o[num].astype("float32")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    o.to_parquet(OUT, index=False)
    q = o[num].quantile([0.05, 0.5, 0.95]).T.round(2)
    print(q.to_string(), flush=True)
    print(f"wrote {OUT}: {len(o):,} postcodes, {len(num)} columns", flush=True)


if __name__ == "__main__":
    D.mkdir(parents=True, exist_ok=True)
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("fetch", "all"):
        for k in LAYERS:
            fetch_layer(k)
        fetch_chelsa(); fetch_stations()
    if what in ("build", "all"):
        build()
