from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sec_business_evidence.facts.model import FactSnapshot  # noqa: E402
from sec_business_evidence.synthetic import ISSUERS, build_companyfacts  # noqa: E402

FIXTURE_DIR = ROOT / "examples" / "fixtures" / "v1"
FLAGS = ROOT / "configs" / "flags.yaml"
TAGS = ROOT / "configs" / "tags.yaml"


@pytest.fixture(scope="session")
def northwind_doc() -> dict:
    doc, _ = build_companyfacts(ISSUERS[0], seed=42)
    return doc


@pytest.fixture(scope="session")
def bluewater_doc() -> dict:
    doc, _ = build_companyfacts(ISSUERS[1], seed=42)
    return doc


@pytest.fixture(scope="session")
def granite_doc() -> dict:
    doc, _ = build_companyfacts(ISSUERS[2], seed=42)
    return doc


def make_fact(
    tag: str,
    value: int | float,
    end: date,
    start: date | None = None,
    *,
    accession: str = "9999999001-24-000001",
    form: str = "10-K",
    filed: date = date(2024, 2, 25),
    unit: str = "USD",
    fy: int | None = None,
    fp: str = "FY",
    taxonomy: str = "us-gaap",
) -> FactSnapshot:
    return FactSnapshot(
        cik="9999999001", accession=accession, form=form, filed=filed, period_start=start,
        period_end=end, fy=fy if fy is not None else end.year, fp=fp, taxonomy=taxonomy,
        tag=tag, unit=unit, value=value, frame=None,
    )


FY2023 = (date(2023, 1, 1), date(2023, 12, 31))
FY2024 = (date(2024, 1, 1), date(2024, 12, 31))


def annual_set(
    *,
    revenue: int = 1_000_000,
    receivables: int = 100_000,
    ocf: int = 120_000,
    net_income: int = 100_000,
    current_assets: int = 300_000,
    current_liabilities: int = 200_000,
    debt_nc: int = 150_000,
    debt_c: int = 50_000,
    equity: int = 400_000,
    year: tuple[date, date] = FY2024,
    accession: str = "9999999001-25-000001",
    filed: date = date(2025, 2, 25),
) -> list[FactSnapshot]:
    start, end = year
    kw = dict(accession=accession, filed=filed)
    return [
        make_fact("Revenues", revenue, end, start, **kw),
        make_fact("AccountsReceivableNetCurrent", receivables, end, **kw),
        make_fact("NetCashProvidedByUsedInOperatingActivities", ocf, end, start, **kw),
        make_fact("NetIncomeLoss", net_income, end, start, **kw),
        make_fact("AssetsCurrent", current_assets, end, **kw),
        make_fact("LiabilitiesCurrent", current_liabilities, end, **kw),
        make_fact("LongTermDebtNoncurrent", debt_nc, end, **kw),
        make_fact("DebtCurrent", debt_c, end, **kw),
        make_fact("StockholdersEquity", equity, end, **kw),
        make_fact("CashAndCashEquivalentsAtCarryingValue", 90_000, end, **kw),
        make_fact("Liabilities", 500_000, end, **kw),
    ]
