"""Filing chronology, point-in-time selection, restatement versioning, leakage."""

from __future__ import annotations

import copy
import json
from datetime import date

from conftest import FY2023, make_fact
from sec_business_evidence.facts.load import facts_from_companyfacts
from sec_business_evidence.facts.select import apply_versioning, deduplicate, point_in_time
from sec_business_evidence.pipeline import analyze


def _revenue(result, fy: int):
    r = next(x for x in result.ratios_by_year[fy] if x.name == "receivables_to_revenue")
    return next(c for c in r.inputs if c.tag == "Revenues")


def test_point_in_time_excludes_filings_after_analysis_date():
    early = make_fact("Revenues", 100, FY2023[1], FY2023[0], filed=date(2024, 2, 25))
    late = make_fact("Revenues", 97, FY2023[1], FY2023[0], filed=date(2025, 3, 15), form="10-K/A",
                     accession="9999999001-25-000009")
    known = point_in_time([early, late], date(2024, 12, 31))
    assert known == [early]


def test_later_filed_restatement_does_not_enter_earlier_analysis(northwind_doc):
    before = analyze(northwind_doc, date(2025, 3, 1))
    after = analyze(northwind_doc, date(2025, 6, 30))
    rev_before = _revenue(before, 2023)
    rev_after = _revenue(after, 2023)
    assert rev_before.form == "10-K" and rev_after.form == "10-K/A"
    assert rev_after.value < rev_before.value
    assert rev_after.filed == "2025-03-15" and rev_before.filed <= "2025-03-01"


def test_amendment_supersedes_original_for_same_period_once_filed():
    original = make_fact("Revenues", 100, FY2023[1], FY2023[0], filed=date(2024, 2, 25))
    amended = make_fact("Revenues", 97, FY2023[1], FY2023[0], filed=date(2025, 3, 15), form="10-K/A",
                        accession="9999999001-25-000009")
    current, superseded = apply_versioning([original, amended])
    assert current == [amended]
    assert superseded == [original]


def test_same_day_amendment_outranks_original():
    same_day = date(2024, 2, 25)
    original = make_fact("Revenues", 100, FY2023[1], FY2023[0], filed=same_day, accession="9999999001-24-000001")
    amended = make_fact("Revenues", 98, FY2023[1], FY2023[0], filed=same_day, form="10-K/A",
                        accession="9999999001-24-000000")
    current, _ = apply_versioning([original, amended])
    assert current[0].value == 98


def test_identical_facts_across_filings_are_deduplicated_to_earliest():
    first = make_fact("Revenues", 100, FY2023[1], FY2023[0], filed=date(2024, 2, 25), accession="9999999001-24-000001")
    repeat = make_fact("Revenues", 100, FY2023[1], FY2023[0], filed=date(2025, 2, 25), accession="9999999001-25-000002")
    kept, dropped = deduplicate([repeat, first])
    assert kept == [first] and dropped == [repeat]


def test_differing_values_are_not_treated_as_duplicates():
    a = make_fact("Revenues", 100, FY2023[1], FY2023[0], accession="9999999001-24-000001")
    b = make_fact("Revenues", 101, FY2023[1], FY2023[0], accession="9999999001-25-000002", filed=date(2025, 2, 25))
    kept, dropped = deduplicate([a, b])
    assert len(kept) == 2 and dropped == []


def test_fixture_comparatives_are_reported_as_duplicates(northwind_doc):
    result = analyze(northwind_doc, date(2025, 6, 30))
    assert result.selection["facts_duplicates_dropped"] > 0
    assert result.selection["facts_superseded"] >= 2  # restated revenue and net income


def test_perturbing_facts_filed_after_analysis_date_does_not_change_output(northwind_doc):
    as_of = date(2024, 12, 31)
    baseline = json.dumps(analyze(northwind_doc, as_of).evidence_json(), sort_keys=True)
    mutated = copy.deepcopy(northwind_doc)
    touched = 0
    for tag in mutated["facts"]["us-gaap"].values():
        for rows in tag["units"].values():
            for row in rows:
                if date.fromisoformat(row["filed"]) > as_of:
                    row["val"] = int(row["val"]) * 7 + 1
                    touched += 1
    assert touched > 0
    assert json.dumps(analyze(mutated, as_of).evidence_json(), sort_keys=True) == baseline


def test_facts_in_scope_are_all_filed_on_or_before_analysis_date(northwind_doc):
    as_of = date(2023, 6, 1)
    result = analyze(northwind_doc, as_of)
    assert result.facts_in_scope
    assert all(f.filed <= as_of for f in result.facts_in_scope)
    assert len(facts_from_companyfacts(northwind_doc)) > len(result.facts_in_scope)
