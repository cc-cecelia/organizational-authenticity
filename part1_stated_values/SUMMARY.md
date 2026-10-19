# What do companies say they value, and how did it change from 2016 to 2024?

*Part 1 summary: the "About us" and values pages of 50 large S&P 500 companies, 2016 to 2024*

## What we did
Companies publish a statement of who they are and what they stand for: an "About us" page, a mission statement, a credo, a set of values. These pages change quietly, and old versions disappear from the company's website.

We recovered them from the Internet Archive's Wayback Machine, one snapshot per company per year (taken nearest July 1) from 2016 to 2024. Where a company has a dedicated values or mission page (J&J's Credo, Chevron's "The Chevron Way", JPMorgan's Business Principles), we used it; otherwise we used its general About page.

An AI model then read every page. For nine stakeholder themes, it rated how prominently each was stated, from absent to central:
- customers, employees, diversity and inclusion, environment, community, shareholders, integrity, safety and innovation.

It also judged whether each year's page had **substantively** changed its stated values since the previous year, as opposed to a redesign, new photos or rotating news items. Every rating comes with a word-for-word quote from the page, and a sample was checked by hand.

**Coverage:** 415 of 450 company-years (92%). Every missing year has a recorded reason (the full list is in the README):
- The main cause is pages that are built in the browser and so were archived empty (Broadcom, EOG Resources).
- Apple has no values page at all: its "About" page was contact details and, from 2018, redirected to its site map.

## What we found
1. **Companies lead with customers, innovation and integrity.**
   - Customers and community appear on 82% of pages, and innovation on 76%.
   - As *headline* values, customers (30% of pages), integrity (30%) and innovation (29%) dominate.
   - Safety is the least stated theme (29% of pages). Half of its mentions come from energy companies, and a fifth from healthcare (product safety).
2. **From 2016 to 2024, the stated stakeholder circle widened.** Among the 42 companies observed in both years:
   - Diversity and inclusion rose the most: average prominence went from 0.6 to 1.1 on the 0 to 3 scale.
   - Employees (1.0 to 1.4), environment (0.6 to 1.0), community (1.5 to 1.9) and safety (0.3 to 0.7) also rose.
   - Shareholders is the only theme that fell (1.1 to 0.9). Integrity stayed flat.
3. **Diversity language rose steadily and had not retreated by mid-2024.**
   - The share of pages giving diversity clear emphasis doubled, from 22% in 2016 to 41% in 2022 and 2023.
   - It held at 40% in July 2024, a year after the Supreme Court's affirmative-action ruling and amid the backlash against DEI.
   - On these public pages, at least, any retreat came after our window, if at all.
4. **Values pages change more often than one might think.**
   - 43 of 50 companies substantively rewrote their stated values at least once, and a typical company did so twice in eight years.
   - In any given year, between a fifth and a half of companies made a substantive change. 2022 was the busiest year (22 of 42 comparable companies).
   - Examples:
     - **American Express** adopted a formal mission and six named values in 2019.
     - **Wells Fargo** replaced its long Vision & Values narrative in 2018, after its sales-practices scandal, with five values including "ethics" and "diversity and inclusion".
     - **Microsoft** dropped language about being "inclusive, transparent and respectful of human rights" in 2020.
     - **Marathon Petroleum** dropped its aim of an "accident-free, incident-free workplace" in 2021.
     - **UnitedHealth** rewrote its five core values in 2024 and added Inclusion.
5. **The tone is aspirational, and often hedged.**
   - About four in five pages read as aspirational rather than factual.
   - About two in five soften their commitments ("we aim to", "we strive to") rather than state them as absolutes.
   - Some pages are pure fact sheets with no stated values at all: Valero's About page in four of nine years, and Oracle's in 2017 to 2018.

## How to use this
- **Investors, analysts and journalists:** a company's values page is a dated, quotable public commitment, and its history is recoverable.
  - Use the year-by-year record (`stated_values.csv`, with quotes) to see when a commitment appeared, was dropped or was reworded.
  - Check those dates against events: a scandal, a new CEO, a regulatory change.
  - A removed commitment, such as Marathon's "accident-free" aim, is as informative as an added one.
- **Boards and communications teams:** the per-theme profile shows how a company's stated priorities compare with its industry peers', and how they drifted over time.
- **Researchers:** this is the "say" side of the authenticity index in Part 3. Each company-year carries a theme profile, normalized so that long and short pages are comparable, and a flag for whether the page really changed.

## Limits to keep in mind
- **One snapshot per year.** A change made and reversed within a year is invisible.
- **Two kinds of page.** Some companies have a dedicated values page and others only a general About page. About pages say less about values and carry more marketing, so compare like with like (each row records the page type).
- **AI reading, spot-checked.** Single ratings can be off by a step. Patterns across many companies and years are more reliable than any single rating.
- **What a page says is not what a company does.** That comparison is Part 3.

## Bottom line
Between 2016 and 2024, large US companies broadened what they publicly say they value: more about diversity, employees, environment, community and safety, and slightly less about shareholders. Most rewrote their values statements at least once, and diversity language had not retreated by mid-2024. The record is dated and quotable, which makes these pages a practical tool for holding companies to what they said, and when.
