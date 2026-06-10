"""Web UI smoke tests: every function reachable through the browser is
exercised once - seed demo data, import CSV, CRUD, demo run, findings
list/detail, review actions, and CSV export download."""

import pytest
from fastapi.testclient import TestClient

from rum.webapp import create_app


@pytest.fixture
def client(config):
    app = create_app(config)
    return TestClient(app, follow_redirects=True)


def test_dashboard_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Dashboard" in response.text


def test_full_demo_flow(client):
    # 1. Seed the demo watchlist from the dashboard.
    response = client.post("/demo/seed")
    assert "created demo entries" in response.text
    response = client.get("/watchlist")
    assert "DEMO-W-001" in response.text and "DEMO-A-002" in response.text

    # 2. Run ALL collectors in demo mode (no network, no API keys).
    response = client.post(
        "/run", data={"module": "", "market": "", "since": "", "demo": "1"}
    )
    assert "error:" not in response.text
    # The run report must show every module actually executed.
    for line in ("setlistfm [all markets]", "charts [DE]",
                 "tmdb [all markets]", "youtube [all markets]"):
        assert line in response.text, f"missing run report line: {line}"
    # The high-priority demo work scores >= 0.9 -> phase 3 alert in report.
    assert "ALERT" in response.text and "DEMO-W-001" in response.text

    # 2b. Re-run in a fresh request session: idempotent, no errors
    # (regression: snapshots read back from the DB are tz-naive).
    response = client.post(
        "/run", data={"module": "", "market": "", "since": "", "demo": "1"}
    )
    assert "error:" not in response.text
    assert "0 new findings" in response.text

    # 3. Findings from every module (filter by usage type, check the
    # table rows - not the filter dropdown).
    for usage, expected_id in [
        ("live_performance", "DEMO-W-001"),
        ("streaming_chart", "DEMO-W-001"),
        ("video_views", "DEMO-W-001"),
        ("vod_availability", "DEMO-P-001"),
    ]:
        listing = client.get("/findings", params={"usage_type": usage}).text
        assert f'href="/watchlist/{expected_id}"' in listing, usage
    response = client.get("/findings", params={"market": "ES"})
    assert "DEMO-A-002" in response.text

    # 3b. Dashboard now renders the findings-per-market-per-week chart.
    response = client.get("/")
    assert "Findings per market per week" in response.text
    assert "<th>DE</th>" in response.text

    # 3c. MusicBrainz enrichment in demo mode.
    response = client.post("/enrich", data={"demo": "1"})
    assert "alias" in response.text

    # 4. Finding detail shows matched strings + evidence snapshot.
    finding_id = _first_finding_id(
        client, market="DE", usage_type="live_performance"
    )
    response = client.get(f"/findings/{finding_id}")
    assert "Matched strings" in response.text
    assert "Columbiahalle" in response.text  # from the evidence JSON

    # 5. Review actions.
    response = client.post(f"/findings/{finding_id}/reviewed")
    assert "marked reviewed" in response.text
    response = client.post(f"/findings/{finding_id}/false-positive")
    assert "suppressed in future runs" in response.text

    # 6. Run log shows the executed run.
    response = client.get("/runs")
    assert "setlistfm" in response.text

    # 7. CSV export downloads with BOM and semicolons, marks exported.
    response = client.get("/export.csv", params={"market": "ES"})
    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert b"finding_id;watchlist_id" in response.content
    response = client.get("/export")
    assert "Recent export batches" in response.text


def test_watchlist_import_and_crud(client):
    csv_content = (
        "work_id;title;alternative_titles;writers;iswc;recordings;priority;country_filter;notes\n"
        "W-UI-1;UI Test Song;;A. Writer~;;;normal;;\n"
        ";Broken Row;;;;;normal;;\n"
    )
    response = client.post(
        "/watchlist/import",
        data={"entity_type": "work"},
        files={"file": ("works.csv", csv_content.encode(), "text/csv")},
    )
    assert "1 imported" in response.text and "1 rejected" in response.text

    response = client.get("/watchlist/W-UI-1")
    assert "UI Test Song" in response.text

    response = client.post("/watchlist/W-UI-1/toggle")
    assert "now inactive" in response.text
    response = client.post("/watchlist/W-UI-1/delete")
    assert "deleted W-UI-1" in response.text


def _first_finding_id(client, **params):
    # The finding detail links carry the full UUID in the href.
    import re

    listing = client.get("/findings", params=params).text
    match = re.search(r'href="/findings/([0-9a-f-]{36})"', listing)
    assert match, "no finding link found"
    return match.group(1)
