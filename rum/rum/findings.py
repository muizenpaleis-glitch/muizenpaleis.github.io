"""Findings pipeline: dedupe, rejection memory, persistence (req. 4, 5, 6).

Collectors produce FindingDrafts; this module turns them into stored
findings. Idempotency: the dedupe key is
source + source-item ID + watchlist ID + period (req. 4), enforced by a
unique constraint, so re-running a week never duplicates findings.
Rejection memory: pairs marked false positive are suppressed (req. 5).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from sqlalchemy.orm import Session

from .evidence import EvidenceStore
from .models import Finding, Rejection

logger = logging.getLogger("rum.findings")


@dataclass
class FindingDraft:
    """A finding as produced by a collector, before dedupe/persistence."""

    watchlist_id: str
    entity_type: str
    usage_type: str
    market: str
    period: str
    source_module: str
    source_url: str
    source_item_id: str
    match_level: int
    confidence: float
    matched_strings: dict
    evidence_content: bytes
    evidence_ext: str = "json"
    occurred_at: date | None = None
    needs_review: bool = False
    details: dict = field(default_factory=dict)

    @property
    def dedupe_key(self) -> str:
        return "|".join(
            [self.source_module, self.source_item_id, self.watchlist_id, self.period]
        )


class RecordOutcome(Enum):
    CREATED = "created"
    DUPLICATE = "duplicate"
    SUPPRESSED = "suppressed"


def is_rejected(session: Session, source_module: str, source_item_id: str,
                watchlist_id: str) -> bool:
    return (
        session.query(Rejection)
        .filter_by(
            source_module=source_module,
            source_item_id=source_item_id,
            watchlist_id=watchlist_id,
        )
        .first()
        is not None
    )


def record_finding(
    session: Session, draft: FindingDraft, evidence_store: EvidenceStore
) -> tuple[RecordOutcome, Finding | None]:
    """Persist a draft unless it is a duplicate or a rejected pair."""
    if is_rejected(session, draft.source_module, draft.source_item_id, draft.watchlist_id):
        logger.info(
            "suppressed by rejection memory: %s/%s -> %s",
            draft.source_module, draft.source_item_id, draft.watchlist_id,
        )
        return RecordOutcome.SUPPRESSED, None

    existing = session.query(Finding).filter_by(dedupe_key=draft.dedupe_key).first()
    if existing is not None:
        return RecordOutcome.DUPLICATE, existing

    evidence_path = evidence_store.save(
        draft.source_module, draft.source_item_id,
        draft.evidence_content, draft.evidence_ext,
    )
    finding = Finding(
        watchlist_id=draft.watchlist_id,
        entity_type=draft.entity_type,
        usage_type=draft.usage_type,
        market=draft.market,
        occurred_at=draft.occurred_at,
        period=draft.period,
        source_module=draft.source_module,
        source_url=draft.source_url,
        source_item_id=draft.source_item_id,
        evidence_snapshot=evidence_path,
        match_level=draft.match_level,
        confidence=draft.confidence,
        matched_strings=draft.matched_strings,
        needs_review=draft.needs_review,
        details=draft.details,
        dedupe_key=draft.dedupe_key,
    )
    session.add(finding)
    session.flush()
    return RecordOutcome.CREATED, finding


def mark_false_positive(session: Session, finding_id: str) -> Finding:
    """Review action: mark a finding false positive and remember the
    (source item <-> watchlist item) pair so future runs suppress it."""
    finding = session.get(Finding, finding_id)
    if finding is None:
        raise KeyError(f"no finding with id {finding_id}")
    finding.status = "false_positive"
    if not is_rejected(session, finding.source_module, finding.source_item_id,
                       finding.watchlist_id):
        session.add(
            Rejection(
                source_module=finding.source_module,
                source_item_id=finding.source_item_id,
                watchlist_id=finding.watchlist_id,
            )
        )
    session.flush()
    return finding
