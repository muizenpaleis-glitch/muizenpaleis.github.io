"""Alerting (req. 8 phase 3): notify when a high-priority watchlist item
gets a high-confidence finding in a market.

Alerts are always logged; if SLACK_WEBHOOK_URL is configured they are
also posted to Slack. Email can be added as a further channel later.
"""

from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from .config import Config
from .models import Finding, WatchlistEntry

logger = logging.getLogger("rum.alerts")


def alert_messages(session: Session, config: Config, findings: list[Finding]) -> list[str]:
    messages = []
    for f in findings:
        if f.confidence < config.alert_min_confidence:
            continue
        entry = session.get(WatchlistEntry, f.watchlist_id)
        if entry is None or entry.priority != "high":
            continue
        messages.append(
            f"High-priority usage: '{entry.display_name}' ({f.watchlist_id}) - "
            f"{f.usage_type} in {f.market}, period {f.period}, "
            f"confidence {f.confidence} via {f.source_module} ({f.source_url})"
        )
    return messages


def notify_new_findings(
    session: Session, config: Config, findings: list[Finding], http_post=httpx.post
) -> list[str]:
    """Generate and deliver alerts for newly created findings."""
    messages = alert_messages(session, config, findings)
    for msg in messages:
        logger.warning("ALERT: %s", msg)
    if messages and config.slack_webhook_url:
        try:
            http_post(
                config.slack_webhook_url,
                json={"text": "\n".join(messages)},
                timeout=15,
            )
        except httpx.HTTPError as exc:
            logger.error("alert delivery to Slack failed: %s", exc)
    return messages
