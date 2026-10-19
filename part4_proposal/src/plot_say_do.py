"""Say vs do year trends for DEI and environment, 2016-2026.

Usage: python part4_proposal/src/plot_say_do.py   (after say_do.py)

One panel per theme. Three series, each indexed to its own 2021-2022 mean
(= 100), because they sit on incomparable scales (0-3 salience, hits per 10k
words, firm counts) and a dual axis would mislead:
  say: page salience (Part 1, mean over firms; 2016-2024 only)
  say: proxy firm voice (Part 2, mean hits per 10k words)
  do:  firms with a pay-linked criterion (Part 2; count of firm-years)
2025-2026 come from Part 2's out-of-sample extension (shaded). Event markers
are Part 2's, placed at the median filing year in which the sample's firms
first filed a proxy after the event, and shown on the theme they are
expected to move. Colours: validated default categorical slots 1-3; every
line is direct-labelled.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from say_do import OUT, REPO

INK, INK2, MUTED, GRID, BASE, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
SERIES = [("say_p1_salience", "Say: page salience", "#2a78d6", "mean"),
          ("say_p2_fv_rate", "Say: proxy firm voice", "#1baf7a", "mean"),
          ("do_present", "Do: firms paying for it", "#eb6834", "sum")]
SHORT = {"racial_justice_2020": "E1", "sec_human_capital_2020": "E2", "nasdaq_board_diversity_2021": "E3",
         "engine_no1_xom_2021": "E4", "esg_backlash_2022": "E5", "sffa_2023": "E6"}


def series(fy: pd.DataFrame, theme: str) -> pd.DataFrame:
    f = fy[fy["theme"] == theme]
    out = {}
    for col, _, _, how in SERIES:
        g = f.groupby("year")[col]
        s = g.sum(min_count=1) if how == "sum" else g.mean()
        out[col] = s
    df = pd.DataFrame(out)
    base = df.loc[[2021, 2022]].mean()
    return df, (df / base * 100)


def main() -> int:
    fy = pd.read_csv(OUT / "say_do_firm_year.csv")
    ev = pd.read_csv(REPO / "part2_lived_values/output/analysis/events.csv")
    ex = pd.read_csv(REPO / "part2_lived_values/output/analysis/firm_event_exposure.csv")
    ev_year = ex.groupby("event_id")["first_exposed_filing_year"].median().round().astype(int).to_dict()

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), sharey=False)
    fig.patch.set_facecolor(SURFACE)
    raw_rows = []
    for ax, theme in zip(axes, ["dei", "environment"]):
        raw, idx = series(fy, theme)
        raw_rows.append(raw.assign(theme=theme))
        ax.set_facecolor(SURFACE)
        ax.axvspan(2024.5, 2026.5, color=GRID, alpha=0.45, lw=0, zorder=0)
        ax.text(2025.5, 0.02, "out-of-sample\nfilings", transform=ax.get_xaxis_transform(),
                ha="center", va="bottom", fontsize=7.5, color=MUTED)
        ax.axhline(100, color=BASE, lw=0.8, zorder=1)
        cats = {e: c for e, c in zip(ev.event_id, ev.expected_categories)}
        k = 0
        for e in sorted(ev.event_id, key=lambda e: ev_year.get(e, 0)):
            if theme not in cats[e].split(";") or e not in ev_year:
                continue
            x = ev_year[e]
            ax.axvline(x, color=BASE, lw=1, ls=(0, (3, 3)), zorder=1)
            ax.text(x + 0.06, 0.97 - 0.07 * k, SHORT[e], transform=ax.get_xaxis_transform(),
                    fontsize=7.5, color=MUTED, va="top")
            k += 1
        ends = []
        for col, label, color, _ in SERIES:
            s = idx[col].dropna()
            ax.plot(s.index, s.values, color=color, lw=2, marker="o", ms=4,
                    markeredgecolor=SURFACE, markeredgewidth=1, zorder=3)
            ends.append((s.values[-1], s.index[-1], label))
        ymax = ax.get_ylim()[1]
        prev = None
        for y, x, label in sorted(ends):
            y = y if prev is None else max(y, prev + ymax * 0.06)
            ax.text(x + 0.15, y, label, fontsize=7.5, color=INK2, va="center")
            prev = y
        ax.set_title("DEI" if theme == "dei" else "Environment", loc="left", fontsize=12, color=INK, fontweight="bold")
        ax.set_xlim(2015.6, 2028.6)
        ax.set_xticks(range(2016, 2027, 2))
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", color=GRID, lw=0.6)
        ax.tick_params(colors=MUTED, labelsize=8, length=0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(BASE)
    fig.suptitle("After the backlash: what firms say vs what they pay for", x=0.05, y=0.98, ha="left",
                 fontsize=14, color=INK, fontweight="bold")
    items = [f"{SHORT[e]} {lab.split(' (')[0]} ({ev_year.get(e)})" for e, lab in zip(ev.event_id, ev.label)]
    note = "   ".join(items[:3]) + "\n" + "   ".join(items[3:])
    fig.text(0.05, 0.015, "Each series indexed to its 2021-2022 mean = 100. By filing year (pages: mid-year snapshot). "
             "Page salience ends in 2024 (no Wayback pass for the extension).\n" + note, fontsize=7.5, color=MUTED)
    fig.tight_layout(rect=(0.02, 0.09, 1, 0.94))
    path = OUT / "figures/say_vs_do_trends.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    pd.concat(raw_rows).reset_index().to_csv(OUT / "say_do_trends.csv", index=False)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
