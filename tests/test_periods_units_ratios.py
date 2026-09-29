"""Duration compatibility, unit checks, and the six ratios on hand-built facts."""

from __future__ import annotations

from datetime import date

import pytest

from conftest import FY2023, FY2024, TAGS, annual_set, make_fact
from sec_business_evidence.errors import PeriodMismatchError, UnitMismatchError
from sec_business_evidence.facts.model import PeriodKind, period_kind
from sec_business_evidence.facts.select import require_compatible, require_same_unit, safe_div
from sec_business_evidence.ratios.compute import (
    collect_fiscal_years, compute_all, current_ratio, debt_to_equity, dso, load_concept_map,
    ocf_to_net_income, receivables_to_revenue, revenue_growth,
)

CMAP = load_concept_map(TAGS)


def _year(facts):
    years = collect_fiscal_years(facts, CMAP)
    assert len(years) == 1
    return years[0]


def test_period_kind_classification():
    assert period_kind(date(2024, 1, 1), date(2024, 12, 31)) is PeriodKind.ANNUAL
    assert period_kind(date(2023, 1, 1), date(2023, 12, 31)) is PeriodKind.ANNUAL  # 364 days
    assert period_kind(date(2024, 1, 1), date(2024, 3, 31)) is PeriodKind.QUARTERLY
    assert period_kind(None, date(2024, 12, 31)) is PeriodKind.INSTANT
    assert period_kind(date(2024, 1, 1), date(2024, 6, 30)) is PeriodKind.OTHER  # six months


def test_annual_and_quarterly_cannot_be_compared():
    annual = make_fact("Revenues", 1000, FY2024[1], FY2024[0])
    quarter = make_fact("Revenues", 250, date(2024, 3, 31), date(2024, 1, 1), form="10-Q")
    with pytest.raises(PeriodMismatchError):
        require_compatible(annual, quarter)
    require_compatible(annual, make_fact("Revenues", 900, FY2023[1], FY2023[0]))  # no raise


def test_quarterly_facts_never_enter_fiscal_year_ratios():
    facts = annual_set() + [
        make_fact("Revenues", 250, date(2024, 3, 31), date(2024, 1, 1), form="10-Q", fp="Q1"),
        make_fact("AccountsReceivableNetCurrent", 999_999, date(2024, 3, 31), form="10-Q", fp="Q1"),
    ]
    year = _year(facts)
    assert year.duration["revenue"].value == 1_000_000
    assert year.instant["receivables"].value == 100_000


def test_mixed_units_are_rejected():
    usd = make_fact("Revenues", 1000, FY2024[1], FY2024[0])
    shares = make_fact("Revenues", 1000, FY2024[1], FY2024[0], unit="shares")
    with pytest.raises(UnitMismatchError):
        require_same_unit(usd, shares)


def test_non_money_units_are_ignored_when_picking_inputs():
    facts = annual_set() + [make_fact("Revenues", 5, FY2024[1], FY2024[0], unit="shares")]
    assert _year(facts).duration["revenue"].unit == "USD"


def test_safe_div_guards_zero():
    assert safe_div(1, 0) is None
    assert safe_div(1, 4) == 0.25


def test_revenue_growth_value_and_citations():
    prior = _year(annual_set(revenue=800_000, year=FY2023, accession="9999999001-24-000001", filed=date(2024, 2, 25)))
    cur = _year(annual_set(revenue=1_000_000))
    r = revenue_growth(cur, prior)
    assert r.value == pytest.approx(0.25)
    assert [c.tag for c in r.inputs] == ["Revenues", "Revenues"]
    assert {c.accession for c in r.inputs} == {"9999999001-25-000001", "9999999001-24-000001"}
    assert all(c.unit == "USD" for c in r.inputs)


def test_revenue_growth_without_prior_is_unavailable_with_reason():
    r = revenue_growth(_year(annual_set()), None)
    assert r.value is None and "prior" in r.reason


def test_receivables_to_revenue_and_dso():
    year = _year(annual_set(revenue=1_000_000, receivables=100_000))
    assert receivables_to_revenue(year).value == pytest.approx(0.10)
    assert dso(year).value == pytest.approx(36.5)
    assert dso(year).unit == "days"


def test_ocf_to_net_income_and_current_ratio():
    year = _year(annual_set(ocf=120_000, net_income=100_000, current_assets=300_000, current_liabilities=200_000))
    assert ocf_to_net_income(year).value == pytest.approx(1.2)
    assert current_ratio(year).value == pytest.approx(1.5)


def test_debt_to_equity_sums_both_debt_components():
    year = _year(annual_set(debt_nc=150_000, debt_c=50_000, equity=400_000))
    r = debt_to_equity(year)
    assert r.value == pytest.approx(0.5)
    assert {c.tag for c in r.inputs} == {"LongTermDebtNoncurrent", "DebtCurrent", "StockholdersEquity"}


def test_debt_to_equity_with_one_component_missing_still_computes():
    facts = [f for f in annual_set(debt_nc=150_000, equity=300_000) if f.tag != "DebtCurrent"]
    assert debt_to_equity(_year(facts)).value == pytest.approx(0.5)


def test_zero_denominator_yields_none_with_reason():
    year = _year(annual_set(net_income=0))
    r = ocf_to_net_income(year)
    assert r.value is None and "zero denominator" in r.reason
    assert len(r.inputs) == 2  # citations still carried


def test_missing_input_yields_none_without_exception():
    facts = [f for f in annual_set() if f.tag != "NetCashProvidedByUsedInOperatingActivities"]
    r = ocf_to_net_income(_year(facts))
    assert r.value is None and "missing input" in r.reason and r.inputs == ()


def test_compute_all_produces_six_ratios_per_year():
    facts = annual_set(year=FY2023, accession="9999999001-24-000001", filed=date(2024, 2, 25)) + annual_set()
    out = compute_all(collect_fiscal_years(facts, CMAP))
    assert sorted(out) == [2023, 2024]
    assert [r.name for r in out[2024]] == [
        "revenue_growth", "receivables_to_revenue", "dso", "ocf_to_net_income", "current_ratio", "debt_to_equity"]


def test_unit_mismatch_in_ratio_inputs_raises():
    facts = [f for f in annual_set() if f.tag != "AccountsReceivableNetCurrent"]
    facts.append(make_fact("AccountsReceivableNetCurrent", 100, FY2024[1], unit="EUR"))
    cmap = load_concept_map(TAGS)
    cmap = type(cmap)(concepts=cmap.concepts, money_units=frozenset({"USD", "EUR"}))
    year = collect_fiscal_years(facts, cmap)[0]
    with pytest.raises(UnitMismatchError):
        receivables_to_revenue(year)
