# Method

## 1. Fact snapshot

`facts.model.FactSnapshot` (frozen): `cik, accession, form, filed, period_start, period_end, fy, fp, taxonomy, tag, unit, value, frame`. USD values are integers (whole dollars as EDGAR reports them). A fact's *identity* is `(taxonomy, tag, unit, period_start, period_end)`: the reported quantity, independent of which filing carried it.

Period kind from duration in days: instant (no start), annual (350 to 380 days), quarterly (80 to 100 days), other.

## 2. Selection, in order

1. **Point in time.** For analysis date D keep facts with `filed <= D`. A restatement filed after D does not exist yet for that analysis.
2. **Versioning.** Group by identity. If values differ within a group, the latest filed wins (an amendment outranks an original filed the same day). A 10-K/A therefore supersedes the 10-K for the same period once D passes its filing date. Losers are counted as `facts_superseded`.
3. **Deduplication.** Identical (identity, value) pairs collapse to the earliest filing that reported them, so a comparative column in a later 10-K is attributed to the filing that first disclosed the number. Dropped rows are counted as `facts_duplicates_dropped`.

## 3. Fiscal year assembly

Annual duration facts are grouped by period end. Each group takes the smallest `fy` seen (a comparative column is stamped with the later filing's `fy`). Concepts map to tags through `configs/tags.yaml`, first tag present wins, money units only. Instants are matched on the same period end date. Quarterly facts never enter fiscal-year ratios; `require_compatible` raises `PeriodMismatchError` if an annual and a quarterly duration are ever compared, and `require_same_unit` raises `UnitMismatchError` on mixed units.

## 4. Ratios

| Name | Definition | Unit |
|---|---|---|
| revenue_growth | (revenue_t - revenue_{t-1}) / revenue_{t-1} | fraction |
| receivables_to_revenue | receivables_end / revenue | fraction |
| dso | receivables_end / revenue * 365 | days |
| ocf_to_net_income | operating cash flow / net income | ratio |
| current_ratio | current assets / current liabilities | ratio |
| debt_to_equity | (LongTermDebtNoncurrent + DebtCurrent) / stockholders equity | ratio |

Division by zero returns `value: null` with `reason: "zero denominator: ..."`; a missing concept returns `value: null` with `reason: "missing input: ..."`. Every `RatioResult` carries `inputs`, a tuple of `Citation` objects (`id, cik, accession, form, filed, tag, unit, value, period, fy, fp`). Citation id format: `E:{accession-without-dashes}:{tag}:{period_end}`.

## 5. Review flags

Rules live in `configs/flags.yaml`: `id, ratio, op, threshold, message`. Operators: `gt`, `lt`, `abs_gt`, `delta_gt`, `delta_lt` (delta against the prior fiscal year; skipped when no prior exists). Messages must begin with a description of a change to review; the loader rejects accusatory vocabulary. A fired flag carries the citation ids of the current ratio's inputs and, for delta rules, the prior year's inputs too. Thresholds shipped are illustrative starting points, not calibrated.

## 6. Summary

`TemplateBackend` writes one sentence per ratio of the latest fiscal year with inline citation ids, then one sentence per flag. Identical inputs give identical text. `LlmAdapter` is an interface with no provider; `get_backend("llm")` raises `ConfigurationError`. Any future adapter must return citation ids verbatim from the ratio inputs.

## 7. Evidence and flow documents

`evidence.json`: `schemaVersion, mode, evidence_status, issuer, as_of, url_patterns, selection, fiscal_years[].ratios[], flags[], summary[], evidence[]` where each evidence entry is a citation plus EDGAR URLs built from the accession:

```
filing_index   https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/{accn}-index.htm
filing_folder  https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/
company_browse https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik10}&type={form}&dateb=&owner=include&count=40
companyfacts   https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json
```

`flow.json`: `{schemaVersion: 1, mode: "synthetic-demo", issuer, fiscal_year, nodes: [revenue, receivables, cash, liabilities], edges: [...]}`. Edges: revenue to receivables (receivables_to_revenue), receivables to cash (dso), revenue to cash (ocf_to_net_income), cash to liabilities (current_ratio), liabilities to revenue (debt_to_equity). Every node and edge lists `citation_ids`; edges list the `flag_ids` of rules that fired on their ratio.

## 8. Ingest

`EdgarClient` requires a descriptive User-Agent from `SEC_USER_AGENT`, sleeps to stay at or under 10 requests per second, and writes each response into `JsonCache` as an envelope `{envelope_version, key, url, retrieved_at, sha256, payload}`. `get()` re-hashes the payload and raises `CacheError` on mismatch; `get_fresh()` raises when the entry is older than a maximum age. The network function `http_get_json` is a module-level callable so tests replace it with one that raises.

## Settings taken from the source paper

None. This is an original project with no source paper.
