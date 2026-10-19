"""Shared configuration for the Part 2 EDGAR proxy-statement pipeline.

Every path and tunable lives here so the downloader and later analysis
steps agree on where things are and what the sample window is.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Paths -----------------------------------------------------------------
PART2_DIR = Path(__file__).resolve().parents[1]          # part2_lived_values/
REPO_DIR = PART2_DIR.parent
COMPANIES_CSV = REPO_DIR / "data" / "companies.csv"      # shared 50-firm sample (read only)

DATA_DIR = PART2_DIR / "data"
CIK_OVERRIDES_CSV = DATA_DIR / "cik_overrides.csv"       # hand-curated, committed
CACHE_DIR = DATA_DIR / "cache"                           # SEC JSON responses (gitignored)
RAW_DIR = DATA_DIR / "raw"                               # raw filing HTML (gitignored)
TEXT_DIR = DATA_DIR / "text"                             # clean extracted text (gitignored)

OUTPUT_DIR = PART2_DIR / "output"
CIK_MAP_OUT = OUTPUT_DIR / "cik_map.csv"
MANIFEST_OUT = OUTPUT_DIR / "filings_manifest.csv"
COVERAGE_OUT = OUTPUT_DIR / "proxy_coverage.csv"
GAPS_OUT = OUTPUT_DIR / "coverage_gaps.csv"

# --- Sample window ---------------------------------------------------------
# "Year" = calendar year of the EDGAR filing date. A proxy filed in spring
# 2020 mostly describes fiscal 2019 (compensation, board actions); we keep
# the filing year as the key and record report/filing dates so analysts can
# re-key by fiscal year (e.g. MSFT files in October for a June fiscal year).
FIRST_YEAR = 2016
LAST_YEAR = 2024

# Definitive proxy forms. In a contested director election (proxy fight)
# the company's annual proxy is filed as DEFC14A instead of DEF 14A
# (e.g. XOM 2021 vs Engine No. 1). Dissidents also file DEFC14A under the
# target's CIK, so DEFC14A is accepted only when the SGML header shows the
# registrant itself as FILED BY. Amendments (DEF 14A/A, DEFC14A/A) are logged
# but not selected: they range from one-page corrections to restatements.
PROXY_FORMS = ("DEF 14A", "DEFC14A")
CONTESTED_FORM = "DEFC14A"
AMENDMENT_FORMS = ("DEF 14A/A", "DEFC14A/A")

# --- SEC access policy -----------------------------------------------------
# SEC fair-access rules: declare a User-Agent with contact info and stay
# under 10 requests/second. We target 8/s to leave headroom.
USER_AGENT = os.environ.get(
    "EDGAR_USER_AGENT", "Chang Gao (research) ceceliagao1129@gmail.com"
)
MAX_REQUESTS_PER_SEC = 8.0
MAX_RETRIES = 5
REQUEST_TIMEOUT = 60  # seconds

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{doc}"
HEADER_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{acc}-index-headers.html"

# --- Quality thresholds ----------------------------------------------------
# A full annual proxy is typically 30k-120k words. Anything far below this
# probably means the primary document is a wrapper and the body lives in
# other files of the filing, so we flag it for review rather than silently
# accept it.
MIN_EXPECTED_WORDS = 10_000
