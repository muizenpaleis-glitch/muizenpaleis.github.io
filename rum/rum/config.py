"""Configuration. All thresholds and limits are configurable (req. 5, 10.4).

Secrets (API keys) come from environment variables only and are never
written to disk by this module (req. 7).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # Storage. SQLite for local MVP; schema is Postgres-compatible (req. 6).
    database_url: str = "sqlite:///rum.db"
    evidence_dir: str = "evidence"
    # Evidence snapshots are immutable and retained >= 5 years (req. 6).
    evidence_retention_years: int = 5

    # Honest identification (req. 4 collector behavior, 10.3).
    contact_email: str = "repertoire-monitor@example.org"

    # Central per-domain rate limit: default <= 1 request / 2 seconds (req. 4).
    rate_limit_seconds: float = 2.0
    backoff_max_retries: int = 4
    backoff_base_seconds: float = 2.0

    # Matching engine thresholds (req. 5, all configurable).
    # Level 2: normalized title + artist/writer token-set ratio >= this value.
    level2_threshold: float = 0.92
    # Level 3: title-only match threshold; results are confidence < 0.8.
    level3_threshold: float = 0.80
    # Confidence assigned to an artist-only concert finding (Level 3).
    artist_only_confidence: float = 0.5

    # Collector API keys (from environment).
    setlistfm_api_key: str | None = None
    youtube_api_key: str | None = None
    tmdb_api_key: str | None = None

    # Per-module enable/disable and market lists (req. 7).
    # enabled_modules None means: all registered modules.
    enabled_modules: list | None = None
    # e.g. {"charts": ["DE", "JP"], "setlistfm": ["DE"]}
    module_markets: dict = field(default_factory=dict)

    # Streaming charts source (req. 4 source #1). The access route is an
    # open question (req. 12) - the URL template is configurable so the
    # route chosen after the ToS assessment can be plugged in.
    charts_url_template: str = (
        "https://spotifycharts.com/regional/{market}/weekly/latest/download"
    )
    charts_source_name: str = "spotify-weekly-top200"

    # Phase 3 alerting: notify when a high-priority watchlist item gets a
    # high-confidence finding (req. 8 phase 3).
    alert_min_confidence: float = 0.9
    slack_webhook_url: str | None = None

    @property
    def user_agent(self) -> str:
        return f"RUM-RepertoireUsageMonitor/0.1 (+contact: {self.contact_email})"

    @classmethod
    def from_env(cls) -> "Config":
        cfg = cls()
        cfg.database_url = os.environ.get("RUM_DATABASE_URL", cfg.database_url)
        cfg.evidence_dir = os.environ.get("RUM_EVIDENCE_DIR", cfg.evidence_dir)
        cfg.evidence_retention_years = int(
            os.environ.get("RUM_EVIDENCE_RETENTION_YEARS", cfg.evidence_retention_years)
        )
        cfg.contact_email = os.environ.get("RUM_CONTACT_EMAIL", cfg.contact_email)
        cfg.rate_limit_seconds = float(
            os.environ.get("RUM_RATE_LIMIT_SECONDS", cfg.rate_limit_seconds)
        )
        cfg.level2_threshold = float(
            os.environ.get("RUM_LEVEL2_THRESHOLD", cfg.level2_threshold)
        )
        cfg.level3_threshold = float(
            os.environ.get("RUM_LEVEL3_THRESHOLD", cfg.level3_threshold)
        )
        cfg.setlistfm_api_key = os.environ.get("SETLISTFM_API_KEY")
        cfg.youtube_api_key = os.environ.get("YOUTUBE_API_KEY")
        cfg.tmdb_api_key = os.environ.get("TMDB_API_KEY")
        enabled = os.environ.get("RUM_ENABLED_MODULES", "").strip()
        if enabled:
            cfg.enabled_modules = [m.strip() for m in enabled.split(",") if m.strip()]
        markets_json = os.environ.get("RUM_MODULE_MARKETS", "").strip()
        if markets_json:
            cfg.module_markets = json.loads(markets_json)
        cfg.charts_url_template = os.environ.get(
            "RUM_CHARTS_URL_TEMPLATE", cfg.charts_url_template
        )
        cfg.alert_min_confidence = float(
            os.environ.get("RUM_ALERT_MIN_CONFIDENCE", cfg.alert_min_confidence)
        )
        cfg.slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
        return cfg
