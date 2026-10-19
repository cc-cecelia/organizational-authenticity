"""
Part 1 (c): one row per firm summarizing how its stated values shifted 2016-2024.

Built only from stated_values.csv (no new LLM calls):
  rising / falling themes  mean salience in the firm's last 3 observed years minus
                           its first 3; categories that moved by >= 1 point, each with
                           the year of its largest single-year step in that direction.
  biggest change           the substantive year-over-year change with the largest L1
                           shift in the salience vector, its LLM change summary, and
                           one verbatim quote each side, from the category that moved
                           most at that change.
  tone                     first sentence of analyst_notes in the first and last year.

Caveat carried in `page_type_changed`: when a firm's page type differs between the
early and late window, part of a theme shift is page choice, not wording.

Usage: .venv/bin/python part1_stated_values/src/linguistic_shifts.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

sys.path.insert(0, str(config.REPO_ROOT / "part2_lived_values" / "src"))
from theme_dictionary import CATEGORIES  # noqa: E402

WINDOW = 3          # years averaged at each end
MIN_SHIFT = 1.0     # salience points needed to call a theme rising/falling


def first_sentence(text) -> str:
    if not isinstance(text, str):
        return ""
    return re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]


def firm_row(g: pd.DataFrame) -> dict:
    g = g.sort_values("year").reset_index(drop=True)
    sal = g[[f"sal_{c}" for c in CATEGORIES]].to_numpy(dtype=float)
    early, late = g.head(WINDOW), g.tail(WINDOW)
    row = {"ticker": g.ticker[0], "company_name": g.company_name[0], "sector": g.sector[0],
           "years_observed": len(g), "first_year": int(g.year.iloc[0]), "last_year": int(g.year.iloc[-1]),
           "page_type_changed": set(early.page_type) != set(late.page_type),
           "n_substantive_changes": int((g.change_type == "substantive").sum()),
           "substantive_change_years": " ".join(str(y) for y in g.year[g.change_type == "substantive"])}

    # Rising / falling themes, each with the year of its largest step that way.
    rising, falling = [], []
    for j, c in enumerate(CATEGORIES):
        delta = late[f"sal_{c}"].mean() - early[f"sal_{c}"].mean()
        if abs(delta) < MIN_SHIFT or len(g) < 2:
            continue
        steps = pd.Series(sal[1:, j] - sal[:-1, j], index=g.year[1:])
        when = int((steps if delta > 0 else -steps).idxmax())
        (rising if delta > 0 else falling).append((abs(delta), f"{c} {delta:+.1f} ({when})"))
    row["rising_themes"] = "; ".join(s for _, s in sorted(rising, reverse=True))
    row["falling_themes"] = "; ".join(s for _, s in sorted(falling, reverse=True))

    # Biggest substantive change (L1 shift in salience vs the prior collected year).
    best = None
    for i in range(1, len(g)):
        if g.change_type[i] != "substantive":
            continue
        diff = sal[i] - sal[i - 1]
        l1 = abs(diff).sum()
        if best is None or l1 > best[0]:
            best = (l1, i, diff)
    if best:
        l1, i, diff = best
        k = int(abs(diff).argmax())
        c = CATEGORIES[k]
        before, after = g.iloc[i - 1], g.iloc[i]
        row.update({
            "biggest_change_year": int(after.year),
            "biggest_change_from_year": int(before.year),
            "biggest_change_salience_l1": int(l1),
            "biggest_change_category": f"{c} {int(before[f'sal_{c}'])}->{int(after[f'sal_{c}'])}",
            "quote_before": before[f"ev_{c}"] if isinstance(before[f"ev_{c}"], str) else "(absent)",
            "quote_after": after[f"ev_{c}"] if isinstance(after[f"ev_{c}"], str) else "(absent)",
            "biggest_change_summary": after.change_summary,
        })
    row["tone_first_year"] = first_sentence(g.analyst_notes.iloc[0])
    row["tone_last_year"] = first_sentence(g.analyst_notes.iloc[-1])
    return row


def main() -> int:
    d = pd.read_csv(config.STATED_VALUES_CSV)
    ok = d[d.status == "ok"]
    out = pd.DataFrame([firm_row(g) for _, g in ok.groupby("ticker", sort=False)])
    order = {t: i for i, t in enumerate(pd.read_csv(config.COMPANIES_CSV).ticker)}
    out = out.sort_values("ticker", key=lambda s: s.map(order))
    path = config.OUTPUT_DIR / "linguistic_shifts.csv"
    out.to_csv(path, index=False)
    print(f"wrote {path} ({len(out)} firms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
