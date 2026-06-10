"""Streaming charts collector (req. 4 Tier 1 #1): per-country chart
rows matched by normalized artist + title, weekly idempotency, and the
explicit-market requirement."""

import httpx
import pytest

from rum.models import Finding
from rum.runner import run_collectors

from conftest import SINCE

CHART_CSV = """\
Note: figures are generated using a formula (preamble line, must be skipped)
Position,Track Name,Artist,Streams,URL
1,Global Megahit,Superstar,9000000,https://open.spotify.com/track/zzz999
42,Voorbeeldlied,De Voorbeelden,1834210,https://open.spotify.com/track/abc123
"""


@pytest.fixture
def charts_client_factory():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "spotifycharts.com" and "/regional/de/" in request.url.path:
            return httpx.Response(200, content=CHART_CSV.encode("utf-8"))
        return httpx.Response(404)

    def factory(headers=None):
        return httpx.Client(transport=httpx.MockTransport(handler), headers=headers)

    return factory


def test_chart_entry_finding(seeded_session, config, charts_client_factory):
    report = run_collectors(
        seeded_session, config, modules=["charts"], markets=["DE"],
        since=SINCE, http_client_factory=charts_client_factory,
    )
    run = report.runs[0]
    assert run.errors == []
    assert run.items_checked == 2  # both chart rows checked
    finding = seeded_session.query(Finding).one()
    assert finding.usage_type == "streaming_chart"
    assert finding.market == "DE"
    assert finding.watchlist_id == "W-001"
    assert finding.details["position"] == 42
    assert finding.details["streams"] == 1834210
    assert finding.match_level == 2 and finding.confidence >= 0.8
    assert finding.evidence_snapshot.endswith(".csv")
    with open(finding.evidence_snapshot, encoding="utf-8") as fh:
        assert "Position,Track Name" in fh.read()


def test_chart_rerun_is_idempotent(seeded_session, config, charts_client_factory):
    for _ in range(2):
        report = run_collectors(
            seeded_session, config, modules=["charts"], markets=["DE"],
            since=SINCE, http_client_factory=charts_client_factory,
        )
    assert report.runs[0].findings_new == 0
    assert report.runs[0].findings_duplicate == 1
    assert seeded_session.query(Finding).count() == 1


def test_charts_require_explicit_market(seeded_session, config, charts_client_factory):
    report = run_collectors(
        seeded_session, config, modules=["charts"],
        since=SINCE, http_client_factory=charts_client_factory,
    )
    run = report.runs[0]
    assert not run.ok
    assert any("market" in err for err in run.errors)
    assert seeded_session.query(Finding).count() == 0


def test_charts_market_comes_from_module_config(seeded_session, config, charts_client_factory):
    config.module_markets = {"charts": ["DE"]}
    report = run_collectors(
        seeded_session, config, modules=["charts"],
        since=SINCE, http_client_factory=charts_client_factory,
    )
    assert report.runs[0].market == "DE"
    assert report.runs[0].findings_new == 1
