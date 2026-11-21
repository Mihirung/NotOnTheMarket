"""Run a command while holding a reservation in the national run's memory
ledger, so the run counts this job's memory and never overruns the limit.

The reservation is taken in two steps. The job's row goes into the ledger
at once, so no new cell can start in the room it needs; the job then waits
for cells already running to finish until its share is genuinely free.
Without the first step a waiting job can be overtaken by new cells for
hours.

Usage: python ledger_run.py <national_dir> <GB> <command...>
"""
import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import national_views as NV  # noqa: E402


def _rows(ledger):
    rows = [l.split() for l in ledger.read_text().splitlines()] if ledger.exists() else []
    return [r for r in rows if len(r) == 2 and os.path.exists(f"/proc/{r[0]}")]


def claim(out, need):
    """Put this job in the ledger now, then wait until everything else fits beside it."""
    ledger, me = out / ".memory_ledger", str(os.getpid())
    with open(out / ".memory.lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        rows = _rows(ledger) + [[me, f"{need:.2f}"]]
        ledger.write_text("".join(" ".join(r) + "\n" for r in rows))
    while True:
        with open(out / ".memory.lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            others = sum(float(r[1]) for r in _rows(ledger) if r[0] != me)
        if others + need <= NV.BUDGET_GB:
            return
        time.sleep(15)


def main(out, gb, cmd):
    out = Path(out)
    t0 = time.time()
    claim(out, float(gb))
    print(f"reserved {gb} GB after {time.time() - t0:.0f}s; running: {' '.join(cmd)}", flush=True)
    try:
        return subprocess.call(cmd)
    finally:
        NV.release_reservation(out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3:]))
