"""Which later sellers were already on the market on the day they were scored?

A sale completing between July of the year and June of the next is the model's stand-in for a
home that was not yet listed on 1 January. Most were not, but a slow sale can have been listed
before that day, and a fresh sale certificate is exactly what finds those. This works out, for
every test home that went on to sell, when the certificate for that sale was lodged, so the
homes already on the market can be told from the homes about to come to it. It looks forward
from the scoring day (it is a label, never a signal).

  Exact. The home's UPRN is known by the time of the sale: the latest sale certificate on it,
  lodged while the seller owned it, dates the listing.

  By postcode. Otherwise: sale certificates for that kind of home in the postcode in the 18
  months up to the sale, less one for each other sale there in that time (earliest first).
  What is left are the candidates for this sale; the share of them lodged on or after the
  scoring day is the chance the home was not yet listed.

  A sale with no fresh certificate reused an older one. Its listing date cannot be known, and
  no certificate signal can have found it, so it stays a later seller.

Written beside the panel for the test rows (as local_eval.load_test orders them):
  test_listed_after.npy   1 = not yet listed on the scoring day, 0 = already listed, between = share
  test_list_ym.npy        the month the certificate for the sale was lodged, where exact (else 0)
  test_EPC2.npy           the columns of epc2_signals.py for the same rows (screen_facts.py, stack_late.py)

    python listed_truth.py
"""
import json

import numpy as np

import epc2_signals as E2
import epc_signals as ES
import local_eval as LE
import screen_catb as SC
import screen_late as SL

PANEL, OUT = SL.PANEL, SL.OUT
M = ES.M


def main():
    from panel2 import Panel
    panel = Panel(SL.TX, verbose=False)
    e = ES.Epc(panel, panel.month)
    rows = SC.test_rows(); t = LE.load_test(PANEL); years = t["year"].astype(np.int64)
    assert len(rows) == len(years)
    n = len(panel.key); s = np.minimum(rows + 1, n - 1)              # the sale that ends the spell (rows are sorted by home, then date)
    sold = panel.sold[rows] & (panel.key[s] == panel.key[rows])
    t0 = years * 12; g = e.g[rows]; bought = e.ym[rows]; sale = np.where(sold, e.ym[s], 0)
    lo = np.maximum(bought + 1, sale - 18)

    # exact: the home's UPRN is known at the sale
    u = np.where(sold, e.spell_u[s], -1); ex = u >= 0
    m = E2._latest(e.u_key, (u[ex] * 4 + 0) * M, bought[ex] + 1, sale[ex] + 1)
    list_ym = np.zeros(len(rows), np.int64); list_ym[ex] = np.maximum(m, 0)
    reused = np.zeros(len(rows), bool); reused[ex] = m < 0           # known home, no fresh certificate: an older one was reused

    # by postcode: candidates left after the other sales there have taken theirs
    sel = e.c_k == 0
    key = np.sort(e.c_g[sel] * M + e.c_ym[sel])
    skey = np.sort(e.g * M + e.ym)
    cut = np.clip(t0, lo, sale + 1)
    pre = ES._win(key, g * M, lo, cut); post = ES._win(key, g * M, cut, sale + 1)
    other = ES._win(skey, g * M, lo, sale)                            # other sales there before this one's month
    avail = pre + post - other
    frac = np.ones(len(rows), np.float32)
    amb = sold & ~ex & (avail > 0)
    frac[amb] = np.minimum(post[amb], avail[amb]) / avail[amb]
    known = sold & ex & (list_ym > 0)
    frac[known] = (list_ym[known] >= t0[known]).astype(np.float32)
    frac[~sold] = 1
    np.save(PANEL / "test_listed_after.npy", frac); np.save(PANEL / "test_list_ym.npy", list_ym.astype(np.int32))

    ym = SL.end_ym(); late = (ym >= t0 + 6) & (ym < t0 + 18) & (years <= 2018)
    R = {"later_sellers": int(late.sum()), "bands": {}}
    for nm, a, b in LE.TENURE:
        k = late & (t["tenure"] >= a) & (t["tenure"] < b)
        lag = (sale - list_ym)[k & known]
        R["bands"][nm] = {
            "later_sellers": int(k.sum()),
            "exact_listing_date": round(float((k & known).sum() / k.sum()), 4),
            "exact_and_already_listed": round(float((k & known & (list_ym < t0)).sum() / max((k & known).sum(), 1)), 4),
            "home_known_certificate_reused": round(float((k & reused).sum() / k.sum()), 4),
            "by_postcode": round(float((k & amb).sum() / k.sum()), 4),
            "no_fresh_certificate_in_postcode": round(float((k & ~ex & (avail <= 0)).sum() / k.sum()), 4),
            "not_yet_listed_share": round(float(frac[k].mean()), 4),
            "months_certificate_to_completion": [int(v) for v in np.percentile(lag, (10, 25, 50, 75, 90))] if len(lag) else None}
        print(nm, R["bands"][nm], flush=True)
    lag = (sale - list_ym)[known & (years <= 2018)]
    R["share_completing_more_than_n_months_after_certificate"] = {str(q): round(float((lag > q).mean()), 4) for q in (3, 6, 9, 12, 18)}
    print(R["share_completing_more_than_n_months_after_certificate"], flush=True)
    json.dump(R, open(OUT / "LISTED_TRUTH.json", "w"), indent=1)

    X = E2.Epc2(e).features(rows, t["year"])
    np.save(PANEL / "test_EPC2.npy", X); json.dump(E2.COLS, open(PANEL / "test_EPC2.json", "w"))
    print("columns of epc2_signals written for", len(X), "rows; stated:", {c: round(float(np.isfinite(X[:, i]).mean()), 3) for i, c in enumerate(E2.COLS)}, flush=True)
    print("=== finished", flush=True)


if __name__ == "__main__":
    main()
