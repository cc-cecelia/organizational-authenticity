"""
Thin, polite client for the Internet Archive's Wayback Machine.

Two responsibilities:
  1. CDX index queries (which captures exist for a URL, and when).
  2. Fetching raw archived bytes with the `id_` modifier, which returns the page
     exactly as originally captured, without the Wayback toolbar or rewritten
     links that would otherwise pollute text extraction.

Both are cached to disk so that re-runs (and the eventual 500-firm run) never
hit archive.org twice for the same thing, and both share one rate limiter with
exponential-backoff retries.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

import requests

import config

_session = requests.Session()
_session.headers.update({"User-Agent": config.USER_AGENT})

_rate_lock = threading.Lock()
_last_request_at = 0.0

WAYBACK_URL_RE = re.compile(r"/web/(\d{14})(?:[a-z]{2}_)?/(.+)$")


class WaybackError(Exception):
    """Raised when a request still fails after all retries.

    `cause` holds the last underlying error (HTTP status or exception text) so
    that logs show why, not just which URL.
    """

    def __init__(self, message: str, cause: str = ""):
        super().__init__(message)
        self.cause = cause or message


def _throttle() -> None:
    """Block until at least MIN_REQUEST_INTERVAL_S has passed since the last request."""
    global _last_request_at
    with _rate_lock:
        wait = config.MIN_REQUEST_INTERVAL_S - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def _get(url: str, params: Optional[dict] = None, timeout: int = 60,
         max_retries: int = config.MAX_RETRIES) -> requests.Response:
    """GET with global throttling and exponential backoff.

    Retries on connection errors, timeouts, truncated bodies, HTTP 429 and HTTP 5xx (archive.org
    returns these under load). Honors Retry-After when present. Any other status
    (including 404) is returned to the caller, because a 404 from Wayback is a
    meaningful answer ("not archived"), not a transient failure.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        _throttle()
        try:
            resp = _session.get(url, params=params, timeout=timeout, allow_redirects=True)
        except (requests.ConnectionError, requests.Timeout,
                requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ContentDecodingError) as exc:
            # Includes responses archive.org truncates mid-body under load.
            last_exc = exc
        else:
            if resp.status_code != 429 and resp.status_code < 500:
                return resp
            last_exc = WaybackError(f"HTTP {resp.status_code} for {resp.url}")
            retry_after = resp.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                time.sleep(min(int(retry_after), 300))
                continue
        if attempt < max_retries:
            wait = config.BACKOFF_BASE_S * (2 ** attempt)
            # 429/503 are archive.org's throttling signals; short backoffs were
            # observed to keep failing during the pilot, so wait longer.
            if isinstance(last_exc, WaybackError) and any(
                    f"HTTP {c}" in str(last_exc) for c in (429, 503)):
                wait = max(wait, config.THROTTLE_BACKOFF_MIN_S)
            time.sleep(wait)
    raise WaybackError(f"giving up on {url} {params or ''}: {last_exc}",
                       cause=f"{type(last_exc).__name__}: {last_exc}"[:200])


# --------------------------------------------------------------------------- #
# CDX
# --------------------------------------------------------------------------- #
def _cache_key(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:16]


def cdx_query(params: Dict[str, object], use_cache: bool = True,
              max_retries: int = config.MAX_RETRIES) -> List[Dict[str, str]]:
    """Run a CDX query and return rows as dicts keyed by the requested fields.

    `params` may contain repeated filters as a list under "filter". The response
    is cached on disk keyed by the exact parameter set. Discovery passes a low
    `max_retries` because an over-broad prefix 504s deterministically, and
    retrying it only burns time.
    """
    params = dict(params)
    params.setdefault("output", "json")
    path = config.CDX_CACHE_DIR / f"{_cache_key(params)}.json"
    if use_cache and path.exists():
        return json.loads(path.read_text())["rows"]

    resp = _get(config.CDX_ENDPOINT, params=params, timeout=config.CDX_TIMEOUT_S,
                max_retries=max_retries)
    if resp.status_code != 200:
        raise WaybackError(f"CDX HTTP {resp.status_code}: {params}",
                           cause=f"HTTP {resp.status_code}")
    text = resp.text.strip()
    data = json.loads(text) if text else []
    rows = [dict(zip(data[0], r)) for r in data[1:]] if data else []

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"params": params, "rows": rows}))
    return rows


def captures_for_url(url: str, year_from: int, year_to: int) -> List[Dict[str, str]]:
    """All 2xx/3xx captures of one exact URL in [year_from, year_to].

    CDX canonicalizes scheme, "www." and trailing slashes, so one query covers
    those variants. `collapse=timestamp:8` keeps at most one capture per day,
    which bounds response size for heavily archived pages without losing the
    ability to pick the capture nearest July 1.
    """
    return cdx_query({
        "url": url,
        "from": str(year_from),
        "to": str(year_to),
        "fl": "timestamp,original,statuscode,mimetype,digest,length",
        "filter": ["statuscode:[23].."],
        "collapse": "timestamp:8",
    })


# --------------------------------------------------------------------------- #
# Snapshot fetching
# --------------------------------------------------------------------------- #
@dataclass
class FetchResult:
    requested_timestamp: str
    requested_url: str
    final_timestamp: Optional[str]   # timestamp of the capture actually served
    final_url: Optional[str]         # original (live-web) URL actually served
    http_status: int                 # status Wayback returned for the final hop
    content_type: str
    redirect_chain: List[str] = field(default_factory=list)  # original URLs, in order
    content: bytes = b""

    @property
    def wayback_url(self) -> str:
        return f"{config.WAYBACK_PREFIX}{self.final_timestamp}/{self.final_url}"


def parse_wayback_url(wb_url: str):
    """Split 'https://web.archive.org/web/<ts>id_/<orig>' into (ts, orig)."""
    m = WAYBACK_URL_RE.search(wb_url)
    return (m.group(1), m.group(2)) if m else (None, None)


def fetch_snapshot(timestamp: str, original_url: str, use_cache: bool = True) -> FetchResult:
    """Fetch raw archived bytes for one capture using the `id_` modifier.

    Redirects are followed: for a capture archived as a 3xx, Wayback answers with
    a 302 to the archived target (at the nearest timestamp it holds). We record
    every hop's original URL and the final URL/timestamp so that the caller can
    apply the redirect acceptance rules.
    """
    key = f"{timestamp}_{hashlib.sha1(original_url.encode()).hexdigest()[:12]}"
    meta_path = config.RAW_CACHE_DIR / f"{key}.json"
    body_path = config.RAW_CACHE_DIR / f"{key}.bin"
    if use_cache and meta_path.exists() and body_path.exists():
        meta = json.loads(meta_path.read_text())
        return FetchResult(content=body_path.read_bytes(), **meta)

    resp = _get(f"{config.WAYBACK_PREFIX}{timestamp}id_/{original_url}",
                timeout=config.FETCH_TIMEOUT_S)
    chain = []
    for hop in list(resp.history) + [resp]:
        _, orig = parse_wayback_url(hop.url)
        if orig and (not chain or chain[-1] != orig):
            chain.append(orig)
    final_ts, final_orig = parse_wayback_url(resp.url)
    result = FetchResult(
        requested_timestamp=timestamp,
        requested_url=original_url,
        final_timestamp=final_ts,
        final_url=final_orig,
        http_status=resp.status_code,
        content_type=resp.headers.get("Content-Type", ""),
        redirect_chain=chain,
        content=resp.content,
    )

    config.RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    body_path.write_bytes(result.content)
    meta = asdict(result)
    meta.pop("content")
    meta_path.write_text(json.dumps(meta, indent=1))
    return result
