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
# A full annual proxy is typically 25k-80k words; Berkshire's famously lean
# proxies are 10k-15k. Anything under 5k words is almost surely a wrapper
# (NVDA 2022 filed an 86-word notice as a separate DEF 14A) or a body split
# across several files, so we flag it rather than silently accept it.
MIN_EXPECTED_WORDS = 5_000

# --- Analysis --------------------------------------------------------------
ANALYSIS_DIR = OUTPUT_DIR / "analysis"
LLM_CACHE_DIR = DATA_DIR / "llm_cache"     # committed: makes LLM results reproducible

# Loughran-McDonald Master Dictionary (1993-2025 release), downloaded from the
# authors' Google Drive link on https://sraf.nd.edu/loughranmcdonald-master-dictionary/
# Free for academic use; not redistributed in this repo, fetched on first run
# and verified against this checksum.
LM_URL = ("https://drive.usercontent.google.com/download?"
          "id=1iq2RUf8qGFEAk1g8wQntP3habOnR3fXF&export=download&confirm=t")
LM_SHA256 = "e2d1328682bab7d2187684fb9f5420bb730401c9eefc00daf835edd203f4859d"
LM_PATH = CACHE_DIR / "Loughran-McDonald_MasterDictionary_1993-2025.csv"

# LLM extraction. Haiku 5.5 rejects non-default sampling parameters, so
# temperature 0 is not available; determinism comes from schema-constrained
# output plus a content-hash cache (each section is extracted exactly once).
LLM_MODEL = "claude-haiku-5-5"
LLM_EFFORT = "low"
LLM_PROMPT_VERSION = "v3"   # bump to invalidate the cache after prompt edits (v2: hand-check fixes; v3: weight_of)
