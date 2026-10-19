"""
Page identification and snapshot validation.

Candidate pages
---------------
Each firm gets an ordered list of candidate URLs:
  1. Curated seed URLs from data/companies.csv (always first: "seeds override
     discovery").
  2. URLs found by anchored-prefix CDX discovery (discover.py), appended only for
     firms whose seeds leave year gaps.
  3. Redirect successors ("aliases") of the above, learned from observed redirect
     chains; they join their parent's page group.

Page groups are ordered by
  (seed before discovered, page_type priority, -years of CDX coverage, seed order)
so that (a) a dedicated values/mission page is preferred over a general About
page, and (b) the URL with the longest archive history is chosen first, which
keeps the same page across years wherever possible. For each year we walk this
list and take the first candidate with an acceptable capture.

Snapshot acceptance rules
-------------------------
A fetched capture is rejected (and the next capture / candidate is tried) if:
  - Wayback could not serve it (e.g. redirect target never archived);
  - a redirect resolved to a capture in a different calendar year;
  - it redirected to a homepage, a login page, or an unrelated domain;
  - it is not HTML or PDF;
  - it is a soft 404, or extracted text is below MIN_WORDS.
Every accept/reject is written to the decision log with its reason.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import config
import extract
import wayback


# --------------------------------------------------------------------------- #
# URL helpers
# --------------------------------------------------------------------------- #
def registrable_domain(url_or_host: str) -> str:
    """Approximate registrable domain as the last two host labels.

    Adequate for this sample (all .com/.xyz/.google/.jobs); a 500-firm run with
    country-code domains (e.g. .co.uk) should swap in `tldextract`.
    """
    host = urlparse(url_or_host).hostname if "//" in url_or_host else url_or_host
    host = (host or "").lower().split(":")[0]
    return ".".join(host.split(".")[-2:])


def _path_segments(url: str) -> List[str]:
    return [s for s in urlparse(url).path.split("/") if s]


def is_homepage(url: str) -> bool:
    """True if the path is empty or only locale / index segments ("/en-us/")."""
    return all(config.LOCALE_SEGMENT_RE.match(s) for s in _path_segments(url))


def canonical(url: str) -> str:
    """Comparable form: lowercase host without www, no scheme/port/trailing slash."""
    p = urlparse(url)
    host = (p.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    return f"{host}{p.path.rstrip('/').lower()}"


def classify_page_type(url: str) -> str:
    """'values' if the path names mission/values/purpose/credo etc., else 'about'.

    URL-based classification is cheap and scales to 500 firms; it is checked by
    eye in the coverage review and could be replaced by a content classifier.
    """
    path = urlparse(url).path
    if config.VALUES_PATH_RE.search(path):
        return "values"
    return "about"


# --------------------------------------------------------------------------- #
# Candidates
# --------------------------------------------------------------------------- #
@dataclass
class Candidate:
    url: str
    page_type: str
    source: str                 # "seed", "discovered" or "redirect_alias"
    rank_in_source: int
    group: str = ""             # logical page id; redirect successors share it
    captures: List[Dict[str, str]] = field(default_factory=list)

    @property
    def years_covered(self) -> Set[int]:
        return {int(c["timestamp"][:4]) for c in self.captures}


_SOURCE_PRIORITY = {"seed": 0, "discovered": 1}


def build_candidates(seed_urls: List[str], discovered: List[Dict],
                     aliases: Optional[List[Dict]] = None) -> List[Candidate]:
    """Query CDX for each candidate URL and return them in selection order.

    `aliases` are redirect successors learned on an earlier pass (see
    scrape.scrape_firm): {"url", "group"}. An alias inherits its group's
    page_type and is ranked with its group, so when a firm moves its values page
    to a new URL we keep following the same logical page instead of falling back
    to a different page.
    """
    cands: List[Candidate] = []
    seen: Set[str] = set()
    sources = [(u, "seed", i, None) for i, u in enumerate(seed_urls)]
    sources += [(d["url"], "discovered", i, None) for i, d in enumerate(discovered)]
    sources += [(a["url"], "redirect_alias", i, a["group"]) for i, a in enumerate(aliases or [])]
    for url, source, i, group in sources:
        key = canonical(url)
        if key in seen:
            continue
        seen.add(key)
        caps = wayback.captures_for_url(url, config.YEARS[0], config.YEARS[-1])
        cands.append(Candidate(url, classify_page_type(url), source, i, group or key, caps))

    # An alias that points at a URL already in the list (e.g. an old values URL
    # redirecting to a newer seed URL) merges that URL's group into the alias's
    # group, so both are treated as one logical page.
    by_key = {canonical(c.url): c for c in cands}
    for a in aliases or []:
        target = by_key.get(canonical(a["url"]))
        if target is not None and target.group != a["group"]:
            old = target.group
            for c in cands:
                if c.group == old:
                    c.group = a["group"]

    # Group-level ordering: (seed before discovered, values before about,
    # most years covered by the whole group, curated order). Within a group,
    # the root URL first, then members by their own coverage.
    roots = {c.group: c for c in cands if c.group == canonical(c.url)}
    for c in cands:
        if c.group in roots:
            c.page_type = roots[c.group].page_type
    group_years: Dict[str, Set[int]] = {}
    for c in cands:
        group_years.setdefault(c.group, set()).update(c.years_covered)

    def key(c: Candidate):
        root = roots.get(c.group, c)
        return (_SOURCE_PRIORITY.get(root.source, 2),
                config.PAGE_TYPE_PRIORITY[root.page_type],
                -len(group_years[c.group]),
                root.rank_in_source,
                c.group,
                0 if c is root else 1,
                -len(c.years_covered))
    return sorted(cands, key=key)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
@dataclass
class Attempt:
    """One fetch attempt and its outcome; becomes a row in the decision log."""
    candidate: Candidate
    capture: Dict[str, str]
    accepted: bool
    reason: str
    fetch: Optional[wayback.FetchResult] = None
    text: str = ""
    method: str = ""


def validate(fetch: wayback.FetchResult, cand: Candidate, year: int,
             allowed_domains: Set[str]) -> Tuple[bool, str, str, str]:
    """Apply the acceptance rules. Returns (ok, reason, text, method)."""
    if fetch.http_status != 200:
        reason = ("redirect_target_not_archived" if len(fetch.redirect_chain) > 1
                  else f"wayback_http_{fetch.http_status}")
        return False, reason, "", ""
    if not fetch.final_timestamp or int(fetch.final_timestamp[:4]) != year:
        return False, "resolved_outside_year", "", ""

    final = fetch.final_url or ""
    if registrable_domain(final) not in allowed_domains:
        return False, "redirect_offdomain", "", ""
    if config.LOGIN_PATH_RE.search(urlparse(final).path):
        return False, "redirect_login", "", ""
    if (canonical(final) != canonical(cand.url)
            and config.UNRELATED_PATH_RE.search(urlparse(final).path)):
        return False, "redirect_unrelated_page", "", ""
    # Landing on a homepage is only a failure if we did not ask for a root URL
    # (e.g. about.google/ is itself a legitimate About site) or if the host changed.
    if is_homepage(final) and (not is_homepage(cand.url)
                               or urlparse(final).hostname != urlparse(cand.url).hostname):
        return False, "redirect_homepage", "", ""
    # A redirect from a values page to a general About page (or vice versa) means
    # the requested page no longer exists; accepting it would mislabel page_type.
    # The other page is picked up under its own candidate instead.
    if canonical(final) != canonical(cand.url) and classify_page_type(final) != cand.page_type:
        return False, "redirect_type_mismatch", "", ""

    ctype = fetch.content_type.lower()
    if not any(t in ctype for t in ("html", "pdf", "xml")) and fetch.content[:5] != b"%PDF-":
        return False, "non_html_content", "", ""

    text, method = extract.extract_text(fetch.content, fetch.content_type)
    title = extract.page_title(fetch.content) if method != "pypdf" else ""
    if config.SOFT_404_RE.search(title) or (
            extract.word_count(text) < 150 and config.SOFT_404_RE.search(text)):
        return False, "soft_404", text, method
    if extract.word_count(text) < config.MIN_WORDS:
        return False, "thin_text", text, method
    return True, "accepted", text, method


def _ordered_captures(cand: Candidate, year: int) -> List[Dict[str, str]]:
    """Captures for one year: 200s nearest July 1 first, then 3xx nearest July 1.

    Captures whose content digest matches one already queued are skipped, since
    they would yield the identical page (and the identical rejection).
    """
    anchor = config.target_date(year)

    def dist(c):
        return abs((datetime.strptime(c["timestamp"], "%Y%m%d%H%M%S") - anchor).total_seconds())

    in_year = [c for c in cand.captures if int(c["timestamp"][:4]) == year]
    ok = sorted((c for c in in_year if c["statuscode"] == "200"), key=dist)
    redir = sorted((c for c in in_year if c["statuscode"].startswith("3")), key=dist)

    out, digests = [], set()
    for group, cap in ((ok, config.MAX_200_ATTEMPTS), (redir, config.MAX_3XX_ATTEMPTS)):
        n = 0
        for c in group:
            if c["digest"] in digests:
                continue
            digests.add(c["digest"])
            out.append(c)
            n += 1
            if n >= cap:
                break
    return out


def select_year(cands: List[Candidate], year: int, allowed_domains: Set[str]
                ) -> Tuple[Optional[Attempt], List[Attempt]]:
    """Walk candidates in order; return (accepted attempt or None, all attempts)."""
    attempts: List[Attempt] = []
    for cand in cands:
        for cap in _ordered_captures(cand, year):
            try:
                fetch = wayback.fetch_snapshot(cap["timestamp"], cap["original"])
            except wayback.WaybackError as exc:
                attempts.append(Attempt(cand, cap, False, f"fetch_error: {exc.cause}"))
                continue
            ok, reason, text, method = validate(fetch, cand, year, allowed_domains)
            att = Attempt(cand, cap, ok, reason, fetch, text, method)
            attempts.append(att)
            if ok:
                return att, attempts
    return None, attempts


def gap_reason(cands: List[Candidate], year: int, attempts: List[Attempt]) -> Tuple[str, str]:
    """Summarize why a company-year has no accepted snapshot: (reason, detail)."""
    if not cands:
        return "no_candidate_urls", "no seed or discovered URL for this firm"
    if not attempts:
        covered = sorted({y for c in cands for y in c.years_covered})
        return ("no_captures_in_year",
                f"{len(cands)} candidate URL(s) have no 2xx/3xx capture in {year}; "
                f"archived years across candidates: {covered}")
    counts = Counter(a.reason.split(":")[0] for a in attempts)
    primary = counts.most_common(1)[0][0]
    detail = "; ".join(f"{r} x{n}" for r, n in counts.most_common())
    return f"all_captures_rejected:{primary}", f"{len(attempts)} capture(s) tried: {detail}"
