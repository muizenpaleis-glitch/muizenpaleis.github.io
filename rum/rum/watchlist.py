"""Watchlist management (req. 3): CSV import with per-entity-type
templates, validation with rejected-row reporting, and CRUD helpers.

Templates (see templates/ directory) are semicolon-delimited UTF-8;
comma-delimited files are detected and accepted too. Multi-value cells
use "|" between values. Recordings use ISRC~title~artist triples
(ISRC may be empty); writers use Name~IPI pairs (IPI may be empty).

Identifiers are expected to be inconsistent (req. 3.1): ISWC/ISRC are
optional and validated only when present.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from .models import (
    ENTITY_TYPES,
    PRIORITIES,
    AvProduction,
    Performer,
    WatchlistEntry,
    Work,
    WorkRecording,
)

ISWC_RE = re.compile(r"^T\d{9,10}\d$")          # after removing . and -
ISRC_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}\d{7}$")  # after removing -
COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")
AV_TYPES = ("film", "series", "documentary", "commercial")

WORK_COLUMNS = [
    "work_id", "title", "alternative_titles", "writers", "iswc",
    "recordings", "priority", "country_filter", "notes",
]
AV_COLUMNS = [
    "production_id", "title", "original_title", "production_year", "type",
    "imdb_id", "tmdb_id", "eidr", "country_of_origin", "contained_work_ids",
    "priority", "country_filter", "notes",
]
PERFORMER_COLUMNS = [
    "performer_id", "artist_name", "aliases", "musicbrainz_id",
    "setlistfm_artist_id", "known_work_ids", "priority", "country_filter", "notes",
]
TEMPLATE_COLUMNS = {
    "work": WORK_COLUMNS,
    "av_production": AV_COLUMNS,
    "performer": PERFORMER_COLUMNS,
}


@dataclass
class RejectedRow:
    row_number: int  # 1-based, counting the header as row 1
    reasons: list[str]
    raw: dict


@dataclass
class ImportReport:
    entity_type: str
    imported: int = 0
    updated: int = 0
    rejected: list[RejectedRow] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"{self.entity_type}: {self.imported} imported, "
            f"{self.updated} updated, {len(self.rejected)} rejected"
        ]
        for r in self.rejected:
            lines.append(f"  row {r.row_number}: {'; '.join(r.reasons)}")
        return "\n".join(lines)


def _split_multi(cell: str | None) -> list[str]:
    return [part.strip() for part in (cell or "").split("|") if part.strip()]


def _detect_delimiter(header_line: str) -> str:
    return ";" if header_line.count(";") >= header_line.count(",") else ","


def _validate_common(row: dict, id_col: str, name_col: str) -> tuple[list[str], dict]:
    """Validate fields shared by all entity types (req. 3.4)."""
    reasons: list[str] = []
    entry_id = (row.get(id_col) or "").strip()
    name = (row.get(name_col) or "").strip()
    if not entry_id:
        reasons.append(f"missing {id_col}")
    if not name:
        reasons.append(f"missing {name_col}")
    priority = (row.get("priority") or "normal").strip().lower() or "normal"
    if priority not in PRIORITIES:
        reasons.append(f"invalid priority '{priority}' (allowed: high, normal)")
    countries = [c.upper() for c in _split_multi(row.get("country_filter"))]
    for c in countries:
        if not COUNTRY_RE.match(c):
            reasons.append(f"invalid country code '{c}' in country_filter")
    common = {
        "id": entry_id,
        "display_name": name,
        "priority": priority,
        "country_filter": countries or None,
        "notes": (row.get("notes") or "").strip() or None,
    }
    return reasons, common


def _parse_work(row: dict) -> tuple[list[str], dict]:
    reasons, common = _validate_common(row, "work_id", "title")
    iswc = (row.get("iswc") or "").strip() or None
    if iswc and not ISWC_RE.match(iswc.replace("-", "").replace(".", "").upper()):
        reasons.append(f"invalid ISWC '{iswc}'")
    writers = []
    for part in _split_multi(row.get("writers")):
        name, _, ipi = part.partition("~")
        if not name.strip():
            reasons.append(f"writer entry without a name: '{part}'")
            continue
        writers.append({"name": name.strip(), "ipi": ipi.strip() or None})
    recordings = []
    for part in _split_multi(row.get("recordings")):
        bits = part.split("~")
        if len(bits) != 3:
            reasons.append(
                f"recording '{part}' must be ISRC~title~artist (ISRC may be empty)"
            )
            continue
        isrc, rec_title, rec_artist = (b.strip() for b in bits)
        if isrc and not ISRC_RE.match(isrc.replace("-", "").upper()):
            reasons.append(f"invalid ISRC '{isrc}'")
            continue
        if not rec_title or not rec_artist:
            reasons.append(f"recording '{part}' is missing title or artist")
            continue
        recordings.append(
            {"isrc": isrc.replace("-", "").upper() or None,
             "recording_title": rec_title, "main_artist": rec_artist}
        )
    common.update({
        "iswc": iswc,
        "alternative_titles": _split_multi(row.get("alternative_titles")),
        "writers": writers,
        "recordings": recordings,
    })
    return reasons, common


def _parse_av(row: dict) -> tuple[list[str], dict]:
    reasons, common = _validate_common(row, "production_id", "title")
    year_raw = (row.get("production_year") or "").strip()
    year = None
    if year_raw:
        if year_raw.isdigit() and 1880 <= int(year_raw) <= 2100:
            year = int(year_raw)
        else:
            reasons.append(f"invalid production_year '{year_raw}'")
    av_type = (row.get("type") or "").strip().lower() or None
    if av_type and av_type not in AV_TYPES:
        reasons.append(f"invalid type '{av_type}' (allowed: {', '.join(AV_TYPES)})")
    imdb_id = (row.get("imdb_id") or "").strip() or None
    if imdb_id and not re.match(r"^tt\d{6,10}$", imdb_id):
        reasons.append(f"invalid imdb_id '{imdb_id}'")
    origin = (row.get("country_of_origin") or "").strip().upper() or None
    if origin and not COUNTRY_RE.match(origin):
        reasons.append(f"invalid country_of_origin '{origin}'")
    common.update({
        "original_title": (row.get("original_title") or "").strip() or None,
        "production_year": year,
        "production_type": av_type,
        "imdb_id": imdb_id,
        "tmdb_id": (row.get("tmdb_id") or "").strip() or None,
        "eidr": (row.get("eidr") or "").strip() or None,
        "country_of_origin": origin,
        "contained_work_ids": _split_multi(row.get("contained_work_ids")),
    })
    return reasons, common


def _parse_performer(row: dict) -> tuple[list[str], dict]:
    reasons, common = _validate_common(row, "performer_id", "artist_name")
    mbid = (row.get("musicbrainz_id") or "").strip() or None
    if mbid and not re.match(r"^[0-9a-fA-F-]{36}$", mbid):
        reasons.append(f"invalid musicbrainz_id '{mbid}' (expected a UUID)")
    common.update({
        "aliases": _split_multi(row.get("aliases")),
        "musicbrainz_id": mbid,
        "setlistfm_id": (row.get("setlistfm_artist_id") or "").strip() or None,
        "known_work_ids": _split_multi(row.get("known_work_ids")),
    })
    return reasons, common


_PARSERS = {"work": _parse_work, "av_production": _parse_av, "performer": _parse_performer}


def import_csv(session: Session, entity_type: str, path: str | Path) -> ImportReport:
    """Import a watchlist CSV. Invalid rows are reported with reasons and
    skipped; valid rows are upserted and active (acceptance criterion 1)."""
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"unknown entity type '{entity_type}' (use one of {ENTITY_TYPES})")
    path = Path(path)
    report = ImportReport(entity_type=entity_type)
    with path.open(encoding="utf-8-sig", newline="") as fh:
        first_line = fh.readline()
        if not first_line.strip():
            raise ValueError(f"{path} is empty")
        delimiter = _detect_delimiter(first_line)
        fh.seek(0)
        reader = csv.DictReader(fh, delimiter=delimiter)
        expected = TEMPLATE_COLUMNS[entity_type]
        missing = [c for c in expected if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(
                f"{path} does not match the {entity_type} template; "
                f"missing columns: {', '.join(missing)}"
            )
        seen_ids: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            reasons, parsed = _PARSERS[entity_type](row)
            if parsed.get("id") in seen_ids:
                reasons.append(f"duplicate ID '{parsed['id']}' in this file")
            if reasons:
                report.rejected.append(RejectedRow(row_number, reasons, dict(row)))
                continue
            seen_ids.add(parsed["id"])
            if _upsert(session, entity_type, parsed):
                report.updated += 1
            else:
                report.imported += 1
    session.flush()
    return report


def _upsert(session: Session, entity_type: str, parsed: dict) -> bool:
    """Insert or update one entry. Returns True when it was an update."""
    entry = session.get(WatchlistEntry, parsed["id"])
    existed = entry is not None
    if entry is None:
        entry = WatchlistEntry(id=parsed["id"], entity_type=entity_type)
        session.add(entry)
    elif entry.entity_type != entity_type:
        raise ValueError(
            f"ID '{parsed['id']}' already exists as {entry.entity_type}"
        )
    entry.display_name = parsed["display_name"]
    entry.priority = parsed["priority"]
    entry.country_filter = parsed["country_filter"]
    entry.notes = parsed["notes"]
    entry.active = True

    if entity_type == "work":
        work = entry.work or Work(watchlist_id=entry.id)
        work.iswc = parsed["iswc"]
        work.alternative_titles = parsed["alternative_titles"]
        work.writers = parsed["writers"]
        work.recordings = [WorkRecording(**r) for r in parsed["recordings"]]
        entry.work = work
    elif entity_type == "av_production":
        av = entry.av_production or AvProduction(watchlist_id=entry.id)
        for key in ("original_title", "production_year", "production_type",
                    "imdb_id", "tmdb_id", "eidr", "country_of_origin",
                    "contained_work_ids"):
            setattr(av, key, parsed[key])
        entry.av_production = av
    else:
        perf = entry.performer or Performer(watchlist_id=entry.id)
        for key in ("aliases", "musicbrainz_id", "setlistfm_id", "known_work_ids"):
            setattr(perf, key, parsed[key])
        entry.performer = perf
    return existed


def set_active(session: Session, watchlist_id: str, active: bool) -> WatchlistEntry:
    entry = session.get(WatchlistEntry, watchlist_id)
    if entry is None:
        raise KeyError(f"no watchlist entry with id {watchlist_id}")
    entry.active = active
    session.flush()
    return entry


def delete_entry(session: Session, watchlist_id: str) -> None:
    entry = session.get(WatchlistEntry, watchlist_id)
    if entry is None:
        raise KeyError(f"no watchlist entry with id {watchlist_id}")
    session.delete(entry)
    session.flush()


def list_entries(
    session: Session, entity_type: str | None = None, active_only: bool = False
) -> list[WatchlistEntry]:
    query = session.query(WatchlistEntry)
    if entity_type:
        query = query.filter(WatchlistEntry.entity_type == entity_type)
    if active_only:
        query = query.filter(WatchlistEntry.active.is_(True))
    return query.order_by(WatchlistEntry.id).all()


def write_template(entity_type: str, path: str | Path) -> None:
    """Write an empty documented CSV template for an entity type."""
    columns = TEMPLATE_COLUMNS[entity_type]
    with Path(path).open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(columns)
