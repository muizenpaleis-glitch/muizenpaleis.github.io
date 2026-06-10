"""Streaming charts collector (req. 4 Tier 1, source #1).

Per-country published charts (Spotify weekly top 200 format). Matches
watchlist recordings by ISRC where the source exposes it, otherwise by
normalized artist + title via the matching engine.

The exact access route for Spotify chart data is an open question in
the requirements (req. 12: public charts site vs. third-party archives,
assess ToS at build time). The URL template and source name are
therefore configurable (RUM_CHARTS_URL_TEMPLATE); the parser expects
the public weekly-chart CSV format:

    Position,Track Name,Artist,Streams,URL

This module requires an explicit market list (a chart is per country).
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date

import httpx

from ..findings import FindingDraft, week_period
from ..matching import build_work_candidates
from ..models import WatchlistEntry
from ..ratelimit import request_with_backoff
from .base import Collector, register

logger = logging.getLogger("rum.collectors.charts")


def _parse_chart_csv(raw: bytes) -> list[dict]:
    """Parse the chart CSV, skipping any preamble before the header."""
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.lower().startswith("position,")),
        None,
    )
    if start is None:
        return []
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])))
    rows = []
    for row in reader:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        if row.get("position") and row.get("track name"):
            rows.append(row)
    return rows


@register
class ChartsCollector(Collector):
    name = "charts"
    entity_types = ("work",)

    def _client(self) -> httpx.Client:
        headers = {"User-Agent": self.context.config.user_agent}
        if self.context.http_client_factory is not None:
            return self.context.http_client_factory(headers=headers)
        return httpx.Client(headers=headers, timeout=30, follow_redirects=True)

    def collect(
        self,
        watchlist_slice: list[WatchlistEntry],
        market: str | None,
        since: date,
    ) -> list[FindingDraft]:
        cfg = self.context.config
        if not market:
            msg = (
                "charts: a chart is per country - configure markets for this "
                "module (run --market or RUM_MODULE_MARKETS)"
            )
            logger.error(msg)
            self.errors.append(msg)
            return []

        candidates = [
            c for c in build_work_candidates(self.context.session)
            if any(
                e.id == c.watchlist_id and e.applies_to_market(market)
                for e in watchlist_slice
            )
        ]
        if not candidates:
            return []

        url = cfg.charts_url_template.format(market=market.lower())
        with self._client() as client:
            response = request_with_backoff(
                client, "GET", url,
                limiter=self.context.limiter,
                max_retries=cfg.backoff_max_retries,
                backoff_base=cfg.backoff_base_seconds,
            )
        raw = response.content
        rows = _parse_chart_csv(raw)
        if not rows:
            msg = f"charts: no parseable chart rows from {url}"
            logger.error(msg)
            self.errors.append(msg)
            return []

        period = week_period(date.today())
        drafts: list[FindingDraft] = []
        for row in rows:
            self.items_checked += 1
            match = self.context.engine.match_song(
                title=row.get("track name"),
                artist=row.get("artist"),
                candidates=candidates,
                isrc=row.get("isrc") or None,  # matched by ISRC when exposed
            )
            if match is None:
                continue
            track_url = row.get("url", "")
            track_id = track_url.rstrip("/").rsplit("/", 1)[-1] or row["position"]
            drafts.append(
                FindingDraft(
                    watchlist_id=match.watchlist_id,
                    entity_type="work",
                    usage_type="streaming_chart",
                    market=market.upper(),
                    occurred_at=date.today(),
                    period=period,
                    source_module=self.name,
                    source_url=url,
                    source_item_id=f"{cfg.charts_source_name}-{market.lower()}-{track_id}",
                    match_level=match.level,
                    confidence=match.confidence,
                    matched_strings=match.matched_strings,
                    needs_review=match.needs_review,
                    details={
                        "chart": cfg.charts_source_name,
                        "position": int(row["position"]),
                        "streams": int(row["streams"]) if row.get("streams", "").isdigit() else None,
                        "track_name": row.get("track name"),
                        "artist": row.get("artist"),
                        "track_url": track_url,
                    },
                    evidence_content=raw,
                    evidence_ext="csv",
                )
            )
        return drafts
