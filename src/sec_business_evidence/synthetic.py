"""Synthetic companyfacts and submissions documents for fictional issuers.

Authored demonstration data. Fictional identifiers. Not derived from any person, company,
account or dataset. Deterministic for a given seed. Used by tools/make_fixture.py and by
the test-suite. Values are whole US dollars stored as integers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np

FIXTURE_VERSION = "v1"
DEFAULT_SEED = 42
FISCAL_YEARS = (2021, 2022, 2023, 2024)


@dataclass(frozen=True)
class IssuerSpec:
    name: str
    cik: int
    base_revenue: int
    growth: tuple[float, ...]  # one per fiscal year after the first
    ar_ratio: tuple[float, ...]  # receivables / revenue per year
    margin: float
    cash_conversion: tuple[float, ...]
    current_liab_ratio: tuple[float, ...]
    restate_fy: int | None = None  # 10-K/A for this fiscal year
    omit: frozenset[tuple[str, int]] = frozenset()  # (tag, fy) pairs left out
    drop_tags: frozenset[str] = frozenset()


ISSUERS = (
    IssuerSpec(
        name="Northwind Demo Corp", cik=9_999_999_001, base_revenue=1_840_000_000,
        growth=(0.08, 0.11, 0.06), ar_ratio=(0.12, 0.12, 0.13, 0.13), margin=0.09,
        cash_conversion=(1.15, 1.05, 1.10, 1.02), current_liab_ratio=(0.22, 0.22, 0.23, 0.23),
        restate_fy=2023,
    ),
    IssuerSpec(
        name="Bluewater Demo Holdings", cik=9_999_999_002, base_revenue=640_000_000,
        growth=(0.31, 0.18, 0.09), ar_ratio=(0.10, 0.11, 0.16, 0.19), margin=0.06,
        cash_conversion=(0.95, 0.85, 0.55, 0.70), current_liab_ratio=(0.20, 0.21, 0.24, 0.26),
        omit=frozenset({("NetCashProvidedByUsedInOperatingActivities", 2021)}),
        drop_tags=frozenset({"DebtCurrent"}),
    ),
    IssuerSpec(
        name="Granite Demo Industries", cik=9_999_999_003, base_revenue=3_120_000_000,
        growth=(0.04, -0.02, -0.15), ar_ratio=(0.14, 0.14, 0.15, 0.20), margin=0.05,
        cash_conversion=(1.20, 1.10, 0.90, 0.40), current_liab_ratio=(0.30, 0.31, 0.36, 0.42),
    ),
)


def _accn(cik: int, filed: date, seq: int) -> str:
    return f"{cik:010d}-{filed.year % 100:02d}-{seq:06d}"


def _row(start: date | None, end: date, val: int, accn: str, fy: int, fp: str, form: str,
         filed: date, frame: str | None) -> dict[str, Any]:
    row: dict[str, Any] = {"end": end.isoformat(), "val": int(val), "accn": accn, "fy": fy, "fp": fp,
                           "form": form, "filed": filed.isoformat()}
    if start is not None:
        row["start"] = start.isoformat()
    if frame:
        row["frame"] = frame
    return row


def _annual_values(spec: IssuerSpec, rng: np.random.Generator) -> dict[int, dict[str, int]]:
    out: dict[int, dict[str, int]] = {}
    revenue = spec.base_revenue
    for i, fy in enumerate(FISCAL_YEARS):
        if i > 0:
            revenue = int(round(revenue * (1.0 + spec.growth[i - 1])))
        jitter = float(rng.uniform(0.97, 1.03))
        ni = int(round(revenue * spec.margin * jitter))
        ocf = int(round(ni * spec.cash_conversion[i]))
        ar = int(round(revenue * spec.ar_ratio[i]))
        cur_liab = int(round(revenue * spec.current_liab_ratio[i]))
        cur_assets = int(round(revenue * 0.34 * float(rng.uniform(0.98, 1.02))))
        cash = int(round(revenue * 0.09 * float(rng.uniform(0.9, 1.1))))
        debt_nc = int(round(revenue * (0.18 + 0.03 * i)))
        debt_c = int(round(revenue * 0.025))
        liabilities = cur_liab + debt_nc + int(round(revenue * 0.08))
        equity = int(round(revenue * (0.48 - 0.02 * i)))
        shares = int(round(120_000_000 * (1.0 + 0.01 * i)))
        out[fy] = {
            "Revenues": revenue, "NetIncomeLoss": ni,
            "NetCashProvidedByUsedInOperatingActivities": ocf,
            "AccountsReceivableNetCurrent": ar, "AssetsCurrent": cur_assets,
            "LiabilitiesCurrent": cur_liab, "Liabilities": liabilities,
            "StockholdersEquity": equity, "LongTermDebtNoncurrent": debt_nc,
            "DebtCurrent": debt_c, "CashAndCashEquivalentsAtCarryingValue": cash,
            "EntityCommonStockSharesOutstanding": shares,
        }
    return out


DURATION_TAGS = ("Revenues", "NetIncomeLoss", "NetCashProvidedByUsedInOperatingActivities")
INSTANT_TAGS = ("AccountsReceivableNetCurrent", "AssetsCurrent", "LiabilitiesCurrent", "Liabilities",
                "StockholdersEquity", "LongTermDebtNoncurrent", "DebtCurrent",
                "CashAndCashEquivalentsAtCarryingValue")
QUARTER_ENDS = ((3, 31), (6, 30), (9, 30))
QUARTER_FILED = ((5, 10), (8, 9), (11, 8))


def build_companyfacts(spec: IssuerSpec, seed: int = DEFAULT_SEED) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return (companyfacts document, list of filings) for one issuer."""
    rng = np.random.default_rng(seed + spec.cik % 1000)
    annual = _annual_values(spec, rng)
    facts: dict[str, dict[str, dict[str, Any]]] = {"us-gaap": {}, "dei": {}}
    filings: list[dict[str, Any]] = []

    def add(taxonomy: str, tag: str, unit: str, row: dict[str, Any]) -> None:
        if tag in spec.drop_tags:
            return
        body = facts[taxonomy].setdefault(tag, {"label": tag, "description": f"Synthetic {tag}", "units": {}})
        body["units"].setdefault(unit, []).append(row)

    seq = 0
    for i, fy in enumerate(FISCAL_YEARS):
        # Three 10-Q filings with quarterly durations and quarter-end instants.
        for q, ((m, d), (fm, fd)) in enumerate(zip(QUARTER_ENDS, QUARTER_FILED), start=1):
            filed = date(fy, fm, fd)
            seq += 1
            accn = _accn(spec.cik, filed, seq)
            filings.append({"accn": accn, "form": "10-Q", "filed": filed, "report": date(fy, m, d)})
            q_start = date(fy, m - 2, 1)
            q_end = date(fy, m, d)
            share = float(rng.uniform(0.22, 0.27))
            for tag in DURATION_TAGS:
                if (tag, fy) in spec.omit:
                    continue
                val = int(round(annual[fy][tag] * share))
                add("us-gaap", tag, "USD", _row(q_start, q_end, val, accn, fy, f"Q{q}", "10-Q", filed, f"CY{fy}Q{q}"))
            for tag in INSTANT_TAGS[:3]:
                val = int(round(annual[fy][tag] * float(rng.uniform(0.9, 1.1))))
                add("us-gaap", tag, "USD", _row(None, q_end, val, accn, fy, f"Q{q}", "10-Q", filed, f"CY{fy}Q{q}I"))
        # The 10-K, filed the following February, reports the year and the prior-year comparative.
        filed = date(fy + 1, 2, 25)
        seq += 1
        accn = _accn(spec.cik, filed, seq)
        filings.append({"accn": accn, "form": "10-K", "filed": filed, "report": date(fy, 12, 31)})
        for report_fy in ([fy - 1, fy] if i > 0 else [fy]):
            fy_start, fy_end = date(report_fy, 1, 1), date(report_fy, 12, 31)
            for tag in DURATION_TAGS:
                if (tag, report_fy) in spec.omit:
                    continue
                add("us-gaap", tag, "USD", _row(fy_start, fy_end, annual[report_fy][tag], accn, fy, "FY", "10-K", filed, f"CY{report_fy}"))
            for tag in INSTANT_TAGS:
                add("us-gaap", tag, "USD", _row(None, fy_end, annual[report_fy][tag], accn, fy, "FY", "10-K", filed, f"CY{report_fy}Q4I"))
        add("dei", "EntityCommonStockSharesOutstanding", "shares",
            _row(None, date(fy + 1, 2, 15), annual[fy]["EntityCommonStockSharesOutstanding"], accn, fy, "FY", "10-K", filed, None))
        # Optional amendment: restates revenue and net income for one fiscal year.
        if spec.restate_fy == fy:
            a_filed = date(fy + 2, 3, 15)
            seq += 1
            a_accn = _accn(spec.cik, a_filed, seq)
            filings.append({"accn": a_accn, "form": "10-K/A", "filed": a_filed, "report": date(fy, 12, 31)})
            restated_rev = int(round(annual[fy]["Revenues"] * 0.97))
            restated_ni = int(round(annual[fy]["NetIncomeLoss"] * 0.90))
            add("us-gaap", "Revenues", "USD", _row(date(fy, 1, 1), date(fy, 12, 31), restated_rev, a_accn, fy, "FY", "10-K/A", a_filed, f"CY{fy}"))
            add("us-gaap", "NetIncomeLoss", "USD", _row(date(fy, 1, 1), date(fy, 12, 31), restated_ni, a_accn, fy, "FY", "10-K/A", a_filed, f"CY{fy}"))

    doc = {"cik": spec.cik, "entityName": spec.name, "facts": facts,
           "_synthetic": {"generator": "tools/make_fixture.py", "seed": seed, "version": FIXTURE_VERSION,
                          "note": "Authored synthetic demonstration data. Fictional issuer. Not derived from any company."}}
    return doc, filings


def build_submissions(spec: IssuerSpec, filings: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(filings, key=lambda f: f["filed"], reverse=True)
    return {
        "cik": f"{spec.cik:010d}",
        "entityType": "operating",
        "name": spec.name,
        "sicDescription": "Synthetic demonstration issuer",
        "fiscalYearEnd": "1231",
        "filings": {"recent": {
            "accessionNumber": [f["accn"] for f in ordered],
            "filingDate": [f["filed"].isoformat() for f in ordered],
            "reportDate": [f["report"].isoformat() for f in ordered],
            "form": [f["form"] for f in ordered],
            "primaryDocument": [f"{f['form'].lower().replace('/', '')}-{f['report'].isoformat()}.htm" for f in ordered],
        }},
        "_synthetic": {"generator": "tools/make_fixture.py", "version": FIXTURE_VERSION},
    }


def issuer_slug(spec: IssuerSpec) -> str:
    return spec.name.lower().replace(" ", "-")
