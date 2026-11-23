"""How far apart are two fits of the same model? The yardstick for every 'does it add to the model' test.

The ranges in assess_signal.py cover which homes happen to be in the test years, not the
fit's own randomness (row and column sampling, early stopping). Here the deployed model is
fitted again with other seeds and compared with itself exactly as a new family would be.
If two fits of the same model differ by as much as a new family moves the score, a family
has to beat that spread, not just zero.

    python seed_noise.py [seed ...]        (default: 8 9; each fit takes about two hours)

Writes research/outputs/signals/SEED_NOISE.json and .md.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

PANEL, LAB, OUT = "research/data/panel3", Path("research/outputs/lab"), Path("research/outputs/signals")


def fit_seed(seed):
    """Each seed in its own process: SEED is read when model_lab is imported."""
    code = ("import sys; sys.path.insert(0,'research/src'); import model_lab as ML, assess_signal as A; "
            "from pathlib import Path; ch=ML.Chunks(A.PANEL); "
            "ML.predict_cached(ch, Path(A.LAB), 4, A.CUR_NAME, 100, A.CURRENT)")
    subprocess.run([sys.executable, "-c", code], check=True, env=os.environ | {"QM_SEED": str(seed)})


def compare(seeds):
    import assess_signal as A
    import local_eval as LE
    t = LE.load_test(PANEL)
    key = f"{A.CUR_NAME}@100"
    p = {7: np.load(LAB / "preds" / f"{key}.npy")}
    for s in seeds:
        p[s] = np.load(LAB / "preds" / f"{key}~s{s}.npy")
    rows, R = [], {"model": A.CUR_NAME, "families": A.CURRENT, "pairs": {}}
    pairs = [(7, s) for s in seeds] + [(a, b) for i, a in enumerate(seeds) for b in seeds[i + 1:]]
    for a, b in pairs:
        res = {}
        for name, lo, hi in LE.TENURE:
            L = LE.Local(t, lo, hi)
            ma, mb = L.top_mask(p[a][L.keep]), L.top_mask(p[b][L.keep])
            la, lb = L.lift(ma), L.lift(mb)
            rng = np.random.default_rng(3); d = []
            for _ in range(A.BOOT):
                w = rng.poisson(1.0, LE.N_BLOCKS).astype(float)[L.block]
                d.append(L.lift(mb, w) - L.lift(ma, w))
            res[name] = {"a": round(la, 4), "b": round(lb, 4), "diff": round(lb - la, 4),
                         "range": [round(float(np.percentile(d, q)), 4) for q in (2.5, 97.5)]}
            rows.append(f"| {a} vs {b} | {name} | {la:.3f} | {lb:.3f} | {lb - la:+.3f} | "
                        f"{res[name]['range'][0]:+.3f} to {res[name]['range'][1]:+.3f} |")
        R["pairs"][f"{a} vs {b}"] = res
    alld = [v["all"]["diff"] for v in R["pairs"].values()]
    R["spread_all"] = round(float(np.max(np.abs(alld))), 4)
    json.dump(R, open(OUT / "SEED_NOISE.json", "w"), indent=1)
    md = ["# Two fits of the same model: how far apart?", "",
          f"The deployed model ({' + '.join(A.CURRENT)}) fitted with different random seeds and nothing else changed. "
          "Sellers found in the best tenth of each district, times random, 2017 and 2018.", "",
          "| Seeds | Owners | First | Second | Difference | 95% range (test homes only) |", "|---|---|---|---|---|---|", *rows, "",
          f"Largest difference for all owners between two fits of the same model: {R['spread_all']:.3f}. "
          "A new family's gain has to be judged against this, not only against zero.", ""]
    (OUT / "SEED_NOISE.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    seeds = [int(x) for x in sys.argv[1:]] or [8, 9]
    for s in seeds:
        if not (LAB / "preds" / f"{json.load(open(LAB / 'lab_deploy.json'))['name']}@100~s{s}.npy").exists():
            fit_seed(s)
    compare(seeds)
