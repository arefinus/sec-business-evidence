"""Review flags: threshold rules from configs/flags.yaml applied to ratio results.

A flag says "review this change" and carries the citations of every ratio input. The
vocabulary is deliberately limited; the word describing an offence never appears here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from ..errors import ConfigurationError
from .citation import RatioResult

ALLOWED_OPS = ("gt", "lt", "abs_gt", "delta_gt", "delta_lt")
FORBIDDEN_WORDS = ("fraud", "fraudulent", "manipulat")


@dataclass(frozen=True)
class FlagRule:
    id: str
    ratio: str
    op: str
    threshold: float
    message: str

    def needs_prior(self) -> bool:
        return self.op.startswith("delta_")


@dataclass(frozen=True)
class ReviewFlag:
    rule_id: str
    ratio: str
    fiscal_year: int
    value: float
    prior_value: Optional[float]
    threshold: float
    op: str
    message: str
    citation_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "ratio": self.ratio,
            "fiscal_year": self.fiscal_year,
            "value": self.value,
            "prior_value": self.prior_value,
            "threshold": self.threshold,
            "op": self.op,
            "severity": "review",
            "message": self.message,
            "citation_ids": list(self.citation_ids),
        }


def _validate_rule(raw: dict[str, Any], where: str) -> FlagRule:
    for key in ("id", "ratio", "op", "threshold", "message"):
        if key not in raw:
            raise ConfigurationError(f"{where}: rule is missing {key!r}")
    if raw["op"] not in ALLOWED_OPS:
        raise ConfigurationError(f"{where}: op {raw['op']!r} not in {ALLOWED_OPS}")
    message = str(raw["message"])
    lowered = message.lower()
    for word in FORBIDDEN_WORDS:
        if word in lowered:
            raise ConfigurationError(
                f"{where}: rule {raw['id']!r} message must describe a change to review, not an accusation"
            )
    try:
        threshold = float(raw["threshold"])
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"{where}: threshold must be numeric") from exc
    return FlagRule(id=str(raw["id"]), ratio=str(raw["ratio"]), op=str(raw["op"]),
                    threshold=threshold, message=message)


def load_flag_rules(path: str | Path) -> list[FlagRule]:
    p = Path(path)
    if not p.exists():
        raise ConfigurationError(f"flags config not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    rules_raw = raw.get("rules")
    if not isinstance(rules_raw, list) or not rules_raw:
        raise ConfigurationError(f"{p}: 'rules' must be a non-empty list")
    rules = [_validate_rule(r, f"{p}[{i}]") for i, r in enumerate(rules_raw)]
    ids = [r.id for r in rules]
    if len(set(ids)) != len(ids):
        raise ConfigurationError(f"{p}: duplicate rule ids")
    return rules


def _fires(rule: FlagRule, value: float, prior: Optional[float]) -> bool:
    if rule.op == "gt":
        return value > rule.threshold
    if rule.op == "lt":
        return value < rule.threshold
    if rule.op == "abs_gt":
        return abs(value) > rule.threshold
    if prior is None:
        return False
    delta = value - prior
    if rule.op == "delta_gt":
        return delta > rule.threshold
    if rule.op == "delta_lt":
        return delta < rule.threshold
    raise ConfigurationError(f"unsupported op {rule.op!r}")


def evaluate_flags(rules: list[FlagRule], ratios_by_year: dict[int, list[RatioResult]]) -> list[ReviewFlag]:
    """Evaluate every rule on every fiscal year. Prior values come from the preceding year."""
    years = sorted(ratios_by_year)
    lookup: dict[tuple[int, str], RatioResult] = {
        (fy, r.name): r for fy in years for r in ratios_by_year[fy]
    }
    out: list[ReviewFlag] = []
    for idx, fy in enumerate(years):
        prior_fy = years[idx - 1] if idx > 0 else None
        for rule in rules:
            cur = lookup.get((fy, rule.ratio))
            if cur is None or cur.value is None:
                continue
            prior = lookup.get((prior_fy, rule.ratio)) if prior_fy is not None else None
            prior_value = prior.value if prior is not None else None
            if rule.needs_prior() and prior_value is None:
                continue
            if _fires(rule, cur.value, prior_value):
                cites = tuple(c.id for c in cur.inputs)
                if prior is not None and rule.needs_prior():
                    cites = cites + tuple(c.id for c in prior.inputs)
                out.append(ReviewFlag(rule_id=rule.id, ratio=rule.ratio, fiscal_year=fy, value=cur.value,
                                      prior_value=prior_value, threshold=rule.threshold, op=rule.op,
                                      message=rule.message, citation_ids=cites))
    return out
