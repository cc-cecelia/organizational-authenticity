"""Polite, rate-limited HTTP client for SEC EDGAR.

- Sends the declared User-Agent on every request (SEC requirement).
- Enforces a global minimum interval between requests (< 10 req/s).
- Retries 429 / 5xx / network errors with exponential backoff and
  honours Retry-After.
- Optional on-disk caching so reruns cost zero requests.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

import requests

import config

log = logging.getLogger(__name__)


class EdgarClient:
    def __init__(self, user_agent: str = config.USER_AGENT,
                 max_rps: float = config.MAX_REQUESTS_PER_SEC):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        })
        self.min_interval = 1.0 / max_rps
        self._last_request = 0.0
        self.n_requests = 0  # reported at the end of a run

    def _throttle(self) -> None:
        """Sleep just long enough to keep under the request-rate ceiling."""
        wait = self._last_request + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def get(self, url: str) -> requests.Response:
        """GET with throttling and retries. Raises on final failure."""
        last_err: Optional[Exception] = None
        for attempt in range(config.MAX_RETRIES):
            self._throttle()
            self.n_requests += 1
            try:
                resp = self.session.get(url, timeout=config.REQUEST_TIMEOUT)
            except requests.RequestException as e:
                last_err = e
                backoff = 2 ** attempt
                log.warning("network error %s on %s; retry in %ss", e, url, backoff)
                time.sleep(backoff)
                continue
            if resp.status_code == 200:
                return resp
            if resp.status_code in (429, 500, 502, 503, 504):
                # SEC returns 429 or 403-with-message when throttled; back off hard.
                backoff = int(resp.headers.get("Retry-After", 2 ** (attempt + 1)))
                log.warning("HTTP %s on %s; retry in %ss", resp.status_code, url, backoff)
                time.sleep(backoff)
                last_err = requests.HTTPError(f"HTTP {resp.status_code}")
                continue
            # 403/404 etc. are not transient; fail immediately.
            resp.raise_for_status()
        raise RuntimeError(f"GET failed after {config.MAX_RETRIES} attempts: {url}: {last_err}")

    def get_json_cached(self, url: str, cache_path: Path, refresh: bool = False) -> dict:
        """Fetch JSON, caching the response body on disk."""
        if cache_path.exists() and not refresh:
            return json.loads(cache_path.read_text())
        data = self.get(url).json()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data))
        return data

    def download_file(self, url: str, dest: Path) -> int:
        """Download raw bytes to dest (skipped if already present). Returns size."""
        if dest.exists() and dest.stat().st_size > 0:
            return dest.stat().st_size
        content = self.get(url).content
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(content)
        tmp.rename(dest)  # atomic: never leave a half-written file behind
        return len(content)
