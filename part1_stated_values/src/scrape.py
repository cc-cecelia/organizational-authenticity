"""
Part 1 scraper: one archived About/values snapshot per firm per year (2016-2024).

Usage (from repo root):
    .venv/bin/python part1_stated_values/src/scrape.py --tickers MSFT JPM XOM
    .venv/bin/python part1_stated_values/src/scrape.py            # all 50 firms

Outputs (part1_stated_values/output/):
    snapshots.csv     one row per company-year (missing years included, status=missing)
    decision_log.csv  every capture tried, with accept/reject reason
    gap_log.csv       one row per missing company-year with the reason it is missing
    coverage.csv      firm x year matrix (V = values page, A = about page, . = gap)

Running on a subset updates only those firms' rows in existing outputs, so the
3-firm pilot and the full run write to the same files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import extract  # noqa: E402
import pages  # noqa: E402


def load_companies(tickers: List[str] = None) -> pd.DataFrame:
    df = pd.read_csv(config.COMPANIES_CSV, dtype=str)
    if tickers:
        unknown = set(tickers) - set(df.ticker)
        if unknown:
            raise SystemExit(f"Unknown tickers: {sorted(unknown)}")
        df = df[df.ticker.isin(tickers)]
    return df


def load_discovered(ticker: str) -> List[Dict]:
    """Discovered candidates approved in data/discovery_review.csv, in file order.

    Only rows with approved == True are used: discovery output is noisy, and the
    review CSV is the human-in-the-loop gate (pre-filled by rule, spot-checked).
    """
    path = config.DISCOVERY_REVIEW_CSV
    if not path.exists():
        return []
    review = pd.read_csv(path, dtype=str, keep_default_na=False)
    ok = review[(review.ticker == ticker) & (review.approved.str.lower() == "true")]
    return [{"url": u} for u in ok.url]


def scrape_firm(firm: pd.Series):
    """Return (rows, decision_log_rows, gap_rows) for one firm."""
    seeds = [u.strip() for u in str(firm.seed_urls).split(";") if u.strip()]
    discovered = load_discovered(firm.ticker)
    cands = pages.build_candidates(seeds, discovered)

    # Domains a redirect may legitimately land on: the firm's primary domain plus
    # every domain that appears in its candidate list (e.g. fb.com -> meta.com).
    allowed = {pages.registrable_domain(firm.domain)}
    allowed |= {pages.registrable_domain(c.url) for c in cands}

    # Pass loop: a redirect observed in one year (old values URL -> new values
    # URL) teaches us the page's successor URL, which may have captures in years
    # where the old URL has none. Successors are added as aliases in the same
    # page group and the years are re-selected. Fetches are cached, so extra
    # passes cost only the new URLs' CDX queries and fetches.
    aliases: List[Dict] = []
    for _ in range(3):
        selections = [(y, *pages.select_year(cands, y, allowed)) for y in config.YEARS]
        group_of = {pages.canonical(c.url): c.group for c in cands}
        new = []
        for _, _, attempts in selections:
            for a in attempts:
                f = a.fetch
                # Only redirects that passed the domain/homepage/login/type
                # checks (reason past those gates) can define a successor.
                if not (f and f.http_status == 200 and len(f.redirect_chain) > 1
                        and a.reason in ("accepted", "thin_text", "soft_404")):
                    continue
                key = pages.canonical(f.final_url)
                if group_of.get(key) != a.candidate.group:
                    group_of[key] = a.candidate.group
                    new.append({"url": f.final_url, "group": a.candidate.group})
        if not new:
            break
        aliases += new
        cands = pages.build_candidates(seeds, discovered, aliases)

    rows, log, gaps = [], [], []
    prev_group = None
    for year, accepted, attempts in selections:
        for a in attempts:
            log.append({
                "ticker": firm.ticker, "year": year,
                "candidate_url": a.candidate.url, "page_type": a.candidate.page_type,
                "source": a.candidate.source, "page_group": a.candidate.group,
                "capture_timestamp": a.capture["timestamp"],
                "capture_status": a.capture["statuscode"],
                "final_url": a.fetch.final_url if a.fetch else "",
                "final_timestamp": a.fetch.final_timestamp if a.fetch else "",
                "redirect_chain": " -> ".join(a.fetch.redirect_chain) if a.fetch else "",
                "decision": "accepted" if a.accepted else "rejected",
                "reason": a.reason,
                "word_count": extract.word_count(a.text),
            })

        base = {"ticker": firm.ticker, "company_name": firm.company_name,
                "sector": firm.sector, "year": year}
        if accepted is None:
            reason, detail = pages.gap_reason(cands, year, attempts)
            gaps.append({**base, "reason": reason, "detail": detail,
                         "discovery_run": bool(discovered) or
                         (config.DISCOVERY_CACHE_DIR / f"{firm.ticker}.json").exists()})
            rows.append({**base, "status": "missing", "gap_reason": reason})
            continue

        f = accepted.fetch
        group = accepted.candidate.group
        rows.append({
            **base,
            "status": "ok",
            "gap_reason": "",
            "page_type": accepted.candidate.page_type,
            "page_source": accepted.candidate.source,
            "page_group": group,
            "page_url": accepted.candidate.url,
            # A switch to a different logical page (not a URL move of the same
            # page) is never a content change; downstream change detection must
            # skip rows where this is True.
            "page_switched": prev_group is not None and group != prev_group,
            "final_url": f.final_url,
            "snapshot_timestamp": f.final_timestamp,
            "wayback_url": f.wayback_url,
            "capture_status": accepted.capture["statuscode"],
            "redirected": len(f.redirect_chain) > 1,
            "extraction_method": accepted.method,
            "word_count": extract.word_count(accepted.text),
            "text_sha1": hashlib.sha1(accepted.text.encode()).hexdigest(),
            "page_text_clean": accepted.text,
        })
        prev_group = group
    return rows, log, gaps


def _merge_write(new: pd.DataFrame, path: Path, tickers: List[str]) -> pd.DataFrame:
    """Replace these tickers' rows in an existing output file, keep the rest."""
    if path.exists():
        old = pd.read_csv(path, dtype=str, keep_default_na=False)
        new = pd.concat([old[~old.ticker.isin(tickers)], new.astype(str)], ignore_index=True)
    order = {t: i for i, t in enumerate(pd.read_csv(config.COMPANIES_CSV, dtype=str).ticker)}
    sort_cols = [c for c in ("year", "capture_timestamp") if c in new.columns]
    new = (new.assign(_o=new.ticker.map(order))
              .sort_values(["_o"] + sort_cols, kind="stable").drop(columns="_o"))
    new.to_csv(path, index=False)
    return new


def coverage_table(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Firm x year grid: V = values page, A = about page, . = missing."""
    code = snapshots.apply(
        lambda r: "." if r.status == "missing" else ("V" if r.page_type == "values" else "A"),
        axis=1)
    grid = (snapshots.assign(code=code)
            .pivot(index="ticker", columns="year", values="code")
            .reindex(snapshots.ticker.drop_duplicates()))
    grid["n_years"] = (grid != ".").sum(axis=1)
    return grid


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tickers", nargs="*", help="subset of tickers (default: all)")
    args = ap.parse_args()

    firms = load_companies(args.tickers)
    tickers = list(firms.ticker)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_rows, all_log, all_gaps = [], [], []
    for _, firm in firms.iterrows():
        print(f"[{firm.ticker}] scraping...", flush=True)
        try:
            rows, log, gaps = scrape_firm(firm)
        except Exception as exc:  # one firm's failure must not abort the run
            msg = f"{type(exc).__name__}: {exc}"[:300]
            print(f"[{firm.ticker}] FAILED: {msg}", flush=True)
            base = {"ticker": firm.ticker, "company_name": firm.company_name, "sector": firm.sector}
            rows = [{**base, "year": y, "status": "missing", "gap_reason": "scrape_error"}
                    for y in config.YEARS]
            gaps = [{**base, "year": y, "reason": "scrape_error", "detail": msg,
                     "discovery_run": False} for y in config.YEARS]
            log = []
        ok = sum(r["status"] == "ok" for r in rows)
        print(f"[{firm.ticker}] {ok}/{len(rows)} years, {len(log)} captures tried", flush=True)
        all_rows += rows
        all_log += log
        all_gaps += gaps

    snaps = _merge_write(pd.DataFrame(all_rows), config.OUTPUT_DIR / "snapshots.csv", tickers)
    _merge_write(pd.DataFrame(all_log), config.OUTPUT_DIR / "decision_log.csv", tickers)
    gap_cols = ["ticker", "company_name", "sector", "year", "reason", "detail", "discovery_run"]
    _merge_write(pd.DataFrame(all_gaps, columns=gap_cols), config.OUTPUT_DIR / "gap_log.csv", tickers)

    snaps["year"] = snaps["year"].astype(int)
    cov = coverage_table(snaps)
    cov.to_csv(config.OUTPUT_DIR / "coverage.csv")
    print("\nCoverage (V = values page, A = about page, . = gap):")
    print(cov.to_string())
    total = (snaps.status == "ok").sum()
    print(f"\n{total}/{len(snaps)} company-years collected")


if __name__ == "__main__":
    main()
