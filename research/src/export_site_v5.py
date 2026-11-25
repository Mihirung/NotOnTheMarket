"""Prototype data, version 5: every postcode area in England and Wales.

Version 4 searched two cities. This one searches any of the postcode areas
of England and Wales, with the same measures drawn the same way, taken from
the national house-level run (docs/08). Each area is a file the page loads
when it is chosen. The page itself carries an index of the areas and a
table of every postcode sector, so a brief can be matched against the whole
country before choosing where to look.

Stages:
  score   <transactions> <model.txt> <lab_deploy.json> <cache_dir>
          score every currently owned home in England and Wales for a sale
          in the next 12 months with the deployed model
  live    <model.txt> <lab_deploy.json> <cache_dir> [second.json] [live_dir]
          the same on the up-to-date sale records (live_sales.py): scored on
          the first of the month after they end, with notices read to today
  houses  <national_dir> <cache_dir>
          one pass over the national cells: the houses and sight-lines of
          each postcode area, one file per area
  export  <cache_dir> <geo.parquet> <national_dir> <lab_dir> <out_dir> [areas...]
          one JSON file per area, and the page's own data (the area index,
          the national sector table, the area shown first)

Privacy, as before: no address, postcode or coordinate of an individual
home is exported. Drawings are of unnamed houses inside a postcode sector.
"""
import json
import sys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent))
import export_site_v4 as V4  # noqa: E402
from national_house_view import view_dict  # noqa: E402
from national_views import load_panos  # noqa: E402
from views2 import A_LO, A_SPAN, ALPH  # noqa: E402

REGIONS = {
    "London": "E EC N NW SE SW W WC BR CR DA EN HA IG KT RM SM TW UB WD",
    "South East": "BN CT GU HP ME MK OX PO RG RH SL SO TN",
    "East of England": "AL CB CM CO IP LU NR PE SG SS",
    "South West": "BA BH BS DT EX GL PL SN SP TA TQ TR",
    "Midlands": "B CV DE DY HR LE LN NG NN ST TF WR WS WV",
    "North West": "BB BL CA CH CW FY L LA M OL PR SK WA WN",
    "Yorkshire and the North East": "BD DH DL DN HD HG HU HX LS NE S SR TD TS WF YO",
    "Wales": "CF LD LL NP SA SY",
}
REGION_OF = {a: r for r, s in REGIONS.items() for a in s.split()}
TOWN = {
    "AL": "St Albans", "B": "Birmingham", "BA": "Bath", "BB": "Blackburn", "BD": "Bradford", "BH": "Bournemouth",
    "BL": "Bolton", "BN": "Brighton", "BR": "Bromley", "BS": "Bristol", "CA": "Carlisle", "CB": "Cambridge",
    "CF": "Cardiff", "CH": "Chester", "CM": "Chelmsford", "CO": "Colchester", "CR": "Croydon", "CT": "Canterbury",
    "CV": "Coventry", "CW": "Crewe", "DA": "Dartford", "DE": "Derby", "DH": "Durham", "DL": "Darlington",
    "DN": "Doncaster", "DT": "Dorchester", "DY": "Dudley", "E": "East London", "EC": "the City of London",
    "EN": "Enfield", "EX": "Exeter", "FY": "Blackpool", "GL": "Gloucester", "GU": "Guildford", "HA": "Harrow",
    "HD": "Huddersfield", "HG": "Harrogate", "HP": "Hemel Hempstead", "HR": "Hereford", "HU": "Hull",
    "HX": "Halifax", "IG": "Ilford", "IP": "Ipswich", "KT": "Kingston upon Thames", "L": "Liverpool",
    "LA": "Lancaster", "LD": "Llandrindod Wells", "LE": "Leicester", "LL": "Llandudno", "LN": "Lincoln",
    "LS": "Leeds", "LU": "Luton", "M": "Manchester", "ME": "Medway", "MK": "Milton Keynes", "N": "North London",
    "NE": "Newcastle", "NG": "Nottingham", "NN": "Northampton", "NP": "Newport", "NR": "Norwich",
    "NW": "North West London", "OL": "Oldham", "OX": "Oxford", "PE": "Peterborough", "PL": "Plymouth",
    "PO": "Portsmouth", "PR": "Preston", "RG": "Reading", "RH": "Redhill", "RM": "Romford", "S": "Sheffield",
    "SA": "Swansea", "SE": "South East London", "SG": "Stevenage", "SK": "Stockport", "SL": "Slough",
    "SM": "Sutton", "SN": "Swindon", "SO": "Southampton", "SP": "Salisbury", "SR": "Sunderland",
    "SS": "Southend-on-Sea", "ST": "Stoke-on-Trent", "SW": "South West London", "SY": "Shrewsbury",
    "TA": "Taunton", "TD": "Berwick-upon-Tweed", "TF": "Telford", "TN": "Tonbridge", "TQ": "Torquay",
    "TR": "Truro", "TS": "Teesside", "TW": "Twickenham", "UB": "Uxbridge", "W": "West London",
    "WA": "Warrington", "WC": "the West End", "WD": "Watford", "WF": "Wakefield", "WN": "Wigan",
    "WR": "Worcester", "WS": "Walsall", "WV": "Wolverhampton", "YO": "York"}
CENTRAL_LONDON = set("E EC N NW SE SW W WC".split())
CHARING_CROSS = (51.5080, -0.1247)
# The two original cities keep their hand-written place names and copy.
OVERRIDE = {a: dict(centre=c["centre"], centre_name=c["centre_name"], water=c["water"], hills=c["hills"],
                    outcodes=c["areas"]) for a, c in (("EX", V4.CITIES["exeter"]), ("BA", V4.CITIES["bath"]))}
WATER = "A river, lake, canal, estuary or the sea somewhere in the upstairs view."
HILLS = "Hills or high ground on the skyline from the upper windows."
N_LM = 6                                            # landmarks offered as search flags in each area
DEFAULT_AREA = "BA"
HOUSE_COLS = ["x", "y", "postcode", "sector", "n_uprn", "has_garden", "storeys", "e", "n", "eye_up",
              "u_longest_km", "u_best_bearing", "garden_bearing", "u_long", "u_water", "u_hills", "u_horizon",
              "g_horizon", "g_overlooked", "sun_jun", "sun_evening_jun", "sun_equinox", "sun_dec",
              "has_long", "has_water", "has_hills", "has_private", "has_evening", "has_swgarden",
              "light_back", "light_front", "winter_front", "winter_back", "lm_n", "h3"]
# What could be built, and heritage (permitted_development.py, per house)
BUILD = [("extend", "Room to extend without planning permission",
          "A rear extension or a loft the house could add under permitted development, judged from its type, the room "
          "behind it and where it stands. An estimate: earlier extensions use the allowance up.",
          lambda H: (H.pd_rear_m.fillna(0) > 0) | H.pd_loft.fillna(False).astype(bool)),
         ("loftok", "Loft extension allowed without permission",
          "A house, not on a conservation area, protected landscape, National Park or World Heritage Site, and not under "
          "an Article 4 direction for roofs.", lambda H: H.pd_loft.fillna(False).astype(bool)),
         ("historic", "Conservation area or listed",
          "The house stands in a conservation area or is listed (or joined to a listed building).",
          lambda H: H.in_conservation.fillna(False).astype(bool) | H.listed.fillna(False).astype(bool))]
PD_COLS = ["h3", "pd_rear_m", "pd_loft", "in_conservation", "listed", "add_value", "add_m2"]
NATION_FLAGS = [k for k, *_ in V4.GENERIC] + [k for k, *_ in V4.LIGHT] + [k for k, *_ in BUILD]
# cells travel as rows; the page turns them back into objects with these names (outcode is the sector's first part)
CELL_COLS = ["sector", "ptype", "band", "n", "n_top", "exp_sellers", "p_med", "value_med", "offer_med", "premium_med",
             "tenure_med", "nox", "density", "km_gp", "min_centre", "lat", "lon", "vm",
             "km_hosp", "km_park", "km_blue", "km_pub", "add_value",
             "sun_h", "rain_mm", "winter_c", "summer_c", "frosts", "wind", "warm_2c", "hot_2c"]
# climate columns carried by each cell (climate_signals.py), in CELL_COLS order
CLIM = [("sun_hours_year", "sun_h", 0), ("rain_year", "rain_mm", 0), ("coldest_nights", "winter_c", 1),
        ("warmest_days", "summer_c", 1), ("frost_days", "frosts", 0), ("wind", "wind", 1), ("warming_2c", "warm_2c", 2),
        ("hot_days_2c", "hot_2c", 1)]


def area_of(pc):
    return pc.str.extract(r"^([A-Z]+)")[0]


# ---------------------------------------------------------------- stage 1
def live_clock(live_dir, today=None):
    """Where the live site stands. The scoring day is the first of the month after the last month of sales on
    record; panel2.clock() puts it on a 1 January. The notices are read as on the first of next month, so every
    notice published to today counts: `ahead` is how many months after the scoring day that is, and `read` the
    same month as an index (year * 12 + month - 1). `late` is the weight of each part-registered month's sales
    in the panel's counts (live_sales.registered), by month in the panel's clock."""
    import datetime as dt
    import panel2 as P2
    info = json.load(open(Path(live_dir) / "sales.json"))
    y, m = int(info["last_month"][:4]), int(info["last_month"][5:])
    day = dt.date(y + (m == 12), m % 12 + 1, 1)
    today = today or dt.date.today()
    read = today.year * 12 + today.month
    shift, year = P2.clock(day)
    late = {int(k[:4]) * 12 + int(k[5:]) - 1 + shift: round(1 / max(q, 0.2), 3) for k, q in info.get("registered_share", {}).items() if q < 1}
    return {"sales_to": info["last_month"], "sales_read_on": info["read_on"], "scored_on": day.isoformat(),
            "notices_to": today.isoformat(), "shift": shift, "year": year, "read": read,
            "ahead": read - (day.year * 12 + day.month - 1), "late": late}


def live(model_path, deploy_json, cache_dir, second_json=None, live_dir="research/data/live"):
    """score(), on the up-to-date sale records (live_sales.py) and the notices published to today."""
    score(None, model_path, deploy_json, cache_dir, second_json, live_dir=live_dir)


def score(tx_path, model_path, deploy_json, cache_dir, second_json=None, batch=1_000_000, live_dir=None):
    """Every currently owned home in England and Wales, scored in batches.

    With `second_json` the model's prediction is passed through a second step, which adds to its log-odds:
    p_sale is then the second step's figure and p_year keeps the model's own. notice_step.py's
    lab_second_notice.json adds the Gazette notices and keeps the calendar-year meaning; stack_late.py's
    lab_second.json aims at homes not yet on the market (a sale completing between July and June)."""
    import lightgbm as lgb
    import panel2 as P2
    import signals as SG
    cache = Path(cache_dir); cache.mkdir(parents=True, exist_ok=True)
    fams = json.load(open(deploy_json))["families"]
    year, when = V4.SCORE_YEAR, None
    if live_dir:                                      # the scoring day follows the sale records; see live_clock()
        import notice_signals as NS
        when = live_clock(live_dir); year = when["year"]
        P2.set_last_year(year - 1); NS.go_live(live_dir)
        tx_path = str(Path(live_dir) / "transactions.parquet")
        print(f"live: sales to {when['sales_to']}, scored on {when['scored_on']}, notices to {when['notices_to']}", flush=True)
    panel = P2.Panel(tx_path, shift=when["shift"] if when else 0, late=when["late"] if when else None)
    if when:
        panel.ahead = when["ahead"]
    Y0, full_features = P2.Y0, P2.full_features
    bst = lgb.Booster(model_file=model_path)
    assert bst.feature_name() == SG.columns(fams), "model features do not match its families"
    second, row_fams = None, []
    if second_json:
        sj = json.load(open(second_json))
        assert sj["passes"], "the second step did not pass its test"
        if sj.get("parts"):                           # several small steps, each for the homes where its first column is present
            second = [(lgb.Booster(model_file=str(Path(second_json).parent / q["file"])), q["columns"], True) for q in sj["parts"]]
        else:                                         # one step read by every home
            one = Path(second_json).with_name(Path(second_json).name.replace("lab_", "model_")).with_suffix(".txt")
            second = [(lgb.Booster(model_file=str(one)), sj["columns"], False)]
        row_fams = [f for f in SG.ROW_FAMILIES if set(SG.ROW_FAMILIES[f]["columns"]) & set(sj["columns"])]
        known = {"first_step", "tenure"} | {c for f in row_fams for c in SG.ROW_FAMILIES[f]["columns"]}
        assert all(b.feature_name() == cols for b, cols, _ in second) and set(sj["columns"]) <= known, "the second step's columns are not all known"
    lookups = {f: SG.lookup(f, panel.pc_names) for f in fams if f not in SG.TIME_VARYING}
    s_all = np.nonzero(~panel.sold & (panel.ptype >= 0))[0]
    parts = []
    for a in range(0, len(s_all), batch):
        s = s_all[a:a + batch]
        t = np.full(len(s), year, dtype="int32")
        p = bst.predict(full_features(panel, s, t, fams, lookups), num_threads=4)
        p_year = p; flag = np.zeros(len(s), bool)
        if second is not None:                        # the columns as the second step was fitted on them (stored at half precision)
            lp = np.clip(p, 1e-6, 1 - 1e-6); lp = np.log(lp / (1 - lp))
            have = {"first_step": lp, "tenure": (year - panel.year[s]).astype("float64")}
            for f in row_fams:
                R = np.clip(SG.row_features(f, panel, s, t), -6e4, 6e4).astype("float16").astype("float32")
                have.update({c: R[:, i] for i, c in enumerate(SG.ROW_FAMILIES[f]["columns"])})
            raw = np.zeros(len(s))
            for b2, cols, where_present in second:
                Z = np.column_stack([have[c] for c in cols])
                m = np.isfinite(Z[:, 0]) if where_present else np.ones(len(s), bool)
                if m.any():
                    raw[m] += b2.predict(Z[m], num_threads=4, raw_score=True)
            for c in sj["columns"]:                       # a home with a notice: scored, but never shown as an example
                if c.startswith("notice_") and c.endswith("_months"):
                    flag |= np.isfinite(have[c])
            p = 1 / (1 + np.exp(-(lp + raw)))             # the second step adds to the first step's log-odds
        d, byi = panel.oc[s], panel.year[s] - Y0
        est = panel.price[s] * panel.d_med[d, P2.NY - 1] / np.maximum(panel.d_med[d, byi], 1)
        parts.append(pd.DataFrame({
            "pc": panel.pc[s].astype("int32"), "ptype": np.array(list("DSTF"))[panel.ptype[s]],
            "tenure": (year - panel.year[s]).astype("int16"), "price": panel.price[s].astype("int32"),
            "p_sale": p.astype("float32"), "p_year": p_year.astype("float32"), "notice": flag,
            "est_value": np.clip(est, 30_000, 5_000_000).astype("float32")}))
        print(f"  scored {a + len(s):,} of {len(s_all):,}", flush=True)
    out = pd.concat(parts, ignore_index=True)
    out["postcode"] = pd.Categorical.from_codes(out.pc.to_numpy(), categories=pd.Index(panel.pc_names).astype(str))
    out = out.drop(columns="pc"); out["unseen"] = False
    n_notice = int(out.notice.sum())                      # scored homes with a notice, before any others are added
    if second is not None and "NOTICE" in row_fams:       # homes named in a notice that the sale records do not hold
        import notice_signals as NS
        u = NS.unseen_homes(year, out, t0=when["read"] if when else None)
        print(f"{n_notice:,} scored homes have a notice; {len(u):,} more homes named in a notice have no sale on record "
              f"(expected sellers {u.p_sale.sum():,.0f})", flush=True)
        if len(u):
            u["postcode"] = pd.Categorical(u.postcode, categories=out.postcode.cat.categories)
            out = pd.concat([out, u[out.columns]], ignore_index=True)
    if second_json:
        json.dump({**sj, "homes_with_a_notice": n_notice, "unseen_homes": int(out.unseen.sum())},
                  open(cache / "second.json", "w"), indent=1)
    elif (cache / "second.json").exists():
        (cache / "second.json").unlink()
    if when:
        json.dump({**when, "sales": json.load(open(Path(live_dir) / "sales.json"))["sales"]}, open(cache / "live.json", "w"), indent=1)
    elif (cache / "live.json").exists():
        (cache / "live.json").unlink()
    out.to_parquet(cache / "scored_all.parquet", index=False)
    print(f"{len(out):,} owned homes scored, mean p {out.p_sale.mean():.4f}, expected sellers {out.p_sale.sum():,.0f}",
          flush=True)


# ---------------------------------------------------------------- stage 2
def houses(nat, cache_dir):
    """Split the national cells by postcode area: houses and sight-lines."""
    nat, out = Path(nat), Path(cache_dir) / "houses"
    out.mkdir(parents=True, exist_ok=True)
    writers, swriters = {}, {}
    files = sorted(p for p in (nat / "cells").glob("*.parquet") if not p.stem.endswith("_sight")
                   and "has_garden" in pq.read_schema(p).names)       # cells with no houses are skipped
    for i, p in enumerate(files):
        cid = int(p.stem.split("_")[0]) * 1000 + int(p.stem.split("_")[1])
        h = pd.read_parquet(p, columns=HOUSE_COLS)
        pdf = nat / "pd" / p.name                     # what could be built, where the permitted development table exists
        if pdf.exists():
            h = h.merge(pd.read_parquet(pdf, columns=PD_COLS), on="h3", how="left")
        else:
            for c in PD_COLS[1:]:
                h[c] = np.nan
        for c in ("pd_loft", "in_conservation", "listed"):
            h[c] = h[c].astype("float32")
        h = h[h.postcode.notna()]
        h["cell"] = np.int32(cid)
        for c in h.columns:
            if h[c].dtype == "float64":
                h[c] = h[c].astype("float32")
        h["postcode"] = h.postcode.astype(str); h["sector"] = h.sector.astype(str)
        h["area"] = area_of(h.postcode)
        s = pd.read_parquet(nat / "cells" / f"{p.stem}_sight.parquet")
        s = s.merge(h[["h3", "area"]], left_on="hid", right_on="h3")
        for a, g in h.groupby("area"):
            t = pa.Table.from_pandas(g.drop(columns="area"), preserve_index=False)
            if a not in writers:
                writers[a] = pq.ParquetWriter(out / f"{a}.parquet", t.schema)
            writers[a].write_table(t.cast(writers[a].schema))
        for a, g in s.groupby("area"):
            t = pa.Table.from_pandas(pd.DataFrame({"cell": np.int32(cid), "h3": g.h3.astype("int32"),
                                                   "lid": g.lid.astype("int32"), "dist_m": g.dist_m.astype("float32")}),
                                     preserve_index=False)
            if a not in swriters:
                swriters[a] = pq.ParquetWriter(out / f"{a}_sight.parquet", t.schema)
            swriters[a].write_table(t)
        if i % 100 == 0:
            print(f"  {i + 1} of {len(files)} cells split", flush=True)
    for w in list(writers.values()) + list(swriters.values()):
        w.close()
    print(f"{len(writers)} postcode areas written", flush=True)


# ---------------------------------------------------------------- stage 3
def draw_homes(nat, H, Sg, lmk, area_lms, wanted):
    """Both drawn views of each wanted house (row index into H), loading each
    cell's stored drawings once. The landmarks a house has in sight are
    marked on its upstairs view; the area's own landmarks are placed too,
    marked out of sight when this house cannot see them."""
    keys = H.loc[list(wanted), "key"]
    seen = Sg[Sg.key.isin(keys)].sort_values("dist_m")
    seen_by = {k: list(g.lid) for k, g in seen.groupby("key")}
    out = {}
    for cell, rows in H.loc[list(wanted)].groupby("cell"):
        P = load_panos(nat, int(cell))
        for i, row in rows.iterrows():
            j = int(row.h3)
            mine = [(lmk.loc[l, "name"], float(lmk.loc[l, "e"]), float(lmk.loc[l, "n"]), float(lmk.loc[l, "top_m"]))
                    for l in seen_by.get(row.key, [])][:10]
            names = {m[0] for m in mine}
            up = view_dict(P["pu_a"][j], P["pu_c"][j], P["pu_w"][j], row, mine + [l for l in area_lms if l[0] not in names])
            for l in up["lm"]:
                l["sees"] = bool(l["sees"] and l["name"] in names)
            garden = view_dict(P["pg_a"][j], P["pg_c"][j], P["pg_w"][j]) if bool(row.has_garden) else None
            out[i] = {"storeys": int(row.storeys), "reach_km": round(float(row.u_longest_km), 1),
                      "facing": round(float(row.u_best_bearing)) if np.isfinite(row.u_best_bearing) else 0,
                      "garden_bearing": round(float(row.garden_bearing)) if bool(row.has_garden) else None,
                      "up": up, "garden": garden}
        del P
    return out


def closest_to_typical(g, cols):
    z = sum(((g[c] - g[c].median()) / (g[c].std() or 1.0)).fillna(3.0) ** 2 for c in cols)
    return z.idxmin()


def lad_names(cache="research/data/onsud/postcode_lad.parquet"):
    """Postcode to local authority name, from the ONS UPRN Directory, read one
    part at a time and kept as a small table."""
    if not Path(cache).exists():
        parts = []
        for p in sorted(Path("research/data/onsud/parts").glob("*.parquet")):
            t = pd.read_parquet(p, columns=["postcode", "lad26cd"]).dropna()
            parts.append(t.drop_duplicates("postcode"))
        t = pd.concat(parts).drop_duplicates("postcode")
        names = pd.read_csv("research/data/onsud/lad_names.csv", encoding="utf-8-sig").set_index("LAD25CD").LAD25NM
        t["lad"] = names.reindex(t.lad26cd).to_numpy()
        t[["postcode", "lad"]].astype(str).to_parquet(cache, index=False)
    t = pd.read_parquet(cache)
    tidy = t.lad.str.replace(r"^(.*), (City of|County of)$", r"\2 \1", regex=True)   # "Bristol, City of" -> "City of Bristol"
    return pd.Series(tidy.to_numpy(), index=t.postcode.to_numpy())


def place(sub, lad, w):
    """The local authority most of these addresses are in."""
    s = pd.Series(w, index=lad.reindex(sub).to_numpy()).groupby(level=0).sum()
    return s.idxmax() if len(s) else ""


def centre_of(A, geo):
    if A in OVERRIDE:
        return OVERRIDE[A]["centre"], OVERRIDE[A]["centre_name"]
    if A in CENTRAL_LONDON:
        return CHARING_CROSS, "Charing Cross"
    g = geo[geo.outcode.str.match(rf"^{A}\d")]
    num = g.outcode.str.extract(r"^[A-Z]+(\d+)")[0].astype(float)
    g = g[num == num.min()]
    r = g.loc[g.pc_within_1km.idxmax()]
    return (float(r.lat), float(r.lon)), f"the centre of {TOWN.get(A, A)}"


def med1(s, nd=1):
    s = s.dropna()
    return round(float(s.median()), nd) if len(s) else None


def export_area(A, cache, geo, lmk, nat, scored, lad, amen, clim=None):
    H = pd.read_parquet(Path(cache) / "houses" / f"{A}.parquet").reset_index(drop=True)
    if clim is not None:                              # each house's climate, by its postcode
        ci, pcs = clim.drop_duplicates("postcode").set_index("postcode"), H.postcode.astype(str)
        for c, _, _ in CLIM:
            H[f"clim_{c}"] = pcs.map(ci[c]).to_numpy(dtype="float32")
    Sg = pd.read_parquet(Path(cache) / "houses" / f"{A}_sight.parquet")
    H["key"] = H.cell.astype(np.int64) * 10_000_000 + H.h3
    Sg["key"] = Sg.cell.astype(np.int64) * 10_000_000 + Sg.h3
    Sg["w"] = H.set_index("key").n_uprn.reindex(Sg.key).to_numpy()
    gA = geo[geo.postcode.isin(H.postcode.unique())].set_index("postcode")
    H["lat"] = gA.lat.reindex(H.postcode).to_numpy(); H["lon"] = gA.lon.reindex(H.postcode).to_numpy()
    H["lad"] = lad.reindex(H.postcode).to_numpy()
    tot = float(H.n_uprn.sum())
    (lat0, lon0), centre_name = centre_of(A, geo)
    ov = OVERRIDE.get(A, {})

    # landmarks seen by the most addresses in the area become search flags
    chosen, names = [], set()
    for lid, w in Sg.groupby("lid").w.sum().sort_values(ascending=False).items():
        if w < max(100, 0.005 * tot):
            break
        nm = lmk.loc[lid, "name"]
        near = any(np.hypot(lmk.loc[lid, "e"] - lmk.loc[c, "e"], lmk.loc[lid, "n"] - lmk.loc[c, "n"]) < 150 for c in chosen)
        if nm not in names and not near:              # one entry per structure (Wikidata can list a tower and its museum)
            chosen.append(lid); names.add(nm)
        if len(chosen) == N_LM:
            break
    area_lms = [(lmk.loc[l, "name"], float(lmk.loc[l, "e"]), float(lmk.loc[l, "n"]), float(lmk.loc[l, "top_m"])) for l in chosen]
    for i, lid in enumerate(chosen):
        H[f"sees_{i}"] = H.key.isin(Sg.key[Sg.lid == lid])

    flags = [{"key": k, "label": lab, "why": why or {"water": ov.get("water", WATER), "hills": ov.get("hills", HILLS)}[k],
              "group": "view"} for k, lab, why in V4.GENERIC]
    flagcols = ["has_" + k for k, *_ in V4.GENERIC]
    for k, lab, why, rule in V4.LIGHT:
        H["has_" + k] = rule(H).to_numpy()
        flags.append({"key": k, "label": lab, "why": why, "group": "light"}); flagcols.append("has_" + k)
    for k, lab, why, rule in BUILD:
        H["has_" + k] = rule(H).to_numpy()
        flags.append({"key": k, "label": lab, "why": why, "group": "build"}); flagcols.append("has_" + k)
    flags += [{"key": f"lm{i}", "label": f"Can see {nm}", "lm": nm, "group": "lm",
               "why": f"A clear line of sight from the upper windows to {nm}, checked against every roof and tree in between."}
              for i, (nm, *_) in enumerate(area_lms)]
    flagcols += [f"sees_{i}" for i in range(len(area_lms))]
    pc_dist, sec_dist = V4.mask_tables(H, flagcols)
    nb = len(NATION_FLAGS)

    # ---- owned homes, scored, into cells ------------------------------
    d = scored[scored.area == A].copy()
    d["postcode"] = d.postcode.astype(str)
    d = d.merge(geo[["postcode", "nox", "pc_within_1km", "km_gp", "km_hospital", "lat", "lon"]], on="postcode", how="left")
    d = d.merge(amen, on="postcode", how="left")
    if clim is not None:
        d = d.merge(clim, on="postcode", how="left")
    for c, _, _ in CLIM:
        if c not in d.columns:
            d[c] = np.nan
    pv = H.groupby("postcode").add_value.median().rename("add_value")      # typical value a house there could add
    d = d.merge(pv, left_on="postcode", right_index=True, how="left")
    d = d[d.nox.notna() & d.postcode.str.contains(" ")].copy()
    if not len(d):                                   # no sale records here: views only
        d = pd.DataFrame(columns=["postcode", "ptype", "tenure", "p_sale", "est_value", "nox", "pc_within_1km", "km_gp",
                                  "lat", "lon"]).astype({"postcode": str, "ptype": str, "p_sale": float, "est_value": float,
                                                         "lat": float, "lon": float, "tenure": float})
    part = d.postcode.str.rsplit(" ", n=1)
    d["outcode"] = part.str[0].astype(str); d["sector"] = (part.str[0] + " " + part.str[1].str[0]).astype(str)
    d["band"] = d.est_value.apply(V4.band_of).astype(str)
    pct = d.p_sale.rank(pct=True)
    d["premium"] = 0.06 + 0.12 * (1 - pct) + 0.004 * d.tenure.astype(float).clip(upper=25)
    d["offer_mid"] = d.est_value * (1 + d.premium)
    top_cut = float(d.p_sale.quantile(0.80)) if len(d) else 0.0
    d["top"] = d.p_sale >= top_cut
    dlat = (d.lat - lat0) * 111.19; dlon = (d.lon - lon0) * 111.19 * np.cos(np.radians(lat0))
    d["mins"] = np.hypot(dlat, dlon) / V4.KMH_URBAN * 60
    d["cell"] = d.sector + "|" + d.ptype + "|" + d.band
    a = d[["cell", "postcode", "sector"]].merge(pc_dist, on="postcode", how="left")
    miss = a["mask"].isna()
    b = a.loc[miss, ["cell", "sector"]].merge(sec_dist, on="sector", how="left")
    a = pd.concat([a.loc[~miss, ["cell", "mask", "w"]], b[["cell", "mask", "w"]]])
    a["mask"] = a["mask"].fillna(0).astype(np.int64); a["w"] = a.w.fillna(1.0)
    hist = a.groupby(["cell", "mask"]).w.sum()
    cells = []
    for cell, g in d.groupby("cell"):
        if len(g) < 12:
            continue
        sec, pt, band = cell.split("|")
        vm = []                                       # combinations held by at least 1.5% of the cell's homes
        for m_, w_ in hist.loc[cell].items():
            if w_ >= max(0.05, 0.015 * len(g)):
                vm += [int(m_), round(float(w_), 1)]
        cells.append([sec, pt, band, int(len(g)), int(g.top.sum()), round(float(g.p_sale.sum()), 2),
                      round(float(g.p_sale.median()), 4), int(g.est_value.median() // 1000 * 1000),
                      int(g.offer_mid.median() // 1000 * 1000), round(float(g.premium.median()), 3),
                      float(g.tenure.median()), round(float(g.nox.median()), 1), int(g.pc_within_1km.median()),
                      round(float(g.km_gp.median()), 2), int(round(g.mins.median())), round(float(g.lat.median()), 4),
                      round(float(g.lon.median()), 4), vm,
                      med1(g.km_hospital), med1(g.km_park, 2), med1(g.km_blue), med1(g.km_pub, 2),
                      int(g.add_value.median()) if g.add_value.notna().any() else None]
                     + [med1(g[c], nd) for c, _, nd in CLIM])

    # ---- each sector: shares, and two real houses to draw -----------------
    H["log_reach"] = np.log10(H.u_longest_km.clip(lower=0.05))
    H["outlook"] = (H.u_long.fillna(0) + 2 * H.u_water.fillna(0) + H.u_hills.fillna(0) + 0.02 * H.u_longest_km.fillna(0)
                    + sum((1.0 if i == 0 else 0.3) * H[f"sees_{i}"].astype(float) for i in range(len(area_lms))))
    sec_mask = sec_dist.assign(sub=sec_dist["mask"].to_numpy() & ((1 << nb) - 1)).groupby(["sector", "sub"]).w.sum()
    views, nation, picks = {}, [], {}
    for sec, g in H.groupby("sector"):
        wg = g.n_uprn.to_numpy(float)
        share = lambda col: round(float(np.average(g[col].fillna(False).astype(float), weights=wg)), 2)
        if len(g) >= 25:
            gg = g[g.has_garden] if g.has_garden.any() else g
            gard = g[g.has_garden]
            typ = closest_to_typical(gg, ["u_long", "u_horizon", "log_reach", "u_hills", "sun_equinox", "sun_evening_jun"])
            best = g.outlook.idxmax()
            picks[sec] = [(typ, "typical")] + ([(best, "best")] if best != typ else [])
            med = lambda s: round(float(s.median()), 1) if len(s) else None
            views[sec] = {
                "n_houses": int(len(g)), "n_addr": int(wg.sum()),
                "landmarks": {nm: share(f"sees_{i}") for i, (nm, *_) in enumerate(area_lms)},
                "typical": {"horizon_deg": med(gard.g_horizon),
                            "overlooked": round(float(gard.g_overlooked.median()), 2) if len(gard) else None,
                            "longest_km": med(g.u_longest_km), "sun_jun": med(gard.sun_jun),
                            "sun_evening_jun": med(gard.sun_evening_jun), "sun_equinox": med(gard.sun_equinox),
                            "sun_dec": med(gard.sun_dec), "storeys": float(g.storeys.median())},
                "shares": {c[4:]: share(c) for c in flagcols[:nb]}}
        # the national table: every sector's share of each combination of outlook and light flags
        vm = []
        for m_, w_ in sec_mask.loc[sec].sort_values(ascending=False).items():
            if w_ >= 0.03:
                vm += [int(m_), round(float(w_), 2)]
        lads = pd.Series(wg, index=g.lad.fillna("").to_numpy()).groupby(level=0).sum()
        nation.append([sec, A, lads.idxmax() if len(lads) else "", int(wg.sum()),
                       round(float(g.lat.mean()), 3) if g.lat.notna().any() else None,
                       round(float(g.lon.mean()), 3) if g.lon.notna().any() else None,
                       vm, round(float(np.average(g.lm_n.fillna(0) > 0, weights=wg)), 2),
                       [med1(g[f"clim_{c}"], nd) if f"clim_{c}" in g else None for c, _, nd in CLIM]])

    # ---- three owners to show the postcard and offer pages ----------------
    by_pc = H[H.has_garden].reset_index().groupby("postcode").head(1).set_index("postcode")["index"]
    rng = np.random.RandomState({"EX": 42, "BA": 7}.get(A, zlib.crc32(A.encode()) % 2**31))
    if "notice" not in d:
        d["notice"] = False
    pool = d[d.top & ~d.notice.astype(bool) & d.ptype.isin(["S", "T", "D"]) & d.est_value.between(200_000, 700_000)
             & d.sector.isin(list(views))].nlargest(400, "p_sale")
    ex_rows, seen_sec = [], set()
    for _, r in pool.iterrows():
        if r.sector in seen_sec or len(ex_rows) >= 3 or r.postcode not in by_pc.index:
            continue
        seen_sec.add(r.sector); ex_rows.append((r, int(by_pc[r.postcode])))

    wanted = {i for v in picks.values() for i, _ in v} | {i for _, i in ex_rows}
    drawn = draw_homes(nat, H, Sg, lmk, area_lms, wanted)
    for sec, v in picks.items():
        views[sec]["homes"] = [{"kind": kind, **drawn[i]} for i, kind in v]
    exemplars = [{
        "code": f"{r.outcode}-{rng.randint(0x1000, 0xFFFF):04X}", "city": A, "sector": r.sector,
        "ptype": r.ptype, "tenure": int(r.tenure), "p_sale": round(float(r.p_sale), 3),
        "est_value": int(round(r.est_value, -4)), "offer_lo": int(round(r.offer_mid * 0.96, -3)),
        "offer_mid": int(round(r.offer_mid, -3)), "offer_hi": int(round(r.offer_mid * 1.04, -3)),
        "premium_pct": round(float(r.premium) * 100, 1), "nox": round(float(r.nox), 1),
        "min_centre": int(round(r.mins)), "home": {"kind": "yours", **drawn[i]}} for r, i in ex_rows]

    outs = {}
    for oc, g in H.groupby(H.postcode.str.split(" ").str[0]):
        lads = pd.Series(g.n_uprn.to_numpy(float), index=g.lad.fillna("").to_numpy()).groupby(level=0).sum()
        outs[oc] = ov.get("outcodes", {}).get(oc) or (lads.idxmax() if len(lads) else "")
    entry = {
        "code": A, "name": TOWN.get(A, A), "region": REGION_OF.get(A, "Other"), "centre_name": centre_name,
        "frank": A, "areas": outs, "lat": round(lat0, 4), "lon": round(lon0, 4),
        "area": {"n_owned_tracked": int(len(d)), "exp_sellers_12m": round(float(d.p_sale.sum())),
                 "top_band_cut": round(top_cut, 4), "p_sale_mean": round(float(d.p_sale.mean()), 4) if len(d) else 0,
                 "n_houses_viewed": int(len(H)), "n_addr_viewed": int(tot)},
        "flags": flags,
        "landmarks": [{"name": nm, "e": round(e), "n": round(n), "top_m": round(z)} for nm, e, n, z in area_lms],
        "cell_cols": CELL_COLS, "cells": cells, "exemplars": exemplars, "views": views}
    return entry, nation


def export(cache, geo_path, nat, lab_dir, out_dir, *only):
    cache, out = Path(cache), Path(out_dir)
    (out / "areas").mkdir(parents=True, exist_ok=True)
    geo = pd.read_parquet(geo_path)
    lmk = pd.read_parquet("research/data/landmarks/national_landmarks.parquet").set_index("lid")
    scored = pd.read_parquet(cache / "scored_all.parquet")
    cats = scored.postcode.cat.categories                 # the postcode area, worked out once per postcode
    scored["area"] = area_of(pd.Series(cats)).fillna("?").to_numpy()[scored.postcode.cat.codes.to_numpy()]
    lad = lad_names()
    amen = pd.read_parquet("research/data/signals/amenity_postcode.parquet",
                           columns=["postcode", "km_park", "km_blue", "km_pub"])
    cp = Path("research/data/signals/climate_postcode.parquet")
    clim = (pd.read_parquet(cp, columns=["postcode"] + [c for c, _, _ in CLIM]).drop_duplicates("postcode")
            if cp.exists() else None)
    lab = Path(lab_dir)
    load = lambda f: json.load(open(lab / f)) if (lab / f).exists() else {}
    deploy = load("lab_deploy.json"); pct = deploy.get("pct", 100); name = deploy.get("name", "ALL")
    best = load(f"lab_fit_{name}@{pct}.json") or load("lab_curve.json").get(f"ALL@{pct}") or {}
    local = load("lab_local.json").get(f"{name}@{pct}", {})
    model = {"auc_oot": round(best.get("auc", 0), 3),
             "lift_top10": round(local.get("local_lift10") or best.get("lift10", 0), 2),
             "lift_top10_national": round(best.get("lift10", 0), 2), "lift_top1": round(best.get("lift1", 0), 2),
             "train_rows": deploy.get("train_rows"), "sample_pct": pct, "n_signals": len(deploy.get("features", [])),
             "families": deploy.get("families"),
             "trained_on": "HM Land Registry Price Paid Data 1995-2019, 24.3M transactions"}
    if (cache / "second.json").exists():                  # a second step was used to score (notice_step.py): its own headline
        sec = json.load(open(cache / "second.json"))
        if sec.get("lift_top10"):
            model["lift_top10"] = round(sec["lift_top10"]["with_notices"], 2)
        model["second_step"] = {"reads": sec.get("row_families"), "homes_with_a_notice": sec.get("homes_with_a_notice"),
                                "homes_with_no_sale_on_record": sec.get("unseen_homes")}
    if (cache / "live.json").exists():                    # scored by the live refresh: what the scores are made from
        import calendar
        import datetime as dt
        lv = json.load(open(cache / "live.json"))
        day, (y, m) = dt.date.fromisoformat(lv["notices_to"]), lv["sales_to"].split("-")
        model["as_of"] = {"sales_to": f"{calendar.month_name[int(m)]} {y}", "notices_to": f"{day.day} {calendar.month_name[day.month]} {day.year}",
                          "scored_on": lv["scored_on"], "sales": lv.get("sales")}
    areas = sorted(p.stem for p in (cache / "houses").glob("*.parquet") if not p.stem.endswith("_sight"))
    areas = [a for a in areas if not only or a in only]
    index, nation, first = [], [], None
    for A in areas:
        entry, nat_rows = export_area(A, cache, geo, lmk, nat, scored, lad, amen, clim)
        nation += nat_rows
        with open(out / "areas" / f"{A}.json", "w") as fh:
            json.dump(entry, fh, separators=(",", ":"))
        if A == DEFAULT_AREA:
            first = entry
        index.append({"code": A, "name": entry["name"], "region": entry["region"], "lat": entry["lat"], "lon": entry["lon"],
                      "homes": entry["area"]["n_addr_viewed"], "sectors": len(entry["views"])})
        print(f"{A} {entry['name']}: {entry['area']['n_houses_viewed']:,} houses, {len(entry['cells'])} cells, "
              f"{len(entry['views'])} sectors drawn, {len(entry['exemplars'])} exemplars, "
              f"landmarks {[l['name'] for l in entry['landmarks']]}, "
              f"{(out / 'areas' / f'{A}.json').stat().st_size / 1e6:.2f} MB", flush=True)
    first = first or json.load(open(out / "areas" / f"{index[0]['code']}.json"))
    site = {"model": model,
            "nox_national": {str(k): v for k, v in geo.nox.quantile([.1, .25, .5, .75, .9]).round(2).to_dict().items()},
            "density_national": {str(k): v for k, v in geo.pc_within_1km.quantile([.1, .25, .5, .75, .9]).round(0).to_dict().items()},
            # climate filters: national quarters and halves across every postcode in England and Wales
            "climate_national": ({short: {str(k): round(float(v), nd) for k, v in clim[c].quantile([.25, .5, .75]).items()}
                                  for c, short, nd in CLIM} if clim is not None else {}),
            "alph": ALPH, "a_lo": round(float(A_LO), 4), "a_span": round(float(A_SPAN), 4),
            "index": index, "nation_flags": NATION_FLAGS, "default_area": first["code"], "cities": {first["code"]: first}}
    with open(out / "site_data.json", "w") as fh:
        json.dump(site, fh, separators=(",", ":"))
    with open(out / "nation.json", "w") as fh:                 # every sector in the country, fetched beside the page
        json.dump({"flags": NATION_FLAGS, "rows": nation}, fh, separators=(",", ":"))
    print(f"wrote {len(index)} areas and {out / 'site_data.json'} ({(out / 'site_data.json').stat().st_size / 1e6:.1f} MB); "
          f"{len(nation):,} sectors in the national table", flush=True)
    import export_sectors                                        # the national ranking table the search starts from
    export_sectors.build(out)


if __name__ == "__main__":
    {"score": score, "live": live, "houses": houses, "export": export}[sys.argv[1]](*sys.argv[2:])
