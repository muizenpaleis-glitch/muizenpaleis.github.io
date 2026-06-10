"""Acceptance criterion 1: import a watchlist CSV with mixed-quality
identifiers; invalid rows are reported, valid rows are active."""

from rum.models import WatchlistEntry
from rum.watchlist import import_csv, list_entries, set_active

WORKS_CSV = """\
work_id;title;alternative_titles;writers;iswc;recordings;priority;country_filter;notes
W-100;Volle Identificatie;Full ID Song;J. de Vries~00012345678;T-123456789-0;NLA011234567~Volle Identificatie~De Voorbeelden;high;DE|JP;all identifiers present
W-101;Alleen Titel En Schrijver;;A. Jansen~;;;normal;;title + writer only, no ISWC/ISRC
;Geen ID;;;;;normal;;missing work_id
W-103;Kapotte Identifiers;;B. Bakker~;NOT-AN-ISWC;BADISRC~Title~Artist;urgent;Germany;several invalid fields
W-100;Dubbel;;C. Citroen~;;;normal;;duplicate of W-100
"""


def test_mixed_quality_import(session, tmp_path):
    path = tmp_path / "works.csv"
    path.write_text(WORKS_CSV, encoding="utf-8")

    report = import_csv(session, "work", path)
    session.commit()

    # Valid rows (full identifiers AND minimal title+writer) are imported.
    assert report.imported == 2
    active_ids = {e.id for e in list_entries(session, "work", active_only=True)}
    assert active_ids == {"W-100", "W-101"}

    # Invalid rows are rejected with row numbers and reasons.
    assert len(report.rejected) == 3
    by_row = {r.row_number: r.reasons for r in report.rejected}
    assert any("missing work_id" in reason for reason in by_row[4])
    row5 = " ".join(by_row[5])
    assert "ISWC" in row5 and "ISRC" in row5 and "priority" in row5 and "country" in row5
    assert any("duplicate ID" in reason for reason in by_row[6])

    # The minimal entry kept its (lack of) identifiers - that's allowed.
    minimal = session.get(WatchlistEntry, "W-101")
    assert minimal.work.iswc is None
    assert minimal.work.writers == [{"name": "A. Jansen", "ipi": None}]

    # Full-identifier entry round-trips recordings and country filter.
    full = session.get(WatchlistEntry, "W-100")
    assert full.country_filter == ["DE", "JP"]
    assert full.work.recordings[0].isrc == "NLA011234567"
    assert full.applies_to_market("DE") and not full.applies_to_market("FR")


def test_reimport_updates_instead_of_duplicating(session, tmp_path):
    path = tmp_path / "works.csv"
    path.write_text(WORKS_CSV, encoding="utf-8")
    import_csv(session, "work", path)
    report2 = import_csv(session, "work", path)
    assert report2.updated == 2 and report2.imported == 0
    assert len(list_entries(session, "work")) == 2


def test_wrong_template_is_refused(session, tmp_path):
    path = tmp_path / "wrong.csv"
    path.write_text("foo;bar\n1;2\n", encoding="utf-8")
    try:
        import_csv(session, "work", path)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "missing columns" in str(exc)


def test_crud_set_active(session, tmp_path):
    path = tmp_path / "works.csv"
    path.write_text(WORKS_CSV, encoding="utf-8")
    import_csv(session, "work", path)
    entry = set_active(session, "W-100", False)
    assert entry.active is False
    assert {e.id for e in list_entries(session, "work", active_only=True)} == {"W-101"}
