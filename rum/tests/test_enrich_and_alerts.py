"""MusicBrainz enrichment (req. 4 #5) and Phase 3 alerting (req. 8)."""

import httpx
import pytest

from rum import alerts, enrich
from rum.models import Finding, WatchlistEntry
from rum.runner import run_collectors

from conftest import MBID_VOORBEELDEN, SINCE


@pytest.fixture
def musicbrainz_client_factory():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "contact" in request.headers.get("user-agent", "")  # MB etiquette
        path = request.url.path
        if path == f"/ws/2/artist/{MBID_VOORBEELDEN}":
            return httpx.Response(200, json={
                "id": MBID_VOORBEELDEN, "name": "De Voorbeelden",
                "aliases": [{"name": "The Examples"}, {"name": "De Voorbeelden"}],
            })
        if path == "/ws/2/isrc/NLA011234567":
            return httpx.Response(200, json={
                "recordings": [{"title": "Voorbeeldlied (Remastered)"}],
            })
        return httpx.Response(404)

    def factory(headers=None):
        return httpx.Client(transport=httpx.MockTransport(handler), headers=headers)

    return factory


def test_enrichment_adds_aliases_and_titles(seeded_session, config, musicbrainz_client_factory):
    messages = enrich.enrich_all(seeded_session, config, musicbrainz_client_factory)
    seeded_session.commit()

    performer = seeded_session.get(WatchlistEntry, "A-001").performer
    # "De Voorbeelden" was already known and must not be duplicated.
    assert performer.aliases == ["The Examples"]
    work = seeded_session.get(WatchlistEntry, "W-001").work
    assert "Voorbeeldlied (Remastered)" in work.alternative_titles
    assert len(messages) == 2

    # Idempotent: a second pass adds nothing.
    assert enrich.enrich_all(seeded_session, config, musicbrainz_client_factory) == []


def test_enriched_alias_strengthens_matching(seeded_session, config, musicbrainz_client_factory):
    """The point of enrichment (req. 4 #5): a source using the alias now
    matches at Level 2 instead of missing."""
    from rum.matching import MatchingEngine, build_work_candidates

    engine = MatchingEngine(config)
    enrich.enrich_all(seeded_session, config, musicbrainz_client_factory)
    seeded_session.commit()
    candidates = build_work_candidates(seeded_session)
    match = engine.match_song("Voorbeeldlied (Remastered)", "De Voorbeelden", candidates)
    assert match is not None and match.level == 2


def test_alert_for_high_priority_high_confidence(
    seeded_session, config, http_client_factory
):
    """W-001 is priority=high; its setlist match (confidence 0.95) must
    trigger an alert, the low-confidence A-002 finding must not."""
    posted = []
    config.slack_webhook_url = "https://hooks.slack.example/T000/B000"

    report = run_collectors(
        seeded_session, config, modules=["setlistfm"], since=SINCE,
        http_client_factory=http_client_factory,
    )
    assert len(report.alerts) == 1
    assert "W-001" in report.alerts[0] and "live_performance" in report.alerts[0]

    # Delivery: same messages go to the configured Slack webhook.
    messages = alerts.notify_new_findings(
        seeded_session, config,
        seeded_session.query(Finding).all(),
        http_post=lambda url, json, timeout: posted.append((url, json)),
    )
    assert len(messages) == 1
    assert posted and posted[0][0] == config.slack_webhook_url
    assert "W-001" in posted[0][1]["text"]


def test_no_alert_for_normal_priority(seeded_session, config, http_client_factory):
    entry = seeded_session.get(WatchlistEntry, "W-001")
    entry.priority = "normal"
    seeded_session.commit()
    report = run_collectors(
        seeded_session, config, modules=["setlistfm"], since=SINCE,
        http_client_factory=http_client_factory,
    )
    assert report.alerts == []
