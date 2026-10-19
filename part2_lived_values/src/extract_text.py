"""Convert a raw EDGAR proxy HTML document into clean, analysable text.

Design choices (documented in README):
- Drop non-content markup: <script>, <style>, <head>, and the hidden
  inline-XBRL header (<ix:header>, display:none blocks) that post-2019
  filings carry. Otherwise XBRL facts leak into the text.
- Block elements (p, div, li, headings, rows) become line breaks; inline
  spans are joined with no separator, because EDGAR filer software often
  splits words across <span>s.
- Tables: a table where every row has at most one non-empty cell is a
  layout table (prose wrapped in a table for formatting) and is unwrapped
  into ordinary paragraphs. Every other table is a data table and is
  flattened one row per line ("cell | cell | cell") between [TABLE] and
  [/TABLE] markers. Analysts can then keep tables (comp metrics) or drop
  them (tone/topic models) without re-parsing HTML.
- Remove page furniture: bare page numbers, "Table of Contents" links,
  and running headers/footers (lines whose page number varies but whose
  pattern repeats on many pages).
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from bs4 import BeautifulSoup, NavigableString

TABLE_OPEN, TABLE_CLOSE = "[TABLE]", "[/TABLE]"

BLOCK_TAGS = ["p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
              "section", "article", "blockquote", "pre", "hr", "center", "dl", "dt", "dd"]

# Lines that are pure page furniture.
FURNITURE_RE = re.compile(
    r"^(page\s*)?([ivxlc]+|\d{1,3}|[a-z]-\d{1,3})$"   # page numbers: 12, iv, A-3
    r"|^(back to |return to )?(table of )?contents$"
    r"|^return to top$",
    re.I,
)

# Running headers/footers ("2024 PROXY STATEMENT | 11 | JPMORGAN CHASE & CO.")
# are recognised by a page number that changes from page to page: after
# replacing digits with '#', the same line pattern recurs in several distinct
# variants. Numbered content also recurs ("Age: 63 | Director since: 2015",
# "Board response to proposal 5"), so a pattern is treated as furniture only
# if (a) it names the document ("proxy statement") and recurs >= 5 times in
# >= 3 variants, or (b) it is page-frequent: >= 20 times in >= 10 variants.
# Erring this way leaves some footer noise in rather than deleting content.
RUNNING_TITLE_RE = re.compile(r"proxy statement", re.I)
RUNNING_TITLE_MIN = (5, 3)       # (occurrences, distinct variants)
RUNNING_GENERIC_MIN = (20, 10)
RUNNING_MAX_CHARS = 120

QUOTE_MAP = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def _row_cells(tr) -> list:
    cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False)]
    return [re.sub(r"\s+", " ", c) for c in cells if c and c.strip()]


def _join_cells(cells: list) -> str:
    """Join cells, re-attaching currency/percent fragments EDGAR splits off."""
    s = " | ".join(cells)
    s = re.sub(r"\$ \| ", "$", s)          # "$ | 1,234" -> "$1,234"
    s = re.sub(r" \| (%|\))", r"\1", s)    # "12 | %" -> "12%"
    s = re.sub(r"\( \| ", "(", s)
    return s


def _flatten_tables(soup) -> tuple:
    """Replace each <table> by plain text. Innermost tables are handled first."""
    n_data = n_layout = 0
    for table in reversed(soup.find_all("table")):
        rows = [_row_cells(tr) for tr in table.find_all("tr")]
        rows = [r for r in rows if r]
        if not rows:
            table.decompose()
            continue
        if max(len(r) for r in rows) <= 1:
            # Layout table: keep its contents as ordinary paragraphs.
            n_layout += 1
            text = "\n" + "\n".join(r[0] for r in rows) + "\n"
        else:
            n_data += 1
            body = "\n".join(_join_cells(r) for r in rows)
            text = f"\n{TABLE_OPEN}\n{body}\n{TABLE_CLOSE}\n"
        table.replace_with(NavigableString(text))
    return n_data, n_layout


def _strip_hidden(soup) -> None:
    for tag in soup(["script", "style", "head", "title", "noscript"]):
        tag.decompose()
    # Inline XBRL header block (contexts, units, hidden facts).
    for tag in soup.find_all(lambda t: t.name and t.name.lower() in ("ix:header", "xbrli:xbrl")):
        tag.decompose()
    for tag in soup.find_all(style=re.compile(r"display\s*:\s*none", re.I)):
        tag.decompose()


def html_to_text(raw: bytes) -> tuple:
    """Return (clean_text, stats dict)."""
    soup = BeautifulSoup(raw, "lxml")
    _strip_hidden(soup)
    n_data, n_layout = _flatten_tables(soup)

    for br in soup.find_all("br"):
        br.replace_with(NavigableString("\n"))
    for tag in soup.find_all(BLOCK_TAGS):
        tag.insert_before(NavigableString("\n"))
        tag.insert_after(NavigableString("\n"))

    text = soup.get_text()
    return clean_text(text, n_data_tables=n_data, n_layout_tables=n_layout)


def plain_to_text(raw: bytes) -> tuple:
    """Fallback for legacy .txt primary documents: strip SGML-ish tags."""
    text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"<[^>]+>", " ", text)
    return clean_text(text)


def _digit_pattern(line: str) -> str:
    return re.sub(r"\d+", "#", line.lower())


def _running_patterns(blocks: list) -> set:
    """Digit-normalised patterns that behave like running headers/footers."""
    counts, variants = Counter(), {}
    for kind, lines in blocks:
        if kind == "table" and len(lines) != 1:
            continue  # only one-row tables can be page furniture
        for ln in lines:
            if len(ln) <= RUNNING_MAX_CHARS and re.search(r"\d", ln):
                pat = _digit_pattern(ln)
                counts[pat] += 1
                variants.setdefault(pat, set()).add(ln)
    def is_running(p: str) -> bool:
        n, v = counts[p], len(variants[p])
        if RUNNING_TITLE_RE.search(p) and n >= RUNNING_TITLE_MIN[0] and v >= RUNNING_TITLE_MIN[1]:
            return True
        return n >= RUNNING_GENERIC_MIN[0] and v >= RUNNING_GENERIC_MIN[1]
    return {p for p in counts if is_running(p)}


def clean_text(text: str, **extra_stats) -> tuple:
    text = unicodedata.normalize("NFKC", text).translate(QUOTE_MAP)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", ln).strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]

    # Group into prose and table blocks so table rows are never mistaken
    # for prose furniture.
    blocks, cur = [], None
    for ln in lines:
        if ln == TABLE_OPEN:
            cur = ("table", [])
        elif ln == TABLE_CLOSE:
            if cur is not None:
                blocks.append(cur)
            cur = None
        elif cur is not None:
            cur[1].append(ln)
        else:
            blocks.append(("prose", [ln]))
    if cur is not None:  # unbalanced marker: keep what we have
        blocks.append(cur)

    running = _running_patterns(blocks)
    out_lines, n_furniture, n_running = [], 0, 0
    prose_words = table_words = 0
    for kind, blines in blocks:
        if kind == "prose":
            ln = blines[0]
            if FURNITURE_RE.match(ln):
                n_furniture += 1
            elif _digit_pattern(ln) in running:
                n_running += 1
            else:
                out_lines.append(ln)
                prose_words += len(ln.split())
        else:
            if len(blines) == 1 and _digit_pattern(blines[0]) in running:
                n_running += 1
                continue
            out_lines.append(TABLE_OPEN)
            out_lines.extend(blines)
            out_lines.append(TABLE_CLOSE)
            table_words += sum(len(ln.split()) for ln in blines)

    out = "\n".join(out_lines)
    stats = {
        "text_chars": len(out),
        "prose_words": prose_words,
        "table_words": table_words,
        "lines_dropped_furniture": n_furniture,
        "lines_dropped_running": n_running,
        "running_patterns": " || ".join(sorted(running)[:5]),
    }
    stats.update(extra_stats)
    return out + "\n", stats


def classify_meeting(text: str, head_chars: int = 20_000) -> str:
    """Label a proxy 'annual', 'special' or 'unknown' from its opening pages.

    Used only when a firm has more than one DEF 14A in a filing year.
    """
    head = text[:head_chars].lower()
    annual = len(re.findall(r"annual (general )?meeting", head))
    special = len(re.findall(r"special (general )?meeting", head))
    if annual == special == 0:
        return "unknown"
    return "annual" if annual >= special else "special"
