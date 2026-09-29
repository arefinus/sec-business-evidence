"""Run manifest (contract section 5). Written by every smoke, demo and analyze run."""

from __future__ import annotations

import hashlib
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from . import PROJECT_ID

DEFAULT_SEED = 42


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_files(paths: list[Path]) -> str:
    """Hash of the sorted (name, sha256) pairs of several files."""
    h = hashlib.sha256()
    for p in sorted(paths, key=lambda x: x.name):
        h.update(p.name.encode("utf-8"))
        h.update(sha256_file(p).encode("utf-8"))
    return h.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_run_id(mode: str, started_at: str) -> str:
    stamp = started_at.replace(":", "").replace("-", "").replace("+0000", "Z")
    return f"{stamp}-{PROJECT_ID}-{mode}"


def write_manifest(
    out_dir: str | Path,
    *,
    mode: str,
    status: str,
    started_at: str,
    data_source_id: str,
    split_manifest_hash: str,
    sample_counts: dict[str, int],
    configuration_hash: str,
    metrics_file: Optional[str],
    predictions_file: Optional[str] = None,
    seed: int = DEFAULT_SEED,
    evidence_status: str = "demo",
) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {
        "schema_version": 1,
        "project_id": PROJECT_ID,
        "run_id": make_run_id(mode, started_at),
        "status": status,
        "mode": mode,
        "evidence_status": evidence_status,
        "git_commit": None,
        "data": {
            "source_id": data_source_id,
            "version": "v1",
            "split_manifest_hash": split_manifest_hash,
            "sample_counts": sample_counts,
        },
        "configuration_hash": configuration_hash,
        "seed": seed,
        "environment": {"python": platform.python_version(), "device": "cpu"},
        "metrics_file": metrics_file,
        "predictions_file": predictions_file,
        "started_at": started_at,
        "finished_at": now_iso(),
    }
    path = out / "run_manifest.yaml"
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(doc, fh, sort_keys=False)
    return path
