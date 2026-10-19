"""Map sample tickers to SEC CIKs.

Source: SEC's company_tickers.json (current ticker -> CIK snapshot).
That file reflects *today's* tickers, so two failure modes need handling:
  1. Ticker punctuation: SEC uses "BRK-B" where our list has "BRK.B".
  2. Entity changes: a ticker can move to a new registrant (e.g. a new
     holding company), so the current CIK may have no 2016-2024 history.
     download_proxies.py checks each CIK's earliest filing against the
     window and flags such cases; fixes go in data/cik_overrides.csv with
     a written reason.
"""
from __future__ import annotations

import csv

import config
from edgar_client import EdgarClient


def normalize_ticker(ticker: str) -> str:
    """Our list uses class-share dots (BRK.B); SEC uses dashes (BRK-B)."""
    return ticker.strip().upper().replace(".", "-")


def load_overrides() -> dict:
    """ticker -> (cik, reason) from the hand-curated overrides file."""
    if not config.CIK_OVERRIDES_CSV.exists():
        return {}
    with open(config.CIK_OVERRIDES_CSV, newline="") as f:
        return {r["ticker"].strip(): (int(r["cik"]), r["reason"].strip())
                for r in csv.DictReader(f)}


def build_cik_map(client: EdgarClient, tickers: list) -> dict:
    """Return {ticker: {cik, sec_ticker, sec_title, cik_source, cik_note}}."""
    raw = client.get_json_cached(config.TICKERS_URL,
                                 config.CACHE_DIR / "company_tickers.json")
    by_ticker = {v["ticker"].upper(): v for v in raw.values()}
    overrides = load_overrides()

    out = {}
    for t in tickers:
        sec_t = normalize_ticker(t)
        hit = by_ticker.get(sec_t)
        row = {
            "sec_ticker": sec_t,
            "sec_title": hit["title"] if hit else "",
            "cik_from_tickers_json": hit["cik_str"] if hit else None,
        }
        if t in overrides:
            cik, reason = overrides[t]
            row.update(cik=cik, cik_source="override", cik_note=reason)
        elif hit:
            row.update(cik=hit["cik_str"], cik_source="company_tickers.json", cik_note="")
        else:
            row.update(cik=None, cik_source="unmapped",
                       cik_note=f"{sec_t} not in company_tickers.json")
        out[t] = row
    return out
