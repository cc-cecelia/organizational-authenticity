"""Summary figure for a non-technical reader: non-financial goals in executive
bonuses became common, but carry little money.

Usage: python part2_lived_values/src/plot_summary_figure.py   (after build_panel.py)
Output: part2_lived_values/output/analysis/figures/pay_criteria_summary.png

Reads output/lived_values_panel.csv. Two panels, each with its own axis (two
different measures, so two charts rather than a dual axis):
  left   share of companies whose bonus or long-term award includes at least one
         criterion in the category (firm-years with extracted pay criteria)
  right  average share of the annual bonus's weight on the category
         (firm-years with weights: disclosed, derived from a stated split, or
         estimated)
Financial results (about 70% of bonus weight) are left out of the right panel
so the small categories stay visible; the subtitle states that figure.
Colors: validated reference palette (dataviz skill), slots 1-5, passing all
checks; the contrast warning is relieved by direct labels on every line.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
PANEL = REPO / "part2_lived_values" / "output" / "lived_values_panel.csv"
OUT = REPO / "part2_lived_values" / "output" / "analysis" / "figures" / "pay_criteria_summary.png"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"
SERIES = [  # (category code, plain label, color)
    ("environment", "Environment", "#2a78d6"),
    ("dei", "Diversity & inclusion", "#eb6834"),
    ("safety", "Safety", "#1baf7a"),
    ("customers", "Customers", "#eda100"),
    ("employees", "Employees", "#e87ba4"),
]


def style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK2)
    ax.grid(axis="y", color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    ax.set_xticks(range(2016, 2025, 2))


def place_labels(ax, ends: list, min_gap: float) -> None:
    """Direct labels at line ends, nudged apart vertically so they never overlap."""
    ends = sorted(ends, key=lambda e: e[1])
    ys = []
    for _, y, _, _ in ends:
        ys.append(max(y, ys[-1] + min_gap) if ys else y)
    for (x, _, label, color), y in zip(ends, ys):
        ax.text(x + 0.25, y, label, color=INK2, fontsize=9.5, va="center")


def main() -> int:
    p = pd.read_csv(PANEL)
    p = p[p.year.between(2016, 2024)]
    has_pay = p[p.pay_n_total.notna()]
    has_w = p[p[[f"cat_weight_{k}" for k, _, _ in SERIES]].notna().any(axis=1)]
    fin = has_w.groupby("year").cat_weight_shareholders.mean()

    plt.rcParams.update({"font.size": 11})
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 5.2))
    fig.patch.set_facecolor(SURFACE)
    ends1, ends2 = [], []
    for k, label, color in SERIES:
        share = has_pay.groupby("year")[f"pay_n_{k}"].apply(lambda s: (s > 0).mean() * 100)
        weight = has_w.groupby("year")[f"cat_weight_{k}"].mean() * 100
        for ax, s, ends in ((a1, share, ends1), (a2, weight, ends2)):
            ax.plot(s.index, s.values, color=color, lw=2.4, marker="o", ms=4.5, mec=SURFACE, mew=1.1)
            ends.append((s.index[-1], s.values[-1], label, color))
    style(a1)
    style(a2)
    a1.set_ylim(0, 100)
    a1.set_yticks(range(0, 101, 25))
    a1.set_yticklabels([f"{v}%" for v in range(0, 101, 25)])
    a1.set_xlim(2015.6, 2026.6)
    a1.set_title("How common: share of companies whose executive pay\nincludes a goal in this area",
                 loc="left", fontsize=11, fontweight="bold", color=INK)
    top = max(e[1] for e in ends2) * 1.25
    a2.set_ylim(0, max(top, 10))
    a2.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    a2.set_xlim(2015.6, 2026.6)
    a2.set_title("How much money: average share of the annual\nbonus that rides on this area",
                 loc="left", fontsize=11, fontweight="bold", color=INK)
    place_labels(a1, ends1, 5.5)
    place_labels(a2, ends2, a2.get_ylim()[1] * 0.055)
    a1.set_xlabel("Year of proxy statement", color=INK2)
    a2.set_xlabel("Year of proxy statement", color=INK2)
    fig.suptitle("Non-financial goals became common in executive pay, but little money rides on them",
                 x=0.02, ha="left", fontsize=13, fontweight="bold", color=INK)
    fig.text(0.02, 0.885, f"50 large US companies, 2016–2024. Financial results (left out of the right panel) "
             f"take about {fin.mean() * 100:.0f}% of bonus weight in every year.",
             ha="left", fontsize=10, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=160)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
