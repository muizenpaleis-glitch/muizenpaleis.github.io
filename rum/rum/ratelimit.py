"""Central per-domain rate limiter (req. 4 collector behavior, 10.4).

One shared instance is passed to every collector. Defaults to at most
1 request per 2 seconds per domain. Every acquisition is logged so
compliance is verifiable in logs (acceptance criterion 6). Requests
against a single domain are serialized via a per-domain lock - never
parallelized (req. 4).
"""

from __future__ import annotations

import logging
import threading
import time
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("rum.ratelimit")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class RateLimiter:
    def __init__(self, min_interval_seconds: float = 2.0, sleep=time.sleep):
        self.min_interval = min_interval_seconds
        self._sleep = sleep
        self._last_request: dict[str, float] = {}
        self._domain_locks: dict[str, threading.Lock] = {}
        self._lock = threading.Lock()

    def _domain_lock(self, domain: str) -> threading.Lock:
        with self._lock:
            return self._domain_locks.setdefault(domain, threading.Lock())

    def acquire(self, url_or_domain: str) -> None:
        """Block until a request to this domain is allowed."""
        domain = urlparse(url_or_domain).netloc or url_or_domain
        with self._domain_lock(domain):
            now = time.monotonic()
            last = self._last_request.get(domain)
            if last is not None:
                wait = self.min_interval - (now - last)
                if wait > 0:
                    logger.info(
                        "rate_limiter: waiting %.2fs before request to %s", wait, domain
                    )
                    self._sleep(wait)
            self._last_request[domain] = time.monotonic()
            logger.info("rate_limiter: slot acquired for %s", domain)


def request_with_backoff(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    limiter: RateLimiter,
    max_retries: int = 4,
    backoff_base: float = 2.0,
    sleep=time.sleep,
    **kwargs,
) -> httpx.Response:
    """Rate-limited request with exponential backoff on 429/5xx (req. 4)."""
    attempt = 0
    while True:
        limiter.acquire(url)
        response = client.request(method, url, **kwargs)
        if response.status_code not in RETRYABLE_STATUS:
            response.raise_for_status()
            return response
        attempt += 1
        if attempt > max_retries:
            response.raise_for_status()
            return response
        delay = backoff_base * (2 ** (attempt - 1))
        retry_after = response.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            delay = max(delay, float(retry_after))
        logger.warning(
            "backoff: HTTP %s from %s, retry %d/%d in %.1fs",
            response.status_code, url, attempt, max_retries, delay,
        )
        sleep(delay)
