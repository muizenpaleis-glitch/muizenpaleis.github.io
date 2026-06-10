"""Shared fixtures: in-memory-style SQLite DB, seeded watchlist, and a
mocked setlist.fm API so no test touches the network."""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from rum.config import Config
from rum.db import init_db, make_engine, make_session_factory
from rum.models import AvProduction, Performer, WatchlistEntry, Work, WorkRecording

MBID_VOORBEELDEN = "b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d"
SINCE = date(2026, 5, 1)

SETLIST_DE = {
    "id": "63de4613",
    "eventDate": "30-05-2026",
    "artist": {"mbid": MBID_VOORBEELDEN, "name": "De Voorbeelden"},
    "venue": {
        "id": "v-col",
        "name": "Columbiahalle",
        "city": {"name": "Berlin", "country": {"code": "DE", "name": "Germany"}},
    },
    "sets": {
        "set": [
            {
                "song": [
                    {"name": "Voorbeeldlied"},
                    {"name": "Some Unrelated Cover Song"},
                ]
            }
        ]
    },
    "url": "https://www.setlist.fm/setlist/de-voorbeelden/2026/columbiahalle-berlin-63de4613.html",
}

SETLIST_ES = {
    "id": "73ab9921",
    "eventDate": "22-05-2026",
    "artist": {"mbid": None, "name": "Other Band"},
    "venue": {
        "id": "v-mad",
        "name": "Sala Caracol; Madrid",  # semicolon on purpose for export test
        "city": {"name": "Madrid", "country": {"code": "ES", "name": "Spain"}},
    },
    "sets": {"set": [{"song": [{"name": "Totally Different Track"}]}]},
    "url": "https://www.setlist.fm/setlist/other-band/2026/sala-caracol-madrid-73ab9921.html",
}


def _page(setlists: list[dict]) -> dict:
    return {
        "type": "setlists",
        "itemsPerPage": 20,
        "page": 1,
        "total": len(setlists),
        "setlist": setlists,
    }


@pytest.fixture
def config(tmp_path) -> Config:
    return Config(
        database_url=f"sqlite:///{tmp_path / 'rum.db'}",
        evidence_dir=str(tmp_path / "evidence"),
        rate_limit_seconds=0.0,  # keep tests fast; AC6 tests use a real interval
        setlistfm_api_key="test-key",
        youtube_api_key="test-key",
        tmdb_api_key="test-key",
        contact_email="claims@cmo-test.nl",
    )


@pytest.fixture
def session(config):
    engine = make_engine(config.database_url)
    init_db(engine)
    session = make_session_factory(engine)()
    yield session
    session.close()


@pytest.fixture
def seeded_session(session):
    """Watchlist: one work with full identifiers, one performer with a
    known-works subset + MBID, one performer with neither (req. 3.3)."""
    work_entry = WatchlistEntry(
        id="W-001", entity_type="work", display_name="Voorbeeldlied", priority="high"
    )
    work_entry.work = Work(
        iswc="T-123456789-0",
        alternative_titles=["Example Song"],
        writers=[{"name": "J. de Vries", "ipi": "00012345678"}],
        recordings=[
            WorkRecording(
                isrc="NLA011234567",
                recording_title="Voorbeeldlied",
                main_artist="De Voorbeelden",
            )
        ],
    )
    performer_known = WatchlistEntry(
        id="A-001", entity_type="performer", display_name="De Voorbeelden"
    )
    performer_known.performer = Performer(
        musicbrainz_id=MBID_VOORBEELDEN, known_work_ids=["W-001"]
    )
    performer_unknown = WatchlistEntry(
        id="A-002", entity_type="performer", display_name="Other Band"
    )
    performer_unknown.performer = Performer(known_work_ids=[])
    production = WatchlistEntry(
        id="P-001", entity_type="av_production", display_name="Voorbeeldfilm"
    )
    production.av_production = AvProduction(
        original_title="Voorbeeldfilm", production_year=2023,
        production_type="film", tmdb_id="550",
    )
    session.add_all([work_entry, performer_known, performer_unknown, production])
    session.commit()
    return session


@pytest.fixture
def setlistfm_transport():
    """Mocked setlist.fm API: MBID route for A-001, search route for A-002."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-api-key") == "test-key"
        assert "contact" in request.headers.get("user-agent", "")
        path = request.url.path
        if path == f"/rest/1.0/artist/{MBID_VOORBEELDEN}/setlists":
            return httpx.Response(200, json=_page([SETLIST_DE]))
        if path == "/rest/1.0/search/setlists":
            if request.url.params.get("artistName") == "Other Band":
                return httpx.Response(200, json=_page([SETLIST_ES]))
            return httpx.Response(404, json={"code": 404})
        return httpx.Response(404, json={"code": 404})

    return httpx.MockTransport(handler)


@pytest.fixture
def http_client_factory(setlistfm_transport):
    def factory(headers=None):
        return httpx.Client(transport=setlistfm_transport, headers=headers)

    return factory
