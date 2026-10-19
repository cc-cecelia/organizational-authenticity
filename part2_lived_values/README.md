# Part 2: Lived values (SEC proxy statements)

**Status:** data collection only. The analysis is not built yet.

## What
For each of the 50 sample firms and each filing year 2016–2024, we retrieve the
company's definitive proxy statement from SEC EDGAR, save the raw filing, and
extract clean text for later text mining.

## How to run
```bash
source .venv/bin/activate
python part2_lived_values/src/download_proxies.py --tickers MSFT JPM XOM   # test subset
python part2_lived_values/src/download_proxies.py                          # all 50 firms
```
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

## Decisions and why
1. **Year = calendar year of the filing date.** A proxy filed in April 2020 mainly
   describes fiscal 2019. We keep filing year as the panel key and store
   `filing_date` and `report_date`, so the panel can be re-keyed by fiscal year.
   MSFT is the clearest case: it files in October, after a June fiscal year end.
2. **Ticker → CIK uses SEC's current `company_tickers.json`, then a sanity check.**
   That file reflects today's tickers. We normalise `BRK.B` → `BRK-B`. We also
   flag any CIK whose earliest EDGAR filing is after 2016-01-01, because that
   means the ticker has moved to a new registrant. Fixes go in
   `data/cik_overrides.csv` with a written reason. Example: XOM now maps to
   *ExxonMobil Holdings Corp* (CIK 2115436, first filing July 2026). The
   2016–2024 proxies were filed by *Exxon Mobil Corp*, CIK 34088. At 500 firms
   this stays a short manual-review list.
3. **Forms: DEF 14A, plus DEFC14A when the company itself filed it.** In a
   contested director election, the company's annual proxy is filed as DEFC14A.
   XOM 2021 (the Engine No. 1 proxy fight) would otherwise appear as a gap.
   Dissidents also file DEFC14A under the target's CIK, so we read each
   DEFC14A's SGML header and accept it only if `FILED BY` is the registrant.
   Amendments (`/A`) are logged but never selected: they range from one-page
   corrections to full restatements. Additional materials (DEFA14A) and
   third-party solicitations (PX14A6G, DFAN14A) are out of scope.
4. **One proxy per firm-year.** If a year has several eligible filings, prefer
   the annual-meeting proxy over special-meeting proxies (detected from the
   opening text), then take the earliest. Filings not selected stay in the
   manifest.
5. **Primary document only.** We take the document the submissions API marks as
   primary. If the text is under 10,000 words we flag the row
   (`ok_flagged`), because the body may sit in other files of the filing.
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

Gap reasons: `no_cik`, `cik_history_starts_after_window`,
`no_def14a_in_filing_year` (the notes give the nearest filing dates on each side,
to expose timing shifts), `only_amendment_in_year`, `only_special_meeting_proxy`,
`retrieval_failed`.

Raw filings (`data/raw/`), clean text (`data/text/`) and the API cache
(`data/cache/`) are gitignored and can be rebuilt with the command above.

## Known limitations
- `company_tickers.json` is a current snapshot. Ticker reuse or registrant changes
  need the override file; the sanity check catches only registrants created after 2016.
- Meeting-type detection is a keyword heuristic over the first 20k characters.
  It is used only to break ties.
- Running-footer removal is conservative. Footers that never say "proxy
  statement" and appear fewer than 20 times stay in the text as minor noise.
- Text and graphics inside images (infographics, pay-mix charts) are not
  captured.
