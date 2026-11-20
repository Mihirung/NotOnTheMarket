"""Chart of scale_tests.py and on_top.py: sunlight and how often homes are sold.

One row per city, then the cities pooled, then the same measure once the
national model's own score is allowed for. Each dot is the change in the
yearly chance of a sale for one more hour of direct sun a day on the
windows, with its 95% range.

Usage: python scale_chart.py <views2_dir> <out_png>
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
PANELS = [("light_both", "Sun on the front and back windows"), ("m_sun_evening_jun", "Evening sun in the garden")]


def main(views_dir, out_png):
    sc = json.load(open(Path(views_dir) / "scale_tests.json"))
    top = json.load(open(Path(views_dir) / "on_top.json"))
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.3), facecolor=SURFACE, sharey=True)
    for ax, (col, title) in zip(axes, PANELS):
        row = sc["timing"]["per_unit"][col]
        names = [k for k in row if k not in ("label", "unit")]
        words = {"2": "two", "3": "three", "4": "four", "5": "five", "6": "six"}
        items = [(" ".join(words.get(w, w) for w in n.split()), row[n], S1) for n in names]
        items.append(("All, on top of the national model", top["left_over"][col], S2))
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=MUTED, labelsize=9, length=0)
        ax.grid(axis="x", color=GRID, lw=0.8); ax.set_axisbelow(True)
        ax.axvline(0, color=INK, lw=1.1)
        n = len(items)
        for i, (name, r, colr) in enumerate(items):
            y = n - 1 - i
            pooled = "pooled" in name or "national" in name
            ax.plot(r["range"], [y, y], color=colr, lw=2.6 if pooled else 2, solid_capstyle="round")
            ax.plot([r["est"]], [y], "o", color=colr, ms=9 if pooled else 7.5, mec=SURFACE, mew=2)
            ax.annotate(f"{round(r['est'], 2) + 0.0:+.2f}", (r["range"][1], y), xytext=(8, 0), textcoords="offset points",
                        va="center", ha="left", fontsize=9, color=INK,
                        bbox=dict(facecolor=SURFACE, edgecolor="none", pad=1.5))
        ax.set_title(title, loc="left", fontsize=11, color=INK, fontweight="bold", pad=10)
        lo = min(min(r["range"][0] for _, r, _ in items), 0); hi = max(max(r["range"][1] for _, r, _ in items), 0)
        pad = 0.12 * (hi - lo)
        ax.set_xlim(lo - pad, hi + 2.6 * pad)
        ax.set_xlabel("Change in the yearly chance of a sale\nfor one more hour a day, percentage points", color=MUTED, fontsize=9)
        if ax is axes[0]:
            ax.set_yticks(range(n)); ax.set_yticklabels([name for name, _, _ in items][::-1], color=INK, fontsize=9.5)
            ax.set_ylim(-0.6, n - 0.4)
    h = [plt.Line2D([], [], marker="o", color=S1, lw=2, ms=7, mec=SURFACE, mew=2, label="Like for like: same kind of home, price, length of ownership and year"),
         plt.Line2D([], [], marker="o", color=S2, lw=2, ms=7, mec=SURFACE, mew=2, label="The same, once the national model's own score is allowed for")]
    fig.legend(handles=h, frameon=False, fontsize=9, loc="lower left", bbox_to_anchor=(0.01, 0.0), ncol=1)
    fig.suptitle("More sun, fewer sales, but the national model already knows", x=0.012, ha="left", fontsize=12.5, color=INK)
    fig.subplots_adjust(left=0.235, right=0.985, top=0.83, bottom=0.33, wspace=0.08)
    fig.savefig(out_png, dpi=150); plt.close(fig)
    print("wrote", out_png)


if __name__ == "__main__":
    main(*sys.argv[1:3])
