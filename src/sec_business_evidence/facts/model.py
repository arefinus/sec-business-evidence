"""The fact snapshot: one reported XBRL value, as filed, with its provenance."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from enum import Enum
from typing import Any, Optional

# Duration windows in days. A fiscal year is 52 or 53 weeks; a quarter is 13 or 14 weeks.
ANNUAL_MIN_DAYS = 350
ANNUAL_MAX_DAYS = 380
QUARTER_MIN_DAYS = 80
QUARTER_MAX_DAYS = 100


class PeriodKind(str, Enum):
    INSTANT = "instant"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    OTHER = "other"


@dataclass(frozen=True)
class FactSnapshot:
    """One value reported in one filing.

    ``value`` is an integer for money units (EDGAR reports USD in whole dollars) and
    may be a float only for non-money units such as ratios or per-share amounts.
    """

    cik: str
    accession: str
    form: str
    filed: date
    period_start: Optional[date]
    period_end: date
    fy: Optional[int]
    fp: Optional[str]
    taxonomy: str
    tag: str
    unit: str
    value: int | float
    frame: Optional[str] = None

    @property
    def kind(self) -> PeriodKind:
        return period_kind(self.period_start, self.period_end)

    @property
    def duration(self) -> Optional[int]:
        return duration_days(self.period_start, self.period_end)

    @property
    def period_label(self) -> str:
        if self.period_start is None:
            return f"as of {self.period_end.isoformat()}"
        return f"{self.period_start.isoformat()} to {self.period_end.isoformat()}"

    @property
    def is_amendment(self) -> bool:
        return self.form.endswith("/A")

    def identity(self) -> tuple:
        """Identity of the *reported quantity*, independent of which filing carried it."""
        return (self.taxonomy, self.tag, self.unit, self.period_start, self.period_end)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["filed"] = self.filed.isoformat()
        d["period_start"] = self.period_start.isoformat() if self.period_start else None
        d["period_end"] = self.period_end.isoformat()
        d["kind"] = self.kind.value
        return d


def duration_days(start: Optional[date], end: date) -> Optional[int]:
    if start is None:
        return None
    return (end - start).days


def period_kind(start: Optional[date], end: date) -> PeriodKind:
    days = duration_days(start, end)
    if days is None:
        return PeriodKind.INSTANT
    if ANNUAL_MIN_DAYS <= days <= ANNUAL_MAX_DAYS:
        return PeriodKind.ANNUAL
    if QUARTER_MIN_DAYS <= days <= QUARTER_MAX_DAYS:
        return PeriodKind.QUARTERLY
    return PeriodKind.OTHER
