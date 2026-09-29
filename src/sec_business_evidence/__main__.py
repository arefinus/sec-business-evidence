"""Command line entry point: python -m sec_business_evidence {smoke,demo,fetch,analyze,flags,figures}

Exit codes: 0 success, 1 output failed validation, 2 missing input or configuration.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .errors import ConfigurationError, NetworkError, SchemaError, SecEvidenceError
from .evidence import validate_evidence_schema, validate_flow_schema
from .facts.load import load_companyfacts
from .ingest.cache import JsonCache
from .ingest.client import TERMS_URL, USER_AGENT_ENV, EdgarClient
from .manifest import now_iso, sha256_file, sha256_files, write_manifest
from .pipeline import DEFAULT_FLAGS, DEFAULT_TAGS, REPO_ROOT, analyze, write_outputs
from .synthetic import ISSUERS, issuer_slug

FIXTURE_DIR = REPO_ROOT / "examples" / "fixtures" / "v1"
OUTPUT_DIR = REPO_ROOT / "examples" / "output"
FIGURES_DIR = REPO_ROOT / "docs" / "figures"
DEMO_AS_OF = date(2025, 6, 30)


def _fixture_path(cik: int) -> Path:
    p = FIXTURE_DIR / f"CIK{cik:010d}_companyfacts.json"
    if not p.exists():
        raise ConfigurationError(f"fixture {p} not found; run 'python tools/make_fixture.py' first")
    return p


def _config_hash() -> str:
    return sha256_files([Path(DEFAULT_FLAGS), Path(DEFAULT_TAGS)])


def _run_issuer(path: Path, as_of: date, out_dir: Path, mode: str) -> tuple[dict, int]:
    doc, _ = load_companyfacts(path)
    result = analyze(doc, as_of, mode=mode)
    paths = write_outputs(result, out_dir)
    with paths["evidence"].open("r", encoding="utf-8") as fh:
        evidence = json.load(fh)
    problems = validate_evidence_schema(evidence)
    if paths["flow"].exists():
        with paths["flow"].open("r", encoding="utf-8") as fh:
            problems += validate_flow_schema(json.load(fh))
    if problems:
        raise SchemaError("output failed validation: " + "; ".join(problems))
    return evidence, result.selection["facts_in_scope"]


def cmd_smoke(args: argparse.Namespace) -> int:
    started = now_iso()
    out = Path(args.out)
    path = _fixture_path(ISSUERS[0].cik)
    evidence, n_facts = _run_issuer(path, DEMO_AS_OF, out, "synthetic-demo")
    write_manifest(out, mode="smoke", status="completed", started_at=started,
                   data_source_id="synthetic-fixture-v1", split_manifest_hash=sha256_file(path),
                   sample_counts={"facts_in_scope": n_facts, "fiscal_years": len(evidence["fiscal_years"])},
                   configuration_hash=_config_hash(), metrics_file=str(out / "evidence.json"))
    print(f"smoke ok: {evidence['issuer']['name']}, {len(evidence['fiscal_years'])} fiscal years, "
          f"{len(evidence['flags'])} review flags, {len(evidence['evidence'])} cited facts -> {out}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    started = now_iso()
    out = Path(args.out)
    fixture_paths = []
    counts: dict[str, int] = {}
    for spec in ISSUERS:
        path = _fixture_path(spec.cik)
        fixture_paths.append(path)
        evidence, n = _run_issuer(path, DEMO_AS_OF, out / issuer_slug(spec), "synthetic-demo")
        counts[issuer_slug(spec)] = n
        print(f"{spec.name}: {len(evidence['fiscal_years'])} fiscal years, {len(evidence['flags'])} review flags")
    # Portfolio flow file: the first issuer's latest fiscal year.
    src = out / issuer_slug(ISSUERS[0]) / "flow.json"
    (out / "demo_flow.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    write_manifest(out, mode="demo", status="completed", started_at=started,
                   data_source_id="synthetic-fixture-v1", split_manifest_hash=sha256_files(fixture_paths),
                   sample_counts=counts, configuration_hash=_config_hash(), metrics_file=None)
    print(f"demo outputs written to {out}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    print(f"SEC EDGAR access terms: {TERMS_URL}")
    print(f"Declared User-Agent comes from {USER_AGENT_ENV}; requests are limited to 10 per second.")
    cache = JsonCache(args.cache_dir)
    client = EdgarClient.from_env(cache)  # raises ConfigurationError without the env var
    facts = client.fetch_companyfacts(args.cik)
    subs = client.fetch_submissions(args.cik)
    print(f"cached companyfacts sha256 {facts.sha256[:16]} and submissions sha256 {subs.sha256[:16]} under {cache.root}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    started = now_iso()
    path = Path(args.companyfacts)
    if not path.exists():
        raise ConfigurationError(f"companyfacts file not found: {path}")
    as_of = date.fromisoformat(args.as_of)
    out = Path(args.out)
    doc, _ = load_companyfacts(path)
    result = analyze(doc, as_of, flags_path=args.flags, tags_path=args.tags, mode=args.mode)
    paths = write_outputs(result, out)
    write_manifest(out, mode="experiment", status="completed", started_at=started,
                   data_source_id=args.mode, split_manifest_hash=sha256_file(path),
                   sample_counts={"facts_in_scope": result.selection["facts_in_scope"]},
                   configuration_hash=sha256_files([Path(args.flags), Path(args.tags)]),
                   metrics_file=str(paths["evidence"]), evidence_status="demo")
    for s in result.summary:
        print(s)
    return 0


def cmd_flags(args: argparse.Namespace) -> int:
    path = Path(args.evidence)
    if not path.exists():
        raise ConfigurationError(f"evidence file not found: {path}; run demo or analyze first")
    with path.open("r", encoding="utf-8") as fh:
        doc = json.load(fh)
    problems = validate_evidence_schema(doc)
    if problems:
        raise SchemaError("evidence file failed validation: " + "; ".join(problems))
    flags = doc.get("flags", [])
    print(f"{doc['issuer']['name']} (CIK {doc['issuer']['cik']}), as of {doc['as_of']}: {len(flags)} review flags")
    for f in flags:
        print(f"  FY{f['fiscal_year']} {f['rule_id']}: value {f['value']:.3f} {f['op']} {f['threshold']} -> {f['message']}")
        print(f"      citations: {', '.join(f['citation_ids'])}")
    if not flags:
        print("  no review flags under the configured thresholds")
    return 0


def cmd_figures(args: argparse.Namespace) -> int:
    from .figures import render_all

    written = render_all(args.output, args.figures)
    for p in written:
        print(f"wrote {p}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sec_business_evidence", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("smoke", help="offline check on the first synthetic issuer")
    s.add_argument("--out", default=str(REPO_ROOT / "runs" / "smoke"))
    s.set_defaults(func=cmd_smoke)
    d = sub.add_parser("demo", help="analyse all three synthetic issuers into examples/output")
    d.add_argument("--out", default=str(OUTPUT_DIR))
    d.set_defaults(func=cmd_demo)
    f = sub.add_parser("fetch", help="fetch companyfacts and submissions for a CIK into the cache (network)")
    f.add_argument("--cik", required=True)
    f.add_argument("--cache-dir", default=str(REPO_ROOT / "cache"))
    f.set_defaults(func=cmd_fetch)
    a = sub.add_parser("analyze", help="analyse one companyfacts JSON at an analysis date")
    a.add_argument("--companyfacts", required=True)
    a.add_argument("--as-of", required=True, help="ISO date; only filings filed on or before it are used")
    a.add_argument("--out", required=True)
    a.add_argument("--flags", default=str(DEFAULT_FLAGS))
    a.add_argument("--tags", default=str(DEFAULT_TAGS))
    a.add_argument("--mode", default="cached-source", choices=["cached-source", "synthetic-demo"])
    a.set_defaults(func=cmd_analyze)
    g = sub.add_parser("flags", help="print the review flags in an evidence.json")
    g.add_argument("--evidence", required=True)
    g.set_defaults(func=cmd_flags)
    fig = sub.add_parser("figures", help="render SVG figures from examples/output")
    fig.add_argument("--output", default=str(OUTPUT_DIR))
    fig.add_argument("--figures", default=str(FIGURES_DIR))
    fig.set_defaults(func=cmd_figures)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ConfigurationError, NetworkError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except SchemaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except SecEvidenceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
