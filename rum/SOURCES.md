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

## charts (implemented; access route requires sign-off before production)

- **Data source**: per-country published streaming charts (Spotify weekly
  top 200 CSV format by default).
- **Access method**: HTTP download of the publicly published chart file.
  The exact route is an **open question in the requirements (req. 12)**:
  the historical `spotifycharts.com` CSV endpoint vs. the current
  `charts.spotify.com` site vs. licensed third-party archives. The URL
  template is configurable (`RUM_CHARTS_URL_TEMPLATE`) so the route chosen
  after the ToS assessment can be plugged in without code changes.
- **ToS assessment date**: PENDING - must be completed and recorded here
  by the product owner before the module's first production run. The
  module ships disabled-by-default guidance: enable it only after
  sign-off. No login wall, CAPTCHA, or paywall circumvention under any
  route (req. 10.2); if no compliant route exists, this module stays off.
- **Rate limit applied**: central limiter, 1 request / 2 s per domain
  (one request per market per week in practice).
- **Data stored**: matched chart rows (position, streams) and the chart
  file as evidence snapshot.

## youtube (implemented)

- **Data source**: YouTube video metadata and view counts for watchlist
  recordings (view-count deltas per week as a usage signal).
- **Access method**: official YouTube Data API v3
  (`https://www.googleapis.com/youtube/v3`), API key via
  `YOUTUBE_API_KEY`. Subject to the YouTube API Services Terms; usage is
  metadata-only and well within default quota for the expected watchlist
  size.
- **ToS assessment date**: 2026-06-10 - API ToS permit this analytical
  use; re-assess before production rollout.
- **Rate limit applied**: central limiter, 1 request / 2 s, plus the
  API's own quota system.
- **Data stored**: video ID, title, channel, view counts (snapshots for
  weekly deltas) and the raw API JSON as evidence. Market recorded as
  "global" - the region signal on YouTube is weak (req. 4 source #2).

## tmdb (implemented)

- **Data source**: TMDb watch providers (streaming availability per
  country) for watchlist AV productions.
- **Access method**: official TMDb API (`https://api.themoviedb.org/3`),
  API key via `TMDB_API_KEY`. TMDb terms require attribution
  ("This product uses the TMDB API but is not endorsed or certified by
  TMDB") - include this in any user-facing output of TMDb-derived data.
- **ToS assessment date**: 2026-06-10 - non-commercial internal
  analytical use permitted with attribution; re-assess before production.
- **Rate limit applied**: central limiter, 1 request / 2 s (TMDb's own
  limit is ~50 req/s, we stay far below).
- **Data stored**: provider names per country and the raw watch-providers
  JSON as evidence.

## musicbrainz (implemented - enrichment only, produces no findings)

- **Data source**: artist aliases and ISRC -> canonical recording titles,
  used solely to strengthen matching (req. 4 source #5).
- **Access method**: official MusicBrainz web service
  (`https://musicbrainz.org/ws/2`), no key needed. MusicBrainz etiquette
  requires an identifying User-Agent and max 1 request/second.
- **ToS assessment date**: 2026-06-10 - data is CC0/CC BY-NC-SA; metadata
  lookups for internal matching are within the published guidelines.
- **Rate limit applied**: central limiter, 1 request / 2 s (stricter than
  the required 1 req/s).
- **Data stored**: aliases and alternative titles merged into the
  watchlist; no evidence snapshots (not a usage source).

## Planned modules (not yet implemented)

| Module | Source | Access method | Status |
|---|---|---|---|
| apple_music_charts / youtube_music_charts | additional public charts | per-source assessment required | not built |
| Tier 2 TV/EPG per country (DE, JP, FR, UK, ES suggested) | national EPG aggregators | per-source assessment required (req. 4 Tier 2) | not built |
| Tier 2 radio airplay | station "now playing" pages/APIs | per-station-group assessment | not built |

Each new module must add its entry here **before** its first production
run, including the ToS assessment date.
