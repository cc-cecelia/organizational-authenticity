"""Summary figure for a non-technical reader: companies differ more from each
other than they change over time.

Usage: .venv/bin/python part3_authenticity_index/src/plot_summary_figure.py
Output: part3_authenticity_index/output/figures/firms_vs_years_summary.png

Reads output/authenticity_index.csv. Of the companies with at least 5 scored
years (45), the 10 highest and 10 lowest are shown, one row each: the dot is
its average score, the bar spans its lowest to highest yearly score. The shaded band is the range of the all-company
average across the nine years (2016-2024), which barely moves. Single series
(slot-1 blue), so no legend; the title names it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
INDEX_CSV = ROOT / "part3_authenticity_index" / "output" / "authenticity_index.csv"
OUT = ROOT / "part3_authenticity_index" / "output" / "figures" / "firms_vs_years_summary.png"
INK, INK2, MUTED, GRID, SURFACE, BLUE, BAND = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb", \
    "#2a78d6", "#f0eee6"
MIN_YEARS = 5
SHOW_N = 10   # highest and lowest companies shown
SHORT = {"JPMorgan Chase": "JPMorgan", "Thermo Fisher Scientific": "Thermo Fisher",
         "SLB (Schlumberger)": "SLB", "Bristol-Myers Squibb": "Bristol Myers Squibb",
         "Marathon Petroleum": "Marathon Petroleum", "Occidental Petroleum": "Occidental",
         "Abbott Laboratories": "Abbott", "UnitedHealth Group": "UnitedHealth"}


def main() -> int:
    d = pd.read_csv(INDEX_CSV)
    ok = d[d.A.notna()]
    f = ok.groupby(["ticker", "company_name"]).A.agg(["mean", "min", "max", "size"]).reset_index()
    f = f[f["size"] >= MIN_YEARS].sort_values("mean").reset_index(drop=True)
    n_all = len(f)
    years = ok.groupby("year").A.mean()
    # Bottom 10, a gap row, then top 10 (rows are plotted bottom-up).
    f = pd.concat([f.head(SHOW_N), f.tail(SHOW_N)]).reset_index(drop=True)
    ypos = list(range(SHOW_N)) + [i + 1 for i in range(SHOW_N, 2 * SHOW_N)]

    plt.rcParams.update({"font.size": 10})
    fig, ax = plt.subplots(figsize=(8.6, 7.4))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.axvspan(years.min(), years.max(), color=BAND, lw=0, zorder=0)
    ax.text((years.min() + years.max()) / 2, ypos[-1] + 1.0,
            f"All-company average,\nevery year 2016–2024:\n{years.min():.2f} to {years.max():.2f}",
            ha="center", va="bottom", fontsize=9, color=INK2)
    for (_, r), y in zip(f.iterrows(), ypos):
        ax.plot([r["min"], r["max"]], [y, y], color=BLUE, alpha=0.35, lw=3, solid_capstyle="round", zorder=2)
        ax.plot(r["mean"], y, "o", color=BLUE, ms=6.5, mec=SURFACE, mew=1.2, zorder=3)
    ax.text(0.5, SHOW_N, f"· · ·  {n_all - 2 * SHOW_N} companies in between  · · ·", ha="center", va="center",
            fontsize=9, color=MUTED, bbox=dict(facecolor=SURFACE, edgecolor="none", pad=2), zorder=4)
    ax.set_yticks(ypos)
    ax.set_yticklabels([SHORT.get(n, n) for n in f.company_name], fontsize=9, color=INK2)
    ax.set_ylim(-0.8, ypos[-1] + 4.2)
    ax.set_xlim(-0.02, 1.02)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1])
    ax.set_xticklabels(["0\nnothing stated\nis paid for", "0.25", "0.5", "0.75", "1\neverything stated\nis paid for"])
    ax.tick_params(colors=INK2, length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.grid(axis="x", color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    ax.set_xlabel("Authenticity score: share of what the values page emphasizes that executive pay also rewards",
                  color=INK2, fontsize=9.5)
    fig.text(0.03, 0.99, "Companies differ more from each other than they change over time", ha="left",
             va="top", fontsize=13.5, fontweight="bold", color=INK)
    fig.text(0.03, 0.945, f"The 10 highest and 10 lowest of {n_all} companies with at least {MIN_YEARS} years "
             "of data. Dot = average score, bar = lowest to highest year.\nAverages run from "
             f"{f['mean'].min():.2f} to {f['mean'].max():.2f}, while the all-company average (shaded) stayed "
             f"between {years.min():.2f} and {years.max():.2f} every year.\nSingle years can still swing widely "
             "when a page or a pay plan changes.", ha="left", va="top", fontsize=9.3, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=160)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
