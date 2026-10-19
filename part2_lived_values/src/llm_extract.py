"""Layer 2: LLM structured extraction from targeted proxy sections.

Usage:
    python part2_lived_values/src/llm_extract.py --tickers MSFT JPM XOM --dry-run   # sizes + cost, no API calls
    python part2_lived_values/src/llm_extract.py --tickers MSFT JPM XOM             # pilot
    python part2_lived_values/src/llm_extract.py --handcheck 10                     # write the hand-check sheet

Two tasks, each reading only the section that contains the answer
(sections.py), never the whole proxy:
  incentives  CD&A -> every metric executive incentive pay is tied to,
              with its weight where stated, mapped to a stakeholder category.
              This is the core "lived values" signal: what the board pays for.
  proposals   Shareholder-proposal section -> each proposal's topic,
              category, and the board's recommendation.

Model: Claude Haiku 5.5 (claude-haiku-5-5), JSON output constrained by a
schema (output_config.format), effort "low". Haiku 5.5 rejects non-default
sampling parameters, so temperature 0 cannot be set. Reproducibility comes
from the cache instead: each request is keyed by a SHA-256 of
(model, prompt version, task, prompts, schema, section text), and the
response is stored in data/llm_cache/. A rerun never re-queries a section
it has already seen, so published results are fixed. Bump
config.LLM_PROMPT_VERSION after any prompt change to force re-extraction.
Needs ANTHROPIC_API_KEY (or another credential the SDK resolves).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

import config
import sections
from theme_dictionary import CATEGORIES, CATEGORY_DEFINITIONS, CODING_RULES

CATEGORY_ENUM = CATEGORIES + ["other"]

# Account limits (from the anthropic-ratelimit-* response headers): 500k input
# and 80k output tokens per minute. Output limits are charged against
# max_tokens up front, so max_tokens is sized per task from the pilot's
# observed outputs (incentives max 7.6k, proposals max 2.2k incl. thinking).
MAX_TOKENS = {"incentives": 10_000, "proposals": 8_000}   # proposals raised after COP 2018 hit 4k
BUDGET_IN, BUDGET_OUT = 400_000, 64_000          # 80% of the per-minute limits


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
# Claude Haiku 5.5 list prices (USD per million tokens, prompts <= 100k tokens).
PRICE_IN, PRICE_OUT = 0.10, 0.50

SYSTEM = (
    "You extract structured data from US proxy statements (SEC Schedule 14A) for an academic "
    "study of corporate values.\n\n"
    "Stakeholder categories (stakeholder theory, Freeman 1984):\n"
    + "\n".join(f"- {k}: {v}" for k, v in CATEGORY_DEFINITIONS.items())
    + "\n- other: fits none of the above (e.g. individual performance, strategic milestones "
    "that name no stakeholder).\n\n"
    "Coding rules for ambiguous cases:\n" + "\n".join(f"- {r}" for r in CODING_RULES) + "\n\n"
    "Rules: extract only what the text states. Never invent or infer a weight: if no weight is "
    "stated, use null. Evidence must be a verbatim quote from the text of at most 30 words."
)

INCENTIVES_TASK = """Below is the Compensation Discussion and Analysis (CD&A) from {company}'s proxy statement filed {filing_date}.

List every performance metric that the named executive officers' incentive pay is tied to, in the annual incentive (bonus) plan and in long-term incentive plans (performance shares or units).
For each metric give:
- metric: its name as written;
- plan: annual_incentive, long_term_incentive or other;
- level: metric for a metric or assessment dimension; sub_criterion for a named criterion listed under a dimension;
- weight_pct: the weight in percent stated in the text for this specific metric, else null. Do not derive a weight (a sole metric with no stated weight is null);
- weight_of: plan_total if weight_pct is a share of the whole plan's payout; parent_component if it is a share of a component (e.g. three equal thirds of a 50% qualitative portion); none if weight_pct is null;
- application: weighted (a component with a weight or formula), modifier (adjusts the payout up or down, e.g. a +/-10% ESG modifier), or holistic_factor (an unweighted factor in a discretionary or scorecard assessment);
- measurement: quantitative (numeric target or formula) or qualitative;
- category: the stakeholder category the metric serves. Financial and stock-market metrics (EPS, TSR, ROE, ROTCE, revenue, operating income, cash flow, margins) are shareholders;
- applies_to: reported_year if it governed pay decided in the cycle the proxy reports on (including long-term awards granted in that cycle, although they vest later); future_year only for a change announced for a later cycle;
- scope: all if the metric and weight apply to all named executives; ceo if they apply to the CEO only (when weights differ between the CEO and the others, report the CEO's and use ceo);
- evidence: a short verbatim quote.
If pay is decided by a holistic assessment with no formula, list the assessment dimensions the text names as holistic_factor metrics. When a dimension or scorecard item names specific criteria (e.g. "Delivery on DEI commitments", "emissions-intensity reductions", "integrating environmental sustainability"), also list each named criterion as its own sub_criterion item with its own category. Report each metric once per plan; if the same factors govern both the annual and the long-term award, list them under both. Do not list compensation elements that are not performance metrics (salary, time-vested awards, benefits).

<cda>
{text}
</cda>"""

PROPOSALS_TASK = """Below is the shareholder-proposal section from {company}'s proxy statement filed {filing_date}.

List each proposal submitted by shareholders. Exclude management proposals (election of directors, auditor ratification, say-on-pay, equity plans, charter amendments proposed by the board).
For each give:
- item_number: as printed (e.g. "5"), or "" if none;
- title: as printed;
- proponent: the proponent as named, or "not stated";
- topic_summary: what the proposal asks for, in at most 25 words;
- category: the stakeholder category the proposal mainly concerns;
- secondary_category: a second category if clearly relevant, else none;
- board_recommendation: for, against, no_recommendation, or not_stated;
- evidence: a short verbatim quote showing the board's recommendation.
Return an empty list if the section contains no shareholder proposals.

<section>
{text}
</section>"""

NULLABLE_NUMBER = {"anyOf": [{"type": "number"}, {"type": "null"}]}

INCENTIVES_SCHEMA = {
    "type": "object",
    "properties": {
        "metrics": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "metric": {"type": "string"},
                "plan": {"type": "string", "enum": ["annual_incentive", "long_term_incentive", "other"]},
                "level": {"type": "string", "enum": ["metric", "sub_criterion"]},
                "weight_pct": NULLABLE_NUMBER,
                "weight_of": {"type": "string", "enum": ["plan_total", "parent_component", "none"]},
                "application": {"type": "string", "enum": ["weighted", "modifier", "holistic_factor"]},
                "measurement": {"type": "string", "enum": ["quantitative", "qualitative"]},
                "category": {"type": "string", "enum": CATEGORY_ENUM},
                "applies_to": {"type": "string", "enum": ["reported_year", "future_year"]},
                "scope": {"type": "string", "enum": ["all", "ceo"]},
                "evidence": {"type": "string"},
            },
            "required": ["metric", "plan", "level", "weight_pct", "weight_of", "application", "measurement",
                         "category", "applies_to", "scope", "evidence"],
            "additionalProperties": False,
        }},
    },
    "required": ["metrics"],
    "additionalProperties": False,
}

PROPOSALS_SCHEMA = {
    "type": "object",
    "properties": {
        "proposals": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "item_number": {"type": "string"},
                "title": {"type": "string"},
                "proponent": {"type": "string"},
                "topic_summary": {"type": "string"},
                "category": {"type": "string", "enum": CATEGORY_ENUM},
                "secondary_category": {"type": "string", "enum": CATEGORY_ENUM + ["none"]},
                "board_recommendation": {"type": "string",
                                         "enum": ["for", "against", "no_recommendation", "not_stated"]},
                "evidence": {"type": "string"},
            },
            "required": ["item_number", "title", "proponent", "topic_summary", "category",
                         "secondary_category", "board_recommendation", "evidence"],
            "additionalProperties": False,
        }},
    },
    "required": ["proposals"],
    "additionalProperties": False,
}

TASKS = {
    "incentives": (INCENTIVES_TASK, INCENTIVES_SCHEMA, sections.find_cda, "metrics"),
    "proposals": (PROPOSALS_TASK, PROPOSALS_SCHEMA, sections.find_proposals, "proposals"),
}


def cache_key(task: str, prompt: str, schema: dict) -> str:
    payload = json.dumps({"model": config.LLM_MODEL, "effort": config.LLM_EFFORT,
                          "prompt_version": config.LLM_PROMPT_VERSION, "task": task,
                          "system": SYSTEM, "prompt": prompt, "schema": schema}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def call_model(client, prompt: str, schema: dict, max_tokens: int, label: str) -> dict:
    """One schema-constrained request. Returns {'result', 'usage'} or {'error'}."""
    import anthropic
    # The account has an input-tokens-per-minute limit and sections are large
    # (up to ~40k tokens), so parallel workers hit 429s. The SDK's own quick
    # retries are not enough: wait as long as the server's retry-after says.
    for attempt in range(8):
        ev = BUDGET.reserve(len(prompt) // 3, max_tokens, label)
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
        except anthropic.BadRequestError as e:          # not retryable: record and move on
            return {"error": f"bad_request: {e.message}"}
        except anthropic.APIStatusError as e:       # SDK already retried 5xx
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


CDA_TARGETS = {}   # (ticker, year) -> firm's median CD&A length in other years; set in main()


def run_one(client, r: dict, task: str, dry_run: bool) -> dict:
    template, schema, finder, _ = TASKS[task]
    text = (config.REPO_DIR / r["text_path"]).read_text()
    if task == "incentives":
        sec = sections.find_cda(text, CDA_TARGETS.get((r["ticker"], r["filing_year"])))
    else:
        sec = finder(text)
    base = {"ticker": r["ticker"], "sector": r["sector"], "filing_year": r["filing_year"],
            "accession": r["accession"], "task": task}
    if sec is None:
        return dict(base, status="no_section", section_words=0)
    prompt = template.format(company=r["company_name"], filing_date=r["filing_date"], text=sec["text"])
    key = cache_key(task, prompt, schema)
    base.update(section_words=sec["words"], section_method=sec["method"], cache_key=key,
                est_input_tokens=len(prompt) // 3)  # pilot: ~3 chars/token on proxy text
    path = config.LLM_CACHE_DIR / task / f"{key}.json"
    if path.exists():
        rec = json.loads(path.read_text())
        return dict(base, status="cached", **rec.get("usage", {}), result=rec["result"])
    if dry_run:
        return dict(base, status="dry_run")
    out = call_model(client, prompt, schema, MAX_TOKENS[task], f"{r['ticker']} {r['filing_year']} {task}")
    print(f"  done {r['ticker']} {r['filing_year']} {task}", flush=True)
    if "error" in out:
        return dict(base, status="error", error=out["error"], **out.get("usage", {}))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"meta": base, "model": config.LLM_MODEL, "usage": out["usage"],
                                "result": out["result"]}, indent=1))
    return dict(base, status="ok", **out["usage"], result=out["result"])


def flatten(runs: list) -> tuple:
    """Long tables of metrics and proposals, plus firm-year aggregates."""
    metrics, proposals = [], []
    for r in runs:
        if "result" not in r:
            continue
        keys = {k: r[k] for k in ("ticker", "sector", "filing_year", "accession")}
        items = r["result"].get(TASKS[r["task"]][3], [])
        (metrics if r["task"] == "incentives" else proposals).extend(dict(keys, **it) for it in items)
    return pd.DataFrame(metrics), pd.DataFrame(proposals)


def apply_overrides(df: pd.DataFrame, task: str) -> pd.DataFrame:
    """Documented manual corrections (data/extraction_overrides.csv), applied after
    reading the cache so model outputs and cache stay untouched. Each override must
    match the extracted value it replaces (`expected`), otherwise the run stops:
    a stale override never applies silently."""
    path = config.DATA_DIR / "extraction_overrides.csv"
    if not path.exists() or df.empty:
        return df
    ov = pd.read_csv(path, dtype=str, keep_default_na=False)
    ov = ov[ov["task"] == task]
    for o in ov.itertuples():
        mask = ((df["ticker"] == o.ticker) & (df["filing_year"] == int(o.filing_year))
                & (df["metric" if task == "incentives" else "title"] == o.metric))
        if mask.sum() != 1:
            if not ((df["ticker"] == o.ticker) & (df["filing_year"] == int(o.filing_year))).any():
                continue   # firm-year not in this run (e.g. a --tickers subset or the extension)
            raise RuntimeError(f"override matches {mask.sum()} rows: {o.ticker} {o.filing_year} {o.metric}")
        cur = df.loc[mask, o.field].iloc[0]
        if str(cur) != o.expected and not (pd.isna(cur) and o.expected == ""):
            try:
                same = float(cur) == float(o.expected)
            except (TypeError, ValueError):
                same = False
            if not same:
                raise RuntimeError(f"override expected {o.field}={o.expected!r}, found {cur!r}: "
                                   f"{o.ticker} {o.filing_year} {o.metric}")
        new = None if o.new == "" else (float(o.new) if o.field == "weight_pct" else o.new)
        df.loc[mask, o.field] = new
        print(f"  override applied: {o.ticker} {o.filing_year} {o.metric} {o.field}: {cur!r} -> {new!r}")
    return df


def firm_year_aggregates(runs_df: pd.DataFrame, met: pd.DataFrame, prop: pd.DataFrame) -> pd.DataFrame:
    """One row per firm-year: incentive emphasis and proposal pressure by category."""
    keys = ["ticker", "sector", "filing_year"]
    fy = runs_df.pivot_table(index=keys, columns="task", values="status", aggfunc="first").reset_index()
    fy.columns = [f"status_{c}" if c in TASKS else c for c in fy.columns]
    if len(met):
        cur = met[met["applies_to"] == "reported_year"]
        n_sub = cur[cur["level"] == "sub_criterion"].groupby(keys).size().rename("n_sub_criteria")
        sub_cats = (cur[cur["level"] == "sub_criterion"].pivot_table(index=keys, columns="category", values="metric",
                                                                       aggfunc="size", fill_value=0)
                    .add_prefix("n_sub_criteria_"))
        cur = cur[cur["level"] == "metric"]
        agg = cur.groupby(keys).agg(n_metrics=("metric", "size"),
                                    n_nonfinancial=("category", lambda s: (s != "shareholders").sum()),
                                    has_modifier=("application", lambda s: (s == "modifier").any()))
        # Count share: each listed metric counts once, whether or not it is weighted.
        cnt = cur.pivot_table(index=keys, columns="category", values="metric", aggfunc="size", fill_value=0)
        cnt = cnt.div(cnt.sum(axis=1), axis=0).add_prefix("inc_count_share_")
        # Weight share of the annual incentive. Only weights stated as a share of the
        # plan total count (nested weights would double count), and only when one
        # scope's weights are complete (sum to ~100%): firms often disclose weights
        # for part of the plan or only for the CEO, and a partial set would give a
        # misleading share. Prefer all-executive rows, else CEO rows; else leave empty.
        w = cur[(cur["plan"] == "annual_incentive") & (cur["application"] == "weighted")
                & (cur["weight_of"] == "plan_total") & cur["weight_pct"].notna()]
        picked = []
        for k, g in w.groupby(keys):
            for scope in ("all", "ceo"):
                gs = g[g["scope"] == scope]
                if 95 <= gs["weight_pct"].sum() <= 105:
                    picked.append(gs)
                    break
        if picked:
            w = pd.concat(picked)
            ws = w.pivot_table(index=keys, columns="category", values="weight_pct", aggfunc="sum", fill_value=0)
            ws = ws.div(ws.sum(axis=1), axis=0).add_prefix("aip_weight_share_")
            ws["aip_weight_scope"] = w.groupby(keys)["scope"].first()
        else:
            ws = pd.DataFrame(index=agg.index)
        fy = fy.merge(agg.join(cnt, how="left").join(ws, how="left").join(n_sub, how="left")
                      .join(sub_cats, how="left").reset_index(), on=keys, how="left")
    if len(prop):
        pa = prop.groupby(keys).agg(n_proposals=("title", "size"),
                                    share_board_against=("board_recommendation", lambda s: (s == "against").mean()))
        pc = prop.pivot_table(index=keys, columns="category", values="title", aggfunc="size", fill_value=0)
        fy = fy.merge(pa.join(pc.add_prefix("n_proposals_")).reset_index(), on=keys, how="left")
    return fy


def write_handcheck(runs_df: pd.DataFrame, met: pd.DataFrame, prop: pd.DataFrame, n: int) -> None:
    """Sample n firm-years (spread across firms and years) for manual verification."""
    done = runs_df[runs_df["status"].isin(["ok", "cached"])][["ticker", "filing_year"]].drop_duplicates()
    sample = (done.sample(frac=1, random_state=7)
              .groupby("ticker", group_keys=False).head(max(1, n // max(done["ticker"].nunique(), 1) + 1))
              .head(n).sort_values(["ticker", "filing_year"]))
    rows = []
    for t, y in sample.itertuples(index=False):
        for _, m in met[(met.ticker == t) & (met.filing_year == y)].iterrows():
            rows.append({"ticker": t, "filing_year": y, "task": "incentives", "item": m["metric"],
                         "extracted": f"{m['plan']} | w={m['weight_pct']} | {m['application']} | {m['category']}",
                         "evidence": m["evidence"], "hc_verdict": "", "hc_notes": ""})
        for _, p in prop[(prop.ticker == t) & (prop.filing_year == y)].iterrows():
            rows.append({"ticker": t, "filing_year": y, "task": "proposals", "item": p["title"],
                         "extracted": f"{p['category']} | board={p['board_recommendation']}",
                         "evidence": p["evidence"], "hc_verdict": "", "hc_notes": ""})
    # One sheet per prompt version; never overwrite a sheet that may hold verdicts.
    out = config.ANALYSIS_DIR / f"handcheck_sheet_{config.LLM_PROMPT_VERSION}.csv"
    if out.exists():
        print(f"hand-check sheet exists, not overwritten: {out}")
        return
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"hand-check sheet: {len(sample)} firm-years, {len(rows)} items -> {out}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tickers", nargs="*")
    ap.add_argument("--tasks", nargs="*", default=list(TASKS))
    ap.add_argument("--dry-run", action="store_true", help="find sections and estimate cost; no API calls")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--handcheck", type=int, default=0, help="write a hand-check sheet for N firm-years")
    args = ap.parse_args(argv)

    cov = pd.read_csv(config.COVERAGE_OUT)
    cov = cov[cov["status"] != "gap"]
    if args.tickers:
        cov = cov[cov["ticker"].isin([t.upper() for t in args.tickers])]

    client = None
    if not args.dry_run:
        import anthropic
        from dotenv import load_dotenv
        load_dotenv(config.REPO_DIR / ".env")   # gitignored; ANTHROPIC_API_KEY=...
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            print("No ANTHROPIC_API_KEY set. Export a key, or use --dry-run.", file=sys.stderr)
            return 2
        client = anthropic.Anthropic(max_retries=5)

    # CD&A targets use all of a firm's years, whatever subset is being run.
    allcov = pd.read_csv(config.COVERAGE_OUT)
    allcov = allcov[(allcov["status"] != "gap") & allcov["ticker"].isin(cov["ticker"])]
    CDA_TARGETS.update(sections.cda_targets(
        (r.ticker, r.filing_year, (config.REPO_DIR / r.text_path).read_text()) for r in allcov.itertuples()))
    jobs = [(r, t) for r in cov.to_dict("records") for t in args.tasks]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        runs = list(pool.map(lambda j: run_one(client, j[0], j[1], args.dry_run), jobs))

    runs_df = pd.DataFrame([{k: v for k, v in r.items() if k != "result"} for r in runs])
    for col in ("input_tokens", "output_tokens"):
        if col not in runs_df:
            runs_df[col] = None
    tok_in = runs_df["input_tokens"].fillna(runs_df.get("est_input_tokens", 0)).sum()
    tok_out = runs_df["output_tokens"].fillna(0).sum()
    print(runs_df.groupby(["task", "status"]).size().to_string())
    print(f"input tokens {tok_in:,.0f}  output tokens {tok_out:,.0f}  "
          f"cost ~${tok_in / 1e6 * PRICE_IN + tok_out / 1e6 * PRICE_OUT:.2f}"
          + (" (output not yet known)" if args.dry_run else ""))

    out = config.ANALYSIS_DIR
    out.mkdir(parents=True, exist_ok=True)
    runs_df.to_csv(out / "llm_runs.csv", index=False)
    if args.dry_run:
        return 0
    met, prop = flatten(runs)
    met = apply_overrides(met, "incentives")
    prop = apply_overrides(prop, "proposals")
    met.to_csv(out / "incentive_metrics.csv", index=False)
    prop.to_csv(out / "shareholder_proposals.csv", index=False)
    firm_year_aggregates(runs_df, met, prop).to_csv(out / "llm_firm_year.csv", index=False)
    if args.handcheck:
        write_handcheck(runs_df, met, prop, args.handcheck)
    errors = runs_df[runs_df["status"] == "error"]
    if len(errors):
        print(errors[["ticker", "filing_year", "task", "error"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
