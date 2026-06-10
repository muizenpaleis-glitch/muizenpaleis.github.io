"""CSV export for the claims team (req. 8 phase 1).

Filters: market, period, usage type, minimum confidence, watchlist
entry. Exported findings are marked `exported` and stamped with an
export batch ID so the team can work in periods.

Excel round-trip (acceptance criterion 5): UTF-8 with BOM so Excel
detects the encoding, semicolon delimiter (Dutch/most EU locales), and
proper quoting so semicolons inside values stay safe.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from sqlalchemy.orm import Session

from .models import ExportBatch, Finding

EXPORT_COLUMNS = [
    "finding_id", "watchlist_id", "entity_type", "usage_type", "market",
    "occurred_at", "period", "source_module", "source_url", "source_item_id",
    "evidence_snapshot", "captured_at", "match_level", "confidence",
    "matched_strings", "needs_review", "details", "status", "export_batch_id",
]


def export_findings(
    session: Session,
    out_path: str | Path,
    market: str | None = None,
    period_from: str | None = None,
    period_to: str | None = None,
    usage_type: str | None = None,
    min_confidence: float | None = None,
    watchlist_id: str | None = None,
    include_false_positives: bool = False,
    mark_exported: bool = True,
) -> ExportBatch:
    filters = {
        "market": market, "period_from": period_from, "period_to": period_to,
        "usage_type": usage_type, "min_confidence": min_confidence,
        "watchlist_id": watchlist_id,
    }
    query = session.query(Finding)
    if market:
        query = query.filter(Finding.market == market.upper())
    if period_from:
        query = query.filter(Finding.period >= period_from)
    if period_to:
        query = query.filter(Finding.period <= period_to)
    if usage_type:
        query = query.filter(Finding.usage_type == usage_type)
    if min_confidence is not None:
        query = query.filter(Finding.confidence >= min_confidence)
    if watchlist_id:
        query = query.filter(Finding.watchlist_id == watchlist_id)
    if not include_false_positives:
        query = query.filter(Finding.status != "false_positive")
    findings = query.order_by(Finding.period, Finding.market, Finding.watchlist_id).all()

    out_path = Path(out_path)
    batch = ExportBatch(filters={k: v for k, v in filters.items() if v is not None},
                        path=str(out_path), row_count=len(findings))
    session.add(batch)
    session.flush()

    with out_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(EXPORT_COLUMNS)
        for f in findings:
            if mark_exported and f.status in ("new", "reviewed"):
                f.status = "exported"
                f.export_batch_id = batch.id
            writer.writerow([
                f.finding_id, f.watchlist_id, f.entity_type, f.usage_type,
                f.market,
                f.occurred_at.isoformat() if f.occurred_at else "",
                f.period, f.source_module, f.source_url, f.source_item_id,
                f.evidence_snapshot,
                f.captured_at.isoformat() if f.captured_at else "",
                f.match_level, f.confidence,
                json.dumps(f.matched_strings, ensure_ascii=False),
                "yes" if f.needs_review else "no",
                json.dumps(f.details, ensure_ascii=False),
                f.status, f.export_batch_id or "",
            ])
    session.flush()
    return batch
