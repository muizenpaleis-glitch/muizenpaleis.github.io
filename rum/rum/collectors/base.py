"""Common collector interface (req. 4).

Every source is a pluggable module implementing
    collect(watchlist_slice, market, since) -> findings[]
where findings are FindingDrafts (persistence, dedupe and rejection
memory are handled centrally by the runner / findings pipeline).
Adding a country or source must not require touching the core.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from ..config import Config
from ..findings import FindingDraft
from ..matching import MatchingEngine
from ..models import WatchlistEntry
from ..ratelimit import RateLimiter


@dataclass
class CollectorContext:
    """Shared services handed to every collector by the runner."""

    config: Config
    session: Session
    engine: MatchingEngine
    limiter: RateLimiter  # the central, shared rate limiter (req. 10.4)
    http_client_factory: object | None = None  # tests inject a mock transport


class Collector(abc.ABC):
    """Base class for source modules."""

    #: unique module name, used in findings, run logs and SOURCES.md
    name: str = ""
    #: which watchlist entity types this collector consumes
    entity_types: tuple[str, ...] = ()

    def __init__(self, context: CollectorContext):
        self.context = context
        self.items_checked = 0
        self.errors: list[str] = []

    @abc.abstractmethod
    def collect(
        self,
        watchlist_slice: list[WatchlistEntry],
        market: str | None,
        since: date,
    ) -> list[FindingDraft]:
        """Check the given watchlist entries against this source and
        return finding drafts. `market` is an ISO country code or None
        for all markets; `since` is the start of the collection window."""


REGISTRY: dict[str, type[Collector]] = {}


def register(cls: type[Collector]) -> type[Collector]:
    if not cls.name:
        raise ValueError(f"{cls.__name__} has no module name")
    REGISTRY[cls.name] = cls
    return cls
