"""Evidence JSON and flow JSON. Every number carries the accession that supports it and
an EDGAR URL built from that accession.

URL patterns (documented, deterministic, built from accession and CIK only):

    filing_index   https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/{accn}-index.htm
    filing_folder  https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/
    company_browse https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik10}&type={form}&dateb=&owner=include&count=40
    companyfacts   https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json

For the synthetic issuers shipped in examples/fixtures the URLs are well formed but do
not resolve, because the CIKs and accessions are fictional.
"""

from __future__ import annotations

import re
from typing import Any

from . import __version__
from .ratios.citation import Citation, RatioResult
from .ratios.flags import ReviewFlag

SCHEMA_VERSION = 1
ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
FLOW_NODES = ("revenue", "receivables", "cash", "liabilities")

URL_PATTERNS = {
    "filing_index": "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/{accn}-index.htm",
    "filing_folder": "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/",
    "company_browse": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik10}&type={form}&dateb=&owner=include&count=40",
    "companyfacts_api": "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json",
}


def validate_accession(accn: str) -> str:
    if not ACCESSION_RE.match(accn):
        raise ValueError(f"accession {accn!r} is not of the form 0000000000-YY-NNNNNN")
    return accn


def edgar_urls(cik10: str, accn: str, form: str) -> dict[str, str]:
    validate_accession(accn)
    cik_int = str(int(cik10))
    accn_nodash = accn.replace("-", "")
    form_base = form.split("/")[0]  # browse by 10-K for a 10-K/A
    fields = {"cik_int": cik_int, "cik10": cik10, "accn": accn, "accn_nodash": accn_nodash, "form": form_base}
    return {name: pattern.format(**fields) for name, pattern in URL_PATTERNS.items()}


def evidence_entry(c: Citation) -> dict[str, Any]:
    d = c.to_dict()
    d["urls"] = edgar_urls(c.cik, c.accession, c.form)
    return d


def build_evidence(
    *,
    issuer_name: str,
    cik10: str,
    as_of: str,
    mode: str,
    years: list[dict[str, Any]],
    ratios_by_year: dict[int, list[RatioResult]],
    flags: list[ReviewFlag],
    summary: list[str],
    selection: dict[str, int],
) -> dict[str, Any]:
    cites: dict[str, Citation] = {}
    for results in ratios_by_year.values():
        for r in results:
            for c in r.inputs:
                cites.setdefault(c.id, c)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "mode": mode,
        "evidence_status": "demo" if mode == "synthetic-demo" else "cached-source",
        "generated_by": f"sec_business_evidence {__version__}",
        "disclaimer": (
            "Review flags are threshold rules that ask an analyst to look at a change. "
            "This repository contains no fraud classifier and produces no verdict."
        ),
        "issuer": {"cik": cik10, "name": issuer_name},
        "as_of": as_of,
        "url_patterns": URL_PATTERNS,
        "selection": selection,
        "fiscal_years": [
            {
                "fy": fy,
                "period_end": next((y["period_end"] for y in years if y["fy"] == fy), None),
                "ratios": [r.to_dict() for r in ratios_by_year[fy]],
            }
            for fy in sorted(ratios_by_year)
        ],
        "flags": [f.to_dict() for f in flags],
        "summary": summary,
        "evidence": [evidence_entry(c) for _, c in sorted(cites.items())],
    }


def _node(node_id: str, label: str, citation: Citation | None) -> dict[str, Any]:
    return {
        "id": node_id,
        "label": label,
        "value": citation.value if citation else None,
        "unit": citation.unit if citation else None,
        "period": citation.period if citation else None,
        "tag": citation.tag if citation else None,
        "citation_ids": [citation.id] if citation else [],
    }


def _edge(src: str, dst: str, ratio: RatioResult | None, flags: list[ReviewFlag]) -> dict[str, Any]:
    return {
        "source": src,
        "target": dst,
        "relation": ratio.name if ratio else None,
        "value": ratio.value if ratio else None,
        "unit": ratio.unit if ratio else None,
        "citation_ids": [c.id for c in ratio.inputs] if ratio else [],
        "flag_ids": [f.rule_id for f in flags if ratio and f.ratio == ratio.name],
    }


def build_flow(
    *,
    issuer_name: str,
    cik10: str,
    fiscal_year: int,
    concept_citations: dict[str, Citation],
    ratios: list[RatioResult],
    flags: list[ReviewFlag],
) -> dict[str, Any]:
    """Portfolio flow graph for one fiscal year: four nodes, ratio-labelled edges."""
    by_name = {r.name: r for r in ratios}
    year_flags = [f for f in flags if f.fiscal_year == fiscal_year]
    nodes = [
        _node("revenue", "Revenue", concept_citations.get("revenue")),
        _node("receivables", "Receivables", concept_citations.get("receivables")),
        _node("cash", "Cash", concept_citations.get("cash")),
        _node("liabilities", "Liabilities", concept_citations.get("liabilities")),
    ]
    edges = [
        _edge("revenue", "receivables", by_name.get("receivables_to_revenue"), year_flags),
        _edge("receivables", "cash", by_name.get("dso"), year_flags),
        _edge("revenue", "cash", by_name.get("ocf_to_net_income"), year_flags),
        _edge("cash", "liabilities", by_name.get("current_ratio"), year_flags),
        _edge("liabilities", "revenue", by_name.get("debt_to_equity"), year_flags),
    ]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "mode": "synthetic-demo",
        "issuer": {"cik": cik10, "name": issuer_name},
        "fiscal_year": fiscal_year,
        "nodes": nodes,
        "edges": edges,
        "flags": [f.to_dict() for f in year_flags],
    }


def validate_evidence_schema(doc: dict[str, Any]) -> list[str]:
    """Return a list of problems (empty when the document is well formed)."""
    problems: list[str] = []
    for key in ("schemaVersion", "mode", "issuer", "as_of", "fiscal_years", "flags", "summary", "evidence"):
        if key not in doc:
            problems.append(f"missing key {key!r}")
    if problems:
        return problems
    ids = [e["id"] for e in doc["evidence"]]
    if len(ids) != len(set(ids)):
        problems.append("duplicate evidence ids")
    for e in doc["evidence"]:
        if not ACCESSION_RE.match(e.get("accession", "")):
            problems.append(f"bad accession {e.get('accession')!r}")
        urls = e.get("urls", {})
        for name in URL_PATTERNS:
            if not str(urls.get(name, "")).startswith("https://"):
                problems.append(f"evidence {e.get('id')} missing url {name}")
    known = set(ids)
    for fy in doc["fiscal_years"]:
        for r in fy["ratios"]:
            for cid in r["citation_ids"]:
                if cid not in known:
                    problems.append(f"ratio {r['name']} FY{fy['fy']} cites unknown id {cid}")
    for f in doc["flags"]:
        if "fraud" in f.get("message", "").lower():
            problems.append("flag message uses forbidden vocabulary")
    return problems


def validate_flow_schema(doc: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if doc.get("schemaVersion") != SCHEMA_VERSION:
        problems.append("schemaVersion mismatch")
    if doc.get("mode") != "synthetic-demo":
        problems.append("flow mode must be synthetic-demo")
    node_ids = [n.get("id") for n in doc.get("nodes", [])]
    if node_ids != list(FLOW_NODES):
        problems.append(f"nodes must be {list(FLOW_NODES)}, got {node_ids}")
    for e in doc.get("edges", []):
        if e.get("source") not in node_ids or e.get("target") not in node_ids:
            problems.append(f"edge references unknown node: {e}")
    return problems
