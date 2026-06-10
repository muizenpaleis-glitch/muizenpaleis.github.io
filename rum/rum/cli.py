"""Typer CLI (req. 3.4: CLI acceptable for MVP).

Usage examples:
    rum init-db
    rum template work works.csv
    rum import-watchlist work works.csv
    rum list-watchlist --entity-type performer
    rum set-active W-001 --inactive
    rum run --module setlistfm --market DE --since 2026-06-01
    rum export findings.csv --market DE --period-from 2026-06-01
    rum mark-false-positive <finding-id>
"""

from __future__ import annotations

import logging
from datetime import date, datetime

import typer

from . import export as export_mod
from . import findings as findings_mod
from . import watchlist as watchlist_mod
from .config import Config
from .db import init_db, make_engine, make_session_factory
from .models import Finding
from .runner import run_collectors

app = typer.Typer(help="RUM - International Repertoire Usage Monitor")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


def _session():
    config = Config.from_env()
    engine = make_engine(config.database_url)
    init_db(engine)
    return config, make_session_factory(engine)()


@app.command("init-db")
def init_db_cmd():
    """Create the database schema."""
    config = Config.from_env()
    init_db(make_engine(config.database_url))
    typer.echo(f"schema ready at {config.database_url}")


@app.command()
def template(
    entity_type: str = typer.Argument(help="work | av_production | performer"),
    out: str = typer.Argument(help="path for the CSV template"),
):
    """Write the documented CSV import template for an entity type."""
    watchlist_mod.write_template(entity_type, out)
    typer.echo(f"template written to {out}")


@app.command()
def import_watchlist(
    entity_type: str = typer.Argument(help="work | av_production | performer"),
    path: str = typer.Argument(help="CSV file matching the template"),
):
    """Import a watchlist CSV; rejected rows are reported with reasons."""
    _, session = _session()
    try:
        report = watchlist_mod.import_csv(session, entity_type, path)
    except ValueError as exc:
        typer.echo(f"import failed: {exc}", err=True)
        raise typer.Exit(1)
    session.commit()
    typer.echo(report.summary())


@app.command()
def list_watchlist(
    entity_type: str = typer.Option(None, help="filter by entity type"),
    active_only: bool = typer.Option(False, "--active-only"),
):
    """List watchlist entries."""
    _, session = _session()
    for e in watchlist_mod.list_entries(session, entity_type, active_only):
        flag = "active" if e.active else "inactive"
        countries = ",".join(e.country_filter) if e.country_filter else "all"
        typer.echo(
            f"{e.id}\t{e.entity_type}\t{e.display_name}\t"
            f"priority={e.priority}\t{flag}\tmarkets={countries}"
        )


@app.command()
def set_active(
    watchlist_id: str,
    active: bool = typer.Option(True, "--active/--inactive"),
):
    """Activate or deactivate a watchlist entry."""
    _, session = _session()
    entry = watchlist_mod.set_active(session, watchlist_id, active)
    session.commit()
    typer.echo(f"{entry.id} is now {'active' if entry.active else 'inactive'}")


@app.command()
def run(
    module: list[str] = typer.Option(None, help="collector module(s); default all"),
    market: list[str] = typer.Option(None, help="ISO country code(s); default all"),
    since: str = typer.Option(None, help="start date YYYY-MM-DD; default 7 days ago"),
):
    """Execute a collection run and print the run report (req. 7)."""
    config, session = _session()
    since_date = datetime.strptime(since, "%Y-%m-%d").date() if since else None
    report = run_collectors(
        session, config,
        modules=list(module) or None,
        markets=[m.upper() for m in market] or None,
        since=since_date,
    )
    typer.echo(report.summary())


@app.command()
def export(
    out: str = typer.Argument(help="output CSV path"),
    market: str = typer.Option(None),
    period_from: str = typer.Option(None, help="YYYY-MM-DD or ISO week"),
    period_to: str = typer.Option(None),
    usage_type: str = typer.Option(None),
    min_confidence: float = typer.Option(None),
    watchlist_id: str = typer.Option(None),
    no_mark: bool = typer.Option(False, help="do not mark findings as exported"),
):
    """Export findings to a semicolon-delimited UTF-8 CSV (Excel-safe)."""
    _, session = _session()
    batch = export_mod.export_findings(
        session, out, market=market, period_from=period_from,
        period_to=period_to, usage_type=usage_type,
        min_confidence=min_confidence, watchlist_id=watchlist_id,
        mark_exported=not no_mark,
    )
    session.commit()
    typer.echo(f"exported {batch.row_count} findings to {out} (batch {batch.id})")


@app.command()
def list_findings(
    status: str = typer.Option(None),
    market: str = typer.Option(None),
    needs_review: bool = typer.Option(False, "--needs-review"),
):
    """List findings."""
    _, session = _session()
    query = session.query(Finding)
    if status:
        query = query.filter(Finding.status == status)
    if market:
        query = query.filter(Finding.market == market.upper())
    if needs_review:
        query = query.filter(Finding.needs_review.is_(True))
    for f in query.order_by(Finding.captured_at).all():
        typer.echo(
            f"{f.finding_id}\t{f.period}\t{f.market}\t{f.usage_type}\t"
            f"{f.watchlist_id}\tL{f.match_level}/{f.confidence}\t{f.status}"
        )


@app.command()
def mark_false_positive(finding_id: str):
    """Review action: mark a finding as false positive; the source-item /
    watchlist pair is suppressed in future runs (req. 5)."""
    _, session = _session()
    try:
        finding = findings_mod.mark_false_positive(session, finding_id)
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    session.commit()
    typer.echo(f"{finding.finding_id} marked false_positive; pair suppressed")


if __name__ == "__main__":
    app()
