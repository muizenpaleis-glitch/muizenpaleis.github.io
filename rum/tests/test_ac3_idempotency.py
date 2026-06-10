"""Acceptance criterion 3: re-running the same week produces zero
duplicate findings (dedupe key: source + source-item ID + watchlist ID
+ period, req. 4)."""

from rum.models import Finding
from rum.runner import run_collectors

from conftest import SINCE


def test_rerun_same_week_creates_no_duplicates(
    seeded_session, config, http_client_factory
):
    first = run_collectors(
        seeded_session, config, modules=["setlistfm"], since=SINCE,
        http_client_factory=http_client_factory,
    )
    count_after_first = seeded_session.query(Finding).count()
    assert first.runs[0].findings_new == count_after_first > 0

    second = run_collectors(
        seeded_session, config, modules=["setlistfm"], since=SINCE,
        http_client_factory=http_client_factory,
    )
    assert second.runs[0].findings_new == 0
    assert second.runs[0].findings_duplicate == count_after_first
    assert seeded_session.query(Finding).count() == count_after_first
