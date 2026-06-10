"""YouTube collector (req. 4 Tier 1 #2): official-upload matching,
"global" market, and weekly view-count deltas from snapshots."""

from datetime import timedelta

import httpx
import pytest

from rum.models import Finding, VideoViewSnapshot, utcnow
from rum.runner import run_collectors

from conftest import SINCE

VIDEO_STATE = {"viewCount": "123456"}


@pytest.fixture
def youtube_client_factory():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/youtube/v3/search":
            assert request.url.params.get("key") == "test-key"
            return httpx.Response(200, json={"items": [
                {"id": {"videoId": "vid123"},
                 "snippet": {"title": "De Voorbeelden - Voorbeeldlied (Official Video)",
                             "channelTitle": "De Voorbeelden"}},
            ]})
        if request.url.path == "/youtube/v3/videos":
            return httpx.Response(200, json={"items": [
                {"id": "vid123",
                 "snippet": {"title": "De Voorbeelden - Voorbeeldlied (Official Video)",
                             "channelTitle": "De Voorbeelden"},
                 "statistics": {"viewCount": VIDEO_STATE["viewCount"]}},
            ]})
        return httpx.Response(404)

    def factory(headers=None):
        return httpx.Client(transport=httpx.MockTransport(handler), headers=headers)

    return factory


def test_first_run_creates_baseline_finding(seeded_session, config, youtube_client_factory):
    VIDEO_STATE["viewCount"] = "123456"
    report = run_collectors(
        seeded_session, config, modules=["youtube"],
        since=SINCE, http_client_factory=youtube_client_factory,
    )
    assert report.runs[0].errors == []
    finding = seeded_session.query(Finding).one()
    assert finding.usage_type == "video_views"
    assert finding.market == "global"  # region signal is weak (req. 4 #2)
    assert finding.watchlist_id == "W-001"
    assert finding.details["view_count"] == 123456
    assert finding.details["view_delta"] is None  # no previous snapshot yet
    assert finding.match_level == 2
    snapshot = seeded_session.query(VideoViewSnapshot).one()
    assert snapshot.video_id == "vid123" and snapshot.view_count == 123456


def test_weekly_delta_after_previous_snapshot(seeded_session, config, youtube_client_factory):
    VIDEO_STATE["viewCount"] = "123456"
    run_collectors(
        seeded_session, config, modules=["youtube"],
        since=SINCE, http_client_factory=youtube_client_factory,
    )
    # Simulate the next weekly run: age the snapshot, clear last week's
    # finding (a new week would have a new period), raise the view count.
    snapshot = seeded_session.query(VideoViewSnapshot).one()
    snapshot.captured_at = utcnow() - timedelta(days=7)
    seeded_session.query(Finding).delete()
    seeded_session.commit()
    VIDEO_STATE["viewCount"] = "150000"

    run_collectors(
        seeded_session, config, modules=["youtube"],
        since=SINCE, http_client_factory=youtube_client_factory,
    )
    finding = seeded_session.query(Finding).one()
    assert finding.details["previous_view_count"] == 123456
    assert finding.details["view_delta"] == 150000 - 123456


def test_rerun_same_week_is_idempotent(seeded_session, config, youtube_client_factory):
    VIDEO_STATE["viewCount"] = "123456"
    for _ in range(2):
        report = run_collectors(
            seeded_session, config, modules=["youtube"],
            since=SINCE, http_client_factory=youtube_client_factory,
        )
    assert report.runs[0].findings_new == 0
    assert seeded_session.query(Finding).count() == 1
    # Idempotent snapshots too: at most one per day per video.
    assert seeded_session.query(VideoViewSnapshot).count() == 1


def test_missing_api_key_is_reported(seeded_session, config, youtube_client_factory):
    config.youtube_api_key = None
    report = run_collectors(
        seeded_session, config, modules=["youtube"],
        since=SINCE, http_client_factory=youtube_client_factory,
    )
    assert any("YOUTUBE_API_KEY" in err for err in report.runs[0].errors)
    assert seeded_session.query(Finding).count() == 0
