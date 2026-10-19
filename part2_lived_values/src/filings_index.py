"""List a registrant's proxy filings from the EDGAR submissions API.

data.sec.gov/submissions/CIK##########.json holds the most recent ~1000
filings inline ("recent") and pages older history into extra JSON files
("files"), each with a filingFrom/filingTo range. Heavy filers such as
JPM (tens of thousands of structured-note 424B2s) spread 2016-2024 across
dozens of pages, so we fetch only the pages whose date range overlaps the
sample window. Every page is cached on disk.
"""
from __future__ import annotations

import re

import config
from edgar_client import EdgarClient

PROXY_FORMS = set(config.PROXY_FORMS) | set(config.AMENDMENT_FORMS)


def _rows_from_block(block: dict) -> list:
    """Turn the column-oriented submissions block into a list of dicts."""
    keys = list(block.keys())
    n = len(block.get("accessionNumber", []))
    return [{k: block[k][i] for k in keys} for i in range(n)]


def list_filings(client: EdgarClient, cik: int) -> tuple:
    """Return (meta, filings) for a CIK.

    meta: entity name, former names, earliest filing date seen.
    filings: every DEF 14A / DEF 14A/A dated within the sample window.
    """
    cik10 = f"{cik:010d}"
    name = f"CIK{cik10}.json"
    sub = client.get_json_cached(config.SUBMISSIONS_URL.format(name=name),
                                 config.CACHE_DIR / "submissions" / name)

    win_start = f"{config.FIRST_YEAR}-01-01"
    win_end = f"{config.LAST_YEAR}-12-31"

    rows = _rows_from_block(sub["filings"]["recent"])
    earliest = min((r["filingDate"] for r in rows), default="")
    for page in sub["filings"].get("files", []):
        earliest = min(earliest, page["filingFrom"]) if earliest else page["filingFrom"]
        # Skip pages that lie entirely outside the window.
        if page["filingTo"] < win_start or page["filingFrom"] > win_end:
            continue
        data = client.get_json_cached(config.SUBMISSIONS_URL.format(name=page["name"]),
                                      config.CACHE_DIR / "submissions" / page["name"])
        rows.extend(_rows_from_block(data))

    seen = set()
    filings = []
    for r in rows:
        if r["form"] not in PROXY_FORMS or not (win_start <= r["filingDate"] <= win_end):
            continue
        if r["accessionNumber"] in seen:
            continue
        seen.add(r["accessionNumber"])
        filings.append({
            "cik": cik,
            "accession": r["accessionNumber"],
            "form": r["form"],
            "filing_date": r["filingDate"],
            "report_date": r.get("reportDate", ""),
            "primary_doc": r.get("primaryDocument", ""),
            "primary_doc_desc": r.get("primaryDocDescription", ""),
            "size_bytes_reported": r.get("size", ""),
        })
    filings.sort(key=lambda f: f["filing_date"])

    meta = {
        "entity_name": sub.get("name", ""),
        "former_names": "; ".join(fn["name"] for fn in sub.get("formerNames", [])),
        "earliest_filing": earliest,
    }
    return meta, filings


def archive_url(cik: int, accession: str, doc: str) -> str:
    return config.ARCHIVE_URL.format(cik=cik, acc_nodash=accession.replace("-", ""), doc=doc)


def filed_by(client: EdgarClient, cik: int, accession: str) -> tuple:
    """Return (filer_cik, filer_name) from a filing's SGML header.

    Filings where our firm is only the SUBJECT COMPANY (e.g. a dissident's
    DEFC14A) list the dissident under FILED BY. A self-filed form has either
    a FILER block or a FILED BY block naming the registrant.
    """
    cache = config.CACHE_DIR / "headers" / f"{accession}.html"
    if cache.exists():
        text = cache.read_text()
    else:
        url = config.HEADER_URL.format(cik=cik, acc_nodash=accession.replace("-", ""), acc=accession)
        text = client.get(url).text
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(text)
    m = re.search(r"(?:FILED BY|FILER):.*?COMPANY CONFORMED NAME:\s*([^\n<]+).*?"
                  r"CENTRAL INDEX KEY:\s*(\d+)", text, re.S)
    if not m:
        return None, ""
    return int(m.group(2)), m.group(1).strip()
