"""End-to-end analysis of one companyfacts document at one analysis date."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from .evidence import build_evidence, build_flow
from .facts.load import entity_name, facts_from_companyfacts, normalise_cik
from .facts.model import FactSnapshot
from .facts.select import apply_versioning, deduplicate, point_in_time
from .ratios.citation import Citation, RatioResult, citation_from_fact
from .ratios.compute import ConceptMap, FiscalYearFacts, collect_fiscal_years, compute_all, load_concept_map
from .ratios.flags import ReviewFlag, evaluate_flags, load_flag_rules
from .ratios.summarise import summarise

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent.parent
DEFAULT_FLAGS = REPO_ROOT / "configs" / "flags.yaml"
DEFAULT_TAGS = REPO_ROOT / "configs" / "tags.yaml"


@dataclass(frozen=True)
class AnalysisResult:
    cik: str
    issuer: str
    as_of: date
    mode: str
    years: list[FiscalYearFacts]
    ratios_by_year: dict[int, list[RatioResult]]
    flags: list[ReviewFlag]
    summary: list[str]
    selection: dict[str, int]
    facts_in_scope: list[FactSnapshot] = field(default_factory=list, repr=False)

    @property
    def latest_fy(self) -> Optional[int]:
        return max(self.ratios_by_year) if self.ratios_by_year else None

    def concept_citations(self, fy: int) -> dict[str, Citation]:
        year = next((y for y in self.years if y.fy == fy), None)
        if year is None:
            return {}
        out: dict[str, Citation] = {}
        for concept, fact in {**year.duration, **year.instant}.items():
            out[concept] = citation_from_fact(fact)
        return out

    def year_dicts(self) -> list[dict[str, Any]]:
        return [{"fy": y.fy, "period_end": y.period_end} for y in self.years]

    def evidence_json(self) -> dict[str, Any]:
        return build_evidence(
            issuer_name=self.issuer, cik10=self.cik, as_of=self.as_of.isoformat(), mode=self.mode,
            years=self.year_dicts(), ratios_by_year=self.ratios_by_year, flags=self.flags,
            summary=self.summary, selection=self.selection,
        )

    def flow_json(self, fy: Optional[int] = None) -> dict[str, Any]:
        target = fy if fy is not None else self.latest_fy
        if target is None:
            raise ValueError("no fiscal year available for the flow graph")
        return build_flow(
            issuer_name=self.issuer, cik10=self.cik, fiscal_year=target,
            concept_citations=self.concept_citations(target),
            ratios=self.ratios_by_year[target], flags=self.flags,
        )

    def ratios_frame(self) -> pd.DataFrame:
        rows = [
            {"fiscal_year": fy, "ratio": r.name, "value": r.value, "unit": r.unit,
             "reason": r.reason, "citation_ids": ";".join(c.id for c in r.inputs)}
            for fy in sorted(self.ratios_by_year) for r in self.ratios_by_year[fy]
        ]
        return pd.DataFrame(rows, columns=["fiscal_year", "ratio", "value", "unit", "reason", "citation_ids"])


def select_facts(all_facts: list[FactSnapshot], as_of: date) -> tuple[list[FactSnapshot], dict[str, int]]:
    known = point_in_time(all_facts, as_of)
    current, superseded = apply_versioning(known)
    kept, dropped = deduplicate(current)
    stats = {
        "facts_total": len(all_facts),
        "facts_known_at_as_of": len(known),
        "facts_superseded": len(superseded),
        "facts_duplicates_dropped": len(dropped),
        "facts_in_scope": len(kept),
    }
    return kept, stats


def analyze(
    doc: dict[str, Any],
    as_of: date,
    *,
    flags_path: str | Path = DEFAULT_FLAGS,
    tags_path: str | Path = DEFAULT_TAGS,
    mode: str = "synthetic-demo",
    concept_map: Optional[ConceptMap] = None,
) -> AnalysisResult:
    cik = normalise_cik(doc["cik"])
    issuer = entity_name(doc)
    all_facts = facts_from_companyfacts(doc)
    kept, stats = select_facts(all_facts, as_of)
    cmap = concept_map or load_concept_map(tags_path)
    years = collect_fiscal_years(kept, cmap)
    ratios_by_year = compute_all(years)
    rules = load_flag_rules(flags_path)
    flags = evaluate_flags(rules, ratios_by_year)
    summary = summarise(issuer, ratios_by_year, flags)
    return AnalysisResult(cik=cik, issuer=issuer, as_of=as_of, mode=mode, years=years,
                          ratios_by_year=ratios_by_year, flags=flags, summary=summary,
                          selection=stats, facts_in_scope=kept)


def write_outputs(result: AnalysisResult, out_dir: str | Path) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "evidence": out / "evidence.json",
        "flow": out / "flow.json",
        "summary": out / "summary.md",
        "ratios": out / "ratios.csv",
    }
    with paths["evidence"].open("w", encoding="utf-8") as fh:
        json.dump(result.evidence_json(), fh, indent=1, sort_keys=False)
    if result.latest_fy is not None:
        with paths["flow"].open("w", encoding="utf-8") as fh:
            json.dump(result.flow_json(), fh, indent=1)
    lines = [f"# {result.issuer} (CIK {result.cik}), analysis date {result.as_of.isoformat()}", "",
             f"Mode: {result.mode}. Review flags are threshold rules; no verdict is implied.", ""]
    lines += [f"- {s}" for s in result.summary]
    paths["summary"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    result.ratios_frame().to_csv(paths["ratios"], index=False)
    return paths
