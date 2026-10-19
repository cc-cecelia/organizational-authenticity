# Part 3: Organizational Authenticity Index

**Status: pilot.** The index is built on Part 2's *pilot* panel, which has pay data for MSFT, JPM and XOM only, giving 26 firm-years. Every number below that comes from the data is a pilot number. The pipeline reruns unchanged once Part 2 commits the full `lived_values_panel.csv`:

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
| `w_ikt` | Part 2 `aip_weight_share_<k>` (disclosed), else an imputed panel column | Share of the annual incentive plan |

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

### Guard on disclosed weights (found in the pilot)
Part 2 keeps only weights stated as a share of the plan total. Microsoft's 2019 and 2020 bonus was split as follows:
- 50% financial.
- 50% "qualitative", split equally across customers, product/innovation and culture.

Part 2 records the whole qualitative half as `other`, so customers, innovation and employees read 0%, though each was really about 16.7%. The weighted index then returned 0.0 for a firm with full count-based coverage.

Part 3 therefore uses disclosed weights only when less than 5% of the plan is unresolved in `other`. Otherwise the weighted index uses imputed weights once Part 2 adds them, or is NaN with reason `disclosed_weights_unresolved`. The primary τ → 0 index is unaffected. The nested-weight case is flagged for Part 2 to resolve.

## Results (pilot: 3 firms, 26 firm-years)
`output/analysis/results.md` holds every table. Figures are in `output/figures/`.

- **Distribution.** A (τ → 0) has mean 0.74 and median 0.80, ranging from 0.33 to 1.00. Without shareholders, the mean is 0.69 and the minimum 0.
  - XOM is lowest (median 0.42). Its pages state innovation every year, and customers, community and integrity in 5 of 9 years, none of which its pay plan rewards in those years.
  - JPM is highest (median 0.94). Its Business Principles name nearly the same stakeholders as its pay scorecard; innovation is the only regular gap (4 years).
- **Weighted versions are much lower** (mean A at τ = 10% is 0.35). Most non-financial pay criteria are unweighted holistic factors or small slices of the plan. **The gap between `A` and `A_tau10` is itself informative: it separates nominal backing from material backing.**
- **Sensitivity.** The Spearman machinery runs, but with 3 firms it is not interpretable. It reruns on the full panel.
- **Known groups.**
  - **XOM environment: passes.** Environment pay criteria go 0 → 1 → 4 as the 2022 proxy adds energy-transition metrics. With the t/t+1 window, this shows as coverage from page-year 2020 (the 2021 proxy's first criterion) and full strength from 2021. The page meanwhile keeps environment at low salience (1, rising to 2 in 2024): pay moved before the page did.
  - **WFC customers: pending.** WFC has no pay data in the pilot panel.
- **Discriminant check: pending.** It needs at least 4 firms across sectors.

## Limitations and threats to validity
1. **LLM label noise on both sides.** Salience (Part 1) and pay-criterion categories (Part 2) are single-model codings without temperature control. Both were hand-checked on samples, but re-sampling can move a category by ±1 salience or flip a borderline criterion's category. The index is a ratio over a few categories, so one flip can move a firm-year by 0.1 to 0.3. Firm-level means over years are more robust than single years.
2. **Pay criteria are a proxy for priority, and weights are often missing.** A criterion can be a holistic factor with no weight. Many firms disclose no category weights, and some disclose nested weights that Part 2 cannot yet resolve (see above). This is why the primary index is weight-free and the weighted version is secondary. Pay also covers only top executives, not company-wide practice.
3. **Say-side coverage gaps and the page mix.**
   - 35 firm-years have no page (Part 1 gaps), and 9 pages state no codable value.
   - About pages and values pages differ systematically: values pages have higher total salience and more integrity and employees content. Comparisons across firms should control for `page_type`, which is what the discriminant check tests.
4. **Survivorship.** The sample is the 2024 constituents of the S&P 500, observed back to 2016. Firms that fell out of the index, possibly those whose rhetoric and practice diverged most, are not observed. Levels are therefore likely biased upward, and the 2016 cross-section is not representative of the 2016 S&P 500.
5. **Recall is not precision.** A firm that states almost nothing scores well if that little is paid for. `say_all_zero` rows are excluded rather than scored, but thin pages still make high scores cheap. Read `A` together with total salience and `unstated_backing`.

## With more time
- Resolve nested weights (parent × component) for weighted coverage, and estimate weights for holistic factors (equal split within their parent component).
- A precision-side companion: the share of material pay weight in categories the page states. The two together would give an F1-style alignment.
- Measure inter-run reliability of both LLM codings, and report index confidence intervals by re-sampling labels.
