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
SOFT_404_RE = re.compile(
    r"(page (you requested )?(was )?not (be )?found|404 error|error 404|"
    r"page (cannot|can't|could not) be found|no longer available|page does not exist)",
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
