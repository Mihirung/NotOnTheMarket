"""Will buyers get responses, and how much postage is at risk?

The propensity model multiplies the response rate. It does not set it.
This script separates those two things and shows which one actually
decides the business:

  1. Break-even — the scan rate at which a campaign pays for itself,
     given the model lift we measured.
  2. Sensitivity — conversations and cost per completed sale across the
     plausible range of response rates, since that range is far wider
     than any uncertainty in the model.
  3. Wave protocol — how much money a sequential test-and-stop mailing
     strategy puts at risk versus one large campaign.
  4. Buyer experience — the probability a buyer sees nothing at all,
     under per-buyer campaigns versus a continuously-canvassed pool of
     already-warm sellers.

Every assumption is a named constant. Nothing here is measured; the
pilot exists to measure it. Usage:
    python response_economics.py <out_dir> [model_lift_top_decile]
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

CARD_COST = 0.72        # £, print + post at volume
TALK_GIVEN_SCAN = 0.33  # scanners who open a conversation
AGREE_GIVEN_TALK = 0.15 # conversations reaching an agreed price
COMPLETE_GIVEN_AGREE = 0.70  # agreed sales that complete
NET_REVENUE = 5000.0    # £ net fee per completed sale
OPS_PER_DEAL = 1200.0   # £ progression cost per completed sale

INK = "#20282E"; MUTED = "#5A646D"; GRID = "#DBD8CC"
TEAL = "#275E54"; TEAL_MID = "#4E9484"; TEAL_LT = "#8FC3B6"; RUST = "#C33D2E"


def per_completion(scan, lift):
    """Cards needed per completed sale at a given base scan rate."""
    p = scan * lift * TALK_GIVEN_SCAN * AGREE_GIVEN_TALK * COMPLETE_GIVEN_AGREE
    return np.inf if p <= 0 else 1.0 / p


def breakeven_scan(lift):
    """Scan rate where postage per completion equals net contribution."""
    budget = NET_REVENUE - OPS_PER_DEAL            # £ available for postage
    cards_affordable = budget / CARD_COST
    return 1.0 / (cards_affordable * lift * TALK_GIVEN_SCAN
                  * AGREE_GIVEN_TALK * COMPLETE_GIVEN_AGREE)


def wave_protocol(scan, lift, waves=(2000, 5000, 12000, 30000),
                  min_talks_per_1000=4.0, rng=None):
    """Sequential mailing that stops when a wave under-performs.

    Returns total cards mailed and whether the campaign was abandoned.
    The stopping rule is deliberately crude — it is the discipline, not
    the cleverness, that caps the loss.
    """
    rng = rng or np.random.default_rng(0)
    rate = scan * lift * TALK_GIVEN_SCAN
    total = 0
    for n in waves:
        talks = rng.poisson(n * rate)
        total += n
        if talks / (n / 1000) < min_talks_per_1000:
            return total, True
    return total, False


def main(out_dir, lift=1.59):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    res = {"assumptions": {
        "card_cost_gbp": CARD_COST, "talk_given_scan": TALK_GIVEN_SCAN,
        "agree_given_talk": AGREE_GIVEN_TALK,
        "complete_given_agree": COMPLETE_GIVEN_AGREE,
        "net_revenue_per_sale_gbp": NET_REVENUE,
        "ops_per_deal_gbp": OPS_PER_DEAL, "model_lift_top_decile": lift}}

    # ---- 1. break-even ---------------------------------------------------
    be = breakeven_scan(lift)
    be_untargeted = breakeven_scan(1.0)
    res["breakeven_scan_rate_pct"] = round(100 * be, 3)
    res["breakeven_scan_rate_untargeted_pct"] = round(100 * be_untargeted, 3)
    print(f"break-even scan rate: {100*be:.2f}% targeted "
          f"({100*be_untargeted:.2f}% untargeted)")

    # ---- 2. sensitivity across plausible response rates ------------------
    scans = np.array([0.005, 0.010, 0.015, 0.024, 0.035, 0.050])
    table = []
    for s in scans:
        cards = per_completion(s, lift)
        table.append({
            "base_scan_pct": round(100 * s, 1),
            "effective_scan_pct": round(100 * s * lift, 2),
            "talks_per_1000_cards": round(1000 * s * lift * TALK_GIVEN_SCAN, 1),
            "cards_per_completion": int(cards),
            "postage_per_completion_gbp": int(cards * CARD_COST),
            "contribution_per_sale_gbp": int(NET_REVENUE - OPS_PER_DEAL
                                             - cards * CARD_COST),
        })
    res["sensitivity"] = table
    for r in table:
        print(f"  scan {r['base_scan_pct']:>4}% -> {r['talks_per_1000_cards']:>5} "
              f"talks/1k, £{r['postage_per_completion_gbp']:>6}/sale, "
              f"contribution £{r['contribution_per_sale_gbp']:>6}")

    # ---- 3. wave protocol: money actually at risk ------------------------
    rng = np.random.default_rng(7)
    protocol = {}
    for s in (0.005, 0.010, 0.024):
        spends, abandoned = [], 0
        for _ in range(2000):
            total, stopped = wave_protocol(s, lift, rng=rng)
            spends.append(total * CARD_COST)
            abandoned += stopped
        protocol[f"scan_{100*s:.1f}pct"] = {
            "median_spend_gbp": int(np.median(spends)),
            "p95_spend_gbp": int(np.percentile(spends, 95)),
            "abandon_rate": round(abandoned / 2000, 3)}
    res["wave_protocol"] = protocol
    res["single_campaign_spend_gbp"] = int(49000 * CARD_COST)
    print("\nwave protocol vs one 49,000-card campaign "
          f"(£{res['single_campaign_spend_gbp']:,}):")
    for k, v in protocol.items():
        print(f"  {k}: median £{v['median_spend_gbp']:,}, "
              f"p95 £{v['p95_spend_gbp']:,}, abandoned {v['abandon_rate']:.0%}")

    # ---- 4. buyer experience: silence risk is a brief-width problem ------
    # A buyer's own campaign can only mail the top-band homes matching
    # their brief. Narrow brief -> few cards -> a real chance of total
    # silence, whatever the scan rate. Continuous city-wide canvassing
    # decouples the two: the buyer arrives to sellers already warm.
    sizes = np.array([50, 100, 200, 400, 800, 1600, 3200])
    exp = {"solo_p_nothing_by_cohort_size": {}}
    for s in (0.005, 0.010, 0.024):
        rate = s * lift * TALK_GIVEN_SCAN
        exp["solo_p_nothing_by_cohort_size"][f"scan_{100*s:.1f}pct"] = {
            int(n): round(float(np.exp(-n * rate)), 3) for n in sizes}
        monthly_cards = 6000              # continuous city-level canvassing
        # Warm sellers accumulated over 3 months, of which a given brief
        # matches roughly a fifth.
        pool_stock = monthly_cards * rate * 3 * 0.20
        exp[f"pooled_scan_{100*s:.1f}pct"] = {
            "matching_sellers_waiting": round(pool_stock, 1),
            "p_nothing": round(float(np.exp(-pool_stock)), 4)}
    res["buyer_experience"] = exp
    print("\nchance a buyer's own campaign returns total silence:")
    print("  cohort:  " + "".join(f"{n:>7}" for n in sizes))
    for s in (0.005, 0.010, 0.024):
        row = exp["solo_p_nothing_by_cohort_size"][f"scan_{100*s:.1f}pct"]
        print(f"  {100*s:>4.1f}%:  " + "".join(f"{100*row[int(n)]:>6.0f}%" for n in sizes))
    for s in (0.005, 0.010, 0.024):
        v = exp[f"pooled_scan_{100*s:.1f}pct"]
        print(f"  pooled @ {100*s:.1f}%: {v['matching_sellers_waiting']} waiting, "
              f"silence {v['p_nothing']:.2%}")

    # ---- charts ----------------------------------------------------------
    fig, ax = plt.subplots(1, 3, figsize=(14.5, 4.3))

    # (a) postage per completion vs scan rate, with break-even marked
    xs = np.linspace(0.003, 0.05, 300)
    ys = np.array([per_completion(x, lift) * CARD_COST for x in xs])
    ax[0].plot(100 * xs, ys, color=TEAL, lw=2.5)
    ax[0].axhline(NET_REVENUE - OPS_PER_DEAL, color=RUST, ls="--", lw=2)
    ax[0].text(3.4, (NET_REVENUE - OPS_PER_DEAL) * 1.08,
               f"£{int(NET_REVENUE-OPS_PER_DEAL):,} available per sale",
               color=RUST, fontsize=9.5)
    ax[0].axvline(100 * be, color=MUTED, ls=":", lw=1.8)
    ax[0].text(100 * be + .18, 500, f"break-even {100*be:.2f}%",
               color=MUTED, fontsize=9.5)
    ax[0].set_yscale("log")
    ax[0].set_xlabel("Base scan rate (%)")
    ax[0].set_ylabel("Postage per completed sale (£)")
    ax[0].set_title("The rate that decides it", color=INK)
    ax[0].grid(alpha=.25, color=GRID)

    # (b) money at risk: waves vs one big campaign
    labels = ["0.5%", "1.0%", "2.4%"]
    med = [protocol[f"scan_{float(l[:-1]):.1f}pct"]["median_spend_gbp"] for l in labels]
    p95 = [protocol[f"scan_{float(l[:-1]):.1f}pct"]["p95_spend_gbp"] for l in labels]
    xs2 = np.arange(3); w = .36
    cap = res["single_campaign_spend_gbp"]
    ax[1].bar(xs2 - w/2, med, w, color=TEAL_MID, label="median spend")
    ax[1].bar(xs2 + w/2, p95, w, color=TEAL_LT, label="95th percentile")
    ax[1].axhline(cap, color=RUST, ls="--", lw=2)
    ax[1].text(-0.48, cap * .82, f"one 49,000-card\ncampaign: £{cap:,}",
               color=RUST, fontsize=9.5, ha="left", va="top")
    ax[1].set_ylim(0, cap * 1.12)
    for i, lab in enumerate(labels):
        if i == 0:  # only the abandoned case needs its value spelled out
            ax[1].text(i - w/2, med[i] + cap * .02, f"£{med[i]/1000:.1f}k",
                       ha="center", fontsize=9)
        ab = protocol[f"scan_{float(lab[:-1]):.1f}pct"]["abandon_rate"]
        ax[1].text(i, -cap * .10, f"stops early {ab:.0%}", ha="center",
                   fontsize=8.5, color=MUTED)
    ax[1].set_xticks(xs2); ax[1].set_xticklabels(labels)
    ax[1].set_xlabel("If the true scan rate turns out to be…", labelpad=18)
    ax[1].set_ylabel("Postage spent (£)")
    ax[1].set_title("A bad campaign gets caught for £1.4k", color=INK)
    ax[1].legend(frameon=False, fontsize=9, loc="center left")
    ax[1].grid(alpha=.25, axis="y", color=GRID)

    # (c) silence risk is driven by how narrow the buyer's brief is
    cols = {"0.5": RUST, "1.0": TEAL_MID, "2.4": TEAL}
    for lab, colour in cols.items():
        rate = (float(lab) / 100) * lift * TALK_GIVEN_SCAN
        ax[2].plot(sizes, 100 * np.exp(-sizes * rate), color=colour, lw=2.5,
                   marker="o", ms=5, label=f"{lab}% scan")
    ax[2].axhline(20, color=MUTED, ls=":", lw=1.8)
    ax[2].text(52, 22.5, "1 buyer in 5 hears nothing", color=MUTED, fontsize=9)
    ax[2].set_xscale("log")
    ax[2].set_xticks(sizes)
    ax[2].set_xticklabels([str(int(n)) for n in sizes])
    ax[2].set_xlabel("Homes matching the buyer's brief (top band, mailed)")
    ax[2].set_ylabel("Chance the buyer hears nothing (%)")
    ax[2].set_title("Narrow briefs, not low response, are the risk", color=INK)
    ax[2].legend(frameon=False, fontsize=9); ax[2].grid(alpha=.25, color=GRID)

    fig.tight_layout(); fig.savefig(out / "response_economics.png", dpi=140)
    plt.close(fig)

    with open(out / "response_economics.json", "w") as fh:
        json.dump(res, fh, indent=1)
    print(f"\nwrote {out}/response_economics.json")


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 1.59)
