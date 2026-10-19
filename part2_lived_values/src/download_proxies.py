"""Download DEF 14A proxy statements from EDGAR for the sample firms.

Usage (from the repo root, inside the venv):
    python part2_lived_values/src/download_proxies.py --tickers MSFT JPM XOM
    python part2_lived_values/src/download_proxies.py            # all 50 firms

Pipeline per firm:
  1. ticker -> CIK (company_tickers.json + overrides), sanity-checked
     against the registrant's earliest filing date.
  2. List every definitive proxy (DEF 14A, or DEFC14A in a proxy fight)
     and their amendments filed 2016-2024 (submissions API, including
     paged history). DEFC14As filed by dissidents are excluded.
  3. Download each eligible primary document (raw) and extract clean text.
  4. Choose one proxy per firm x filing-year (rule below) and record every
     year that has no usable proxy, with a reason.

Selection rule when a year has several definitive proxies: prefer the annual-meeting
proxy over special-meeting proxies; among several annual ones take the
earliest. Non-selected filings stay in the manifest.

Outputs (part2_lived_values/output/):
  cik_map.csv           ticker -> CIK resolution and sanity checks
  filings_manifest.csv  every proxy filing found, selected or not
  proxy_coverage.csv    one row per firm x year (the panel skeleton)
  coverage_gaps.csv     the rows of proxy_coverage that are gaps or flagged
Reruns are cheap: SEC JSON and raw filings are cached on disk.
"""
from __future__ import annotations

import argparse
import logging
import sys

import pandas as pd

import config
from cik_map import build_cik_map
from edgar_client import EdgarClient
from extract_text import classify_meeting, html_to_text, plain_to_text
from filings_index import archive_url, fiscal_year_covered, header_parties, list_filings

log = logging.getLogger("download_proxies")
YEARS = list(range(config.FIRST_YEAR, config.LAST_YEAR + 1))


def rel(p) -> str:
    """Repo-relative path for portable output tables."""
    return str(p.relative_to(config.REPO_DIR)) if p else ""


def fetch_and_extract(client: EdgarClient, ticker: str, f: dict) -> dict:
    """Download one filing's primary document and write its clean text.

    Returns the filing dict enriched with paths, sizes, text stats, meeting
    type, or an 'error' key on failure.
    """
    doc = f["primary_doc"]
    stem = f"{f['filing_date']}_{f['accession']}"
    ext = doc.rsplit(".", 1)[-1].lower() if "." in doc else "htm"
    raw_path = config.RAW_DIR / ticker / f"{stem}.{ext}"
    text_path = config.TEXT_DIR / ticker / f"{stem}.txt"
    f = dict(f, source_url=archive_url(f["cik"], f["accession"], doc))

    if not doc:
        return dict(f, error="no primary document listed in submissions API")
    try:
        f["raw_bytes"] = client.download_file(f["source_url"], raw_path)
    except Exception as e:  # logged as a coverage gap, never fatal
        return dict(f, error=f"download failed: {e}")
    f["raw_path"] = rel(raw_path)

    raw = raw_path.read_bytes()
    if ext in ("htm", "html"):
        text, stats = html_to_text(raw)
    elif ext == "txt":
        text, stats = plain_to_text(raw)
    else:
        return dict(f, error=f"unsupported primary document type .{ext}")

    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(text)
    f.update(stats)
    f["text_path"] = rel(text_path)
    f["meeting_type"] = classify_meeting(text)
    return f


def process_firm(client: EdgarClient, firm: dict, cmap: dict) -> tuple:
    """Return (manifest_rows, coverage_rows, cik_row) for one firm."""
    t = firm["ticker"]
    m = cmap[t]
    base = {"ticker": t, "company_name": firm["company_name"], "sector": firm["sector"]}
    cik_row = dict(base, **{k: v for k, v in m.items() if k != "ciks"})
    cik_row["cik"] = ";".join(str(c) for c in m["ciks"])

    if not m["ciks"]:
        cov = [dict(base, cik="", filing_year=y, status="gap",
                    gap_reason="no_cik", notes=m["cik_note"]) for y in YEARS]
        return [], cov, cik_row

    # Union the proxy filings of every registrant in the firm's CIK chain.
    metas, filings, seen = [], [], set()
    for cik in m["ciks"]:
        meta, fl = list_filings(client, cik)
        metas.append(meta)
        for f in fl:
            if f["accession"] not in seen:
                seen.add(f["accession"])
                f["fiscal_year_end_raw"] = meta["fiscal_year_end"]
                filings.append(f)
    filings.sort(key=lambda f: f["filing_date"])
    cik_row["entity_name"] = " ; ".join(x["entity_name"] for x in metas)
    cik_row["former_names"] = " ; ".join(x["former_names"] for x in metas if x["former_names"])
    cik_row["earliest_filing"] = min(x["earliest_filing"] for x in metas)
    # Sanity check: the registrant chain must have existed throughout the window.
    cik_row["history_covers_window"] = cik_row["earliest_filing"] <= f"{config.FIRST_YEAR}-01-01"
    if not cik_row["history_covers_window"]:
        log.warning("%s: CIK %s earliest filing %s is after window start; "
                    "check for a predecessor registrant and add an override",
                    t, cik_row["cik"], cik_row["earliest_filing"])

    manifest = []
    for f in filings:
        f["eligible"] = f["form"] in config.PROXY_FORMS
        if f["form"] == config.CONTESTED_FORM:
            hp = header_parties(client, f["cik"], f["accession"])
            f["filed_by"] = hp["filer_name"]
            f["subject_company"] = hp["subject_name"]
            if hp["filer_cik"] != f["cik"]:
                f["eligible"] = False
                f["excluded_reason"] = f"filed by third party ({hp['filer_name']})"
            elif hp["subject_cik"] != f["cik"]:
                f["eligible"] = False
                f["excluded_reason"] = f"our solicitation at another company ({hp['subject_name']})"
        if f["eligible"]:
            f = fetch_and_extract(client, t, f)
            if "error" in f:
                log.warning("%s %s: %s", t, f["accession"], f["error"])
        manifest.append(dict(base, filing_year=int(f["filing_date"][:4]), **f))

    coverage = []
    for y in YEARS:
        in_year = [r for r in manifest if r["filing_year"] == y]
        originals = [r for r in in_year if r["eligible"]]
        n_amend = sum(r["form"] in config.AMENDMENT_FORMS for r in in_year)
        row = dict(base, cik=cik_row["cik"], filing_year=y, n_definitive_in_year=len(originals),
                   n_amendments_in_year=n_amend, status="gap", gap_reason="", notes="")

        usable = [r for r in originals if "error" not in r]
        if not originals:
            row["gap_reason"] = ("only_amendment_in_year" if n_amend
                                 else "no_def14a_in_filing_year")
            if not cik_row["history_covers_window"] and not filings:
                row["gap_reason"] = "cik_history_starts_after_window"
            # Nearby filing dates help spot timing shifts (e.g. Dec vs Jan filing).
            dates = [r["filing_date"] for r in manifest if r["eligible"]]
            prev = max((d for d in dates if d < f"{y}-01-01"), default="none")
            nxt = min((d for d in dates if d > f"{y}-12-31"), default="none")
            row["notes"] = f"nearest definitive proxy before: {prev}; after: {nxt}"
        elif not usable:
            row["gap_reason"] = "retrieval_failed"
            row["notes"] = "; ".join(r["error"] for r in originals)
        else:
            annual = [r for r in usable if r.get("meeting_type") == "annual"]
            unknown = [r for r in usable if r.get("meeting_type") == "unknown"]
            pick_from = annual or unknown
            if not pick_from:
                row["gap_reason"] = "only_special_meeting_proxy"
                row["notes"] = "; ".join(r["accession"] for r in usable)
            else:
                chosen = min(pick_from, key=lambda r: r["filing_date"])
                chosen["selected"] = True
                notes = []
                if len(originals) > 1:
                    others = [f"{r['accession']} ({r.get('meeting_type', 'n/a')})"
                              for r in originals if r is not chosen]
                    notes.append("multiple definitive proxies; not selected: " + ", ".join(others))
                if chosen["form"] == config.CONTESTED_FORM:
                    notes.append("contested election: company proxy filed as DEFC14A")
                if chosen.get("meeting_type") == "unknown":
                    notes.append("meeting type not detected in opening text")
                words = chosen.get("prose_words", 0) + chosen.get("table_words", 0)
                if words < config.MIN_EXPECTED_WORDS:
                    notes.append(f"short text ({words} words): possible split or wrapper document")
                row.update({k: chosen.get(k, "") for k in (
                    "accession", "form", "filing_date", "report_date", "meeting_type",
                    "primary_doc", "source_url", "raw_path", "text_path", "raw_bytes",
                    "prose_words", "table_words", "text_chars")})
                row["cik"] = chosen["cik"]  # the registrant that filed this year's proxy
                fye = chosen["fiscal_year_end_raw"]
                row["fiscal_year_end"] = f"{fye[:2]}-{fye[2:]}" if fye else ""  # MM-DD
                row["fiscal_year_covered"] = fiscal_year_covered(chosen["filing_date"], fye)
                row["status"] = "ok_flagged" if notes else "ok"
                row["notes"] = "; ".join(notes)
        coverage.append(row)

    for r in manifest:
        r.setdefault("selected", False)
    return manifest, coverage, cik_row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tickers", nargs="*", help="subset of tickers (default: all in companies.csv)")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    firms = pd.read_csv(config.COMPANIES_CSV)[["ticker", "company_name", "sector"]]
    if args.tickers:
        wanted = [t.upper() for t in args.tickers]
        missing = set(wanted) - set(firms["ticker"])
        if missing:
            ap.error(f"tickers not in companies.csv: {sorted(missing)}")
        firms = firms[firms["ticker"].isin(wanted)]

    client = EdgarClient()
    log.info("User-Agent: %s | max %.0f req/s", config.USER_AGENT, config.MAX_REQUESTS_PER_SEC)
    cmap = build_cik_map(client, firms["ticker"].tolist())

    manifest, coverage, cik_rows = [], [], []
    for firm in firms.to_dict("records"):
        log.info("== %s (CIK %s)", firm["ticker"], cmap[firm["ticker"]]["ciks"])
        mf, cov, ck = process_firm(client, firm, cmap)
        manifest += mf
        coverage += cov
        cik_rows.append(ck)

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(cik_rows).to_csv(config.CIK_MAP_OUT, index=False)
    pd.DataFrame(manifest).to_csv(config.MANIFEST_OUT, index=False)
    cov_df = pd.DataFrame(coverage)
    cov_df.to_csv(config.COVERAGE_OUT, index=False)
    cov_df[cov_df["status"] != "ok"].to_csv(config.GAPS_OUT, index=False)

    log.info("done: %d HTTP requests; %d firm-years ok, %d flagged, %d gaps",
             client.n_requests, (cov_df.status == "ok").sum(),
             (cov_df.status == "ok_flagged").sum(), (cov_df.status == "gap").sum())
    return 0


if __name__ == "__main__":
    sys.exit(main())
