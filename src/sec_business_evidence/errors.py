"""Exception types. Every boundary failure names what is wrong and what to do."""

from __future__ import annotations


class SecEvidenceError(Exception):
    """Base class for all package errors."""


class ConfigurationError(SecEvidenceError):
    """A required setting is missing or malformed (for example SEC_USER_AGENT)."""


class NetworkError(SecEvidenceError):
    """A network call failed or was blocked. Nothing was cached."""


class CacheError(SecEvidenceError):
    """A cache entry is missing, stale or does not match its recorded hash."""


class SchemaError(SecEvidenceError):
    """Input JSON does not have the expected companyfacts or submissions shape."""


class PeriodMismatchError(SecEvidenceError):
    """Two facts with incompatible durations were compared."""


class UnitMismatchError(SecEvidenceError):
    """Two facts with different units were combined."""
