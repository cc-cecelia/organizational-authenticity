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
        # MMDD of the current fiscal year end (e.g. "0630" for MSFT).
        "fiscal_year_end": sub.get("fiscalYearEnd") or "",
    }
    return meta, filings


def archive_url(cik: int, accession: str, doc: str) -> str:
    return config.ARCHIVE_URL.format(cik=cik, acc_nodash=accession.replace("-", ""), doc=doc)


def _header_party(text: str, label: str) -> tuple:
    m = re.search(label + r":.*?COMPANY CONFORMED NAME:\s*([^\n<]+).*?"
                  r"CENTRAL INDEX KEY:\s*(\d+)", text, re.S)
    return (int(m.group(2)), m.group(1).strip()) if m else (None, "")


def header_parties(client: EdgarClient, cik: int, accession: str) -> dict:
    """Read filer and subject company from a filing's SGML header.

    Contested-solicitation filings have two parties:
      SUBJECT COMPANY = the company whose meeting it is,
      FILED BY        = who is soliciting.
    A dissident's DEFC14A against our firm has us as subject only; our firm's
    DEFC14A against another company (Broadcom vs Qualcomm, 2018) has us as
    filer only. Only a filing where we are both is our own proxy.
    """
    cache = config.CACHE_DIR / "headers" / f"{accession}.html"
    if cache.exists():
        text = cache.read_text()
    else:
        url = config.HEADER_URL.format(cik=cik, acc_nodash=accession.replace("-", ""), acc=accession)
        text = client.get(url).text
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(text)
    filer = _header_party(text, r"(?:FILED BY|FILER)")
    subject = _header_party(text, r"SUBJECT COMPANY")
    return {"filer_cik": filer[0], "filer_name": filer[1],
            # Single-party filings have no SUBJECT COMPANY block: the filer is the subject.
            "subject_cik": subject[0] or filer[0], "subject_name": subject[1] or filer[1]}


def fiscal_year_covered(filing_date: str, fye_mmdd: str):
    """Fiscal year of the latest fiscal year end before the filing date.

    A proxy reports on the just-completed fiscal year (its compensation and
    performance). Naming follows the Compustat `fyear` convention: a fiscal
    year ending in June-December is named by that calendar year (MSFT's year
    ending 2016-06-30 -> 2016); one ending in January-May is named by the
    prior year, the year most of its months fall in (HD's year ending
    2024-01-28 -> 2023). Uses the registrant's *current* fiscal year end;
    firms that changed FYE within the window would need a manual correction.
    """
    if not fye_mmdd or len(fye_mmdd) != 4:
        return None
    y = int(filing_date[:4])
    end_year = y if f"{y}-{fye_mmdd[:2]}-{fye_mmdd[2:]}" < filing_date else y - 1
    return end_year if int(fye_mmdd[:2]) >= 6 else end_year - 1
