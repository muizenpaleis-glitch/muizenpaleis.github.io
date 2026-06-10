"""Run orchestration: instantiate enabled collectors, feed them the
watchlist, persist drafts through the dedupe/rejection pipeline, and
write a per-collector run log (req. 4, 7)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import alerts
from .collectors import REGISTRY, CollectorContext
from .config import Config
from .evidence import EvidenceStore
from .findings import RecordOutcome, record_finding
from .matching import MatchingEngine
from .models import CollectorRun, Finding, WatchlistEntry, utcnow
from .ratelimit import RateLimiter

logger = logging.getLogger("rum.runner")


@dataclass
class RunReport:
    runs: list[CollectorRun] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = ["Run report:"]
        for r in self.runs:
            market = r.market or "all markets"
            lines.append(
                f"  {r.module} [{market}]: {r.items_checked} items checked, "
                f"{r.findings_new} new findings, {r.findings_duplicate} duplicates "
                f"skipped, {r.findings_suppressed} suppressed, "
                f"{len(r.errors)} errors"
            )
            for err in r.errors:
                lines.append(f"    error: {err}")
        for alert in self.alerts:
            lines.append(f"  ALERT: {alert}")
        return "\n".join(lines)


def run_collectors(
    session: Session,
    config: Config,
    modules: list[str] | None = None,
    markets: list[str] | None = None,
    since: date | None = None,
    http_client_factory=None,
) -> RunReport:
    """Execute one collection run. One shared rate limiter for all
    collectors (req. 10.4); idempotent thanks to the dedupe key (req. 4)."""
    since = since or (date.today() - timedelta(days=7))
    limiter = RateLimiter(config.rate_limit_seconds)
    engine = MatchingEngine(config)
    evidence_store = EvidenceStore(config.evidence_dir)
    report = RunReport()
    new_findings: list[Finding] = []

    # Per-module enable/disable (req. 7): explicit modules > config > all.
    names = modules or config.enabled_modules or sorted(REGISTRY)
    watchlist = (
        session.query(WatchlistEntry).filter(WatchlistEntry.active.is_(True)).all()
    )

    for name in names:
        if name not in REGISTRY:
            raise ValueError(f"unknown collector module '{name}' (known: {sorted(REGISTRY)})")
        module_markets = markets or config.module_markets.get(name) or [None]
        for market in module_markets:
            context = CollectorContext(
                config=config, session=session, engine=engine,
                limiter=limiter, http_client_factory=http_client_factory,
            )
            collector = REGISTRY[name](context)
            run = CollectorRun(module=name, market=market, ok=True)
            session.add(run)
            wl_slice = [
                e for e in watchlist if e.entity_type in collector.entity_types
            ]
            try:
                drafts = collector.collect(wl_slice, market, since)
                for draft in drafts:
                    outcome, finding = record_finding(session, draft, evidence_store)
                    if outcome is RecordOutcome.CREATED:
                        run.findings_new += 1
                        new_findings.append(finding)
                    elif outcome is RecordOutcome.DUPLICATE:
                        run.findings_duplicate += 1
                    else:
                        run.findings_suppressed += 1
            except Exception as exc:  # one failing module must not kill the run
                logger.exception("collector %s failed", name)
                collector.errors.append(f"{type(exc).__name__}: {exc}")
                run.ok = False
            run.items_checked = collector.items_checked
            run.errors = list(collector.errors)
            run.ok = run.ok and not collector.errors
            run.finished_at = utcnow()
            logger.info(
                "collector %s [%s]: checked=%d new=%d dup=%d suppressed=%d errors=%d",
                name, market or "all", run.items_checked, run.findings_new,
                run.findings_duplicate, run.findings_suppressed, len(run.errors),
            )
            report.runs.append(run)
    # Phase 3 alerting: high-priority watchlist + high-confidence finding.
    report.alerts = alerts.notify_new_findings(session, config, new_findings)
    session.commit()
    return report
