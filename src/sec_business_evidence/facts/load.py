"""Parse a companyfacts JSON document into FactSnapshot objects.

The companyfacts API shape (documented at https://www.sec.gov/edgar/sec-api-documentation):

    {"cik": 320193, "entityName": "...",
     "facts": {"us-gaap": {"Revenues": {"label": ..., "description": ...,
                "units": {"USD": [{"start": "2023-01-01", "end": "2023-12-31",
                                    "val": 123, "accn": "0000320193-24-000001",
                                    "fy": 2023, "fp": "FY", "form": "10-K",
                                    "filed": "2024-02-01", "frame": "CY2023"}]}}}}}
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from ..errors import SchemaError
from .model import FactSnapshot

MONEY_UNITS = frozenset({"USD"})


def _parse_date(text: Any, field: str, where: str) -> date:
    if not isinstance(text, str):
        raise SchemaError(f"{where}: field {field!r} must be an ISO date string, got {text!r}")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise SchemaError(f"{where}: field {field!r} is not an ISO date: {text!r}") from exc


def _coerce_value(val: Any, unit: str, where: str) -> int | float:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise SchemaError(f"{where}: field 'val' must be numeric, got {val!r}")
    if unit in MONEY_UNITS:
        # EDGAR reports USD in whole dollars. Keep money as an integer; never a float.
        if isinstance(val, float):
            if abs(val - round(val)) > 1e-9:
                raise SchemaError(f"{where}: USD value {val!r} is not a whole-dollar amount")
            return int(round(val))
        return int(val)
    return val


def normalise_cik(cik: Any) -> str:
    """Return the ten-digit zero-padded CIK string."""
    try:
        n = int(str(cik).strip())
    except ValueError as exc:
        raise SchemaError(f"CIK must be an integer or digit string, got {cik!r}") from exc
    if n < 0 or n > 9_999_999_999:
        raise SchemaError(f"CIK out of range: {cik!r}")
    return f"{n:010d}"


def facts_from_companyfacts(doc: dict[str, Any]) -> list[FactSnapshot]:
    """Flatten a companyfacts document into a list of snapshots (unordered)."""
    if not isinstance(doc, dict) or "facts" not in doc or "cik" not in doc:
        raise SchemaError("companyfacts document must be an object with 'cik' and 'facts'")
    cik = normalise_cik(doc["cik"])
    facts_by_taxonomy = doc["facts"]
    if not isinstance(facts_by_taxonomy, dict):
        raise SchemaError("'facts' must be an object keyed by taxonomy")
    out: list[FactSnapshot] = []
    for taxonomy, tags in facts_by_taxonomy.items():
        if not isinstance(tags, dict):
            raise SchemaError(f"facts[{taxonomy!r}] must be an object keyed by tag")
        for tag, body in tags.items():
            units = body.get("units") if isinstance(body, dict) else None
            if not isinstance(units, dict):
                raise SchemaError(f"facts[{taxonomy!r}][{tag!r}] has no 'units' object")
            for unit, rows in units.items():
                if not isinstance(rows, list):
                    raise SchemaError(f"{taxonomy}:{tag}:{unit} 'units' entry must be a list")
                for i, row in enumerate(rows):
                    where = f"{taxonomy}:{tag}:{unit}[{i}]"
                    out.append(_row_to_fact(cik, taxonomy, tag, unit, row, where))
    return out


def _row_to_fact(cik: str, taxonomy: str, tag: str, unit: str, row: Any, where: str) -> FactSnapshot:
    if not isinstance(row, dict):
        raise SchemaError(f"{where}: must be an object")
    for required in ("end", "val", "accn", "form", "filed"):
        if required not in row:
            raise SchemaError(f"{where}: missing required field {required!r}")
    start = _parse_date(row["start"], "start", where) if row.get("start") else None
    end = _parse_date(row["end"], "end", where)
    if start is not None and start > end:
        raise SchemaError(f"{where}: period start {start} is after end {end}")
    fy = row.get("fy")
    return FactSnapshot(
        cik=cik,
        accession=str(row["accn"]),
        form=str(row["form"]),
        filed=_parse_date(row["filed"], "filed", where),
        period_start=start,
        period_end=end,
        fy=int(fy) if fy is not None else None,
        fp=str(row["fp"]) if row.get("fp") is not None else None,
        taxonomy=taxonomy,
        tag=tag,
        unit=unit,
        value=_coerce_value(row["val"], unit, where),
        frame=row.get("frame"),
    )


def load_companyfacts(path: str | Path) -> tuple[dict[str, Any], list[FactSnapshot]]:
    """Read a companyfacts JSON file (raw API shape or cache envelope) and flatten it."""
    p = Path(path)
    if not p.exists():
        raise SchemaError(f"companyfacts file not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        doc = json.load(fh)
    if isinstance(doc, dict) and "payload" in doc and "sha256" in doc:
        doc = doc["payload"]  # cache envelope written by ingest.cache
    return doc, facts_from_companyfacts(doc)


def entity_name(doc: dict[str, Any]) -> str:
    name = doc.get("entityName")
    return str(name) if name else "UNKNOWN ISSUER"


def unique_tags(facts: Iterable[FactSnapshot]) -> set[str]:
    return {f.tag for f in facts}
