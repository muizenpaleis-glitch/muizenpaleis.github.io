"""Acceptance criterion 4: a Level 2/3 finding shows its matched strings
and confidence; marking it false positive suppresses it in the next run.
Plus unit coverage of the matching engine levels (req. 5)."""

from rum.config import Config
from rum.findings import mark_false_positive
from rum.matching import MatchingEngine, WorkCandidate, build_work_candidates
from rum.models import Finding, Rejection
from rum.normalize import normalize, normalize_title
from rum.runner import run_collectors

from conftest import SINCE


def _candidates():
    return [
        WorkCandidate(
            watchlist_id="W-001",
            titles=["Voorbeeldlied", "Example Song"],
            artists=["De Voorbeelden", "J. de Vries"],
            isrcs={"NLA011234567"},
            iswc="T-123456789-0",
        )
    ]


def test_level1_identifier_match():
    engine = MatchingEngine(Config())
    match = engine.match_song(None, None, _candidates(), isrc="NL-A01-12-34567")
    assert match.level == 1 and match.confidence == 1.0
    assert match.matched_strings["identifier"] == "ISRC"


def test_level2_fuzzy_match_stores_matched_strings_and_confidence():
    engine = MatchingEngine(Config())
    # Diacritics, case, punctuation and a feat. clause must not break it.
    match = engine.match_song(
        "Vóórbeeldlied (feat. Someone)", "DE VOORBEELDEN!", _candidates()
    )
    assert match.level == 2
    assert 0.8 <= match.confidence <= 0.95
    assert match.matched_strings["source_title"] == "Vóórbeeldlied (feat. Someone)"
    assert match.matched_strings["watchlist_title"] == "Voorbeeldlied"
    assert match.matched_strings["title_score"] >= 0.92
    assert not match.needs_review


def test_level3_title_only_flagged_for_review():
    engine = MatchingEngine(Config())
    match = engine.match_song("Voorbeeldlied", "Completely Different Artist", _candidates())
    assert match.level == 3
    assert match.confidence < 0.8
    assert match.needs_review
    assert match.matched_strings["artist_score"] < 0.92


def test_no_match_below_thresholds():
    engine = MatchingEngine(Config())
    assert engine.match_song("Bohemian Rhapsody", "Queen", _candidates()) is None


def test_normalization_rules():
    assert normalize("Café Del MAR") == "cafe del mar"
    assert normalize_title("Song Title feat. Other Artist") == "song title"
    assert normalize("Ｔｏｋｙｏ Ｎｉｇｈｔｓ") == "tokyo nights"  # fullwidth (JP)
    assert normalize("A & B") == normalize("A and B")


def test_candidates_built_from_seeded_watchlist(seeded_session):
    candidates = build_work_candidates(seeded_session)
    assert [c.watchlist_id for c in candidates] == ["W-001"]
    assert "NLA011234567" in candidates[0].isrcs
    assert "Example Song" in candidates[0].titles


def test_false_positive_suppressed_in_next_run(
    seeded_session, config, http_client_factory
):
    run_collectors(
        seeded_session, config, modules=["setlistfm"], since=SINCE,
        http_client_factory=http_client_factory,
    )
    finding = seeded_session.query(Finding).filter_by(watchlist_id="A-002").one()
    # The finding is auditable: matched strings + confidence are stored.
    assert finding.matched_strings["watchlist_artist"] == "Other Band"
    assert finding.confidence < 0.8

    mark_false_positive(seeded_session, finding.finding_id)
    seeded_session.commit()
    assert finding.status == "false_positive"
    assert seeded_session.query(Rejection).count() == 1

    # Wipe the finding so only the rejection memory can stop recreation.
    seeded_session.delete(finding)
    seeded_session.commit()

    report = run_collectors(
        seeded_session, config, modules=["setlistfm"], since=SINCE,
        http_client_factory=http_client_factory,
    )
    assert report.runs[0].findings_suppressed == 1
    assert seeded_session.query(Finding).filter_by(watchlist_id="A-002").count() == 0
