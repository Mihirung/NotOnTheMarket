"""Run a command while holding a reservation in the national run's memory
ledger, so the run counts this job's memory and never overruns the limit.

Usage: python ledger_run.py <national_dir> <GB> <command...>
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import national_views as NV  # noqa: E402


def main(out, gb, cmd):
    out = Path(out)
    t0 = time.time()
    NV.reserve(out, float(gb))
    print(f"reserved {gb} GB after {time.time() - t0:.0f}s; running: {' '.join(cmd)}", flush=True)
    try:
        return subprocess.call(cmd)
    finally:
        NV.release_reservation(out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3:]))
