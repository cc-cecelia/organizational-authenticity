"""
Visible body-text extraction from raw archived pages.

Strategy (in order):
  1. PDF bytes  -> pypdf (used for Berkshire Hathaway's Owner's Manual).
  2. HTML       -> trafilatura, a boilerplate-removal library tuned on web pages.
  3. A structural BeautifulSoup pass is always computed too: it drops nav,
     header, footer, aside, script/style, chrome identified by ARIA role or by
     class/id token, and link-dense lists (menus). It replaces trafilatura's text
     when trafilatura is thin (< MIN_WORDS) or when it recovers
     >= EXTRACTION_RECALL_RATIO x as much text, which is the signature of a
     card/tile layout that trafilatura (tuned for articles) partly discarded.

The method actually used is returned so every row records how its text was
produced, which lets us audit extraction quality by method later.
"""
from __future__ import annotations

import io
import re
from typing import Tuple

import trafilatura
from bs4 import BeautifulSoup, Comment, Declaration, Doctype, ProcessingInstruction

import config

# Tags that never carry body text we want.
# <form> is deliberately NOT dropped: ASP.NET WebForms sites (common among
# 2016-2019 corporate sites, e.g. ExxonMobil) wrap the entire page in one <form>.
_DROP_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside",
              "iframe", "svg", "button", "select", "template"]
# ARIA roles for site chrome.
_DROP_ROLES = re.compile(r"^(navigation|banner|contentinfo|search|dialog|menu|menubar)$", re.I)
# Whole class/id tokens that mark chrome or overlays. Matched per token, not as
# substrings: an earlier substring rule matched "tab-nav-content" (JPM's tabbed
# Business Principles text) and "has-nav" layout wrappers.
_DROP_CLASS_RE = re.compile(
    r"^(site-|global-|main-|primary-|top-|mobile-|sub-|mega-)?"
    r"(nav|navbar|navigation|menu|megamenu|footer|header|breadcrumbs?|cookies?|"
    r"cookie-?(banner|bar|notice|consent)|consent|gdpr|skip-?(link|nav|to-content)|"
    r"social|share|sharing|subscribe|newsletter|modal|popup|overlay|search)"
    r"(-?(wrapper|container|inner|bar|links|list|area|region))?$",
    re.I,
)

# Block-level tags: a newline is inserted after each so that inline elements
# (links, <span>, <b>) stay on the same line as the sentence they belong to.
_BLOCK_TAGS = ["p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr",
               "section", "article", "blockquote", "dd", "dt", "td", "th", "ul", "ol"]


# Whole lines that are UI chrome rather than content (seen in pilot output).
_UI_LINE_RE = re.compile(
    r"^(search|menu|close|skip to (main )?content|back to top|learn more|read more|"
    r"please update your browser\.?|selected item|share|print|toggle navigation|loading\.*)$",
    re.I,
)


# Short call-to-action link lines ("Learn about our commitment", "Explore
# innovation stories"). Only removed when short, so real sentences that happen
# to start with "See" or "Learn" survive.
_CTA_LINE_RE = re.compile(
    r"^(learn|read|explore|discover|see|view|check out|find out|watch|download|visit)\b", re.I)
_CTA_MAX_WORDS = 8


def _clean_whitespace(text: str) -> str:
    """Normalize whitespace, keep paragraph breaks, drop exact duplicate lines
    and known UI-chrome lines.

    Duplicate lines are removed because responsive layouts often render the same
    heading or teaser twice (desktop + mobile variants).
    """
    lines, seen = [], set()
    for raw in text.splitlines():
        line = re.sub(r"[ \t ]+", " ", raw).strip()
        if not line or line in seen or _UI_LINE_RE.match(line):
            continue
        if _CTA_LINE_RE.match(line) and len(line.split()) <= _CTA_MAX_WORDS:
            continue
        seen.add(line)
        lines.append(line)
    return "\n".join(lines)


def word_count(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


def _extract_pdf(content: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _extract_bs4(html: bytes) -> str:
    soup = BeautifulSoup(html, "lxml")
    # HTML comments (tracking-tag notes, IE conditional blocks) are not visible.
    for node in soup.find_all(string=lambda t: isinstance(t, (Comment, Declaration, Doctype, ProcessingInstruction))):
        node.extract()
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    for tag in soup.find_all(attrs={"role": _DROP_ROLES}):
        tag.decompose()
    body = soup.body or soup
    total = word_count(body.get_text(" ")) or 1
    for tag in body.find_all(True):
        if tag.decomposed:  # already removed with a dropped ancestor
            continue
        attrs = tag.attrs or {}
        tokens = list(attrs.get("class", []) or []) + [attrs.get("id") or ""]
        if not any(_DROP_CLASS_RE.match(t) for t in tokens if t):
            continue
        # Safety guard: class names are noisy ("has-nav", "page-header-wrapper").
        # Never let a class/id match remove most of the page; such an element is
        # a layout wrapper, not chrome.
        if word_count(tag.get_text(" ")) > 0.5 * total:
            continue
        tag.decompose()
    # Link-density filter: menus built from <ul>/<ol> outside a <nav> element
    # (mega-menus, site maps in footers) are lists whose text is almost entirely
    # anchor text. Real content lists (e.g. a list of values) are not.
    for lst in body.find_all(["ul", "ol"]):
        if lst.decomposed:
            continue
        n = word_count(lst.get_text(" "))
        linked = sum(word_count(a.get_text(" ")) for a in lst.find_all("a"))
        if n and linked / n > 0.6:
            lst.decompose()
    # Source-code line breaks inside a paragraph are not visible breaks: flatten
    # them first, then mark real block boundaries with "\n".
    for node in body.find_all(string=True):
        if "\n" in node or "\t" in node:
            node.replace_with(re.sub(r"\s+", " ", str(node)))
    for tag in body.find_all(_BLOCK_TAGS):
        tag.append("\n")
    return body.get_text("")


def page_title(content: bytes) -> str:
    """Return the HTML <title> (used for soft-404 checks); empty for non-HTML."""
    try:
        soup = BeautifulSoup(content[:200_000], "lxml")
        return (soup.title.get_text(" ", strip=True) if soup.title else "")[:300]
    except Exception:
        return ""


def extract_text(content: bytes, content_type: str = "") -> Tuple[str, str]:
    """Return (clean_text, method) for one archived page."""
    if content[:5] == b"%PDF-" or "pdf" in content_type.lower():
        try:
            return _clean_whitespace(_extract_pdf(content)), "pypdf"
        except Exception:
            return "", "pypdf_failed"

    traf = trafilatura.extract(
        content,
        include_comments=False,
        include_tables=True,
        favor_recall=True,     # About pages are short; prefer keeping text
        # deduplicate=False: trafilatura's dedup uses a process-wide cache, which
        # would delete text repeated across years and make output order-dependent.
        deduplicate=False,
    ) or ""
    traf = _clean_whitespace(traf)
    structural = _clean_whitespace(_extract_bs4(content))
    n_traf, n_struct = word_count(traf), word_count(structural)

    # Selection rule. trafilatura is the default: it is the stronger boilerplate
    # remover. But it is tuned for articles and can keep only the lead paragraph
    # of card/tile-based About pages, discarding values statements in the cards
    # (pilot: ExxonMobil 2016-2022 kept 48-144 words; the cards held "Our guiding
    # principles" and "Standards of business conduct"). When the structural pass
    # recovers >= RECALL_RATIO x as much text, or trafilatura is below MIN_WORDS,
    # the structural text is used instead.
    if n_traf < config.MIN_WORDS and n_struct > n_traf:
        return structural, "bs4_fallback_thin"
    if n_struct >= config.EXTRACTION_RECALL_RATIO * max(n_traf, 1):
        return structural, "bs4_fallback_recall"
    return traf, "trafilatura"
