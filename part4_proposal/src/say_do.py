"""Part 4: did firms retreat in what they SAY, what they DO, or both, after the
2023 backlash (SFFA ruling, anti-DEI and anti-ESG pressure)?

Usage: python part4_proposal/src/say_do.py

Reads only other parts' outputs (never edits them):
  part1_stated_values/output/stated_values.csv      say: About/values page salience (0-3)
  part2_lived_values/output/lived_values_panel.csv  say: proxy firm-voice rate; do: pay criteria, weights
  part3_authenticity_index/output/authenticity_index.csv   unstated_backing, s_<k>, d_<k>

Writes part4_proposal/output/:
  say_do_firm_year.csv   one row per firm x year x theme (dei, environment)
  quadrants.csv          one row per firm x theme x specification: pre/post means,
                         per-measure verdicts, say/do verdicts, quadrant
  quadrant_counts.csv    quadrant counts by theme, specification and sector

Windows: pre = 2021-2022, post = 2023-2024 (filing / page years).
Specification "main" uses these windows on both sides. "lag" shifts the do
side to fiscal timing: a proxy filed in year t reports pay for fiscal t-1,
so the do side compares the 2022 filing (fiscal 2021) with the 2024 filing
(fiscal 2023, the first pay cycle decided after SFFA). "imputed_weights" is
"main" but lets imputed weights vote on the do side (sensitivity only).
"ext" is the out-of-sample timing test: 2021-2022 vs 2025-2026 filings (Part 2
extension), say = proxy firm voice only, do = pay-linked criterion present.

Verdict per measure (pre -> post):
  P1 salience      cut if mean falls >= 0.5 points (0-3 scale), rise if rises >= 0.5
  P2 firm voice    cut if falls >= 25% relative,  rise if rises >= 25%
  do present       cut if the share of years with >=1 pay-linked criterion falls >= 0.5,
                   rise if it rises >= 0.5
  do weight        cut if cat_weight falls >= 50% relative (pre >= 1 pp), rise if rises >= 50%
                   (or from 0 to >= 1 pp); counted only where weights are disclosed or
                   derived from a stated split, except in the imputed_weights spec
A side is "cut" if any of its measures is cut and none rose; "rise" if any rose
and none was cut; "conflict" if its measures disagree; otherwise "kept".
A firm is eligible for the quadrant if it had something to cut on both sides
in the pre window (say > 0 on some say measure, a pay-linked criterion in some
pre year). Quadrants (eligible firms): kept_both, cut_say_only
(quiet retention), cut_do_only, cut_both; plus "conflict" when either side
conflicts.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "part4_proposal" / "output"
THEMES = ["dei", "environment"]
PRE, POST = (2021, 2022), (2023, 2024)
LAG_PRE, LAG_POST = (2022,), (2024,)
EXT_POST = (2025, 2026)          # out-of-sample timing test (Part 2 extension)
EXT_DIR = REPO / "part2_lived_values/output/extension_2025_2026"

P1_ABS = 0.5      # salience points on the 0-3 scale
P2_REL = 0.25     # relative change in firm-voice rate
PRESENT_ABS = 0.5
W_REL, W_MIN = 0.50, 0.01


def load() -> pd.DataFrame:
    p1 = pd.read_csv(REPO / "part1_stated_values/output/stated_values.csv")
    p2 = pd.read_csv(REPO / "part2_lived_values/output/lived_values_panel.csv")
    p3 = pd.read_csv(REPO / "part3_authenticity_index/output/authenticity_index.csv")
    rows = []
    p1 = p1[p1["status"] == "ok"].set_index(["ticker", "year"])
    p3 = p3.set_index(["ticker", "year"])
    for r in p2.itertuples():
        k = (r.ticker, r.year)
        for th in THEMES:
            weight = getattr(r, f"cat_weight_{th}")
            rows.append({
                "ticker": r.ticker, "sector": r.sector, "year": r.year, "theme": th,
                "say_p1_salience": p1[f"sal_{th}"].get(k, np.nan),
                "page_type": p1["page_type"].get(k, np.nan),
                "say_p2_fv_rate": getattr(r, f"fv_rate_{th}"),
                "do_present": (float(getattr(r, f"pay_n_{th}") > 0)
                               if pd.notna(getattr(r, f"pay_n_{th}")) else np.nan),
                "do_n_criteria": getattr(r, f"pay_n_{th}"),
                # cat_weight is NaN when the firm-year has no annual-incentive criteria;
                # read as 0 when criteria exist elsewhere but none in this category.
                "do_weight": weight,
                "weight_source": r.weight_source,
                "p3_unstated_backing": p3["unstated_backing"].get(k, np.nan),
                "p3_unstated_this_theme": (float(p3[f"d_{th}"].get(k, np.nan) > 0 and p3[f"s_{th}"].get(k, np.nan) == 0)
                                           if pd.notna(p3[f"d_{th}"].get(k, np.nan)) and pd.notna(p3[f"s_{th}"].get(k, np.nan))
                                           else np.nan),
            })
    out = pd.DataFrame(rows)
    ext = load_extension(p2[["ticker", "sector"]].drop_duplicates())
    return pd.concat([out, ext], ignore_index=True) if len(ext) else out


def load_extension(sectors: pd.DataFrame) -> pd.DataFrame:
    """Filing years 2025-2026 from Part 2's extension: proxy firm voice (say) and
    pay-linked criteria (do). No Part 1 pages (no Wayback pass) and no weight
    layer for these years. Pay counts follow build_panel.pay_counts: distinct
    criteria by name for the reported cycle."""
    tm_path, met_path = EXT_DIR / "analysis/text_measures.csv", EXT_DIR / "analysis/incentive_metrics.csv"
    if not (tm_path.exists() and met_path.exists()):
        return pd.DataFrame()
    tm = pd.read_csv(tm_path)
    met = pd.read_csv(met_path)
    runs = pd.read_csv(EXT_DIR / "analysis/llm_runs.csv")
    met = met[met["applies_to"] == "reported_year"].copy()
    met["key"] = met["metric"].str.lower().str.replace(r"\(.*?\)", "", regex=True).str.replace(r"[^a-z0-9]+", " ", regex=True).str.strip()
    met = met.drop_duplicates(["ticker", "filing_year", "key", "category"])
    ok = set(map(tuple, runs.loc[(runs.task == "incentives") & runs.status.isin(["ok", "cached"]), ["ticker", "filing_year"]].values))
    rows = []
    for r in tm.itertuples():
        k = (r.ticker, r.filing_year)
        for th in THEMES:
            n = int(((met.ticker == r.ticker) & (met.filing_year == r.filing_year) & (met.category == th)).sum())
            rows.append({"ticker": r.ticker, "sector": r.sector, "year": r.filing_year, "theme": th,
                         "say_p1_salience": np.nan, "page_type": np.nan,
                         "say_p2_fv_rate": getattr(r, f"fv_rate_{th}"),
                         "do_present": float(n > 0) if k in ok else np.nan,
                         "do_n_criteria": n if k in ok else np.nan,
                         "do_weight": np.nan, "weight_source": "none",
                         "p3_unstated_backing": np.nan, "p3_unstated_this_theme": np.nan,
                         "source": "extension"})
    return pd.DataFrame(rows)


def window_mean(g: pd.DataFrame, col: str, years) -> float:
    v = g.loc[g["year"].isin(years), col].dropna()
    return v.mean() if len(v) else np.nan


def verdict_abs(pre, post, thr):
    if pd.isna(pre) or pd.isna(post):
        return "na"
    d = post - pre
    return "cut" if d <= -thr else "rise" if d >= thr else "kept"


def verdict_rel(pre, post, thr):
    if pd.isna(pre) or pd.isna(post):
        return "na"
    if pre <= 0:                      # nothing said before: any mention is a rise
        return "rise" if post > 0 else "kept"
    d = (post - pre) / pre
    return "cut" if d <= -thr else "rise" if d >= thr else "kept"


def side(verdicts):
    v = [x for x in verdicts if x != "na"]
    if not v:
        return "na"
    cut, rise = "cut" in v, "rise" in v
    return "conflict" if cut and rise else "cut" if cut else "rise" if rise else "kept"


def classify(df: pd.DataFrame, spec: str) -> pd.DataFrame:
    say_pre, say_post = (PRE, EXT_POST) if spec == "ext" else (PRE, POST)
    do_pre, do_post = (LAG_PRE, LAG_POST) if spec == "lag" else (PRE, EXT_POST) if spec == "ext" else (PRE, POST)
    use_imputed = spec == "imputed_weights"
    rows = []
    for (t, th), g in df.groupby(["ticker", "theme"]):
        r = {"ticker": t, "sector": g["sector"].iloc[0], "theme": th, "spec": spec}
        for col, yrs_pre, yrs_post in (("say_p1_salience", say_pre, say_post), ("say_p2_fv_rate", say_pre, say_post),
                                       ("do_present", do_pre, do_post), ("do_weight", do_pre, do_post),
                                       ("p3_unstated_backing", PRE, POST), ("p3_unstated_this_theme", PRE, POST)):
            r[f"{col}_pre"], r[f"{col}_post"] = window_mean(g, col, yrs_pre), window_mean(g, col, yrs_post)
        pt = g.loc[g["year"].isin(say_pre + say_post), ["year", "page_type"]].dropna()
        r["page_type_switch"] = pt.loc[pt.year.isin(say_pre), "page_type"].nunique() > 0 and \
            set(pt.loc[pt.year.isin(say_pre), "page_type"]) != set(pt.loc[pt.year.isin(say_post), "page_type"])
        ws = g.loc[g["year"].isin(do_pre + do_post), "weight_source"]
        r["weights_imputed"] = bool((ws == "imputed_emphasis").any())
        # Imputed weights carry ~10 pp item-level error (Part 2 masking test), and
        # an extraction slip can zero a category (JPM 2024 DEI: 3 criteria, weight 0),
        # so the weight verdict counts only where weights are disclosed or derived,
        # except in the "imputed_weights" sensitivity specification.

        # ext: no Part 1 pages after 2024, so say rests on proxy firm voice alone
        r["v_p1"] = "na" if spec == "ext" else verdict_abs(r["say_p1_salience_pre"], r["say_p1_salience_post"], P1_ABS)
        r["v_p2"] = verdict_rel(r["say_p2_fv_rate_pre"], r["say_p2_fv_rate_post"], P2_REL)
        r["v_present"] = verdict_abs(r["do_present_pre"], r["do_present_post"], PRESENT_ABS)
        wpre = r["do_weight_pre"] if pd.notna(r["do_weight_pre"]) else np.nan
        wpost = r["do_weight_post"] if pd.notna(r["do_weight_post"]) else np.nan
        if pd.isna(wpre) or pd.isna(wpost):
            r["v_weight"] = "na"
        elif wpre < W_MIN:
            r["v_weight"] = "rise" if wpost >= W_MIN else "kept"
        else:
            d = (wpost - wpre) / wpre
            r["v_weight"] = "cut" if d <= -W_REL else "rise" if d >= W_REL else "kept"
        r["say"] = side([r["v_p1"], r["v_p2"]])
        r["do"] = side([r["v_present"], r["v_weight"] if (use_imputed or not r["weights_imputed"]) else "na"])

        has_say = ((r["say_p1_salience_pre"] or 0) > 0 and spec != "ext") or (r["say_p2_fv_rate_pre"] or 0) > 0
        has_do = (r["do_present_pre"] or 0) > 0
        r["eligible"] = bool(has_say and has_do and r["say"] != "na" and r["do"] != "na")
        if not r["eligible"]:
            r["quadrant"] = ("no_pre_do" if has_say and not has_do else "no_pre_say" if has_do and not has_say
                             else "nothing_to_cut" if not has_say and not has_do else "insufficient_data")
        elif "conflict" in (r["say"], r["do"]):
            r["quadrant"] = "conflict"
        else:
            cs, cd = r["say"] == "cut", r["do"] == "cut"
            r["quadrant"] = ("cut_both" if cs and cd else "cut_say_only" if cs else "cut_do_only" if cd else "kept_both")
        rows.append(r)
    return pd.DataFrame(rows)


def dei_pay_exits() -> pd.DataFrame:
    """Firms with a pay-linked DEI criterion in the 2024 filing: what their latest
    2025-2026 filing does with it. 'relabeled' = no DEI criterion left but at least
    one employees (people/culture/talent) criterion in the plan; 'dropped' = neither."""
    base = pd.read_csv(REPO / "part2_lived_values/output/analysis/incentive_metrics.csv")
    ext = pd.read_csv(EXT_DIR / "analysis/incentive_metrics.csv")
    m = pd.concat([base, ext])
    m = m[m["applies_to"] == "reported_year"]
    n = m.groupby(["ticker", "filing_year", "category"]).size().unstack(fill_value=0)
    rows = []
    for t in sorted(n[(n.index.get_level_values(1) == 2024) & (n["dei"] > 0)].index.get_level_values(0)):
        yrs = [y for y in (2026, 2025) if (t, y) in n.index]
        if not yrs:
            rows.append({"ticker": t, "latest_year": None, "outcome": "no_2025_2026_extraction"})
            continue
        y = yrs[0]
        d, e = n.loc[(t, y), "dei"], n.loc[(t, y), "employees"]
        crit = m[(m.ticker == t) & (m.filing_year == y) & m.category.isin(["dei", "employees"])]["metric"]
        rows.append({"ticker": t, "latest_year": y, "dei_2024": int(n.loc[(t, 2024), "dei"]), "dei_latest": int(d),
                     "employees_2024": int(n.loc[(t, 2024), "employees"]), "employees_latest": int(e),
                     "outcome": "kept_dei" if d > 0 else ("relabeled_people_criteria" if e > 0 else "dropped"),
                     "latest_people_criteria": "; ".join(crit.astype(str))})
    return pd.DataFrame(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    fy = load()
    fy.to_csv(OUT / "say_do_firm_year.csv", index=False)
    q = pd.concat([classify(fy, s) for s in ("main", "lag", "imputed_weights", "ext")])
    q.to_csv(OUT / "quadrants.csv", index=False)
    counts = (q.groupby(["theme", "spec", "sector", "quadrant"]).size().rename("n_firms").reset_index())
    counts.to_csv(OUT / "quadrant_counts.csv", index=False)
    if (EXT_DIR / "analysis/incentive_metrics.csv").exists():
        ex = dei_pay_exits()
        ex.to_csv(OUT / "dei_pay_exits.csv", index=False)
        print(ex["outcome"].value_counts().to_string())
    print(f"firm-year rows: {len(fy)}; firm x theme x spec rows: {len(q)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
