"""Locate the sections of a proxy statement that the LLM layer reads.

Two targets:
- CD&A (Compensation Discussion and Analysis): where firms explain which
  metrics executive pay is tied to.
- Shareholder proposals: each proposal, its supporting statement, and
  the board's response.

Proxy text has no reliable heading markup. Section names recur in the
table of contents, the summary, cross-references and glossaries, and some
filings render whole pages as single lines (XOM 2023). So we generate every
candidate span from a heading-like start to the next end marker and pick
the best one:
- CD&A: the longest valid span (the real CD&A is by far the longest
  passage under that name).
- Proposals: the span densest in proposal language ("proponent",
  "supporting statement", "RESOLVED"). The longest span would be wrong
  here, because a summary-page mention can run on to an unrelated section.
Start and end phrases must appear within the first 60 characters of a
line. That catches both real headings and page-as-line renderings, but not
mid-sentence cross-references.
"""
from __future__ import annotations

import re
from typing import Optional

from extract_text import TABLE_CLOSE, TABLE_OPEN

HEAD_CHARS = 60

TOC_LINE = re.compile(r"(\|\s*\d{1,3}\s*$)|(\s\d{1,3}\s*$)")       # "... | 45" or "... 45"
CROSS_REF = re.compile(r"refer to|see (the|our|page)|beginning on page|described (in|under)", re.I)

CDA_START = re.compile(r"compensation discussion (and|&) analysis|\bcd&a\b", re.I)
CDA_END = re.compile(
    r"summary compensation table|compensation committee report|executive compensation tables"
    r"|(shareholder|stockholder) proposals?|^\W*(item|proposal) (no\. ?)?\d+\b|audit committee report"
    r"|pay (versus|vs\.?) performance|security ownership|director compensation", re.I)
CDA_MIN_WORDS, CDA_MAX_WORDS = 2_000, 40_000
# Second pass for very short CD&As (Berkshire ~1k words). Not the default: the
# minimum also stops a section from ending at one of its own sub-headings.
CDA_MIN_WORDS_SHORT = 800

SP_START = re.compile(r"(shareholder|stockholder) proposals?", re.I)
SP_NOT_START = re.compile(r"for next year|for (the )?20\d\d|nominations|deadline|submit|to be presented at", re.I)
SP_END = re.compile(
    r"information about the (annual )?(shareholder |stockholder )?meeting|general information"
    r"|important (annual )?meeting information|annual meeting information|other matters"
    r"|frequently asked questions|questions and answers|voting (information|procedures)"
    r"|(shareholder|stockholder) proposals? (and director nominations )?(for|at) (next year|the 20\d\d)"
    r"|(shareholder|stockholder) proposals and (director )?nominations"
    r"|compensation discussion|summary compensation table|security ownership|audit committee", re.I)
SP_SIGNAL = re.compile(r"\bproponents?\b|supporting statement|\bresolved\b|has (advised|notified) (us|the company)", re.I)
SP_MIN_WORDS, SP_MAX_WORDS = 300, 30_000
RESOLVED_RE = re.compile(r"\bresolved\b", re.I)
# Window anchors: the RESOLVED clause, or the statement headings used by firms
# that paraphrase proposals instead of quoting them (BAC 2018, BMY 2021-22).
ANCHOR_RE = re.compile(r"\bresolved\b|supporting statement|proponent'?s'? statement|statement (of|by) (the )?proponent"
                       r"|the proponents?'?s? (concern|request|proposal)", re.I)
MGMT_RESOLUTION = re.compile(
    r"approve[sd]?,? (on an )?(a non-binding,? )?advisory basis|compensation (paid to|of) (the|our) "
    r"(company's |corporation's )?named executive|ratif(y|ies|ied|ication)|"
    r"(amend(ed|ment)?|restate(d|ment)?) .{0,60}(certificate of incorporation|articles of|charter|by-?laws)|"
    r"(stock|equity|incentive|purchase) plan", re.I)
RES_BEFORE, RES_AFTER = 300, 2_000
CHAIN_GAP = 5   # lines


def _lines_and_offsets(text: str):
    lines = text.split("\n")
    offsets, wc = [], 0
    for ln in lines:
        offsets.append(wc)
        wc += len(ln.split())
    return lines, offsets, wc


def _is_heading_hit(line: str, pattern, allow_glued: bool = False) -> bool:
    """Does `pattern` occur where a heading would be on this line?

    Short lines (<= 60 chars) are headings. On longer lines (a heading run
    into its paragraph, or a whole page rendered as one line) the phrase
    counts only if it is set in capitals and preceded only by capitals
    ("EXECUTIVE COMPENSATION COMPENSATION DISCUSSION AND ANALYSIS ...").
    Mixed-case long lines are sentences ('"Summary Compensation Table"
    ("SCT") on page 51 ...'). Lines starting in lower case are sentence
    continuations, never headings.
    """
    m = pattern.search(line)
    if not m or m.start() >= HEAD_CHARS:
        return False
    if line[:1].islower():
        # A short line that is (almost) only the phrase is a heading rendered in
        # lower case by CSS (CVX: "compensation discussion and analysis").
        return len(line) <= 60 and len(m.group(0)) >= 0.7 * len(line.strip())
    if CROSS_REF.search(line[:HEAD_CHARS + 40]):
        return False
    if len(line) <= 60:
        return True
    # Mid-length line that opens with the phrase and does not end like a
    # sentence: a long heading ("Shareholder Proposal 1: Report on Employee
    # Representation on Board of Directors").
    if len(line) <= 120 and m.start() <= 3 and not line.rstrip().endswith((".", ",", ";")):
        return True
    # A heading glued to its paragraph: the line opens with the phrase in title
    # case ("Compensation Discussion and Analysis This section provides ...", ORCL).
    hit = m.group(0)
    # Start markers only: an end phrase opening a paragraph is usually a sentence
    # inside the section ("Summary Compensation Table amounts reflect ...").
    if allow_glued and m.start() == 0 and all(w[:1].isupper() for w in hit.split()
                                               if w.lower() not in ("and", "&", "of", "the")):
        return True
    # Other long lines are sentences unless the heading is set in capitals.
    prefix = line[:m.start()]
    return hit == hit.upper() and prefix == prefix.upper()


def _candidate_spans(lines, offsets, total, start_re, end_re, not_start=None,
                     min_words=0, max_words=10**9):
    """All (start_idx, end_idx, n_words) spans from a start hit to the next end hit."""
    starts = [i for i, ln in enumerate(lines)
              if _is_heading_hit(ln, start_re, allow_glued=True) and not (len(ln) <= 120 and TOC_LINE.search(ln))
              and not (not_start and not_start.search(ln))]
    ends = [i for i, ln in enumerate(lines) if _is_heading_hit(ln, end_re)]
    spans = []
    for s in starts:
        # First end marker far enough away that it isn't the section's own sub-heading.
        e = next((e for e in ends if e > s and offsets[e] - offsets[s] >= min_words), None)
        if e is None:
            continue
        n = offsets[e] - offsets[s]
        if min_words <= n <= max_words:
            spans.append((s, e, n))
    return spans


# Fallback when the CD&A heading is an image (MSFT 2018): the section's
# standard opening sentence, ending at the Compensation Committee Report,
# whose wording is close to boilerplate under Reg S-K Item 407(e)(5).
CDA_OPENING = re.compile(r"^(in )?(this|the|our) compensation discussion (and|&) analysis\b.{0,40}"
                         r"\b(provides?|describes?|explains?|discuss(es)?|summari[sz]es?|sets? forth|presents?|reviews?)", re.I)
CDA_REPORT = re.compile(r"has reviewed and discussed.{0,60}compensation discussion (and|&) analysis", re.I)


def _cda_fallback(lines, offsets):
    start = next((i for i, ln in enumerate(lines) if CDA_OPENING.search(ln)), None)
    if start is None:
        return []
    end = next((i for i in range(start + 1, len(lines))
                if offsets[i] - offsets[start] >= CDA_MIN_WORDS
                and (CDA_REPORT.search(lines[i]) or _is_heading_hit(lines[i], CDA_END))), None)
    if end is None or offsets[end] - offsets[start] > CDA_MAX_WORDS:
        return []
    return [(start, end, offsets[end] - offsets[start])]


def find_cda(text: str, target_words: Optional[float] = None) -> Optional[dict]:
    """Best CD&A span. With target_words (the firm's median CD&A length over its
    other years), a best span outside 0.5x-1.8x of it is replaced by the
    candidate closest to it: a firm's CD&A length is stable across years, so a
    much shorter span is usually truncated at an internal sub-heading and a
    much longer one has run past the section."""
    # Rejoin a heading split over two lines ("Compensation Discussion and" / "Analysis", HAL).
    text = re.sub(r"(?im)^(\W*compensation discussion (and|&))[ \t]*\n[ \t]*(analysis\b)", r"\1 \3", text)
    lines, offsets, total = _lines_and_offsets(text)
    spans = _candidate_spans(lines, offsets, total, CDA_START, CDA_END,
                             min_words=CDA_MIN_WORDS, max_words=CDA_MAX_WORDS)
    method = "heading"
    if not spans:
        spans = _candidate_spans(lines, offsets, total, CDA_START, CDA_END,
                                 min_words=CDA_MIN_WORDS_SHORT, max_words=CDA_MAX_WORDS)
        method = "heading_short"
    if not spans:
        spans, method = _cda_fallback(lines, offsets), "opening_sentence"
    if not spans:
        return None
    s, e, n = max(spans, key=lambda x: x[2])
    if target_words and not (0.5 * target_words <= n <= 1.8 * target_words):
        import math
        alt = min(spans, key=lambda x: abs(math.log(x[2] / target_words)))
        if abs(math.log(alt[2] / target_words)) < abs(math.log(n / target_words)):
            (s, e, n), method = alt, method + "+median_adjusted"
    return {"method": method, "start_line": s, "end_line": e, "words": n,
            "start_word_frac": round(offsets[s] / max(total, 1), 3),
            "end_marker": lines[e][:80], "text": "\n".join(lines[s:e])}


def find_proposals(text: str) -> Optional[dict]:
    lines, offsets, total = _lines_and_offsets(text)
    spans = _candidate_spans(lines, offsets, total, SP_START, SP_END, not_start=SP_NOT_START,
                             min_words=SP_MIN_WORDS, max_words=SP_MAX_WORDS)
    # Chain spans that follow each other (next start within CHAIN_GAP lines of
    # the previous end): one proposal per span is common when sub-headings
    # inside a board response look like end markers.
    chains = []
    for s, e, n in sorted(spans):
        if chains and chains[-1][0] <= s <= chains[-1][1] + CHAIN_GAP:
            chains[-1][1] = max(chains[-1][1], e)
        elif not (chains and s < chains[-1][1]):   # skip spans nested in the previous chain
            chains.append([s, e])
    scored = []
    for s, e in chains:
        n = offsets[e] - offsets[s]
        if n > SP_MAX_WORDS:
            continue
        signal = len(SP_SIGNAL.findall("\n".join(lines[s:e])))
        scored.append((signal, -n, s, e, n))
    scored = [x for x in scored if x[0] > 0]
    intervals, method, end_marker = [], [], ""
    if scored:
        _, _, s, e, _ = max(scored)   # most proposal language; ties -> shorter span
        intervals.append((s, e)); method.append("heading"); end_marker = lines[e][:80]

    # Anchor windows. Rule 14a-8 proposals reproduce the proponent's RESOLVED
    # clause, so every non-management RESOLVED gets a window: RES_BEFORE words
    # back (title, proponent) to RES_AFTER words on (supporting statement and
    # board response), stopping early at a meeting-information heading. This
    # catches proposals that heading rules miss in unusual layouts. Management
    # resolutions (say-on-pay, auditor, plans, charter) are skipped so their
    # surrounding firm text stays in the firm-voice measure.
    windows = []
    for i, ln in enumerate(lines):
        for m in ANCHOR_RE.finditer(ln):
            if MGMT_RESOLUTION.search(ln[m.start():m.start() + 300]):
                continue
            a = i
            while a > 0 and offsets[i] - offsets[a] < RES_BEFORE:
                a -= 1
            b = i + 1
            while b < len(lines) and offsets[b] - offsets[i] < RES_AFTER and not _is_heading_hit(lines[b], SP_END):
                b += 1
            windows.append((a, b))
            break
    if windows:
        method.append("resolved_windows")
    merged = []
    for a, b in sorted(intervals + windows):
        if merged and a <= merged[-1][1] + CHAIN_GAP:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    if not merged:
        return None
    text_out = "\n[...]\n".join("\n".join(lines[a:b]) for a, b in merged)
    n = sum(offsets[b - 1] - offsets[a] + len(lines[b - 1].split()) for a, b in merged)
    return {"method": "+".join(method), "intervals": merged, "words": n,
            "signal_hits": len(SP_SIGNAL.findall(text_out)),
            "start_line": merged[0][0], "end_line": merged[-1][1],
            "start_word_frac": round(offsets[merged[0][0]] / max(total, 1), 3),
            "end_marker": end_marker, "text": text_out}


def prose_only(text: str) -> str:
    """Drop [TABLE]...[/TABLE] blocks (used for dictionary and tone measures)."""
    return re.sub(rf"{re.escape(TABLE_OPEN)}\n.*?\n{re.escape(TABLE_CLOSE)}\n?", "", text, flags=re.S)


def cda_targets(rows) -> dict:
    """{(ticker, year): median CD&A length of the firm's OTHER years} (first pass).
    rows: iterable of (ticker, year, text)."""
    import statistics
    lengths = {}
    for t, y, text in rows:
        c = find_cda(text)
        if c:
            lengths.setdefault(t, {})[y] = c["words"]
    out = {}
    for t, by_year in lengths.items():
        for y in by_year:
            others = [w for yy, w in by_year.items() if yy != y]
            if len(others) >= 3:
                out[(t, y)] = statistics.median(others)
    return out
