"""Ratios with citations, review flags, and the template summariser."""

from __future__ import annotations

from .citation import Citation, RatioResult, citation_from_fact
from .compute import ConceptMap, load_concept_map, FiscalYearFacts, collect_fiscal_years, compute_all
from .flags import FlagRule, ReviewFlag, load_flag_rules, evaluate_flags
from .summarise import TemplateBackend, SummaryBackend, get_backend, summarise

__all__ = [
    "Citation",
    "RatioResult",
    "citation_from_fact",
    "ConceptMap",
    "load_concept_map",
    "FiscalYearFacts",
    "collect_fiscal_years",
    "compute_all",
    "FlagRule",
    "ReviewFlag",
    "load_flag_rules",
    "evaluate_flags",
    "TemplateBackend",
    "SummaryBackend",
    "get_backend",
    "summarise",
]
