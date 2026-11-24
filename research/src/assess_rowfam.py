"""Does a row family (signals.ROW_FAMILIES) make the national model better?

The same test as assess_signal.py's test 4, for a family worked out from dated
events (stored beside the panel by panel2.write_row_family): the deployed model
is refitted with the family added, and the sellers found in the best tenth of
each district are compared, with a 95% range that counts both the test homes
and the fit's own randomness.

    python assess_rowfam.py <FAMILY> [pct]

Writes research/outputs/signals/<FAMILY>.json and .md.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import assess_signal as A  # noqa: E402
import model_lab as ML  # noqa: E402
import signals as SG  # noqa: E402


def main():
    fam = sys.argv[1]; pct = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    say = lambda *a: print(*a, flush=True)                # noqa: E731
    ch = ML.Chunks(A.PANEL)
    assert fam in ch.rowfam, f"{fam} is not stored beside the panel (run panel2.py ... rowfam {fam})"
    R = {"family": fam, "about": SG.ROW_FAMILIES[fam]["label"], "source": SG.ROW_FAMILIES[fam]["source"],
         "when": time.strftime("%Y-%m-%d"), "against": {"name": A.CUR_NAME, "families": A.CURRENT},
         "columns": SG.ROW_FAMILIES[fam]["columns"]}
    R["adds"], _ = A.adds_to_model(ch, fam, pct, 4, say)
    g = R["adds"]["all"]; rng = g.get("range_with_fit_noise", g["range"])
    R["verdict"] = ("add it: the model finds more sellers and the range is clear of zero and of the fit's own noise" if rng[0] > 0
                    else "do not add it to the model: no gain clear of zero and of the fit's own noise")
    out = Path(A.OUT)
    json.dump(R, open(out / f"{fam}.json", "w"), indent=1)
    lab = {"all": "All", "t0_9": "Under 10 years", "t10_19": "10 to 19 years", "t20p": "20 years or more"}
    md = [f"# {fam}: {R['about']}", "", f"**Verdict:** {R['verdict']}", "", f"Source: {R['source']}.", "",
          "| Owners | Current model | With this family | Gain | 95% range |", "|---|---|---|---|---|"]
    for k, l in lab.items():
        v = R["adds"][k]; r = v.get("range_with_fit_noise", v["range"])
        md.append(f"| {l} | {v['current']:.3f} | {v['with']:.3f} | {v['gain']:+.3f} | {r[0]:+.3f} to {r[1]:+.3f} |")
    md += ["", "Sellers found in the best tenth of each postcode district, times random, 2017 and 2018. The current model is "
           f"the deployed one: {' + '.join(A.CURRENT)}. The range includes the fit's own randomness (SEED_NOISE.md).", "",
           f"Share of the refitted model's gain that comes from this family: {100 * (R['adds'].get('gain_share') or {}).get(fam, 0):.1f}%.", ""]
    (out / f"{fam}.md").write_text("\n".join(md))
    say(f"== {fam}: {R['verdict']}")


if __name__ == "__main__":
    main()
