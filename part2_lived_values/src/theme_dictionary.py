"""Seed dictionary for the shared stakeholder taxonomy (see CLAUDE.md).

One entry per term: (regex, note). Regexes run on lower-cased prose (tables
removed) with word boundaries added automatically, and each match counts
once. The output measure is hits per 10,000 prose words for each category
and firm-year.

Design principles:
- Proxies are dominated by procedural language ("annual meeting of
  shareholders", "equity awards", "Governance Committee"), so wherever a
  stakeholder word is also proxy machinery we either use a value-laden
  phrase instead of the bare word, or add an explicit exclusion. Each such
  choice is in the term's note.
- Terms are deliberately conservative: a smaller dictionary of
  unambiguous terms gives cleaner within-firm trends than a broad one,
  and within-firm change over time is the main use of this measure.
- Multi-label by construction: "racial equity" counts for dei only, but a
  sentence about "employee safety" counts for both employees and safety.

Exported as output/analysis/theme_dictionary.csv by text_measures.py.
"""
from __future__ import annotations

import re

CATEGORIES = ["customers", "employees", "dei", "environment", "community",
              "shareholders", "integrity", "safety", "innovation"]

# Same wording as the "Shared theme taxonomy" table in CLAUDE.md; also used
# in the LLM prompts so both layers code against identical definitions.
CATEGORY_DEFINITIONS = {
    "customers": "Customer focus, satisfaction, service quality, product access and affordability",
    "employees": "Workforce, talent, culture, engagement, pay equity, wellbeing, human capital",
    "dei": "Diversity, equity, inclusion: representation goals, board diversity, racial/gender equity, belonging",
    "environment": "Climate, emissions, energy transition, sustainability, natural resources",
    "community": "Communities, philanthropy, social impact, human rights, broader society",
    "shareholders": "Shareholder value, financial performance, returns, growth, capital discipline",
    "integrity": "Ethics, compliance, governance, transparency, accountability, risk culture",
    "safety": "Health and safety of workers and operations, process safety, product safety",
    "innovation": "Innovation, R&D, technology, new products, transformation",
}

THEME_TERMS = {
    "customers": [
        (r"customers?", "Core term; rarely procedural in proxies."),
        (r"clients?", "Banks and asset managers (JPM, GS, MS, BLK) say client, not customer."),
        (r"patients?", "Healthcare firms' end customer (LLY, PFE, UNH, MDT)."),
        (r"guests?", "Retail and restaurant firms' term for customers (TGT, SBUX, MCD)."),
        (r"customer (satisfaction|experience|service)", "Explicit customer-outcome language; often an incentive metric."),
        (r"net promoter( score)?|\bnps", "Customer-loyalty metric used in incentive plans."),
        (r"affordab(le|ility)", "Product access/affordability (pharma pricing, retail value)."),
        (r"access to (medicines?|care|healthcare|treatment)", "Healthcare access commitments."),
        # Excluded: "consumer(s)" - mostly appears in segment names
        # ("Consumer & Community Banking", "consumer products"), not stakeholder talk.
        # Excluded: "members" - UNH members, but also board/committee members.
    ],
    "employees": [
        (r"(?<!non-)(?<!non )employees?(?! stock purchase)",
         "Core term. Excludes 'non-employee director(s)' (director-pay section) and 'employee stock purchase plan'."),
        (r"workforce", "Core term; also the SEC human-capital rule's vocabulary."),
        (r"human capital", "Term of art after the Nov 2020 SEC human-capital disclosure rule."),
        (r"talent", "Talent attraction/development. Also used for executive talent; accepted."),
        (r"employee engagement|engagement survey", "Bare 'engagement' excluded: mostly 'shareholder engagement'."),
        (r"(employee|workforce) (well-?being|health)", "Wellbeing language tied to employees."),
        (r"well-?being", "Mostly employee wellbeing in proxies."),
        (r"training|upskill(ing)?|reskill(ing)?", "Investment in workers' skills."),
        (r"career (development|growth|progression)", "Employee development."),
        (r"(minimum|hourly|living) wages?|wages", "Frontline pay; distinct from executive pay vocabulary."),
        (r"workers?", "Workers' rights / labor proposals."),
        (r"culture", "Corporate culture. Some 'risk culture' (banks) overlap with integrity; accepted."),
        (r"labor|labour|labor unions?|unioni[sz](ed|ation)|collective bargaining",
         "Labor relations. Bare 'union' excluded ('European Union')."),
        # Excluded: "retention" (mostly executive retention awards); "benefits"
        # (executive perquisites tables); "people" (too generic).
    ],
    "dei": [
        (r"diversity", "Core term; covers board diversity and workforce diversity."),
        (r"diverse", "Mainly 'diverse board/slate/perspectives' in proxies."),
        (r"inclusion|inclusive", "Core term."),
        (r"diversity,? equity,? (and|&) inclusion|\bdei\b|\bd&i\b|\bde&i\b", "Named DEI programs."),
        (r"racial (equity|justice|equality)", "Post-2020 racial-justice vocabulary."),
        (r"race|racial|ethnic(ity|ally)?", "Demographic disclosure (Nasdaq rule, EEO-1 proposals)."),
        (r"women|female|gender", "Gender representation and pay."),
        (r"underrepresented|minorit(y|ies)|people of color", "Representation language."),
        (r"black(?!-scholes)(?! scholes)", "Excludes the Black-Scholes option-pricing model."),
        (r"hispanic|latin[oax]|african[- ]american|asian", "Demographic categories (board matrices, EEO-1)."),
        (r"lgbtq\+?|lgbt", "LGBTQ+ inclusion."),
        (r"pay equity|equal pay|pay gap", "Gender/racial pay equity. Bare 'equity' excluded: it means stock."),
        (r"belonging", "DEI program vocabulary ('inclusion and belonging')."),
        (r"eeo-?1", "Workforce demographic report; frequent proposal subject."),
        (r"civil rights( audit)?", "Civil-rights audits (proposal topic 2021-2023)."),
    ],
    "environment": [
        (r"climate", "Core term."),
        (r"carbon|decarboni[sz](e|ation|ing)|low-carbon", "Emissions and transition."),
        (r"emissions?|greenhouse gas(es)?|\bghg", "Core term."),
        (r"net[- ]zero", "Net-zero commitments."),
        (r"scope [123]", "GHG accounting scopes."),
        (r"methane|flaring", "Oil and gas specific emissions."),
        (r"energy transition|transition to (a )?low", "Energy-transition framing."),
        (r"renewables?|solar|wind power|clean energy", "Renewable energy."),
        (r"environment(al|ally)?", "Includes the 'E' of ESG."),
        (r"sustainab(le|ility)", "Mostly ESG usage. 'Sustainable growth' (financial) also matches; accepted."),
        (r"water|biodiversity|deforestation|plastics?|recycl(e|ed|ing)|packaging waste",
         "Natural-resource topics (frequent proposal subjects)."),
        (r"paris (agreement|accord|aligned)", "Paris climate alignment."),
        (r"spills?", "Environmental releases (oil spills)."),
    ],
    "community": [
        (r"communit(y|ies)(?! bank)(?! and corporate bank)", "Excludes JPM's 'Consumer & Community Banking' segment name."),
        (r"philanthrop(y|ic)|charitable|charit(y|ies)|donations?|non-?profits?", "Giving."),
        (r"volunteer(s|ing|ism)?", "Employee volunteering."),
        (r"human rights", "Human-rights policy and proposals."),
        (r"social (impact|responsibility|justice)", "Broader social purpose."),
        (r"societ(y|al)", "Benefit to society."),
        (r"economic (opportunity|mobility|inclusion)", "Community economic development (JPM AdvancingCities etc.)."),
        (r"small business(es)?", "Community economic support."),
    ],
    "shareholders": [
        (r"shareholder value|stockholder value|value for (our )?(share|stock)holders",
         "Bare 'shareholder(s)' excluded: procedural ('annual meeting of shareholders')."),
        (r"(total )?(shareholder|stockholder) returns?|\btsr", "TSR: the standard long-term incentive metric."),
        (r"earnings per share|\beps", "EPS: common annual-bonus metric."),
        (r"return on (equity|invested capital|capital( employed)?|assets|tangible common equity)|\broe\b|\broic\b|\brotce\b|\broce\b",
         "Capital-efficiency metrics."),
        (r"free cash flow|operating cash flow|cash flow", "Cash generation metrics."),
        (r"operating (income|margin|profit)|net income|pre-?tax (income|margin)|ebitda", "Profit metrics."),
        (r"revenues?|net sales|sales growth", "Top-line metrics."),
        (r"profit(s|ability|able)?|margins?", "Profitability."),
        (r"dividends?|(share|stock) (repurchases?|buybacks?)|capital returns?", "Capital returned to shareholders."),
        (r"capital (discipline|allocation)", "Capital discipline (energy firms post-2020)."),
        (r"stock price|share price|market capitali[sz]ation", "Market value."),
    ],
    "integrity": [
        (r"ethic(s|al|ally)", "Core term."),
        (r"integrity", "Core term."),
        (r"(?<!reporting )compliance",
         "Legal/regulatory compliance. Excludes 'Section 16(a) beneficial ownership reporting compliance' boilerplate."),
        (r"political (contributions?|spending|activity|activities)|lobbying",
         "Political-spending and lobbying disclosure: almost always transparency/accountability proposals, hence integrity, not community."),
        (r"code of (business )?(conduct|ethics)", "Formal codes."),
        (r"transparen(t|cy)", "Disclosure/transparency."),
        (r"accountab(le|ility)", "Accountability."),
        (r"clawbacks?|recoupment|malus|forfeiture provisions?", "Pay-side integrity: recovering pay for misconduct."),
        (r"misconduct|wrongdoing|fraud|bribery|corruption|whistle-?blow(er|ing)", "Misconduct and controls."),
        (r"risk culture|conduct risk|tone at the top", "Bank conduct and culture."),
        (r"honest(y|ly)?|trustworth(y|iness)", "Bare 'trust' excluded: legal trusts in ownership tables."),
        # Excluded: "governance" - committee names and section headings
        # ("Nominating and Governance Committee") dominate every proxy.
    ],
    "safety": [
        (r"safety", "Core term."),
        (r"safe(?! harbor)(?! harbour)", "Excludes the forward-looking-statement 'safe harbor' boilerplate."),
        (r"injur(y|ies)|fatalit(y|ies)|recordable|lost[- ]time", "Safety outcome metrics (often in energy bonus scorecards)."),
        (r"process safety|personnel safety|workplace safety|occupational", "Operational safety."),
        (r"incident rates?|serious incidents?|\bsif\b", "Safety incident metrics."),
        (r"\bosha\b", "US workplace-safety regulator."),
        (r"product (quality and )?safety|patient safety|food safety|drug safety", "Product/patient safety."),
    ],
    "innovation": [
        (r"innovat(ion|ions|ive|e|ing)", "Core term."),
        (r"research and development|r&d", "R&D investment."),
        (r"technolog(y|ies|ical)", "Technology. Sector levels differ (MSFT); within-firm change is the focus."),
        (r"new products?|product launch(es)?|pipeline of (new )?(medicines|products|drugs)",
         "New products. Bare 'pipeline' excluded: oil and gas pipelines."),
        (r"patents?|intellectual property", "IP output."),
        (r"digital|artificial intelligence|\bai\b|machine learning|cloud", "Digital/AI transformation."),
        (r"transformation(al)?|breakthrough", "Transformation language."),
    ],
}


def compiled() -> dict:
    """{category: [compiled regex, ...]} with word boundaries added."""
    return {cat: [re.compile(rf"\b(?:{pat})\b") for pat, _ in terms]
            for cat, terms in THEME_TERMS.items()}


def as_rows() -> list:
    """Flat list for documentation export."""
    return [{"category": cat, "term_regex": pat, "note": note}
            for cat, terms in THEME_TERMS.items() for pat, note in terms]
