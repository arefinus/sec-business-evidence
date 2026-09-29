# sec-business-evidence

A business analyst reading US public-company disclosures needs to know what changed in revenue, receivables, cash flow and liabilities, and which filing supports each number. This code ingests SEC EDGAR company facts with an on-disk cache, selects facts point-in-time, computes six ratios whose every input carries its accession number, and raises threshold-based review flags with a citation trail. There is no fraud classifier here and no fraud label dataset; nothing in this repository produces a verdict.

**Status:** `demo_ready` (runs end to end on authored synthetic fixtures; no real-data evaluation performed in this repository).

## Problem and user

The user is a business analyst studying disclosures. The question is not "is this company good or bad" but "what moved, by how much, against which prior period, and where in EDGAR is the number that says so". Two things make that hard with the raw companyfacts feed: the same quantity is reported by several filings (comparative columns, amendments), and quarterly and annual durations sit side by side under one tag. This repository resolves both before any ratio is computed, and keeps the accession of every input attached to every output.

## Demo

```
python tools/make_fixture.py            # regenerate the synthetic fixture (seed 42)
python -m sec_business_evidence demo    # analyse three fictional issuers -> examples/output/
python -m sec_business_evidence flags --evidence examples/output/granite-demo-industries/evidence.json
python tools/render_figures.py          # docs/figures/*.svg
```

Committed demo output, computed by `make demo` on synthetic fixture v1, seed 42, not a benchmark result:

| Issuer (fictional) | Facts in scope | Duplicates dropped | Superseded by 10-K/A | Review flags |
|---|---|---|---|---|
| Northwind Demo Corp | 120 | 31 | 4 | 0 |
| Bluewater Demo Holdings | 112 | 29 | 0 | 4 |
| Granite Demo Industries | 120 | 33 | 0 | 6 |

Each issuer directory holds `evidence.json` (ratios, flags, summary sentences, one evidence entry per cited fact with EDGAR URLs), `flow.json` (the four-node graph for the portfolio), `summary.md` and `ratios.csv`. `examples/output/demo_flow.json` is the portfolio copy.

![pipeline](docs/figures/pipeline.svg)

## Implementation status

Works:

- `ingest/`: companyfacts and submissions client with a required descriptive User-Agent from `SEC_USER_AGENT`, a 10 requests per second limiter that sleeps, and a JSON cache recording URL, retrieval time and sha256 with staleness and tamper checks.
- `facts/`: fact snapshot dataclass; point-in-time selection; amendment versioning; deduplication; annual, quarterly and instant classification; unit checks; zero-guarded division.
- `ratios/`: revenue growth, receivables to revenue, DSO, operating cash flow to net income, current ratio, debt to equity, each with citation objects; review flags from `configs/flags.yaml`; deterministic template summariser with inline citation ids.
- CLI `python -m sec_business_evidence {smoke,demo,fetch,analyze,flags,figures}`; run manifest on every run.

Stub by design:

- The language-model adapter (`ratios/summarise.py: LlmAdapter`) is an interface only. No provider is wired in and `get_backend("llm")` raises.

Not present, on purpose:

- No fraud classifier, no fraud labels, no scoring of issuers. Flags are threshold rules that say "review this change".

## Quickstart (offline, CPU, under a minute)

```
pip install -e . && pip install pytest
make smoke        # first synthetic issuer, validates output schema, writes runs/smoke/run_manifest.yaml
make demo         # all three synthetic issuers -> examples/output/
make test         # python -m pytest -q
```

No network is used by `smoke`, `demo` or the tests. `make fetch CIK=...` is the only command that touches the network; it prints the SEC access terms URL first and refuses to run without `SEC_USER_AGENT`.

## Data

See [DATA_CARD.md](DATA_CARD.md). Real data comes from the SEC EDGAR data APIs (`https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` and `https://data.sec.gov/submissions/CIK##########.json`). No API key exists; the SEC fair-access policy requires a descriptive User-Agent and at most 10 requests per second. No real company data is shipped. The fixture under `examples/fixtures/v1/` is authored synthetic data for three fictional issuers with CIKs in the 9999999xxx range (see `FIXTURE.md` there).

## Architecture / method

```
companyfacts JSON -> point in time (filed <= D) -> amendment versioning -> deduplicate
                  -> annual / quarterly / instant split -> ratios with citations -> review flags
                  -> template summary -> evidence.json, flow.json, summary.md, ratios.csv
```

Selection rules, in order: (1) only facts from filings filed on or before the analysis date D are known; (2) for one reported quantity (tag, unit, period) with differing values, the latest filed filing wins, so a 10-K/A supersedes the 10-K for the same period once its filing date has passed; (3) identical values carried by several filings collapse to the earliest filing that reported them. Ratios combine only annual duration facts with fiscal-year-end instants, all in the same money unit. Details in [docs/method.md](docs/method.md).

EDGAR URL patterns are built from the accession only (documented in `evidence.py`): `https://www.sec.gov/Archives/edgar/data/{cik}/{accession-without-dashes}/{accession}-index.htm`.

## Train, validate, test

There is no model to train. Tests (`python -m pytest -q`) cover filing chronology, units, period mismatch rejection, deduplication, restatement versioning, missing values, stale and tampered cache detection, evidence link formation, the blocked-network fallback (fetch without the environment variable exits 2; the network function is replaced with one that raises) and point-in-time leakage (facts filed after D are perturbed and the output must not change).

## Results and provenance

Everything under `examples/output/` carries `"evidence_status": "demo"` and `"mode": "synthetic-demo"`. It is computed by `make demo` on synthetic fixture v1, seed 42, and is not a benchmark result. No `paper-reported` or `reproduced` values exist in this repository. The review flags in the demo fire because the fixture was authored to exercise each rule (a revenue decline, a receivables build-up, low cash conversion, a thin current ratio), not because anything was measured about a real company.

## Limitations

- Ratios use the first matching tag per concept (`configs/tags.yaml`). Real filers vary in tag choice; unmatched concepts appear as `value: null` with a `reason`, never as a guess.
- Fiscal year grouping keys on the annual period end date; issuers with 52/53-week years or changed year ends need review.
- Debt to equity sums `LongTermDebtNoncurrent` and `DebtCurrent` when present; it does not reconstruct total debt from leases or other instruments.
- Thresholds in `configs/flags.yaml` are illustrative starting points, not calibrated on any population.
- The synthetic fixture is small and regular. It exercises the selection logic; it says nothing about real disclosure behaviour.
- Money values are whole US dollars as EDGAR reports them (integers). No currency conversion is attempted; non-USD facts are excluded from the ratios.

## Contribution

`original_project`. Not derived from a publication and not built for a client. Business analytics research with an academic affiliation to Trine University.

## License and sources

MIT, copyright 2026 Md Sultanul Arefin Sourav. See [NOTICE.md](NOTICE.md). Data source terms: SEC EDGAR, https://www.sec.gov/os/accessing-edgar-data (applies to any use of `make fetch`; nothing fetched is redistributed here).
