"""
Part 3 analysis of the authenticity index: distribution, sensitivity to tau,
validity checks. Reads output/authenticity_index.csv (build_index.py).

Usage (from repo root):
    .venv/bin/python part3_authenticity_index/src/analyze.py

Writes output/analysis/*.csv, output/figures/*.png and output/analysis/results.md
(the numbers quoted in the README).
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.formula.api as smf  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "part3_authenticity_index" / "output"
AN, FIG = OUT / "analysis", OUT / "figures"
TAUS = ["tau0", "tau5", "tau10", "tau20"]
MIN_N = 5   # firms with fewer firm-years are flagged in every ranking table
TAU_LABEL = {"tau0": "τ→0", "tau5": "τ=5%", "tau10": "τ=10%", "tau20": "τ=20%"}

# Reference palette (dataviz skill, light mode): surface, text tokens, slot-1 blue.
SURFACE, INK, INK2, GRID, BLUE = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
    "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
})


def md_table(df: pd.DataFrame, floatfmt: str = ".2f") -> str:
    """Small markdown table without the tabulate dependency."""
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    # astype(object) keeps ints as ints (iterrows on mixed dtypes coerces to float).
    for _, r in df.astype(object).iterrows():
        cells = [format(v, floatfmt) if isinstance(v, (float, np.floating)) and pd.notna(v)
                 else ("" if pd.isna(v) else str(v)) for v in r]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def distribution(ok: pd.DataFrame, res: list) -> None:
    desc = ok[["A", "A_ex_shareholders", "unstated_backing"] + [f"A_{t}" for t in TAUS[1:]]].describe(
        percentiles=[.1, .25, .5, .75, .9]).T.round(3)
    desc.to_csv(AN / "distribution.csv")
    res += ["## Distribution", f"Firm-years with A: {len(ok)}; firms: {ok.ticker.nunique()}.", "",
            md_table(desc.reset_index().rename(columns={"index": "measure"}), ".3f"), ""]

    by_sector = ok.groupby("sector").agg(n=("A", "size"), firms=("ticker", "nunique"), mean_A=("A", "mean"),
                                         median_A=("A", "median"), mean_A_ex_sh=("A_ex_shareholders", "mean"),
                                         mean_unstated=("unstated_backing", "mean")).round(3).reset_index()
    by_year = ok.groupby("year").agg(n=("A", "size"), mean_A=("A", "mean"), median_A=("A", "median"),
                                     mean_A_ex_sh=("A_ex_shareholders", "mean"),
                                     mean_unstated=("unstated_backing", "mean")).round(3).reset_index()
    by_sector.to_csv(AN / "by_sector.csv", index=False)
    by_year.to_csv(AN / "by_year.csv", index=False)
    res += ["### By sector", md_table(by_sector, ".3f"), "", "### By year", md_table(by_year, ".3f"), ""]

    # Histogram (single series: no legend; the title names it).
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    ax.hist(ok.A, bins=np.linspace(0, 1, 21), color=BLUE, edgecolor=SURFACE, linewidth=2)
    ax.set_title("Authenticity index A (τ→0), all firm-years")
    ax.set_xlabel("A: share of stated emphasis backed by pay-linked criteria")
    ax.set_ylabel("Firm-years")
    ax.grid(axis="x", visible=False)
    fig.tight_layout(); fig.savefig(FIG / "hist_A.png", dpi=160); plt.close(fig)

    # By sector and by year: firm-year dots plus the median as a short bar.
    for key, fname, title in (("sector", "A_by_sector.png", "A by sector"),
                              ("year", "A_by_year.png", "A by year")):
        groups = sorted(ok[key].unique())
        fig, ax = plt.subplots(figsize=(6.4, 3.4 if key == "year" else 3.0))
        rng = np.random.default_rng(0)
        for i, g in enumerate(groups):
            v = ok.loc[ok[key] == g, "A"].to_numpy()
            if key == "sector":
                ax.scatter(v, i + rng.uniform(-.15, .15, len(v)), s=14, color=BLUE, alpha=.55, linewidths=0)
                ax.plot([np.median(v)] * 2, [i - .3, i + .3], color=INK, lw=2, solid_capstyle="round")
            else:
                ax.scatter(i + rng.uniform(-.15, .15, len(v)), v, s=14, color=BLUE, alpha=.55, linewidths=0)
                ax.plot([i - .3, i + .3], [np.median(v)] * 2, color=INK, lw=2, solid_capstyle="round")
        if key == "sector":
            ax.set_yticks(range(len(groups)), groups); ax.set_xlim(-.02, 1.02); ax.set_xlabel("A (τ→0)")
            ax.grid(axis="y", visible=False)
        else:
            ax.set_xticks(range(len(groups)), groups); ax.set_ylim(-.02, 1.02); ax.set_ylabel("A (τ→0)")
            ax.grid(axis="x", visible=False)
        ax.set_title(f"{title} (dots = firm-years, bar = median)")
        fig.tight_layout(); fig.savefig(FIG / fname, dpi=160); plt.close(fig)


def flag_n(n) -> str:
    return f"n<{MIN_N}" if n < MIN_N else ""


def firm_ranking(ok: pd.DataFrame, res: list) -> None:
    """Firm means of the primary index, with the number of firm-years behind each."""
    f = ok.groupby(["ticker", "sector"]).agg(n=("A", "size"), mean_A=("A", "mean"),
                                             mean_A_ex_sh=("A_ex_shareholders", "mean"),
                                             mean_unstated=("unstated_backing", "mean")).reset_index()
    f["flag"] = f.n.map(flag_n)
    f = f.sort_values("mean_A").round(3)
    f.to_csv(AN / "firm_ranking.csv", index=False)
    res += ["## Firm ranking (mean A over firm-years)",
            f"Firms flagged `n<{MIN_N}` rest on fewer than {MIN_N} firm-years; read their position with caution.",
            "", "Lowest 8:", "", md_table(f.head(8), ".3f"), "", "Highest 8:", "",
            md_table(f.tail(8).iloc[::-1], ".3f"), ""]


def sensitivity(ok_all: pd.DataFrame, res: list) -> None:
    """Rank firms by mean A over the firm-years where every tau is defined."""
    common = ok_all.dropna(subset=[f"A_{t}" for t in TAUS])
    res += ["## Sensitivity to τ",
            f"Compared on the {len(common)} firm-years ({common.ticker.nunique()} firms) where all four τ values "
            "are defined (the weighted versions need disclosed or imputed weights).", ""]
    if common.ticker.nunique() < 3:
        res += ["Too few firms with weights for a rank comparison yet.", ""]
        return
    firm = common.groupby("ticker")[[f"A_{t}" for t in TAUS]].mean()
    n_obs = common.groupby("ticker").size()
    rho = pd.DataFrame(index=TAUS, columns=TAUS, dtype=float)
    for a in TAUS:
        for b in TAUS:
            rho.loc[a, b] = spearmanr(firm[f"A_{a}"], firm[f"A_{b}"]).correlation
    rho = rho.round(3)
    rho.to_csv(AN / "spearman_tau.csv")
    res += ["Spearman rank correlation of firm rankings (firm mean A):", "",
            md_table(rho.rename(index=TAU_LABEL, columns=TAU_LABEL).reset_index().rename(columns={"index": ""}),
                     ".3f"), ""]
    ranks = firm.rank(ascending=False)
    drop = pd.DataFrame({"rank_tau0": ranks.A_tau0, "rank_tau20": ranks.A_tau20,
                         "rank_drop": ranks.A_tau20 - ranks.A_tau0,
                         "A_tau0": firm.A_tau0.round(3), "A_tau20": firm.A_tau20.round(3),
                         "n": n_obs, "flag": n_obs.map(flag_n)}
                        ).sort_values("rank_drop", ascending=False)
    drop.to_csv(AN / "rank_drop_tau.csv")
    res += ["Firms whose rank drops most as τ rises (token coverage: pay criteria exist but carry little weight):",
            "", md_table(drop.head(10).reset_index(), ".3f"), ""]

    # Distribution of A by tau (single series).
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    for i, t in enumerate(TAUS):
        v = common[f"A_{t}"].to_numpy()
        ax.scatter(np.full(len(v), i) + np.random.default_rng(i).uniform(-.12, .12, len(v)), v,
                   s=14, color=BLUE, alpha=.55, linewidths=0)
        ax.plot([i - .3, i + .3], [np.median(v)] * 2, color=INK, lw=2, solid_capstyle="round")
    ax.set_xticks(range(len(TAUS)), [TAU_LABEL[t] for t in TAUS])
    ax.set_ylim(-.02, 1.02); ax.set_ylabel("A"); ax.grid(axis="x", visible=False)
    ax.set_title("A by materiality threshold τ (dots = firm-years, bar = median)")
    fig.tight_layout(); fig.savefig(FIG / "A_by_tau.png", dpi=160); plt.close(fig)


def robustness_stated_weights(ok: pd.DataFrame, res: list) -> None:
    """Weighted index from stated weights only (disclosed, derived_from_stated_split) vs all weights."""
    c = ok.dropna(subset=["A_strict_tau10", "A_tau10"])
    res += ["## Robustness: stated weights only",
            "The weighted index recomputed with only `disclosed` and `derived_from_stated_split` weights "
            f"(Part 2's `imputed_emphasis` estimates excluded). Defined for {len(c)} firm-years, "
            f"{c.ticker.nunique()} firms. Rankings compared on the same firm-years.", ""]
    if c.ticker.nunique() < 3:
        res += ["Too few firms.", ""]
        return
    f = c.groupby("ticker").agg(n=("A", "size"), A_tau0=("A", "mean"), A_tau10_all=("A_tau10", "mean"),
                                A_tau10_stated=("A_strict_tau10", "mean"),
                                A_tau20_all=("A_tau20", "mean"), A_tau20_stated=("A_strict_tau20", "mean"))
    rho = {
        "τ=10%: all weights vs stated only": spearmanr(f.A_tau10_all, f.A_tau10_stated).correlation,
        "τ=20%: all weights vs stated only": spearmanr(f.A_tau20_all, f.A_tau20_stated).correlation,
        "τ→0 vs τ=10% stated only": spearmanr(f.A_tau0, f.A_tau10_stated).correlation,
    }
    f["rank_all"] = f.A_tau10_all.rank(ascending=False)
    f["rank_stated"] = f.A_tau10_stated.rank(ascending=False)
    f["flag"] = f.n.map(flag_n)
    f = f.sort_values("rank_stated").round(3)
    f.to_csv(AN / "robustness_stated_weights.csv")
    res += [md_table(pd.DataFrame({"comparison": list(rho), "spearman": list(rho.values())}), ".3f"), "",
            "Firm means (τ = 10%):", "", md_table(f.reset_index(), ".3f"), ""]


def other_residual(res: list) -> None:
    """Documented residual: proxy-years with >= 5% of the bonus in `other` (no stakeholder)."""
    panel = pd.read_csv(ROOT / "part2_lived_values" / "output" / "lived_values_panel.csv")
    met = pd.read_csv(ROOT / "part2_lived_values" / "output" / "analysis" / "incentive_metrics.csv")
    r = panel[panel.cat_weight_other >= 0.05][["ticker", "year", "weight_source", "cat_weight_other"]].copy()
    oth = (met[(met.category == "other") & (met.plan == "annual_incentive") & (met.applies_to == "reported_year")]
           .groupby(["ticker", "filing_year"]).metric.apply(lambda m: "; ".join(dict.fromkeys(m)))
           .rename("other_criteria").reset_index().rename(columns={"filing_year": "year"}))
    r = r.merge(oth, on=["ticker", "year"], how="left").sort_values(["ticker", "year"])
    r.to_csv(AN / "other_residual.csv", index=False)
    n_w = int(panel[[c for c in panel.columns if c.startswith("cat_weight_")
                     and not c.startswith("cat_weight_lti")]].notna().any(axis=1).sum())
    by_firm = r.groupby("ticker").agg(years=("year", "size"), mean_other=("cat_weight_other", "mean"),
                                      example=("other_criteria", "first")).reset_index()
    by_firm["example"] = by_firm.example.fillna("").str.slice(0, 80)
    res += ["## Residual: bonus weight on criteria with no stakeholder (`other` >= 5%)",
            f"{len(r)} of {n_w} proxy-years with weights put >= 5% of the bonus on criteria that fit no "
            f"stakeholder ({r.ticker.nunique()} firms; full list in `other_residual.csv`). These weights are not "
            "counted toward any category, so they lower weighted coverage only by leaving less weight for "
            "stakeholders; they are not unresolved splits.", "",
            md_table(by_firm.sort_values("mean_other", ascending=False), ".2f"), ""]


def validity(d: pd.DataFrame, ok: pd.DataFrame, res: list) -> None:
    res += ["## Validity", "### Known groups"]
    for t, k, years, expect in (("WFC", "customers", range(2016, 2025), "low coverage 2016-2018"),
                                ("XOM", "environment", range(2016, 2025), "coverage jumps from 2022")):
        x = d[(d.ticker == t) & d.year.isin(years)][["year", f"s_{k}", f"d_{k}", f"cov_{k}", f"w_{k}", "A",
                                                      "A_tau10", "A_reason"]].copy()
        # Weighted coverage at the headline tau = 10%: min(w / 0.10, 1).
        x.insert(5, f"cov10_{k}", (x[f"w_{k}"] / 0.10).clip(upper=1.0))
        x.to_csv(AN / f"known_group_{t}_{k}.csv", index=False)
        res += [f"**{t} {k}** (expected: {expect}). `s` = stated salience, `d` = pay-linked criteria and "
                "`w` = plan weight (max over proxies t and t+1), `cov` = coverage indicator (τ→0), "
                "`cov10` = weighted coverage at τ = 10%:", "", md_table(x, ".2f"), ""]

    # WFC, every category: stated salience / coverage (tau -> 0) / weighted coverage at tau = 10%.
    import sys as _s
    _s.path.insert(0, str(ROOT / "part2_lived_values" / "src"))
    from theme_dictionary import CATEGORIES
    wfc = d[d.ticker == "WFC"].sort_values("year")
    rows = []
    for _, r in wfc.iterrows():
        row = {"year": int(r.year), "page_type": r.page_type, "A": r.A}
        for k in CATEGORIES:
            cov10 = min(r[f"w_{k}"] / 0.10, 1.0) if pd.notna(r[f"w_{k}"]) else np.nan
            row[k] = (f"{int(r[f's_{k}'])}/{int(r[f'cov_{k}'])}" if pd.notna(r[f"cov_{k}"]) else "")\
                + (f"/{cov10:.1f}" if pd.notna(cov10) else "")
        rows.append(row)
    wt = pd.DataFrame(rows)
    wt.to_csv(AN / "known_group_WFC_all_categories.csv", index=False)
    res += ["**WFC, every category** (cell = stated salience / coverage τ→0 / weighted coverage τ=10%):", "",
            md_table(wt, ".2f"), ""]

    res += ["### Discriminant check", "OLS of A (τ→0) on page type, log page word count and sector, "
            "standard errors clustered by firm. A valid alignment measure should not be explained by "
            "which page was scraped or how long it is.", ""]
    m = ok.dropna(subset=["A", "page_type", "word_count"]).copy()
    m["log_words"] = np.log(m.word_count)
    if m.ticker.nunique() < 4 or m.sector.nunique() < 2:
        res += [f"Not estimable yet: {m.ticker.nunique()} firms and {m.sector.nunique()} sectors with A.", ""]
        return
    fit = smf.ols("A ~ C(page_type) + log_words + C(sector)", data=m).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(m.ticker)[0]})
    tab = pd.DataFrame({"coef": fit.params, "se": fit.bse, "p": fit.pvalues}).round(3)
    tab.to_csv(AN / "discriminant_ols.csv")
    res += [md_table(tab.reset_index().rename(columns={"index": "term"}), ".3f"), "",
            f"R² = {fit.rsquared:.3f} (adj. {fit.rsquared_adj:.3f}), n = {int(fit.nobs)} firm-years, "
            f"{m.ticker.nunique()} firms.", ""]


def main() -> int:
    AN.mkdir(parents=True, exist_ok=True); FIG.mkdir(parents=True, exist_ok=True)
    d = pd.read_csv(OUT / "authenticity_index.csv")
    ok = d[d.A.notna()]
    res = ["# Part 3 results (generated by src/analyze.py; do not edit by hand)", "",
           "NaN reasons for A: " + ", ".join(f"{k or 'computed'} {v}" for k, v in
                                             d.A_reason.fillna("").value_counts().items()), ""]
    distribution(ok, res)
    firm_ranking(ok, res)
    sensitivity(ok, res)
    robustness_stated_weights(ok, res)
    other_residual(res)
    validity(d, ok, res)
    (AN / "results.md").write_text("\n".join(res))
    print("\n".join(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
