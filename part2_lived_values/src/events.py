"""External events used to annotate year trends.

Proxies are backward-looking and filed once a year, so an event can only
show up in proxies filed after it. Instead of assuming a fixed lag, we
compute each firm's first proxy filed after the event date
(`first_exposed_filing_year`). MSFT, for example, files in October, so it
reacts to a mid-year event in the same calendar year. Spring filers react
the following year.
"""
from __future__ import annotations

# (event_id, date, label, categories most likely affected, source note)
EVENTS = [
    ("racial_justice_2020", "2020-05-25",
     "Racial justice moment (George Floyd murder, May 2020)",
     ["dei", "employees", "community"],
     "Wave of corporate racial-equity pledges, summer 2020."),
    ("sec_human_capital_2020", "2020-11-09",
     "SEC human capital disclosure rule takes effect (Reg S-K Item 101(c))",
     ["employees"],
     "Principles-based workforce disclosure in 10-Ks; spills into proxy narratives."),
    ("nasdaq_board_diversity_2021", "2021-08-06",
     "SEC approves Nasdaq board diversity rule (Rule 5605(f))",
     ["dei"],
     "Board diversity matrix required from 2022 for Nasdaq listings; vacated by the 5th Circuit in Dec 2024."),
    ("engine_no1_xom_2021", "2021-05-26",
     "Engine No. 1 wins three ExxonMobil board seats",
     ["environment", "shareholders"],
     "Signal that climate-focused activism can win; most relevant to Energy."),
    ("esg_backlash_2022", "2022-08-01",
     "ESG backlash (state anti-ESG laws, 2022-2023)",
     ["environment", "dei"],
     "Approximate start date: mid-2022 wave of state anti-ESG bills and AG letters."),
    ("sffa_2023", "2023-06-29",
     "SFFA v. Harvard Supreme Court ruling",
     ["dei"],
     "Ended race-conscious college admissions; triggered legal pressure on corporate DEI."),
]


def as_rows() -> list:
    return [{"event_id": e, "event_date": d, "label": l,
             "expected_categories": ";".join(c), "note": n} for e, d, l, c, n in EVENTS]
