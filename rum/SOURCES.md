# Source register (compliance requirement 10.6)

Per module: data source, access method, ToS assessment date, rate limit
applied. All modules go through the central per-domain rate limiter
(`rum/ratelimit.py`); the default is at most 1 request per 2 seconds per
domain, with exponential backoff on 429/5xx and no parallel requests
against a single domain.

## setlistfm (implemented)

- **Data source**: setlist.fm concert setlists.
- **Access method**: Official REST API (`https://api.setlist.fm/rest/1.0`),
  documented at <https://api.setlist.fm/docs/1.0/index.html>. No scraping.
- **Authentication**: free API key requested from setlist.fm, supplied via
  the `SETLISTFM_API_KEY` environment variable. No login wall is bypassed;
  the API is the access channel setlist.fm provides for exactly this use.
- **Identification**: honest `User-Agent` including a contact address
  (configured via `RUM_CONTACT_EMAIL`), plus the `x-api-key` header.
- **ToS assessment date**: 2026-06-10. The setlist.fm API terms permit
  non-commercial / internal analytical use with attribution; the API key
  registration states the allowed request volume. Re-assess before
  production rollout and record the outcome here.
- **Rate limit applied**: central limiter at 1 request / 2 s against
  `api.setlist.fm` (well below the published API limit), exponential
  backoff on 429/5xx honoring `Retry-After`.
- **Data stored**: setlist metadata (venue, city, country, date, song
  titles) and the raw API JSON of the matched setlist as the evidence
  snapshot. Only public performer names; no personal data beyond that.

## Planned Tier 1 modules (not yet implemented)

| Module | Source | Access method | Status |
|---|---|---|---|
| streaming_charts | Spotify / Apple Music / YouTube Music public charts | per-source assessment required (open question, req. 12) | not built |
| youtube | YouTube Data API v3 | official API, key via env | not built |
| tmdb | TMDb API (watch providers, releases) | official API, key via env | not built |
| musicbrainz | MusicBrainz web service (enrichment only) | official API, 1 req/s etiquette | not built |

Each new module must add its entry here **before** its first production
run, including the ToS assessment date.
