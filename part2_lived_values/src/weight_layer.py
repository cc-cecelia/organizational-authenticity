"""Weight layer: incentive-plan weights for every firm-year, including those
whose proxies do not fully disclose them.

Usage (after llm_extract.py):
    python part2_lived_values/src/weight_layer.py --tickers MSFT JPM XOM   # pilot
    python part2_lived_values/src/weight_layer.py                          # all firms
    python part2_lived_values/src/weight_layer.py --mask-test              # leakage-controlled validation

A separate pass. It reads llm_extract.py's outputs and never modifies that
extraction or its cache. Its own LLM calls are cached in data/llm_cache_weights/.

Method, per firm-year and plan (annual incentive; long-term incentive):
 0. Items: extracted metrics for the reported cycle. All-executive rows are
    used if the plan has any, else CEO rows, so no criterion is counted twice.
 1. One call per firm-year, only where some tier lacks per-metric weights
    (needs_call) plus the masking-test set; all weight arithmetic below is
    plain Python, so rules can change without new API calls.
    Structure + stated split + emphasis call (Claude Haiku 5.5, JSON schema, cached by a
    SHA-256 fingerprint of model, layer version, prompt, schema, CD&A text and
    item list). Input: the CD&A and the extracted item list (names, levels,
    categories; never the extracted weights). Output per item: parent_id (the
    tier it belongs to, null for a top-level tier), emphasis (1 = listed in
    passing, 2 = given its own description or rationale, 3 = called primary
    or key, or given the most space), evidence; plus every parent whose
    children the text says are weighted equally.
 2. Top-level tier weights: as disclosed (weight_of == plan_total). Any
    remaining mass (100 - disclosed sum) goes to the undisclosed top-level
    tiers in proportion to emphasis (or equally if the text says so).
 3. A tier's weight is always passed down to its children: stated child
    weights (weight_of == parent_component), else a stated equal split, else
    emphasis / sum of emphasis within the tier. Proportional, not softmax.
    Refinement for imputed splits only: if none of a tier's children shares the
    tier's own category, the tier keeps a residual share as an implicit sibling
    (scored with its own emphasis), because extracted children list named
    criteria and are often partial. Stated splits are always passed down in full.
 4. Category weight = sum of leaf weights by category.
weight_source (per leaf; per firm-year = the weakest source of any leaf with
weight): disclosed < derived_from_stated_split < imputed_emphasis; none when
the plan has no items.

Masking test (--mask-test): on firm-years whose annual-incentive weights are
fully disclosed, the CD&A and item names are redacted (every number replaced
by '#', plus weight vocabulary such as 'equally', 'weighted', 'weighting') so
the model cannot read the answer. Weights are then rebuilt from the masked
structure by (a) equal split within every tier and (b) emphasis, and compared
with the disclosed truth by mean absolute error in percentage points, at item
and at category level.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

import config
import sections
from llm_extract import BUDGET, PRICE_IN, PRICE_OUT
from theme_dictionary import CATEGORIES

LAYER_VERSION = "w1"
CACHE = config.DATA_DIR / "llm_cache_weights"
OUT = config.ANALYSIS_DIR
PLANS = {"annual_incentive": "aip", "long_term_incentive": "lti"}
SOURCE_RANK = {"disclosed": 0, "derived_from_stated_split": 1, "imputed_emphasis": 2}
RESIDUAL = "__residual__"

SYSTEM = (
    "You analyse the Compensation Discussion and Analysis (CD&A) of US proxy statements for an academic "
    "study. You are given the CD&A and a numbered list of incentive-plan items already extracted from it. "
    "Judge only from the text. Evidence must be a verbatim quote of at most 25 words."
)

TASK = """Items extracted from this CD&A (id | plan | level | name | category):
{items}

For every item give:
- parent_id: the id of the item it sits under (a sub-criterion or component of a broader tier, e.g. "Customer satisfaction" under "Customers & Stakeholders", or "Product & Strategy" under "Qualitative performance"); null if it is a top-level tier of its plan. Parents must be in the same plan.
- emphasis: 1 if the CD&A only lists it in passing; 2 if it gets its own description or rationale; 3 if the CD&A calls it primary or key, or gives it the most space among its siblings.
- evidence: a short verbatim quote supporting the emphasis score.
Also list in equal_split every parent whose children the text says are weighted equally (use -1 for the top-level tiers of a plan, with that plan named), with a quote.

<cda>
{text}
</cda>"""

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "parent_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                "emphasis": {"type": "integer", "enum": [1, 2, 3]},
                "evidence": {"type": "string"},
            },
            "required": ["id", "parent_id", "emphasis", "evidence"],
            "additionalProperties": False,
        }},
        "equal_split": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "parent_id": {"type": "integer"},
                "plan": {"type": "string", "enum": list(PLANS)},
                "evidence": {"type": "string"},
            },
            "required": ["parent_id", "plan", "evidence"],
            "additionalProperties": False,
        }},
    },
    "required": ["items", "equal_split"],
    "additionalProperties": False,
}

# Leakage control for the masking test. Strict by design (v2 of the redaction,
# after a scan of the first version found spelled-out percentages such as
# "fifty percent" and cues such as "three equal components" surviving):
#  - every digit sequence, with any currency sign or percent sign -> '#'
#  - every spelled-out number word and fraction word -> '#'
#  - every word containing weigh / equal / proportion / percent, and "evenly" -> '[w]'
#  - any remaining '%' removed
NUM_RE = re.compile(r"[$€£]?\d[\d,]*(\.\d+)?\s*%?")
NUM_WORDS = re.compile(
    r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|"
    r"half|halves|thirds?|quarters?|fourths?|fifths?|tenths?|twice|double|triple)\b", re.I)
WEIGHT_WORDS = re.compile(r"\b\w*(weigh|equal|proportion|percent)\w*\b|\bevenly\b|\bin equal (parts|portions)\b", re.I)
REDACTION_VERSION = "r2"
def redact(text: str) -> str:
    text = WEIGHT_WORDS.sub("[w]", text)
    text = NUM_RE.sub("#", text)
    text = NUM_WORDS.sub("#", text)
    return text.replace("%", "")


# ---------------------------------------------------------------------------
def select_items(met: pd.DataFrame) -> pd.DataFrame:
    """Reported-cycle items per firm-year and plan: union of the all-executive
    and CEO-only rows, de-duplicated by name. Many firms tag their scorecard
    'ceo' and the bonus formula 'all' (XOM 2023), so keeping one scope would
    drop most of the plan. Where the same criterion appears in both scopes
    (MSFT 2021: CEO 35/35/10/10/10, others unstated), the row with a stated
    weight wins, then the all-executive row."""
    cur = met[(met["applies_to"] == "reported_year") & met["plan"].isin(PLANS)].copy()
    cur["_key"] = cur["metric"].map(lambda x: re.sub(r"[^a-z0-9]+", " ", str(x).lower()).strip())
    cur["_rank"] = cur["weight_pct"].isna().astype(int) * 2 + (cur["scope"] != "all").astype(int)
    out = (cur.sort_values("_rank")
              .drop_duplicates(["ticker", "filing_year", "plan", "_key"])
              .sort_index()
              .drop(columns=["_key", "_rank"])
              .reset_index(drop=True))
    out["item_id"] = out.groupby(["ticker", "filing_year"]).cumcount()
    return out


def fingerprint(prompt: str) -> str:
    key = {"model": config.LLM_MODEL, "effort": config.LLM_EFFORT, "layer": LAYER_VERSION,
           "system": SYSTEM, "prompt": prompt, "schema": SCHEMA}
    # Redaction version only for masked prompts: adding the key to unmasked
    # prompts would change every production fingerprint and force re-calls.
    if "[w]" in prompt:
        key["redaction"] = REDACTION_VERSION
    payload = json.dumps(key, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def call_structure(client, prompt: str, label: str) -> dict:
    import anthropic, time
    for attempt in range(8):
        ev = BUDGET.reserve(len(prompt) // 3, 6_000, label)
        try:
            resp = client.messages.create(
                model=config.LLM_MODEL, max_tokens=6_000, system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": config.LLM_EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}})
            BUDGET.settle(ev, resp.usage.input_tokens, resp.usage.output_tokens)
            break
        except anthropic.RateLimitError as e:
            if attempt == 7:
                return {"error": "rate_limited"}
            time.sleep(min(int(e.response.headers.get("retry-after", "20")), 90) + 2 * attempt)
        except anthropic.APIError as e:
            return {"error": f"api: {getattr(e, 'message', e)}"}
    usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    if resp.stop_reason in ("refusal", "max_tokens"):
        return {"error": resp.stop_reason, "usage": usage}
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        return {"result": json.loads(text), "usage": usage}
    except json.JSONDecodeError as e:
        return {"error": f"invalid_json: {e}", "usage": usage}


def structure_for(client, key, items: pd.DataFrame, cda_text: str, masked: bool, dry_run: bool) -> dict:
    t, y = str(key[0]), int(key[1])   # plain types: the cache metadata is JSON
    txt = redact(cda_text) if masked else cda_text
    lines = []
    for r in items.itertuples():
        name = redact(r.metric) if masked else r.metric
        lines.append(f"{r.item_id} | {r.plan} | {r.level} | {name} | {r.category}")
    prompt = TASK.format(items="\n".join(lines), text=txt)
    fp = fingerprint(prompt)
    path = CACHE / ("masked" if masked else "full") / f"{fp}.json"
    base = {"ticker": t, "filing_year": y, "masked": masked, "fingerprint": fp, "est_input_tokens": len(prompt) // 3}
    if path.exists():
        rec = json.loads(path.read_text())
        return dict(base, status="cached", result=rec["result"], **rec.get("usage", {}))
    if dry_run:
        return dict(base, status="dry_run")
    out = call_structure(client, prompt, f"{t} {y}{' masked' if masked else ''}")
    if "error" in out:
        return dict(base, status="error", error=out["error"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"meta": base, "usage": out["usage"], "result": out["result"]}, indent=1))
    print(f"  done {t} {y}{' masked' if masked else ''}", flush=True)
    return dict(base, status="ok", result=out["result"], **out["usage"])


# ---------------------------------------------------------------------------
def build_weights(items: pd.DataFrame, struct: dict, use_disclosed: bool = True,
                  method: str = "emphasis") -> pd.DataFrame:
    """Leaf weights for one firm-year. method: 'emphasis' or 'equal'.
    use_disclosed=False ignores extracted weights (masking test)."""
    s_items = {d["id"]: d for d in struct.get("items", [])}
    eq = {(d["plan"], d["parent_id"]) for d in struct.get("equal_split", [])} if method == "emphasis" else set()
    rows = []
    for plan, g in items.groupby("plan"):
        ids = set(g["item_id"])
        parent = {}
        for i in ids:
            p = s_items.get(i, {}).get("parent_id")
            parent[i] = p if (p in ids and p != i) else None
        # Break cycles defensively: an item whose parent chain loops becomes top-level.
        for i in ids:
            seen, p = {i}, parent[i]
            while p is not None and p not in seen:
                seen.add(p); p = parent[p]
            if p is not None:
                parent[i] = None
        emph = {i: s_items.get(i, {}).get("emphasis", 1) for i in ids}
        rec = g.set_index("item_id")
        weight, source = {}, {}
        resid_weight, resid_source = {}, {}

        def split(children, total, parent_key, parent_src):
            """Distribute `total` over children: stated -> stated equal -> emphasis (or equal)."""
            if not children:
                return
            stated_kind = "plan_total" if parent_key == -1 else "parent_component"
            stated = {c: rec.at[c, "weight_pct"] for c in children
                      if use_disclosed and rec.at[c, "weight_of"] == stated_kind and pd.notna(rec.at[c, "weight_pct"])}
            if stated:
                if parent_key == -1:   # plan_total weights are already absolute
                    for c, w in stated.items():
                        weight[c], source[c] = float(w), "disclosed"
                    rest_total = max(total - sum(stated.values()), 0.0)
                else:                  # parent_component weights are shares of the parent
                    ssum = sum(stated.values())
                    for c, w in stated.items():
                        weight[c] = total * float(w) / (ssum if ssum > 105 or len(stated) == len(children) else 100)
                        source[c] = worst(parent_src, "derived_from_stated_split")
                    rest_total = max(total - sum(weight[c] for c in stated), 0.0)
            else:
                rest_total = total
            rest = [c for c in children if c not in stated]
            # Residual for the parent itself, only when the split is imputed: the
            # extraction lists *named* criteria, so a dimension's children are often
            # partial (JPM's Client/Customer/Stakeholder -> only "Delivery on DEI
            # commitments"). If no child shares the parent's category, the parent
            # keeps an implicit sibling share so its own stakeholder is not erased.
            # Stated splits (numbers or "equally") are always passed down in full.
            residual = (parent_key != -1 and not stated and (plan, parent_key) not in eq
                        and rec.at[parent_key, "category"] not in {rec.at[c, "category"] for c in children})
            if residual:
                rest = rest + [RESIDUAL]
                emph[RESIDUAL] = emph[parent_key]
            if rest and rest_total > 0:
                if method == "equal" or (plan, parent_key) in eq:
                    for c in rest:
                        weight[c] = rest_total / len(rest)
                        source[c] = worst(parent_src, "derived_from_stated_split" if method == "emphasis" else "equal")
                else:
                    esum = sum(emph[c] for c in rest)
                    for c in rest:
                        weight[c] = rest_total * emph[c] / esum
                        source[c] = worst(parent_src, "imputed_emphasis")
            elif rest:
                for c in rest:
                    weight[c], source[c] = 0.0, worst(parent_src, "disclosed")
            if residual:
                resid_weight[parent_key] = weight.pop(RESIDUAL, 0.0)
                resid_source[parent_key] = source.pop(RESIDUAL, "none")

        tops = sorted(i for i in ids if parent[i] is None)
        split(tops, 100.0, -1, "disclosed")
        frontier = list(tops)
        while frontier:
            nxt = []
            for p in frontier:
                kids = sorted(i for i in ids if parent[i] == p)
                split(kids, weight.get(p, 0.0), p, source.get(p, "disclosed"))
                nxt += kids
            frontier = nxt
        has_kids = {parent[i] for i in ids if parent[i] is not None}
        for i in ids:
            rows.append({"item_id": i, "plan": plan, "metric": rec.at[i, "metric"], "category": rec.at[i, "category"],
                         "parent_id": parent[i], "emphasis": emph[i], "is_leaf": i not in has_kids,
                         "weight": round(weight.get(i, 0.0), 3), "weight_source": source.get(i, "none")})
        for p, w in resid_weight.items():   # parent residual as its own leaf
            rows.append({"item_id": f"{p}r", "plan": plan, "metric": f"{rec.at[p, 'metric']} (residual)",
                         "category": rec.at[p, "category"], "parent_id": p, "emphasis": emph[p], "is_leaf": True,
                         "weight": round(w, 3), "weight_source": resid_source[p]})
    return pd.DataFrame(rows)


def worst(a: str, b: str) -> str:
    if a not in SOURCE_RANK:
        return a
    return max(a, b, key=lambda s: SOURCE_RANK.get(s, 3))


def category_shares(leaves: pd.DataFrame) -> dict:
    lv = leaves[leaves["is_leaf"] & (leaves["weight"] > 0)]
    tot = lv["weight"].sum()
    return {c: round(lv.loc[lv["category"] == c, "weight"].sum() / tot, 4) if tot else None
            for c in CATEGORIES + ["other"]}


def firm_year_source(leaves: pd.DataFrame) -> str:
    lv = leaves[leaves["is_leaf"] & (leaves["weight"] > 0)]
    if lv.empty:
        return "none"
    return max(lv["weight_source"], key=lambda s: SOURCE_RANK.get(s, 3))


def needs_call(items: pd.DataFrame) -> bool:
    """True if some tier lacks per-metric weights, so structure/emphasis are needed.

    No call is needed only when, in every plan, every item carries its own stated
    plan-level weight (a flat, fully disclosed scorecard). Items weighted only as a
    share of a parent (MSFT 2019's thirds) need the call to learn their parent.
    """
    for _, g in items.groupby("plan"):
        if not ((g["weight_of"] == "plan_total") & g["weight_pct"].notna()).all():
            return True
    return False


FLAT = {"items": [], "equal_split": []}   # structure for no-call firm-years: all top-level


def fully_disclosed(items: pd.DataFrame) -> bool:
    """Annual-incentive top-level weights stated and summing to ~100%."""
    g = items[(items["plan"] == "annual_incentive") & (items["weight_of"] == "plan_total")]
    return len(g) >= 2 and 95 <= g["weight_pct"].sum() <= 105


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tickers", nargs="*")
    ap.add_argument("--mask-test", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)

    met = pd.read_csv(OUT / "incentive_metrics.csv")
    if args.tickers:
        met = met[met["ticker"].isin([t.upper() for t in args.tickers])]
    items = select_items(met)
    cov = pd.read_csv(config.COVERAGE_OUT)
    cov = cov[cov["status"] != "gap"].set_index(["ticker", "filing_year"])
    allcov = cov.reset_index()
    allcov = allcov[allcov["ticker"].isin(items["ticker"].unique())]
    targets = sections.cda_targets((r.ticker, r.filing_year, (config.REPO_DIR / r.text_path).read_text())
                                   for r in allcov.itertuples())

    client = None
    if not args.dry_run:
        import anthropic
        from dotenv import load_dotenv
        load_dotenv(config.REPO_DIR / ".env")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("No ANTHROPIC_API_KEY set.", file=sys.stderr)
            return 2
        client = anthropic.Anthropic(max_retries=5)

    groups = {k: g for k, g in items.groupby(["ticker", "filing_year"])}
    if args.mask_test:
        groups = {k: g for k, g in groups.items() if fully_disclosed(g)}
        to_call = list(groups)
        print(f"masking test on {len(groups)} firm-years with fully disclosed annual-incentive weights")
    else:
        to_call = [k for k, g in groups.items() if needs_call(g)]
        print(f"{len(groups)} firm-years with incentive items; LLM call needed for {len(to_call)} "
              f"(some tier lacks per-metric weights); {len(groups) - len(to_call)} fully weighted, Python only")

    # Resolve paths before the thread pool: pandas MultiIndex lookups are not
    # thread-safe on first use (the lookup engine is built lazily).
    paths = {(t, int(y)): config.REPO_DIR / tp for (t, y), tp in cov["text_path"].items()}

    def job(k):
        cda = sections.find_cda(paths[(k[0], int(k[1]))].read_text(), targets.get(k))
        return structure_for(client, k, groups[k], cda["text"], args.mask_test, args.dry_run)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        runs = list(pool.map(job, to_call))
    rdf = pd.DataFrame([{k: v for k, v in r.items() if k != "result"} for r in runs])
    for col in ("input_tokens", "output_tokens"):
        if col not in rdf:
            rdf[col] = float("nan")
    tin = rdf["input_tokens"].fillna(rdf["est_input_tokens"]).sum()
    tout = rdf["output_tokens"].fillna(0).sum()
    print(rdf["status"].value_counts().to_string())
    print(f"input tokens {tin:,.0f}  output {tout:,.0f}  cost ~${tin / 1e6 * PRICE_IN + tout / 1e6 * PRICE_OUT:.2f}")
    if args.dry_run:
        return 0
    results = {k: FLAT for k in groups}          # fully weighted: flat structure, no call
    results.update({(r["ticker"], r["filing_year"]): r.get("result") for r in runs})

    if args.mask_test:
        return report_mask_test(groups, results)

    long_rows, fy_rows = [], []
    for k, g in groups.items():
        if results.get(k) is None:
            continue
        leaves = build_weights(g, results[k])
        long_rows.append(leaves.assign(ticker=k[0], filing_year=k[1]))
        row = {"ticker": k[0], "filing_year": k[1]}
        for plan, short in PLANS.items():
            lv = leaves[leaves["plan"] == plan]
            shares = category_shares(lv) if len(lv) else {c: None for c in CATEGORIES + ["other"]}
            pre = "cat_weight_" if short == "aip" else "cat_weight_lti_"
            row.update({f"{pre}{c}": v for c, v in shares.items()})
            row[f"weight_source{'' if short == 'aip' else '_lti'}"] = firm_year_source(lv) if len(lv) else "none"
        fy_rows.append(row)
    pd.concat(long_rows).to_csv(OUT / "weights_long.csv", index=False)
    fy = pd.DataFrame(fy_rows)
    fy.to_csv(OUT / "weights_firm_year.csv", index=False)
    rdf.to_csv(OUT / "weight_runs.csv", index=False)
    print(fy["weight_source"].value_counts().to_string())
    return 0


def known_frontier(truth: pd.DataFrame) -> set:
    """Deepest nodes whose true weight is known (disclosed or derived from a stated
    split) and none of whose children are known. Evaluating there keeps the test
    fair when disclosed tiers carry unweighted named sub-criteria."""
    known = set(truth.loc[truth["weight_source"].isin(["disclosed", "derived_from_stated_split"]), "item_id"])
    parents_of_known = set(truth.loc[truth["item_id"].isin(known), "parent_id"].dropna())
    return {i for i in known if i not in parents_of_known}


def frontier_shares(df: pd.DataFrame, frontier: set) -> dict:
    f = df[df["item_id"].isin(frontier)]
    tot = f["weight"].sum()
    return {c: (f.loc[f["category"] == c, "weight"].sum() / tot if tot else None) for c in CATEGORIES + ["other"]}


def report_mask_test(groups: dict, results: dict) -> int:
    rows, cat_rows = [], []
    for k, g in groups.items():
        if results.get(k) is None:
            continue
        aip = g[g["plan"] == "annual_incentive"]
        # Truth: disclosed weights pushed through the masked structure; methods
        # rebuild every weight from that structure with all weights hidden.
        truth = build_weights(aip, results[k], use_disclosed=True, method="equal")
        emph = build_weights(aip, results[k], use_disclosed=False, method="emphasis")
        eqw = build_weights(aip, results[k], use_disclosed=False, method="equal")
        frontier = known_frontier(truth)
        if len(frontier) < 2:
            continue
        m = truth[truth["item_id"].isin(frontier)][["item_id", "metric", "category", "weight"]].rename(columns={"weight": "true"})
        m = m.merge(emph[["item_id", "weight"]].rename(columns={"weight": "emphasis"}), on="item_id")
        m = m.merge(eqw[["item_id", "weight"]].rename(columns={"weight": "equal"}), on="item_id")
        rows.append(m.assign(ticker=k[0], filing_year=k[1]))
        for name, df in (("true", truth), ("emphasis", emph), ("equal", eqw)):
            cat_rows.append(dict(ticker=k[0], filing_year=k[1], method=name, **frontier_shares(df, frontier)))
    it = pd.concat(rows)
    it["err_emphasis"] = (it["emphasis"] - it["true"]).abs()
    it["err_equal"] = (it["equal"] - it["true"]).abs()
    cats = pd.DataFrame(cat_rows)
    piv = cats.melt(id_vars=["ticker", "filing_year", "method"], var_name="category", value_name="share")
    piv = piv.pivot_table(index=["ticker", "filing_year", "category"], columns="method", values="share").reset_index()
    piv["err_emphasis"] = (piv["emphasis"] - piv["true"]).abs() * 100
    piv["err_equal"] = (piv["equal"] - piv["true"]).abs() * 100

    fy = it.groupby(["ticker", "filing_year"]).agg(n_items=("item_id", "size"),
                                                    mae_equal=("err_equal", "mean"),
                                                    mae_emphasis=("err_emphasis", "mean")).reset_index()
    fy["emphasis_minus_equal"] = fy["mae_emphasis"] - fy["mae_equal"]
    carrying = piv[(piv["true"] > 0) | (piv["equal"] > 0) | (piv["emphasis"] > 0)]
    nonsh = carrying[carrying["category"] != "shareholders"]
    wins, losses = int((fy.emphasis_minus_equal < -1e-9).sum()), int((fy.emphasis_minus_equal > 1e-9).sum())
    n = wins + losses
    p_sign = min(1.0, 2 * sum(math.comb(n, k) for k in range(min(wins, losses) + 1)) / 2 ** n) if n else 1.0

    it.to_csv(OUT / "mask_test_items.csv", index=False)
    fy.to_csv(OUT / "mask_test_firm_year.csv", index=False)
    fy["gap"] = fy["mae_equal"] - fy["mae_emphasis"]
    ex = pd.concat([fy.nlargest(5, "gap").assign(direction="emphasis_better"),
                    fy.nsmallest(5, "gap").assign(direction="emphasis_worse")])
    ex = ex.merge(it, on=["ticker", "filing_year"])[["direction", "ticker", "filing_year", "mae_equal", "mae_emphasis",
                                                       "metric", "category", "true", "equal", "emphasis"]]
    ex.round(2).to_csv(OUT / "mask_test_examples.csv", index=False)

    summary = pd.DataFrame([
        {"level": "item", "subset": "all known-weight items", "n": len(it),
         "mae_equal_pp": it.err_equal.mean(), "mae_emphasis_pp": it.err_emphasis.mean()},
        {"level": "category", "subset": "all 10 categories (incl. true zeros)", "n": len(piv),
         "mae_equal_pp": piv.err_equal.mean(), "mae_emphasis_pp": piv.err_emphasis.mean()},
        {"level": "category", "subset": "categories carrying weight", "n": len(carrying),
         "mae_equal_pp": carrying.err_equal.mean(), "mae_emphasis_pp": carrying.err_emphasis.mean()},
        {"level": "category", "subset": "carrying, excluding shareholders", "n": len(nonsh),
         "mae_equal_pp": nonsh.err_equal.mean(), "mae_emphasis_pp": nonsh.err_emphasis.mean()},
    ]).round(2)
    summary.to_csv(OUT / "mask_test_summary.csv", index=False)
    print(f"\nfirm-years evaluated: {len(fy)}  known-weight items: {len(it)}")
    print(summary.to_string(index=False))
    print(f"firm-years: emphasis better {wins}, worse {losses}, tied {len(fy) - n}; sign test p = {p_sign:.4f}")
    print(f"firm-years where an equal split is exactly right: {(fy.mae_equal < 1e-6).mean():.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
