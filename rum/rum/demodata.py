"""Demo data for testing the web UI without a setlist.fm API key.

Seeds a small sample watchlist and provides an httpx client factory
backed by canned setlist.fm API responses, so the full pipeline
(collect -> match -> dedupe -> evidence -> export) can be exercised
offline. Demo entries are prefixed DEMO- and never touch the network.
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx

from .models import AvProduction, Performer, WatchlistEntry, Work, WorkRecording

DEMO_MBID = "b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d"


def seed_demo_watchlist(session) -> list[str]:
    """Insert demo watchlist entries; returns the IDs created (idempotent)."""
    created: list[str] = []

    if session.get(WatchlistEntry, "DEMO-W-001") is None:
        work = WatchlistEntry(
            id="DEMO-W-001", entity_type="work",
            display_name="Voorbeeldlied", priority="high",
            notes="demo entry",
        )
        work.work = Work(
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
        session.add(work)
        created.append(work.id)

    if session.get(WatchlistEntry, "DEMO-A-001") is None:
        performer = WatchlistEntry(
            id="DEMO-A-001", entity_type="performer",
            display_name="De Voorbeelden", notes="demo entry",
        )
        performer.performer = Performer(
            musicbrainz_id=DEMO_MBID, known_work_ids=["DEMO-W-001"]
        )
        session.add(performer)
        created.append(performer.id)

    if session.get(WatchlistEntry, "DEMO-A-002") is None:
        performer = WatchlistEntry(
            id="DEMO-A-002", entity_type="performer",
            display_name="Other Band", notes="demo entry, no known works",
        )
        performer.performer = Performer(known_work_ids=[])
        session.add(performer)
        created.append(performer.id)

    if session.get(WatchlistEntry, "DEMO-P-001") is None:
        production = WatchlistEntry(
            id="DEMO-P-001", entity_type="av_production",
            display_name="Voorbeeldfilm", priority="normal", notes="demo entry",
        )
        production.av_production = AvProduction(
            original_title="Voorbeeldfilm", production_year=2023,
            production_type="film", tmdb_id="550",
            contained_work_ids=["DEMO-W-001"],
        )
        session.add(production)
        created.append(production.id)

    session.commit()
    return created


def _setlist(setlist_id, days_ago, artist, mbid, venue, city, country_code,
              country, songs, slug):
    event = date.today() - timedelta(days=days_ago)
    return {
        "id": setlist_id,
        "eventDate": event.strftime("%d-%m-%Y"),
        "artist": {"mbid": mbid, "name": artist},
        "venue": {
            "id": f"v-{setlist_id}",
            "name": venue,
            "city": {"name": city, "country": {"code": country_code, "name": country}},
        },
        "sets": {"set": [{"song": [{"name": s} for s in songs]}]},
        "url": f"https://www.setlist.fm/setlist/{slug}/{event:%Y}/{setlist_id}.html",
    }


def _demo_setlists_voorbeelden():
    return [
        _setlist("demo63de4613", 4, "De Voorbeelden", DEMO_MBID,
                 "Columbiahalle", "Berlin", "DE", "Germany",
                 ["Voorbeeldlied", "Some Unrelated Cover"], "de-voorbeelden"),
        _setlist("demo81fa2207", 11, "De Voorbeelden", DEMO_MBID,
                 "Zepp DiverCity", "Tokyo", "JP", "Japan",
                 ["Voorbeeldlied (Live)", "Another Tune"], "de-voorbeelden"),
    ]


def _demo_setlists_other_band():
    return [
        _setlist("demo73ab9921", 7, "Other Band", None,
                 "Sala Caracol", "Madrid", "ES", "Spain",
                 ["Totally Different Track"], "other-band"),
    ]


def _page(setlists):
    return {
        "type": "setlists", "itemsPerPage": 20, "page": 1,
        "total": len(setlists), "setlist": setlists,
    }


DEMO_CHART_CSV = """\
Note: demo chart data bundled with RUM, not real Spotify figures
Position,Track Name,Artist,Streams,URL
17,Voorbeeldlied,De Voorbeelden,1834210,https://open.spotify.com/track/demoTrack01
18,Some Other Hit,Some Other Act,1790031,https://open.spotify.com/track/demoTrack02
"""

DEMO_VIDEO = {
    "id": "demoVid0001",
    "snippet": {
        "title": "De Voorbeelden - Voorbeeldlied (Official Video)",
        "channelTitle": "De Voorbeelden",
    },
    "statistics": {"viewCount": "123456"},
}

DEMO_TMDB_PROVIDERS = {
    "id": 550,
    "results": {
        "DE": {
            "link": "https://www.themoviedb.org/movie/550/watch?locale=DE",
            "flatrate": [{"provider_name": "Netflix"}],
        },
        "JP": {
            "link": "https://www.themoviedb.org/movie/550/watch?locale=JP",
            "rent": [{"provider_name": "Amazon Video"}],
        },
    },
}

DEMO_MB_ARTIST = {
    "id": DEMO_MBID,
    "name": "De Voorbeelden",
    "aliases": [{"name": "The Examples"}, {"name": "D. Voorbeelden"}],
}


def demo_http_client_factory(headers=None) -> httpx.Client:
    """httpx client serving canned responses for every source module
    (setlist.fm, charts, YouTube, TMDb, MusicBrainz) - no network."""

    def handler(request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        # setlist.fm
        if path == f"/rest/1.0/artist/{DEMO_MBID}/setlists":
            return httpx.Response(200, json=_page(_demo_setlists_voorbeelden()))
        if path == "/rest/1.0/search/setlists":
            if request.url.params.get("artistName") == "Other Band":
                return httpx.Response(200, json=_page(_demo_setlists_other_band()))
            return httpx.Response(404, json={"code": 404})
        # streaming charts (CSV format)
        if host == "spotifycharts.com":
            return httpx.Response(200, content=DEMO_CHART_CSV.encode("utf-8"))
        # YouTube Data API
        if path == "/youtube/v3/search":
            return httpx.Response(
                200, json={"items": [{"id": {"videoId": DEMO_VIDEO["id"]},
                                      "snippet": DEMO_VIDEO["snippet"]}]},
            )
        if path == "/youtube/v3/videos":
            return httpx.Response(200, json={"items": [DEMO_VIDEO]})
        # TMDb
        if path == "/3/movie/550/watch/providers":
            return httpx.Response(200, json=DEMO_TMDB_PROVIDERS)
        # MusicBrainz (enrichment)
        if path == f"/ws/2/artist/{DEMO_MBID}":
            return httpx.Response(200, json=DEMO_MB_ARTIST)
        if path.startswith("/ws/2/isrc/"):
            return httpx.Response(
                200, json={"recordings": [{"title": "Voorbeeldlied (Remastered)"}]}
            )
        return httpx.Response(404, json={"code": 404})

    return httpx.Client(transport=httpx.MockTransport(handler), headers=headers)
