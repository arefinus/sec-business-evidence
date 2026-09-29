"""On-disk JSON cache. Every entry records the source URL, the retrieval time and the
sha256 of the payload so that staleness and tampering are both detectable."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from ..errors import CacheError

ENVELOPE_VERSION = 1


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_of_json(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _parse_iso(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass(frozen=True)
class CacheEntry:
    key: str
    url: str
    retrieved_at: datetime
    sha256: str
    payload: Any

    def age(self, now: Optional[datetime] = None) -> timedelta:
        now = now or datetime.now(timezone.utc)
        return now - self.retrieved_at

    def is_stale(self, max_age: timedelta, now: Optional[datetime] = None) -> bool:
        return self.age(now) > max_age

    def verify(self) -> None:
        actual = sha256_of_json(self.payload)
        if actual != self.sha256:
            raise CacheError(
                f"cache entry {self.key!r} failed integrity check: recorded {self.sha256[:12]}..., "
                f"actual {actual[:12]}...; delete the file and fetch again"
            )

    def to_envelope(self) -> dict[str, Any]:
        return {
            "envelope_version": ENVELOPE_VERSION,
            "key": self.key,
            "url": self.url,
            "retrieved_at": self.retrieved_at.isoformat(),
            "sha256": self.sha256,
            "payload": self.payload,
        }


class JsonCache:
    """Directory of ``<key>.json`` envelopes."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def path_for(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
        return self.root / f"{safe}.json"

    def has(self, key: str) -> bool:
        return self.path_for(key).exists()

    def put(self, key: str, url: str, payload: Any, retrieved_at: Optional[datetime] = None) -> CacheEntry:
        entry = CacheEntry(
            key=key,
            url=url,
            retrieved_at=retrieved_at or datetime.now(timezone.utc),
            sha256=sha256_of_json(payload),
            payload=payload,
        )
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.path_for(key).with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(entry.to_envelope(), fh, indent=1, sort_keys=True)
        tmp.replace(self.path_for(key))
        return entry

    def get(self, key: str, verify: bool = True) -> CacheEntry:
        p = self.path_for(key)
        if not p.exists():
            raise CacheError(f"no cache entry for {key!r} at {p}; run the fetch command first")
        with p.open("r", encoding="utf-8") as fh:
            env = json.load(fh)
        for field in ("url", "retrieved_at", "sha256", "payload"):
            if field not in env:
                raise CacheError(f"cache file {p} is missing field {field!r}")
        entry = CacheEntry(
            key=key,
            url=env["url"],
            retrieved_at=_parse_iso(env["retrieved_at"]),
            sha256=env["sha256"],
            payload=env["payload"],
        )
        if verify:
            entry.verify()
        return entry

    def get_fresh(self, key: str, max_age: timedelta, now: Optional[datetime] = None) -> CacheEntry:
        entry = self.get(key)
        if entry.is_stale(max_age, now):
            raise CacheError(
                f"cache entry {key!r} retrieved {entry.retrieved_at.date().isoformat()} is older than "
                f"{max_age.days} days; fetch again or pass a larger --max-age-days"
            )
        return entry
