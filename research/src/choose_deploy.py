"""Which model to deploy, from the district-level comparisons (local_eval.py).

The rule that keeps the model from ever getting worse: a set of signal
families replaces the current model only when its gain in sellers found in
the best tenth of each district has a 95% range clear of zero. Among the
sets that pass, a larger set is preferred only if it beats the smaller one
with a range clear of zero too.

Prints "<name> <FAM+FAM+...>" for model_lab.py deploy_set.

Usage: python choose_deploy.py research/outputs/lab/lab_local.json
"""
import json
import sys

CURRENT = ("CURRENT", "BASE+HIST+GEO+VIEW")
LADDER = [("+HOUSE+AREA+PD", "BASE+HIST+GEO+VIEW+HOUSE+AREA+PD"),
          ("+HOUSE+AREA+PD+CLIMATE", "BASE+HIST+GEO+VIEW+HOUSE+AREA+PD+CLIMATE"),
          ("+ALLNEW", "BASE+HIST+GEO+VIEW+HOUSE+AREA+AMENITY+PD")]
SINGLES = [("+PD", "BASE+HIST+GEO+VIEW+PD"), ("+HOUSE", "BASE+HIST+GEO+VIEW+HOUSE"),
           ("+AREA", "BASE+HIST+GEO+VIEW+AREA"), ("+HOUSE+AREA", "BASE+HIST+GEO+VIEW+HOUSE+AREA")]


def gain(ci, new, old):
    e = ci.get(f"{new}@100 vs {old}@100")
    return None if e is None else e["all"]          # [low, median, high, P(gain > 0)]


def choose(ci):
    pick = CURRENT
    for name, fams in LADDER:                        # each step must beat the one before it
        g = gain(ci, name, pick[0])
        if g is not None and g[0] > 0:
            pick = (name, fams)
        print(f"{name} vs {pick[0] if pick[0] != name else CURRENT[0]}: {g}", file=sys.stderr)
    if pick == CURRENT:                              # no combination passed: the best single family that did
        ok = [(gain(ci, n, "CURRENT")[1], (n, f)) for n, f in SINGLES
              if gain(ci, n, "CURRENT") is not None and gain(ci, n, "CURRENT")[0] > 0]
        if ok:
            pick = max(ok)[1]
    return pick


if __name__ == "__main__":
    ci = json.load(open(sys.argv[1]))["ci"]
    print(*choose(ci))
