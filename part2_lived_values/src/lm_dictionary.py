"""Loughran-McDonald (LM) sentiment word lists.

LM (2011, Journal of Finance) built finance-specific word lists because
general-purpose sentiment dictionaries misclassify words like "liability"
or "tax" in financial filings. We use the 1993-2025 Master Dictionary.
It is downloaded on first use (free for academic use, not redistributed
here) and verified against a pinned checksum.

Proxy-specific adjustment: several LM negatives are procedural in a proxy
statement, not tone. "The Board recommends a vote AGAINST", "statement in
OPPOSITION", "DISSIDENT nominees", "TERMINATION of employment" in severance
tables, "FORFEITURE"/"CLAWBACK" of awards. Their frequency follows the
number of shareholder proposals and the length of the compensation tables,
not the tone of the writing. We report both the standard LM negative count
(comparable with the literature) and an adjusted count without the words in
PROXY_PROCEDURAL_NEGATIVES.
"""
from __future__ import annotations

import csv
import hashlib
import urllib.request

import config

LM_CATEGORIES = ["Negative", "Positive", "Uncertainty", "Litigious", "Constraining"]

PROXY_PROCEDURAL_NEGATIVES = {
    "AGAINST",                                   # "vote AGAINST this proposal"
    "OPPOSE", "OPPOSES", "OPPOSED", "OPPOSING", "OPPOSITION",   # board statements in opposition
    "DISSIDENT", "DISSIDENTS",                   # proxy-contest vocabulary
    "TERMINATION", "TERMINATIONS", "TERMINATE", "TERMINATED",   # severance / change-in-control tables
    "FORFEITURE", "FORFEITURES", "FORFEIT", "FORFEITED", "FORFEITS",  # award vesting terms
    "CLAWBACK", "CLAWBACKS",                     # recoupment policy (integrity, not negativity)
}


def _download() -> None:
    config.LM_PATH.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(config.LM_URL, headers={"User-Agent": config.USER_AGENT})
    data = urllib.request.urlopen(req, timeout=120).read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != config.LM_SHA256:
        raise RuntimeError(f"LM dictionary checksum mismatch ({digest}); the source file changed. "
                           "Inspect it, then update LM_SHA256 in config.py deliberately.")
    config.LM_PATH.write_bytes(data)


def load_lm() -> dict:
    """{category: set of UPPERCASE words}. A non-zero cell (the year added) means membership."""
    if not config.LM_PATH.exists():
        _download()
    sets = {c: set() for c in LM_CATEGORIES}
    with open(config.LM_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for c in LM_CATEGORIES:
                if row[c] not in ("0", ""):
                    sets[c].add(row["Word"].upper())
    sets["Negative_adj"] = sets["Negative"] - PROXY_PROCEDURAL_NEGATIVES
    return sets
