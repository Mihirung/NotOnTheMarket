"""District and sector of every row in the first panel chunks.

The chunk files written by panel2.py carry no geography, which is right
for training but means the test rows cannot be grouped by place. This
rebuilds the same rows in the same order and saves each row's postcode
district and sector code, so that ranking can be judged within a local
area: campaigns are local, so that is the ranking that matters.

Usage: python panel_districts.py <transactions.parquet> <panel_dir> [n_chunks]
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from panel2 import CHUNK_BUCKETS, Panel  # noqa: E402


def main(tx_path, panel_dir, n_chunks=2):
    panel = Panel(tx_path)
    out = Path(panel_dir)
    for c in range(int(n_chunks)):
        lo, hi = c * CHUNK_BUCKETS, (c + 1) * CHUNK_BUCKETS
        spells = np.nonzero((panel.bucket >= lo) & (panel.bucket < hi))[0]
        rows, years, label = panel.expand(spells)
        assert np.array_equal(label, np.load(out / f"y_{c}.npy")), "row order does not match the chunk"
        np.save(out / f"district_{c}.npy", panel.oc[rows].astype("int16"))
        np.save(out / f"sector_{c}.npy", panel.pc2sec[panel.pc[rows]].astype("int32"))
        print(f"chunk {c}: {len(rows):,} rows, {len(np.unique(panel.oc[rows])):,} districts", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
