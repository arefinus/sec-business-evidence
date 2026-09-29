"""EDGAR data API client.

Fair access policy (https://www.sec.gov/os/accessing-edgar-data): declare a descriptive
User-Agent that identifies you and gives a way to contact you, and stay at or under
10 requests per second. This client refuses to run without a User-Agent taken from the
``SEC_USER_AGENT`` environment variable and sleeps between requests to respect the cap.

No API key exists for these endpoints. The endpoints do not send CORS headers, so a
browser page cannot call them directly; a script such as this one has to.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..errors import ConfigurationError, NetworkError
from ..facts.load import normalise_cik
from .cache import CacheEntry, JsonCache

USER_AGENT_ENV = "SEC_USER_AGENT"
TERMS_URL = "https://www.sec.gov/os/accessing-edgar-data"
COMPANYFACTS_BASE = "https://data.sec.gov/api/xbrl/companyfacts/"
SUBMISSIONS_BASE = "https://data.sec.gov/submissions/"
MAX_REQUESTS_PER_SECOND = 10
DEFAULT_TIMEOUT_SECONDS = 30


def companyfacts_url(cik: str | int) -> str:
    return f"{COMPANYFACTS_BASE}CIK{normalise_cik(cik)}.json"


def submissions_url(cik: str | int) -> str:
    return f"{SUBMISSIONS_BASE}CIK{normalise_cik(cik)}.json"


def user_agent_from_env(env: Optional[dict[str, str]] = None) -> str:
    env = os.environ if env is None else env
    value = (env.get(USER_AGENT_ENV) or "").strip()
    if len(value) < 8 or " " not in value:
        raise ConfigurationError(
            f"{USER_AGENT_ENV} is not set to a descriptive User-Agent. The SEC fair-access policy "
            f"({TERMS_URL}) requires one naming you and a contact address, for example "
            f'"Jane Analyst jane@example.invalid". Set it and run again.'
        )
    return value


@dataclass
class RateLimiter:
    """Sleep so that consecutive calls are at least ``min_interval`` seconds apart."""

    max_per_second: int = MAX_REQUESTS_PER_SECOND
    clock: Callable[[], float] = time.monotonic
    sleeper: Callable[[float], None] = time.sleep
    _last: Optional[float] = field(default=None, repr=False)

    @property
    def min_interval(self) -> float:
        return 1.0 / float(self.max_per_second)

    def wait(self) -> float:
        """Block if needed; return the seconds slept."""
        now = self.clock()
        slept = 0.0
        if self._last is not None:
            gap = now - self._last
            if gap < self.min_interval:
                slept = self.min_interval - gap
                self.sleeper(slept)
                now = now + slept
        self._last = now
        return slept


def http_get_json(url: str, headers: dict[str, str], timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Any:
    """Plain urllib GET. Tests replace this function to block the network."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https host)
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise NetworkError(f"HTTP {exc.code} from {url}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise NetworkError(f"network call to {url} failed: {exc}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NetworkError(f"response from {url} was not JSON") from exc


class EdgarClient:
    """Fetch companyfacts and submissions into a JsonCache."""

    def __init__(
        self,
        user_agent: str,
        cache: JsonCache,
        limiter: Optional[RateLimiter] = None,
        getter: Callable[[str, dict[str, str]], Any] = http_get_json,
    ) -> None:
        if not user_agent or len(user_agent.strip()) < 8:
            raise ConfigurationError("user_agent must be a descriptive string")
        self.user_agent = user_agent.strip()
        self.cache = cache
        self.limiter = limiter or RateLimiter()
        self._getter = getter

    @classmethod
    def from_env(cls, cache: JsonCache, env: Optional[dict[str, str]] = None, **kwargs: Any) -> "EdgarClient":
        return cls(user_agent_from_env(env), cache, **kwargs)

    @property
    def headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": "data.sec.gov",
        }

    def _fetch(self, key: str, url: str) -> CacheEntry:
        self.limiter.wait()
        payload = self._getter(url, self.headers)
        if not isinstance(payload, dict):
            raise NetworkError(f"unexpected payload type from {url}: {type(payload).__name__}")
        return self.cache.put(key, url, payload)

    def fetch_companyfacts(self, cik: str | int) -> CacheEntry:
        cik10 = normalise_cik(cik)
        return self._fetch(f"CIK{cik10}_companyfacts", companyfacts_url(cik10))

    def fetch_submissions(self, cik: str | int) -> CacheEntry:
        cik10 = normalise_cik(cik)
        return self._fetch(f"CIK{cik10}_submissions", submissions_url(cik10))
