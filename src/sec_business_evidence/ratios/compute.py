"""Compute the six ratios for each fiscal year from selected facts.

Every ratio is built from annual duration facts and fiscal-year-end instant facts of a
single fiscal year. Duration compatibility and unit agreement are enforced on every input.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import yaml

from ..errors import ConfigurationError
from ..facts.model import FactSnapshot, PeriodKind
from ..facts.select import require_compatible, require_same_unit, safe_div
from .citation import Citation, RatioResult, citation_from_fact

DAYS_PER_YEAR = 365
RATIO_NAMES = (
    "revenue_growth",
    "receivables_to_revenue",
    "dso",
    "ocf_to_net_income",
    "current_ratio",
    "debt_to_equity",
)


@dataclass(frozen=True)
class ConceptMap:
    concepts: dict[str, tuple[str, tuple[str, ...]]]  # name -> (kind, tags)
    money_units: frozenset[str]

    def tags_for(self, concept: str) -> tuple[str, ...]:
        if concept not in self.concepts:
            raise ConfigurationError(f"unknown concept {concept!r} in tags config")
        return self.concepts[concept][1]


def load_concept_map(path: str | Path) -> ConceptMap:
    p = Path(path)
    if not p.exists():
        raise ConfigurationError(f"tags config not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    concepts = {}
    for name, body in (raw or {}).get("concepts", {}).items():
        kind = body.get("kind")
        tags = tuple(body.get("tags", []))
        if kind not in ("duration", "instant") or not tags:
            raise ConfigurationError(f"concept {name!r} needs kind duration|instant and a non-empty tag list")
        concepts[name] = (kind, tags)
    if not concepts:
        raise ConfigurationError(f"tags config {p} defines no concepts")
    return ConceptMap(concepts=concepts, money_units=frozenset(raw.get("money_units", ["USD"])))


@dataclass(frozen=True)
class FiscalYearFacts:
    fy: int
    period_end: str
    duration: dict[str, FactSnapshot]  # concept -> annual fact
    instant: dict[str, FactSnapshot]  # concept -> fiscal-year-end fact

    def get(self, concept: str) -> Optional[FactSnapshot]:
        return self.duration.get(concept) or self.instant.get(concept)


def _pick(facts: Iterable[FactSnapshot], tags: tuple[str, ...], money_units: frozenset[str]) -> Optional[FactSnapshot]:
    by_tag = {}
    for f in facts:
        if f.unit in money_units and f.tag in tags:
            by_tag.setdefault(f.tag, f)
    for tag in tags:  # first tag in config order wins
        if tag in by_tag:
            return by_tag[tag]
    return None


def collect_fiscal_years(facts: Iterable[FactSnapshot], cmap: ConceptMap) -> list[FiscalYearFacts]:
    """Group annual duration facts and matching fiscal-year-end instants by fiscal year end."""
    items = list(facts)
    annual = [f for f in items if f.kind is PeriodKind.ANNUAL]
    instants = [f for f in items if f.kind is PeriodKind.INSTANT]
    ends = sorted({f.period_end for f in annual})
    out: list[FiscalYearFacts] = []
    for end in ends:
        a_here = [f for f in annual if f.period_end == end]
        i_here = [f for f in instants if f.period_end == end]
        # A later 10-K repeats the prior year as a comparative and stamps it with the later
        # filing's fy, so the fiscal year of a period is the smallest fy that reported it.
        fy_values = [f.fy for f in a_here if f.fy is not None]
        fy = min(fy_values) if fy_values else end.year
        dur: dict[str, FactSnapshot] = {}
        ins: dict[str, FactSnapshot] = {}
        for name, (kind, tags) in cmap.concepts.items():
            pool = a_here if kind == "duration" else i_here
            picked = _pick(pool, tags, cmap.money_units)
            if picked is not None:
                (dur if kind == "duration" else ins)[name] = picked
        out.append(FiscalYearFacts(fy=fy, period_end=end.isoformat(), duration=dur, instant=ins))
    return out


def _missing(name: str, fy: int, concepts: list[str]) -> RatioResult:
    return RatioResult(name=name, fiscal_year=fy, value=None, unit="ratio",
                       reason=f"missing input: {', '.join(concepts)}")


def _cites(*facts: FactSnapshot) -> tuple[Citation, ...]:
    return tuple(citation_from_fact(f) for f in facts)


def _simple_ratio(name: str, unit: str, year: FiscalYearFacts, num: str, den: str,
                  scale: float = 1.0) -> RatioResult:
    a, b = year.get(num), year.get(den)
    missing = [c for c, f in ((num, a), (den, b)) if f is None]
    if missing:
        return _missing(name, year.fy, missing)
    assert a is not None and b is not None
    require_same_unit(a, b)
    require_compatible(a, b)
    value = safe_div(a.value, b.value)
    reason = None if value is not None else f"zero denominator: {den} = 0"
    return RatioResult(name=name, fiscal_year=year.fy, unit=unit,
                       value=None if value is None else value * scale,
                       inputs=_cites(a, b), reason=reason)


def revenue_growth(year: FiscalYearFacts, prior: Optional[FiscalYearFacts]) -> RatioResult:
    name = "revenue_growth"
    cur = year.get("revenue")
    if cur is None:
        return _missing(name, year.fy, ["revenue"])
    if prior is None or prior.get("revenue") is None:
        return RatioResult(name=name, fiscal_year=year.fy, value=None, unit="fraction",
                           inputs=_cites(cur), reason="no prior fiscal year revenue")
    prev = prior.get("revenue")
    assert prev is not None
    require_same_unit(cur, prev)
    require_compatible(cur, prev)
    value = safe_div(cur.value - prev.value, prev.value)
    return RatioResult(name=name, fiscal_year=year.fy, value=value, unit="fraction",
                       inputs=_cites(cur, prev),
                       reason=None if value is not None else "zero denominator: prior revenue = 0")


def receivables_to_revenue(year: FiscalYearFacts) -> RatioResult:
    return _simple_ratio("receivables_to_revenue", "fraction", year, "receivables", "revenue")


def dso(year: FiscalYearFacts) -> RatioResult:
    return _simple_ratio("dso", "days", year, "receivables", "revenue", scale=DAYS_PER_YEAR)


def ocf_to_net_income(year: FiscalYearFacts) -> RatioResult:
    return _simple_ratio("ocf_to_net_income", "ratio", year, "operating_cash_flow", "net_income")


def current_ratio(year: FiscalYearFacts) -> RatioResult:
    return _simple_ratio("current_ratio", "ratio", year, "current_assets", "current_liabilities")


def debt_to_equity(year: FiscalYearFacts) -> RatioResult:
    name = "debt_to_equity"
    eq = year.get("equity")
    parts = [f for f in (year.get("debt_noncurrent"), year.get("debt_current")) if f is not None]
    if eq is None or not parts:
        missing = (["equity"] if eq is None else []) + (["debt_noncurrent or debt_current"] if not parts else [])
        return _missing(name, year.fy, missing)
    require_same_unit(eq, *parts)
    total_debt = sum(int(f.value) for f in parts)
    value = safe_div(total_debt, eq.value)
    return RatioResult(name=name, fiscal_year=year.fy, value=value, unit="ratio",
                       inputs=_cites(*parts, eq),
                       reason=None if value is not None else "zero denominator: equity = 0")


def compute_all(years: list[FiscalYearFacts]) -> dict[int, list[RatioResult]]:
    """Ratios per fiscal year, in chronological order of fiscal year end."""
    out: dict[int, list[RatioResult]] = {}
    prior: Optional[FiscalYearFacts] = None
    for year in years:
        out[year.fy] = [
            revenue_growth(year, prior),
            receivables_to_revenue(year),
            dso(year),
            ocf_to_net_income(year),
            current_ratio(year),
            debt_to_equity(year),
        ]
        prior = year
    return out
