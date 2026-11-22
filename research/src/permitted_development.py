"""What could be built at each house without planning permission, and what
it might add in value.

Householder permitted development (the General Permitted Development Order,
Schedule 2 Part 1, in England; its Welsh counterpart in Wales) lets the
owner of a house, not a flat, extend within set limits without applying.
This applies the main limits to every house of the national run, using:

  the house's type      from its building outline (house_plot.py): standing
                        alone (detached), joined on one side to one other
                        (semi-detached), or joined in a row (terraced; an end
                        of terrace counts as terraced for loft volume)
  the room around it    rear gap and side gaps to the next building; rear
                        gardens meet back to back, so the garden is taken as
                        half the rear gap, up to 30 m
  where it stands       planning_constraints.py: listed buildings have no
                        permitted development; conservation areas, protected
                        landscapes, National Parks and World Heritage Sites
                        ('article 2(3) land') rule out side extensions,
                        two-storey rear extensions, roof extensions and the
                        larger rear extensions; Article 4 directions remove
                        the rights they name

Rules applied (England unless marked):
  rear, single storey   up to 3 m deep (4 m detached); up to 6 m (8 m
                        detached) after a prior-approval notice, England
                        only and not on article 2(3) land; never more than
                        half the garden (the 50% coverage rule)
  rear, two storey      3 m deep, at least 7 m from the rear boundary, not
                        on article 2(3) land
  side, single storey   up to half the house's width, where there is a gap
                        beside it, not on article 2(3) land
  loft (roof extension) 40 m3 (terraced) or 50 m3 (others) of new roof,
                        not on article 2(3) land or under an Article 4 for
                        roofs
  garden building       where the garden is at least 6 m deep; on protected
                        landscapes, National Parks and World Heritage Sites
                        smaller where far from the house

Floor area added is estimated from the house's width (footprint over depth)
and the allowed depth; a loft adds about half the footprint, up to 30 m2.
The signal is the single biggest job (what most owners weigh); every
allowance used at once is kept beside it as an upper limit.
Value added = floor area x the postcode's price per m2 x 0.7, the share of
average price per m2 that extra space usually fetches; this factor is an
assumption until the planning sample (planit_fetch.py) measures it. These
are estimates for search and conversation: real allowances depend on the
original house (earlier extensions use them up), boundaries and design.

Writes research/outputs/national/pd/<cell>.parquet per house and
research/data/signals/pd_postcode.parquet (the PD signal family).

Usage: python permitted_development.py [cells...]
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from planning_constraints import BITS  # noqa: E402

NAT = Path("research/outputs/national")
PCON = Path("research/data/planning/constraints_positions.parquet")
ALPHA = 0.7                                       # value of an extra m2 relative to the average m2 (assumption)
WALES = {"Isle of Anglesey", "Gwynedd", "Conwy", "Denbighshire", "Flintshire", "Wrexham", "Ceredigion",
         "Pembrokeshire", "Carmarthenshire", "Swansea", "Neath Port Talbot", "Bridgend", "Vale of Glamorgan",
         "Cardiff", "Rhondda Cynon Taf", "Caerphilly", "Blaenau Gwent", "Torfaen", "Monmouthshire", "Newport",
         "Powys", "Merthyr Tydfil"}
REASON = {0: "", 1: "a flat or shared building", 2: "listed", 3: "Article 4 removes extension rights",
          4: "no room at the back"}


def bit(b, name):
    return ((b >> BITS[name]) & 1).astype(bool)


def values():
    """Each postcode's typical house value at 2019 prices and its sector's, from
    sales of houses 2010-2019 brought to 2019 by their district's price index."""
    tx = pd.read_parquet("research/data/transactions.parquet",
                         columns=["key", "year", "price", "ptype", "postcode", "outcode"])
    tx = tx[(tx.year >= 2010) & tx.ptype.isin(["D", "S", "T"])]
    med = tx.groupby(["outcode", "year"], observed=True).price.median()
    idx = (med / med.xs(2019, level="year").reindex(med.index.get_level_values(0)).to_numpy()).rename("f")
    tx = tx.join(idx, on=["outcode", "year"])
    tx["v2019"] = tx.price / tx.f.where(tx.f > 0)
    last = tx.sort_values("year").drop_duplicates("key", keep="last")
    last["postcode"] = last.postcode.astype(str)
    pc = last.groupby("postcode").v2019.median()
    sec = last.assign(sector=last.postcode.str[:-2]).groupby("sector").v2019.median()
    return pc, sec


def country():
    from export_site_v5 import lad_names
    lad = lad_names()
    return pd.Series(np.where(lad.isin(WALES).to_numpy(), "W", "E"), index=lad.index)


def assess(h):
    """The permitted development rules for a table of houses."""
    b = h.bits.to_numpy(np.uint16)
    flat = h.n_uprn.to_numpy() > 1
    l_gap, r_gap = h.side_gap_l_m.to_numpy(), h.side_gap_r_m.to_numpy()
    joined = (l_gap < 0.5).astype(int) + (r_gap < 0.5).astype(int)
    n_on = np.maximum(h.n_on_outline.to_numpy(), 1)
    # A pair of semis or a terrace is often one outline: the number of addresses on the outline decides;
    # a house alone on its outline is detached unless it touches the next outline (separately drawn terraces)
    kind = np.where(flat, "F", np.where(n_on >= 3, "T", np.where(n_on == 2, "S",
                    np.where(joined == 0, "D", np.where(joined == 1, "S", "T")))))
    listed = bit(b, "listed")
    a23 = bit(b, "conservation") | bit(b, "landscape") | bit(b, "national_park") | bit(b, "world_heritage")
    a4_ext = bit(b, "a4_extension"); a4_roof = bit(b, "a4_roof")
    a4_any = bit(b, "a4_house") & ~a4_ext & ~a4_roof      # rights removed, classes not stated
    wales = h.country.to_numpy() == "W"
    rear = h.rear_gap_m.to_numpy()
    garden = np.where(rear >= 59.5, 30.0, np.clip(rear / 2, 0, 30))
    garden = np.where(h.has_garden.to_numpy(), garden, 0.0)
    depth = np.clip(np.nan_to_num(h.depth_m.to_numpy(float), nan=8.0), 5, 20)
    width = np.clip(h.footprint_m2.to_numpy() / depth, 3.5, 15)
    house_ok = ~flat & ~listed
    ext_ok = house_ok & ~a4_ext
    det = kind == "D"
    base = np.where(det, 4.0, 3.0)
    big = np.where(det, 8.0, 6.0)
    half = 0.5 * garden                                   # the 50% coverage rule, on the back garden alone
    rear_pd = np.where(ext_ok, np.minimum(base, half), 0.0)
    rear_pd = np.where(rear_pd >= 1.5, rear_pd, 0.0)
    rear_pa = np.where(ext_ok & ~a23 & ~wales, np.minimum(big, half), 0.0)
    rear_pa = np.where(rear_pa > rear_pd + 0.5, rear_pa, rear_pd)
    two = ext_ok & ~a23 & (h.storeys.to_numpy() >= 2) & (garden >= 10)
    side_gap = np.maximum(l_gap, r_gap)
    side = ext_ok & ~a23 & (kind != "T") & (side_gap >= 2.0)
    loft = house_ok & ~a23 & ~a4_roof & (h.storeys.to_numpy() <= 3)
    outb = house_ok & (garden >= 6)
    # floor area each could add, and the best combination (a rear extension and a loft can both be done)
    m2_rear = rear_pa * width * 0.9
    m2_two = np.where(two, 3.0 * width * 0.9 * 2, 0.0)
    m2_side = np.where(side, np.minimum(side_gap - 1.0, width / 2) * depth * 0.9, 0.0)
    m2_loft = np.where(loft, np.minimum(0.5 * h.footprint_m2.to_numpy(), 30.0), 0.0)
    m2_all = np.maximum(m2_rear, m2_two) + m2_loft + m2_side          # every allowance used at once: an upper limit
    jobs = np.column_stack([m2_rear, m2_two, m2_loft, m2_side])        # the single biggest job is what most owners weigh
    best = jobs.argmax(axis=1)
    m2_best = jobs.max(axis=1)
    reason = np.where(flat, 1, np.where(listed, 2, np.where(a4_ext, 3, np.where(rear_pd == 0, 4, 0))))
    return pd.DataFrame({
        "h3": h.h3.to_numpy(), "pd_kind": kind, "pd_rear_m": rear_pd.round(1).astype("float32"),
        "pd_rear_prior_m": rear_pa.round(1).astype("float32"), "pd_two_storey": two, "pd_side": side,
        "pd_loft": loft, "pd_garden_building": outb, "pd_check_a4": a4_any & house_ok,
        "pd_heritage_limits": a23 & house_ok, "pd_reason": reason.astype("int8"),
        "in_conservation": bit(b, "conservation"), "listed": listed, "green_belt": bit(b, "green_belt"),
        "add_m2": np.round(m2_best, 0).astype("float32"),
        "best_job": np.where(m2_best > 0, np.array(["rear", "two_storey", "loft", "side"])[best], ""),
        "add_m2_all": np.round(m2_all, 0).astype("float32"),
        "floor_m2": np.round(h.footprint_m2.to_numpy() * np.clip(h.storeys.to_numpy(), 1, 4) * 0.85, 0).astype("float32"),
        "garden_depth_m": garden.astype("float32")})


def main(cells):
    t0 = time.time()
    out_dir = NAT / "pd"; out_dir.mkdir(exist_ok=True)
    pc_val, sec_val = values()
    ctry = country()
    pcon = pd.read_parquet(PCON)
    pcon = pcon.set_index(["x", "y"]).bits
    if not cells:
        cells = sorted(p.stem for p in (NAT / "plots").glob("*.parquet"))
    rows = []
    import pyarrow.parquet as pq
    for k, cell in enumerate(cells):
        if "storeys" not in pq.read_schema(NAT / "cells" / f"{cell}.parquet").names:
            continue                                  # no houses in this cell
        h = pd.read_parquet(NAT / "cells" / f"{cell}.parquet",
                            columns=["x", "y", "h3", "postcode", "n_uprn", "storeys", "has_garden", "depth_m"])
        if not len(h):
            continue
        h = h.merge(pd.read_parquet(NAT / "plots" / f"{cell}.parquet"), on="h3", how="left")
        h["bits"] = pcon.reindex(pd.MultiIndex.from_arrays([h.x, h.y])).fillna(0).to_numpy().astype(np.uint16)
        h["postcode"] = h.postcode.astype(str)
        h["country"] = ctry.reindex(h.postcode).fillna("E").to_numpy()
        h["n_on_outline"] = h.n_on_outline.fillna(0)
        for c in ("rear_gap_m", "side_gap_l_m", "side_gap_r_m"):
            h[c] = h[c].fillna(0.0)
        h["footprint_m2"] = h.footprint_m2.fillna(60.0)
        r = assess(h)
        r["postcode"] = h.postcode.to_numpy(); r["n_uprn"] = h.n_uprn.to_numpy()
        # price per m2 from the postcode's typical value and its houses' typical floor area
        houses = r[r.pd_kind != "F"]
        fa = houses.groupby("postcode").floor_m2.median()
        v = pc_val.reindex(fa.index)
        v = v.fillna(sec_val.reindex(fa.index.str[:-2]).set_axis(fa.index))
        ppm = (v / fa.clip(lower=30)).clip(500, 25_000)
        r["price_m2"] = ppm.reindex(r.postcode).to_numpy().astype("float32")
        r["value_2019"] = v.reindex(r.postcode).to_numpy().astype("float32")
        r["add_value"] = np.round(r.add_m2 * r.price_m2 * ALPHA, -3).astype("float32")
        r["add_value_all"] = np.round(r.add_m2_all * r.price_m2 * ALPHA, -3).astype("float32")
        r["add_pct"] = (r.add_value / r.value_2019).astype("float32")
        tmp = out_dir / f"{cell}.tmp"
        r.drop(columns=["postcode", "n_uprn"]).to_parquet(tmp, index=False); tmp.replace(out_dir / f"{cell}.parquet")
        rows.append(r.assign(w=h.n_uprn.to_numpy(float)))
        if k % 100 == 0:
            print(f"  {k + 1} of {len(cells)} cells, {time.time() - t0:.0f}s", flush=True)
    a = pd.concat(rows, ignore_index=True)
    a["is_flat"] = (a.pd_kind == "F") * a.w; a["is_listed"] = (a.pd_reason == 2) * a.w
    hs = a[a.pd_kind != "F"].assign(rear_any=lambda x: x.pd_rear_m > 0)
    g = hs.groupby("postcode")
    t = pd.DataFrame({
        "pd_houses": g.size(), "pd_rear_share": g.rear_any.mean(), "pd_rear_prior_m": g.pd_rear_prior_m.mean(),
        "pd_loft_share": g.pd_loft.mean(), "pd_two_storey_share": g.pd_two_storey.mean(),
        "pd_side_share": g.pd_side.mean(), "pd_heritage_share": g.pd_heritage_limits.mean(),
        "pd_add_m2": g.add_m2.median(), "pd_add_pct": g.add_pct.median(), "price_m2": g.price_m2.median()})
    s_ = a.groupby("postcode")[["is_flat", "is_listed", "w"]].sum()
    t = t.join(pd.DataFrame({"flat_share": s_.is_flat / s_.w, "listed_share": s_.is_listed / s_.w}), how="outer")
    t = t.astype("float32").reset_index().rename(columns={"index": "postcode"})
    Path("research/data/signals").mkdir(parents=True, exist_ok=True)
    t.to_parquet("research/data/signals/pd_postcode.parquet", index=False)
    print(f"{len(a):,} homes assessed; {len(t):,} postcodes; houses with a permitted rear extension "
          f"{(hs.pd_rear_m > 0).mean():.1%}, a loft {hs.pd_loft.mean():.1%}; the biggest single job adds a median "
          f"{hs.add_m2.median():.0f} m2 (every allowance at once {hs.add_m2_all.median():.0f} m2), worth a median "
          f"£{hs.add_value.median():,.0f}; biggest job: {hs.best_job.value_counts(normalize=True).round(3).to_dict()}; "
          f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
