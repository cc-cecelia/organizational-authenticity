"""
Anchored-prefix CDX discovery of About/values pages, for firms whose curated
seed URLs leave year gaps.

Why anchored prefixes: a domain-wide CDX prefix query with a regex path filter
times out (HTTP 504 after ~60 s) for large corporate sites, and paging through
the full index costs hundreds to thousands of requests per firm. Instead we
query narrow prefixes "host/<base><keyword>", where <base> is "" or a locale
segment seen in the firm's seeds (e.g. "en-us/"), and <keyword> comes from
config.DISCOVERY_KEYWORDS. Each query is collapsed to one row per URL per year,
which is exactly what ranking by year coverage needs. Trade-off: a page whose
keyword sits deeper in the path (e.g. /corporate/About-JPMC/...) is only found
if a seed points into that directory, which is why seed parent directories are
added as extra prefixes.

Results are cached per firm in cache/discovery/<TICKER>.json. Discovery is
noisy (it surfaces sub-organization and function pages under /about), so every
candidate is appended to data/discovery_review.csv with a pre-filled
`approved` judgment and `reason` (rules in config.REVIEW_*_RE, applied to the
URL path and the archived page title). A human spot-checks that file; scrape.py
uses approved rows only. Existing rows are never overwritten, so manual edits
survive re-runs.

Usage (from repo root; slow, meant for the background):
    .venv/bin/python part1_stated_values/src/discover.py --from-gaps
    .venv/bin/python part1_stated_values/src/discover.py --tickers JPM XOM
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set
from urllib.parse import urlparse

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import pages  # noqa: E402
import extract  # noqa: E402
import wayback  # noqa: E402

REVIEW_COLUMNS = ["ticker", "url", "page_type", "years", "gap_years_filled",
                  "page_title", "approved", "reason", "judged_by"]


def prefixes_for(firm: pd.Series) -> List[str]:
    """Build the list of anchored prefixes to query for one firm."""
    seeds = [u.strip() for u in str(firm.seed_urls).split(";") if u.strip()]
    hosts: Dict[str, Set[str]] = defaultdict(lambda: {""})
    out: List[str] = []
    for url in seeds:
        p = urlparse(url)
        segs = [s for s in p.path.split("/") if s]
        # A leading locale segment ("en-us", "en") becomes an extra base path.
        if segs and config.LOCALE_SEGMENT_RE.match(segs[0]) and "." not in segs[0]:
            hosts[p.hostname].add(segs[0] + "/")
        else:
            hosts[p.hostname]  # register host with default base
        # Seed parent directory, e.g. "www.jpmorganchase.com/corporate/About-JPMC/".
        # Skipped when the parent is just a locale root ("www.microsoft.com/en-us/"),
        # which is the whole site and times out.
        parent = f"{p.hostname}/{'/'.join(segs[:-1])}/"
        if len(segs) >= 2 and not pages.is_homepage("https://" + parent):
            out.append(parent)
    for host, bases in hosts.items():
        for base in sorted(bases):
            for kw in config.DISCOVERY_KEYWORDS:
                out.append(f"{host}/{base}{kw}")
    return list(dict.fromkeys(out))  # dedupe, keep order


def discover_firm(firm: pd.Series, gap_years: Set[int]) -> Dict:
    """Run all prefix queries for one firm and rank the URLs found."""
    years: Dict[str, Set[int]] = defaultdict(set)
    originals: Dict[str, str] = {}
    query_log = []
    for prefix in prefixes_for(firm):
        try:
            rows = wayback.cdx_query({
                "url": prefix,
                "matchType": "prefix",
                # Only scan the gap-year range: smaller index scans, faster
                # queries, and pages outside the gaps cannot help anyway.
                "from": str(min(gap_years)),
                "to": str(max(gap_years)),
                "fl": "urlkey,timestamp,original,statuscode",
                "filter": ["statuscode:[23]..", "mimetype:text/html"],
                # One row per URL per year. Caveat: collapse compares adjacent
                # rows, so a URL whose first year equals the previous URL's last
                # year loses that one year here (coverage is re-queried exactly
                # in scrape.py, so this only affects ranking).
                "collapse": "timestamp:4",
                "limit": "20000",
            }, max_retries=3)
            query_log.append({"prefix": prefix, "status": "ok", "rows": len(rows)})
        except wayback.WaybackError as exc:
            # Failed prefixes are not cached, so re-running discovery retries them.
            query_log.append({"prefix": prefix, "status": f"error: {exc.cause}", "rows": 0})
            continue
        for r in rows:
            years[r["urlkey"]].add(int(r["timestamp"][:4]))
            originals.setdefault(r["urlkey"], r["original"])

    seed_keys = {pages.canonical(u) for u in str(firm.seed_urls).split(";")}
    found = []
    for key, yrs in years.items():
        url = originals[key]
        path = urlparse(url).path
        if pages.canonical(url) in seed_keys:
            continue
        # Keywords must appear in the page's own (last) path segment: a keyword in
        # a parent directory ("/corporate/About-JPMC/esg.htm") marks a sub-page
        # of the About section, not the About page itself.
        last = [s for s in path.split("/") if s][-1:] or [""]
        if not config.DISCOVERY_KEEP_RE.search(last[0]) or config.DISCOVERY_DROP_RE.search(url):
            continue
        if len([s for s in path.split("/") if s]) > config.DISCOVERY_MAX_DEPTH:
            continue
        found.append({"url": url, "page_type": pages.classify_page_type(url),
                      "years": sorted(yrs), "gap_years_filled": sorted(yrs & gap_years)})

    # Rank: fills the most gap years, then values before about, then longest
    # history, then shallowest path (top-level pages are more likely the real one).
    found.sort(key=lambda d: (-len(d["gap_years_filled"]),
                              config.PAGE_TYPE_PRIORITY[d["page_type"]],
                              -len(d["years"]),
                              urlparse(d["url"]).path.count("/")))
    return {"ticker": firm.ticker, "gap_years": sorted(gap_years),
            "queries": query_log, "n_urls_seen": len(years),
            "candidates": [d for d in found if d["gap_years_filled"]][:config.DISCOVERY_TOP_K]}


def fetch_title(url: str, years: List[int]) -> str:
    """Title of one archived capture of `url` (latest year first), for review."""
    caps = wayback.captures_for_url(url, config.YEARS[0], config.YEARS[-1])
    ok = sorted((c for c in caps if c["statuscode"] == "200"),
                key=lambda c: c["timestamp"], reverse=True)
    for c in ok[:2]:
        try:
            f = wayback.fetch_snapshot(c["timestamp"], c["original"])
        except wayback.WaybackError:
            continue
        if f.http_status == 200:
            return extract.page_title(f.content)
    return ""


def auto_judge(firm: pd.Series, cand: Dict, title: str):
    """Pre-fill (approved, reason) following the review rules.

    Approve: same host as a seed, and path or title clearly about the parent
    company or its values/mission/purpose/principles/credo.
    Reject: other host; sub-organizations (institute, foundation, subsidiary);
    function pages (governance, careers, investors, ESG, products, ...).
    """
    seed_hosts = {urlparse(u.strip()).hostname for u in str(firm.seed_urls).split(";")}
    host = urlparse(cand["url"]).hostname
    path = urlparse(cand["url"]).path
    if host not in seed_hosts:
        return False, f"different host ({host})"
    m = config.REVIEW_REJECT_RE.search(path) or config.REVIEW_REJECT_RE.search(title)
    if m:
        return False, f"function or sub-organization page ('{m.group(0)}')"
    # Approval must rest on the page's own name (last segment) or its title, not
    # on a parent directory such as "/About-JPMC/".
    last = ([seg for seg in path.split("/") if seg][-1:] or [""])[0]
    m = config.REVIEW_APPROVE_RE.search(last) or config.REVIEW_APPROVE_RE.search(title)
    if m:
        return True, f"parent-company About/values page ('{m.group(0)}')"
    return False, "not clearly an About/values page"


def update_review_csv(firm: pd.Series, candidates: List[Dict]) -> pd.DataFrame:
    """Append new candidates to the review CSV; keep existing (possibly edited) rows."""
    path = config.DISCOVERY_REVIEW_CSV
    review = (pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists()
              else pd.DataFrame(columns=REVIEW_COLUMNS))
    have = {(r.ticker, pages.canonical(r.url)) for r in review.itertuples()}
    new = []
    for c in candidates:
        if (firm.ticker, pages.canonical(c["url"])) in have:
            continue
        title = fetch_title(c["url"], c["years"])
        approved, reason = auto_judge(firm, c, title)
        new.append({"ticker": firm.ticker, "url": c["url"], "page_type": c["page_type"],
                    "years": " ".join(map(str, c["years"])),
                    "gap_years_filled": " ".join(map(str, c["gap_years_filled"])),
                    "page_title": title, "approved": str(approved), "reason": reason,
                    "judged_by": "auto"})
    review = pd.concat([review, pd.DataFrame(new, columns=REVIEW_COLUMNS)], ignore_index=True)
    review.to_csv(path, index=False)
    return review[review.ticker == firm.ticker]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tickers", nargs="*", help="firms to run discovery for")
    ap.add_argument("--from-gaps", action="store_true",
                    help="run for every firm with gaps in output/gap_log.csv")
    ap.add_argument("--force", action="store_true", help="re-run even if cached")
    args = ap.parse_args()

    firms = pd.read_csv(config.COMPANIES_CSV, dtype=str)
    gap_path = config.OUTPUT_DIR / "gap_log.csv"
    gaps = pd.read_csv(gap_path, dtype=str) if gap_path.exists() else pd.DataFrame(columns=["ticker", "year"])
    gap_years = gaps.groupby("ticker").year.apply(lambda s: {int(y) for y in s}).to_dict()

    if args.from_gaps:
        tickers = sorted(gap_years, key=list(firms.ticker).index)
    else:
        tickers = args.tickers or []
    config.DISCOVERY_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    for t in tickers:
        out = config.DISCOVERY_CACHE_DIR / f"{t}.json"
        if out.exists() and not args.force:
            print(f"[{t}] cached, skipping")
            continue
        if t not in gap_years and not args.tickers:
            continue
        firm = firms[firms.ticker == t].iloc[0]
        print(f"[{t}] discovering ({len(prefixes_for(firm))} prefixes)...", flush=True)
        res = discover_firm(firm, gap_years.get(t, set(config.YEARS)))
        out.write_text(json.dumps(res, indent=1))
        n_err = sum(q["status"] != "ok" for q in res["queries"])
        print(f"[{t}] {res['n_urls_seen']} URLs seen, {len(res['candidates'])} candidates kept, "
              f"{n_err} prefix queries failed", flush=True)
        rows = update_review_csv(firm, res["candidates"])
        for r in rows.itertuples():
            print(f"     {'APPROVE' if r.approved == 'True' else 'reject '} {r.page_type:6s} "
                  f"{r.url}  [{r.page_title[:50]}]  ({r.reason})", flush=True)


if __name__ == "__main__":
    main()
