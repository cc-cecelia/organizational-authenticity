"""Layer 1: classical text measures for every firm-year proxy.

Usage:
    python part2_lived_values/src/text_measures.py --tickers MSFT JPM XOM   # pilot
    python part2_lived_values/src/text_measures.py                          # all firms

Per firm-year (selected proxy from proxy_coverage.csv):
- Theme intensity: seed-dictionary hits per 10,000 prose words for each
  stakeholder category (theme_dictionary.py), on three texts:
    rate_*     full proxy
    fv_rate_*  firm voice = full proxy minus the shareholder-proposal
               section, whose text is largely written by proponents, not the
               company (XOM 2023 carries ~18k words of mostly climate
               proposals). This is the headline "what the firm says" measure;
               proposals are measured separately by the LLM layer.
    cda_rate_* CD&A only: what the firm talks about when explaining pay.
- Theme share: a category's hits / all theme hits. This is composition
  independent of length and verbosity, and the scale comparable with
  Part 1's About pages.
- Tone: Loughran-McDonald negative, positive, uncertainty, litigious and
  constraining words per 10,000 words; net tone = (pos - neg) / (pos + neg),
  standard and proxy-adjusted (lm_dictionary.py).
Tables ([TABLE] blocks) are excluded throughout, because tables are numbers
and labels, not language.

Also writes the documentation tables (dictionary, events, per-firm event
exposure) and sector x year means. Section diagnostics for the LLM layer
are in sections.csv.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter

import pandas as pd

import config
import events
import sections
from lm_dictionary import LM_CATEGORIES, load_lm
from theme_dictionary import CATEGORIES, as_rows, compiled

WORD_RE = re.compile(r"[a-z]+(?:['-][a-z]+)*")
RESOLVED_RE = re.compile(r"\bresolved\b", re.I)
PER = 10_000


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def theme_counts(norm_text: str, patterns: dict) -> dict:
    return {cat: sum(len(p.findall(norm_text)) for p in pats) for cat, pats in patterns.items()}


def theme_block(prefix: str, norm_text: str, n_words: int, patterns: dict) -> dict:
    """Raw counts, rates per 10k words and shares for one text."""
    counts = theme_counts(norm_text, patterns)
    total = sum(counts.values())
    out = {f"{prefix}words": n_words}
    for cat in CATEGORIES:
        out[f"{prefix}n_{cat}"] = counts[cat]
        out[f"{prefix}rate_{cat}"] = round(PER * counts[cat] / n_words, 2) if n_words else None
        out[f"{prefix}share_{cat}"] = round(counts[cat] / total, 4) if total else None
    return out


def tone_block(tokens: list, lm: dict) -> dict:
    upper = Counter(t.upper() for t in tokens)
    n = len(tokens)
    out = {}
    for cat in LM_CATEGORIES + ["Negative_adj"]:
        k = sum(c for w, c in upper.items() if w in lm[cat])
        out[f"lm_n_{cat.lower()}"] = k
        out[f"lm_rate_{cat.lower()}"] = round(PER * k / n, 2) if n else None
    for suffix, neg in (("", out["lm_n_negative"]), ("_adj", out["lm_n_negative_adj"])):
        pos = out["lm_n_positive"]
        out[f"lm_net_tone{suffix}"] = round((pos - neg) / (pos + neg), 4) if pos + neg else None
    return out


def firm_event_exposure(cov: pd.DataFrame) -> pd.DataFrame:
    """First proxy each firm filed after each event, given its own filing calendar."""
    rows = []
    for t, g in cov.groupby("ticker"):
        g = g.sort_values("filing_date")
        for e, date, label, _, _ in events.EVENTS:
            after = g[g["filing_date"] > date]
            rows.append({"ticker": t, "sector": g["sector"].iloc[0], "event_id": e, "event_date": date,
                         "first_exposed_filing_year": int(after["filing_year"].iloc[0]) if len(after) else None,
                         "first_exposed_filing_date": after["filing_date"].iloc[0] if len(after) else None})
    return pd.DataFrame(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tickers", nargs="*")
    args = ap.parse_args(argv)

    cov = pd.read_csv(config.COVERAGE_OUT)
    cov = cov[cov["status"] != "gap"]
    if args.tickers:
        cov = cov[cov["ticker"].isin([t.upper() for t in args.tickers])]

    patterns, lm = compiled(), load_lm()
    allcov = pd.read_csv(config.COVERAGE_OUT)
    allcov = allcov[(allcov["status"] != "gap") & allcov["ticker"].isin(cov["ticker"])]
    targets = sections.cda_targets(
        (r.ticker, r.filing_year, (config.REPO_DIR / r.text_path).read_text()) for r in allcov.itertuples())
    rows, sec_rows = [], []
    for r in cov.sort_values(["ticker", "filing_year"]).to_dict("records"):
        text = (config.REPO_DIR / r["text_path"]).read_text()
        prose = sections.prose_only(text)
        norm = normalise(prose)
        tokens = WORD_RE.findall(norm)

        cda = sections.find_cda(text, targets.get((r["ticker"], r["filing_year"])))
        sp = sections.find_proposals(text)
        sec_rows.append({
            "ticker": r["ticker"], "filing_year": r["filing_year"],
            "cda_found": cda is not None, "cda_method": cda and cda["method"],
            "cda_words": cda and cda["words"], "cda_end_marker": cda and cda["end_marker"],
            "cda_target_words": targets.get((r["ticker"], r["filing_year"])),
            "proposals_found": sp is not None, "proposals_words": sp and sp["words"],
            "proposals_signal_hits": sp and sp["signal_hits"], "proposals_end_marker": sp and sp["end_marker"],
            # QA: every "RESOLVED" in the proxy except the say-on-pay resolution should
            # fall inside the proposal section; a gap > 1 means proposals were missed.
            "resolved_in_doc": len(RESOLVED_RE.findall(text)),
            "resolved_in_section": len(RESOLVED_RE.findall(sp["text"])) if sp else 0,
        })

        row = {k: r[k] for k in ("ticker", "company_name", "sector", "filing_year", "filing_date",
                                 "fiscal_year_covered", "accession", "form", "status")}
        row.update(theme_block("", norm, len(tokens), patterns))
        if sp:
            lines = text.split("\n")
            drop = set()
            for a, b in sp["intervals"]:
                drop.update(range(a, b))
            fv_text = "\n".join(l for i, l in enumerate(lines) if i not in drop)
        else:
            fv_text = text
        fv_norm = normalise(sections.prose_only(fv_text))
        row.update(theme_block("fv_", fv_norm, len(WORD_RE.findall(fv_norm)), patterns))
        if cda:
            cda_norm = normalise(sections.prose_only(cda["text"]))
            row.update(theme_block("cda_", cda_norm, len(WORD_RE.findall(cda_norm)), patterns))
        row.update(tone_block(tokens, lm))
        rows.append(row)
        print(f"{r['ticker']:6} {r['filing_year']}  words={len(tokens):6d}  "
              f"cda={'%dw' % cda['words'] if cda else 'NOT FOUND'}  "
              f"proposals={'%dw' % sp['words'] if sp else 'none'}")

    out = config.ANALYSIS_DIR
    out.mkdir(parents=True, exist_ok=True)
    m = pd.DataFrame(rows)
    m.to_csv(out / "text_measures.csv", index=False)
    pd.DataFrame(sec_rows).to_csv(out / "sections.csv", index=False)
    pd.DataFrame(as_rows()).to_csv(out / "theme_dictionary.csv", index=False)
    pd.DataFrame(events.as_rows()).to_csv(out / "events.csv", index=False)
    firm_event_exposure(cov).to_csv(out / "firm_event_exposure.csv", index=False)

    # Sector x year means (equal weight per firm), with firm counts.
    value_cols = [c for c in m.columns if c.startswith(("rate_", "share_", "fv_rate_", "fv_share_", "cda_rate_",
                                                         "lm_rate_", "lm_net_tone"))]
    trend = m.groupby(["sector", "filing_year"])[value_cols].mean().round(4)
    trend.insert(0, "n_firms", m.groupby(["sector", "filing_year"]).size())
    trend.reset_index().to_csv(out / "sector_year_trends.csv", index=False)
    print(f"wrote {len(m)} firm-years to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
