from __future__ import annotations

import hashlib
import json

import pytest

from conftest import FIXTURE_DIR
from sec_business_evidence.errors import SchemaError
from sec_business_evidence.facts.load import facts_from_companyfacts, load_companyfacts, normalise_cik
from sec_business_evidence.synthetic import ISSUERS, build_companyfacts


def test_fixture_generation_is_deterministic():
    a, _ = build_companyfacts(ISSUERS[0], seed=42)
    b, _ = build_companyfacts(ISSUERS[0], seed=42)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_fixture_identifiers_are_obviously_synthetic():
    for spec in ISSUERS:
        assert spec.cik >= 9_999_999_000
        assert "Demo" in spec.name


def test_committed_fixture_matches_manifest_hashes():
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["seed"] == 42
    for name, digest in manifest["sha256"].items():
        text = (FIXTURE_DIR / name).read_text(encoding="utf-8").rstrip("\n")
        assert hashlib.sha256(text.encode("utf-8")).hexdigest() == digest, name


def test_committed_fixture_equals_regenerated_document():
    doc, _ = build_companyfacts(ISSUERS[0], seed=42)
    on_disk, _ = load_companyfacts(FIXTURE_DIR / "CIK9999999001_companyfacts.json")
    assert json.dumps(on_disk, sort_keys=True) == json.dumps(doc, sort_keys=True)


def test_flatten_produces_facts_with_provenance(northwind_doc):
    facts = facts_from_companyfacts(northwind_doc)
    assert len(facts) > 100
    f = facts[0]
    assert f.cik == "9999999001"
    assert f.accession.count("-") == 2
    assert f.form in {"10-K", "10-Q", "10-K/A"}


def test_money_values_are_integers(northwind_doc):
    for f in facts_from_companyfacts(northwind_doc):
        if f.unit == "USD":
            assert isinstance(f.value, int)


def test_non_money_units_are_preserved(northwind_doc):
    units = {f.unit for f in facts_from_companyfacts(northwind_doc)}
    assert "shares" in units and "USD" in units


def test_cik_is_normalised_to_ten_digits():
    assert normalise_cik(320193) == "0000320193"
    assert normalise_cik("9999999001") == "9999999001"
    with pytest.raises(SchemaError):
        normalise_cik("not-a-cik")


def test_missing_facts_key_is_a_schema_error():
    with pytest.raises(SchemaError):
        facts_from_companyfacts({"cik": 1})


def test_bad_date_is_a_schema_error():
    doc = {"cik": 1, "facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        {"end": "2024-13-45", "val": 1, "accn": "0000000001-24-000001", "form": "10-K", "filed": "2025-01-01"}]}}}}}
    with pytest.raises(SchemaError):
        facts_from_companyfacts(doc)


def test_fractional_usd_is_rejected_and_integral_float_is_coerced():
    base = {"end": "2024-12-31", "accn": "0000000001-24-000001", "form": "10-K", "filed": "2025-01-01"}
    ok = {"cik": 1, "facts": {"us-gaap": {"Revenues": {"units": {"USD": [dict(base, val=5.0)]}}}}}
    assert facts_from_companyfacts(ok)[0].value == 5 and isinstance(facts_from_companyfacts(ok)[0].value, int)
    bad = {"cik": 1, "facts": {"us-gaap": {"Revenues": {"units": {"USD": [dict(base, val=5.25)]}}}}}
    with pytest.raises(SchemaError):
        facts_from_companyfacts(bad)
