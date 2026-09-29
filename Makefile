PYTHON ?= python
CIK ?=

.PHONY: setup smoke demo test evaluate fetch figures

setup:
	pip install -e . && pip install pytest

smoke:
	$(PYTHON) -m sec_business_evidence smoke

demo:
	$(PYTHON) -m sec_business_evidence demo

test:
	$(PYTHON) -m pytest -q

evaluate:
	$(PYTHON) -m sec_business_evidence flags --evidence examples/output/northwind-demo-corp/evidence.json

figures:
	$(PYTHON) tools/render_figures.py

# Public API access. Prints the SEC fair-access terms URL first. Never run in tests or CI.
# Requires SEC_USER_AGENT set to a descriptive value naming you and a contact address.
fetch:
	@echo "SEC EDGAR access terms: https://www.sec.gov/os/accessing-edgar-data"
	$(PYTHON) -m sec_business_evidence fetch --cik "$(CIK)"
