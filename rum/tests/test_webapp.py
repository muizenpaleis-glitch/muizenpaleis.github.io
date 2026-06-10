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

    # 2. Run the setlist.fm collector in demo mode (no network).
    response = client.post(
        "/run", data={"module": "setlistfm", "market": "", "since": "", "demo": "1"}
    )
    assert "new findings" in response.text
    assert "0 errors" in response.text

    # 3. Findings list with a market filter.
    response = client.get("/findings", params={"market": "DE"})
    assert "live_performance" in response.text and "DEMO-W-001" in response.text
    response = client.get("/findings", params={"market": "ES"})
    assert "DEMO-A-002" in response.text

    # 4. Finding detail shows matched strings + evidence snapshot.
    finding_id = _first_finding_id(client, market="DE")
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


def _first_finding_id(client, market):
    # The finding detail links carry the full UUID in the href.
    import re

    listing = client.get("/findings", params={"market": market}).text
    match = re.search(r'href="/findings/([0-9a-f-]{36})"', listing)
    assert match, "no finding link found"
    return match.group(1)
