"""Plain tables and two charts from the model experiments.

Reads the JSON written by model_lab.py (and, if present, the two-city
view test) and prints the numbers the write-up quotes, so every figure
in docs/06 and docs/07 can be traced to a file.

Usage: python lab_report.py <lab_dir> [views2_dir]
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Validated two-series palette (blue, orange) on a near-white surface.
S1, S2 = "#2a78d6", "#eb6834"
INK, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
BANDS = [("t0_4", "0 to 4 years"), ("t5_9", "5 to 9 years"), ("t10_19", "10 to 19 years"), ("t20p", "20 years or more")]


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)


def load(d, name):
    f = Path(d) / name
    return json.load(open(f)) if f.exists() else None


def main(lab_dir, views_dir=None):
    lab = Path(lab_dir)
    ladder, curve, rolling = (load(lab, f"lab_{k}.json") for k in ("ladder", "curve", "rolling"))
    ablates = [json.load(open(f)) for f in sorted(lab.glob("lab_ablate_*.json"))]

    if ladder:
        print(f"\nLADDER at {ladder['pct']}% of properties ({ladder['test_rows']:,} test rows)")
        print(f"{'model':12s} {'AUC':>7s} {'in-year':>8s} {'lift@1':>7s} {'lift@5':>7s} {'lift@10':>8s} {'lift@20':>8s} {'20y+ lift':>10s} rounds")
        for k in ("BASE", "+HIST", "+HIST+GEO", "+HIST+VIEW", "ALL"):
            r = ladder[k]
            print(f"{k:12s} {r['auc']:7.4f} {r['auc_within_year']:8.4f} {r['lift1']:7.2f} {r['lift5']:7.2f} {r['lift10']:8.3f} "
                  f"{r['lift20']:8.3f} {r.get('lift10_t20p', float('nan')):10.3f} {r.get('rounds', '')}")
        for name in ("ci", "ci_t10_19", "ci_t20p"):
            print(f"  intervals ({name}):")
            for k, v in ladder[name].items():
                print(f"    {k:26s} dAUC {v['d_auc']}  dLift@10 {v['d_lift10']}  P(better) {v['p_better']}")
        print("  share of the model's splitting gain by family:", ladder.get("gain_by_family"))
        print("  top signals:", ", ".join(f"{n} {g:.3f}" for n, g in ladder.get("top_features", [])[:14]))
        print("  calibration (predicted, actual) by tenth:", ladder.get("calibration_all"))

        fig, ax = plt.subplots(figsize=(7.6, 3.9), facecolor=SURFACE); style(ax)
        x = range(len(BANDS)); w = 0.36
        # Use the fits on the largest share of homes available.
        big = max((int(k.split("@")[1]) for k in (curve or {}) if k.startswith("ALL@")), default=None)
        src_old = curve[f"BASE@{big}"] if big else ladder["BASE"]
        src_new = curve[f"ALL@{big}"] if big else ladder["ALL"]
        old = [100 * (src_old.get(f"lift10_{b}") - 1) for b, _ in BANDS]
        new = [100 * (src_new.get(f"lift10_{b}") - 1) for b, _ in BANDS]
        ax.bar([i - w / 2 - .012 for i in x], old, w, color=S1, label="Original 13 signals")
        ax.bar([i + w / 2 + .012 for i in x], new, w, color=S2, label="Reviewed model, 73 signals")
        for i in x:
            ax.text(i - w / 2 - .012, old[i] + 1.5, f"+{old[i]:.0f}%", ha="center", fontsize=9, color=INK)
            ax.text(i + w / 2 + .012, new[i] + 1.5, f"+{new[i]:.0f}%", ha="center", fontsize=9, color=INK)
        ax.set_xticks(list(x)); ax.set_xticklabels([l for _, l in BANDS])
        ax.set_ylim(0, max(new + old) * 1.18)
        ax.set_yticks([0, 25, 50, 75, 100]); ax.set_yticklabels(["0", "+25%", "+50%", "+75%", "+100%"])
        ax.set_xlabel("How long the owner has been there", color=MUTED, fontsize=9.5)
        ax.set_title("Extra sellers found in the best tenth of homes, against mailing at random",
                     fontsize=11.5, color=INK, loc="left")
        ax.legend(frameon=False, fontsize=9, loc="upper right")
        fig.tight_layout(); fig.savefig(lab / "lift_by_tenure.png", dpi=150); plt.close(fig)

    if curve:
        sizes = sorted({int(k.split("@")[1]) for k in curve if "@" in k})
        print("\nLEARNING CURVE")
        print(f"{'model':10s} {'%':>3s} {'rows':>12s} {'AUC':>7s} {'lift@10':>8s} {'lift@1':>7s} {'20y+ AUC':>9s} {'20y+ lift':>10s} rounds")
        for name in ("BASE", "ALL"):
            for s in sizes:
                r = curve.get(f"{name}@{s}")
                if r:
                    print(f"{name:10s} {s:3d} {r['train_rows']:12,} {r['auc']:7.4f} {r['lift10']:8.3f} {r['lift1']:7.2f} "
                          f"{r.get('auc_t20p', float('nan')):9.4f} {r.get('lift10_t20p', float('nan')):10.3f} {r.get('rounds', '')}")
        for k, v in curve.get("ci", {}).items():
            print(f"    {k:26s} dAUC {v['d_auc']}  dLift@10 {v['d_lift10']}")
        fig, ax = plt.subplots(figsize=(7.6, 3.9), facecolor=SURFACE); style(ax)
        homes = {1: "138 thousand", 5: "690 thousand", 10: "1.4 million", 20: "2.8 million", 40: "5.5 million",
                 100: "13.8 million"}
        local = load(lab, "lab_local.json") or {}
        use_local = all(f"{n}@{s}" in local for n in ("BASE", "ALL") for s in sizes)
        val = (lambda n, s: local[f"{n}@{s}"]["local_lift10"]) if use_local else (lambda n, s: curve[f"{n}@{s}"]["auc"])
        fmt = "{:.2f}" if use_local else "{:.3f}"
        for name, col, lab_ in (("BASE", S1, "Original 13 signals"), ("ALL", S2, "Reviewed model, 73 signals")):
            pts = [(s, val(name, s)) for s in sizes if f"{name}@{s}" in curve]
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col, lw=2, marker="o", ms=7,
                    markeredgecolor=SURFACE, markeredgewidth=1.5, label=lab_)
            ax.text(pts[-1][0] * 1.12, pts[-1][1], fmt.format(pts[-1][1]), va="center", fontsize=9.5, color=INK)
            ax.text(pts[0][0] * 0.89, pts[0][1] + (0.004 if name == "ALL" and use_local else -0.004 if use_local else 0),
                    fmt.format(pts[0][1]), va="center", ha="right", fontsize=9.5, color=INK)
        ax.set_xscale("log"); ax.set_xlim(0.55, 190)
        ax.set_xticks(sizes); ax.set_xticklabels([f"{s}%\n{homes.get(s, '')}" for s in sizes]); ax.minorticks_off()
        ax.set_xlabel("Share of all homes in England and Wales the model learned from", color=MUTED, fontsize=9.5)
        ax.set_title("Sellers reached in the best tenth of each district, against random (2017 and 2018)" if use_local
                     else "Ranking skill on sales it has never seen (AUC, 2017 and 2018)", fontsize=11.5, color=INK, loc="left")
        if use_local:
            ax.set_ylim(1.58, 1.70); ax.set_yticks([1.60, 1.62, 1.64, 1.66, 1.68])
            ax.set_yticklabels(["1.60 times", "1.62", "1.64", "1.66", "1.68"])
        ax.legend(frameon=False, fontsize=9, loc="center right")
        fig.tight_layout(); fig.savefig(lab / "learning_curve.png", dpi=150); plt.close(fig)

    if rolling:
        print("\nROLLING REFIT (frozen in 2015 vs refitted to the year before)")
        for y in ("2017", "2018"):
            r = rolling[y]
            print(f"  {y}: AUC {r['frozen']['auc']:.4f} -> {r['fresh']['auc']:.4f}; lift@10 {r['frozen']['lift10']:.3f} -> "
                  f"{r['fresh']['lift10']:.3f}; mean predicted {r['frozen']['mean_pred']:.4f} / {r['fresh']['mean_pred']:.4f} "
                  f"vs actual {r['base_rate']:.4f}; dAUC {r['ci']['d_auc']}")
            for b in ("t0_9", "t10_19", "t20p"):
                print(f"      {b:7s} AUC {r[b]['frozen_auc']:.4f} -> {r[b]['fresh_auc']:.4f}; lift@10 "
                      f"{r[b]['frozen_lift10']:.3f} -> {r[b]['fresh_lift10']:.3f}")
            print(f"      20y+ interval: {r['ci_t20p']}")

    for ablate in ablates:
        print(f"\nLEAVE ONE FAMILY OUT at {ablate['pct']}%")
        for k in ("ALL", "no VIEW", "no GEO"):
            if k in ablate:
                r = ablate[k]
                print(f"  {k:15s} AUC {r['auc']:.4f} lift@10 {r['lift10']:.3f} 20y+ lift {r.get('lift10_t20p', float('nan')):.3f}")
        for name in ("ci", "ci_t20p"):
            for k, v in ablate.get(name, {}).items():
                print(f"    [{name}] {k:24s} dAUC {v['d_auc']} dLift@10 {v['d_lift10']} P(better) {v['p_better']}")

    if views_dir:
        va, vf = load(views_dir, "view_ablation2.json"), load(views_dir, "view_fidelity.json")
        if va:
            print("\nHOUSE-LEVEL VIEWS AND SALE TIMING")
            for k, r in va.items():
                print(f"  {k:26s} AUC {r['auc_base']:.4f} -> {r['auc_view']:.4f}  d {r['d_auc']}  P {r['p_improves']}  "
                      f"lift@10 {r['lift10_base']:.2f} -> {r['lift10_view']:.2f}  ({r['test_sales']:,} test sales)")
        if vf:
            print("\nNATIONAL 30 m LAYER AGAINST HOUSE-LEVEL TRUTH (rank correlation)")
            for city, r in vf.items():
                print(f"  {city} ({r['n_postcodes']:,} postcodes): " + "; ".join(f"{k} {v:+.2f}" for k, v in r["spearman"].items()))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
