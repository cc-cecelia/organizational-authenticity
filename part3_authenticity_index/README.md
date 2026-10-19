# Part 3: Organizational Authenticity Index

**Status: full run.** The index is built on Part 2's full `lived_values_panel.csv` (commit `f098411`, which includes the JPM 2024 weight correction). For page-year 2024 it also uses the 2025 proxies from Part 2's out-of-sample extension. The primary index covers **384 of 450 firm-years across 48 firms**. To reproduce:

```
.venv/bin/pip install -r part3_authenticity_index/requirements.txt
.venv/bin/python part3_authenticity_index/src/build_index.py   # -> output/authenticity_index.csv
.venv/bin/python part3_authenticity_index/src/analyze.py       # -> output/analysis/, output/figures/
```

## The index in plain words
A company's About or values page states what it values, and some values get more prominence than others (Part 1). Its proxy statement shows what the board actually pays executives to deliver (Part 2).

**The index asks: of everything the company emphasizes on its values page, what share does executive pay also reward?**
- A score of 1 means every value the page states is tied to at least one pay criterion.
- A score of 0 means none is.
- Values the page states more prominently count for more.

In technical terms, the index is a **salience-weighted recall** of stated values against pay-linked criteria:
- *Recall*: how many of the stated values are found again in pay.
- *Salience-weighted*: a headline value counts three times as much as a passing mention.

**The parameter τ is a materiality threshold.** It sets how much of the pay plan a value needs before it counts as fully backed:
- With τ close to 0 (the primary version), one pay criterion anywhere in the plan is enough.
- With τ = 10%, a value tied to only 2% of the bonus counts as one fifth backed.

Raising τ separates real backing from token mentions.

## Why this operationalization of alignment
- **Theory.** The shared taxonomy follows stakeholder theory (Freeman 1984). A values statement declares which stakeholders a firm prioritizes, and an incentive plan reveals which stakeholders the board is willing to spend executive pay on. Pay is costly and legally disclosed, so it is a credible signal of priority. A page, by contrast, is cheap talk.
- **Why recall, not similarity.** Alignment is defined as recall of the say side, not as similarity between two distributions. The claim we can test is "what the firm says is backed by what it does". Pay plans also contain things a values page has no reason to mention, mainly financial metrics, so penalizing those would measure page style rather than authenticity.
- **Why salience-weighted.** Leaving a headline value unbacked is a bigger gap than leaving a passing mention unbacked.
- **Why a ratio.** It is scale-free across short and long pages.
- **Why proxies t and t+1.** The page for year t was archived around July 1 of t. The proxy filed in t reports pay for fiscal t−1, and the proxy filed in t+1 reports pay for fiscal t, the year the page was live. Either can show backing, so coverage uses the maximum over both.
- **2024's t+1 comes from Part 2's extension.**
  - **Source.** The 2025 proxies come from Part 2's out-of-sample extension (`output/extension_2025_2026/`). They are used only where that extension's CD&A extraction exists and lists reported-year metrics. The criteria counts are built with Part 2's own `pay_counts()`, so de-duplication matches the main panel. The source is recorded in `do_t1_source`.
  - **Coverage.** 44 firms get a 2025 t+1 this way. The other 6 keep 2024 alone and are flagged:
    - MRK's 2025 proxy has no CD&A section.
    - BRK.B, GS, AMZN, F and MPC have 2025 extractions with no metrics. Part 2's panel treats such rows as missing, not zero, and Part 3 follows it.
  - **No 2025 weights.** The extension has no weight layer. For 2024, the weighted versions therefore use 2024 weights only (`weights_partial` = True), while the primary index uses both years' criteria counts.
  - **Effect.** With a second proxy, 2024 is comparable to the other years. Its mean A rose from 0.40 (t only) to 0.47.

## Definitions
For firm *i*, year *t* and category *k* (the 9 shared codes):

| Input | Source | Meaning |
|---|---|---|
| `s_ikt` | Part 1 `sal_<k>` | Stated salience, 0 to 3 |
| `d_ikt` | Part 2 `pay_n_<k>` | Count of distinct pay-linked criteria |
| `w_ikt` | Part 2 `cat_weight_<k>` (provenance in `weight_source`: `disclosed`, `derived_from_stated_split`, `imputed_emphasis` or `none`) | Share of the annual incentive plan's payout weight. The long-term plan's weights (`cat_weight_lti_*`) are not used: those plans are almost entirely financial (on average 95.6% of LTI weight is on shareholders, and 88% of plans put at least 90% there). |

```
c_ikt(τ) = min( max(w_ik,t , w_ik,t+1) / τ , 1 )       coverage of category k
A_it(τ)  = Σ_k s_ikt · c_ikt(τ) / Σ_k s_ikt             salience-weighted coverage
τ → 0:  c_ikt = 1 if d_ik,t > 0 or d_ik,t+1 > 0, else 0  (primary; needs no weights)
```

Columns in `output/authenticity_index.csv` (one row per firm-year, 450 rows):

| Column | Meaning |
|---|---|
| `A` | Primary index (τ → 0) |
| `A_tau5`, `A_tau10`, `A_tau20` | Weighted versions (τ = 10% is the headline weighted index) |
| `A_ex_shareholders` (+ `_tau*`) | The same index without the shareholders category. Nearly every pay plan covers shareholders, which inflates scores for firms that mainly talk about returns. |
| `unstated_backing` | Share of pay-linked categories (shareholders excluded) with d > 0 but s = 0: **doing without saying**, input to Part 4 |
| `s_<k>`, `d_<k>`, `w_<k>`, `cov_<k>` | Per-category inputs and the τ → 0 coverage, for auditing any score |
| `A_reason`, `A_weighted_reason`, `A_ex_shareholders_reason`, `unstated_backing_reason` | Why a value is NaN (see below) |
| `do_window` | Proxy years used: `t_and_t1`, `t_only_2024`, `t_only_t1_missing`, `t1_only_t_missing` |
| `do_t1_source` | Where the t+1 proxy came from: `panel`, `extension_2025_2026` (page-year 2024 only), or `none` |
| `flag_2024_t_only` | True for page-year 2024 rows with no usable 2025 proxy (6 firms) |
| `w_source`, `weights_partial` | Where the weights came from; True if only one of the two proxy years had them |
| `p2_flagged_t/t1`, `p2_flag_reason_t/t1`, `p2_cda_quality_t/t1` | Part 2 quality flags for both proxy years, carried through |
| `page_type`, `word_count` | Say-side context, used in the discriminant check |

NaN reasons:

| Reason | Meaning |
|---|---|
| `say_missing` | Part 1 gap year |
| `say_all_zero` | The page states no codable value (e.g. AAPL's contact page, VLO's fact sheet). The index is undefined, not 0. |
| `do_missing` | No extracted pay data for t or t+1 |
| `no_weights` | Weighted versions only: no usable weights |
| `say_only_shareholders` | `A_ex_shareholders` only |
| `no_non_shareholder_pay_criteria` | `unstated_backing` only |

### Weight guard (added in the pilot, now removed) and the `other` residual
- **Why the guard existed.** In the pilot, Part 2 parked nested weight splits in `other`. MSFT's 2019 to 2020 bonus was 50% "qualitative", split equally across customers, innovation and culture, and all of it was recorded as `other`. That made those categories read 0%, so Part 3 temporarily ignored any proxy-year with 5% or more in `other`.
- **Why it was removed.** Part 2's weight layer now resolves nested splits (MSFT 2019: customers 15.8%, employees 8.3%, `other` 0%). `cat_weight_other` now holds only criteria that fit no stakeholder, and the index does not count them. The guard was therefore removed.
- **What removing it changed.** The τ = 10% index is now defined for 350 firm-years instead of 253. The primary index is unchanged.
- **Documented residual.** 136 of 375 proxy-years with weights (34 firms) still put 5% or more of the bonus in `other` (`output/analysis/other_residual.csv`, which lists each row's criteria).
  - These are mostly individual-performance factors (META in all 9 years, IBM, NKE), team or operational components (INTC, MDT) and strategic projects (MS).
  - They lower weighted coverage only by leaving less of the plan for stakeholders, which is the intended reading.
  - Two entries are coarse labels that may hide stakeholder content: GOOGL 2024's "Environmental, Social, and Governance Bonus" (100% `other`) and TJX's plan-name entries. A finer Part 2 coding could move them into categories.

## Results (full panel: 48 firms, 384 firm-years)
`output/analysis/results.md` holds every table, and figures are in `output/figures/`. Numbers below are for the primary index A (τ → 0) unless stated.

**Distribution.**
- A has mean 0.42 and median 0.40, spanning the full 0 to 1 range (10th percentile 0, 90th percentile 0.83).
- `A_ex_shareholders` has mean 0.36.
- `unstated_backing` has mean 0.19: about a fifth of a typical firm's non-financial pay categories go unmentioned on its page.
- The index varies more between firms than within them over time: the SD of firm means is 0.25, against an average within-firm SD of 0.16.
- 2 firms have no index. AAPL has no page with codable values, and BRK.B has no pay-metric section to extract.

**The rankings, and what they measure.** The full table is `output/analysis/firm_ranking.csv`. Firms with fewer than 5 firm-years are flagged **(n<5)**.
- **Lowest firm means:** SCHW 0.02, NVDA 0.03, CRM 0.09, GOOGL 0.12, AMZN 0.14 (n<5), ABT 0.14 and HD 0.16.
- **Highest firm means:** EOG 1.00 (n<5), JPM 0.92, VLO 0.82, MSFT 0.82, WFC 0.75 and BLK 0.71.
- **A measures whether stated values enter executive incentive design. It does not measure honesty in general.**
  - NVDA, SCHW and GOOGL score near 0 because their annual bonus is purely financial *by design*. Their pages state customers, innovation and community, and their pay philosophy deliberately ties executive incentives to financial results and equity value alone.
  - A firm with a purely financial pay philosophy therefore scores low by construction, whatever it practices elsewhere.
  - JPM, MSFT and the energy firms score high because they run stakeholder scorecards that name the same stakeholders their pages do.
  - This is the first threat to validity below.

**By sector and year.**
- Energy (0.53) and Financials (0.53) score highest. Consumer Discretionary (0.31) and Technology (0.33) score lowest.
- The year means range from 0.36 to 0.47, with no clear trend. 2023 (0.46) and 2024 (0.47) are the two highest years, a small late rise that two years cannot establish as a trend.

**Weighted versions are lower:** mean 0.38 at τ = 5%, 0.34 at τ = 10% and 0.26 at τ = 20% (350 firm-years). Most non-financial criteria are unweighted holistic factors or small slices of the bonus. **The gap between `A` and `A_tau10` separates nominal backing from material backing.**

**Sensitivity to τ** (46 firms, 350 firm-years with weights): the firm rankings are stable. Spearman correlations of firm mean A are 0.95 between τ → 0 and 5%, 0.92 with 10%, and 0.87 with 20%. The firms whose rank drops most as τ rises are the "token coverage" cases: they list many stakeholder criteria that carry little bonus weight. In this table, n counts the firm-years where all four τ values are defined.

| Firm | Rank at τ → 0 | Rank at τ = 20% | n |
|---|---|---|---|
| TMO | 16 | 36 | 9 |
| MSFT | 4 | 20 | 9 |
| SLB | 19 | 34 | 9 |
| NKE | 31 | 45 | 7 |
| TGT | 18 | 29 | 9 |

**Robustness: stated weights only.** As Session 2 suggested, the weighted index was recomputed using only `disclosed` and `derived_from_stated_split` weights, excluding Part 2's `imputed_emphasis` estimates. This leaves 99 firm-years across 23 firms (`output/analysis/robustness_stated_weights.csv`).
- **The rankings mostly hold.** Compared on the same firm-years, the Spearman correlation with the all-weights version is 0.79 at τ = 10% and 0.84 at τ = 20%.
- **Two firms drive the gap, and both have fewer than 5 firm-years (n<5):**
  - INTC falls from rank 7 to 21.5 and SLB from 12 to 21.5.
  - Their stated splits put no weight on stakeholder categories, while the imputed weights credit their unweighted holistic factors.
  - Without them the correlation is 0.95. Among the 9 firms with at least 5 firm-years it is 0.88.
- **Caveat:** 14 of the 23 firms have fewer than 5 firm-years with stated weights, so this check covers a small subset.
- **Reading:** the weighted ranking is robust where firms state their weights, but it relies on imputed weights for firms that do not.
- **The weight-free and weighted indexes differ:** their correlation is 0.45 (τ → 0 vs stated-only τ = 10%). They answer different questions: whether pay names a stakeholder at all, and how much pay rides on it.

**Validity: known groups.**
- **XOM environment: passes.** Environment pay criteria go 0 → 1 → 4 as the 2022 proxy adds energy-transition metrics. With the t/t+1 window, that shows as coverage from page-year 2020 and full strength from 2021. The page keeps environment at low salience (1, then 2 in 2024): pay moved before the page did.
- **WFC: the check fails as specified, and the reason is timing.**
  - **The expectation:** customer coverage should be low in 2016 to 2018, around the fake-accounts scandal.
  - **The result:** customer coverage (τ → 0) is 1 in page-year 2016, 0 in 2017 and 1 in 2018.
  - **Per-category detail** (`output/analysis/known_group_WFC_all_categories.csv`; cell = salience / coverage τ → 0 / weighted coverage τ = 10%; page-year t uses the proxies filed in t and t + 1):

| Page-year | Proxies | customers | integrity | dei | employees | community |
|---|---|---|---|---|---|---|
| 2016 | 2016, 2017 | 2 / 1 / 0.6 | 2 / 1 / 1.0 | 0 / 1 / 0.7 | 1 / 0 / 0.0 | 0 / 1 / 0.3 |
| 2017 | 2017, 2018 | 3 / 0 / 0.0 | 2 / 1 / 0.0 | 0 / 0 / 0.0 | 1 / 0 / 0.0 | 0 / 0 / 0.0 |
| 2018 | 2018, 2019 | 3 / 1 / 0.4 | 3 / 1 / 1.0 | 3 / 1 / 0.6 | 3 / 1 / 0.4 | 2 / 1 / 0.4 |
| 2019 | 2019, 2020 | 3 / 1 / 0.4 | 3 / 1 / 1.0 | 3 / 1 / 0.6 | 3 / 1 / 0.4 | 2 / 1 / 0.4 |

  - **What the proxies show.** The scandal was disclosed in September 2016, so the panel holds a single pre-disclosure proxy.
    - **2016 proxy** (filed March 2016, fiscal 2015; pre-disclosure). Customers 5.7% of the bonus, from one holistic factor: "furthering the Company's objectives of creating deep and enduring relationships with our customers". That is the cross-selling objective at the root of the misconduct, which the coding reads as `customers`. Risk and conduct (`integrity`) 21%.
    - **2017 proxy** (fiscal 2016, the scandal year). The bonus criteria collapse to financial results alone: 100% `shareholders`. The text explains why: the board had the former CEO and the former Community Bank head forfeit their unvested equity and receive no 2016 annual incentive, and it used its discretion to cut the senior leadership team's award payouts to 75% of target. That year's pay was governed by forfeiture, not by criteria. Hence the page-year 2017 dip.
    - **2019 proxy** (fiscal 2018, remediation). Integrity rises to 44% of the bonus, and a new "Customer Service and Advice" criterion (branch satisfaction scores) carries 4.2%. The page meanwhile raises customers, integrity, DEI and employees to salience 3.
  - **Likely explanation.** The 2016 to 2024 window cannot observe the pre-scandal decoupling. It sees a single pre-disclosure proxy whose customer criterion *was* the cross-selling objective, then a forfeiture year, then remediation. The index therefore captures **re-coupling after the scandal**, not the decoupling before it.
  - **What would test the hypothesis properly:** **2011 to 2016**, the period of the sales-goal pressure documented in the CFPB consent order (September 2016).
    - Wells Fargo's 2011 to 2016 DEF 14A proxies (EDGAR, Part 2's pipeline).
    - Its archived About and Vision & Values pages for the same years (Wayback, Part 1's pipeline).
    - The prediction: customers stated at high salience, while the only customer-linked pay criteria are cross-sell volume objectives. Testing it needs cross-sell and product-per-household metrics coded as volume (`shareholders` under the shared tie-break rule) rather than as `customers`.
- **A threat to validity, shown by WFC: a category match is not a values match.** A criterion coded `customers` can reward the very behavior that harmed customers.

**Validity: discriminant check.** OLS of A on page type, log word count and sector, with firm-clustered standard errors, gives R² = 0.16.
- Page type (values vs About: +0.09, p = 0.13) and page length (p = 0.17) do not significantly explain the score, so the index is not an artifact of which page was scraped or how long it is.
- Sector does explain the score: Energy is +0.23 (p = 0.001) and Financials +0.23 (p = 0.010), relative to Consumer Discretionary.
- This is consistent with substance rather than artifact. Energy pay plans carry safety and environment scorecards, and bank plans carry risk and conduct criteria, which matches what those firms state. Cross-firm comparisons are best made within sector.

## Limitations and threats to validity
1. **Construct validity: A measures whether stated values enter executive incentive design, not honesty in general.**
   - A firm whose pay philosophy is purely financial by design scores low by construction, however sincerely it pursues the values it states. NVDA, SCHW and GOOGL score near 0 for this reason.
   - Conversely, a firm can score high by adding a stakeholder line to a bonus scorecard while its practice is unchanged.
   - Read A as "incentive alignment of stated values", one observable channel through which a firm can make its stated values costly, not as a verdict on authenticity.
2. **LLM label noise on both sides.** Salience (Part 1) and pay-criterion categories (Part 2) are single-model codings without temperature control. Both were hand-checked on samples, but re-sampling can move a category by ±1 salience or flip a borderline criterion's category. The index is a ratio over a few categories, so one flip can move a firm-year by 0.1 to 0.3. Firm-level means over years are more robust than single years.
3. **Pay criteria are a proxy for priority, and weights are often missing.** A criterion can be a holistic factor with no weight. Many firms disclose no category weights. 251 of the 350 firm-years with weights rest only on Part 2's `imputed_emphasis` weights, which are estimates; the stated-weights robustness check above shows where this matters (INTC, SLB). This is why the primary index is weight-free and the weighted version is secondary. Pay also covers only top executives, not company-wide practice.
4. **Say-side coverage gaps and the page mix.**
   - 35 firm-years have no page (Part 1 gaps), and 9 pages state no codable value.
   - About pages and values pages differ systematically: values pages have higher total salience and more integrity and employees content. Comparisons across firms should control for `page_type`, which is what the discriminant check tests.
5. **Survivorship.** The sample is the 2024 constituents of the S&P 500, observed back to 2016. Firms that fell out of the index, possibly those whose rhetoric and practice diverged most, are not observed. Levels are therefore likely biased upward, and the 2016 cross-section is not representative of the 2016 S&P 500.
6. **A category match is not a values match.** WFC 2016 shows this: a pay criterion coded `customers` can reward the very behavior that harmed customers. The index measures whether the same stakeholder appears on both sides, not whether pay serves the stated value.
7. **Recall is not precision.** A firm that states almost nothing scores well if that little is paid for. `say_all_zero` rows are excluded rather than scored, but thin pages still make high scores cheap. Read `A` together with total salience and `unstated_backing`.

## With more time
- A precision-side companion: the share of material pay weight in categories the page states. The two together would give an F1-style alignment.
- Measure inter-run reliability of both LLM codings, and report index confidence intervals by re-sampling labels.
