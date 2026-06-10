"""YouTube collector (req. 4 Tier 1, source #2) - official Data API v3.

For watchlist works, tracks official and prominent uploads and captures
view counts; once a baseline snapshot exists (>= 6 days old), findings
carry the weekly view-count delta as the usage signal. The region
signal on YouTube is weak, so the market is recorded as "global"
(req. 4 source #2).

Compliance: official API, key via YOUTUBE_API_KEY, central rate limiter.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta

import httpx

from ..findings import FindingDraft, week_period
from ..matching import build_work_candidates
from ..models import VideoViewSnapshot, WatchlistEntry, utcnow
from ..ratelimit import request_with_backoff
from .base import Collector, register

logger = logging.getLogger("rum.collectors.youtube")

API_BASE = "https://www.googleapis.com/youtube/v3"
SEARCH_RESULTS = 5


@register
class YouTubeCollector(Collector):
    name = "youtube"
    entity_types = ("work",)

    def _client(self) -> httpx.Client:
        headers = {"User-Agent": self.context.config.user_agent}
        if self.context.http_client_factory is not None:
            return self.context.http_client_factory(headers=headers)
        return httpx.Client(headers=headers, timeout=30)

    def _get(self, client, path: str, params: dict) -> dict:
        cfg = self.context.config
        response = request_with_backoff(
            client, "GET", f"{API_BASE}/{path}",
            limiter=self.context.limiter,
            max_retries=cfg.backoff_max_retries,
            backoff_base=cfg.backoff_base_seconds,
            params={**params, "key": cfg.youtube_api_key},
        )
        return response.json()

    def collect(
        self,
        watchlist_slice: list[WatchlistEntry],
        market: str | None,
        since: date,
    ) -> list[FindingDraft]:
        if not self.context.config.youtube_api_key:
            msg = "youtube: YOUTUBE_API_KEY is not set, skipping module"
            logger.error(msg)
            self.errors.append(msg)
            return []
        # Region signal is weak on YouTube: findings are "global", so a
        # market-restricted run does not apply to this module.
        if market:
            logger.info("youtube: market %s requested; module reports global only", market)

        candidates = build_work_candidates(self.context.session)
        by_id = {c.watchlist_id: c for c in candidates}
        drafts: list[FindingDraft] = []
        with self._client() as client:
            for entry in watchlist_slice:
                if entry.entity_type != "work" or not entry.active:
                    continue
                candidate = by_id.get(entry.id)
                if candidate is None:
                    continue
                self.items_checked += 1
                try:
                    drafts.extend(self._collect_work(client, entry, candidate, candidates))
                except httpx.HTTPError as exc:
                    msg = f"youtube: {entry.id} ({entry.display_name}): {exc}"
                    logger.error(msg)
                    self.errors.append(msg)
        return drafts

    def _collect_work(self, client, entry, candidate, candidates) -> list[FindingDraft]:
        artist = candidate.artists[0] if candidate.artists else ""
        query = f"{artist} {entry.display_name}".strip()
        search = self._get(
            client, "search",
            {"part": "snippet", "q": query, "type": "video", "maxResults": SEARCH_RESULTS},
        )
        video_ids = [
            item["id"]["videoId"]
            for item in search.get("items", [])
            if item.get("id", {}).get("videoId")
        ]
        if not video_ids:
            return []
        videos = self._get(
            client, "videos",
            {"part": "snippet,statistics", "id": ",".join(video_ids)},
        )
        drafts: list[FindingDraft] = []
        for video in videos.get("items", []):
            title = video.get("snippet", {}).get("title", "")
            channel = video.get("snippet", {}).get("channelTitle", "")
            match = self.context.engine.match_song(
                title=title, artist=channel, candidates=[candidate]
            )
            if match is None:
                continue
            drafts.append(self._video_finding(entry, video, match))
        return drafts

    def _video_finding(self, entry, video, match) -> FindingDraft:
        session = self.context.session
        video_id = video["id"]
        view_count = int(video.get("statistics", {}).get("viewCount", 0))
        # Weekly delta: compare against the latest snapshot that is old
        # enough to represent the previous week.
        cutoff = utcnow() - timedelta(days=6)
        previous = (
            session.query(VideoViewSnapshot)
            .filter(
                VideoViewSnapshot.video_id == video_id,
                VideoViewSnapshot.watchlist_id == entry.id,
                VideoViewSnapshot.captured_at <= cutoff,
            )
            .order_by(VideoViewSnapshot.captured_at.desc())
            .first()
        )
        delta = view_count - previous.view_count if previous else None
        # Store at most one snapshot per day per video (idempotent re-runs).
        latest = (
            session.query(VideoViewSnapshot)
            .filter_by(video_id=video_id, watchlist_id=entry.id)
            .order_by(VideoViewSnapshot.captured_at.desc())
            .first()
        )
        if latest is None or latest.captured_at <= utcnow() - timedelta(days=1):
            session.add(
                VideoViewSnapshot(
                    video_id=video_id, watchlist_id=entry.id, view_count=view_count
                )
            )
        return FindingDraft(
            watchlist_id=match.watchlist_id,
            entity_type="work",
            usage_type="video_views",
            market="global",
            occurred_at=date.today(),
            period=week_period(date.today()),
            source_module=self.name,
            source_url=f"https://www.youtube.com/watch?v={video_id}",
            source_item_id=video_id,
            match_level=match.level,
            confidence=match.confidence,
            matched_strings=match.matched_strings,
            needs_review=match.needs_review,
            details={
                "video_id": video_id,
                "video_title": video.get("snippet", {}).get("title"),
                "channel": video.get("snippet", {}).get("channelTitle"),
                "view_count": view_count,
                "previous_view_count": previous.view_count if previous else None,
                "view_delta": delta,
            },
            evidence_content=json.dumps(video, ensure_ascii=False, indent=2).encode("utf-8"),
        )
