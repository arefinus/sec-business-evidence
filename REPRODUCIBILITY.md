# Reproducibility

Release date 2026-09-27. Python 3.10, 3.11 or 3.12. Dependencies: numpy, pandas, pyyaml, pytest.

## Exact commands

```
pip install -e . && pip install pytest
python tools/make_fixture.py                 # writes examples/fixtures/v1/ (seed 42)
python -m sec_business_evidence smoke        # runs/smoke/: evidence.json, flow.json, run_manifest.yaml
python -m sec_business_evidence demo         # examples/output/: three issuers + demo_flow.json + run_manifest.yaml
python tools/render_figures.py               # docs/figures/*.svg from examples/output
python -m pytest -q
```

## Seeds

The only randomness is in the fixture generator (`numpy.random.default_rng(seed + cik % 1000)`, seed 42). `tests/test_fixture_and_load.py` asserts that regeneration reproduces the committed files byte for byte (via `manifest.json` hashes). Everything downstream of the fixture is deterministic.

## Analysis date

Smoke and demo use analysis date `2025-06-30`. Under that date the Northwind 10-K/A filed 2025-03-15 is known, so its restated FY2023 revenue and net income supersede the original 10-K values. Running `analyze --as-of 2025-03-01` on the same fixture uses the original values; `tests/test_chronology.py` locks this behaviour.

## What is reproduced

Nothing from any paper. There are no `paper-reported` or `reproduced` values. All committed outputs are `demo` evidence computed on the synthetic fixture.

## What is not reproduced

No real registrant has been analysed in this repository. To analyse one:

```
export SEC_USER_AGENT="Your Name your.contact@example.invalid"
make fetch CIK=0000320193                       # prints the SEC terms URL first
python -m sec_business_evidence analyze --companyfacts cache/CIK0000320193_companyfacts.json --as-of 2025-06-30 --out runs/cik320193
```

Results depend on the retrieval date because the APIs are updated continuously; the cache envelope records `retrieved_at` and `sha256`, and the run manifest records the hash of the input file.

## Run manifest

Every smoke, demo and analyze run writes `run_manifest.yaml` with `schema_version`, `project_id`, `run_id`, `status`, `mode`, `evidence_status`, `git_commit: null`, `data` (source id, version, split manifest hash, sample counts), `configuration_hash` (sha256 over `configs/flags.yaml` and `configs/tags.yaml`), `seed`, `environment`, and timestamps.
