"""After new signal families have been assessed one by one (assess_signal.py),
put the ones that passed together and decide what to deploy.

  plan   <FAM...>   read each family's verdict; write research/outputs/lab/candidates.json
                    with the deployed model plus every family that passed on its own, in
                    the order they gained most; print the fits to run
  choose            after the fits and local_eval.py: print "<name> <FAM+FAM+...>" for
                    model_lab.py deploy_set, or nothing to keep the deployed model

The rule is the one that has always applied: a set of families replaces the
deployed model only when its gain in sellers found in the best tenth of
each district has a 95% range clear of zero; a larger set is kept over a
smaller one only if it beats that one clear of zero too. If no combination
passes, the single family with the clearest gain is deployed, if any.

Usage:
  python combine_signals.py plan PEOPLE SCHOOLS ACCESS STOCK CRIME
  python combine_signals.py choose
"""
import json
import sys
from pathlib import Path

LAB = Path("research/outputs/lab")
SIG = Path("research/outputs/signals")


def deployed():
    d = json.load(open(LAB / "lab_deploy.json"))
    return d["name"], d["families"]


def plan(fams):
    name, base = deployed()
    passed = []
    for f in fams:
        p = SIG / f"{f}.json"
        if not p.exists():
            print(f"# {f}: not assessed", file=sys.stderr); continue
        r = json.load(open(p))
        g = r.get("adds", {}).get("all", {})
        ok = r.get("verdict", "").startswith("add it") and r.get("against", {}).get("name") == name
        print(f"# {f}: {r.get('verdict')} (gain {g.get('gain')}, range {g.get('range')})", file=sys.stderr)
        if ok:
            passed.append((g["gain"], f))
    passed = [f for _, f in sorted(passed, reverse=True)]
    cands = []
    for k in range(2, len(passed) + 1):                    # one family alone is already fitted by assess_signal.py
        add = passed[:k]
        cands.append({"name": name + "+" + "+".join(add), "families": base + add})
    singles = [{"name": f"{name}+{f}", "families": base + [f]} for f in passed]
    json.dump({"deployed": name, "deployed_families": base, "passed": passed, "singles": singles,
               "candidates": singles[:1] + cands}, open(LAB / "candidates.json", "w"), indent=1)
    for c in cands:
        print(f"{c['name']} {'+'.join(c['families'])}")


def choose():
    c = json.load(open(LAB / "candidates.json"))
    ci = json.load(open(LAB / "lab_local.json"))["ci"]
    base = c["deployed"]
    gain = lambda new, old: (ci.get(f"{new}@100 vs {old}@100") or {}).get("all")    # noqa: E731
    pick = None
    for k in c["candidates"]:                              # growing sets: each must beat the deployed model and the last pick
        g0, gp = gain(k["name"], base), gain(k["name"], pick["name"]) if pick else None
        print(f"{k['name']} vs {base}: {g0}" + (f"; vs {pick['name']}: {gp}" if pick else ""), file=sys.stderr)
        if g0 and g0[0] > 0 and (pick is None or (gp and gp[0] > 0)):
            pick = k
    if pick is None:
        ok = [(gain(s["name"], base)[1], s) for s in c["singles"] if gain(s["name"], base) and gain(s["name"], base)[0] > 0]
        pick = max(ok, key=lambda t: t[0])[1] if ok else None
    if pick:
        print(pick["name"], "+".join(pick["families"]))


if __name__ == "__main__":
    {"plan": lambda: plan(sys.argv[2:]), "choose": choose}[sys.argv[1]]()
