# What large US companies pay their executives for (2016-2024)

## The question
Companies describe their values on their websites. A sharper test of what they
prioritise is what they **pay** their leaders to deliver. Every year, each
listed US company must publish a proxy statement explaining how executive pay
is decided. We read those statements for 50 large S&P 500 companies across
five sectors, for every year from 2016 to 2024. That is 450 company-years,
with none missing.

## What we measured
- **The criteria executive bonuses and long-term awards are tied to:** for
  example earnings per share, customer satisfaction, safety, emissions or
  workforce diversity. Each criterion is sorted into one of nine stakeholder
  groups, such as shareholders, employees, DEI, environment and safety.
- **How much each criterion counts.** Where the company states the weight, we
  use it. Where it does not, we estimate it from how much prominence the text
  gives the criterion, and say so.
- **What the company says in its own voice** in the proxy, and which
  shareholder proposals it faced and how the board responded.

A sample of ten company-years was checked line by line against the original
documents: 97% of pay criteria and 100% of shareholder proposals were
extracted correctly.

## What we found
1. **Executive pay is overwhelmingly financial.** About 70% of annual-bonus
   weight sits on financial results (profit, revenue, returns) in every year,
   and that share barely moves over nine years.
2. **Non-financial criteria became common, but they carry little money.**
   - The share of company-years with a pay-linked environmental criterion rose
     from 6% (2016) to about half (2023-24); for DEI it rose from about 20% to
     about half.
   - Yet environmental criteria carry only about 4-5% of bonus weight on
     average, and DEI about 3%.
   - Many criteria are named, but little pay moves with them.
3. **Sectors differ in a predictable way.**
   - Energy companies put real weight on environment (12%) and safety (11%)
     in 2024.
   - Consumer companies remain almost purely financial (88% on financial
     measures).
   - Banks use holistic scorecards: JPMorgan, for example, assesses "risk,
     controls and conduct", "client/customer/stakeholder" and "teamwork and
     leadership" without fixed weights.
4. **Companies talk about stakeholders more than they pay for them.** Between
   2016 and 2023, DEI language in proxies roughly tripled and environmental
   language grew about fivefold, while the money attached to either stayed
   small.
5. **Boards opposed almost every shareholder proposal.** Of 1,287 proposals,
   on climate, pay equity, lobbying, governance and more, boards recommended
   voting against 99.4%.

## How far to trust it
- **Stated vs estimated weights.** Only about a quarter of company-years
  disclose bonus weights fully. For the rest, the estimate was tested by
  hiding the true weights of 179 company-years that disclose them. It is off
  by about 10 percentage points per criterion on average, so estimated weights
  are an approximation; whether a criterion is present at all is the more
  reliable signal.
- **A criterion's category is not its substance.** A bonus tied to "customer"
  goals can still reward behaviour that harms customers.
- **The sample is today's large companies looking back.** Firms that left the
  index are not observed.
- **Corrections:** a few extraction errors were fixed by hand, each recorded
  with the quote that justifies it (for example, JPMorgan 2024 and Alphabet
  2023-24).

## What a reader could do with this
- **Investors and proxy advisers:** ask what share of pay a non-financial goal
  actually controls, not just whether it is listed. Pay attention to
  unweighted "holistic" scorecards, where nothing guarantees the goal matters
  in the final payout.
- **Boards and compensation committees:** if a stakeholder commitment matters,
  disclose its weight and its measure. The disclosure gap is wide, and firms
  that close it are easy to distinguish.
- **Researchers:** the company-year table (`output/lived_values_panel.csv`) is
  ready to join with other data on ticker and year. The method needs no
  changes to cover all 500 S&P companies, at roughly $35 in model costs (this
  50-company run cost about $3.50).
