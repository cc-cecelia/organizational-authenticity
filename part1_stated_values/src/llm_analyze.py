"""
Part 1 LLM step: theme coding, change detection and analyst notes for every
collected About/values snapshot.

Usage (from repo root):
    .venv/bin/python part1_stated_values/src/llm_analyze.py --pilot --dry-run   # sizes + cost, no API calls
    .venv/bin/python part1_stated_values/src/llm_analyze.py --pilot             # 10-snapshot pilot + hand-check sheet
    .venv/bin/python part1_stated_values/src/llm_analyze.py                     # all collected snapshots

Two tasks:
  themes   One call per snapshot. For each of the 9 shared taxonomy categories
           (part2_lived_values/README.md, "Shared stakeholder taxonomy", imported from Part 2's
           theme_dictionary so both parts code against identical definitions
           and tie-break rules): salience 0-3 and the single strongest
           verbatim evidence span. Plus analyst_notes on tone and framing.
  change   Only when (a) the prior collected year exists, (b) it is the same
           logical page (page_group) with the same page_type, and (c) the
           word-sequence similarity is below SIMILARITY_THRESHOLD. The LLM
           reads a line diff, not both full pages, and says whether the change
           is substantive (values content) or cosmetic.

Every evidence span is checked against the page text; spans not found verbatim
are listed in `evidence_unverified` (salience is kept, the flag lets Part 3
drop or down-weight them).

Model, effort, schema-constrained JSON, fingerprint cache and the rolling
token budget follow Part 2's llm_extract.py.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

# Shared taxonomy: read-only import from Part 2 (single source of truth).
sys.path.insert(0, str(config.REPO_ROOT / "part2_lived_values" / "src"))
from theme_dictionary import CATEGORIES, CATEGORY_DEFINITIONS, CODING_RULES  # noqa: E402

# --------------------------------------------------------------------------- #
# Token budget (same pattern and limits as Part 2's llm_extract.py)
# --------------------------------------------------------------------------- #
# Account limits: 500k input and 80k output tokens per minute. Output limits
# are charged against max_tokens up front, so max_tokens is sized per task.
MAX_TOKENS = {"themes": 4_000, "change": 1_500}
BUDGET_IN, BUDGET_OUT = 400_000, 64_000          # 80% of the per-minute limits
PRICE_IN, PRICE_OUT = 0.10, 0.50                 # Haiku 5.5, USD per million tokens


class RateBudget:
    """Rolling 60-second token budget shared by all worker threads."""

    def __init__(self):
        self.lock = threading.Lock()
        self.events = []   # [timestamp, input_tokens, output_tokens]

    def reserve(self, tin: int, tout: int, label: str) -> list:
        waited = 0.0
        while True:
            with self.lock:
                now = time.monotonic()
                self.events = [e for e in self.events if now - e[0] < 60]
                used_in = sum(e[1] for e in self.events)
                used_out = sum(e[2] for e in self.events)
                if used_in + tin <= BUDGET_IN and used_out + tout <= BUDGET_OUT or not self.events:
                    ev = [now, tin, tout]
                    self.events.append(ev)
                    if waited:
                        print(f"  waited {waited:.0f}s for token budget: {label}", flush=True)
                    return ev
            time.sleep(2)
            waited += 2

    def settle(self, ev: list, tin: int, tout: int) -> None:
        with self.lock:
            ev[1], ev[2] = tin, tout


BUDGET = RateBudget()

# --------------------------------------------------------------------------- #
# Prompts and schemas
# --------------------------------------------------------------------------- #
PART1_RULES = [
    "Code what the page says the company values, commits to, or prioritizes. Business description is NOT a "
    "value: what the company sells, its size, locations, history, rankings or facts ('the world's largest "
    "refiner', '30,000 employees', 'products in 175 countries') are not coded unless the sentence states a "
    "commitment or priority ('we are committed to...', 'we put patients first', 'our mission is...').",
    "Ignore residual website chrome: menu items, link labels, news or article teasers, cookie and legal text.",
    "A list of products or business lines is not innovation; innovation needs a stated commitment to "
    "innovating, R&D, or invention.",
    # Added after the pilot hand check (p1v2): these were coded as values in p1v1.
    "Calls to action and site features are chrome, never values: shopping, store-locator or contact prompts "
    "('Visit an Apple Store', 'call 1-800-...'), recruiting prompts ('Want to work at X?'), 'Learn more' links.",
    "Claims about scale, reach, headcount, market position or economic impact ('transforming 100 trillion "
    "dollars of industries', 'about 377,000 employees') are business description: code 0 for them unless the "
    "same sentence states a commitment.",
    "Statements that the firm's capital, products or work should benefit society are community, not "
    "shareholders.",
    "Cite a span only for a category it actually addresses; do not reuse one span for several categories "
    "unless it states a commitment to each.",
]

SALIENCE_SCALE = (
    "Salience scale, per category:\n"
    "0 = absent.\n"
    "1 = passing mention: one phrase or list item, not developed.\n"
    "2 = clear stated value or commitment with some elaboration (a sentence or short paragraph).\n"
    "3 = central: a headline or named core value, or a dominant theme the page returns to repeatedly."
)

SYSTEM = (
    "You code corporate About-us and values web pages for an academic study of stated corporate values.\n\n"
    "Stakeholder categories (stakeholder theory, Freeman 1984):\n"
    + "\n".join(f"- {k}: {v}" for k, v in CATEGORY_DEFINITIONS.items())
    + "\n\nCoding rules for ambiguous cases:\n"
    + "\n".join(f"- {r}" for r in CODING_RULES + PART1_RULES)
    + "\n\n" + SALIENCE_SCALE + "\n\n"
    "Text can belong to several categories. Evidence must be one contiguous span copied character for "
    "character from the page, at most 25 words: never omit, add or change words (not even a name). If a "
    "sentence is too long, copy a shorter contiguous part of it instead of paraphrasing. Pick the span that "
    "best supports the salience; use an empty string when salience is 0."
)

THEMES_TASK = """Below is the visible text of {company}'s {page_kind} as archived in {year}.

For each of the 9 categories, give salience (0-3) and one verbatim evidence span.
Then write analyst_notes: at most 60 words on tone and framing, for example aspirational vs. factual, which stakeholders the page addresses first, first-person voice, hedged vs. absolute commitments, and any distinctive wording. Describe only what is on this page.

<page>
{text}
</page>"""

CHANGE_TASK = """{company}'s {page_kind} changed between {prior_year} and {year}. Below is a line diff of the visible text ("-" = removed in {year}, "+" = added in {year}).

Classify the change:
- substantive: the page's own standing statements change. Its mission, purpose, vision, values, principles or stated commitments are added, removed or reworded in meaning, or the emphasis among them clearly shifts.
- cosmetic: everything else. Layout, reordering without a shift in emphasis, typos, updated facts or figures, navigation or legal text, and rotating featured content (news, stories, article teasers, report, event or award promos, featured initiatives) even when that content mentions a value topic.
Then summarize what changed in at most 40 words, quoting key added or removed words where useful.

<diff>
{diff}
</diff>"""

SALIENCE = {"type": "integer", "enum": [0, 1, 2, 3]}  # min/max unsupported in structured outputs

THEMES_SCHEMA = {
    "type": "object",
    "properties": {
        "themes": {
            "type": "object",
            "properties": {c: {"type": "object",
                               "properties": {"salience": SALIENCE, "evidence": {"type": "string"}},
                               "required": ["salience", "evidence"],
                               "additionalProperties": False}
                           for c in CATEGORIES},
            "required": CATEGORIES,
            "additionalProperties": False,
        },
        "analyst_notes": {"type": "string"},
    },
    "required": ["themes", "analyst_notes"],
    "additionalProperties": False,
}

CHANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "classification": {"type": "string", "enum": ["substantive", "cosmetic"]},
        "summary": {"type": "string"},
    },
    "required": ["classification", "summary"],
    "additionalProperties": False,
}

# Pilot: 10 snapshots across both page types and the extraction edge cases
# (PDF, card layout, long page, near-empty contact page, teaser-heavy page).
PILOT = [("MSFT", 2020), ("JPM", 2022), ("BRK.B", 2020), ("JNJ", 2021), ("CVX", 2024),   # values pages
         ("XOM", 2018), ("AAPL", 2016), ("MS", 2024), ("BAC", 2021), ("NVDA", 2022)]     # about pages


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def page_kind(page_type: str) -> str:
    return "values/mission page" if page_type == "values" else "About page"


def similarity(a: str, b: str) -> float:
    """Word-sequence similarity in [0, 1] (difflib ratio over word tokens)."""
    return difflib.SequenceMatcher(None, a.split(), b.split(), autojunk=False).ratio()


def line_diff(a: str, b: str) -> str:
    """Changed lines only (no context): smaller prompt, and context lines add nothing here."""
    out = [l for l in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0)
           if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    return "\n".join(out)


_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                         "–": "-", "—": "-", " ": " "})


def _norm(s: str) -> str:
    # Rejoin words hyphenated across a line break (PDF text: "owner-\npartners").
    s = re.sub(r"-\s*\n\s*", "-", s.translate(_QUOTES))
    return re.sub(r"\s+", " ", s).strip().lower()


def evidence_found(evidence: str, text: str) -> bool:
    """True if the span appears in the page text (whitespace, quotes, case normalized).

    Spans that bridge two lines of the extracted text are matched after
    joining lines, and a trailing ellipsis the model may add is ignored.
    """
    ev = _norm(evidence).rstrip(". …").strip()
    return bool(ev) and ev in _norm(text)


def cache_key(task: str, prompt: str, schema: dict) -> str:
    # Each task has its own prompt version so one task can be revised and re-run
    # without invalidating (and re-sampling) the other task's cached results.
    version = config.LLM_PROMPT_VERSION if task == "themes" else config.LLM_CHANGE_PROMPT_VERSION
    payload = json.dumps({"model": config.LLM_MODEL, "effort": config.LLM_EFFORT,
                          "prompt_version": version, "task": task,
                          "system": SYSTEM, "prompt": prompt, "schema": schema}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def call_model(client, prompt: str, schema: dict, max_tokens: int, label: str) -> dict:
    """One schema-constrained request. Returns {'result', 'usage'} or {'error'}."""
    import anthropic
    for attempt in range(8):
        ev = BUDGET.reserve(len(prompt) // 4, max_tokens, label)   # ~4 chars/token on web prose
        try:
            resp = client.messages.create(
                model=config.LLM_MODEL,
                max_tokens=max_tokens,
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": config.LLM_EFFORT,
                               "format": {"type": "json_schema", "schema": schema}},
            )
            BUDGET.settle(ev, resp.usage.input_tokens, resp.usage.output_tokens)
            break
        except anthropic.RateLimitError as e:
            if attempt == 7:
                return {"error": f"rate_limited: {e.message}"}
            wait = min(int(e.response.headers.get("retry-after", "20")), 90) + 2 * attempt
            print(f"  429 on {label}, retry {attempt + 1} in {wait}s", flush=True)
            time.sleep(wait)
        except anthropic.BadRequestError as e:          # not retryable
            return {"error": f"bad_request: {e.message}"}
        except anthropic.APIStatusError as e:           # SDK already retried 5xx
            return {"error": f"api_status_{e.status_code}: {e.message}"}
        except anthropic.APIConnectionError as e:
            return {"error": f"connection: {e}"}

    usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens,
             "request_id": resp._request_id}
    if resp.stop_reason == "refusal":
        return {"error": "refusal", "usage": usage}
    if resp.stop_reason == "max_tokens":
        return {"error": "max_tokens: output truncated", "usage": usage}
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        return {"result": json.loads(text), "usage": usage}
    except json.JSONDecodeError as e:
        return {"error": f"invalid_json: {e}", "usage": usage}


def run_cached(client, task: str, prompt: str, label: str, dry_run: bool) -> dict:
    schema = THEMES_SCHEMA if task == "themes" else CHANGE_SCHEMA
    key = cache_key(task, prompt, schema)
    path = config.LLM_CACHE_DIR / task / f"{key}.json"
    base = {"cache_key": key, "est_input_tokens": len(prompt) // 4}
    if path.exists():
        rec = json.loads(path.read_text())
        return dict(base, status="cached", **rec["usage"], result=rec["result"])
    if dry_run:
        return dict(base, status="dry_run")
    out = call_model(client, prompt, schema, MAX_TOKENS[task], label)
    if "error" in out:
        print(f"  ERROR {label}: {out['error']}", flush=True)
        return dict(base, status="error", error=out["error"], **out.get("usage", {}))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"label": label, "model": config.LLM_MODEL,
                                "usage": out["usage"], "result": out["result"]}, indent=1))
    return dict(base, status="ok", **out["usage"], result=out["result"])


# --------------------------------------------------------------------------- #
# Per-row work
# --------------------------------------------------------------------------- #
def plan_change(row: dict, prior: Optional[dict]) -> dict:
    """Decide the change label without the LLM where possible.

    Returns change_type and, when the LLM is needed, the diff to send.
    changed_from_prior is True/False, or None when no comparison is valid.
    """
    if prior is None:
        return {"change_type": "first_observation", "changed_from_prior": None}
    gap = int(row["year"]) - int(prior["year"])
    base = {"compared_to_year": int(prior["year"]), "years_since_prior": gap}
    if row["page_group"] != prior["page_group"] or row["page_type"] != prior["page_type"]:
        # Rule (README, "Which page counts"): a page switch is never counted as a content change.
        return dict(base, change_type="page_switch", changed_from_prior=None)
    if row["text_sha1"] == prior["text_sha1"]:
        return dict(base, change_type="identical", changed_from_prior=False, text_similarity=1.0)
    sim = round(similarity(prior["page_text_clean"], row["page_text_clean"]), 4)
    if sim >= config.SIMILARITY_THRESHOLD:
        return dict(base, change_type="minor_edit", changed_from_prior=False, text_similarity=sim)
    return dict(base, change_type="llm", changed_from_prior=None, text_similarity=sim,
                diff=line_diff(prior["page_text_clean"], row["page_text_clean"]))


def analyze_row(client, row: dict, prior: Optional[dict], dry_run: bool) -> dict:
    label = f"{row['ticker']} {row['year']}"
    out = {"ticker": row["ticker"], "year": int(row["year"])}

    # Themes
    prompt = THEMES_TASK.format(company=row["company_name"], page_kind=page_kind(row["page_type"]),
                                year=row["year"], text=row["page_text_clean"])
    th = run_cached(client, "themes", prompt, f"{label} themes", dry_run)
    out.update(themes_status=th["status"], themes_error=th.get("error", ""),
               themes_in=th.get("input_tokens", th["est_input_tokens"]),
               themes_out=th.get("output_tokens", 0))
    if "result" in th:
        res = th["result"]["themes"]
        sal = {c: int(res[c]["salience"]) for c in CATEGORIES}
        total = sum(sal.values())
        unverified = []
        for c in CATEGORIES:
            ev = res[c]["evidence"].strip()
            out[f"sal_{c}"] = sal[c]
            # Normalized shares: Part 3 compares emphasis, not raw volume.
            out[f"share_{c}"] = round(sal[c] / total, 4) if total else None
            out[f"ev_{c}"] = ev if sal[c] else ""
            if sal[c] and not evidence_found(ev, row["page_text_clean"]):
                unverified.append(c)
        out["salience_total"] = total
        out["theme_categories"] = ";".join(
            c for c in sorted(CATEGORIES, key=lambda c: -sal[c]) if sal[c] >= 1)
        out["evidence_unverified"] = ";".join(unverified)
        out["analyst_notes"] = th["result"]["analyst_notes"].strip()

    # Change from prior year
    plan = plan_change(row, prior)
    diff = plan.pop("diff", None)
    out.update(plan)
    if plan["change_type"] == "llm":
        cprompt = CHANGE_TASK.format(company=row["company_name"], page_kind=page_kind(row["page_type"]),
                                     prior_year=plan["compared_to_year"], year=row["year"], diff=diff)
        ch = run_cached(client, "change", cprompt, f"{label} change", dry_run)
        out.update(change_status=ch["status"], change_in=ch.get("input_tokens", ch["est_input_tokens"]),
                   change_out=ch.get("output_tokens", 0))
        if "result" in ch:
            cls = ch["result"]["classification"]
            out.update(change_type=cls, changed_from_prior=(cls == "substantive"),
                       change_summary=ch["result"]["summary"].strip())
    return out


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def load_snapshots() -> pd.DataFrame:
    s = pd.read_csv(config.OUTPUT_DIR / "snapshots.csv", dtype=str, keep_default_na=False)
    s["year"] = s["year"].astype(int)
    return s


def priors(ok: pd.DataFrame) -> Dict[tuple, Optional[dict]]:
    """Map (ticker, year) -> the firm's previous collected snapshot (any gap)."""
    out = {}
    for _, g in ok.sort_values("year").groupby("ticker"):
        prev = None
        for r in g.to_dict("records"):
            out[(r["ticker"], r["year"])] = prev
            prev = r
    return out


def write_handcheck(rows: List[dict], snaps: pd.DataFrame, path: Path) -> None:
    """One line per (snapshot, category) plus one per change call, with blank verdict columns."""
    if path.exists():
        print(f"hand-check sheet exists, not overwritten: {path}")
        return
    lines = []
    for r in rows:
        meta = snaps[(snaps.ticker == r["ticker"]) & (snaps.year == r["year"])].iloc[0]
        for c in CATEGORIES:
            lines.append({"ticker": r["ticker"], "year": r["year"], "page_type": meta.page_type,
                          "item": c, "llm": r.get(f"sal_{c}"), "evidence": r.get(f"ev_{c}", ""),
                          "evidence_verbatim": c not in r.get("evidence_unverified", "").split(";"),
                          "hc_verdict": "", "hc_notes": ""})
        lines.append({"ticker": r["ticker"], "year": r["year"], "page_type": meta.page_type,
                      "item": "analyst_notes", "llm": "", "evidence": r.get("analyst_notes", ""),
                      "evidence_verbatim": "", "hc_verdict": "", "hc_notes": ""})
        lines.append({"ticker": r["ticker"], "year": r["year"], "page_type": meta.page_type,
                      "item": f"change ({r.get('change_type')}, sim={r.get('text_similarity')})",
                      "llm": r.get("changed_from_prior"), "evidence": r.get("change_summary", ""),
                      "evidence_verbatim": "", "hc_verdict": "", "hc_notes": ""})
    pd.DataFrame(lines).to_csv(path, index=False)
    print(f"hand-check sheet: {len(rows)} snapshots, {len(lines)} items -> {path}")


def build_output(snaps: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    """One row per company-year (missing years included), required columns first."""
    keep = ["ticker", "company_name", "sector", "year", "status", "gap_reason", "page_type", "page_source",
            "page_group", "page_url", "final_url", "snapshot_timestamp", "wayback_url", "extraction_method",
            "word_count", "page_text_clean"]
    out = snaps[keep].merge(results, on=["ticker", "year"], how="left")
    first = ["ticker", "company_name", "sector", "year", "page_text_clean", "changed_from_prior",
             "theme_categories", "analyst_notes"]
    rest = [c for c in out.columns if c not in first]
    return out[first + rest]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pilot", action="store_true", help="run the 10-snapshot pilot only")
    ap.add_argument("--tickers", nargs="*")
    ap.add_argument("--dry-run", action="store_true", help="estimate tokens and cost; no API calls")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)

    snaps = load_snapshots()
    ok = snaps[snaps.status == "ok"].copy()
    prior_of = priors(ok)
    todo = ok
    if args.pilot:
        todo = ok[[(t, y) in set(PILOT) for t, y in zip(ok.ticker, ok.year)]]
    elif args.tickers:
        todo = ok[ok.ticker.isin(args.tickers)]

    client = None
    if not args.dry_run:
        import anthropic
        from dotenv import load_dotenv
        load_dotenv(config.REPO_ROOT / ".env")     # gitignored; ANTHROPIC_API_KEY=...
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            print("No ANTHROPIC_API_KEY set. Export a key, or use --dry-run.", file=sys.stderr)
            return 2
        client = anthropic.Anthropic(max_retries=5)

    rows = todo.to_dict("records")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(
            lambda r: analyze_row(client, r, prior_of[(r["ticker"], r["year"])], args.dry_run), rows))
    res = pd.DataFrame(results)

    # Cost and status summary
    tin = res.get("themes_in", pd.Series(dtype=float)).fillna(0).sum() + res.get("change_in", pd.Series(dtype=float)).fillna(0).sum()
    tout = res.get("themes_out", pd.Series(dtype=float)).fillna(0).sum() + res.get("change_out", pd.Series(dtype=float)).fillna(0).sum()
    print(res["themes_status"].value_counts().to_string())
    print(res["change_type"].value_counts().to_string())
    print(f"input tokens {tin:,.0f}  output tokens {tout:,.0f}  "
          f"cost ~${tin / 1e6 * PRICE_IN + tout / 1e6 * PRICE_OUT:.3f}"
          + (" (output not yet known)" if args.dry_run else ""))
    if args.dry_run:
        return 0

    if args.pilot:
        res.to_csv(config.OUTPUT_DIR / "llm_pilot.csv", index=False)
        write_handcheck(results, snaps,
                        config.OUTPUT_DIR / f"handcheck_sheet_{config.LLM_PROMPT_VERSION}.csv")
        return 0
    out = build_output(snaps, res.drop(columns=[c for c in res.columns if c.endswith(("_in", "_out"))]))
    out.to_csv(config.STATED_VALUES_CSV, index=False)
    print(f"wrote {config.STATED_VALUES_CSV} ({len(out)} rows)")
    errors = res[res["themes_status"] == "error"]
    if len(errors):
        print(errors[["ticker", "year", "themes_error"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
