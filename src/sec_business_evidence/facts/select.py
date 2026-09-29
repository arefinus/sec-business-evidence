"""Point-in-time selection, amendment versioning, deduplication, compatibility checks.

Order of operations used by the pipeline:

1. ``point_in_time``   keep only facts from filings filed on or before the analysis date.
2. ``apply_versioning`` for each reported quantity (tag, unit, period), the latest-filed
   filing wins. A 10-K/A filed after the original supersedes it for the same period.
   Because step 1 ran first, an amendment filed after the analysis date never enters.
3. ``deduplicate``      the same value for the same quantity carried by several filings
   (comparative columns of later 10-Ks) collapses to the earliest filing that reported it.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Iterable, Optional

from ..errors import PeriodMismatchError, UnitMismatchError
from .model import FactSnapshot, PeriodKind


def point_in_time(facts: Iterable[FactSnapshot], as_of: date) -> list[FactSnapshot]:
    """Facts known on ``as_of``: filed on or before that date."""
    return [f for f in facts if f.filed <= as_of]


def _form_rank(form: str) -> int:
    # Amendments outrank originals when filed the same day; otherwise filing date decides.
    return 1 if form.endswith("/A") else 0


def apply_versioning(facts: Iterable[FactSnapshot]) -> tuple[list[FactSnapshot], list[FactSnapshot]]:
    """Return (current, superseded).

    For each identity (taxonomy, tag, unit, start, end) with *differing* values across
    filings, the latest filed wins. Identical values are left for ``deduplicate``.
    """
    groups: dict[tuple, list[FactSnapshot]] = defaultdict(list)
    for f in facts:
        groups[f.identity()].append(f)
    current: list[FactSnapshot] = []
    superseded: list[FactSnapshot] = []
    for members in groups.values():
        ordered = sorted(members, key=lambda f: (f.filed, _form_rank(f.form), f.accession))
        winner = ordered[-1]
        for f in ordered:
            if f.value != winner.value:
                superseded.append(f)
            else:
                current.append(f)
    return current, superseded


def deduplicate(facts: Iterable[FactSnapshot]) -> tuple[list[FactSnapshot], list[FactSnapshot]]:
    """Collapse identical (identity, value) pairs to the earliest filing. Return (kept, dropped)."""
    seen: dict[tuple, FactSnapshot] = {}
    dropped: list[FactSnapshot] = []
    for f in sorted(facts, key=lambda f: (f.filed, f.accession)):
        key = f.identity() + (f.value,)
        if key in seen:
            dropped.append(f)
        else:
            seen[key] = f
    return list(seen.values()), dropped


def annual_only(facts: Iterable[FactSnapshot]) -> list[FactSnapshot]:
    return [f for f in facts if f.kind is PeriodKind.ANNUAL]


def quarterly_only(facts: Iterable[FactSnapshot]) -> list[FactSnapshot]:
    return [f for f in facts if f.kind is PeriodKind.QUARTERLY]


def instants_only(facts: Iterable[FactSnapshot]) -> list[FactSnapshot]:
    return [f for f in facts if f.kind is PeriodKind.INSTANT]


def require_compatible(a: FactSnapshot, b: FactSnapshot) -> None:
    """Two duration facts may be compared only if both are annual or both are quarterly."""
    if a.kind is PeriodKind.INSTANT or b.kind is PeriodKind.INSTANT:
        return  # instants pair with anything of the same end date; checked by the caller
    if a.kind is not b.kind or a.kind is PeriodKind.OTHER:
        raise PeriodMismatchError(
            f"cannot compare {a.tag} ({a.kind.value}, {a.duration} days) with "
            f"{b.tag} ({b.kind.value}, {b.duration} days)"
        )


def require_same_unit(*facts: FactSnapshot) -> str:
    units = {f.unit for f in facts}
    if len(units) != 1:
        names = ", ".join(f"{f.tag}[{f.unit}]" for f in facts)
        raise UnitMismatchError(f"inputs must share one unit, got: {names}")
    return units.pop()


def safe_div(numerator: int | float, denominator: int | float) -> Optional[float]:
    """Division that returns None instead of raising or producing inf."""
    if denominator == 0:
        return None
    return numerator / denominator


def latest_filed(facts: Iterable[FactSnapshot]) -> Optional[FactSnapshot]:
    items = list(facts)
    if not items:
        return None
    return max(items, key=lambda f: (f.filed, f.accession))
