# Part 3: Organizational Authenticity Index

**Status: full run.** The index is built on Part 2's full `lived_values_panel.csv` (commit `08de01f`). The primary index covers **383 of 450 firm-years across 48 firms**. To reproduce:

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
| `flag_2024_t_only` | True for 2024, which has no t+1 proxy in the window |
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
| `disclosed_weights_unresolved` | See the next section |
| `say_only_shareholders` | `A_ex_shareholders` only |
| `no_non_shareholder_pay_criteria` | `unstated_backing` only |

### Interim guard on weights (decision pending)
**Why the guard was added.** In the pilot, Part 2 kept only weights stated as a share of the plan total. Microsoft's 2019 and 2020 bonus was 50% financial plus 50% "qualitative", split equally across customers, product/innovation and culture. That qualitative half landed in `other`, so the three categories read 0% instead of about 16.7% each, and the weighted index scored MSFT 2019 at 0.0 next to a count-based 1.0. Part 3 therefore ignores a proxy year's weights when 5% or more of its plan sits in `other`, and the weighted versions are NaN with reason `disclosed_weights_unresolved` when no other year's weights are usable. The primary τ → 0 index never uses weights.

**Status after Part 2's weight layer.** Part 2 now resolves nested splits: MSFT 2019 has customers 15.8%, employees 8.3% and `other` 0%. `cat_weight_other` now holds genuine non-stakeholder criteria, such as individual-performance factors, team scorecards and strategic milestones.

The removal rule was "remove the guard if no row has ≥ 5% in `other`". **136 of 375 weighted proxy-years still have ≥ 5% in `other`**, so the guard stays for now, but those rows are no longer unresolved weights. With the guard, the τ = 10% index is defined for 253 firm-years (mean 0.29); without it, for 350 (mean 0.33).

The guard also distorts individual rows. WFC 2016's 5.7% customer weight is dropped because its plan also has 5.7% in `other`. Whether to remove the guard is pending a decision.

## Results (full panel: 48 firms, 383 firm-years)
`output/analysis/results.md` holds every table, and figures are in `output/figures/`. Numbers below are for the primary index A (τ → 0) unless stated.

**Distribution.**
- A has mean 0.41 and median 0.38, spanning the full 0 to 1 range (10th percentile 0, 90th percentile 0.82).
- `A_ex_shareholders` has mean 0.35.
- `unstated_backing` has mean 0.20: a fifth of a typical firm's non-financial pay categories go unmentioned on its page.
- The index varies more between firms than within them over time: the SD of firm means is 0.24, against an average within-firm SD of 0.16.
- 2 firms have no index. AAPL has no page with codable values, and BRK.B has no pay-metric section to extract.

**The rankings are interpretable.**
- **Lowest firm means** are SCHW 0.02, NVDA 0.03, CRM 0.09, GOOGL 0.12, ABT 0.14 and AMZN 0.14. Their pay is purely financial or equity-based, while their pages state customers, innovation and community.
- **Highest firm means** are JPM 0.92, VLO 0.82, MSFT 0.80, BLK 0.71 and WFC 0.69. These firms run stakeholder scorecards.
- EOG (1.00) rests on only 3 firm-years because of Part 1 gaps.

**By sector and year.**
- Energy (0.53) and Financials (0.52) score highest. Consumer Discretionary (0.30) and Technology (0.32) score lowest.
- The year means are flat (0.36 to 0.46) with no trend.

**Weighted versions are much lower:** mean 0.33 at τ = 5%, 0.29 at τ = 10% and 0.24 at τ = 20%. Most non-financial criteria are unweighted holistic factors or small slices of the bonus. **The gap between `A` and `A_tau10` separates nominal backing from material backing.**

**Sensitivity to τ** (41 firms with weights): the firm rankings are stable. Spearman correlations are 0.94 between τ → 0 and 5%, 0.89 with 10%, and 0.82 with 20%. The firms whose rank drops most as τ rises are the "token coverage" cases: they list many stakeholder criteria that carry little bonus weight.

| Firm | Rank at τ → 0 | Rank at τ = 20% |
|---|---|---|
| TGT | 16 | 34 |
| TMO | 13 | 31 |
| NKE | 26 | 41 |
| WFC | 5 | 17 |
| MSFT | 4 | 15 |

**Validity: known groups.**
- **XOM environment: passes.** Environment pay criteria go 0 → 1 → 4 as the 2022 proxy adds energy-transition metrics. With the t/t+1 window, that shows as coverage from page-year 2020 and full strength from 2021. The page keeps environment at low salience (1, then 2 in 2024): pay moved before the page did.
- **WFC customers: partly fails, and the failure is informative.** Coverage was expected to be low in 2016 to 2018, around the fake-accounts scandal.
  - Page-year 2017 has no customer pay criteria, as expected.
  - Page-year 2016 is covered by a 2016 holistic factor: "furthering the Company's objectives of creating deep and enduring relationships with our customers". That is the cross-selling objective at the root of the scandal, which the coding treats as `customers`.
  - Page-year 2018 borrows the 2019 proxy's new post-scandal "Customer Service and Advice" metric through the t+1 window.
  - Weighted coverage is low in all three years (0, 0 and 0.42 at τ = 10%).
  - The lesson is a threat to validity: **a category match cannot tell a customer metric that serves customers from one that harmed them.**

**Validity: discriminant check.** OLS of A on page type, log word count and sector, with firm-clustered standard errors, gives R² = 0.16.
- Page type (values vs About: +0.10, p = 0.11) and page length (p = 0.17) do not significantly explain the score, so the index is not an artifact of which page was scraped or how long it is.
- Sector does explain the score: Energy is +0.24 (p = 0.001) and Financials +0.23 (p = 0.009), relative to Consumer Discretionary.
- This is consistent with substance rather than artifact. Energy pay plans carry safety and environment scorecards, and bank plans carry risk and conduct criteria, which matches what those firms state. Cross-firm comparisons are best made within sector.

## Limitations and threats to validity
1. **LLM label noise on both sides.** Salience (Part 1) and pay-criterion categories (Part 2) are single-model codings without temperature control. Both were hand-checked on samples, but re-sampling can move a category by ±1 salience or flip a borderline criterion's category. The index is a ratio over a few categories, so one flip can move a firm-year by 0.1 to 0.3. Firm-level means over years are more robust than single years.
2. **Pay criteria are a proxy for priority, and weights are often missing.** A criterion can be a holistic factor with no weight. Many firms disclose no category weights. 168 of the firm-years with weights rest on Part 2's `imputed_emphasis` weights, which are estimates. This is why the primary index is weight-free and the weighted version is secondary. Pay also covers only top executives, not company-wide practice.
3. **Say-side coverage gaps and the page mix.**
   - 35 firm-years have no page (Part 1 gaps), and 9 pages state no codable value.
   - About pages and values pages differ systematically: values pages have higher total salience and more integrity and employees content. Comparisons across firms should control for `page_type`, which is what the discriminant check tests.
4. **Survivorship.** The sample is the 2024 constituents of the S&P 500, observed back to 2016. Firms that fell out of the index, possibly those whose rhetoric and practice diverged most, are not observed. Levels are therefore likely biased upward, and the 2016 cross-section is not representative of the 2016 S&P 500.
5. **A category match is not a values match.** WFC 2016 shows this: a pay criterion coded `customers` can reward the very behavior that harmed customers. The index measures whether the same stakeholder appears on both sides, not whether pay serves the stated value.
6. **Recall is not precision.** A firm that states almost nothing scores well if that little is paid for. `say_all_zero` rows are excluded rather than scored, but thin pages still make high scores cheap. Read `A` together with total salience and `unstated_backing`.

## With more time
- A precision-side companion: the share of material pay weight in categories the page states. The two together would give an F1-style alignment.
- Measure inter-run reliability of both LLM codings, and report index confidence intervals by re-sampling labels.
