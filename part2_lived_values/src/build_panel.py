"""Build the Part 2 lived-values panel: one row per firm-year.

Usage: python part2_lived_values/src/build_panel.py
       (after download_proxies.py, text_measures.py and llm_extract.py)

Output: part2_lived_values/output/lived_values_panel.csv, keyed on
(ticker, year) so Part 3 can join it to Part 1. `year` is the proxy filing
year, which matches Part 1's convention (the About page as it stood mid-year).
`fiscal_year_covered` and `filing_date` allow a one-year-lag test.

Column groups (per stakeholder category c in theme_dictionary.CATEGORIES):
  pay_n_<c>      distinct pay-linked criteria in category c: metrics plus named
                 sub-criteria that governed pay for the reported cycle,
                 de-duplicated by name across plans and scopes (a criterion
                 used in both the bonus and the long-term award counts once)
  pay_n_other    criteria that fit no stakeholder (e.g. individual performance)
  pay_n_total    all distinct pay-linked criteria, including other
  pay_share_<c>  pay_n_<c> / sum of pay_n over the nine categories (other
                 excluded), so shares sum to 1 and compare with Part 1's
                 category shares
  fv_rate_<c>    firm-voice dictionary hits per 10,000 prose words (proxy
                 minus shareholder-proposal text)
  fv_share_<c>   category share of all firm-voice dictionary hits
  prop_n_<c>     shareholder proposals whose main category is c
  prop_n_total   shareholder proposals; prop_share_board_against
  cat_weight_<c>      share of the annual incentive plan's payout weight in
                      category c (weight_layer.py); cat_weight_other for
                      criteria fitting no stakeholder. Sums to 1 with other.
  cat_weight_lti_<c>  same for the long-term incentive plan
  weight_source, weight_source_lti   disclosed | derived_from_stated_split |
                      imputed_emphasis | none: the weakest basis of any
                      weighted criterion in that plan
Quality and flags:
  flagged        True when the filing row is ok_flagged in proxy_coverage.csv
  flag_reason    the coverage note (contested election, timing shift, ...)
  cda_quality    ok | length_outlier (outside 0.5-1.8x the firm's median
                 CD&A length) | missing
  pay_status, proposals_status   LLM run status (ok/cached = extracted,
                 no_section = nothing to extract, error)
Pay columns are empty when the CD&A was not found; proposal columns are 0
when the proxy had no shareholder proposals (no_section) and empty on error.
"""
from __future__ import annotations

import re
import sys

import pandas as pd

import config
from theme_dictionary import CATEGORIES

OUT = config.OUTPUT_DIR / "lived_values_panel.csv"
KEYS = ["ticker", "filing_year"]


def norm_name(s: str) -> str:
    """Name key for de-duplicating the same criterion across plans/scopes."""
    s = re.sub(r"\(.*?\)", "", str(s).lower())
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def pay_counts(met: pd.DataFrame) -> pd.DataFrame:
    cur = met[met["applies_to"] == "reported_year"].copy()
    cur["key"] = cur["metric"].map(norm_name)
    distinct = cur.drop_duplicates(KEYS + ["key", "category"])
    n = distinct.pivot_table(index=KEYS, columns="category", values="key", aggfunc="size", fill_value=0)
    for c in CATEGORIES + ["other"]:
        if c not in n:
            n[c] = 0
    out = n[CATEGORIES + ["other"]].add_prefix("pay_n_")
    out["pay_n_total"] = out.sum(axis=1)
    stake = out[[f"pay_n_{c}" for c in CATEGORIES]]
    denom = stake.sum(axis=1).where(lambda x: x > 0)
    for c in CATEGORIES:
        out[f"pay_share_{c}"] = (stake[f"pay_n_{c}"] / denom).round(4)
    return out


def proposal_counts(prop: pd.DataFrame) -> pd.DataFrame:
    n = prop.pivot_table(index=KEYS, columns="category", values="title", aggfunc="size", fill_value=0)
    for c in CATEGORIES + ["other"]:
        if c not in n:
            n[c] = 0
    out = n[CATEGORIES + ["other"]].add_prefix("prop_n_")
    out["prop_n_total"] = out.sum(axis=1)
    out["prop_share_board_against"] = prop.groupby(KEYS)["board_recommendation"].apply(
        lambda s: round((s == "against").mean(), 4))
    return out


def main() -> int:
    a = config.ANALYSIS_DIR
    cov = pd.read_csv(config.COVERAGE_OUT)
    cov = cov[cov["status"] != "gap"]
    tm = pd.read_csv(a / "text_measures.csv")
    sec = pd.read_csv(a / "sections.csv")
    runs = pd.read_csv(a / "llm_runs.csv")
    met = pd.read_csv(a / "incentive_metrics.csv")
    prop = pd.read_csv(a / "shareholder_proposals.csv")

    base = cov[["ticker", "company_name", "sector", "filing_year", "fiscal_year_covered", "filing_date",
                "accession", "form", "status", "notes"]].copy()
    base["flagged"] = base.pop("status").eq("ok_flagged")
    base["flag_reason"] = base.pop("notes").where(base["flagged"], "")

    st = runs.pivot_table(index=KEYS, columns="task", values="status", aggfunc="first")
    st = st.rename(columns={"incentives": "pay_status", "proposals": "proposals_status"})

    sec = sec.set_index(KEYS)
    ratio = sec["cda_words"] / sec["cda_target_words"]
    cda_q = pd.Series("ok", index=sec.index)
    cda_q[(ratio < 0.5) | (ratio > 1.8)] = "length_outlier"
    cda_q[~sec["cda_found"].astype(bool)] = "missing"

    fv_cols = [f"fv_rate_{c}" for c in CATEGORIES] + [f"fv_share_{c}" for c in CATEGORIES] + ["fv_words"]
    panel = (base.set_index(KEYS)
             .join(cda_q.rename("cda_quality"))
             .join(st)
             .join(pay_counts(met))
             .join(proposal_counts(prop))
             .join(tm.set_index(KEYS)[fv_cols]))
    wpath = a / "weights_firm_year.csv"
    if wpath.exists():   # weight layer (weight_layer.py); absent until it has run
        panel = panel.join(pd.read_csv(wpath).set_index(KEYS))
        for col in ("weight_source", "weight_source_lti"):
            panel[col] = panel[col].fillna("none")

    # Proposals: a proxy with no shareholder proposals is a true zero, not missing.
    prop_cols = [c for c in panel.columns if c.startswith("prop_n_")]
    none = panel["proposals_status"].eq("no_section")
    panel.loc[none, prop_cols] = panel.loc[none, prop_cols].fillna(0)
    ok = panel["proposals_status"].isin(["ok", "cached"])
    panel.loc[ok, prop_cols] = panel.loc[ok, prop_cols].fillna(0)

    panel = panel.reset_index().rename(columns={"filing_year": "year"})
    lead = ["ticker", "company_name", "sector", "year", "fiscal_year_covered", "filing_date", "accession",
            "form", "flagged", "flag_reason", "cda_quality", "pay_status", "proposals_status"]
    panel = panel[lead + [c for c in panel.columns if c not in lead]]
    panel.to_csv(OUT, index=False)

    print(f"wrote {OUT} ({len(panel)} rows x {panel.shape[1]} cols)")
    print("unique (ticker, year):", not panel.duplicated(["ticker", "year"]).any())
    print(panel["cda_quality"].value_counts().to_string())
    print(panel[["pay_status", "proposals_status"]].apply(lambda s: s.value_counts()).fillna(0).astype(int).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
