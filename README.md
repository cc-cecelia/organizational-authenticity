# Organizational Authenticity: do large companies pay for what they say they value?

## Research question and design
Companies publicly state what they value, and they separately decide what their executives are paid to deliver. This project measures the alignment between the two for 50 large S&P 500 companies (10 per sector across Technology, Financials, Healthcare, Consumer Discretionary and Energy) from 2016 to 2024, with methods built to scale to all 500 firms.

The design pairs a **say** side with a **do** side, coded into one shared stakeholder taxonomy derived from stakeholder theory (Freeman 1984). The nine categories are customers, employees, DEI, environment, community, shareholders, integrity, safety and innovation.
- **Say:** the companies' archived About and values pages, one per year, recovered from the Wayback Machine.
- **Do:** the criteria that executive incentive pay is tied to, read from each year's SEC proxy statement (DEF 14A).

The Organizational Authenticity Index then asks, firm by firm and year by year: **of what a company emphasizes on its values page, how much is also something its executives are paid to deliver?**

## Repository map
| Folder | Contents | Headline finding |
|---|---|---|
| `data/` | `companies.csv` (the 50-firm sample, domains, seed URLs); `discovery_review.csv` (reviewed candidate pages) | |
| `part1_stated_values/` | Wayback scraper, text extraction, LLM theme coding (`src/`); one row per company-year with theme salience, verbatim evidence, change detection and tone notes (`output/stated_values.csv`); per-firm shifts (`output/linguistic_shifts.csv`) | Between 2016 and 2024, values pages broadened (DEI, employees, environment, community and safety up; shareholders down). 43 of 50 firms substantively rewrote their stated values, and DEI emphasis had not retreated by mid-2024. |
| `part2_lived_values/` | EDGAR proxy downloader, classical text measures, LLM extraction of pay criteria and shareholder proposals, weight layer (`src/`); firm-year panel (`output/lived_values_panel.csv`); 2025 to 2026 extension | Executive pay stays about 70% financial. Environmental and DEI criteria became common (environment in 6% of firm-years in 2016, about half by 2023 to 2024) but carry only about 3% to 5% of bonus weight. |
| `part3_authenticity_index/` | Index construction and analysis (`src/`); firm-year index with per-category inputs (`output/authenticity_index.csv`); distribution, sensitivity, robustness and validity results and figures (`output/analysis/`, `output/figures/`) | The typical firm backs about two-fifths of its stated emphasis with executive pay (mean 0.42; 0.34 when a value must carry at least 10% of the bonus). The ratio stayed flat from 2016 to 2024 because pages broadened as pay did. Rankings are driven by pay philosophy and sector. |
| `part4_proposal/` | Say vs do after the 2023 DEI backlash, with an out-of-sample timing test on 2025 to 2026 proxies | Proxies went quiet on DEI first, websites had not by mid-2024, and pay followed one to two years later. Explicit DEI pay goals fell from 23 companies (2024) to 3 (2026), mostly replaced by broader people or culture goals. |

Each part has a `README.md` (methods, decisions, coverage, limitations, what we would do with more time) and a `SUMMARY.md` for non-technical readers.

## How to reproduce

### Setup
Python 3.9+, from the repository root:
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt \
    -r part2_lived_values/requirements.txt -r part3_authenticity_index/requirements.txt
```

**Environment variables:**
- `ANTHROPIC_API_KEY`: needed only for steps that call the LLM *and* miss the cache. Put it in a `.env` file at the repo root (gitignored); the scripts load it.
- `EDGAR_USER_AGENT` (optional): the contact SEC EDGAR requires in the User-Agent; Part 2 has a default.
- `P2_EXTENSION=2025_2026` (optional): runs Part 2's pipeline on the 2025 to 2026 proxies.

**All LLM calls** use Claude Haiku 5.5, with JSON constrained by a schema, and are cached by a SHA-256 fingerprint of the full request. A rerun never re-queries, so published results are fixed. The model has no temperature control, so re-querying after the cache is cleared can shift individual codes slightly.

### What runs where
| Step | Command | Needs | Cost |
|---|---|---|---|
| Part 3: index, analysis, figures | `python part3_authenticity_index/src/build_index.py && python part3_authenticity_index/src/analyze.py` | Committed outputs of Parts 1 and 2 only | **Offline**, free |
| Part 4 | `python part4_proposal/src/say_do.py && python part4_proposal/src/plot_say_do.py` | Committed outputs of Parts 1 to 3 | **Offline**, free |
| Part 1: per-firm shifts | `python part1_stated_values/src/linguistic_shifts.py` | `stated_values.csv` | **Offline**, free |
| Part 1: scrape | `python part1_stated_values/src/scrape.py` (then optionally `discover.py --from-gaps`) | Network (Wayback Machine). The raw HTML cache is gitignored. | Free; about 1 to 2 hours first run (polite rate limit), discovery several hours |
| Part 1: LLM coding | `python part1_stated_values/src/llm_analyze.py` | API. The Part 1 LLM cache is gitignored. | About $0.6 from an empty cache (854 calls) |
| Part 2: proxies | `python part2_lived_values/src/download_proxies.py` | Network (SEC EDGAR). Rebuilds the per-filing text the LLM steps read. | Free; about 5 minutes |
| Part 2: text measures, panel | `text_measures.py`, `plot_trends.py`, `build_panel.py` | Proxy text | Offline, free |
| Part 2: LLM extraction and weights | `llm_extract.py`, `weight_layer.py` | API, but the **caches are committed** (1,864 responses), so a rerun after `download_proxies.py` makes no API calls | $0 with the committed cache; about $3.0 (extraction) and $2.2 (weights) from an empty one |

The exact run order and flags for each part are in that part's README.

## Data sources and coverage
| Source | Used for | Coverage |
|---|---|---|
| Internet Archive Wayback Machine (CDX API, raw `id_` captures) | About and values pages, one capture per year nearest July 1 | 415 of 450 company-years (92%). Every gap is logged with its reason, mainly JavaScript-rendered pages, plus Apple, which has no values page. |
| SEC EDGAR (submissions API, DEF 14A filings) | Executive pay criteria and weights, shareholder proposals, proxy language | Proxies for 450 of 450 firm-years (441 clean, 9 flagged); CD&A sections extracted for 445 of 450, of which 419 list pay criteria. Extension: 98 of 100 firm-years for 2025 to 2026. |
| Part 3 index (derived) | Say vs do alignment | 384 of 450 firm-years across 48 firms (Apple has no values page; Berkshire ties no executive pay to performance criteria) |

The sample is the 50 firms specified by the assignment, used as given. It does not exactly match GICS sectors as of January 2024: GOOGL and META have been in Communication Services since 2018, and V and MA moved to Financials in 2023 but are absent.

## Use of AI tools
The code was developed with Claude Code as a coding assistant under my direction. All design decisions, the taxonomy, the index definition and the interpretations were reviewed and decided by me. LLM extraction outputs were hand-checked as documented in each part's README.
