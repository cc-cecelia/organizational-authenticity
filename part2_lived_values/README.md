# Part 2: Lived values (SEC proxy statements)

**Status:** data collection is complete for all 50 firms. The analysis has been
piloted on MSFT, JPM and XOM: the classical layer has run, the LLM layer is built
and dry-run, and the full run is pending.

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

## Analysis (pilot: MSFT, JPM, XOM)
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

### Layer 2: LLM extraction from targeted sections (`llm_extract.py`, `sections.py`)
- **Sections, not whole documents.** `sections.py` finds the CD&A and the
  shareholder-proposal section. It generates every heading-to-end-marker span
  and picks the longest valid CD&A, and the proposal span densest in proposal
  language. This handles tables of contents, cross-references, glossaries and
  pages rendered as single lines. If a CD&A heading is an image, the fallback
  uses the section's standard opening sentence (MSFT 2018). Pilot: CD&A found
  in 27/27 firm-years; proposals in 25/27 (MSFT 2017 and 2018 had none).
- **Tasks:** (a) every incentive-pay metric, with plan, stated weight (never
  inferred), weighted/modifier/holistic application, quantitative or
  qualitative, category, and evidence quote; (b) every shareholder proposal,
  with topic, category and the board's recommendation.
- **Model and determinism:** Claude Haiku 5.5 with schema-constrained JSON
  output and effort `low`. Haiku 5.5 rejects non-default `temperature`, so
  temperature 0 is not available. Each request is cached in `data/llm_cache/`
  under a SHA-256 of model + prompt version + prompts + schema + section text.
  Results are fixed once extracted, and a rerun costs nothing.
- **Cost:** about 0.8M input tokens for the pilot (about $0.10), roughly $1.50
  for all 50 firms.
- **Hand-check:** `--handcheck 10` samples 10 firm-years across firms into
  `handcheck_sheet.csv` for item-by-item verification against the source text.

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
- Proxy length and format changed a lot over 2016-2024 (more graphics,
  pay-versus-performance tables from 2023), which can move per-10k-word rates
  without any change in substance. Shares are less exposed to this.
