"""TMDb collector (req. 4 Tier 1 #4): VOD availability per country for
watchlist AV productions, by known TMDb ID (Level 1) or title search."""

import httpx
import pytest

from rum.models import AvProduction, Finding, WatchlistEntry
from rum.runner import run_collectors

from conftest import SINCE

PROVIDERS_550 = {
    "id": 550,
    "results": {
        "DE": {"link": "https://www.themoviedb.org/movie/550/watch?locale=DE",
               "flatrate": [{"provider_name": "Netflix"}]},
        "JP": {"link": "https://www.themoviedb.org/movie/550/watch?locale=JP",
               "rent": [{"provider_name": "Amazon Video"}]},
        "US": {"link": "https://www.themoviedb.org/movie/550/watch?locale=US"},
    },
}

PROVIDERS_777 = {
    "id": 777,
    "results": {
        "FR": {"link": "https://www.themoviedb.org/movie/777/watch?locale=FR",
               "flatrate": [{"provider_name": "Canal+"}]},
    },
}


@pytest.fixture
def tmdb_client_factory():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("api_key") == "test-key"
        path = request.url.path
        if path == "/3/movie/550/watch/providers":
            return httpx.Response(200, json=PROVIDERS_550)
        if path == "/3/movie/777/watch/providers":
            return httpx.Response(200, json=PROVIDERS_777)
        if path == "/3/search/movie":
            if "Tweede Film" in request.url.params.get("query", ""):
                return httpx.Response(200, json={"results": [
                    {"id": 777, "title": "Tweede Film", "release_date": "2024-05-01"},
                ]})
            return httpx.Response(200, json={"results": []})
        return httpx.Response(404)

    def factory(headers=None):
        return httpx.Client(transport=httpx.MockTransport(handler), headers=headers)

    return factory


def test_vod_availability_by_known_tmdb_id(seeded_session, config, tmdb_client_factory):
    report = run_collectors(
        seeded_session, config, modules=["tmdb"],
        since=SINCE, http_client_factory=tmdb_client_factory,
    )
    assert report.runs[0].errors == []
    findings = seeded_session.query(Finding).order_by(Finding.market).all()
    # US has an entry but no offers -> no finding; DE and JP qualify.
    assert [f.market for f in findings] == ["DE", "JP"]
    de = findings[0]
    assert de.usage_type == "vod_availability"
    assert de.watchlist_id == "P-001"
    assert de.match_level == 1 and de.confidence == 1.0  # known TMDb ID
    assert de.details["providers"] == {"flatrate": ["Netflix"]}
    assert "themoviedb.org" in de.source_url


def test_market_filter(seeded_session, config, tmdb_client_factory):
    run_collectors(
        seeded_session, config, modules=["tmdb"], markets=["DE"],
        since=SINCE, http_client_factory=tmdb_client_factory,
    )
    assert {f.market for f in seeded_session.query(Finding).all()} == {"DE"}


def test_resolution_via_title_search(seeded_session, config, tmdb_client_factory):
    entry = WatchlistEntry(
        id="P-002", entity_type="av_production", display_name="Tweede Film"
    )
    entry.av_production = AvProduction(production_year=2024, production_type="film")
    seeded_session.add(entry)
    seeded_session.commit()

    run_collectors(
        seeded_session, config, modules=["tmdb"],
        since=SINCE, http_client_factory=tmdb_client_factory,
    )
    finding = seeded_session.query(Finding).filter_by(watchlist_id="P-002").one()
    assert finding.market == "FR"
    assert finding.match_level == 2  # title + year search match
    assert finding.matched_strings["watchlist_title"] == "Tweede Film"
    assert finding.details["providers"] == {"flatrate": ["Canal+"]}


def test_rerun_same_week_is_idempotent(seeded_session, config, tmdb_client_factory):
    for _ in range(2):
        report = run_collectors(
            seeded_session, config, modules=["tmdb"],
            since=SINCE, http_client_factory=tmdb_client_factory,
        )
    assert report.runs[0].findings_new == 0
    assert seeded_session.query(Finding).count() == 2
