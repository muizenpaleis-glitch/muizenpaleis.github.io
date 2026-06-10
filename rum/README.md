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
- **Tier 1 collectors (req. §4)**:
  - **setlistfm** — official API; concerts by watchlist performers with
    venue/city/country/date and song-level matching; artist-only
    concerts become low-confidence review findings.
  - **charts** — per-country streaming charts (Spotify weekly CSV format,
    URL template configurable pending the §12 ToS assessment); matched
    by ISRC where exposed, else normalized artist + title.
  - **youtube** — official Data API v3; official/prominent uploads per
    work, view-count snapshots and weekly deltas; market is "global".
  - **tmdb** — official API; VOD availability per country (watch
    providers) for AV productions, by TMDb ID or title search.
  - **musicbrainz enrichment** — not a usage source; resolves performer
    aliases and ISRC canonical titles to strengthen matching
    (`rum enrich` or the web UI).
- **Scheduling & operations (req. §7)** — per-module enable/disable
  (`RUM_ENABLED_MODULES`) and per-module market lists
  (`RUM_MODULE_MARKETS`), stored + printed run reports, Dockerfile for
  single-VM deployment, cron-driven weekly runs (see below).
- **Alerting (req. §8 phase 3)** — when a high-priority watchlist item
  gets a finding with confidence ≥ `RUM_ALERT_MIN_CONFIDENCE` (default
  0.9), an alert is logged, shown in the run report, and posted to
  `SLACK_WEBHOOK_URL` if configured.
- **Shared collector infrastructure (req. §4)** — pluggable collector
  interface `collect(watchlist_slice, market, since) -> findings[]`,
  central per-domain rate limiter with logged acquisitions, exponential
  backoff, honest User-Agent, idempotent runs via dedupe keys, per-run
  logs, and CSV export with export batches (req. §8 phase 1).

- **Web UI** (`rum/webapp.py`, FastAPI, server-rendered; req. §8
  phase 2) — watchlist CSV import & CRUD, collection runs, findings
  table with filters, finding detail with matched-strings audit and the
  evidence snapshot, review actions (confirm / false positive), run
  log, CSV export download, MusicBrainz enrichment, and a
  findings-per-market-per-week chart on the dashboard. A **demo mode**
  seeds sample watchlist entries and runs all collectors against
  bundled fake API responses, so the whole pipeline can be tested
  without API keys or network access.

Not yet built: Tier 2 country modules (TV/EPG, radio airplay — each
needs its per-source assessment first, see SOURCES.md) and email
alert delivery (Slack + log are in).

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
`RUM_EVIDENCE_RETENTION_YEARS`, `RUM_ENABLED_MODULES`,
`RUM_MODULE_MARKETS` (JSON, e.g. `{"charts": ["DE", "JP"]}`),
`RUM_CHARTS_URL_TEMPLATE`, `RUM_ALERT_MIN_CONFIDENCE`, plus the secrets
`SETLISTFM_API_KEY`, `YOUTUBE_API_KEY`, `TMDB_API_KEY`,
`SLACK_WEBHOOK_URL`. Secrets live only in the environment / `.env`
(never committed).

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

## Web UI

```bash
rum serve            # http://127.0.0.1:8000
```

To test without a setlist.fm API key: on the **Dashboard** click
*Seed demo watchlist*, then on **Run collectors** start a run with
*demo mode* checked. Findings, review actions, the run log and the CSV
export then all work on the demo data. Uncheck demo mode (with
`SETLISTFM_API_KEY` set) to collect from the real API.

## Running a collection (CLI)

```bash
rum run                                # all enabled modules, all markets
rum run --module setlistfm --market DE --since 2026-06-01
rum enrich                             # MusicBrainz alias/title enrichment
rum list-findings --needs-review
rum mark-false-positive <finding-id>   # suppressed in future runs
rum export findings.csv --market DE --period-from 2026-06-01 --min-confidence 0.8
```

Each run prints and stores a per-collector report (items checked, new
findings, duplicates, suppressed, errors) plus any high-priority
alerts. Re-running the same period produces zero duplicates.

## Scheduling & deployment (req. §7, §9)

Build and run the container (web UI on port 8000, data on a volume):

```bash
docker build -t rum .
docker run -d --name rum -p 8000:8000 -v rum-data:/data --env-file .env rum
```

Weekly collection via the host's cron (Monday 03:00, per req. §7 a
full Tier 1 run for 5,000 watchlist items fits comfortably in a night
at the default rate limit):

```cron
0 3 * * 1  docker exec rum rum run >> /var/log/rum-weekly.log 2>&1
0 4 * * 1  docker exec rum rum enrich >> /var/log/rum-enrich.log 2>&1
```

Per-module enable/disable and market lists belong in `.env`, e.g.
`RUM_ENABLED_MODULES=setlistfm,tmdb,youtube` and
`RUM_MODULE_MARKETS={"charts": ["DE", "JP", "FR", "GB", "ES"]}`.

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
