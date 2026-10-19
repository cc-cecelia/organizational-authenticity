"""Summary figure for a non-technical reader: what company values pages
emphasize, 2016-2024.

Usage: .venv/bin/python part1_stated_values/src/plot_summary_figure.py
Output: part1_stated_values/output/figures/themes_summary.png

Reads output/stated_values.csv. For each year, the share of collected pages
that clearly emphasize a theme (salience 2 or 3 on the 0-3 scale). Five themes
are shown: the four that rose most and shareholders, the only one that fell.
Customers, innovation and integrity stay high and roughly flat, as the subtitle
notes. Colors: validated reference palette (dataviz skill), slots 1-5 in fixed
order; every line is direct-labelled (contrast relief).
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"
SERIES = [  # (category code, plain label, color)
    ("dei", "Diversity & inclusion", "#2a78d6"),
    ("employees", "Employees", "#eb6834"),
    ("environment", "Environment", "#1baf7a"),
    ("community", "Community", "#eda100"),
    ("shareholders", "Shareholders", "#e87ba4"),
]
OUT = config.OUTPUT_DIR / "figures" / "themes_summary.png"


def main() -> int:
    d = pd.read_csv(config.STATED_VALUES_CSV)
    ok = d[d.status == "ok"]
    plt.rcParams.update({"font.size": 11})
    fig, ax = plt.subplots(figsize=(10, 5.4))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ends = []
    for k, label, color in SERIES:
        s = ok.groupby("year")[f"sal_{k}"].apply(lambda v: (v >= 2).mean() * 100)
        ax.plot(s.index, s.values, color=color, lw=2.4, marker="o", ms=5, mec=SURFACE, mew=1.2)
        ends.append((s.index[-1], s.values[-1], f"{label} ({s.values[0]:.0f}% → {s.values[-1]:.0f}%)"))
    # Direct labels, nudged apart so they never overlap.
    ends.sort(key=lambda e: e[1])
    y_prev = None
    for x, y, label in ends:
        y = y if y_prev is None else max(y, y_prev + 5.5)
        ax.text(x + 0.2, y, label, color=INK2, fontsize=9.5, va="center")
        y_prev = y
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK2)
    ax.grid(axis="y", color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    ax.set_xlim(2015.6, 2027.4)
    ax.set_xticks(range(2016, 2025))
    ax.set_ylim(0, 100)
    ax.set_yticks(range(0, 101, 25))
    ax.set_yticklabels([f"{v}%" for v in range(0, 101, 25)])
    ax.set_ylabel("Share of values pages that clearly\nemphasize the theme", color=INK2)
    ax.set_xlabel("Year (pages as archived around July 1)", color=INK2)
    fig.suptitle("Company values pages widened their circle: more about people, planet and community,\n"
                 "less about shareholders", x=0.02, ha="left", fontsize=12.5, fontweight="bold", color=INK)
    fig.text(0.02, 0.83, "50 large US companies, 2016–2024. Customers, innovation and integrity stay the most "
             "emphasized themes throughout and are not shown.", ha="left", fontsize=9.5, color=INK2)
    fig.text(0.02, 0.015, "\"Clearly emphasize\" = rated 2 or 3 on a 0–3 scale by an AI model reading each page; "
             "spot-checked by hand.", ha="left", fontsize=8.5, color="#898781")
    fig.tight_layout(rect=(0, 0.04, 1, 0.8))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=160)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
