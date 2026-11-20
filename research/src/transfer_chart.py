"""Chart of transfer_tests.py: does a score built in one city hold in the other?

Two panels on one scale. On the left, what a home sells for; on the
right, when it sells. Each dot is the slope with its 95% range: 1 means
the pattern carries to the other city in full, 0 means it does not carry.

Usage: python transfer_chart.py <views2_dir> <out_png>
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Validated two-series palette (blue, orange) on a near-white surface.
S1, S2 = "#2a78d6", "#eb6834"
INK, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
ROWS = [("outlook", "The outlook from\nthe upper windows"), ("garden_light", "The garden\nand sunlight"), ("all", "All measures\ntogether")]
PAIRS = [("exeter", "bath", S1, "Learned in Exeter, tested in Bath"), ("bath", "exeter", S2, "Learned in Bath, tested in Exeter")]


def main(views_dir, out_png):
    res = json.load(open(Path(views_dir) / "transfer_tests.json"))
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.9), facecolor=SURFACE, sharey=True, sharex=True)
    panels = [("price", "_size", "What a home sells for"), ("timing", "", "When a home sells")]
    for ax, (key, suffix, title) in zip(axes, panels):
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=MUTED, labelsize=9, length=0)
        ax.grid(axis="x", color=GRID, lw=0.8); ax.set_axisbelow(True)
        ax.axvline(0, color=INK, lw=1.1)
        ax.axvline(1, color=AXIS, lw=1.1, ls=(0, (3, 3)))
        for i, (name, _) in enumerate(ROWS):
            for j, (a, b, col, label) in enumerate(PAIRS):
                r = res[key][f"{a}_to_{b}_{name}{suffix}"]
                y = len(ROWS) - 1 - i + (0.15 if j == 0 else -0.15)
                ax.plot(r["range"], [y, y], color=col, lw=2, solid_capstyle="round")
                ax.plot([r["slope"]], [y], "o", color=col, ms=8, mec=SURFACE, mew=2, label=label if i == 0 else None)
                ax.text(r["range"][1] + 0.07, y, f"{round(r['slope'], 1) + 0.0:.1f}", va="center", fontsize=9, color=INK)
        ax.set_title(title, loc="left", fontsize=11, color=INK, fontweight="bold", pad=10)
        ax.set_xlim(-1.5, 2.4); ax.set_xticks([-1, 0, 1, 2])
        ax.set_xlabel("0 = does not carry to the other city    1 = carries in full", color=MUTED, fontsize=9)
    axes[0].set_yticks(range(len(ROWS))); axes[0].set_yticklabels([l for _, l in ROWS][::-1], color=INK, fontsize=9.5)
    axes[0].set_ylim(-0.6, len(ROWS) - 0.4)
    axes[0].legend(frameon=False, fontsize=9, loc="upper left", bbox_to_anchor=(-0.02, -0.24), ncol=2)
    fig.suptitle("A score built from one city's sales, tested on the other city", x=0.012, ha="left", fontsize=12.5, color=INK)
    fig.subplots_adjust(left=0.16, right=0.975, top=0.80, bottom=0.27, wspace=0.10)
    fig.savefig(out_png, dpi=150); plt.close(fig)
    print("wrote", out_png)


if __name__ == "__main__":
    main(*sys.argv[1:3])
