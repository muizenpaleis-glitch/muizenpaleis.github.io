"""MusicBrainz enrichment (req. 4 Tier 1, source #5).

Not a usage source: it strengthens matching by resolving artist aliases
and ISRC -> canonical recording titles from the MusicBrainz web service.

Compliance: official API, MusicBrainz etiquette asks for an identifying
User-Agent and at most 1 request/second - our honest User-Agent and the
central limiter's conservative default (1 req / 2 s) satisfy both.
"""

from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from .config import Config
from .models import WatchlistEntry, Work, WorkRecording
from .ratelimit import RateLimiter, request_with_backoff

logger = logging.getLogger("rum.enrich")

API_BASE = "https://musicbrainz.org/ws/2"


def _client(config: Config, client_factory=None) -> httpx.Client:
    headers = {"User-Agent": config.user_agent, "Accept": "application/json"}
    if client_factory is not None:
        return client_factory(headers=headers)
    return httpx.Client(headers=headers, timeout=30)


def _get(client, limiter, config, path: str, params: dict | None = None) -> dict:
    response = request_with_backoff(
        client, "GET", f"{API_BASE}/{path}",
        limiter=limiter,
        max_retries=config.backoff_max_retries,
        backoff_base=config.backoff_base_seconds,
        params={**(params or {}), "fmt": "json"},
    )
    return response.json()


def enrich_performer_aliases(
    session: Session, config: Config, limiter: RateLimiter | None = None,
    client_factory=None,
) -> list[str]:
    """For performers with a MusicBrainz ID, merge MB aliases into the
    watchlist aliases. Returns human-readable result messages."""
    limiter = limiter or RateLimiter(config.rate_limit_seconds)
    messages: list[str] = []
    performers = (
        session.query(WatchlistEntry)
        .filter(WatchlistEntry.entity_type == "performer", WatchlistEntry.active.is_(True))
        .all()
    )
    with _client(config, client_factory) as client:
        for entry in performers:
            p = entry.performer
            if p is None or not p.musicbrainz_id:
                continue
            try:
                data = _get(
                    client, limiter, config,
                    f"artist/{p.musicbrainz_id}", {"inc": "aliases"},
                )
            except httpx.HTTPError as exc:
                messages.append(f"{entry.id}: MusicBrainz lookup failed ({exc})")
                continue
            known = {a.casefold() for a in [entry.display_name, *(p.aliases or [])]}
            new = [
                a["name"]
                for a in data.get("aliases", [])
                if a.get("name") and a["name"].casefold() not in known
            ]
            canonical = data.get("name")
            if canonical and canonical.casefold() not in known:
                new.insert(0, canonical)
            if new:
                p.aliases = list(p.aliases or []) + new
                messages.append(f"{entry.id}: added {len(new)} alias(es): {', '.join(new)}")
    session.flush()
    return messages


def enrich_work_titles_by_isrc(
    session: Session, config: Config, limiter: RateLimiter | None = None,
    client_factory=None,
) -> list[str]:
    """For recordings with an ISRC, add the MusicBrainz canonical
    recording title as an alternative work title when it differs."""
    limiter = limiter or RateLimiter(config.rate_limit_seconds)
    messages: list[str] = []
    recordings = (
        session.query(WorkRecording)
        .join(Work)
        .join(WatchlistEntry, Work.watchlist_id == WatchlistEntry.id)
        .filter(WorkRecording.isrc.isnot(None), WatchlistEntry.active.is_(True))
        .all()
    )
    with _client(config, client_factory) as client:
        for recording in recordings:
            try:
                data = _get(client, limiter, config, f"isrc/{recording.isrc}")
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    continue  # ISRC unknown to MusicBrainz
                messages.append(f"{recording.isrc}: lookup failed ({exc})")
                continue
            except httpx.HTTPError as exc:
                messages.append(f"{recording.isrc}: lookup failed ({exc})")
                continue
            work = recording.work
            known = {
                t.casefold()
                for t in [
                    work.entry.display_name,
                    recording.recording_title,
                    *(work.alternative_titles or []),
                ]
            }
            new = [
                mb_rec["title"]
                for mb_rec in data.get("recordings", [])
                if mb_rec.get("title") and mb_rec["title"].casefold() not in known
            ]
            if new:
                work.alternative_titles = list(work.alternative_titles or []) + new
                messages.append(
                    f"{work.watchlist_id} ({recording.isrc}): added alternative "
                    f"title(s): {', '.join(new)}"
                )
    session.flush()
    return messages


def enrich_all(session: Session, config: Config, client_factory=None) -> list[str]:
    limiter = RateLimiter(config.rate_limit_seconds)
    return enrich_performer_aliases(session, config, limiter, client_factory) + \
        enrich_work_titles_by_isrc(session, config, limiter, client_factory)
