# Part 2: Lived values (SEC proxy statements)

**Status:** data collection is complete for all 50 firms. The analysis is not built yet.

**Coverage: 449 of 450 firm-years have a proxy.** 440 are clean and 9 are flagged
for review. The only gap is AAPL 2018, a filing-timing artefact explained below.

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
| `ok` | 440 |
| `ok_flagged` | 9 |
| `gap` | 1 |

**The one gap: AAPL 2018.** Apple files its proxy in late December or early
January. Calendar 2017 therefore contains two annual proxies: 2017-01-06 (fiscal
2016) and 2017-12-27 (fiscal 2017, for the February 2018 meeting). Calendar 2018
contains none. Under the filing-year rule this is a true gap, not missing data.
The Dec-2017 filing is in the manifest and in `proxy_text/` (`selected = false`).

**Flagged rows (usable, but worth knowing about):**
| Firm-year | Why flagged |
|---|---|
| XOM 2021, MCD 2022, SBUX 2024 | Contested election: the company proxy is a DEFC14A, so its content is shaped by the proxy fight |
| TSLA 2018, TJX 2018, AVGO 2018 | A special-meeting proxy filed the same year was excluded (TSLA: March 2018 vote on the Musk CEO Performance Award; TJX: special meeting, Oct 2018; AVGO: redomiciliation scheme meeting) |
| AAPL 2017 | Two annual proxies in one year (see the gap above); the earlier one is selected |
| NVDA 2022 | An 86-word notice was filed as a separate DEF 14A; the full proxy is selected |
| OXY 2019 | OXY's own DEFC14A responding to Icahn's consent solicitation (July 2019, not a meeting proxy) was not selected; the March annual proxy is |

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
