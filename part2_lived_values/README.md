# Part 2: Lived values (SEC proxy statements)

**Status:** data collection is complete for all 50 firms. Both analysis layers
have run on the MSFT, JPM and XOM pilot, and the LLM layer has been hand-checked on
10 firm-years (results below). The 50-firm run is pending.

**Coverage: 450 of 450 firm-years have a proxy.** 441 are clean and 9 are flagged
for review (listed below).

## What
For each of the 50 sample firms and each filing year 2016–2024, we retrieve the
company's definitive proxy statement from SEC EDGAR, save the raw filing, and
extract clean text for later text mining.

## How to run
```bash
source .venv/bin/activate
python part2_lived_values/src/download_proxies.py --tickers MSFT JPM XOM   # test subset
python part2_lived_values/src/download_proxies.py                          # all 50 firms
python part2_lived_values/src/package_text.py                              # compress text for the repo
```
A full run from an empty cache takes about 5 minutes and roughly 650 requests.
Set `EDGAR_USER_AGENT` to override the declared contact. Reruns are free:
SEC JSON, filing headers and raw documents are cached on disk.

## Code (`src/`)
| File | Role |
|---|---|
| `config.py` | Paths, sample window, SEC access policy, quality thresholds |
| `edgar_client.py` | Rate-limited HTTP client (declared User-Agent, max 8 req/s, retry/backoff, disk cache) |
| `cik_map.py` | Ticker → CIK via `company_tickers.json`, plus `data/cik_overrides.csv` |
| `filings_index.py` | Lists proxy filings from the submissions API, including paged history; reads SGML headers to identify the filer |
| `extract_text.py` | Raw HTML → clean text; classifies a proxy as annual or special meeting |
| `download_proxies.py` | Driver: download, extract, select one proxy per firm-year, log gaps |
| `package_text.py` | Writes the clean text to gzipped JSON Lines files per sector for the repo (each under 50MB) |

## Decisions and why
1. **Firm-year = calendar year of the filing date.** This matches Part 1, where
   each year is the About page as it stood in mid-year. A proxy filed in April
   2020 mainly reports on fiscal 2019, so every row also carries `filing_date`,
   `fiscal_year_end` and `fiscal_year_covered`, which lets Part 3 test a one-year
   lag. `fiscal_year_covered` is the most recent fiscal year ending before the
   filing date, named by the Compustat `fyear` rule: a fiscal year ending in
   June–December takes that calendar year, and one ending in January–May takes the
   prior year. So HD's year ending January 2024 is 2023, and MSFT's year ending
   June 2016 is 2016. The gap between filing year and fiscal year is 1 for every
   firm except MSFT (0), which files in October right after its June year end.
2. **Ticker → CIK uses SEC's current `company_tickers.json`, then a sanity check.**
   That file reflects today's tickers. We normalise `BRK.B` → `BRK-B`. We also
   flag any CIK whose earliest EDGAR filing is after 2016-01-01, because that
   means the ticker has moved to a new registrant. Fixes go in
   `data/cik_overrides.csv` with a written reason. Example: XOM now maps to
   *ExxonMobil Holdings Corp* (CIK 2115436, first filing July 2026). The
   2016–2024 proxies were filed by *Exxon Mobil Corp*, CIK 34088. A firm can also
   span several registrants, which are unioned:

   | Ticker | CIK(s) used | Why |
   |---|---|---|
   | XOM | 34088 | New holding company (2026) took over the ticker |
   | AVGO | 1649338 → 1730168 | Broadcom Pte. Ltd. (Singapore) until the 2018 US redomiciliation, then Broadcom Inc. |
   | BLK | 1364742 | New holding company (2024 GIP deal) took over the ticker; the original BlackRock, Inc. was renamed BlackRock Finance, Inc. |

   The automatic check flagged AVGO and BLK in the full run. XOM was found
   during the test. At 500 firms this stays a short manual-review list.
3. **Forms: DEF 14A, plus DEFC14A when the company itself filed it.** In a
   contested director election, the company's annual proxy is filed as DEFC14A.
   XOM 2021 (the Engine No. 1 proxy fight) would otherwise appear as a gap.
   Two kinds of DEFC14A appear in a firm's filing list that are not its own
   proxy:
   - A dissident's filing against the firm (Engine No. 1 at XOM, Icahn/Barberry
     at MCD, Starboard at BMY, Icahn at OXY, the Strategic Organizing Center at
     SBUX).
   - The firm's own solicitation at another company (Broadcom vs Qualcomm, 2018).

   So we read each DEFC14A's SGML header and accept it only when the registrant
   is both `FILED BY` and `SUBJECT COMPANY`. Company proxies selected this way:
   XOM 2021, MCD 2022, SBUX 2024.
   Amendments (`/A`) are logged but never selected: they range from one-page
   corrections to full restatements. Additional materials (DEFA14A) and
   third-party solicitations (PX14A6G, DFAN14A) are out of scope.
4. **One proxy per firm-year.** If a year has several eligible filings, prefer
   the annual-meeting proxy over special-meeting proxies (detected from the
   opening text), then take the earliest. Filings not selected stay in the
   manifest.
5. **Primary document only.** We take the document the submissions API marks as
   primary. If the text is under 5,000 words we flag the row (`ok_flagged`),
   because the body may sit in other files of the filing. Berkshire's proxies
   are genuinely short (10k–15k words), which is why the threshold is not
   higher. NVDA filed an 86-word notice as a separate DEF 14A in 2022, and it
   is correctly not selected.
6. **Text extraction** (`extract_text.py`):
   - We drop scripts, styles, `<head>` and the hidden inline-XBRL header, so
     XBRL facts don't leak into the text.
   - Data tables are flattened to one row per line (`cell | cell`) between
     `[TABLE]`/`[/TABLE]` markers. Tone and topic models can drop them;
     compensation-metric extraction can keep them.
   - Layout tables (one non-empty cell per row) are unwrapped back into prose.
   - We remove page furniture: bare page numbers, "Table of Contents" links, and
     running headers/footers. A running header is a line whose page number
     varies while the pattern repeats. Labels that repeat word for word, such
     as skills-matrix entries ("ethnic, gender, national, or other diversity")
     or "Board recommendation", are deliberately kept, because they are content.

## Outputs (`output/`)
| File | Grain | Contents |
|---|---|---|
| `cik_map.csv` | firm | CIK, how it was resolved, entity name, former names, earliest filing, `history_covers_window` |
| `filings_manifest.csv` | filing | Every DEF 14A / DEFC14A / amendment found: eligibility, filer, meeting type, text stats, `selected` |
| `proxy_coverage.csv` | firm × year | Panel skeleton: `status` (`ok` / `ok_flagged` / `gap`), `gap_reason`, `notes`, selected filing, file paths, word counts |
| `coverage_gaps.csv` | firm × year | Rows of `proxy_coverage.csv` that are not plain `ok` |
| `proxy_text/<sector>.jsonl.gz` | filing | Clean text of every extracted filing with its metadata and the `selected` flag. Read with `pd.read_json(path, lines=True)` |
| `download_log.txt` | run | Log of the last full run |

Gap reasons: `no_cik`, `cik_history_starts_after_window`,
`no_def14a_in_filing_year` (the notes give the nearest filing dates on each side,
to expose timing shifts), `only_amendment_in_year`, `only_special_meeting_proxy`,
`retrieval_failed`.

Raw filings (`data/raw/`, about 800MB), per-filing text (`data/text/`, about
150MB) and the API cache (`data/cache/`) are gitignored and can be rebuilt with
the commands above. The committed `proxy_text/` files hold the same text,
compressed (about 43MB in total).

## Coverage results (full run)
| Status | Firm-years |
|---|---|
| `ok` | 441 |
| `ok_flagged` | 9 |
| `gap` | 0 |

**Timing-shift rule (fills AAPL 2018).** Apple files its proxy in late December
or early January. Calendar 2017 therefore holds two annual proxies: 2017-01-06
(fiscal 2016) and 2017-12-27 (fiscal 2017, for the February 2018 meeting).
Calendar 2018 holds none. A narrow rule in `assign_panel_years()` moves a
December-filed annual proxy to the next year only when (a) its own year still
has another annual proxy and (b) the next year has no eligible filing at all.
It never displaces a filing and never empties a year. In this sample it fires
only for AAPL 2018. The row is flagged, and `filing_date` keeps the true date.

**Flagged rows (usable, but worth knowing about):**
| Firm-year | Why flagged |
|---|---|
| XOM 2021, MCD 2022, SBUX 2024 | Contested election: the company proxy is a DEFC14A, so its content is shaped by the proxy fight |
| TSLA 2018, TJX 2018, AVGO 2018 | A special-meeting proxy filed the same year was excluded (TSLA: March 2018 vote on the Musk CEO Performance Award; TJX: special meeting, Oct 2018; AVGO: redomiciliation scheme meeting) |
| AAPL 2018 | Timing shift: the 2017-12-27 proxy for the Feb-2018 meeting is assigned to 2018 (rule above) |
| NVDA 2022 | An 86-word notice was filed as a separate DEF 14A; the full proxy is selected |
| OXY 2019 | OXY's own DEFC14A responding to Icahn's consent solicitation (July 2019, not a meeting proxy) was not selected; the March annual proxy is |

## Lived-values panel (`output/lived_values_panel.csv`)
One row per firm-year (450 rows), keyed on `ticker` + `year` (proxy filing year,
the same convention as Part 1), for Part 3 to join. The full column definitions
are in the docstring of `src/build_panel.py`. In brief:

| Columns | Meaning |
|---|---|
| `pay_n_<category>`, `pay_n_other`, `pay_n_total` | Distinct pay-linked criteria (metrics plus named sub-criteria) that governed pay in the reported cycle, de-duplicated across plans and scopes |
| `pay_share_<category>` | Share of the nine stakeholder categories (`other` excluded); sums to 1, comparable with Part 1's shares |
| `fv_rate_<category>`, `fv_share_<category>` | Firm-voice dictionary rates per 10k words, and category shares |
| `prop_n_<category>`, `prop_n_total`, `prop_share_board_against` | Shareholder-proposal pressure |
| `flagged`, `flag_reason` | Filing-level flags from `proxy_coverage.csv` (contested election, timing shift, ...) |
| `cda_quality`, `pay_status`, `proposals_status` | Extraction quality: drop or check `length_outlier`/`missing` rows in sensitivity analyses |
| `cat_weight_<category>`, `cat_weight_other` | Share of the **annual incentive plan's** payout weight by category (sums to 1); see the weight layer below |
| `cat_weight_lti_<category>` | The same for the long-term incentive plan |
| `weight_source`, `weight_source_lti` | `disclosed` / `derived_from_stated_split` / `imputed_emphasis` / `none`: the weakest basis of any weighted criterion in the plan |
| `fiscal_year_covered`, `filing_date` | For a one-year-lag test |

## Analysis
Run order for all firms: `text_measures.py` → `plot_trends.py` → `llm_extract.py` → `build_panel.py`.
Both layers code text into the shared stakeholder taxonomy defined in the repo's
CLAUDE.md (customers, employees, dei, environment, community, shareholders,
integrity, safety, innovation; the definitions are mirrored in
`theme_dictionary.CATEGORY_DEFINITIONS`).

```bash
python part2_lived_values/src/text_measures.py --tickers MSFT JPM XOM     # layer 1
python part2_lived_values/src/plot_trends.py
python part2_lived_values/src/llm_extract.py --tickers MSFT JPM XOM --dry-run
python part2_lived_values/src/llm_extract.py --tickers MSFT JPM XOM --handcheck 10   # needs ANTHROPIC_API_KEY
```
Extra packages: `part2_lived_values/requirements.txt`.

### Layer 1: classical NLP on the full text (`text_measures.py`)
Scalable, transparent and free to rerun.
- **Seed dictionary** (`theme_dictionary.py`, exported to `output/analysis/theme_dictionary.csv`).
  Every term has a written rationale. Proxy machinery is excluded explicitly:
  bare "shareholder(s)" (procedural), bare "equity" (stock awards), "non-employee
  director", "Consumer & Community Banking", "safe harbor", "Black-Scholes",
  "Section 16(a) … reporting compliance". Lobbying and political-spending terms
  are coded `integrity` (they are disclosure and accountability proposals), not
  `community`. Matched terms were audited on the pilot before freezing.
- **Three texts per firm-year:** full proxy (`rate_*`), **firm voice** (`fv_rate_*`,
  the full proxy minus the shareholder-proposal section, whose text is largely
  written by proponents), and CD&A only (`cda_rate_*`, how the firm explains
  pay). Firm voice is the headline "say in the proxy" measure. It matters:
  XOM 2016 scores 100 per 10k words on environment in the full text, but only
  9 in its own voice, because the rest was proponents' climate text.
- **Shares** (`*share_*`): each category's share of all theme hits, a
  composition measure independent of length. This is the scale to compare
  with Part 1's About pages.
- **Tone:** Loughran-McDonald 1993-2025 (`lm_dictionary.py`; downloaded and
  checksum-verified, not redistributed). We report standard LM negative and net
  tone, plus `_adj` versions without proxy-procedural negatives (AGAINST,
  OPPOSITION, DISSIDENT, TERMINATION, FORFEITURE, CLAWBACK …). Those words track
  the number of proposals and the length of the pay tables, not tone. Without
  this adjustment, a firm's tone "worsens" whenever it receives more
  shareholder proposals.
- **Year trends:** `sector_year_trends.csv` (equal-weight firm means) and
  `figures/trends_firm_voice.png`, `figures/trends_cda.png`. Events
  (`events.py`) are drawn on the categories they are expected to move, at the
  first filing year after the event. That year is computed per firm from its
  own filing calendar in `firm_event_exposure.csv`, so MSFT's October proxies
  react in the same calendar year.

### Scaling the section finder from 3 to 50 firms
The pilot's heading rules did not generalise. On all 450 proxies they missed
the CD&A in 22 firm-years and left proposals outside the found section in 149.
Changes:
- **CD&A:**
  - Headings glued to their paragraph (ORCL), split over two lines (HAL),
    lower-cased by CSS (CVX) or replaced by an opening sentence (MPC) are now
    recognised.
  - A second pass with a lower minimum length catches Berkshire's 1k-word
    CD&A.
  - The best span is checked against the firm's own median CD&A length in its
    other years. Outside 0.5-1.8x, the closest candidate is used instead
    (16 firm-years, marked `median_adjusted`).
  - Result: 445/450 found; 19 remain length outliers and are flagged
    (`cda_quality`) rather than hand-tuned.
- **Proposals:** besides the heading-based section, every non-management
  `RESOLVED` clause, and the "supporting statement" / "proponent's statement"
  headings used by firms that paraphrase proposals, anchors a window (300 words
  before, 2,000 after, stopping at meeting-information headings). Overlapping
  windows are merged. Proposal text is found in 412/450 firm-years. The other 38
  contain no proponent statement at all; they are firms that received no
  proposals that year (e.g. EOG, NVDA, AVGO, TMO, LOW).

### Layer 2: LLM extraction from targeted sections (`llm_extract.py`, `sections.py`)
- **Sections, not whole documents.** `sections.py` finds the CD&A and the
  shareholder-proposal section. It generates every heading-to-end-marker span
  and picks the longest valid CD&A, and the proposal span densest in proposal
  language. This handles tables of contents, cross-references, glossaries and
  pages rendered as single lines. If a CD&A heading is an image, the fallback
  uses the section's standard opening sentence (MSFT 2018). Adjacent spans
  are chained, because sub-headings inside a board response can look like end
  markers. Pilot: CD&A found in 27/27 firm-years; proposals in 25/27 (MSFT 2017
  and 2018 had none). QA in `sections.csv`: every "RESOLVED" in the proxy
  except the say-on-pay resolution must fall inside the proposal section.
- **Tasks:**
  - (a) Every incentive-pay metric, with:
    - plan;
    - level: a metric, or a named sub-criterion under a holistic dimension;
    - stated weight, never inferred, and `weight_of` (plan total or parent
      component, because weights are often nested);
    - weighted / modifier / holistic application;
    - scope: all executives or CEO only;
    - category and an evidence quote.
  - (b) Every shareholder proposal, with topic, category and the board's
    recommendation.
- **Shared coding rules** (`theme_dictionary.CODING_RULES`, mirrored in
  CLAUDE.md) settle the ambiguous cases the hand check exposed: business-volume
  metrics, capital hurdles, pay equity, executive pay, governance and voting
  rights.
- **Which aggregate to use:** `llm_firm_year.csv` gives, per firm-year,
  - counts of pay-linked metrics and of named sub-criteria by category: the
    robust lived-values measure, verified in the hand check;
  - `aip_weight_share_*`: the annual-incentive weight by category. It is filled
    only when one scope's plan-total weights add up to about 100%, so 17 of 27
    pilot firm-years are empty. That is largely substantive: JPM and XOM decide
    pay holistically and state no weights;
  - proposal counts by category and the share the board opposed.
- **Model and determinism:** Claude Haiku 5.5 with schema-constrained JSON
  output and effort `low`. Haiku 5.5 rejects non-default `temperature`, so
  temperature 0 is not available. Each request is cached in `data/llm_cache/`
  under a SHA-256 of model + prompt version + prompts + schema + section text.
  Results are fixed once extracted, and a rerun costs nothing.
- **Cost and rate limits:** about 1.25M input and 0.09M output tokens per pilot
  run (about $0.17), so roughly $3 for all 50 firms. The account allows 80k output
  tokens per minute, and that limit is charged against `max_tokens` up front, so
  `max_tokens` is sized per task from observed outputs. A shared rolling token
  budget keeps workers under 80% of both limits; every wait is logged.

### Hand check (10 firm-years, `handcheck_results.csv`)
Sample: MSFT 2017, 2018, 2021; JPM 2016, 2020, 2023, 2024; XOM 2016, 2021, 2024
(seeded, spread across firms). Every item was read against the source section:
weights against the pay tables, proposals against the section's headings.
Evidence grounding was also measured for all items, as the share of each
quote's 4-word sequences found in the source.

| Round | Incentive items | Proposals | Main problems |
|---|---|---|---|
| v1 | ~88 items, several misses | 50/54 found | Named DEI/environment criteria under JPM's holistic dimensions missed (2023, 2024); XOM 2024 safety/emissions bundle coded `other` and peer scorecard missed; XOM 2016 long-term award listed 3 of 7 areas; JPM 2024 ROTCE weight inferred (100%); CEO-only weights unmarked; pay-equity and executive-pay proposals coded `employees`; **MSFT 2021: 4 of 5 proposals missed** (section-finder bug) |
| v2/v3 | 145 items, 4 errors (97.2%) | 54/54 found, 0 errors | 3 category inconsistencies (MSFT 2021 LinkedIn Sessions, MSFT 2021 CEO-row Product & Strategy, XOM 2024 parent bundle) and 1 paraphrased evidence quote |

Fixes between rounds: the section-finder bug (an "Additional Information"
sub-heading inside MSFT's board responses ended the section; spans are now
chained), the shared coding rules, sub-criterion extraction, the never-derive
weight rule, and the `scope` and `weight_of` fields. On v3, evidence grounding
for the sampled items averages 98.8%, and the round-1 failures are encoded as
regression checks. Item-level sheet: `handcheck_sheet_v3.csv`.

## Weight layer (`src/weight_layer.py`)
Most proxies do not fully disclose how much each criterion counts. Only 60 of
375 firm-years with annual-incentive criteria have fully disclosed weights
down to the last criterion. Counts of criteria treat a passing mention like a
50% metric. The weight layer gives every firm-year a weight vector. It is a
**separate pass**: it reads `incentive_metrics.csv` and never changes the
extraction or its cache. It has its own cache, `data/llm_cache_weights/`.

**One LLM call per firm-year, only where needed.** A call is made where some
tier lacks per-item weights (406 of 418 firm-years; the 12 flat, fully
weighted scorecards are handled in Python alone), plus the masking-test set.
- Input: the CD&A and the extracted item list (names, levels, categories,
  never the extracted weights).
- Output: each item's parent tier, an emphasis score (1 = listed in passing,
  2 = own description or rationale, 3 = called primary or key, or given the
  most space), and any tier whose split the text calls equal.
- Claude Haiku 5.5, schema-constrained JSON, cached by SHA-256 fingerprint.

All arithmetic is plain Python (`build_weights()`), so rules can change
without new API calls:
1. **Stated tiers first.** Top-level weights as disclosed. A tier's weight is
   always passed down to its sub-criteria: by stated child weights, else by a
   stated equal split, else by emphasis. Example: MSFT 2019-20 is 50%
   financial / 50% qualitative with stated thirds, so each qualitative
   dimension gets 16.67% (`derived_from_stated_split`). Each dimension's 16.67%
   then flows to the named criteria MSFT lists under it (e.g. Diversity and
   inclusion, Compliance and integrity, Customer satisfaction).
2. **Otherwise emphasis:** weight = emphasis / sum of emphasis within the
   tier × the tier's weight. Proportional normalisation, not softmax. Any
   undisclosed remainder of 100% is split this way.
3. **Refinement (imputed splits only):** if none of a tier's children shares
   the tier's own category, the tier keeps a residual share as an implicit
   sibling, scored with its own emphasis. The extraction lists *named*
   criteria, so children are often partial. JPM's "Client/Customer/Stakeholder"
   has a single extracted child, "Delivery on DEI commitments"; without the
   residual, its whole weight would move to `dei`. Stated splits are always
   passed down in full.
4. **Scope:** the union of all-executive and CEO-only rows, de-duplicated by
   name (the row with a stated weight wins). Many firms tag the scorecard
   `ceo` and the bonus formula `all`.

Result (annual incentive, 375 firm-years): 60 `disclosed`, 33
`derived_from_stated_split`, 282 `imputed_emphasis`. The 43 firm-years with
`none` have long-term criteria only. Average weight on shareholder
(financial) criteria is ~70% in every year. Environment rises from 0.4% (2016)
to ~4-5% (2022-24); Energy reaches 12% environment and 11% safety in 2024.

### Masking test (validation of the imputation)
Run on the 179 firm-years whose annual-incentive tier weights are fully
disclosed. **Leakage control:** the CD&A and the item names are redacted so
the answer cannot be read:
- every digit, and every spelled-out number or fraction word, becomes `#`;
- every word containing *weigh / equal / proportion / percent*, and "evenly",
  becomes `[w]`;
- every "%" sign is removed.

A first, looser redaction (digits only) was audited and failed: 26 of 180
documents still contained phrases like "fifty percent", and 155 contained
"equal". The strict version leaves **zero** such cues in all 180 documents audited.
Masked calls are cached separately; their fingerprint includes the redaction
version. Weights are rebuilt from the masked structure by (a) an equal split
within every tier and (b) emphasis. They are compared with the disclosed truth
at the deepest level where the truth is known (disclosed or derived from a
stated split), so tiers with unweighted named sub-criteria still count.

| MAE, percentage points | n | Equal split | Emphasis |
|---|---|---|---|
| Items with known weight | 789 | 10.21 | **9.56** |
| Categories carrying weight | 417 | 9.74 | **9.64** |
| Same, excluding shareholders | 240 | 9.08 | **8.91** |

Per firm-year, emphasis beats the equal split in 65, loses in 38 and ties in
76 (sign test p = 0.010). An equal split is exactly right in only 9%. (Rerun
after the JPM 2024 override below, which moved JPM 2024 out of the
fully-disclosed set.)

**Reading.** Emphasis is a modest but significant improvement at the item
level (-6% MAE). At the category level the gain is small (-1%), because most
errors move weight between criteria of the same category (e.g. two financial
metrics). It helps most when a dominant metric is plainly the focus of the text
(TJX 2019: true 80/20, equal 50/50, emphasis 75/25; MCD 2020 operating income
75%). It hurts when the text gives more space to a qualitative component than
its formal weight (SLB 2018 personal objectives; INTC 2021-22 "One Intel"
goals; IBM 2018 strategic-imperatives revenue at 20%). Per-firm examples:
`output/analysis/mask_test_examples.csv`.

**Use.** `cat_weight_*` with `weight_source == imputed_emphasis` carries
roughly ±10 pp item-level error. Part 3 should treat it as an approximation:
run sensitivity checks restricted to `disclosed` and
`derived_from_stated_split` rows, and prefer within-firm changes over
cross-firm levels.

## Manual extraction overrides (`data/extraction_overrides.csv`)
Documented corrections, applied by `llm_extract.py` after reading the cache,
so the model output and the cache stay untouched. Each override names the
value it expects to replace; if the extracted value differs, the run stops,
so a stale override never applies silently. Every application is logged.

| Firm-year | Correction | Why |
|---|---|---|
| JPM 2024 | "Risk, Controls & Conduct": weight 50% → none, `weight_of` plan_total → none, application weighted → holistic_factor | The source says "an approximately 50% weighting to its qualitative consideration of risk, controls & conduct, customer/client/stakeholder and teamwork & leadership": the 50% covers the three dimensions together. Attaching it to one dimension gave the other two, and their DEI, environment and customer criteria, 0%. After the fix the weight layer splits the 50% across the three by emphasis: DEI 12.5% (was 0%). Found in the Part 4 review; a scan of all firm-years found no other instance. |

## Out-of-sample extension: filing years 2025-2026
`P2_EXTENSION=2025_2026` runs the unchanged pipeline (same rules, CIK
overrides and flags) on filing years 2025-2026 and writes everything to
`output/extension_2025_2026/`. The 2016-2024 panel and Part 3's inputs are
untouched. Purpose: Part 4's timing test, because 2023-2024 filings report pay
plans designed before the June 2023 SFFA ruling.

```bash
export P2_EXTENSION=2025_2026
python part2_lived_values/src/download_proxies.py
python part2_lived_values/src/text_measures.py
python part2_lived_values/src/llm_extract.py --tasks incentives
```
- Coverage: 98 of 100 firm-years. MSFT 2026 (files in late October) and TSLA
  2026 had not been filed when the SEC filing lists were cached
  (2026-10-19). Flagged: SLB 2025 (special-meeting proxy excluded) and PSX
  2025 (contested election, DEFC14A).
- BLK: the 2024 holding-company reorganisation moved proxy filing to the new
  BlackRock, Inc. (CIK 2012383) from 2025. It is now part of BLK's CIK chain;
  it has no definitive proxy before 2025, so the 2016-2024 panel is unchanged.
- The CD&A length guard needs a firm's other years, so with two years it is
  inactive in the extension.

## Known limitations
- `company_tickers.json` is a current snapshot. Ticker reuse or registrant changes
  need the override file; the sanity check catches only registrants created after 2016.
- `fiscal_year_covered` uses each registrant's *current* fiscal year end, so a firm
  that changed its year end inside the window would be off by one for some years.
  None did in this sample.
- Meeting-type detection is a keyword heuristic over the first 20k characters.
  It is used only to break ties.
- Running-footer removal is conservative. Footers that never say "proxy
  statement" and appear fewer than 20 times stay in the text as minor noise.
- Text and graphics inside images (infographics, pay-mix charts) are not
  captured.
- Dictionary rates measure emphasis (how much a firm talks about a stakeholder),
  not commitment or sentiment toward it. "We oppose this DEI proposal" still
  counts as dei language. The LLM layer's board-recommendation field partly
  addresses this for proposals.
- LLM category coding is reliable for clear cases but leans on the coding rules
  at the margins. The remaining errors are category inconsistencies, not
  invented items. Holistic-assessment firms produce long lists of named
  criteria, so count measures should be compared within firm over time rather
  than across firms in levels.
- Proxy length and format changed a lot over 2016-2024 (more graphics,
  pay-versus-performance tables from 2023), which can move per-10k-word rates
  without any change in substance. Shares are less exposed to this.
