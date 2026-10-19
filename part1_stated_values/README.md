# Part 1: Stated Values (Wayback Machine About/values pages)

**Status:** complete. The final dataset is `output/stated_values.csv`: 415 of 450 company-years, coded with the LLM step.

## What this does

For each of the 50 sample firms and each year 2016 to 2024, this step collects one archived snapshot of the firm's About or values page from the Internet Archive's Wayback Machine. It then extracts the visible body text. Every attempt, and every gap, is logged with a reason.

```
data/companies.csv              50 firms: ticker, name, sector, domain, curated seed URLs
data/discovery_review.csv       discovered candidate pages, pre-judged, human spot-checked
part1_stated_values/src/
  config.py      every tunable constant, with its justification
  wayback.py     CDX queries and raw id_ fetches; disk cache, rate limit, retries
  pages.py       candidate ordering, page groups, snapshot acceptance rules
  extract.py     visible-text extraction (trafilatura, structural fallback, PDF)
  scrape.py      main entry point; writes all outputs
  discover.py    anchored-prefix discovery for firms whose seeds leave gaps
part1_stated_values/output/
  snapshots.csv     one row per company-year (missing years included)
  decision_log.csv  every capture tried, with accept/reject reason
  gap_log.csv       one row per missing company-year, with reason
  coverage.csv      firm x year grid
```

Run it from the repo root:
```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python part1_stated_values/src/scrape.py              # seeds (+ approved discoveries)
.venv/bin/python part1_stated_values/src/discover.py --from-gaps  # slow; fills review CSV
# spot-check data/discovery_review.csv, then re-run scrape.py (fetches are cached)
```

## Decisions and why

### 1. Which page counts as "the" About page
- **Values page first, general About page second.** When a firm has a dedicated mission, values, purpose, credo or principles page, we use it. Examples are JPMorgan's Business Principles, J&J's Credo and Chevron's "The Chevron Way". These pages are the most direct statement of the construct we are measuring. The general About page is the fallback in years when no values page exists. `page_type` records which kind each row is: `values` or `about`.
- **How page type is decided.** It comes from the URL path (`config.VALUES_PATH_RE`). This is cheap and scales to 500 firms. Its weakness is that an About page carrying a full values statement is labelled `about`.
- **Candidate URLs, in this order:**
  1. Curated seed URLs (`data/companies.csv`).
  2. Pages found by discovery that a reviewer approved.
  3. Redirect successors of either.

  Seeds always rank above discovered pages.
- **Ranking candidates.** Candidates are grouped into logical pages. Groups are ranked by: seed before discovered, values before About, most years of archive coverage, then curated order. For each year we take the first group with an acceptable capture. Ranking by coverage keeps the same page across years wherever the archive allows it.

### 2. Which snapshot within a year
- **The capture nearest July 1.** A mid-year anchor is the most representative single view of a calendar year, and it rarely straddles the January site redesigns common among these firms.
- **Order of attempts.** Captures with HTTP 200 are tried first (up to 3, nearest first). Then archived redirects (3xx) that Wayback can resolve (up to 2).
- **Duplicate skipping.** A capture whose content hash matches one already tried is skipped, because it would give the same result.
- **Raw fetches.** Pages are fetched with the `id_` modifier. That returns the bytes as originally captured, without the Wayback toolbar or rewritten links, and they are cached to disk.

### 3. Redirects
Redirects are followed, and the full chain plus the final URL and timestamp are recorded. The result is rejected if any of these holds:
- the redirect landed on a **homepage** (a path made only of locale segments such as `/en-us/`), unless the candidate was itself a root URL such as `about.google/`;
- it landed on a **login** page;
- it landed on an **unrelated domain** (one not among the firm's candidate domains);
- it resolved to a capture in a **different calendar year**;
- it crossed **page types** (a values URL redirecting to a general About URL means the values page was retired; the About candidate supplies that year with the correct label);
- the target was **never archived**.

**Redirect aliasing:** a URL that a page redirects to becomes an alias of the same logical page (`page_group`). This matters because firms move pages. JPMorgan's Business Principles went from `/corporate/About-JPMC/ab-business-principles.htm` to `/about/our-business/business-principles`. Aliasing follows that move instead of dropping to a different page.

`page_switched = True` marks a change of logical page from the previous collected year. **A page switch is never counted as a content change** in the `changed_from_prior` analysis.

### 4. Text extraction
Three extraction methods, applied as follows:
1. **PDF** via `pypdf`. Only Berkshire Hathaway uses it: it has no About page, and its stated values live in the Owner's Manual (`ownman.pdf`).
2. **trafilatura**, the default.
3. A **structural BeautifulSoup pass**, always computed alongside. It removes:
   - `nav`, `header`, `footer`, `aside`, scripts and styles;
   - ARIA chrome roles;
   - class/id tokens such as `site-footer` and `cookie-banner`, matched as whole tokens;
   - link-dense lists (menus);
   - HTML comments.

   It replaces trafilatura's output when trafilatura is thin (under 40 words), or when the structural pass recovers at least 1.5x as many words.

The pilot showed why the structural pass is needed. On ExxonMobil's tile-based About pages (2016 to 2022), trafilatura kept only the lead paragraph and dropped "Our guiding principles" and "Standards of business conduct".

Both extractors then drop:
- exact duplicate lines;
- known UI strings ("Search", "Please update your browser");
- short call-to-action links ("Learn about our commitment").

`extraction_method` records which path produced each row.

Bugs found in the pilot and fixed, documented because they would silently corrupt the change analysis:
- **Order-dependent extraction.** trafilatura's `deduplicate=True` keeps a process-wide cache. It deleted text that repeated across years, so output depended on processing order. It is now disabled, and two runs produce byte-identical output.
- **Empty pages.** Older ASP.NET sites wrap the whole page in one `<form>`. Dropping `<form>` emptied those pages.
- **Content removed as navigation.** A class rule matching substrings removed JPMorgan's `tab-nav-content` panels, which contain the principles text.

### 5. Discovery: finding pages the seeds miss
A CDX prefix query over a whole domain times out with HTTP 504; `www.microsoft.com/en-us/` alone has 4,543 index pages. Discovery therefore makes narrow keyword-anchored prefix queries:
- `host/{about, who, our, company, corporate, values, mission, purpose, credo}`;
- the same keywords under any locale base the seeds use (for example `en-us/`);
- each seed's parent directory.

Each query is collapsed to one row per URL per year. Discovery runs **only for firms whose seeds leave year gaps**, and its results are cached.

Discovered pages are noisy. For JPMorgan, discovery surfaced the JPMorgan Chase Institute's About page and a corporate-governance page. Every candidate therefore goes into `data/discovery_review.csv` with a pre-filled `approved` value and `reason`:
- **Approve:** same host as a seed, and the page's own name or title is about the parent company's values, mission, purpose, principles, credo or About content.
- **Reject:** subsidiaries, institutes, foundations, governance, careers, investor relations, ESG and similar function pages.

The pre-fill is rule-based plus a manual read, and a reviewer spot-checks it. `scrape.py` uses approved rows only, and manual edits survive re-runs.

### 6. Politeness and reproducibility
- At least 1.5 s between any two requests.
- Exponential backoff (4 to 64 s) on connection errors and 5xx responses, with at least 20 s after 429 or 503 (archive.org's throttling signals). `Retry-After` is honored.
- A descriptive User-Agent.
- Every CDX response and raw page is cached under `part1_stated_values/cache/` (git-ignored), so re-runs are offline and deterministic.

## LLM analysis (`src/llm_analyze.py` → `output/stated_values.csv`)

`stated_values.csv` has one row per company-year: 450 rows, with the 35 gap years kept as `status = missing`. The required columns come first: `ticker, company_name, sector, year, page_text_clean, changed_from_prior, theme_categories, analyst_notes`.

### Theme categories
- **Taxonomy.** Rows are coded into the **shared stakeholder taxonomy** (CLAUDE.md; Freeman 1984) that Part 2 uses for proxy statements. The 9 codes are customers, employees, dei, environment, community, shareholders, integrity, safety and innovation.
- **Why this taxonomy.** Part 3 compares what a firm says (this page) with what it pays for and is pressed on (its proxy), stakeholder by stakeholder. That comparison only works if both sides use identical categories.
- **No duplicated definitions.** The definitions and tie-break rules are imported read-only from Part 2's `theme_dictionary.py`, so the two parts cannot drift apart.

For each category the model returns:
- `sal_<cat>`: salience on a 0 to 3 scale.
  - 0 = absent.
  - 1 = passing mention.
  - 2 = a stated value or commitment with some elaboration.
  - 3 = a headline or named core value, or a dominant theme.
- `ev_<cat>`: the single strongest **verbatim** evidence span.
- `share_<cat>`: salience divided by the row's total salience. This is **normalized emphasis**: Part 3 compares how a page distributes its emphasis, not raw volume. Without it, long values pages would outscore short About pages simply because they say more (mean total salience is 13.2 on values pages vs 9.2 on About pages).
- `theme_categories`: the categories with salience ≥ 1, in descending order of salience.
- `page_type` is kept on every row so Part 3 can control for page type.

Part 1 adds four rules to the shared tie-breaks. They come from the pilot hand check:
- **Business description is not a value** unless the sentence states a commitment. This covers products, size, headcount, rankings and scale claims; "we are committed to…" does count.
- **Calls to action, recruiting prompts and site chrome are never values.**
- **"Benefit society" statements are `community`,** not `shareholders`.
- **A span may only be cited for a category it addresses.**

**Evidence verification.** Every span is checked against the page text, after normalizing whitespace, quotes, case and PDF line-break hyphens. 2,277 of 2,283 spans (99.7%) are found verbatim. The 6 that are not are listed in `evidence_unverified`; their salience is kept, so Part 3 can drop or down-weight them.

### `changed_from_prior`
The value is True (substantive change), False (no change, a minor edit, or a cosmetic change), or empty when no valid comparison exists. Each row is compared with the firm's previous collected year (`compared_to_year`, `years_since_prior`). The decision runs in this order, so the LLM is called only where text similarity cannot settle it:

1. **First observation, or a page switch** (different `page_group` or `page_type`): `changed_from_prior` is empty. A switch to a different page is never counted as a content change.
2. **Identical text** (same hash): False, with no LLM call.
3. **Word-sequence similarity ≥ 0.98** (`text_similarity`, difflib): `minor_edit`, False, with no LLM call.
4. **Otherwise** the LLM reads a line diff (not both full pages) and classifies the change as `substantive` or `cosmetic`, writing a `change_summary`.

The 0.98 threshold was calibrated by reading diffs in each similarity band:
- At 0.98 and above, the edits were figure updates and capitalization only ("121,000 → 120,300 employees").
- Between 0.90 and 0.98, real values edits remained. MPC 2020→21 dropped "We aim for an accident-free, incident-free workplace" (similarity 0.947). JPM 2021→22 added a customer principle (0.941).

LLM calls cost fractions of a cent, so the threshold favors recall.

**Change prompt, version c2.** The first version labelled 75% of the diffs it saw as substantive, including rotating teasers. For example, BAC 2019 replaced an "Investing in women" teaser with a hunger-relief teaser. Version c2 defines **substantive** as a change to the page's own standing statements (mission, purpose, values, principles, commitments). Rotating featured content counts as **cosmetic** even when it mentions a value topic.

Result: 122 substantive, 89 cosmetic, 30 minor edits, 92 identical, 32 page switches and 50 first observations.

A random 12-call hand check of c2 agreed with 10 calls outright. The other two were borderline:
- F 2016→17: removal of an executive's stated commitment, labelled substantive.
- CVX 2019→20: reordering with one added phrase, labelled cosmetic.

### `analyst_notes`
`analyst_notes` gives at most 60 words per row on tone and framing:
- aspirational vs. factual;
- which stakeholder is addressed first;
- voice;
- hedged vs. absolute commitments;
- distinctive wording.

Together with `change_summary`, this is the per-year record of linguistic shifts.

### Model, reproducibility, cost
- **Model.** Claude Haiku 5.5 at effort `low`, with JSON constrained by a schema (`output_config.format`). Salience is an integer enum, because structured outputs do not support min/max.
- **Reproducibility.** Haiku 5.5 rejects `temperature`, so reproducibility comes from a cache. Every request is keyed by a SHA-256 of (model, effort, prompt version, task, system prompt, prompt, schema), and a rerun never re-queries. Each task has its own prompt version, so the change prompt could be revised without re-sampling the hand-checked theme coding. The token budget class is the same as Part 2's.
- **Cost.** About $0.55 for all 415 snapshots and 212 change calls.

### Pilot and hand check
The 10 pilot snapshots cover 5 values pages and 5 About pages. They were chosen for edge cases: a PDF (BRK.B), a card layout (XOM), a long principles page (JPM), a contact-only page (AAPL) and a teaser-heavy page (MS). The sheets are in `output/handcheck_sheet_p1v*.csv`.

Version p1v1 had two kinds of error.

Business description and chrome were coded as values:
- AAPL's "Visit an Apple Store" coded as `customers`.
- NVDA's "$100 trillion of industries" coded as `customers` and `shareholders`.
- BRK.B's headcount coded as `employees`.

Two evidence spans were silent paraphrases:
- JNJ: "We provide" instead of the Credo's "We must provide".
- BRK.B: "Charlie and I" instead of "Charlie Munger and I".

Version p1v2 fixed all of these, with 0 unverified spans. One residual, which I documented rather than kept tuning: MS 2024 `customers` cites a diversity sentence where "put clients first" was the better span.

### What the LLM step found about the scrape
Starbucks 2016 came back coded zero in every category. Its "mission statement" snapshot was actually a site error page ("We're sorry — something has gone wrong…"). The soft-404 check was gated on pages under 150 words, and this page had exactly 150. The check now matches the top of any page, and SBUX 2016 uses Starbucks' real About page.

The other 9 all-zero rows are genuine fact-sheet pages: AAPL 2016–17, ORCL 2017–18, JPM 2018 and VLO 2016–17 and 2019–20.

## Sample note
The firm list is used exactly as given. It does not exactly match GICS sectors as of January 2024:
- GOOGL and META have been in Communication Services since 2018.
- V and MA moved to Financials in 2023 but are absent from the list.

## Coverage and gaps

**415 of 450 company-years collected (92%).**
- 46 of 50 firms have at least 6 of 9 years; 40 have all 9.
- 168 rows are `values` pages and 247 are `about` pages.
- 29 rows were filled by approved discoveries across 9 firms.
- `coverage.csv` holds the full grid.

The 35 gaps, by reason:

| Reason | Company-years | Firms | What it means |
|---|---|---|---|
| Rejected: thin text | 17 | AVGO 6, EOG 6, LLY 3, NKE 2 | The archived HTML has under 40 visible words. Content is rendered by JavaScript, which `id_` raw captures do not execute. Example: AVGO 2021 is a 4.5 KB React shell with 0 visible words. |
| No captures in year | 8 | LOW 4, AVGO 1, BMY 1, CRM 1, PSX 1 | No candidate URL was archived that year. For LOW 2016 to 2019, `corporate.lowes.com` was not archived before 2020, and discovery found no older equivalent. |
| Rejected: redirect to unrelated page | 7 | AAPL 7 | From 2018 on, `apple.com/about/` redirects to `/sitemap/`. Apple has no About or values page; 2016 and 2017 are a contact page. |
| Rejected: redirect to homepage | 2 | PSX 2 | The About URL redirected to the homepage in 2023 and 2024. |
| Rejected: cross-type redirect | 1 | MCD 1 | The 2019 values URL redirected to a general page, and no About capture was available. |

Firms under 6 of 9 years:
- **AAPL (2/9).** There is no corporate About page to collect, which is itself a finding about how Apple presents itself.
- **AVGO (2/9)** and **EOG (3/9).** Their pages are JavaScript-rendered. A headless-browser pass would recover them.
- **LOW (5/9).** The corporate site is not archived before 2020.

Every gap has a row in `gap_log.csv`, and every capture tried has a row in `decision_log.csv`.

## Known limitations
- **Page type is URL-based.** An About page that carries a full values statement is labelled `about`.
- **Discovery recall.** A values page whose keyword appears only deep in the path is found only if a seed points into its directory.
- **The archive is uneven.** A page that existed but was not captured in a given year becomes a gap, or a fallback to another page.
- **Some content is invisible to us.** Sites rendered client-side by JavaScript, or content loaded after page load, may be thin in the raw `id_` HTML.
- **One snapshot per year** misses changes made within a year and reverted.
- **The salience coding comes from a single model.** It has no temperature control, and re-sampling can move a category by ±1; in the pilot, XOM 2018 innovation went from 1 to 2 between prompt versions. The cache freezes the published values, but inter-run reliability was not measured.
- **About pages carry residual teaser content.** Values pages do not have the same problem, so `page_type` should be a control in any cross-firm comparison.
- **The `change_type` boundary is a judgment call.** It separates a page's standing statements from rotating featured content, and borderline cases exist (see the hand check above).

## With more time
- Classify page type from content (an LLM or a small classifier) instead of the URL.
- Use `tldextract` for registrable domains (country-code TLDs at 500-firm scale).
- **Recover the JavaScript-rendered gaps (the 17 `thin_text` gaps: AVGO 6, EOG 6, LLY 3, NKE 2).** These pages exist in the archive, but their visible text is built by JavaScript in the browser, and the raw `id_` HTML holds only an app shell. AVGO 2021, for example, is 4.5 KB with 0 visible words. The fix:
  - Load the archived page, without `id_`, in a headless browser (Playwright, Chromium) so that its scripts run.
  - Wayback serves the archived script and API responses when they were captured; this often works for sites whose data calls were archived alongside the page.
  - Extract the text from the rendered DOM with the same extraction pipeline.

  Cost: a few seconds per page and a browser dependency, run only for `thin_text` gaps.
- Add a second snapshot per year (January and July) to detect within-year churn.
