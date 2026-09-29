# Data

## Source

SEC EDGAR data APIs. See [../DATA_CARD.md](../DATA_CARD.md) for provider, terms, User-Agent requirement, rate limit and the absence of CORS.

## Synthetic fixture v1

Written by `tools/make_fixture.py` (seed 42) to `examples/fixtures/v1/`. Three fictional issuers, fiscal years 2021 to 2024, calendar year ends.

Per issuer and fiscal year the generator emits:

- three 10-Q filings (filed 10 May, 9 Aug, 8 Nov) with quarterly durations for revenue, net income and operating cash flow, and quarter-end instants for receivables, current assets and current liabilities;
- one 10-K (filed 25 Feb of the next year) with annual durations and year-end instants for the fiscal year and, from FY2022 on, the prior year as a comparative (same values, different accession);
- `dei:EntityCommonStockSharesOutstanding` in unit `shares`.

Designed irregularities:

| Issuer | Irregularity | Exercises |
|---|---|---|
| Northwind Demo Corp | 10-K/A filed 2025-03-15 restating FY2023 revenue (-3%) and net income (-10%) | amendment versioning, point-in-time selection |
| Bluewater Demo Holdings | FY2021 operating cash flow absent; no `DebtCurrent` tag at all | missing values, partial debt inputs |
| Granite Demo Industries | revenue decline and receivables build-up in FY2024 | review flags |

The percentages in the table are generator settings, not measured results.

## Counts

Computed by `make demo` on synthetic fixture v1, seed 42, not a benchmark result: Northwind 155 facts total, 120 in scope after versioning (4 superseded) and deduplication (31 dropped); Bluewater 141 total, 112 in scope (29 dropped); Granite 153 total, 120 in scope (33 dropped). Analysis date 2025-06-30.

## What is not here

No real registrant data. No fraud labels. No paper-reported values.
