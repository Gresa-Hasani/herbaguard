"""Polite HTTP client for external sources: User-Agent, timeouts, per-host rate limits, retries.

Retries (exponential backoff with jitter) apply to network errors, HTTP 429 and HTTP 5xx.
Other 4xx responses are returned to the caller unchanged: for some APIs a 404 is a valid answer
("no results"), and the caller records it as such.
"""

from __future__ import annotations

import ssl
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import certifi
import httpx
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from herbaguard.core.config import Settings
from herbaguard.core.logging import get_logger

logger = get_logger("herbaguard.http")

# Minimum seconds between requests per host. Chosen from each provider's documented limits:
# NCBI E-utilities 3 req/s without key; openFDA 240 req/min without key; Wikidata asks for
# moderation; EMA/NCCIH are websites, so we stay slow.
DEFAULT_MIN_INTERVAL: dict[str, float] = {
    "eutils.ncbi.nlm.nih.gov": 0.40,
    "api.fda.gov": 0.30,
    "rxnav.nlm.nih.gov": 0.06,
    "www.ema.europa.eu": 0.75,
    "www.nccih.nih.gov": 0.75,
    "query.wikidata.org": 1.0,
    "api.gbif.org": 0.10,
    "list.worldfloraonline.org": 0.5,
}
DEFAULT_ETHCSTWIN_INTERVAL = 0.10
MAX_ATTEMPTS = 4


class RetryableStatusError(Exception):
    def __init__(self, response: httpx.Response) -> None:
        super().__init__(f"HTTP {response.status_code} from {response.request.url}")
        self.response = response


@dataclass(frozen=True, slots=True)
class HttpResult:
    url: str  # final URL (after redirects), query included
    status_code: int
    content_type: str | None
    content: bytes
    elapsed_seconds: float

    def json(self) -> Any:
        import json

        return json.loads(self.content)


class _RateLimiter:
    def __init__(self, intervals: dict[str, float]) -> None:
        self._intervals = intervals
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    enabled = True

    def wait(self, host: str) -> None:
        if not self.enabled:
            return
        interval = self._intervals.get(host)
        if interval is None:
            interval = DEFAULT_ETHCSTWIN_INTERVAL if host.endswith("ethcstwin.di.uoa.gr") else 0.2
        with self._lock:
            now = time.monotonic()
            ready_at = self._last.get(host, 0.0) + interval
            if ready_at > now:
                time.sleep(ready_at - now)
            self._last[host] = time.monotonic()


def _log_retry(state: RetryCallState) -> None:
    exc = state.outcome.exception() if state.outcome else None
    logger.warning("http_retry", attempt=state.attempt_number, error=str(exc)[:200])


CERT_DIR = Path(__file__).parent / "certs"


def build_ssl_context() -> ssl.SSLContext:
    """certifi trust store plus intermediate CA certificates shipped in ``ingestion/certs``.

    The ETHCSTWIN servers (*.ethcstwin.di.uoa.gr:65000) send only their leaf certificate. Windows
    curl fetches the missing intermediate itself; OpenSSL does not, so verification would fail.
    The intermediate (HARICA Institutional TLS RSA 2) chains to a root already in certifi, so
    adding it keeps full certificate verification. Verification is never disabled.
    """
    context = ssl.create_default_context(cafile=certifi.where())
    for pem in sorted(CERT_DIR.glob("*.pem")):
        context.load_verify_locations(cafile=str(pem))
    return context


class HttpClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        min_interval: dict[str, float] | None = None,
        retry_wait_max: float = 30.0,
        rate_limit: bool = True,
    ) -> None:
        headers = {"User-Agent": settings.http_user_agent}
        if settings.contact_email:
            headers["From"] = settings.contact_email
        self._client = httpx.Client(
            headers=headers,
            timeout=settings.http_timeout_seconds,
            follow_redirects=True,
            transport=transport,
            verify=build_ssl_context(),
        )
        self._limiter = _RateLimiter({**DEFAULT_MIN_INTERVAL, **(min_interval or {})})
        self._limiter.enabled = rate_limit  # tests against mocked transports disable it
        self._retry_wait_max = retry_wait_max

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResult:
        @retry(
            retry=retry_if_exception_type((httpx.TransportError, RetryableStatusError)),
            stop=stop_after_attempt(MAX_ATTEMPTS),
            wait=wait_random_exponential(multiplier=1, max=self._retry_wait_max),
            before_sleep=_log_retry,
            reraise=True,
        )
        def _send() -> HttpResult:
            self._limiter.wait(urlsplit(url).hostname or "")
            started = time.perf_counter()
            response = self._client.request(method, url, params=params, data=data, headers=headers)
            if response.status_code == 429 or response.status_code >= 500:
                raise RetryableStatusError(response)
            return HttpResult(
                url=str(response.url),
                status_code=response.status_code,
                content_type=response.headers.get("content-type"),
                content=response.content,
                elapsed_seconds=time.perf_counter() - started,
            )

        return _send()

    def get(self, url: str, **kwargs: Any) -> HttpResult:
        return self.request("GET", url, **kwargs)
