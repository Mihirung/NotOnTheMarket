"""Do homes named in a deceased-estate or bankruptcy notice sell soon after? A first test on a sample of notices.

Each notice (gazette_fetch.py) is joined to the home whose sales we know, by
postcode, house number or name, and flat, the same key as the sale records.
For homes still in the same hands on 1 January after the notice, the share
sold in that calendar year is compared with what homes owned for as long
sell at in the same year. That is the model's own question (a sale in the
next 12 months) asked of these homes alone.

Nothing about a person or an address is written out: only counts and rates.

    python gazette_test.py [deceased|bankruptcy]

Writes research/outputs/signals/GAZETTE_TEST.json and .md (deceased) or BANKRUPTCY_TEST.json and .md.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import assess_signal as A  # noqa: E402
import local_eval as LE  # noqa: E402
from planning_link import key_of, readings  # noqa: E402

KIND = sys.argv[1] if len(sys.argv) > 1 else "deceased"
DIR = Path("research/data/gazette" if KIND == "deceased" else "research/data/gazette_bankruptcy")
NOTICES, STATE = DIR / "notices.jsonl", DIR / "state.json"
EVENT = {"deceased": ("died", "death", "Deceased-estate notices", "GAZETTE_TEST"),
         "bankruptcy": ("ordered", "bankruptcy order", "Bankruptcy orders", "BANKRUPTCY_TEST")}[KIND]
TX = "research/data/transactions.parquet"
OUT = Path(A.OUT)


def load_notices():
    n = pd.DataFrame([json.loads(l) for l in open(NOTICES)])
    for c in ("address", "a1", "a2", "postcode", "died", "ordered", "edition"):
        if c not in n:
            n[c] = None
    n["died"] = n[EVENT[0]]                                   # the dated event: the death, or the bankruptcy order
    n = n[n.edition.fillna("").str.contains("London") & n.postcode.notna() & n.died.notna()].copy()
    n["addr"] = n.address.fillna(n.a1.fillna("") + np.where(n.a2.notna(), ", " + n.a2.fillna(""), ""))
    n["pub"] = pd.to_datetime(n.published, errors="coerce"); n["dod"] = pd.to_datetime(n.died, errors="coerce")
    return n.dropna(subset=["pub", "dod"])


def link(n, tx_keys):
    """The first reading of each address that is a home with a sale record."""
    rows = []
    for i, (addr, pc) in enumerate(zip(n.addr, n.postcode)):
        for rank, (paon, saon) in enumerate(readings(addr, pc)):
            rows.append((i, rank, pc, paon, saon))
    r = pd.DataFrame(rows, columns=["i", "rank", "pc", "paon", "saon"])
    r["key"] = key_of(r.pc, r.paon, r.saon)
    r = r[r.key.isin(tx_keys)].sort_values(["i", "rank"]).drop_duplicates("i")
    key = np.full(len(n), -1, dtype=np.int64); has = np.zeros(len(n), bool)
    key[r.i.to_numpy()] = r.key.to_numpy(); has[r.i.to_numpy()] = True
    return key, has


def main():
    n = load_notices()
    tx = pd.read_parquet(TX, columns=["key", "year", "month"])
    key, has = link(n, set(tx.key.unique()))
    n_all = n.assign(key=key, has=has)
    n = n_all[has].copy()
    t = tx[tx.key.isin(set(n.key))].copy()
    t["ym"] = t.year.astype(int) * 12 + t.month.astype(int) - 1
    by = t.groupby("key").ym.apply(lambda s: np.sort(s.to_numpy()))
    n["dod_ym"] = n.dod.dt.year * 12 + n.dod.dt.month - 1
    n["pub_ym"] = n.pub.dt.year * 12 + n.pub.dt.month - 1
    bought, nxt = [], []
    for k, d in zip(n.key, n.dod_ym):
        s = by[k]
        b = s[s <= d]; a = s[s > d]
        bought.append(b[-1] if len(b) else -1); nxt.append(a[0] if len(a) else -1)
    n["bought"] = bought; n["next"] = nxt
    owned = n[n.bought >= 0].copy()                          # the home was last bought before the death

    # what homes owned for as long sell at: the test homes of the national panel, by year and whole years owned
    te = LE.load_test(A.PANEL, years=(2016, 2018))
    base = pd.DataFrame({"year": te["year"], "ten": np.minimum(te["tenure"], 24), "y": te["y"]}).groupby(["year", "ten"]).y.mean()
    all_rate = pd.DataFrame({"year": te["year"], "y": te["y"]}).groupby("year").y.mean()

    R = {"notices_read": int(len(pd.DataFrame([json.loads(l) for l in open(NOTICES)]))), "london_gazette_with_address": None,
         "linked_to_a_home_with_sales": int(has.sum()), "last_bought_before_the_death": int(len(owned)), "by_year_after": {}}
    R["london_gazette_with_address"] = int(len(has)); R["link_share"] = round(float(has.mean()), 3)
    rows_md = []
    for lag, lab in ((1, "the calendar year after the notice"), (2, "the year after that")):
        o = owned.copy()
        o["T"] = o.pub.dt.year + lag
        o = o[o["T"] <= 2018]
        still = (o.next < 0) | (o.next >= o["T"] * 12)        # not sold between the death and 1 January of year T
        o = o[still]
        sold = ((o.next >= o["T"] * 12) & (o.next < (o["T"] + 1) * 12)).to_numpy()
        ten = np.minimum(o["T"] - o.bought // 12, 24).astype(int)
        exp = np.array([base.get((int(T), int(k)), np.nan) for T, k in zip(o["T"], ten)])
        rng = np.random.default_rng(3); bs = [sold[rng.integers(0, len(sold), len(sold))].mean() for _ in range(2000)] if len(sold) else [np.nan]
        res = {"homes_still_in_the_same_hands": int(len(o)), "sold_in_the_year": int(sold.sum()),
               "share_sold": round(float(sold.mean()), 4) if len(sold) else None,
               "range": [round(float(np.percentile(bs, q)), 4) for q in (2.5, 97.5)],
               "same_tenure_homes_sell_at": round(float(np.nanmean(exp)), 4) if len(exp) else None,
               "all_homes_sell_at": round(float(np.mean([all_rate.get(int(T), np.nan) for T in o["T"]])), 4) if len(o) else None}
        if res["share_sold"] and res["same_tenure_homes_sell_at"]:
            res["times_same_tenure"] = round(res["share_sold"] / res["same_tenure_homes_sell_at"], 1)
        R["by_year_after"][lab] = res
        rows_md.append(f"| {lab.capitalize()} | {res['homes_still_in_the_same_hands']:,} | {100 * (res['share_sold'] or 0):.1f}% "
                       f"({100 * res['range'][0]:.1f} to {100 * res['range'][1]:.1f}) | {100 * (res['same_tenure_homes_sell_at'] or 0):.1f}% | "
                       f"{res.get('times_same_tenure', 0):.1f} |")
    # homes the model cannot see: no sale on record (since 1995) before the event. The sale records hold only
    # homes sold at least once, so a long-held home appears for the first time when it is sold. Notices that
    # match no sale record at all count as not sold (some are address mismatches, so the shares are lower bounds).
    n_all = n_all.merge(n[["id", "bought", "next"]], on="id", how="left")
    unseen = n_all[~(n_all.bought >= 0)].copy()
    unseen["next"] = unseen.next.fillna(-1)
    R["no_sale_on_record_before"] = {"homes": int(len(unseen))}
    rows_unseen = []
    for lag, lab in ((1, "the calendar year after the notice"), (2, "the year after that")):
        o = unseen.copy(); o["T"] = o.pub.dt.year + lag
        o = o[(o["T"] <= 2018) & ((o.next < 0) | (o.next >= o["T"] * 12))]
        sold = ((o.next >= o["T"] * 12) & (o.next < (o["T"] + 1) * 12)).to_numpy()
        rng = np.random.default_rng(3); bs = [sold[rng.integers(0, len(sold), len(sold))].mean() for _ in range(2000)] if len(sold) else [np.nan]
        R["no_sale_on_record_before"][lab] = {"homes_not_yet_sold": int(len(o)), "first_sold_in_the_year": int(sold.sum()),
                                              "share": round(float(sold.mean()), 4) if len(sold) else None,
                                              "range": [round(float(np.percentile(bs, q)), 4) for q in (2.5, 97.5)]}
        rows_unseen.append(f"| {lab.capitalize()} | {len(o):,} | {100 * (sold.mean() if len(sold) else 0):.1f}% "
                           f"({100 * np.percentile(bs, 2.5):.1f} to {100 * np.percentile(bs, 97.5):.1f}) |")
    by_end = unseen[unseen.pub.dt.year <= 2016]
    R["no_sale_on_record_before"]["sold_by_end_2019"] = round(float((by_end.next >= 0).mean()), 3) if len(by_end) else None

    # the product's own clock: the 12 months from the month the notice appears (a campaign can act on a notice
    # the week it is published; the model's calendar-year scoring misses homes sold before the next 1 January)
    n_all["pub_ym"] = n_all.pub.dt.year * 12 + n_all.pub.dt.month - 1
    R["from_the_notice"] = {}; rows_pub = []
    for lab, g in (("Homes the model covers (bought before)", n_all[n_all.bought >= 0]),
                   ("Homes with no sale on record before", n_all[~(n_all.bought >= 0)])):
        g = g[g.pub.dt.year <= 2017].copy(); g["next"] = g.next.fillna(-1)
        g = g[(g.next < 0) | (g.next >= g.pub_ym)]              # not already sold when the notice appears
        res = {"homes": int(len(g))}
        for m in (12, 24):
            sold = ((g.next >= g.pub_ym) & (g.next < g.pub_ym + m)).to_numpy()
            rng = np.random.default_rng(3); bs = [sold[rng.integers(0, len(sold), len(sold))].mean() for _ in range(2000)] if len(sold) else [np.nan]
            res[f"sold_within_{m}m"] = round(float(sold.mean()), 4) if len(sold) else None
            res[f"range_{m}m"] = [round(float(np.percentile(bs, q)), 4) for q in (2.5, 97.5)]
        R["from_the_notice"][lab] = res
        if len(g):
            rows_pub.append(f"| {lab} | {len(g):,} | {100 * res['sold_within_12m']:.1f}% ({100 * res['range_12m'][0]:.1f} to {100 * res['range_12m'][1]:.1f}) | "
                            f"{100 * res['sold_within_24m']:.1f}% ({100 * res['range_24m'][0]:.1f} to {100 * res['range_24m'][1]:.1f}) |")

    # how long after the death the home is sold (homes whose notice is old enough to see three years)
    o = owned[owned.dod_ym <= 2016 * 12]
    mo = np.where(o.next >= 0, o.next - o.dod_ym, 10**6)
    R["sold_within_months_of_death"] = {str(m): round(float((mo <= m).mean()), 3) for m in (6, 12, 18, 24, 36)} if len(o) else {}
    R["months_death_to_notice_median"] = float((n.pub_ym - n.dod_ym).median())

    # what it could be worth: every notice in a year, if the model put these homes in its best tenth
    st = json.load(open(STATE)) if STATE.exists() else {"lists": {}}
    days = [len(v) for k, v in st["lists"].items() if k.split("..")[0] == k.split("..")[1]]
    per_year = float(np.mean(days)) * 253 if days else None
    first = R["by_year_after"].get("the calendar year after the notice", {})
    if per_year and first.get("share_sold"):
        homes_at_risk = len(te["y"][te["year"] == 2017]) * 10          # the test chunks are a tenth of all homes
        sales = float(te["y"][te["year"] == 2017].mean()) * homes_at_risk
        found = per_year * (len(owned) / max(len(has), 1)) * first["share_sold"]
        R["scale"] = {"notices_a_year": round(per_year), "homes_at_risk": int(homes_at_risk), "sales_a_year": round(sales),
                      "sellers_these_notices_point_to_a_year": round(found),
                      "share_of_all_sellers": round(found / sales, 4)}
    json.dump(R, open(OUT / f"{EVENT[3]}.json", "w"), indent=1)
    md = [f"# {EVENT[2]}: do the homes sell?", "",
          f"A sample of {R['notices_read']:,} notices from The Gazette. {R['london_gazette_with_address']:,} are for England and Wales with an address; "
          f"{R['linked_to_a_home_with_sales']:,} ({100 * R['link_share']:.0f}%) match a home with a sale record, and "
          f"{R['last_bought_before_the_death']:,} of those were last bought before the {EVENT[1]}.", "",
          "| Year scored | Homes still in the same hands | Sold in that year (95% range) | Homes owned as long sell at | Times |",
          "|---|---|---|---|---|", *rows_md, "",
          f"Sold within so many months of the {EVENT[1]}: " + ", ".join(f"{m} months {100 * v:.0f}%" for m, v in R["sold_within_months_of_death"].items()) + ".",
          f"The notice appears a median of {R['months_death_to_notice_median']:.0f} months after the {EVENT[1]}.", ""]
    md += ["## Homes with no sale on record before", "",
           f"{R['no_sale_on_record_before']['homes']:,} notices are for homes with no sale since 1995 before the {EVENT[1]}. "
           "The model does not cover these homes: the sale records hold a home only once it has been sold.", "",
           "| Year | Homes not yet sold | First sold in that year (95% range) |", "|---|---|---|", *rows_unseen, "",
           f"Sold by the end of 2019 (notices to 2016): {100 * (R['no_sale_on_record_before']['sold_by_end_2019'] or 0):.0f}%. "
           "Lower bounds: an address that fails to match counts as not sold.", ""]
    md += ["## From the month the notice appears", "",
           "The product can act on a notice when it is published, so this is its own clock. All homes sell at about 4.4% a year.", "",
           "| Homes | Not yet sold when the notice appears | Sold within 12 months (95% range) | Sold within 24 months |", "|---|---|---|---|", *rows_pub, ""]
    if "scale" in R:
        s = R["scale"]
        md += [f"Scale: about {s['notices_a_year']:,} notices a year point to about {s['sellers_these_notices_point_to_a_year']:,} "
               f"sellers in the following year, {100 * s['share_of_all_sellers']:.1f}% of all sellers among homes with a sale record.", ""]
    (OUT / f"{EVENT[3]}.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
