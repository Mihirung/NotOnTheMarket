"""Before the site moves to current sales: does the model still rank, on any day of the year and years on?

The model was fitted on scores made each 1 January from sales to 2015 (the lab's fit) or 2018 (the
deployed one). The live site scores on the first of whatever month the sale records reach, years later.
Three questions, answered on the up-to-date sale records (live_sales.py):

  The day of the year. panel2.clock() moves every date on so that the first of any month becomes a
  1 January, and every feature then reads the twelve months before it. Does the best tenth find as many
  sellers scored in April, July and October as in January?

  The model's age. Scored on days from 2017 to 2025 against the sales of the twelve months that follow:
  how fast does a model fitted to 2015, or to 2018, lose its edge?

  Sales not yet registered. The Land Registry's latest file holds only part of the last six months'
  sales. One scoring day is run again with that share of its last six months hidden: how much does the
  ranking lose, how many of the homes it puts in the best tenth had in fact just been sold, and how much
  comes back when each sale of a part-registered month is counted for the ones still to come (panel2's
  `late` weights)?

Homes: the tenth never used to fit the lab's model. Figures are sellers found in the best tenth of each
postcode district, times random, with a 95% range from resampling blocks of homes.

  Homes not yet on the market. The site's model is aimed at sales completing six to eighteen months after
  the scoring day and reads energy certificates (LATE_MODEL.md). Does it still find more of those later
  sellers than the model of sales in the next twelve months, years on, and with part of the last six
  months' sales hidden?

    python live_check.py            about an hour (the first three questions)
    python live_check.py lag        the third question again, keeping the rest
    python live_check.py late       the fourth question, keeping the rest (about 25 minutes; needs epc_fetch.py to this year)
    python live_check.py late lag   its second half: one day with part of its last six months hidden (about 15 minutes)
    python live_check.py report     the write-up again, from the figures on disk

Writes research/outputs/signals/LIVE_CHECK.json and .md.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import live_sales as LS  # noqa: E402
import local_eval as LE  # noqa: E402
import panel2 as P2  # noqa: E402
import screen_late as SL  # noqa: E402
import signals as SG  # noqa: E402
from notice_later_year import top_mask  # noqa: E402

LIVE = Path("research/data/live")
LAB, OUT = SL.LAB, SL.OUT
MODELS = {"to_2015": LAB / "models" / f"{SL.CUR}@100.txt", "to_2018": LAB / "model_deploy.txt"}
FITTED_TO = {"to_2015": 2015, "to_2018": 2018}
MONTHS = {1: "January", 4: "April", 7: "July", 10: "October"}
YEARS = range(2017, 2026)
TEST_BUCKETS = 10
LAG_DAY = dt.date(2025, 10, 1)                          # the day run again with its last six months part hidden
LATE_MODELS = {"year_to_2015": LAB / "models" / f"{SL.CUR}@100.txt", "late_to_2015": LAB / "models" / f"{SL.CUR}+EPC@100~late.txt",
               "year_to_2018": LAB / "model_deploy.txt", "late_to_2018": LAB / "model_deploy_late.txt"}
LATE_LAG_DAY = dt.date(2024, 10, 1)                     # its later sales (April 2025 to March 2026) are all but registered


def lift(p, y, district, block, keep=None):
    """Sellers found in the best tenth of each district, times random, and a 95% range."""
    if keep is not None:
        p, y, district, block = p[keep], y[keep], district[keep], block[keep]
    top = top_mask(p, district).astype(np.float64); y = y.astype(np.float64); blk = block.astype(np.int64)
    S = [np.bincount(blk, v, LE.N_BLOCKS) for v in (y * top, top, y, np.ones(len(y)))]
    G = np.random.default_rng(3).poisson(1.0, (500, LE.N_BLOCKS)).astype(np.float64)
    b = ((G @ S[0]) / (G @ S[1])) / ((G @ S[2]) / (G @ S[3]))
    return [round(float((S[0].sum() / S[1].sum()) / (S[2].sum() / S[3].sum())), 4)] + [round(float(np.percentile(b, q)), 4) for q in (2.5, 97.5)]


def scored(panel, day, boosters, fams, lookups):
    """The test homes owned on `day`, each model's figure for them, and whether they sold in the twelve months after."""
    T = P2.clock(day)[1]
    spells = np.nonzero(panel.bucket < TEST_BUCKETS)[0]
    rows, years, label = panel.expand(spells, y_from=T, y_to=T)
    X = P2.full_features(panel, rows, years, fams, lookups)
    return {"rows": rows, "y": label, "district": panel.oc[rows], "block": panel.block[rows], "tenure": T - panel.year[rows],
            "p": {m: b.predict(X, num_threads=4) for m, b in boosters.items()}}


def scored_late(panel, day, boosters, fams, lookups):
    """As scored(), with the certificate columns, and whether each home's sale completed six to eighteen months after."""
    T = P2.clock(day)[1]
    spells = np.nonzero(panel.bucket < TEST_BUCKETS)[0]
    rows, years, label = panel.expand(spells, y_from=T, y_to=T)
    end = panel.end_year[rows].astype(np.int64) * 12 + panel.month[np.minimum(rows + 1, len(panel.month) - 1)] - 1
    late = (panel.sold[rows] & (end >= T * 12 + 6) & (end < T * 12 + 18)).astype(np.uint8)
    X = P2.full_features(panel, rows, years, fams, lookups)
    nb = len(SG.columns([f for f in fams if f != "EPC"]))                    # the certificate columns come last
    return {"rows": rows, "y": label, "late": late, "district": panel.oc[rows], "block": panel.block[rows], "tenure": T - panel.year[rows],
            "p": {m: b.predict(X if b.num_feature() == X.shape[1] else X[:, :nb], num_threads=4) for m, b in boosters.items()}}


def late_check(part="days"):
    """`days`: each 1 January from 2019. `lag`: one day again with part of its last six months hidden and counted up.
    They run apart because a panel with thirty million certificates beside it leaves little room for a second."""
    import gc
    info = json.load(open(LIVE / "sales.json"))
    last = int(info["last_month"][:4]) * 12 + int(info["last_month"][5:]) - 1
    fams = json.load(open(LAB / "lab_deploy.json"))["families"] + ["EPC"]
    boosters = {m: lgb.Booster(model_file=str(f)) for m, f in LATE_MODELS.items() if f.exists()}
    R = json.load(open(OUT / "LIVE_CHECK.json"))
    L = R.setdefault("late", {"models": sorted(boosters), "days": [], "lag": {}})
    P2.set_last_year(2027)
    src = LIVE / "transactions.parquet"
    if part == "days":
        L["models"], L["days"] = sorted(boosters), []
        panel = P2.Panel(src, verbose=False)
        lookups = {f: SG.lookup(f, panel.pc_names) for f in fams if f not in SG.TIME_VARYING and f not in SG.ROW_FAMILIES}
        for y in YEARS:
            if y < 2019 or y * 12 + 18 > last + 1:                          # the later sales are not all on record
                continue
            d = scored_late(panel, dt.date(y, 1, 1), boosters, fams, lookups)
            row = {"day": f"{y}-01-01", "homes": int(len(d["y"])), "sold_later": round(float(d["late"].mean()), 4),
                   "after_months_part_registered": max(0, y * 12 + 18 - (last - 5))}
            for m in boosters:
                if y > int(m[-4:]):
                    row[m] = lift(d["p"][m], d["late"], d["district"], d["block"])
                    row[m + "_t20p"] = lift(d["p"][m], d["late"], d["district"], d["block"], d["tenure"] >= 20)
            L["days"].append(row)
            print(json.dumps(row), flush=True)
    else:
        t = pd.read_parquet(src, columns=["key", "year", "month"])
        ym = t.year.to_numpy().astype(np.int64) * 12 + t.month.to_numpy() - 1
        d0 = LATE_LAG_DAY.year * 12 + LATE_LAG_DAY.month - 1
        share = {last - m: q for m, q in LS.registered(ym).items()}
        rng = np.random.default_rng(11); hide = np.zeros(len(t), bool)
        for k, q in share.items():
            m = ym == d0 - 1 - k
            hide[m] = rng.random(int(m.sum())) > q
        hidden = t.key.to_numpy()[hide]; del t, ym
        shift = P2.clock(LATE_LAG_DAY)[0]
        panel = P2.Panel(src, verbose=False, shift=shift)
        lookups = {f: SG.lookup(f, panel.pc_names) for f in fams if f not in SG.TIME_VARYING and f not in SG.ROW_FAMILIES}
        full = scored_late(panel, LATE_LAG_DAY, boosters, fams, lookups)
        full.pop("rows"); del panel; gc.collect()
        late = {d0 - 1 - k + shift: 1 / q for k, q in share.items() if q < 1}
        thin = pd.read_parquet(src)[~hide]
        panel = P2.Panel(thin, verbose=False, shift=shift, late=late); del thin; gc.collect()
        part_ = scored_late(panel, LATE_LAG_DAY, boosters, fams, lookups)
        gone = np.isin(panel.key[part_["rows"]], hidden)
        G = L["lag"] = {"day": LATE_LAG_DAY.isoformat(), "sales_hidden": int(hide.sum()), "homes": int(len(part_["y"])),
                        "just_sold_share_of_homes": round(float(gone.mean()), 4), "models": {}}
        for m in boosters:
            top = top_mask(part_["p"][m], part_["district"])
            G["models"][m] = {"all_sales_known": lift(full["p"][m], full["late"], full["district"], full["block"]),
                              "part_hidden_counted_up": lift(part_["p"][m], part_["late"], part_["district"], part_["block"]),
                              "just_sold_share_of_best_tenth": round(float(gone[top].mean()), 4)}
            print(m, json.dumps(G["models"][m]), flush=True)
    json.dump(R, open(OUT / "LIVE_CHECK.json", "w"), indent=1)
    report(R)


def main(only_lag=False):
    info = json.load(open(LIVE / "sales.json"))
    last = int(info["last_month"][:4]) * 12 + int(info["last_month"][5:]) - 1
    fams = json.load(open(LAB / "lab_deploy.json"))["families"]
    boosters = {m: lgb.Booster(model_file=str(f)) for m, f in MODELS.items()}
    assert all(b.feature_name() == SG.columns(fams) for b in boosters.values()), "a model's columns do not match its families"
    tx = pd.read_parquet(LIVE / "transactions.parquet")
    R = {"sales_to": info["last_month"], "homes": "the tenth never used to fit the lab's model", "days": [], "lag": {}}
    if only_lag:
        R = json.load(open(OUT / "LIVE_CHECK.json"))
    P2.set_last_year(2027)
    lookups = None
    for month in ([] if only_lag else MONTHS):
        panel = P2.Panel(tx, verbose=False, shift=P2.clock(dt.date(2020, month, 1))[0])
        if lookups is None:
            lookups = {f: SG.lookup(f, panel.pc_names) for f in fams if f not in SG.TIME_VARYING}
        for y in YEARS:
            day = dt.date(y, month, 1)
            if y * 12 + month - 1 + 12 > last + 1:                       # the twelve months after it are not all on record
                continue
            d = scored(panel, day, boosters, fams, lookups)
            row = {"day": day.isoformat(), "month": MONTHS[month], "year": y, "homes": int(len(d["y"])), "sold": round(float(d["y"].mean()), 4),
                   "after_months_part_registered": max(0, y * 12 + month - 1 + 12 - (last - 5))}
            for m in boosters:
                if y > FITTED_TO[m]:
                    row[m] = lift(d["p"][m], d["y"], d["district"], d["block"])
                    row[m + "_t20p"] = lift(d["p"][m], d["y"], d["district"], d["block"], d["tenure"] >= 20)
            R["days"].append(row)
            print(json.dumps(row), flush=True)
        del panel

    # the last six months part hidden, as in the Land Registry's latest file: the share of each month registered so far
    ym = tx.year.to_numpy().astype(np.int64) * 12 + tx.month.to_numpy() - 1
    d0 = LAG_DAY.year * 12 + LAG_DAY.month - 1
    share = {last - m: q for m, q in LS.registered(ym).items()}                # months before the last: share registered
    rng = np.random.default_rng(11)
    hide = np.zeros(len(tx), bool)
    for k, q in share.items():
        m = ym == d0 - 1 - k
        hide[m] = rng.random(int(m.sum())) > q
    shift = P2.clock(LAG_DAY)[0]
    panel = P2.Panel(tx, verbose=False, shift=shift)
    if lookups is None:
        lookups = {f: SG.lookup(f, panel.pc_names) for f in fams if f not in SG.TIME_VARYING}
    full = scored(panel, LAG_DAY, boosters, fams, lookups)
    late = {d0 - 1 - k + shift: 1 / q for k, q in share.items() if q < 1}      # each part-registered month, counted up
    made = scored(P2.Panel(tx[~hide], verbose=False, shift=shift, late=late), LAG_DAY, boosters, fams, lookups)
    panel = P2.Panel(tx[~hide], verbose=False, shift=shift)
    part = scored(panel, LAG_DAY, boosters, fams, lookups)
    gone = np.isin(panel.key[part["rows"]], tx.key.to_numpy()[hide])        # sold in those months, the sale not yet registered
    m = "to_2018"
    top = top_mask(part["p"][m], part["district"])
    R["lag"] = {"day": LAG_DAY.isoformat(), "share_registered_k_months_before_the_last": {str(k): round(q, 3) for k, q in share.items()},
                "sales_hidden": int(hide.sum()), "homes": int(len(part["y"])),
                "all_sales_known": lift(full["p"][m], full["y"], full["district"], full["block"]),
                "part_hidden": lift(part["p"][m], part["y"], part["district"], part["block"]),
                "part_hidden_counted_up": lift(made["p"][m], made["y"], made["district"], made["block"]),
                "part_hidden_among_homes_not_just_sold": lift(part["p"][m], part["y"], part["district"], part["block"], ~gone),
                "just_sold_share_of_homes": round(float(gone.mean()), 4), "just_sold_share_of_best_tenth": round(float(gone[top].mean()), 4),
                "just_sold_times_random": round(float(gone[top].mean() / gone.mean()), 2)}
    print(json.dumps(R["lag"]), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(OUT / "LIVE_CHECK.json", "w"), indent=1)
    report(R)


def report(R):
    cell = lambda r, m: f"{r[m][0]:.3f}" + ("*" if r["after_months_part_registered"] else "") if m in r else ""      # noqa: E731
    rng = lambda v: f"{v[0]:.3f} ({v[1]:.3f} to {v[2]:.3f})"                                                         # noqa: E731
    by = {(r["year"], r["month"]): r for r in R["days"]}
    years = sorted({r["year"] for r in R["days"]})
    md = ["# The model on current sales: any day of the year, and years on", "",
          f"Sale records to {R['sales_to']} (live_sales.py). Homes: {R['homes']}. Each cell scores the homes owned on the first of that",
          "month and counts the sellers of the twelve months that follow, found in the best tenth of each postcode district, times",
          "random. A star marks a day whose twelve months run into the last six on record, which are only part registered: fewer",
          "sales are counted, in the best tenth and outside it alike.", ""]
    for m, title in (("to_2015", "The model fitted on sales to 2015"), ("to_2018", "The deployed model, fitted on sales to 2018")):
        md += [f"## {title}", "", "| Scored on the first of | " + " | ".join(MONTHS.values()) + " |", "|---|" + "---|" * len(MONTHS)]
        md += [f"| {y} | " + " | ".join(cell(by[(y, mo)], m) if (y, mo) in by else "" for mo in MONTHS.values()) + " |"
               for y in years if any(m in by.get((y, mo), {}) for mo in MONTHS.values())]
        md.append("")
    L = R["lag"]
    md += ["## Sales not yet registered", "",
           f"The latest file holds {', '.join(f'{100 * float(q):.0f}%' for q in reversed(list(L['share_registered_k_months_before_the_last'].values())))} of the sales of its last six",
           f"months, oldest first, judged against the same months a year before. {L['day']} is scored again with that share of its own last six",
           f"months hidden ({L['sales_hidden']:,} sales), by the deployed model.", "",
           "| | Best tenth, times random |", "|---|---|",
           f"| Every sale before the day known | {rng(L['all_sales_known'])} |",
           f"| Part of the last six months hidden | {rng(L['part_hidden'])} |",
           f"| The same, each sale of a part-registered month counted for those still to come | {rng(L['part_hidden_counted_up'])} |",
           f"| The same, among homes that had not just been sold | {rng(L['part_hidden_among_homes_not_just_sold'])} |", "",
           f"Homes sold in those six months whose sale was hidden are {100 * L['just_sold_share_of_homes']:.1f}% of the homes scored and "
           f"{100 * L['just_sold_share_of_best_tenth']:.1f}% of the best tenth",
           f"({L['just_sold_times_random']:.1f} times random): the ranking finds them because they were about to sell, and cannot know they have.", ""]
    if R.get("late", {}).get("days"):
        T = R["late"]; ms = T["models"]
        NAME = {"year_to_2015": "Next twelve months, fitted to 2015", "late_to_2015": "Later sales with certificates, fitted to 2015",
                "year_to_2018": "Next twelve months, fitted to 2018 (the model before)", "late_to_2018": "Later sales with certificates, fitted to 2018 (the site's)"}
        md += ["## Homes not yet on the market", "",
               "Scored on 1 January; the sellers counted are those completing between July of that year and June of the next. A model",
               "is shown only for the years after the last one it was fitted on.", "",
               "| Scored on 1 January | " + " | ".join(NAME[m] for m in ms) + " |", "|---|" + "---|" * len(ms)]
        md += [f"| {r['day'][:4]} | " + " | ".join(cell(r, m) for m in ms) + " |" for r in T["days"]]
        G = T.get("lag") or {}
        if G:
            md += ["", f"{G['day']} with part of its last six months hidden and counted up, as the live site scores ({G['sales_hidden']:,} sales hidden; "
                   f"the homes just sold are {100 * G['just_sold_share_of_homes']:.1f}% of those scored):", "",
                   "| Model | Every sale known | Part hidden, counted up | Just sold, share of the best tenth |", "|---|---|---|---|"]
            md += [f"| {NAME[m]} | {rng(v['all_sales_known'])} | {rng(v['part_hidden_counted_up'])} | {100 * v['just_sold_share_of_best_tenth']:.1f}% |"
                   for m, v in G["models"].items()]
        md.append("")
    (OUT / "LIVE_CHECK.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    if sys.argv[1:] == ["report"]:
        report(json.load(open(OUT / "LIVE_CHECK.json")))
    elif sys.argv[1:2] == ["late"]:
        late_check("lag" if sys.argv[2:] == ["lag"] else "days")
    else:
        main(only_lag=sys.argv[1:] == ["lag"])
