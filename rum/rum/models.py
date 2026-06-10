"""Database schema: watchlist (req. 3) and findings (req. 6).

SQLite is used for the local MVP; every type used here (String, Text,
Integer, Float, Boolean, Date, DateTime, JSON) maps cleanly onto
PostgreSQL, as required by req. 6.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ENTITY_TYPES = ("work", "av_production", "performer")
PRIORITIES = ("high", "normal")
USAGE_TYPES = (
    "streaming_chart",
    "playlist",
    "video_views",
    "live_performance",
    "tv_broadcast",
    "radio_airplay",
    "vod_availability",
)
FINDING_STATUSES = ("new", "reviewed", "false_positive", "exported")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------
# Watchlist (req. 3)
# --------------------------------------------------------------------------

class WatchlistEntry(Base):
    """Common fields shared by all three entity types (req. 3.4)."""

    __tablename__ = "watchlist_entries"

    # The CMO-internal ID (work ID / production ID / performer ID).
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(20), index=True)
    display_name: Mapped[str] = mapped_column(String(500))
    priority: Mapped[str] = mapped_column(String(10), default="normal")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # Optional list of ISO country codes; empty/null means all markets.
    country_filter: Mapped[list | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    work: Mapped["Work | None"] = relationship(
        back_populates="entry", cascade="all, delete-orphan", uselist=False
    )
    av_production: Mapped["AvProduction | None"] = relationship(
        back_populates="entry", cascade="all, delete-orphan", uselist=False
    )
    performer: Mapped["Performer | None"] = relationship(
        back_populates="entry", cascade="all, delete-orphan", uselist=False
    )

    def applies_to_market(self, market: str | None) -> bool:
        """Country filter check: monitor this entry only in listed markets."""
        if not self.country_filter or market is None or market == "global":
            return True
        return market.upper() in [c.upper() for c in self.country_filter]


class Work(Base):
    """Musical work (req. 3.1). Identifiers may be partially missing."""

    __tablename__ = "works"

    watchlist_id: Mapped[str] = mapped_column(
        ForeignKey("watchlist_entries.id"), primary_key=True
    )
    iswc: Mapped[str | None] = mapped_column(String(15), nullable=True, index=True)
    alternative_titles: Mapped[list] = mapped_column(JSON, default=list)
    # List of {"name": str, "ipi": str | None}.
    writers: Mapped[list] = mapped_column(JSON, default=list)

    entry: Mapped[WatchlistEntry] = relationship(back_populates="work")
    recordings: Mapped[list["WorkRecording"]] = relationship(
        back_populates="work", cascade="all, delete-orphan"
    )


class WorkRecording(Base):
    """Linked recording of a work: {ISRC (optional), title, main artist}."""

    __tablename__ = "work_recordings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watchlist_id: Mapped[str] = mapped_column(
        ForeignKey("works.watchlist_id"), index=True
    )
    isrc: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    recording_title: Mapped[str] = mapped_column(String(500))
    main_artist: Mapped[str] = mapped_column(String(500))

    work: Mapped[Work] = relationship(back_populates="recordings")


class AvProduction(Base):
    """Film / series / documentary / commercial (req. 3.2)."""

    __tablename__ = "av_productions"

    watchlist_id: Mapped[str] = mapped_column(
        ForeignKey("watchlist_entries.id"), primary_key=True
    )
    original_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    production_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    production_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    imdb_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    tmdb_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    eidr: Mapped[str | None] = mapped_column(String(40), nullable=True)
    country_of_origin: Mapped[str | None] = mapped_column(String(2), nullable=True)
    # Cue sheet reference: list of contained watchlist work IDs (optional).
    contained_work_ids: Mapped[list] = mapped_column(JSON, default=list)

    entry: Mapped[WatchlistEntry] = relationship(back_populates="av_production")


class Performer(Base):
    """Artist who performs member repertoire (req. 3.3)."""

    __tablename__ = "performers"

    watchlist_id: Mapped[str] = mapped_column(
        ForeignKey("watchlist_entries.id"), primary_key=True
    )
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    musicbrainz_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    setlistfm_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    # Watchlist work IDs the artist is known to perform. If empty, any
    # concert is a low-confidence finding flagged for review (req. 3.3).
    known_work_ids: Mapped[list] = mapped_column(JSON, default=list)

    entry: Mapped[WatchlistEntry] = relationship(back_populates="performer")


# --------------------------------------------------------------------------
# Findings (req. 6)
# --------------------------------------------------------------------------

class Finding(Base):
    """One observed usage signal."""

    __tablename__ = "findings"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_findings_dedupe"),)

    finding_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    watchlist_id: Mapped[str] = mapped_column(
        ForeignKey("watchlist_entries.id"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(20))
    usage_type: Mapped[str] = mapped_column(String(30), index=True)
    # ISO country code or "global".
    market: Mapped[str] = mapped_column(String(10), index=True)
    # When the usage happened: a date, plus a period label (date or ISO week).
    occurred_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    period: Mapped[str] = mapped_column(String(20), index=True)
    # Source: module name + source URL (+ the source's own item ID).
    source_module: Mapped[str] = mapped_column(String(50), index=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    source_item_id: Mapped[str] = mapped_column(String(200))
    # Path to archived raw evidence (immutable, req. 6).
    evidence_snapshot: Mapped[str] = mapped_column(String(1000))
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Auditability of the match (req. 5).
    match_level: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)
    matched_strings: Mapped[dict] = mapped_column(JSON, default=dict)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    # Source-specific payload: chart position, venue, channel, view delta...
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    export_batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("export_batches.id"), nullable=True
    )
    # source_module|source_item_id|watchlist_id|period (req. 4 idempotency).
    dedupe_key: Mapped[str] = mapped_column(String(500))


class Rejection(Base):
    """Rejection memory (req. 5): a reviewer marked a (source item <->
    watchlist item) pair as a false positive; suppress it in future runs."""

    __tablename__ = "rejections"
    __table_args__ = (
        UniqueConstraint(
            "source_module", "source_item_id", "watchlist_id", name="uq_rejections_pair"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_module: Mapped[str] = mapped_column(String(50))
    source_item_id: Mapped[str] = mapped_column(String(200))
    watchlist_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CollectorRun(Base):
    """Per-collector run log (req. 4, 7)."""

    __tablename__ = "collector_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    module: Mapped[str] = mapped_column(String(50), index=True)
    market: Mapped[str | None] = mapped_column(String(10), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    items_checked: Mapped[int] = mapped_column(Integer, default=0)
    findings_new: Mapped[int] = mapped_column(Integer, default=0)
    findings_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    findings_suppressed: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)


class ExportBatch(Base):
    """Export batch so the claims team can work in periods (req. 8 phase 1)."""

    __tablename__ = "export_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    path: Mapped[str] = mapped_column(String(1000))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
