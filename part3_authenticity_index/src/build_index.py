"""
Part 3: Organizational Authenticity Index (spec: CLAUDE.md "Part 3 design").

Usage (from repo root):
    .venv/bin/python part3_authenticity_index/src/build_index.py

In plain words: for each firm-year, take the values the About/values page states
(Part 1), weighted by how prominently it states them, and ask what fraction of
that stated emphasis is backed by executive pay (Part 2). It is a salience-weighted
recall of stated values against pay-linked criteria. tau is a materiality
threshold: how much of the pay plan a category needs before it counts as fully
backed.

Inputs per firm i, year t, category k (shared taxonomy):
  s_ikt  Part 1 salience sal_<k>, 0-3                    (stated_values.csv)
  d_ikt  pay-linked criteria in k, pay_n_<k>             (lived_values_panel.csv)
  w_ikt  share of the pay plan tied to k: the disclosed annual-incentive weight
         (Part 2 llm_firm_year.csv aip_weight_share_<k>) if available, else an
         imputed weight column in the panel if Part 2 has added one.

Index:
  c_ikt(tau) = min(max(w_ik,t, w_ik,t+1) / tau, 1)
  A_it(tau)  = sum_k s_ikt c_ikt(tau) / sum_k s_ikt
  tau -> 0 (primary): c = 1 if d_ik,t > 0 or d_ik,t+1 > 0, else 0. Needs no weights.

Why t and t+1: Part 1's year t is the page as archived around July 1 of t. The
proxy filed in t reports pay for fiscal t-1; the proxy filed in t+1 reports pay
for fiscal t, the year the page was live. Either can show the board backing what
the page says. For 2024 there is no t+1 proxy in the window: t only, flagged.

Output: part3_authenticity_index/output/authenticity_index.csv, one row per
firm-year (450), with a reason column wherever an index is NaN.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "part2_lived_values" / "src"))
from theme_dictionary import CATEGORIES  # noqa: E402  (shared taxonomy, read-only)

SAY_CSV = ROOT / "part1_stated_values" / "output" / "stated_values.csv"
PANEL_CSV = ROOT / "part2_lived_values" / "output" / "lived_values_panel.csv"
LLM_FY_CSV = ROOT / "part2_lived_values" / "output" / "analysis" / "llm_firm_year.csv"
OUT_DIR = ROOT / "part3_authenticity_index" / "output"
OUT_CSV = OUT_DIR / "authenticity_index.csv"

# Disclosed weights are used only when less than this share of the plan sits in the
# unresolved `other` bucket.
MAX_UNRESOLVED_OTHER = 0.05
TAUS = {"tau0": 0.0, "tau5": 0.05, "tau10": 0.10, "tau20": 0.20}
LAST_YEAR = 2024
# Weight sources counted as stated (not estimated) for the robustness variant.
STRICT_SOURCES = {"disclosed", "derived_from_stated_split"}
# Candidate names for the imputed-weight column Part 2 may add to the panel
# (fraction of the plan, 0-1). The first prefix found is used.
IMPUTED_WEIGHT_PREFIXES = ["pay_weight_imputed_", "pay_imputed_weight_", "pay_w_imputed_", "pay_weight_"]
NON_SH = [k for k in CATEGORIES if k != "shareholders"]


def load_do() -> tuple:
    """Panel with d (counts) and w (weights) per (ticker, year), and the weight source used."""
    panel = pd.read_csv(PANEL_CSV)
    d = panel[["ticker", "year", "flagged", "flag_reason", "cda_quality", "pay_status", "pay_n_total"]
              + [f"pay_n_{k}" for k in CATEGORIES]].copy()

    w = pd.DataFrame({"ticker": d.ticker, "year": d.year})
    w_src = pd.Series("none", index=d.index)

    # Preferred: Part 2's panel weights, cat_weight_<k> (disclosed where available,
    # else imputed) with their provenance in weight_source.
    if any(c.startswith("cat_weight_") for c in panel.columns):
        cols = [f"cat_weight_{k}" for k in CATEGORIES if f"cat_weight_{k}" in panel]
        vals = panel[cols]
        scale = 100.0 if vals.max().max() > 1.5 else 1.0      # accept percent or fraction
        has = vals.notna().any(axis=1)
        for k in CATEGORIES:
            col = f"cat_weight_{k}"
            w[f"w_{k}"] = np.where(has, panel[col].fillna(0.0) / scale if col in panel else 0.0, np.nan)
        src = panel["weight_source"].astype(str) if "weight_source" in panel else pd.Series("panel", index=panel.index)
        w_src[has.values] = src[has].values
        # Interim guard (kept until the full panel shows no row with >= 5% in `other`).
        if "cat_weight_other" in panel:
            other = (panel["cat_weight_other"].fillna(0.0) / scale)
            unres = has & (other >= MAX_UNRESOLVED_OTHER)
            for k in CATEGORIES:
                w.loc[unres.values, f"w_{k}"] = np.nan
            w_src[unres.values] = "disclosed_unresolved"
        w["w_source"] = w_src.values
        return d.merge(w, on=["ticker", "year"]), "cat_weight_ (panel)"

    # Fallback for the pilot panel, which has no weight columns: disclosed weights
    # from llm_firm_year.csv (fractions; only firm-years whose stated weights sum to ~100%).
    if LLM_FY_CSV.exists():
        fy = pd.read_csv(LLM_FY_CSV)
        cols = [c for c in fy.columns if c.startswith("aip_weight_share_")]
        if cols:
            disc = fy[["ticker", "filing_year"] + cols].rename(columns={"filing_year": "year"})
            disc = disc[disc[cols].notna().any(axis=1)]
            # Guard: Part 2 keeps only weights stated as a share of the plan total, so a
            # nested split (MSFT 2019-20: 50% "qualitative", split 1/3 each across
            # customers, innovation, culture) lands entirely in `other` and the
            # stakeholder categories read 0%. Treat such rows as unresolved rather than
            # as zero weight; they fall back to imputed weights when Part 2 adds them.
            other = disc.get("aip_weight_share_other", pd.Series(0.0, index=disc.index)).fillna(0.0)
            unresolved = disc.loc[other >= MAX_UNRESOLVED_OTHER, ["ticker", "year"]]
            disc = disc[other < MAX_UNRESOLVED_OTHER]
            m = d[["ticker", "year"]].merge(disc, on=["ticker", "year"], how="left")
            has = m[cols].notna().any(axis=1)
            for k in CATEGORIES:
                col = f"aip_weight_share_{k}"
                w[f"w_{k}"] = np.where(has, m[col].fillna(0.0) if col in m else 0.0, np.nan)
            w_src[has.values] = "disclosed"
            unres = d[["ticker", "year"]].merge(unresolved.assign(_u=True), on=["ticker", "year"], how="left")["_u"]
            w_src[unres.fillna(False).astype(bool).values] = "disclosed_unresolved"
    for k in CATEGORIES:
        if f"w_{k}" not in w:
            w[f"w_{k}"] = np.nan

    # Imputed weights from the panel, where no disclosed weight exists.
    prefix = next((p for p in IMPUTED_WEIGHT_PREFIXES
                   if any(c.startswith(p) for c in panel.columns)), None)
    if prefix:
        imp_rows = panel[[f"{prefix}{k}" for k in CATEGORIES if f"{prefix}{k}" in panel]].notna().any(axis=1)
        fill = w_src.isin(["none", "disclosed_unresolved"]) & imp_rows
        for k in CATEGORIES:
            col = f"{prefix}{k}"
            if col in panel:
                w.loc[fill, f"w_{k}"] = panel.loc[fill, col].fillna(0.0)
            else:
                w.loc[fill, f"w_{k}"] = 0.0
        w_src[fill] = "imputed"
    weightish = [c for c in panel.columns if "weight" in c and not (prefix and c.startswith(prefix))]
    if weightish:
        print(f"note: unrecognized weight-like panel columns (not used): {weightish}")
    w["w_source"] = w_src.values
    return d.merge(w, on=["ticker", "year"]), (prefix or "")


def index_row(say: dict, do_t: dict, do_t1: dict, year: int) -> dict:
    """All index columns for one firm-year."""
    out = {}
    s = np.array([say.get(f"sal_{k}", np.nan) for k in CATEGORIES], dtype=float)

    # Which proxy years back this page-year.
    avail = [x for x in (do_t, do_t1) if x is not None and pd.notna(x.get("pay_n_total"))]
    if year == LAST_YEAR:
        window = "t_only_2024"
    elif do_t1 is None or pd.isna(do_t1.get("pay_n_total")):
        window = "t_only_t1_missing" if avail else "none"
    elif do_t is None or pd.isna(do_t.get("pay_n_total")):
        window = "t1_only_t_missing"
    else:
        window = "t_and_t1"
    out["do_window"] = window
    out["flag_2024_t_only"] = year == LAST_YEAR

    # Reasons an index cannot be computed.
    reason = ""
    if say.get("status") != "ok":
        reason = "say_missing"
    elif np.nansum(s) == 0:
        reason = "say_all_zero"
    elif not avail:
        reason = "do_missing"

    # Coverage indicator per category (primary, tau -> 0) and max weight per category.
    d = np.array([[x[f"pay_n_{k}"] for k in CATEGORIES] for x in avail], dtype=float) if avail else None
    cov0 = (np.nanmax(d, axis=0) > 0).astype(float) if avail else np.full(len(CATEGORIES), np.nan)
    wrows = [x for x in avail if x.get("w_source") not in ("none", "disclosed_unresolved", None)
             and not pd.isna(x.get("w_source"))]
    unresolved = any(x.get("w_source") == "disclosed_unresolved" for x in avail)
    wmax = (np.nanmax(np.array([[x[f"w_{k}"] for k in CATEGORIES] for x in wrows], dtype=float), axis=0)
            if wrows else None)
    out["w_source"] = "+".join(sorted({x["w_source"] for x in wrows})) if wrows else "none"
    out["weights_partial"] = bool(wrows) and len(wrows) < len(avail)

    for j, k in enumerate(CATEGORIES):
        out[f"s_{k}"] = s[j]
        out[f"d_{k}"] = np.nanmax(d[:, j]) if avail else np.nan
        out[f"cov_{k}"] = cov0[j]
        out[f"w_{k}"] = wmax[j] if wmax is not None else np.nan

    def A(c: np.ndarray, keep: list) -> float:
        idx = [CATEGORIES.index(k) for k in keep]
        ss, cc = s[idx], c[idx]
        return float((ss * cc).sum() / ss.sum()) if ss.sum() > 0 else np.nan

    for name, tau in TAUS.items():
        if reason:
            c = None
        elif tau == 0:
            c = cov0
        elif wmax is None:
            c = None
        else:
            c = np.minimum(wmax / tau, 1.0)
        out[f"A_{name}"] = A(c, CATEGORIES) if c is not None else np.nan
        out[f"A_ex_shareholders_{name}"] = A(c, NON_SH) if c is not None else np.nan
    # Robustness variant: weighted index from stated weights only (disclosed or
    # derived_from_stated_split), excluding Part 2's imputed_emphasis estimates.
    srows = [x for x in wrows if x.get("w_source") in STRICT_SOURCES]
    smax = (np.nanmax(np.array([[x[f"w_{k}"] for k in CATEGORIES] for x in srows], dtype=float), axis=0)
            if srows else None)
    for name, tau in TAUS.items():
        if tau == 0:
            continue
        c = None if (reason or smax is None) else np.minimum(smax / tau, 1.0)
        out[f"A_strict_{name}"] = A(c, CATEGORIES) if c is not None else np.nan
    out["A_reason"] = reason
    out["A_weighted_reason"] = reason or (("disclosed_weights_unresolved" if unresolved else "no_weights")
                                          if wmax is None else "")
    if not reason and s[[CATEGORIES.index(k) for k in NON_SH]].sum() == 0:
        out["A_ex_shareholders_reason"] = "say_only_shareholders"
    else:
        out["A_ex_shareholders_reason"] = reason

    # Doing without saying: pay-linked (non-shareholder) categories the page never states.
    if say.get("status") != "ok" or not avail:
        out["unstated_backing"], out["unstated_backing_reason"] = np.nan, reason or "do_missing"
    else:
        backed = [k for k in NON_SH if cov0[CATEGORIES.index(k)] == 1]
        out["n_backed_non_sh"] = len(backed)
        if backed:
            out["unstated_backing"] = sum(s[CATEGORIES.index(k)] == 0 for k in backed) / len(backed)
            out["unstated_backing_reason"] = ""
        else:
            out["unstated_backing"], out["unstated_backing_reason"] = np.nan, "no_non_shareholder_pay_criteria"
    return out


def main() -> int:
    say = pd.read_csv(SAY_CSV)
    do, imputed_prefix = load_do()
    do_map = {(r["ticker"], int(r["year"])): r for r in do.to_dict("records")}
    rows = []
    for r in say.to_dict("records"):
        t, y = r["ticker"], int(r["year"])
        do_t, do_t1 = do_map.get((t, y)), do_map.get((t, y + 1))
        row = {"ticker": t, "company_name": r["company_name"], "sector": r["sector"], "year": y,
               "say_status": r["status"], "page_type": r.get("page_type"), "word_count": r.get("word_count")}
        row.update(index_row(r, do_t, do_t1, y))
        # Part 2 quality flags for both proxy years, carried through.
        for tag, x in (("t", do_t), ("t1", do_t1)):
            row[f"p2_flagged_{tag}"] = x.get("flagged") if x else np.nan
            row[f"p2_flag_reason_{tag}"] = x.get("flag_reason") if x else np.nan
            row[f"p2_cda_quality_{tag}"] = x.get("cda_quality") if x else np.nan
        rows.append(row)
    out = pd.DataFrame(rows)
    out.insert(4, "A", out["A_tau0"])                                  # primary index
    out.insert(5, "A_ex_shareholders", out["A_ex_shareholders_tau0"])
    out.insert(6, "unstated_backing", out.pop("unstated_backing"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"wrote {OUT_CSV}: {len(out)} rows, A computed for {out.A.notna().sum()}, "
          f"weighted (tau10) for {out.A_tau10.notna().sum()}; imputed-weight column: "
          f"{imputed_prefix or 'not present yet'}")
    print(out.A_reason.replace('', 'ok').value_counts().to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
