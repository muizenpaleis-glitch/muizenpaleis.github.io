"""setlist.fm collector (req. 4 Tier 1, source #3) - official API only.

Concerts by watchlist performers: captures venue, city, country, date
and the setlist. Song-level matches against watchlist works are
high-confidence live-performance findings; for performers without a
known-works subset, every concert is a low-confidence finding flagged
for review (req. 3.3).

Compliance: official REST API (https://api.setlist.fm/docs/1.0/),
x-api-key from the SETLISTFM_API_KEY environment variable, honest
User-Agent with contact address, all requests through the central
rate limiter with exponential backoff (req. 4, 10). See SOURCES.md.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime

import httpx

from ..findings import FindingDraft
from ..matching import build_work_candidates
from ..models import WatchlistEntry
from ..ratelimit import request_with_backoff
from .base import Collector, register

logger = logging.getLogger("rum.collectors.setlistfm")

API_BASE = "https://api.setlist.fm/rest/1.0"
MAX_PAGES_PER_ARTIST = 20


def _parse_event_date(raw: str) -> date | None:
    """setlist.fm uses dd-MM-yyyy."""
    try:
        return datetime.strptime(raw, "%d-%m-%Y").date()
    except (TypeError, ValueError):
        return None


@register
class SetlistFmCollector(Collector):
    name = "setlistfm"
    entity_types = ("performer",)

    def _client(self) -> httpx.Client:
        cfg = self.context.config
        headers = {
            "x-api-key": cfg.setlistfm_api_key or "",
            "Accept": "application/json",
            "User-Agent": cfg.user_agent,
        }
        if self.context.http_client_factory is not None:
            return self.context.http_client_factory(headers=headers)
        return httpx.Client(headers=headers, timeout=30)

    def collect(
        self,
        watchlist_slice: list[WatchlistEntry],
        market: str | None,
        since: date,
    ) -> list[FindingDraft]:
        cfg = self.context.config
        if not cfg.setlistfm_api_key:
            msg = "setlistfm: SETLISTFM_API_KEY is not set, skipping module"
            logger.error(msg)
            self.errors.append(msg)
            return []

        # Work candidates are built once; per performer we narrow to the
        # known-works subset when one is defined (req. 3.3).
        all_candidates = build_work_candidates(self.context.session)
        by_id = {c.watchlist_id: c for c in all_candidates}
        drafts: list[FindingDraft] = []

        with self._client() as client:
            for entry in watchlist_slice:
                if entry.entity_type != "performer" or not entry.active:
                    continue
                if not entry.applies_to_market(market):
                    continue
                self.items_checked += 1
                try:
                    drafts.extend(
                        self._collect_performer(
                            client, entry, market, since, all_candidates, by_id
                        )
                    )
                except httpx.HTTPError as exc:
                    msg = f"setlistfm: {entry.id} ({entry.display_name}): {exc}"
                    logger.error(msg)
                    self.errors.append(msg)
        return drafts

    # -- per performer ------------------------------------------------------
    def _collect_performer(
        self, client, entry, market, since, all_candidates, by_id
    ) -> list[FindingDraft]:
        performer = entry.performer
        known_ids = list(performer.known_work_ids or []) if performer else []
        candidates = (
            [by_id[i] for i in known_ids if i in by_id] if known_ids else all_candidates
        )
        drafts: list[FindingDraft] = []
        for setlist in self._iter_setlists(client, entry, since):
            event_date = _parse_event_date(setlist.get("eventDate", ""))
            if event_date is None or event_date < since:
                continue
            country = (
                setlist.get("venue", {}).get("city", {}).get("country", {}).get("code")
            )
            if not country:
                continue
            if market and country.upper() != market.upper():
                continue
            identity = self.context.engine.match_performer(
                name=setlist.get("artist", {}).get("name"),
                performer_entry=entry,
                musicbrainz_id=setlist.get("artist", {}).get("mbid"),
            )
            if identity is None:
                continue  # the source artist does not match our performer
            drafts.extend(
                self._setlist_findings(
                    entry, setlist, event_date, country.upper(),
                    identity, candidates, known_ids,
                )
            )
        return drafts

    def _iter_setlists(self, client, entry, since: date):
        """Page through an artist's setlists (newest first) until `since`."""
        performer = entry.performer
        if performer is not None and performer.musicbrainz_id:
            url = f"{API_BASE}/artist/{performer.musicbrainz_id}/setlists"
            params: dict = {}
        else:
            url = f"{API_BASE}/search/setlists"
            params = {"artistName": entry.display_name}
        cfg = self.context.config
        for page in range(1, MAX_PAGES_PER_ARTIST + 1):
            try:
                response = request_with_backoff(
                    client, "GET", url,
                    limiter=self.context.limiter,
                    max_retries=cfg.backoff_max_retries,
                    backoff_base=cfg.backoff_base_seconds,
                    params={**params, "p": page},
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404 and page == 1:
                    return  # no setlists for this artist
                raise
            payload = response.json()
            setlists = payload.get("setlist", [])
            if not setlists:
                return
            oldest_on_page: date | None = None
            for item in setlists:
                yield item
                d = _parse_event_date(item.get("eventDate", ""))
                if d and (oldest_on_page is None or d < oldest_on_page):
                    oldest_on_page = d
            if oldest_on_page is not None and oldest_on_page < since:
                return
            total = payload.get("total", 0)
            per_page = payload.get("itemsPerPage", len(setlists)) or len(setlists)
            if page * per_page >= total:
                return

    def _setlist_findings(
        self, entry, setlist, event_date, country, identity, candidates, known_ids
    ) -> list[FindingDraft]:
        engine = self.context.engine
        evidence = json.dumps(setlist, ensure_ascii=False, indent=2).encode("utf-8")
        base_details = {
            "venue": setlist.get("venue", {}).get("name"),
            "city": setlist.get("venue", {}).get("city", {}).get("name"),
            "country": country,
            "event_date": event_date.isoformat(),
            "artist": setlist.get("artist", {}).get("name"),
            "performer_watchlist_id": entry.id,
            "performer_match": identity.matched_strings,
        }
        common = dict(
            usage_type="live_performance",
            market=country,
            occurred_at=event_date,
            period=event_date.isoformat(),
            source_module=self.name,
            source_url=setlist.get("url", ""),
            source_item_id=str(setlist.get("id", "")),
            evidence_content=evidence,
        )
        drafts: list[FindingDraft] = []
        songs = [
            song.get("name", "")
            for st in setlist.get("sets", {}).get("set", [])
            for song in st.get("song", [])
            if song.get("name") and not song.get("tape")
        ]
        for song_name in songs:
            match = engine.match_song(
                title=song_name, artist=entry.display_name, candidates=candidates
            )
            if match is None:
                continue
            # A finding is only as solid as its weakest link: identity x song.
            confidence = round(min(identity.confidence, match.confidence), 4)
            drafts.append(
                FindingDraft(
                    watchlist_id=match.watchlist_id,
                    entity_type="work",
                    match_level=max(identity.level, match.level),
                    confidence=confidence,
                    matched_strings=match.matched_strings,
                    needs_review=match.needs_review or identity.needs_review,
                    details={**base_details, "song": song_name},
                    **common,
                )
            )
        if not known_ids and not drafts:
            # No known-works subset: the concert itself is a low-confidence
            # finding flagged for review (req. 3.3).
            artist_only = engine.artist_only_concert(
                entry, setlist.get("artist", {}).get("name", "")
            )
            drafts.append(
                FindingDraft(
                    watchlist_id=entry.id,
                    entity_type="performer",
                    match_level=artist_only.level,
                    confidence=artist_only.confidence,
                    matched_strings=artist_only.matched_strings,
                    needs_review=True,
                    details={**base_details, "song_count": len(songs)},
                    **common,
                )
            )
        return drafts
