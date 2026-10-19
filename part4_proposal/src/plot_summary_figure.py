"""Summary figure for a non-technical reader: DEI, say vs do, 2016-2026.

Usage: python part4_proposal/src/plot_summary_figure.py   (after say_do.py)
Output: part4_proposal/output/figures/dei_say_vs_do_summary.png

Reads output/say_do_firm_year.csv (theme == "dei") and Part 2's event table.
Three series on incomparable scales (0-3 page salience, words per 10,000,
company counts), so each is shown as a percentage of its own peak year: one
axis, no dual scale. Every line is direct-labelled. The real values are stated
in the end labels. Events are drawn at their real dates; proxy and pay points
sit at the year the proxy was filed (pay goals in a year's proxy were set the
year before). The validated reference palette (dataviz skill) is used: slots
1-3, passing all checks; the contrast warning is relieved by direct labels.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "part4_proposal" / "output"
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"

EVENTS = [  # (calendar position, label, label height, alignment): labels sit in a band above the data
    (2020.4, "May 2020\nracial-justice protests", 126, "right"),
    (2022.6, "2022–23 anti-ESG /\nanti-DEI backlash", 126, "right"),
    (2023.5, "June 2023 Supreme Court\naffirmative-action ruling", 115, "left"),
]
END_OFFSET = {"proxy": 7, "pay": -6, "web": 0}   # nudge end labels apart


def main() -> int:
    fy = pd.read_csv(OUT / "say_do_firm_year.csv")
    f = fy[fy.theme == "dei"]
    g = f.groupby("year").agg(web=("say_p1_salience", "mean"), proxy=("say_p2_fv_rate", "mean"),
                              pay=("do_present", "sum"))
    g.loc[g.index > 2024, "web"] = float("nan")  # no website pass for 2025-2026

    plt.rcParams.update({"font.size": 11})
    fig, ax = plt.subplots(figsize=(10, 5.6))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.axvspan(2024.5, 2026.5, color=GRID, alpha=0.5, lw=0, zorder=0)
    ax.text(2025.5, 58, "proxies\npublished\nafter the\nbacklash", ha="center", va="center",
            color=MUTED, fontsize=9)

    series = [
        ("web", "Company websites:\nDEI emphasis", BLUE),
        ("proxy", "Proxy statements:\nDEI language", AQUA),
        ("pay", "Executive pay: companies\nwith a DEI bonus goal\n(3 in 2026)", ORANGE),
    ]
    for col, label, color in series:
        s = g[col].dropna()
        pct = s / s.max() * 100
        ax.plot(pct.index, pct.values, color=color, lw=2.4, marker="o", ms=5, mec=SURFACE, mew=1.2, zorder=3)
        ax.text(pct.index[-1] + 0.15, pct.values[-1] + END_OFFSET[col], label, color=INK2, fontsize=9.5,
                va="center")

    for x, label, y, align in EVENTS:
        ax.axvline(x, color=MUTED, lw=1, ls=(0, (3, 3)), zorder=1)
        dx = 0.07 if align == "left" else -0.07
        ax.text(x + dx, y, label, color=INK2, fontsize=8.5, va="center", ha=align)

    # Real numbers for the pay line, where the story turns.
    for yr, va, dy in ((2023, "bottom", 5),):
        n = int(g.loc[yr, "pay"])
        ax.annotate(f"{n} companies", (yr, g.loc[yr, "pay"] / g.pay.max() * 100), xytext=(0, dy),
                    textcoords="offset points", ha="center", va=va, color=ORANGE, fontsize=9, fontweight="bold")

    ax.set_xlim(2015.6, 2028.6)
    ax.set_ylim(0, 136)
    ax.set_xticks(range(2016, 2027, 2))
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%\n(peak)"])
    ax.set_ylabel("Level, as % of each line's own peak year", color=INK2)
    ax.set_xlabel("Year (proxy statements by year filed; websites as of July)", color=INK2)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK2)
    ax.grid(axis="y", color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    fig.suptitle("DEI after the backlash: proxy statements went quiet first,\nexecutive pay followed a year or "
                 "two later", x=0.02, ha="left", fontsize=13, fontweight="bold", color=INK)
    fig.text(0.02, 0.855, "DEI in 50 large US companies: what they say (websites, proxy statements) "
             "vs what executive pay rewards", ha="left", fontsize=10, color=INK2)
    fig.text(0.02, 0.015, "Websites were collected through July 2024 only. Pay goals in a year's proxy were set "
             "the year before.", ha="left", fontsize=8.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 0.84))
    out = OUT / "figures" / "dei_say_vs_do_summary.png"
    fig.savefig(out, dpi=160)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
