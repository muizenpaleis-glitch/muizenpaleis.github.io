"""Acceptance criterion 5: CSV export filtered by market + period
round-trips into Excel cleanly (UTF-8, semicolon-safe), and exported
findings get an export batch ID."""

import csv
import json

from rum.export import EXPORT_COLUMNS, export_findings
from rum.models import Finding
from rum.runner import run_collectors

from conftest import SINCE


def _collect(seeded_session, config, http_client_factory):
    run_collectors(
        seeded_session, config, modules=["setlistfm"], since=SINCE,
        http_client_factory=http_client_factory,
    )


def test_export_filtered_by_market_and_period(
    seeded_session, config, http_client_factory, tmp_path
):
    _collect(seeded_session, config, http_client_factory)
    out = tmp_path / "export.csv"
    batch = export_findings(
        seeded_session, out, market="DE",
        period_from="2026-05-01", period_to="2026-05-31",
    )
    seeded_session.commit()

    # UTF-8 with BOM so Excel detects the encoding.
    assert out.read_bytes().startswith(b"\xef\xbb\xbf")

    with out.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))
    assert [*rows[0]] == EXPORT_COLUMNS
    assert len(rows) == batch.row_count == 1
    row = rows[0]
    assert row["market"] == "DE"
    assert row["period"] == "2026-05-30"
    assert row["usage_type"] == "live_performance"
    # The ES finding (Madrid) is filtered out.
    assert all(r["market"] == "DE" for r in rows)

    # Exported findings carry the batch ID and status (req. 8 phase 1).
    assert row["status"] == "exported"
    assert row["export_batch_id"] == batch.id
    db_finding = seeded_session.get(Finding, row["finding_id"])
    assert db_finding.status == "exported"
    assert db_finding.export_batch_id == batch.id


def test_semicolons_inside_values_are_quoted_safely(
    seeded_session, config, http_client_factory, tmp_path
):
    _collect(seeded_session, config, http_client_factory)
    out = tmp_path / "export_es.csv"
    export_findings(seeded_session, out, market="ES")

    with out.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))
    assert len(rows) == 1
    # The venue name contains a literal ";" and must round-trip intact.
    details = json.loads(rows[0]["details"])
    assert details["venue"] == "Sala Caracol; Madrid"
    # Column count survived, i.e. the semicolon did not split the row.
    assert rows[0]["market"] == "ES"


def test_min_confidence_filter(seeded_session, config, http_client_factory, tmp_path):
    _collect(seeded_session, config, http_client_factory)
    out = tmp_path / "export_conf.csv"
    batch = export_findings(seeded_session, out, min_confidence=0.8)
    with out.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))
    assert batch.row_count == len(rows) == 1
    assert float(rows[0]["confidence"]) >= 0.8
