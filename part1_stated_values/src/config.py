"""
Shared configuration for the Part 1 Wayback scraper.

Every tunable constant lives here so that methodological choices (target date,
rate limits, page-type keywords, validation thresholds) are visible in one place
and documented next to their values.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PART1_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PART1_DIR.parent
COMPANIES_CSV = REPO_ROOT / "data" / "companies.csv"

# Raw cache (git-ignored). Everything here can be regenerated from Wayback.
CACHE_DIR = PART1_DIR / "cache"
CDX_CACHE_DIR = CACHE_DIR / "cdx"            # one JSON file per CDX query
RAW_CACHE_DIR = CACHE_DIR / "raw"            # raw archived bytes + metadata
DISCOVERY_CACHE_DIR = CACHE_DIR / "discovery"  # anchored-prefix discovery results

OUTPUT_DIR = PART1_DIR / "output"

# --------------------------------------------------------------------------- #
# Sample window and snapshot selection
# --------------------------------------------------------------------------- #
YEARS = list(range(2016, 2025))  # 2016..2024 inclusive, 9 time points


def target_date(year: int) -> datetime:
    """Mid-year anchor: we pick the capture nearest July 1 of each year.

    July 1 sits in the middle of the calendar year, so the chosen snapshot is the
    most representative single view of "what the page said that year" and is
    least likely to straddle a January redesign.
    """
    return datetime(year, 7, 1)


# How many captures per (candidate URL, year) we try before falling back to the
# next candidate. Bounds cost while tolerating a few broken captures.
MAX_200_ATTEMPTS = 3
MAX_3XX_ATTEMPTS = 2

# --------------------------------------------------------------------------- #
# HTTP politeness
# --------------------------------------------------------------------------- #
USER_AGENT = (
    "organizational-authenticity-research/0.1 "
    "(academic RA task; Wharton-TAU lab; contact via repo owner)"
)
MIN_REQUEST_INTERVAL_S = 1.5   # global spacing between requests to archive.org
MAX_RETRIES = 5                # retries on 429 / 5xx / connection errors
BACKOFF_BASE_S = 4.0           # exponential backoff: 4, 8, 16, 32, 64 s
THROTTLE_BACKOFF_MIN_S = 20.0  # floor for the wait after HTTP 429 / 503
CDX_TIMEOUT_S = 90
FETCH_TIMEOUT_S = 60

CDX_ENDPOINT = "https://web.archive.org/cdx/search/cdx"
WAYBACK_PREFIX = "https://web.archive.org/web/"

# --------------------------------------------------------------------------- #
# Page identification
# --------------------------------------------------------------------------- #
# Page types, in priority order. "values" pages state mission / values / purpose
# directly and are the closest match to the "stated values" construct, so they
# are preferred; the general "about" page is the fallback.
PAGE_TYPE_PRIORITY = {"values": 0, "about": 1}

# URL path keywords that mark a dedicated values-type page.
VALUES_PATH_RE = re.compile(
    r"(values|mission|purpose|credo|principles|vision|culture|chevron-way|"
    r"ownman|owners-manual|philosophy)",
    re.I,
)
# URL path keywords that mark a general about-type page.
ABOUT_PATH_RE = re.compile(
    r"(about|who-we-are|our-company|company|corporate|our-firm|overview)", re.I
)

# --------------------------------------------------------------------------- #
# Redirect / content validation
# --------------------------------------------------------------------------- #
# A path made only of locale segments (e.g. "/", "/en-us/", "/us/en/") is treated
# as a homepage. Landing on a homepage means the About page no longer existed.
LOCALE_SEGMENT_RE = re.compile(r"^([a-z]{2}([-_][a-z]{2})?|index\.\w+|home(\.\w+)?|default\.\w+)$", re.I)
LOGIN_PATH_RE = re.compile(r"(login|signin|sign-in|logon|auth|sso|account)", re.I)
# A redirect landing on a sitemap, search, or error page means the requested page
# was retired (Apple's /about/ redirected to /sitemap/ from 2018 on).
UNRELATED_PATH_RE = re.compile(r"(sitemap|site-map|/search|/404|/error|not-?found)", re.I)
SOFT_404_RE = re.compile(
    r"(page (you requested )?(was )?not (be )?found|404 error|error 404|"
    r"page (cannot|can't|could not) be found|no longer available|page does not exist|"
    # Starbucks 2016 error page (found by the LLM step coding it all-zero):
    # "We're sorry — something has gone wrong ... We might have removed the page".
    r"something (has )?gone wrong|might have removed the page|link you clicked might be old)",
    re.I,
)

# Pages below this many words after extraction are rejected as thin (redirect
# stubs, JS shells, cookie walls). Kept low because some genuine values pages are
# short (e.g. a single mission paragraph).
MIN_WORDS = 40

# If the structural (BeautifulSoup) extraction keeps at least this many times as
# many words as trafilatura, trafilatura is assumed to have dropped content
# (card layouts) and the structural text is used. See extract.extract_text.
EXTRACTION_RECALL_RATIO = 1.5

# --------------------------------------------------------------------------- #
# Discovery (anchored-prefix CDX queries; only for firms with seed gaps)
# --------------------------------------------------------------------------- #
# A domain-wide CDX prefix query times out (HTTP 504 after ~60 s for large
# sites), so discovery queries narrow prefixes "host/<base><kw>" instead.
# Prefix matching is on the URL string, so "about" also matches "about-us",
# "about-jpmc", "aboutoxy", and "our" matches "our-company", "our-values".
DISCOVERY_KEYWORDS = [
    "about", "who", "our", "company", "corporate",
    "values", "mission", "purpose", "credo",
]
DISCOVERY_KEEP_RE = re.compile(
    r"(about|values|mission|purpose|who-we-are|our-company|credo|principles|"
    r"culture|our-story|philosophy|vision|overview)",
    re.I,
)
# Sub-pages that live under /about but are not the About page itself.
DISCOVERY_DROP_RE = re.compile(
    r"(career|job|news|press|media|contact|investor|leadership/|board|"
    r"location|office|art-?collection|award|history|event|sitemap|search|"
    r"supplier|privacy|terms|legal|\.(jpg|jpeg|png|gif|css|js|xml|json)$|"
    r"[?#])",
    re.I,
)
DISCOVERY_MAX_DEPTH = 4         # path segments; deeper pages are rarely the About page
DISCOVERY_TOP_K = 5             # discovered candidates appended after seeds

# Human-in-the-loop gate: discovered candidates are written here with a
# pre-filled `approved` judgment and `reason`; scrape.py uses approved rows only.
DISCOVERY_REVIEW_CSV = REPO_ROOT / "data" / "discovery_review.csv"

# Pre-fill rules for the review CSV (applied to URL path + page title).
# Reject first: sub-organizations and pages about a specific function.
REVIEW_REJECT_RE = re.compile(
    r"(institute|foundation|subsidiar|ventures|capital-markets|governance|"
    r"board|director|committee|career|job|recruit|investor|esg|sustainab|"
    r"citizenship|diversity|inclusion|human-rights|supplier|procurement|"
    r"news|press|policy|policies|leadership|executive|management-committee|"
    r"client|product|service|solution)",
    re.I,
)
# Approve: the page is clearly about the parent company or its values.
REVIEW_APPROVE_RE = re.compile(
    r"(values|mission|purpose|principles|credo|culture|who-we-are|who we are|"
    r"our-company|our company|about|our-story|our story|overview|vision)",
    re.I,
)

# --------------------------------------------------------------------------- #
# LLM analysis (llm_analyze.py)
# --------------------------------------------------------------------------- #
# Same model, effort and determinism approach as Part 2: Haiku 5.5 rejects
# non-default sampling parameters, so there is no temperature 0; outputs are
# schema-constrained and every request is cached by a SHA-256 fingerprint of
# (model, effort, prompt version, task, system, prompt, schema), so a rerun
# never re-queries and published results are fixed.
LLM_MODEL = "claude-haiku-5-5"
LLM_EFFORT = "low"
LLM_PROMPT_VERSION = "p1v2"    # themes task; bump after any prompt/schema edit (p1v2: pilot hand-check fixes)
# change task (c2: rotating featured content is cosmetic; substantive needs a change
# to the page's own standing statements. v1 called 75% of diffs substantive, many of
# them teaser swaps such as BAC 2019 "Investing in women" -> hunger-relief teaser).
LLM_CHANGE_PROMPT_VERSION = "c2"
LLM_CACHE_DIR = CACHE_DIR / "llm"

# Change detection: word-sequence similarity (difflib ratio) between a page and
# the same logical page in the prior collected year. At or above the threshold
# the edit is treated as minor without an LLM call; below it, the LLM judges
# substantive vs cosmetic from the diff.
# Calibration (read the diffs per similarity band over all 242 eligible pairs):
# [0.98, 1) were figure updates and capitalization only ("121,000 -> 120,300
# employees"); [0.90, 0.98) still held substantive edits (MPC 2020->21 removed
# "We aim for an accident-free, incident-free workplace", sim 0.947; JPM
# 2021->22 added a customer principle, sim 0.941). LLM calls cost fractions of
# a cent, so the threshold favors recall.
SIMILARITY_THRESHOLD = 0.98

STATED_VALUES_CSV = OUTPUT_DIR / "stated_values.csv"
