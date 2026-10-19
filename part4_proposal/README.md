# Part 4: After the backlash, did firms retreat in what they say, what they do, or both?

**Status:** exploratory. 50 firms, two themes (DEI and environment), filing
years 2016-2026. Everything here reads other parts' outputs; nothing in
Parts 1-3 is modified. Inputs as committed: Part 2 `8008c55` (panel and
2025-2026 extension) and Part 3 `b4f9bc5`.

## Motivation
From mid-2023, US companies faced a sharp turn against DEI and ESG: the SFFA
ruling (June 2023), state anti-ESG laws and activist pressure. A common claim
is that firms went quiet without changing course ("greenhushing" or quiet
retention). Parts 1-3 measure what a firm says (its About/values page and its
proxy narrative) and what it pays executives for (incentive-plan criteria and
weights) on the same stakeholder taxonomy. That makes the claim testable. If
firms only went quiet, talk should fall while pay-linked criteria hold.

## Headline
**The early retreat from DEI happened in proxy language, not on websites and
not (at first) in pay.**
- Websites did not retreat. The share of About/values pages emphasizing DEI
  rose from 22% (2016) to 41% (2022) and was still 40% in July 2024, a year
  after SFFA (Part 1).
- Proxies did. DEI language in proxy statements fell from 2024.
- Pay did not move at first. DEI pay criteria rose in the 2023-2024 proxies,
  which looked like quiet retention. The out-of-sample 2025-2026 filings show
  this was mostly timing: once the pay plans designed after the backlash
  appear, explicit DEI criteria largely leave pay too.
- What replaced them is ambiguous. Most firms put a generic people/culture
  goal in their place. That is a **label retreat with unknown substance**, not
  a demonstrated retreat.

### The argument in four steps
1. **Hypothesis: quiet retention.** After the 2023 backlash, firms cut DEI
   talk but kept DEI in executive pay. The 2023-2024 data fit: DEI pay criteria
   rose from 16 to 25 firm-years while DEI proxy language stalled and then fell.
   At firm level, 5 firms cut only talk and none cut only pay.
2. **Confound: the pay calendar.** A proxy filed in year t reports pay for
   fiscal t-1, usually designed early in t-1. The 2023-2024 filings therefore
   describe plans set *before* the June 2023 SFFA ruling, while websites are
   mid-year snapshots. Sticky pay could be pure measurement lag.
3. **Out-of-sample test.** We collected the 2025-2026 filings (fiscal
   2024-2025 plans, designed after SFFA) with the unchanged pipeline. DEI pay
   criteria fall to 9 and then 3 firm-years, and 11 of the 17 firms that had
   both before now cut both talk and explicit DEI pay criteria.
4. **Revised conclusion.** Quiet retention in its strong form (same DEI
   criteria, less talk) does not survive. What remains is:
   - a **channel ordering:** proxy language moved first, websites had not moved
     by mid-2024, and pay criteria moved one to two cycles later;
   - an **open question:** most departing DEI criteria were replaced by generic
     people/culture goals. That could be genuine removal or the same substance
     under a safer label, which would itself be quiet retention, and our data
     cannot tell the two apart.

| DEI, all 50 firms | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| Firm-years with a pay-linked DEI criterion | 10 | 16 | **25** | **23** | **9** | **3** |
| Proxy firm-voice DEI language (hits per 10k words) | 20.3 | 21.2 | 21.3 | 16.7 | 6.4 | 4.7 |
| About/values page DEI salience (0-3, mean) | 1.00 | 1.09 | 1.11 | 1.11 | n/a | n/a |

| Environment | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| Firm-years with a pay-linked environment criterion | 14 | 16 | 26 | 24 | 17 | 15 |
| Proxy firm-voice environment language | 17.2 | 24.7 | 25.2 | 23.7 | 18.1 | 13.9 |
| Page environment salience (0-3) | 0.74 | 0.93 | 0.98 | 0.96 | n/a | n/a |

Website channel in more detail (Part 1, About/values pages):

| Pages, DEI | 2016 | 2019 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|
| Share emphasizing DEI (salience ≥ 2) | 22% | 31% | 37% | 41% | 41% | 40% |
| Share mentioning DEI at all (salience ≥ 1) | 33% | 44% | 48% | 59% | 59% | 60% |

Figure: `output/figures/say_vs_do_trends.png` (each series indexed to its
2021-2022 mean, with Part 2's event markers). Data: `output/say_do_trends.csv`.

## Data and method
- **Say:**
  - Part 1 page salience (`sal_dei`, `sal_environment`, 0-3; mid-year
    Wayback snapshot; 2016-2024).
  - Part 2 proxy firm-voice dictionary rate (`fv_rate_*`, hits per 10,000
    words, with shareholder-proposal text removed; 2016-2026).
- **Do:** Part 2 pay-linked criteria.
  - Presence: at least one criterion in the category, hand-checked at 97%
    item accuracy.
  - `cat_weight_*`: annual-incentive weight share.
- **Out-of-sample years (2025-2026):** Part 2's extension, i.e. the same
  pipeline, rules and overrides run on filing years 2025-2026 (98 of 100
  firm-years). These years have no page side (no Wayback pass) and no weight
  layer.
- **Quadrants** (`src/say_do.py`): each firm's 2021-2022 average is compared
  with its 2023-2024 average.
  - Say is **cut** if page salience falls ≥ 0.5 points or firm voice falls
    ≥ 25%, with neither rising.
  - Do is **cut** if the criterion disappears in at least one post year
    (share of years with it falls ≥ 0.5), or its weight falls ≥ 50%. Weights
    count only where disclosed or derived from a stated split: imputed weights
    carry ~10 pp error (Part 2 masking test), and an extraction slip once
    zeroed JPM 2024's DEI weight.
  - **Eligible** firms had the theme in both say and pay in 2021-2022;
    everyone else had nothing to cut.
  - Specifications:
    - `main`: as above.
    - `lag`: pay by fiscal timing (2022 vs 2024 filing).
    - `imputed_weights`: imputed weights allowed to vote.
    - `ext`: 2021-2022 vs **2025-2026**, say = firm voice only.
- **Complement:** Part 3's `unstated_backing` (pay-linked category not stated
  on the page), computed per theme.

## Findings

### 1. 2023-2024: quadrants consistent with quiet retention (supporting evidence)
DEI, 17 of 50 firms eligible:

| Sector | Kept both | Cut say only | Cut do only | Cut both | Conflict |
|---|---|---|---|---|---|
| Consumer Discretionary | 3 | 1 | 0 | 0 | 0 |
| Energy | 3 | 0 | 0 | 0 | 1 |
| Financials | 1 | 2 | 0 | 1 | 0 |
| Healthcare | 2 | 0 | 0 | 0 | 0 |
| Technology | 1 | 2 | 0 | 0 | 0 |
| **All** | **10** | **5** | **0** | **1** | **1** |

- Kept both: ABBV, COP, JNJ, JPM, MSFT, NKE, SBUX, SLB, TGT, VLO.
- Cut say only: BLK, GS, IBM, INTC, MCD.
- Cut both: WFC.
- Conflict: MPC (page salience fell, proxy DEI language rose).

Say-only cuts outnumber pay-only cuts 5 to 0 (lag specification 6 to 0;
imputed weights 5 to 0). The evidence is thin. Each say-only cut rests on
one of the two say measures. GS, IBM and MCD sit exactly at the 0.5-point
threshold, and GS switched page type. BLK and INTC are cut only in proxy
language.

Environment, 18 eligible: 15 kept both (all 9 Energy firms among them); cut
say only BLK and INTC; cut do only ABBV.

Part 3's complement points the same way. Among firm-years paying for DEI, the
share whose page does not mention DEI rose from 19% (2022) to 30% (2023) and
38% (2024). Part of this is composition: firms that newly adopted DEI pay
criteria may not have updated their pages. For environment the same share
went 13% (2022), 27% (2023), 30% (2024).

### 2. The timing test reverses the reading
A proxy filed in year t reports pay for fiscal t-1, usually designed early in
t-1. The 2023 and 2024 filings therefore reflect plans set before the June 2023
SFFA ruling, while pages are mid-year snapshots. So sticky pay could simply be
measurement lag. The 2025-2026 filings (fiscal 2024-2025 plans, designed after
SFFA) test this directly.

| 2021-22 vs 2025-26 (`ext`) | Kept both | Cut say only | Cut do only | Cut both |
|---|---|---|---|---|
| DEI (17 eligible) | 1 | 5 | 0 | **11** |
| Environment (18 eligible) | 5 | 8 | 2 | 3 |

- DEI cut both: BLK, GS, INTC, JNJ, JPM, MCD, MPC, NKE, TGT, VLO, WFC.
  Only ABBV kept both.
- Environment retreats mainly in talk (cut say only: BLK, COP, CVX, MSFT,
  OXY, PSX, SBUX, WFC). Pay-linked environment criteria fall only modestly
  (26 → 15 firm-years), and ABBV, JNJ, SLB, VLO and XOM keep both.

The out-of-sample collapse is not an extraction artifact. Median CD&A length
(about 9.7-10k words) and criteria per firm-year (10-12) are flat from 2021 to
2026, and `employees` criteria hold steady (29 → 32 → 26).

### 3. How explicit DEI left pay: label retreat, substance unknown
Of the 23 firms with a pay-linked DEI criterion in 2024, by their latest
2025-2026 filing (`output/dei_pay_exits.csv`):
- **13 replaced the explicit DEI goal with a generic people/culture/talent
  goal** (AXP, BLK, GS, HAL, IBM, INTC, JNJ, JPM, MCD, NKE, TGT, VLO, WFC).
  Examples:
  - AXP keeps "Talent Retention" and "Culture" and drops "Diversity
    Representation".
  - HAL replaces four diversity targets with "workforce localization".
  - GOOGL's ESG-bonus social component was "progress toward our DEI goals" in
    the 2023 proxy and "design and build products for a global audience" in
    2024.
- **5 dropped DEI with no people goal left** (AAPL, COP, CRM, MDT, PFE).
- **5 kept an explicit DEI criterion** (ABBV, MSFT, SBUX, SLB, TMO). MSFT and
  SBUX are judged on their 2025 filing only. TMO's "culture of diversity,
  involvement and inclusion" became "culture of involvement and inclusion".

**The 13 are not counted as a clear retreat.** The DEI *label* is gone. What
the replacement goal measures is unknown: it could be a genuine removal of the
DEI objective, or the same representation and inclusion targets under a safer
name, which would be quiet retention in a new form. The criterion names and
CD&A narrative we extract cannot separate the two.

**What would resolve it:** the metrics behind the replacement goals, if later
proxies disclose them. For example:
- representation or promotion targets by group inside a "talent" goal;
- a belonging or inclusion index inside a "culture" score;
- the same scorecard targets reported under a new heading.

Also useful: comparing the replacement goals' weight and payout outcomes with
the DEI goals they replaced, and the firms' EEO-1 or human-capital disclosures.
Until then, only the 5 outright drops are an unambiguous retreat in pay.

### Reading
The channels moved in a clear order:
1. **Proxy language moved first:** DEI firm voice fell in 2024 and collapsed
   in 2025-2026.
2. **Websites had not moved by July 2024:** 40% of pages still emphasized DEI.
3. **Pay criteria moved last,** one to two proxy cycles later, as the design
   calendar predicts.

Quiet retention in its strong form, keeping the same DEI criteria while saying
less, does not survive the out-of-sample test. A weaker form remains possible
and untested: the substance may live on in the generic people goals that
replaced DEI criteria at 13 of 23 firms. Environment differs. Pay-linked
environmental criteria declined only modestly while talk fell more. Of the
five firms that keep both (ABBV, JNJ, SLB, VLO, XOM), three are in Energy, the
closest thing to genuine quiet retention in this sample.

## Threats to validity
1. **Short window and small sample.** Two post years, 50 firms, and 17-18
   eligible firms per theme. Quadrant counts of 0-5 are anecdotal; no test
   statistics are reported for them.
2. **Timing:** a proxy filed in year t reports fiscal t-1 pay, designed early
   in t-1. This is the main confound for the 2023-2024 result, and the reason
   for the 2025-2026 test. Even 2025 filings mix plans designed in late 2023
   and early 2024, and 2026 has two missing filings (MSFT, TSLA not yet filed
   when the filing lists were cached on 2026-10-19).
3. **Page type switches.** Part 1 falls back from a values page to a general
   About page in some years, and page type is URL-based. A salience change can
   reflect which page was available (GS switched within the window).
4. **No page side after 2024.** The 2025-2026 say side is proxy firm voice
   only, a narrower and more procedural text than the values page.
5. **Imputed weights.** 282 of 375 weighted firm-years rest on emphasis
   imputation (~10 pp item-level error). Weights therefore only vote where
   disclosed or derived; the do side is mostly presence.
6. **Labels, not substance.** "Relabeled" means the explicit DEI wording left
   the criterion; it says nothing about what the new goal measures (see
   finding 3). Category coding at the margin also matters: "inclusive culture"
   can be coded `employees` or `dei`. The criteria are listed in
   `dei_pay_exits.csv` so each case can be judged.
7. **Dictionary rates measure emphasis, not stance.** "We oppose this DEI
   proposal" counts as DEI language; firm voice excludes proposal text, which
   limits this.
8. **Website channel.** "Websites had not retreated" is measured on one
   mid-year snapshot of one page per firm (Part 1). A retreat on other pages,
   or after July 2024, would not be seen.

## With more time
- Run the Wayback pass for 2025-2026, so the say side keeps its page measure.
- Add 2027 filings (fiscal 2026 plans, the first fully post-backlash design
  cycle) when available.
- Code criterion wording with an explicit "DEI term present" flag, to measure
  relabeling directly rather than through the category.
- For the 13 firms that replaced DEI goals with people/culture goals, extract
  the underlying metrics, weights and payouts of the replacement goals from
  later proxies, and match them to EEO-1 and human-capital disclosures. This
  would separate removal from relabeling.
- Extend to all 500 firms. The pipeline needs no changes, and the quadrant
  counts would become testable.

## Files
| File | Contents |
|---|---|
| `src/say_do.py` | Firm-year table, quadrant classification (4 specifications), DEI pay exits |
| `src/plot_say_do.py` | Say-vs-do trend figure |
| `output/say_do_firm_year.csv` | One row per firm × year × theme, 2016-2026 |
| `output/quadrants.csv` | One row per firm × theme × specification, with every per-measure verdict |
| `output/quadrant_counts.csv` | Counts by theme, specification, sector |
| `output/dei_pay_exits.csv` | 2024 DEI-paying firms and what their latest plan does |
| `output/say_do_trends.csv`, `output/figures/say_vs_do_trends.png` | Year trends |

Run: `python part4_proposal/src/say_do.py && python part4_proposal/src/plot_say_do.py`
(needs Part 2's `extension_2025_2026` outputs for the out-of-sample years).
