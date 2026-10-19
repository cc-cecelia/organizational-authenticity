"""Year-trend small multiples by sector, annotated with external events.

Usage: python part2_lived_values/src/plot_trends.py   (after text_measures.py)

Two figures (output/analysis/figures/):
  trends_firm_voice.png  fv_rate_*: what the firm itself says in the proxy
  trends_cda.png         cda_rate_*: what it says when explaining pay
One panel per stakeholder category; one line per sector (equal-weight firm
mean; labelled with the ticker when a sector has one firm, as in the
pilot). An event is drawn only on the panels of the categories it is
expected to move (events.py), at the median filing year in which the
sample's firms first filed a proxy after it (firm_event_exposure.csv).
Colours follow the sector in a fixed order (validated default categorical
palette slots 1-5), and every line is direct-labelled, so identity never
depends on colour alone.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config
import events
from theme_dictionary import CATEGORIES

SECTOR_ORDER = ["Technology", "Financials", "Healthcare", "Consumer Discretionary", "Energy"]
SECTOR_COLORS = dict(zip(SECTOR_ORDER, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]))
INK, INK2, MUTED, GRID, BASE, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
EVENT_SHORT = {
    "racial_justice_2020": "E1 Racial justice", "sec_human_capital_2020": "E2 SEC human capital",
    "nasdaq_board_diversity_2021": "E3 Nasdaq diversity", "engine_no1_xom_2021": "E4 Engine No. 1",
    "esg_backlash_2022": "E5 ESG backlash", "sffa_2023": "E6 SFFA",
}


SECTOR_SHORT = {"Technology": "Tech", "Financials": "Fin", "Healthcare": "Health",
                "Consumer Discretionary": "Cons. Disc.", "Energy": "Energy"}


def end_label(sector: str, label: str) -> str:
    """Ticker for a one-firm sector (pilot), short sector name otherwise."""
    inner = label.split(" (")[-1].rstrip(")")
    return SECTOR_SHORT[sector] if inner.startswith("n=") else inner


def sector_lines(m: pd.DataFrame, col: str) -> dict:
    out = {}
    for sector in SECTOR_ORDER:
        g = m[m["sector"] == sector]
        if g.empty:
            continue
        tickers = sorted(g["ticker"].unique())
        label = f"{sector} ({tickers[0]})" if len(tickers) == 1 else f"{sector} (n={len(tickers)})"
        out[sector] = (label, g.groupby("filing_year")[col].mean())
    return out


def event_years() -> dict:
    ex = pd.read_csv(config.ANALYSIS_DIR / "firm_event_exposure.csv")
    return ex.groupby("event_id")["first_exposed_filing_year"].median().round().astype(int).to_dict()


def draw(m: pd.DataFrame, prefix: str, title: str, path) -> None:
    ev_year = event_years()
    ev_by_cat = {c: [] for c in CATEGORIES}
    for e, _, _, cats, _ in events.EVENTS:
        for c in cats:
            ev_by_cat[c].append(e)

    fig, axes = plt.subplots(3, 3, figsize=(13, 10.5), sharex=True)
    fig.patch.set_facecolor(SURFACE)
    years = sorted(m["filing_year"].unique())
    for ax, cat in zip(axes.flat, CATEGORIES):
        ax.set_facecolor(SURFACE)
        lines = sector_lines(m, f"{prefix}rate_{cat}")
        ymax = max(s.max() for _, s in lines.values()) * 1.18
        # Events: recessive dashed hairlines, short code at the top.
        for i, e in enumerate(sorted(ev_by_cat[cat], key=lambda e: ev_year.get(e, 0))):
            x = ev_year.get(e)
            if x is None:
                continue
            ax.axvline(x, color=BASE, lw=1, ls=(0, (3, 3)), zorder=1)
            ax.text(x + 0.05, ymax * (0.97 - 0.07 * i), EVENT_SHORT[e].split(" ")[0],
                    fontsize=7.5, color=MUTED, va="top")
        for sector, (label, s) in lines.items():
            ax.plot(s.index, s.values, color=SECTOR_COLORS[sector], lw=2, zorder=3,
                    marker="o", ms=4, markeredgecolor=SURFACE, markeredgewidth=1)
        # Direct labels at line ends, nudged apart so they never overlap.
        ends = sorted(((s.values[-1], s.index[-1], end_label(sector, lab))
                       for sector, (lab, s) in lines.items()))
        gap, prev = ymax * 0.065, None
        for y, x, text in ends:
            y = y if prev is None else max(y, prev + gap)
            ax.text(x + 0.15, y, text, fontsize=7.5, color=INK2, va="center")
            prev = y
        ax.set_title(cat, loc="left", fontsize=11, color=INK, fontweight="bold")
        ax.set_ylim(0, ymax)
        ax.set_xlim(years[0] - 0.3, years[-1] + 0.9)
        ax.set_xticks(years[::2])
        ax.grid(axis="y", color=GRID, lw=0.6)
        ax.tick_params(colors=MUTED, labelsize=8, length=0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(BASE)

    handles = [plt.Line2D([], [], color=SECTOR_COLORS[s], lw=2, label=lab)
               for s, (lab, _) in sector_lines(m, f"{prefix}rate_{CATEGORIES[0]}").items()]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.06, 0.955), ncol=5,
               frameon=False, fontsize=9, labelcolor=INK2)
    fig.suptitle(title, x=0.06, y=0.985, ha="left", fontsize=14, color=INK, fontweight="bold")
    ev_note = "   ".join(f"{EVENT_SHORT[e]} ({ev_year.get(e)})" for e, *_ in events.EVENTS)
    fig.text(0.06, 0.015, "Hits per 10,000 prose words, by proxy filing year. Dashed lines: events, "
             "shown on the categories they are expected to move, at the median first filing year after "
             "the event.\n" + ev_note, fontsize=8, color=MUTED, ha="left")
    fig.tight_layout(rect=(0.04, 0.05, 1, 0.935))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)
    print(f"wrote {path}")


def main() -> int:
    m = pd.read_csv(config.ANALYSIS_DIR / "text_measures.csv")
    figs = config.ANALYSIS_DIR / "figures"
    draw(m, "fv_", "Stakeholder language in proxy statements (firm voice, excl. shareholder proposals)",
         figs / "trends_firm_voice.png")
    draw(m, "cda_", "Stakeholder language in the CD&A (how firms explain executive pay)",
         figs / "trends_cda.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
