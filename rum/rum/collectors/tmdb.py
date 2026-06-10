"""TMDb collector (req. 4 Tier 1, source #4) - official API.

For watchlist AV productions: streaming availability per country via
TMDb watch providers. A hit on the production (the film is available on
a VOD service in a market) is a valid finding even when individual cues
can't be observed (req. 3.2).

Productions with a known TMDb ID match at Level 1; otherwise the title
(+ year) is searched and matched through the matching engine.
Compliance: official API, key via TMDB_API_KEY, central rate limiter.
"""

from __future__ import annotations

import json
import logging
from datetime import date

import httpx

from ..findings import FindingDraft, week_period
from ..matching import MatchResult
from ..models import WatchlistEntry
from ..ratelimit import request_with_backoff
from .base import Collector, register

logger = logging.getLogger("rum.collectors.tmdb")

API_BASE = "https://api.themoviedb.org/3"


@register
class TmdbCollector(Collector):
    name = "tmdb"
    entity_types = ("av_production",)

    def _client(self) -> httpx.Client:
        headers = {"User-Agent": self.context.config.user_agent}
        if self.context.http_client_factory is not None:
            return self.context.http_client_factory(headers=headers)
        return httpx.Client(headers=headers, timeout=30)

    def _get(self, client, path: str, params: dict | None = None) -> dict:
        cfg = self.context.config
        response = request_with_backoff(
            client, "GET", f"{API_BASE}/{path}",
            limiter=self.context.limiter,
            max_retries=cfg.backoff_max_retries,
            backoff_base=cfg.backoff_base_seconds,
            params={**(params or {}), "api_key": cfg.tmdb_api_key},
        )
        return response.json()

    def collect(
        self,
        watchlist_slice: list[WatchlistEntry],
        market: str | None,
        since: date,
    ) -> list[FindingDraft]:
        if not self.context.config.tmdb_api_key:
            msg = "tmdb: TMDB_API_KEY is not set, skipping module"
            logger.error(msg)
            self.errors.append(msg)
            return []
        drafts: list[FindingDraft] = []
        with self._client() as client:
            for entry in watchlist_slice:
                if entry.entity_type != "av_production" or not entry.active:
                    continue
                self.items_checked += 1
                try:
                    drafts.extend(self._collect_production(client, entry, market))
                except httpx.HTTPError as exc:
                    msg = f"tmdb: {entry.id} ({entry.display_name}): {exc}"
                    logger.error(msg)
                    self.errors.append(msg)
        return drafts

    def _resolve(self, client, entry) -> tuple[str, str, MatchResult] | None:
        """Return (kind, tmdb_id, match) for a production, resolving via
        the known TMDb ID (Level 1) or a title search (Level 2/3)."""
        av = entry.av_production
        kind = "tv" if (av and av.production_type == "series") else "movie"
        if av and av.tmdb_id:
            match = self.context.engine.match_production(
                title=None, production_entry=entry, tmdb_id=av.tmdb_id
            )
            return kind, str(av.tmdb_id), match
        search = self._get(
            client, f"search/{kind}",
            {
                "query": entry.display_name,
                **({"year": av.production_year} if av and av.production_year else {}),
            },
        )
        best: tuple[str, MatchResult] | None = None
        for result in search.get("results", [])[:5]:
            title = result.get("title") or result.get("name")
            release = result.get("release_date") or result.get("first_air_date") or ""
            year = int(release[:4]) if release[:4].isdigit() else None
            match = self.context.engine.match_production(
                title=title, production_entry=entry, year=year
            )
            if match and (best is None or match.confidence > best[1].confidence):
                best = (str(result["id"]), match)
        if best is None:
            return None
        return kind, best[0], best[1]

    def _collect_production(self, client, entry, market) -> list[FindingDraft]:
        resolved = self._resolve(client, entry)
        if resolved is None or resolved[2] is None:
            return []
        kind, tmdb_id, match = resolved
        payload = self._get(client, f"{kind}/{tmdb_id}/watch/providers")
        evidence = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        period = week_period(date.today())
        drafts: list[FindingDraft] = []
        for country, offer in sorted(payload.get("results", {}).items()):
            if market and country.upper() != market.upper():
                continue
            if not entry.applies_to_market(country):
                continue
            providers = {
                offer_type: [p.get("provider_name") for p in offer.get(offer_type, [])]
                for offer_type in ("flatrate", "rent", "buy", "ads", "free")
                if offer.get(offer_type)
            }
            if not providers:
                continue
            drafts.append(
                FindingDraft(
                    watchlist_id=entry.id,
                    entity_type="av_production",
                    usage_type="vod_availability",
                    market=country.upper(),
                    occurred_at=date.today(),
                    period=period,
                    source_module=self.name,
                    source_url=offer.get(
                        "link", f"https://www.themoviedb.org/{kind}/{tmdb_id}/watch"
                    ),
                    source_item_id=f"tmdb-{kind}-{tmdb_id}-{country.upper()}",
                    match_level=match.level,
                    confidence=match.confidence,
                    matched_strings=match.matched_strings,
                    needs_review=match.needs_review,
                    details={
                        "tmdb_id": tmdb_id,
                        "kind": kind,
                        "title": entry.display_name,
                        "providers": providers,
                    },
                    evidence_content=evidence,
                )
            )
        return drafts
