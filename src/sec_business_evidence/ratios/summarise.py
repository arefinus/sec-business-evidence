"""Deterministic template summariser with inline citations, plus an adapter interface for
an optional language model. No provider is wired in; ``get_backend("llm")`` raises."""

from __future__ import annotations

from typing import Optional, Protocol

from ..errors import ConfigurationError
from .citation import RatioResult
from .flags import ReviewFlag

LABELS = {
    "revenue_growth": "Revenue growth",
    "receivables_to_revenue": "Receivables to revenue",
    "dso": "Days sales outstanding",
    "ocf_to_net_income": "Operating cash flow to net income",
    "current_ratio": "Current ratio",
    "debt_to_equity": "Debt to equity",
}


def _fmt(r: RatioResult) -> str:
    assert r.value is not None
    if r.unit == "fraction":
        return f"{r.value * 100:.1f}%"
    if r.unit == "days":
        return f"{r.value:.1f} days"
    return f"{r.value:.2f}"


def _cite(ids: tuple[str, ...] | list[str]) -> str:
    return "[" + "; ".join(ids) + "]" if ids else ""


class SummaryBackend(Protocol):
    name: str

    def summarise(self, issuer: str, ratios_by_year: dict[int, list[RatioResult]],
                  flags: list[ReviewFlag]) -> list[str]: ...


class TemplateBackend:
    """Sentence templates. Same inputs produce the same sentences."""

    name = "template"

    def summarise(self, issuer: str, ratios_by_year: dict[int, list[RatioResult]],
                  flags: list[ReviewFlag]) -> list[str]:
        sentences: list[str] = []
        years = sorted(ratios_by_year)
        if not years:
            return [f"No annual facts were available for {issuer}; nothing to summarise."]
        latest = years[-1]
        for r in ratios_by_year[latest]:
            label = LABELS.get(r.name, r.name)
            if r.value is None:
                sentences.append(f"{label} for FY{latest} is not available ({r.reason}).")
                continue
            sentences.append(
                f"{label} for FY{latest} was {_fmt(r)} {_cite([c.id for c in r.inputs])}."
            )
        if not flags:
            sentences.append(f"No review flags fired for {issuer} under the configured thresholds.")
        for fl in sorted(flags, key=lambda f: (f.fiscal_year, f.rule_id)):
            sentences.append(f"FY{fl.fiscal_year}: {fl.message} Value {fl.value:.3f}"
                             + (f", prior {fl.prior_value:.3f}" if fl.prior_value is not None else "")
                             + f" {_cite(fl.citation_ids)}.")
        return sentences


class LlmAdapter:
    """Interface for an optional language-model backend. Nothing is wired in.

    A concrete adapter would implement ``complete(prompt) -> str`` and must still return
    citation ids verbatim from the ratio inputs; the pipeline rejects sentences whose
    citation ids are not in the evidence set.
    """

    name = "llm"

    def __init__(self, provider: Optional[str] = None) -> None:
        raise ConfigurationError(
            "no language-model provider is wired into this repository; use the 'template' backend"
        )


def get_backend(name: str = "template") -> SummaryBackend:
    if name == "template":
        return TemplateBackend()
    if name == "llm":
        return LlmAdapter()  # raises ConfigurationError
    raise ConfigurationError(f"unknown summary backend {name!r}; choose 'template'")


def summarise(issuer: str, ratios_by_year: dict[int, list[RatioResult]], flags: list[ReviewFlag],
              backend: str = "template") -> list[str]:
    return get_backend(backend).summarise(issuer, ratios_by_year, flags)
