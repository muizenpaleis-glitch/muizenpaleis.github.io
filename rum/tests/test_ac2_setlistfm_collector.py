"""Acceptance criterion 2 (setlist part - the only Tier 1 collector in
this iteration): a run produces a setlist match with an evidence
snapshot and the correct market code."""

import json
import os
import stat

from rum.models import Finding
from rum.runner import run_collectors

from conftest import SINCE


def _run(seeded_session, config, http_client_factory):
    return run_collectors(
        seeded_session, config, modules=["setlistfm"], since=SINCE,
        http_client_factory=http_client_factory,
    )


def test_setlist_song_match_with_evidence_and_market(
    seeded_session, config, http_client_factory
):
    report = _run(seeded_session, config, http_client_factory)
    assert all(r.ok for r in report.runs), report.summary()

    finding = (
        seeded_session.query(Finding)
        .filter_by(watchlist_id="W-001", usage_type="live_performance")
        .one()
    )
    # Correct market code from the venue country (Berlin -> DE).
    assert finding.market == "DE"
    assert finding.occurred_at.isoformat() == "2026-05-30"
    assert finding.source_module == "setlistfm"
    assert "setlist.fm" in finding.source_url
    assert finding.details["venue"] == "Columbiahalle"
    assert finding.details["song"] == "Voorbeeldlied"
    # High-confidence live-performance finding (req. 4 source #3).
    assert finding.confidence >= 0.8
    assert not finding.needs_review

    # Evidence snapshot: raw API JSON, archived and immutable (req. 6).
    assert os.path.exists(finding.evidence_snapshot)
    snapshot = json.loads(open(finding.evidence_snapshot, encoding="utf-8").read())
    assert snapshot["id"] == "63de4613"
    assert snapshot["venue"]["name"] == "Columbiahalle"
    mode = os.stat(finding.evidence_snapshot).st_mode
    assert not (mode & stat.S_IWUSR), "evidence snapshot must be read-only"


def test_artist_without_known_works_yields_review_finding(
    seeded_session, config, http_client_factory
):
    """Req. 3.3: performer with empty known-works subset -> any concert is
    a low-confidence finding flagged for review."""
    _run(seeded_session, config, http_client_factory)
    finding = (
        seeded_session.query(Finding).filter_by(watchlist_id="A-002").one()
    )
    assert finding.entity_type == "performer"
    assert finding.market == "ES"
    assert finding.match_level == 3
    assert finding.confidence < 0.8
    assert finding.needs_review
    assert finding.details["city"] == "Madrid"


def test_market_filter_restricts_findings(seeded_session, config, http_client_factory):
    run_collectors(
        seeded_session, config, modules=["setlistfm"], markets=["DE"],
        since=SINCE, http_client_factory=http_client_factory,
    )
    markets = {f.market for f in seeded_session.query(Finding).all()}
    assert markets == {"DE"}


def test_run_report_logs_items_and_findings(seeded_session, config, http_client_factory):
    report = _run(seeded_session, config, http_client_factory)
    run = report.runs[0]
    assert run.module == "setlistfm"
    assert run.items_checked == 2  # both performers checked
    assert run.findings_new == 2
    assert run.errors == []
    assert run.finished_at is not None
