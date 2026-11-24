"""Does averaging several fits beat one fit? And how do the new families look against more than one baseline fit?

SEED_NOISE showed two fits of the deployed model differ by up to 0.02 in the best-tenth lift, and the
deployed fit (seed 7) is the luckiest of three. So:

  1. Average the three fits of the deployed model (seeds 7, 8, 9). Averaging removes most of the
     fit-to-fit noise and often lifts the score a little. If it beats the deployed fit, it is a free gain.
  2. Average the deployed fits with every new-family fit (all saved). Different inputs make different
     mistakes, so a blend can beat each part even when no single family does.
  3. Judge each family against the mean of the three baseline fits, with the seed spread added to the
     range, instead of against the one lucky fit.

Nothing is refitted: every prediction is cached in research/outputs/lab/preds.

    python seed_ensemble.py

Writes research/outputs/signals/ENSEMBLE.json and .md.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

import assess_signal as A  # noqa: E402
import local_eval as LE  # noqa: E402

LAB, OUT = Path(A.LAB) / "preds", Path(A.OUT)
SEEDS = [7, 8, 9]
FAMILIES = ["LIFE", "PEOPLE", "STOCK", "SCHOOLS", "ACCESS", "CRIME", "COMMUNITY"]


def load(key):
    return np.load(LAB / f"{key}.npy").astype(np.float64)


def rank01(p):
    """Rank within the test homes so fits on slightly different scales average fairly."""
    r = np.empty(len(p)); r[np.argsort(p, kind="stable")] = np.arange(len(p))
    return r / len(p)


def main():
    t = LE.load_test(A.PANEL)
    key = f"{A.CUR_NAME}@100"
    base = {s: load(key + ("" if s == 7 else f"~s{s}")) for s in SEEDS}
    fam = {f: load(f"{A.CUR_NAME}+{f}@100") for f in FAMILIES}
    preds = {f"fit seed {s}": base[s] for s in SEEDS}
    preds["average of 3 fits"] = np.mean([base[s] for s in SEEDS], axis=0)
    preds["average of 3 fits (ranks)"] = np.mean([rank01(base[s]) for s in SEEDS], axis=0)
    preds["3 fits + 7 family fits"] = np.mean([base[s] for s in SEEDS] + list(fam.values()), axis=0)
    preds["3 fits + 4 clean families"] = np.mean([base[s] for s in SEEDS] + [fam[f] for f in ("STOCK", "SCHOOLS", "ACCESS", "CRIME")], axis=0)
    for f in FAMILIES:
        preds[f"family {f}"] = fam[f]

    R, rows = {"deployed": A.CUR_NAME, "seeds": SEEDS, "results": {}}, []
    for name, lo, hi in LE.TENURE:
        L = LE.Local(t, lo, hi)
        masks = {k: L.top_mask(p[L.keep]) for k, p in preds.items()}
        lifts = {k: L.lift(m) for k, m in masks.items()}
        rng = np.random.default_rng(3)
        boots = {k: [] for k in preds}
        for _ in range(A.BOOT):
            w = rng.poisson(1.0, LE.N_BLOCKS).astype(float)[L.block]
            for k, m in masks.items():
                boots[k].append(L.lift(m, w))
        boots = {k: np.array(v) for k, v in boots.items()}
        base_mean = np.mean([boots[f"fit seed {s}"] for s in SEEDS], axis=0)       # mean of the 3 fits, per bootstrap draw
        seed_sd = float(np.std([lifts[f"fit seed {s}"] for s in SEEDS], ddof=1))
        res = {"seed_sd": round(seed_sd, 4)}
        for k in preds:
            d_dep = boots[k] - boots["fit seed 7"]
            d_mean = boots[k] - base_mean
            # a single fit carries its own seed noise on top of the test-home noise; averaged fits mostly do not
            single = k.startswith("family") or k.startswith("fit seed")
            extra = seed_sd * np.sqrt(1 + 1 / len(SEEDS)) if single else seed_sd / np.sqrt(len(SEEDS))
            lo_, hi_ = np.percentile(d_mean, [2.5, 97.5])
            half = np.hypot((hi_ - lo_) / 2, 1.96 * extra)
            gm = lifts[k] - float(np.mean([lifts[f"fit seed {s}"] for s in SEEDS]))
            res[k] = {"lift": round(lifts[k], 4),
                      "vs_deployed": round(lifts[k] - lifts["fit seed 7"], 4),
                      "vs_deployed_range": [round(float(x), 4) for x in np.percentile(d_dep, [2.5, 97.5])],
                      "vs_mean_of_fits": round(gm, 4),
                      "vs_mean_range_with_seed_noise": [round(gm - half, 4), round(gm + half, 4)]}
            if name == "all":
                r = res[k]
                rows.append(f"| {k} | {r['lift']:.3f} | {r['vs_deployed']:+.3f} | {r['vs_deployed_range'][0]:+.3f} to {r['vs_deployed_range'][1]:+.3f} | "
                            f"{r['vs_mean_of_fits']:+.3f} | {r['vs_mean_range_with_seed_noise'][0]:+.3f} to {r['vs_mean_range_with_seed_noise'][1]:+.3f} |")
        R["results"][name] = res
        print(name, {k: v["lift"] for k, v in res.items() if k != "seed_sd"}, flush=True)

    a = R["results"]["all"]
    best = max((k for k in preds if not k.startswith("fit seed")), key=lambda k: a[k]["lift"])
    clear = a[best]["vs_deployed_range"][0] > 0
    R["best"], R["best_clear_of_deployed"] = best, bool(clear)
    json.dump(R, open(OUT / "ENSEMBLE.json", "w"), indent=1)
    md = ["# Averaging fits, and the new families judged against more than one fit", "",
          f"Deployed model: {' + '.join(A.CURRENT)}, fitted with seed 7. Seeds 8 and 9 are the same model refitted. "
          "Family fits are the deployed model plus one family, seed 7. Sellers found in the best tenth of each district, times random, 2017 and 2018, all owners.", "",
          "| Prediction | Lift | vs deployed fit | 95% range | vs mean of 3 fits | 95% range incl. fit noise |", "|---|---|---|---|---|---|", *rows, "",
          f"Spread of the three fits (standard deviation): {a['seed_sd']:.3f}.", "",
          f"Best prediction: {best}, {a[best]['lift']:.3f} against {a['fit seed 7']['lift']:.3f} for the deployed fit "
          f"({'clear of zero' if clear else 'not clear of zero'}).", ""]
    (OUT / "ENSEMBLE.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
