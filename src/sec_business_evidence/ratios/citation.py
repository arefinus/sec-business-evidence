"""Citation objects: every ratio input carries accession, tag, unit, value and period."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..facts.model import FactSnapshot


@dataclass(frozen=True)
class Citation:
    id: str
    cik: str
    accession: str
    form: str
    filed: str
    tag: str
    unit: str
    value: int | float
    period: str
    fy: Optional[int]
    fp: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cik": self.cik,
            "accession": self.accession,
            "form": self.form,
            "filed": self.filed,
            "tag": self.tag,
            "unit": self.unit,
            "value": self.value,
            "period": self.period,
            "fy": self.fy,
            "fp": self.fp,
        }


def citation_id(fact: FactSnapshot) -> str:
    end = fact.period_end.isoformat()
    accn = fact.accession.replace("-", "")
    return f"E:{accn}:{fact.tag}:{end}"


def citation_from_fact(fact: FactSnapshot) -> Citation:
    return Citation(
        id=citation_id(fact),
        cik=fact.cik,
        accession=fact.accession,
        form=fact.form,
        filed=fact.filed.isoformat(),
        tag=fact.tag,
        unit=fact.unit,
        value=fact.value,
        period=fact.period_label,
        fy=fact.fy,
        fp=fact.fp,
    )


@dataclass(frozen=True)
class RatioResult:
    """A ratio value with the citations of every input, or ``None`` with a reason."""

    name: str
    fiscal_year: int
    value: Optional[float]
    unit: str
    inputs: tuple[Citation, ...] = field(default_factory=tuple)
    reason: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.value is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "fiscal_year": self.fiscal_year,
            "value": self.value,
            "unit": self.unit,
            "reason": self.reason,
            "citation_ids": [c.id for c in self.inputs],
            "inputs": [c.to_dict() for c in self.inputs],
        }
