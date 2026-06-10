# RUM — International Repertoire Usage Monitor

Evidence collector for a CMO: monitors public sources for usage of a
curated watchlist of repertoire in foreign markets and stores
timestamped, sourced findings with immutable evidence snapshots.
See the requirements document for full scope.

## What is implemented (this iteration)

- **Watchlist (req. §3)** — three entity types (works, AV productions,
  performers) with common management fields (priority, active flag,
  country filter, notes); CSV import with per-type templates,
  validation and rejected-row reporting; CRUD via the Typer CLI.
- **Matching engine (req. §5)** — Level 1 identifier match (ISRC, ISWC,
  IMDb/TMDb, MusicBrainz, setlist.fm IDs → confidence 1.0), Level 2
  strong fuzzy (normalized title + artist/writer, token-set ratio,
  configurable threshold → 0.8–0.95), Level 3 weak fuzzy (title-only /
  artist-only concert → < 0.8, flagged `needs_review`). Every match
  stores its level and raw matched strings. Rejection memory suppresses
  reviewer-rejected (source item ↔ watchlist item) pairs.
- **Findings data model (req. §6)** — full schema from the requirements,
  immutable content-addressed evidence snapshots, SQLite for the local
  MVP with a Postgres-compatible schema.
- **setlist.fm collector (req. §4, Tier 1 #3)** — official API, concerts
  by watchlist performers with venue/city/country/date and song-level
  matching; artist-only concerts become low-confidence review findings.
- **Shared collector infrastructure (req. §4)** — pluggable collector
  interface `collect(watchlist_slice, market, since) -> findings[]`,
  central per-domain rate limiter with logged acquisitions, exponential
  backoff, honest User-Agent, idempotent runs via dedupe keys, per-run
  logs, and CSV export with export batches (req. §8 phase 1).

Not in this iteration: the chart, YouTube, TMDb and MusicBrainz
collectors (acceptance criterion 2 is therefore only verifiable for the
setlist-match part), Tier 2 country modules, scheduling, and the
dashboard.

## Setup

```bash
cd rum
pip install -e .[dev]
cp .env.example .env        # fill in SETLISTFM_API_KEY etc.
rum init-db
```

Configuration is environment-based (see `rum/config.py`):
`RUM_DATABASE_URL`, `RUM_EVIDENCE_DIR`, `RUM_CONTACT_EMAIL`,
`RUM_RATE_LIMIT_SECONDS`, `RUM_LEVEL2_THRESHOLD`, `RUM_LEVEL3_THRESHOLD`,
`RUM_EVIDENCE_RETENTION_YEARS`, `SETLISTFM_API_KEY`. Secrets live only
in the environment / `.env` (never committed).

## Watchlist import

Templates live in `templates/` (semicolon-delimited UTF-8; comma also
accepted). Multi-value cells use `|`; recordings are
`ISRC~title~artist` triples (ISRC may be empty); writers are
`Name~IPI` pairs (IPI may be empty).

```bash
rum template work works.csv          # write an empty template
rum import-watchlist work works.csv  # invalid rows reported with reasons
rum list-watchlist --active-only
rum set-active W-001 --inactive
```

## Running a collection

```bash
rum run --module setlistfm --market DE --since 2026-06-01
rum list-findings --needs-review
rum mark-false-positive <finding-id>   # suppressed in future runs
rum export findings.csv --market DE --period-from 2026-06-01 --min-confidence 0.8
```

Each run prints and stores a per-collector report (items checked, new
findings, duplicates, suppressed, errors). Re-running the same period
produces zero duplicates.

## Compliance

See `SOURCES.md` for the per-module source register (access method, ToS
assessment date, rate limit). All HTTP goes through the central rate
limiter; every slot acquisition is logged (`rum.ratelimit`), making
acceptance criterion 6 verifiable from the logs.

## Tests

```bash
cd rum && python -m pytest
```

`tests/` maps one file per MVP acceptance criterion (req. §11); the
setlist.fm API is mocked, no network access is needed.
