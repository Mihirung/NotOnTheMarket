"""Skyline sketches for the write-up: the computed horizon from three
very different Exeter streets, drawn as silhouettes. A picture of the
view with no photograph involved.

Usage: python view_figures.py <views_dir> <out_png>
"""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

COL = {1: "#7A8187", 2: "#5B8A4A", 3: "#B3AA7A", 4: "#4C86B0", 5: "#275E54"}
NAME = {1: "buildings", 2: "trees", 3: "land", 4: "water", 5: "hills"}
PICK = [("EX3 0", "Topsham, by the estuary"), ("EX4 5", "Pennsylvania, on the hill"),
        ("EX1 1", "City centre")]


def main(views_dir, out_png):
    df = pd.read_parquet(f"{views_dir}/views_postcode.parquet")
    prof = json.load(open(f"{views_dir}/views_profiles.json"))
    df["sector"] = df.postcode.str.rsplit(" ", n=1).str[0] + " " + df.postcode.str.rsplit(" ", n=1).str[1].str[0]
    fig, axes = plt.subplots(len(PICK), 1, figsize=(12, 2.4 * len(PICK)), sharex=True)
    for ax, (sec, label) in zip(axes, PICK):
        g = df[df.sector == sec]
        rep = g.iloc[(g.u_long_view_share - g.u_long_view_share.median()).abs().argsort().iloc[0]]
        p = prof[rep.postcode]
        deg, cls = np.array(p["u_deg"]), np.array(p["u_cls"])
        b = np.arange(len(deg))
        for c in (3, 5, 2, 1, 4):
            m = cls == c
            if m.any():
                ax.fill_between(b, 0, np.where(m, np.clip(deg, 0, 25), 0), step="mid",
                                color=COL[c], label=NAME[c], linewidth=0)
        ax.set_ylim(0, 25); ax.set_xlim(0, 359)
        ax.set_ylabel("skyline\n(° above eye)", fontsize=9)
        ax.set_title(f"{label} ({rep.postcode}) — upstairs; longest line of sight "
                     f"{rep.u_longest_view_km:.0f} km", fontsize=11, loc="left")
        ax.grid(alpha=.2, axis="y")
        seen = [c for c in df.columns if c.startswith("sees_") and bool(rep[c])]
        if seen:
            ax.text(358, 22, "can see: " + ", ".join(c[5:] for c in seen), ha="right",
                    fontsize=8.5, color="#C33D2E")
    axes[-1].set_xticks([0, 90, 180, 270, 359]); axes[-1].set_xticklabels(["N", "E", "S", "W", "N"])
    handles = [plt.Rectangle((0, 0), 1, 1, color=COL[c]) for c in (1, 2, 3, 4, 5)]
    axes[0].legend(handles, [NAME[c] for c in (1, 2, 3, 4, 5)], ncol=5, fontsize=8.5,
                   frameon=False, loc="upper left")
    fig.suptitle("The view, without a photograph: computed skylines from 1 m LIDAR", fontsize=12, x=.01, ha="left")
    fig.tight_layout(); fig.savefig(out_png, dpi=140); print("wrote", out_png)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
