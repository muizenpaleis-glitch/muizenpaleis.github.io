"""Acceptance criterion 6: all collectors respect the central rate
limiter, verifiable in logs."""

import logging

import httpx
import pytest

from rum.ratelimit import RateLimiter, request_with_backoff
from rum.runner import run_collectors

from conftest import SINCE


def test_limiter_enforces_min_interval_and_logs(caplog):
    sleeps: list[float] = []
    limiter = RateLimiter(min_interval_seconds=2.0, sleep=sleeps.append)
    with caplog.at_level(logging.INFO, logger="rum.ratelimit"):
        limiter.acquire("https://api.setlist.fm/rest/1.0/search/setlists")
        limiter.acquire("https://api.setlist.fm/rest/1.0/search/setlists")
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 2.0
    messages = [r.message for r in caplog.records]
    assert any("waiting" in m and "api.setlist.fm" in m for m in messages)
    assert sum("slot acquired for api.setlist.fm" in m for m in messages) == 2


def test_limiter_is_per_domain():
    sleeps: list[float] = []
    limiter = RateLimiter(min_interval_seconds=2.0, sleep=sleeps.append)
    limiter.acquire("https://api.setlist.fm/x")
    limiter.acquire("https://api.themoviedb.org/y")  # different domain: no wait
    assert sleeps == []


def test_backoff_on_429_then_success():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"ok": True})

    sleeps: list[float] = []
    limiter = RateLimiter(min_interval_seconds=0.0)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = request_with_backoff(
            client, "GET", "https://api.setlist.fm/rest/1.0/x",
            limiter=limiter, max_retries=2, backoff_base=2.0, sleep=sleeps.append,
        )
    assert response.status_code == 200
    assert calls["n"] == 2
    assert sleeps and sleeps[0] >= 1.0


def test_backoff_gives_up_after_max_retries():
    def handler(request):
        return httpx.Response(503)

    limiter = RateLimiter(min_interval_seconds=0.0)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            request_with_backoff(
                client, "GET", "https://api.setlist.fm/rest/1.0/x",
                limiter=limiter, max_retries=2, backoff_base=0.0, sleep=lambda _: None,
            )


def test_collector_requests_go_through_central_limiter(
    seeded_session, config, http_client_factory, caplog
):
    """The setlist.fm collector must acquire a slot for every API request
    - verifiable in the rum.ratelimit log (acceptance criterion 6)."""
    with caplog.at_level(logging.INFO, logger="rum.ratelimit"):
        run_collectors(
            seeded_session, config, modules=["setlistfm"], since=SINCE,
            http_client_factory=http_client_factory,
        )
    acquisitions = [
        r.message for r in caplog.records
        if "slot acquired for api.setlist.fm" in r.message
    ]
    assert len(acquisitions) == 2  # one per performer lookup
