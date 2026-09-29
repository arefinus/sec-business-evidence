from __future__ import annotations

import json
from datetime import date

import pytest
import yaml

from conftest import FLAGS, FY2023, annual_set
from sec_business_evidence.errors import ConfigurationError
from sec_business_evidence.evidence import edgar_urls, validate_evidence_schema, validate_flow_schema
from sec_business_evidence.pipeline import analyze
from sec_business_evidence.ratios.citation import RatioResult
from sec_business_evidence.ratios.compute import collect_fiscal_years, compute_all, load_concept_map
from sec_business_evidence.ratios.flags import FlagRule, evaluate_flags, load_flag_rules
from sec_business_evidence.ratios.summarise import get_backend, summarise
from conftest import TAGS


def _ratios(**overrides):
    prior = annual_set(year=FY2023, accession="9999999001-24-000001", filed=date(2024, 2, 25))
    return compute_all(collect_fiscal_years(prior + annual_set(**overrides), load_concept_map(TAGS)))


def test_flag_rules_load_and_never_use_forbidden_vocabulary():
    rules = load_flag_rules(FLAGS)
    assert len(rules) >= 5
    for r in rules:
        assert "fraud" not in r.message.lower()
        assert r.message.startswith("Review this change")


def test_gt_rule_fires_and_carries_citations():
    rules = [FlagRule("lev", "debt_to_equity", "gt", 0.4, "Review this change: leverage.")]
    flags = evaluate_flags(rules, _ratios(debt_nc=150_000, debt_c=50_000, equity=400_000))
    fy2024 = [f for f in flags if f.fiscal_year == 2024]
    assert len(fy2024) == 1 and fy2024[0].value == pytest.approx(0.5)
    assert len(fy2024[0].citation_ids) == 3


def test_rule_below_threshold_does_not_fire():
    rules = [FlagRule("lev", "debt_to_equity", "gt", 0.9, "Review this change: leverage.")]
    assert evaluate_flags(rules, _ratios()) == []


def test_delta_rule_needs_a_prior_year_and_cites_both():
    rules = [FlagRule("dso_up", "dso", "delta_gt", 10.0, "Review this change: DSO up.")]
    flags = evaluate_flags(rules, _ratios(receivables=200_000))  # 73 days vs 36.5 days
    assert [f.fiscal_year for f in flags] == [2024]
    assert flags[0].prior_value == pytest.approx(36.5)
    assert len(flags[0].citation_ids) == 4


def test_rule_with_unavailable_ratio_is_skipped():
    rules = [FlagRule("cc", "ocf_to_net_income", "lt", 0.6, "Review this change: cash conversion.")]
    assert evaluate_flags(rules, _ratios(net_income=0)) == []


def test_config_with_accusatory_message_is_rejected(tmp_path):
    bad = {"rules": [{"id": "x", "ratio": "dso", "op": "gt", "threshold": 1, "message": "Possible fraud here"}]}
    p = tmp_path / "flags.yaml"
    p.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_flag_rules(p)


def test_config_with_unknown_op_or_duplicate_id_is_rejected(tmp_path):
    p = tmp_path / "flags.yaml"
    p.write_text(yaml.safe_dump({"rules": [{"id": "x", "ratio": "dso", "op": "between", "threshold": 1, "message": "Review this change."}]}), encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_flag_rules(p)
    dup = {"rules": [{"id": "x", "ratio": "dso", "op": "gt", "threshold": 1, "message": "Review this change."}] * 2}
    p.write_text(yaml.safe_dump(dup), encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_flag_rules(p)


def test_template_summary_is_deterministic_and_cites_inputs():
    ratios = _ratios()
    a = summarise("Northwind Demo Corp", ratios, [])
    b = summarise("Northwind Demo Corp", ratios, [])
    assert a == b
    ids = {c.id for rs in ratios.values() for r in rs for c in r.inputs}
    assert any(cid in " ".join(a) for cid in ids)
    assert any("No review flags" in s for s in a)


def test_unavailable_ratio_is_reported_not_invented():
    ratios = {2024: [RatioResult("dso", 2024, None, "days", (), "missing input: receivables")]}
    text = summarise("X", ratios, [])
    assert "not available" in text[0] and "missing input" in text[0]


def test_llm_backend_is_not_wired_and_unknown_backend_rejected():
    with pytest.raises(ConfigurationError):
        get_backend("llm")
    with pytest.raises(ConfigurationError):
        get_backend("oracle")
    assert get_backend("template").name == "template"


def test_edgar_url_patterns_are_well_formed():
    urls = edgar_urls("0000320193", "0000320193-24-000123", "10-K/A")
    assert urls["filing_index"] == "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/0000320193-24-000123-index.htm"
    assert urls["filing_folder"].endswith("/000032019324000123/")
    assert "CIK=0000320193" in urls["company_browse"] and "type=10-K&" in urls["company_browse"]
    assert urls["companyfacts_api"] == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"


def test_malformed_accession_is_rejected():
    with pytest.raises(ValueError):
        edgar_urls("0000320193", "320193-24-1", "10-K")


def test_evidence_document_validates_and_ids_are_unique(granite_doc):
    doc = analyze(granite_doc, date(2025, 6, 30)).evidence_json()
    json.dumps(doc)  # serialisable
    assert validate_evidence_schema(doc) == []
    ids = [e["id"] for e in doc["evidence"]]
    assert len(ids) == len(set(ids))
    assert doc["mode"] == "synthetic-demo" and doc["evidence_status"] == "demo"
    assert all(e["urls"]["filing_index"].startswith("https://www.sec.gov/Archives/edgar/data/9999999003/") for e in doc["evidence"])


def test_every_flag_cites_evidence_present_in_document(granite_doc):
    doc = analyze(granite_doc, date(2025, 6, 30)).evidence_json()
    known = {e["id"] for e in doc["evidence"]}
    assert doc["flags"], "granite fixture is designed to raise review flags"
    for f in doc["flags"]:
        assert f["citation_ids"] and set(f["citation_ids"]) <= known
        assert f["severity"] == "review"


def test_flow_document_has_the_four_nodes_and_cited_edges(northwind_doc):
    flow = analyze(northwind_doc, date(2025, 6, 30)).flow_json()
    assert validate_flow_schema(flow) == []
    assert [n["id"] for n in flow["nodes"]] == ["revenue", "receivables", "cash", "liabilities"]
    assert all(n["citation_ids"] for n in flow["nodes"])
    assert all(e["citation_ids"] for e in flow["edges"])
    assert validate_flow_schema(dict(flow, mode="live")) != []


def test_missing_values_in_fixture_are_surfaced_as_reasons(bluewater_doc):
    result = analyze(bluewater_doc, date(2025, 6, 30))
    r = next(x for x in result.ratios_by_year[2021] if x.name == "ocf_to_net_income")
    assert r.value is None and "operating_cash_flow" in r.reason
    d2e = next(x for x in result.ratios_by_year[2024] if x.name == "debt_to_equity")
    assert d2e.value is not None and "DebtCurrent" not in {c.tag for c in d2e.inputs}
