"""Matching engine (req. 5) - central component shared by all collectors.

Three levels:
  Level 1 - identifier match (ISRC, ISWC, IMDb/TMDb, MusicBrainz,
            setlist.fm ID) -> confidence 1.0.
  Level 2 - strong fuzzy: normalized title + normalized artist/writer
            above a similarity threshold -> confidence 0.8-0.95.
  Level 3 - weak fuzzy: title-only match or artist-only concert
            -> confidence < 0.8, flagged needs_review.

Every match result carries the level and the raw matched strings so a
human can audit the match. The rejection memory lives in the findings
pipeline (see findings.py) since it is keyed on source items.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz
from sqlalchemy.orm import Session, joinedload

from .config import Config
from .models import AvProduction, Performer, WatchlistEntry, Work
from .normalize import normalize, normalize_title


@dataclass
class MatchResult:
    watchlist_id: str
    entity_type: str
    level: int
    confidence: float
    # Raw matched strings + scores, stored on the finding for audit.
    matched_strings: dict
    needs_review: bool = False


@dataclass
class WorkCandidate:
    """Flattened, pre-normalized view of a watchlist work for matching."""

    watchlist_id: str
    titles: list[str]            # canonical + alternative + recording titles (raw)
    artists: list[str]           # recording main artists + writer names (raw)
    isrcs: set[str] = field(default_factory=set)
    iswc: str | None = None
    norm_titles: list[str] = field(default_factory=list)
    norm_artists: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.norm_titles = [normalize_title(t) for t in self.titles if t]
        self.norm_artists = [normalize(a) for a in self.artists if a]
        self.isrcs = {i.replace("-", "").upper() for i in self.isrcs if i}
        if self.iswc:
            self.iswc = self.iswc.replace("-", "").replace(".", "").upper()


def build_work_candidates(
    session: Session, only_ids: list[str] | None = None
) -> list[WorkCandidate]:
    query = (
        session.query(WatchlistEntry)
        .filter(WatchlistEntry.entity_type == "work", WatchlistEntry.active.is_(True))
        .options(joinedload(WatchlistEntry.work).joinedload(Work.recordings))
    )
    if only_ids is not None:
        query = query.filter(WatchlistEntry.id.in_(only_ids))
    candidates = []
    for entry in query.all():
        work = entry.work
        titles = [entry.display_name]
        artists: list[str] = []
        isrcs: set[str] = set()
        iswc = None
        if work is not None:
            titles += list(work.alternative_titles or [])
            artists += [w.get("name", "") for w in (work.writers or [])]
            iswc = work.iswc
            for rec in work.recordings:
                titles.append(rec.recording_title)
                artists.append(rec.main_artist)
                if rec.isrc:
                    isrcs.add(rec.isrc)
        candidates.append(
            WorkCandidate(
                watchlist_id=entry.id, titles=titles, artists=artists,
                isrcs=isrcs, iswc=iswc,
            )
        )
    return candidates


class MatchingEngine:
    def __init__(self, config: Config | None = None):
        self.config = config or Config()

    # -- Level 2/3 confidence scaling ------------------------------------
    def _level2_confidence(self, score: float) -> float:
        """Map a score in [threshold, 1.0] onto [0.8, 0.95]."""
        t = self.config.level2_threshold
        span = (score - t) / (1.0 - t) if t < 1.0 else 1.0
        return round(0.8 + 0.15 * max(0.0, min(1.0, span)), 4)

    def _level3_confidence(self, score: float) -> float:
        """Title-only matches stay below 0.8."""
        return round(min(0.79, 0.5 + 0.29 * score), 4)

    # -- Works / recordings ----------------------------------------------
    def match_song(
        self,
        title: str | None,
        artist: str | None,
        candidates: list[WorkCandidate],
        isrc: str | None = None,
        iswc: str | None = None,
    ) -> MatchResult | None:
        """Match an observed song (e.g. a setlist entry or chart row)
        against watchlist works. Returns the best match or None."""
        # Level 1: identifier match.
        if isrc:
            key = isrc.replace("-", "").upper()
            for c in candidates:
                if key in c.isrcs:
                    return MatchResult(
                        c.watchlist_id, "work", 1, 1.0,
                        {"identifier": "ISRC", "value": isrc},
                    )
        if iswc:
            key = iswc.replace("-", "").replace(".", "").upper()
            for c in candidates:
                if c.iswc and c.iswc == key:
                    return MatchResult(
                        c.watchlist_id, "work", 1, 1.0,
                        {"identifier": "ISWC", "value": iswc},
                    )
        if not title:
            return None

        norm_song = normalize_title(title)
        norm_artist = normalize(artist) if artist else ""
        best: MatchResult | None = None

        for c in candidates:
            title_score, matched_title = 0.0, ""
            for raw, norm in zip(c.titles, c.norm_titles):
                score = fuzz.token_set_ratio(norm_song, norm) / 100.0
                if score > title_score:
                    title_score, matched_title = score, raw
            artist_score, matched_artist = 0.0, ""
            if norm_artist:
                for raw, norm in zip(c.artists, c.norm_artists):
                    score = fuzz.token_set_ratio(norm_artist, norm) / 100.0
                    if score > artist_score:
                        artist_score, matched_artist = score, raw

            matched_strings = {
                "source_title": title,
                "source_artist": artist,
                "watchlist_title": matched_title,
                "watchlist_artist": matched_artist,
                "title_score": round(title_score, 4),
                "artist_score": round(artist_score, 4),
            }
            t2 = self.config.level2_threshold
            result: MatchResult | None = None
            if norm_artist and title_score >= t2 and artist_score >= t2:
                conf = self._level2_confidence(min(title_score, artist_score))
                result = MatchResult(c.watchlist_id, "work", 2, conf, matched_strings)
            elif title_score >= self.config.level3_threshold:
                conf = self._level3_confidence(title_score)
                result = MatchResult(
                    c.watchlist_id, "work", 3, conf, matched_strings, needs_review=True
                )
            if result and (best is None or result.confidence > best.confidence):
                best = result
        return best

    # -- Performers --------------------------------------------------------
    def match_performer(
        self,
        name: str | None,
        performer_entry: WatchlistEntry,
        musicbrainz_id: str | None = None,
        setlistfm_id: str | None = None,
    ) -> MatchResult | None:
        """Confirm an observed artist is the given watchlist performer."""
        p: Performer | None = performer_entry.performer
        if p is None:
            return None
        if musicbrainz_id and p.musicbrainz_id and musicbrainz_id == p.musicbrainz_id:
            return MatchResult(
                performer_entry.id, "performer", 1, 1.0,
                {"identifier": "MusicBrainz ID", "value": musicbrainz_id},
            )
        if setlistfm_id and p.setlistfm_id and setlistfm_id == p.setlistfm_id:
            return MatchResult(
                performer_entry.id, "performer", 1, 1.0,
                {"identifier": "setlist.fm ID", "value": setlistfm_id},
            )
        if not name:
            return None
        norm_name = normalize(name)
        known = [performer_entry.display_name] + list(p.aliases or [])
        best_score, matched = 0.0, ""
        for raw in known:
            score = fuzz.token_set_ratio(norm_name, normalize(raw)) / 100.0
            if score > best_score:
                best_score, matched = score, raw
        matched_strings = {
            "source_artist": name,
            "watchlist_artist": matched,
            "artist_score": round(best_score, 4),
        }
        if best_score >= self.config.level2_threshold:
            return MatchResult(
                performer_entry.id, "performer", 2,
                self._level2_confidence(best_score), matched_strings,
            )
        if best_score >= self.config.level3_threshold:
            return MatchResult(
                performer_entry.id, "performer", 3,
                self._level3_confidence(best_score), matched_strings,
                needs_review=True,
            )
        return None

    # -- AV productions ------------------------------------------------------
    def match_production(
        self,
        title: str | None,
        production_entry: WatchlistEntry,
        imdb_id: str | None = None,
        tmdb_id: str | None = None,
        year: int | None = None,
    ) -> MatchResult | None:
        av: AvProduction | None = production_entry.av_production
        if av is None:
            return None
        if imdb_id and av.imdb_id and imdb_id == av.imdb_id:
            return MatchResult(
                production_entry.id, "av_production", 1, 1.0,
                {"identifier": "IMDb ID", "value": imdb_id},
            )
        if tmdb_id and av.tmdb_id and str(tmdb_id) == str(av.tmdb_id):
            return MatchResult(
                production_entry.id, "av_production", 1, 1.0,
                {"identifier": "TMDb ID", "value": str(tmdb_id)},
            )
        if not title:
            return None
        norm_obs = normalize(title)
        known = [production_entry.display_name]
        if av.original_title:
            known.append(av.original_title)
        best_score, matched = 0.0, ""
        for raw in known:
            score = fuzz.token_set_ratio(norm_obs, normalize(raw)) / 100.0
            if score > best_score:
                best_score, matched = score, raw
        matched_strings = {
            "source_title": title,
            "watchlist_title": matched,
            "title_score": round(best_score, 4),
            "source_year": year,
            "watchlist_year": av.production_year,
        }
        year_ok = year is None or av.production_year is None or year == av.production_year
        if best_score >= self.config.level2_threshold and year_ok:
            return MatchResult(
                production_entry.id, "av_production", 2,
                self._level2_confidence(best_score), matched_strings,
            )
        if best_score >= self.config.level3_threshold:
            return MatchResult(
                production_entry.id, "av_production", 3,
                self._level3_confidence(best_score), matched_strings,
                needs_review=True,
            )
        return None

    def artist_only_concert(
        self, performer_entry: WatchlistEntry, observed_name: str
    ) -> MatchResult:
        """Concert by a watchlist performer with no known-works subset:
        a low-confidence Level 3 finding flagged for review (req. 3.3)."""
        return MatchResult(
            performer_entry.id, "performer", 3,
            self.config.artist_only_confidence,
            {
                "source_artist": observed_name,
                "watchlist_artist": performer_entry.display_name,
                "reason": "artist-only concert, no known-works subset on watchlist",
            },
            needs_review=True,
        )
