# Evaluation

There is no predictive model and therefore no accuracy metric. Evaluation means: does the selection logic behave as specified on the failure cases, and does every output number trace to a filing.

## Local test run (2026-09-27)

```
python -m pytest -q
66 passed in 2.57s
```

Python 3.10.11, Windows; CI runs the same suite on Ubuntu with Python 3.10, 3.11 and 3.12.

## What the tests cover

| Area | Behaviour locked by tests |
|---|---|
| Fixture | regeneration is byte-identical to the committed files; identifiers are obviously synthetic |
| Loading | USD values are integers; fractional USD rejected; non-money units preserved; schema errors on missing keys and bad dates |
| Chronology | facts filed after the analysis date are excluded; a later-filed 10-K/A never enters an earlier analysis; the amendment supersedes the original once filed; same-day amendment outranks the original |
| Deduplication | identical facts across filings collapse to the earliest filing; differing values are kept for versioning |
| Leakage | perturbing every fact filed after D leaves the evidence document byte-identical |
| Periods | annual, quarterly, instant, other classification; annual vs quarterly comparison raises; quarterly facts never enter fiscal-year ratios |
| Units | mixed units raise; `shares` facts are ignored when picking money inputs |
| Ratios | hand-computed values for all six; zero denominator gives null with a reason; missing input gives null with a reason; citations carry accession, tag and unit |
| Flags | rules load; gt and delta operators fire and cite both years; accusatory or malformed configs are rejected |
| Summary | deterministic; cites inputs; unavailable ratios are reported, not invented; the llm backend is not wired |
| Evidence | URL patterns; malformed accession rejected; ids unique; every flag cites evidence present in the document; flow has the four nodes |
| Cache | round trip; tamper detection; staleness by age; missing entry names the fix |
| Client | missing `SEC_USER_AGENT` exits 2 and prints the terms URL; blocked network raises and caches nothing; User-Agent header sent; limiter sleeps |
| CLI | smoke writes validated output and a manifest; demo writes three issuers and the portfolio flow; analyze respects `--as-of`; missing inputs exit 2; figures render |

## Demo output summary

Computed by `make demo` on synthetic fixture v1, seed 42, analysis date 2025-06-30, not a benchmark result:

- Northwind Demo Corp: 4 fiscal years, 4 facts superseded by the 10-K/A, 31 duplicates dropped, 0 review flags.
- Bluewater Demo Holdings: 4 fiscal years, 29 duplicates dropped, 4 review flags (revenue_growth_large_move FY2022; dso_lengthened, receivables_outpace_revenue, cash_conversion_low FY2023).
- Granite Demo Industries: 4 fiscal years, 33 duplicates dropped, 6 review flags (current_ratio_thin FY2023; revenue_decline, dso_lengthened, receivables_outpace_revenue, cash_conversion_low, current_ratio_thin FY2024).

The flags fire because the fixture was authored to trip them. They say nothing about any real company.

## Figures

`docs/figures/revenue_by_year.svg`, `dso_by_year.svg`, `ocf_to_net_income.svg` (from the demo output) and `pipeline.svg` (selection order). Rendered by `tools/render_figures.py`.
