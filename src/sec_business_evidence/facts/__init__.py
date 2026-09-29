"""Fact snapshots, loading from companyfacts JSON, and point-in-time selection."""

from __future__ import annotations

from .model import FactSnapshot, PeriodKind, period_kind, duration_days
from .load import load_companyfacts, facts_from_companyfacts
from .select import (
    point_in_time,
    apply_versioning,
    deduplicate,
    annual_only,
    quarterly_only,
    require_compatible,
    require_same_unit,
    safe_div,
)

__all__ = [
    "FactSnapshot",
    "PeriodKind",
    "period_kind",
    "duration_days",
    "load_companyfacts",
    "facts_from_companyfacts",
    "point_in_time",
    "apply_versioning",
    "deduplicate",
    "annual_only",
    "quarterly_only",
    "require_compatible",
    "require_same_unit",
    "safe_div",
]
