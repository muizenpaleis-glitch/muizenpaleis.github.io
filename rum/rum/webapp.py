"""Minimal server-rendered web UI (req. 8 phase 2, simplified) to test
every function: watchlist import & CRUD, collection runs, findings with
filters, evidence snapshot view, review actions, and CSV export.

Run with:  rum serve   (or: uvicorn rum.webapp:app)

Demo mode: the dashboard can seed sample watchlist entries and the run
form can use bundled fake setlist.fm responses, so the full pipeline is
testable without an API key or network access.
"""

from __future__ import annotations

import dataclasses
import html
import json
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from . import demodata, enrich as enrich_mod, findings as findings_mod, watchlist as watchlist_mod
from .collectors import REGISTRY
from .config import Config
from .db import init_db, make_engine, make_session_factory
from .export import export_findings
from .findings import week_period
from .models import (
    ENTITY_TYPES,
    USAGE_TYPES,
    CollectorRun,
    ExportBatch,
    Finding,
    WatchlistEntry,
)
from .runner import run_collectors


def e(value) -> str:
    return html.escape(str(value if value is not None else ""))


def redirect(path: str, msg: str) -> RedirectResponse:
    return RedirectResponse(f"{path}?flash={quote(msg)}", status_code=303)


STYLE = """
body { font-family: system-ui, sans-serif; margin: 0; background: #f5f6f8; color: #1c2330; }
nav { background: #1c2d4f; padding: 0.7rem 1.2rem; }
nav a { color: #cdd9f4; margin-right: 1.2rem; text-decoration: none; font-weight: 600; }
nav a:hover { color: #fff; }
main { max-width: 1200px; margin: 1.2rem auto; padding: 0 1rem; }
h1 { font-size: 1.4rem; } h2 { font-size: 1.1rem; margin-top: 1.6rem; }
table { border-collapse: collapse; width: 100%; background: #fff; font-size: 0.85rem; }
th, td { border: 1px solid #dde2ea; padding: 0.35rem 0.55rem; text-align: left; vertical-align: top; }
th { background: #e8edf5; }
form.inline { display: inline; }
.card { background: #fff; border: 1px solid #dde2ea; border-radius: 6px; padding: 1rem; margin-bottom: 1rem; }
.cards { display: flex; gap: 1rem; flex-wrap: wrap; }
.cards .card { flex: 1; min-width: 160px; text-align: center; }
.card .num { font-size: 1.8rem; font-weight: 700; }
button, input[type=submit] { background: #1c2d4f; color: #fff; border: 0; padding: 0.35rem 0.8rem; border-radius: 4px; cursor: pointer; }
button.danger { background: #8f2f2f; }
input, select { padding: 0.3rem; border: 1px solid #c5ccd8; border-radius: 4px; }
label { margin-right: 0.8rem; }
pre { background: #10141c; color: #d7e0ef; padding: 0.8rem; border-radius: 6px; overflow-x: auto; font-size: 0.78rem; max-height: 480px; }
.badge { padding: 0.1rem 0.45rem; border-radius: 10px; font-size: 0.75rem; font-weight: 600; }
.b-new { background: #dbeafe; } .b-exported { background: #dcfce7; }
.b-false_positive { background: #fee2e2; } .b-reviewed { background: #fef9c3; }
.b-review { background: #ffedd5; }
.flash { background: #ecfdf3; border: 1px solid #9ad8b1; padding: 0.6rem 0.9rem; border-radius: 6px; margin-bottom: 1rem; white-space: pre-wrap; }
.muted { color: #68748a; font-size: 0.8rem; }
"""

NAV = """
<nav>
  <a href="/">Dashboard</a>
  <a href="/watchlist">Watchlist</a>
  <a href="/run">Run collectors</a>
  <a href="/findings">Findings</a>
  <a href="/runs">Run log</a>
  <a href="/export">Export</a>
</nav>
"""


def page(title: str, body: str, flash: str | None = None) -> HTMLResponse:
    flash_html = f'<div class="flash">{e(flash)}</div>' if flash else ""
    return HTMLResponse(
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{e(title)} - RUM</title><style>{STYLE}</style></head>"
        f"<body>{NAV}<main><h1>{e(title)}</h1>{flash_html}{body}</main></body></html>"
    )


def status_badge(f: Finding) -> str:
    badge = f'<span class="badge b-{e(f.status)}">{e(f.status)}</span>'
    if f.needs_review:
        badge += ' <span class="badge b-review">needs review</span>'
    return badge


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config.from_env()
    engine = make_engine(config.database_url)
    init_db(engine)
    session_factory = make_session_factory(engine)

    app = FastAPI(title="RUM")
    app.state.config = config
    app.state.session_factory = session_factory

    def db():
        return session_factory()

    # -- dashboard ---------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, flash: str | None = None):
        with db() as s:
            wl_counts = {
                t: s.query(WatchlistEntry).filter_by(entity_type=t).count()
                for t in ENTITY_TYPES
            }
            finding_count = s.query(Finding).count()
            review_count = (
                s.query(Finding)
                .filter(Finding.needs_review.is_(True), Finding.status == "new")
                .count()
            )
            run_count = s.query(CollectorRun).count()
        cards = "".join(
            f'<div class="card"><div class="num">{n}</div>{e(label)}</div>'
            for label, n in [
                ("works", wl_counts["work"]),
                ("AV productions", wl_counts["av_production"]),
                ("performers", wl_counts["performer"]),
                ("findings", finding_count),
                ("awaiting review", review_count),
                ("collector runs", run_count),
            ]
        )
        chart_html = _findings_per_market_chart()
        body = f"""
        <div class="cards">{cards}</div>
        <div class="card">
          <h2 style="margin-top:0">Quick test setup</h2>
          <p class="muted">Seeds 4 demo watchlist entries (a work, an AV production,
          a performer with a known-works subset, one without). Then use
          <b>Run collectors</b> with demo mode checked - no API key or network needed.</p>
          <form method="post" action="/demo/seed"><button>Seed demo watchlist</button></form>
        </div>
        <div class="card">
          <h2 style="margin-top:0">Findings per market per week</h2>
          {chart_html}
        </div>
        """
        return page("Dashboard", body, flash)

    def _findings_per_market_chart() -> str:
        """Server-rendered chart (req. 8 phase 2): counts per market for
        the most recent 8 weeks with findings."""
        with db() as s:
            findings = s.query(Finding.period, Finding.market).all()
        counts: dict[tuple[str, str], int] = {}
        for period, market in findings:
            if "-W" in period:
                week = period
            else:
                try:
                    week = week_period(date.fromisoformat(period))
                except ValueError:
                    continue
            counts[(week, market)] = counts.get((week, market), 0) + 1
        if not counts:
            return '<p class="muted">No findings yet.</p>'
        weeks = sorted({w for w, _ in counts}, reverse=True)[:8]
        markets = sorted({m for _, m in counts})
        peak = max(counts.values())
        header = "".join(f"<th>{e(m)}</th>" for m in markets)
        rows = ""
        for week in weeks:
            cells = ""
            for m in markets:
                n = counts.get((week, m), 0)
                bar = (
                    f'<div style="background:#4a6fb5;height:8px;'
                    f'width:{max(4, int(100 * n / peak))}%"></div>' if n else ""
                )
                cells += f"<td>{n or ''}{bar}</td>"
            rows += f"<tr><th>{e(week)}</th>{cells}</tr>"
        return f"<table><tr><th>Week</th>{header}</tr>{rows}</table>"

    @app.post("/demo/seed")
    def demo_seed():
        with db() as s:
            created = demodata.seed_demo_watchlist(s)
        msg = (
            f"created demo entries: {', '.join(created)}"
            if created else "demo entries already present"
        )
        return redirect("/", msg)

    # -- watchlist -----------------------------------------------------------
    @app.get("/watchlist", response_class=HTMLResponse)
    def watchlist_page(entity_type: str | None = None, flash: str | None = None):
        with db() as s:
            entries = watchlist_mod.list_entries(s, entity_type or None)
            rows = ""
            for entry in entries:
                markets = ", ".join(entry.country_filter) if entry.country_filter else "all"
                toggle = "Deactivate" if entry.active else "Activate"
                rows += f"""<tr>
                  <td><a href="/watchlist/{e(entry.id)}">{e(entry.id)}</a></td>
                  <td>{e(entry.entity_type)}</td><td>{e(entry.display_name)}</td>
                  <td>{e(entry.priority)}</td>
                  <td>{"yes" if entry.active else "no"}</td><td>{e(markets)}</td>
                  <td>
                    <form class="inline" method="post" action="/watchlist/{e(entry.id)}/toggle"><button>{toggle}</button></form>
                    <form class="inline" method="post" action="/watchlist/{e(entry.id)}/delete"
                          onsubmit="return confirm('Delete {e(entry.id)}?')"><button class="danger">Delete</button></form>
                  </td></tr>"""
        options = "".join(
            f'<option value="{t}" {"selected" if t == entity_type else ""}>{t}</option>'
            for t in ENTITY_TYPES
        )
        body = f"""
        <div class="card">
          <h2 style="margin-top:0">Import CSV</h2>
          <p class="muted">Templates: semicolon-delimited UTF-8, multi-values with "|",
          recordings as ISRC~title~artist, writers as Name~IPI. Invalid rows are
          reported with reasons; valid rows become active.</p>
          <form method="post" action="/watchlist/import" enctype="multipart/form-data">
            <label>Entity type <select name="entity_type">{"".join(f'<option value="{t}">{t}</option>' for t in ENTITY_TYPES)}</select></label>
            <label>File <input type="file" name="file" accept=".csv" required></label>
            <button>Import</button>
          </form>
        </div>
        <form method="get" action="/watchlist">
          <label>Filter <select name="entity_type"><option value="">all types</option>{options}</select></label>
          <button>Apply</button>
        </form><br>
        <table><tr><th>ID</th><th>Type</th><th>Name</th><th>Priority</th><th>Active</th><th>Markets</th><th>Actions</th></tr>{rows}</table>
        """
        return page("Watchlist", body, flash)

    @app.post("/watchlist/import")
    async def watchlist_import(entity_type: str = Form(...), file: UploadFile = Form(...)):
        content = await file.read()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            with db() as s:
                report = watchlist_mod.import_csv(s, entity_type, tmp_path)
                s.commit()
            msg = report.summary()
        except ValueError as exc:
            msg = f"import failed: {exc}"
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        return redirect("/watchlist", msg)

    @app.get("/watchlist/{watchlist_id}", response_class=HTMLResponse)
    def watchlist_detail(watchlist_id: str):
        with db() as s:
            entry = s.get(WatchlistEntry, watchlist_id)
            if entry is None:
                return page("Not found", f"<p>No watchlist entry {e(watchlist_id)}.</p>")
            detail: dict = {
                "entity_type": entry.entity_type,
                "display_name": entry.display_name,
                "priority": entry.priority,
                "active": entry.active,
                "country_filter": entry.country_filter,
                "notes": entry.notes,
            }
            if entry.work:
                detail.update(
                    iswc=entry.work.iswc,
                    alternative_titles=entry.work.alternative_titles,
                    writers=entry.work.writers,
                    recordings=[
                        {"isrc": r.isrc, "title": r.recording_title, "artist": r.main_artist}
                        for r in entry.work.recordings
                    ],
                )
            if entry.av_production:
                av = entry.av_production
                detail.update(
                    original_title=av.original_title, production_year=av.production_year,
                    type=av.production_type, imdb_id=av.imdb_id, tmdb_id=av.tmdb_id,
                    eidr=av.eidr, country_of_origin=av.country_of_origin,
                    contained_work_ids=av.contained_work_ids,
                )
            if entry.performer:
                p = entry.performer
                detail.update(
                    aliases=p.aliases, musicbrainz_id=p.musicbrainz_id,
                    setlistfm_id=p.setlistfm_id, known_work_ids=p.known_work_ids,
                )
            findings_count = s.query(Finding).filter_by(watchlist_id=watchlist_id).count()
        body = f"""
        <pre>{e(json.dumps(detail, indent=2, ensure_ascii=False))}</pre>
        <p><a href="/findings?watchlist_id={e(watchlist_id)}">{findings_count} finding(s) for this entry</a></p>
        """
        return page(f"Watchlist entry {watchlist_id}", body)

    @app.post("/watchlist/{watchlist_id}/toggle")
    def watchlist_toggle(watchlist_id: str):
        with db() as s:
            entry = s.get(WatchlistEntry, watchlist_id)
            msg = f"no entry {watchlist_id}"
            if entry is not None:
                watchlist_mod.set_active(s, watchlist_id, not entry.active)
                s.commit()
                msg = f"{watchlist_id} is now {'active' if entry.active else 'inactive'}"
        return redirect("/watchlist", msg)

    @app.post("/watchlist/{watchlist_id}/delete")
    def watchlist_delete(watchlist_id: str):
        with db() as s:
            try:
                watchlist_mod.delete_entry(s, watchlist_id)
                s.commit()
                msg = f"deleted {watchlist_id}"
            except KeyError as exc:
                msg = str(exc)
        return redirect("/watchlist", msg)

    # -- collection runs -----------------------------------------------------
    @app.get("/run", response_class=HTMLResponse)
    def run_form(flash: str | None = None):
        default_since = (date.today() - timedelta(days=30)).isoformat()
        keys = {
            "SETLISTFM_API_KEY": config.setlistfm_api_key,
            "YOUTUBE_API_KEY": config.youtube_api_key,
            "TMDB_API_KEY": config.tmdb_api_key,
        }
        key_state = ", ".join(
            f"{name} {'set' if value else 'NOT set'}" for name, value in keys.items()
        )
        module_options = "".join(
            f'<option value="{m}">{m}</option>' for m in sorted(REGISTRY)
        )
        body = f"""
        <div class="card">
          <form method="post" action="/run">
            <label>Module <select name="module">
              <option value="">all enabled modules</option>{module_options}
            </select></label>
            <label>Market (ISO code, empty = all) <input name="market" size="4" maxlength="2"></label>
            <label>Since <input type="date" name="since" value="{default_since}"></label>
            <label><input type="checkbox" name="demo" value="1" checked>
              demo mode (bundled fake API responses, no network)</label>
            <button>Start run</button>
          </form>
          <p class="muted">{key_state}. Uncheck demo mode to hit the real APIs
          (rate-limited to 1 request / {config.rate_limit_seconds:g}s per domain).
          The charts module needs a market (a chart is per country).</p>
        </div>
        <div class="card">
          <h2 style="margin-top:0">MusicBrainz enrichment</h2>
          <p class="muted">Not a usage source: resolves performer aliases and
          ISRC canonical titles to strengthen matching (req. 4 source #5).</p>
          <form method="post" action="/enrich">
            <label><input type="checkbox" name="demo" value="1" checked> demo mode</label>
            <button>Run enrichment</button>
          </form>
        </div>
        """
        return page("Run collectors", body, flash)

    @app.post("/enrich")
    def enrich_post(demo: str = Form("")):
        factory = demodata.demo_http_client_factory if demo else None
        with db() as s:
            messages = enrich_mod.enrich_all(s, config, client_factory=factory)
            s.commit()
        return redirect("/run", "\n".join(messages) or "enrichment: nothing to add")

    @app.post("/run")
    def run_post(
        module: str = Form(""),
        market: str = Form(""),
        since: str = Form(""),
        demo: str = Form(""),
    ):
        since_date = datetime.strptime(since, "%Y-%m-%d").date() if since else None
        run_config = config
        factory = None
        if demo:
            factory = demodata.demo_http_client_factory
            run_config = dataclasses.replace(
                config,
                setlistfm_api_key="demo-key",
                youtube_api_key="demo-key",
                tmdb_api_key="demo-key",
                rate_limit_seconds=0.0,
                # A chart is per country; give the demo a market list.
                module_markets={**config.module_markets, "charts": ["DE"]},
            )
        with db() as s:
            report = run_collectors(
                s, run_config, modules=[module] if module else None,
                markets=[market.upper()] if market.strip() else None,
                since=since_date, http_client_factory=factory,
            )
        return redirect("/run", report.summary())

    @app.get("/runs", response_class=HTMLResponse)
    def runs_page():
        with db() as s:
            runs = (
                s.query(CollectorRun).order_by(CollectorRun.started_at.desc()).limit(50).all()
            )
            rows = "".join(
                f"""<tr><td>{r.id}</td><td>{e(r.module)}</td><td>{e(r.market or "all")}</td>
                <td>{e(r.started_at)}</td><td>{r.items_checked}</td><td>{r.findings_new}</td>
                <td>{r.findings_duplicate}</td><td>{r.findings_suppressed}</td>
                <td>{"ok" if r.ok else e("; ".join(r.errors))}</td></tr>"""
                for r in runs
            )
        body = f"""<table><tr><th>#</th><th>Module</th><th>Market</th><th>Started</th>
        <th>Items checked</th><th>New</th><th>Duplicates</th><th>Suppressed</th><th>Result</th></tr>{rows}</table>"""
        return page("Run log", body)

    # -- findings --------------------------------------------------------------
    def _filtered_findings(s, market, usage_type, status, min_confidence,
                            watchlist_id, needs_review, period_from, period_to):
        query = s.query(Finding)
        if market:
            query = query.filter(Finding.market == market.upper())
        if usage_type:
            query = query.filter(Finding.usage_type == usage_type)
        if status:
            query = query.filter(Finding.status == status)
        if min_confidence:
            query = query.filter(Finding.confidence >= float(min_confidence))
        if watchlist_id:
            query = query.filter(Finding.watchlist_id == watchlist_id)
        if needs_review:
            query = query.filter(Finding.needs_review.is_(True))
        if period_from:
            query = query.filter(Finding.period >= period_from)
        if period_to:
            query = query.filter(Finding.period <= period_to)
        return query.order_by(Finding.period.desc()).limit(500).all()

    @app.get("/findings", response_class=HTMLResponse)
    def findings_page(
        market: str = "", usage_type: str = "", status: str = "",
        min_confidence: str = "", watchlist_id: str = "", needs_review: str = "",
        period_from: str = "", period_to: str = "", flash: str | None = None,
    ):
        with db() as s:
            findings = _filtered_findings(
                s, market, usage_type, status, min_confidence,
                watchlist_id, needs_review, period_from, period_to,
            )
            rows = "".join(
                f"""<tr>
                <td><a href="/findings/{e(f.finding_id)}">{e(f.finding_id[:8])}</a></td>
                <td>{e(f.period)}</td><td>{e(f.market)}</td><td>{e(f.usage_type)}</td>
                <td><a href="/watchlist/{e(f.watchlist_id)}">{e(f.watchlist_id)}</a></td>
                <td>L{f.match_level} / {f.confidence}</td><td>{status_badge(f)}</td>
                <td>{e(f.source_module)}</td></tr>"""
                for f in findings
            )
        usage_options = "".join(
            f'<option value="{t}" {"selected" if t == usage_type else ""}>{t}</option>'
            for t in USAGE_TYPES
        )
        status_options = "".join(
            f'<option value="{t}" {"selected" if t == status else ""}>{t}</option>'
            for t in ("new", "reviewed", "false_positive", "exported")
        )
        body = f"""
        <div class="card"><form method="get" action="/findings">
          <label>Market <input name="market" size="4" value="{e(market)}"></label>
          <label>Usage <select name="usage_type"><option value="">all</option>{usage_options}</select></label>
          <label>Status <select name="status"><option value="">all</option>{status_options}</select></label>
          <label>Min conf. <input name="min_confidence" size="4" value="{e(min_confidence)}"></label>
          <label>Watchlist ID <input name="watchlist_id" size="10" value="{e(watchlist_id)}"></label>
          <label>From <input type="date" name="period_from" value="{e(period_from)}"></label>
          <label>To <input type="date" name="period_to" value="{e(period_to)}"></label>
          <label><input type="checkbox" name="needs_review" value="1" {"checked" if needs_review else ""}> needs review</label>
          <button>Filter</button>
        </form></div>
        <table><tr><th>ID</th><th>Period</th><th>Market</th><th>Usage</th>
        <th>Watchlist</th><th>Match</th><th>Status</th><th>Source</th></tr>{rows}</table>
        <p class="muted">{len(findings)} finding(s) shown (max 500).</p>
        """
        return page("Findings", body, flash)

    @app.get("/findings/{finding_id}", response_class=HTMLResponse)
    def finding_detail(finding_id: str, flash: str | None = None):
        with db() as s:
            f = s.get(Finding, finding_id)
            if f is None:
                return page("Not found", f"<p>No finding {e(finding_id)}.</p>")
            evidence = "(evidence snapshot file missing)"
            path = Path(f.evidence_snapshot)
            if path.exists():
                evidence = path.read_text(encoding="utf-8", errors="replace")
            fields = {
                "finding_id": f.finding_id, "watchlist_id": f.watchlist_id,
                "entity_type": f.entity_type, "usage_type": f.usage_type,
                "market": f.market, "occurred_at": str(f.occurred_at),
                "period": f.period, "source_module": f.source_module,
                "source_url": f.source_url, "source_item_id": f.source_item_id,
                "captured_at": str(f.captured_at),
                "match_level": f.match_level, "confidence": f.confidence,
                "status": f.status, "needs_review": f.needs_review,
                "export_batch_id": f.export_batch_id,
                "evidence_snapshot": f.evidence_snapshot,
            }
            rows = "".join(
                f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in fields.items()
            )
            body = f"""
            <p>{status_badge(f)}</p>
            <table>{rows}</table>
            <h2>Matched strings (match audit)</h2>
            <pre>{e(json.dumps(f.matched_strings, indent=2, ensure_ascii=False))}</pre>
            <h2>Details</h2>
            <pre>{e(json.dumps(f.details, indent=2, ensure_ascii=False))}</pre>
            <h2>Review actions</h2>
            <form class="inline" method="post" action="/findings/{e(f.finding_id)}/reviewed">
              <button>Confirm (mark reviewed)</button></form>
            <form class="inline" method="post" action="/findings/{e(f.finding_id)}/false-positive">
              <button class="danger">Mark false positive (suppress pair)</button></form>
            <h2>Evidence snapshot</h2>
            <pre>{e(evidence)}</pre>
            """
        return page(f"Finding {finding_id[:8]}", body, flash)

    @app.post("/findings/{finding_id}/false-positive")
    def finding_false_positive(finding_id: str):
        with db() as s:
            try:
                findings_mod.mark_false_positive(s, finding_id)
                s.commit()
                msg = "marked false positive; this source/watchlist pair is suppressed in future runs"
            except KeyError as exc:
                msg = str(exc)
        return redirect(f"/findings/{finding_id}", msg)

    @app.post("/findings/{finding_id}/reviewed")
    def finding_reviewed(finding_id: str):
        with db() as s:
            f = s.get(Finding, finding_id)
            msg = f"no finding {finding_id}"
            if f is not None:
                f.status = "reviewed"
                s.commit()
                msg = "marked reviewed"
        return redirect(f"/findings/{finding_id}", msg)

    # -- export ---------------------------------------------------------------
    @app.get("/export", response_class=HTMLResponse)
    def export_page():
        with db() as s:
            batches = (
                s.query(ExportBatch).order_by(ExportBatch.created_at.desc()).limit(20).all()
            )
            rows = "".join(
                f"""<tr><td>{e(b.id[:8])}</td><td>{e(b.created_at)}</td>
                <td>{b.row_count}</td><td>{e(json.dumps(b.filters))}</td></tr>"""
                for b in batches
            )
        usage_options = "".join(f'<option value="{t}">{t}</option>' for t in USAGE_TYPES)
        body = f"""
        <div class="card"><form method="get" action="/export.csv">
          <label>Market <input name="market" size="4"></label>
          <label>Usage <select name="usage_type"><option value="">all</option>{usage_options}</select></label>
          <label>Min conf. <input name="min_confidence" size="4"></label>
          <label>From <input type="date" name="period_from"></label>
          <label>To <input type="date" name="period_to"></label>
          <label><input type="checkbox" name="no_mark" value="1"> do not mark as exported</label>
          <button>Download CSV</button>
        </form>
        <p class="muted">Semicolon-delimited UTF-8 with BOM (opens cleanly in Excel).
        Unless "do not mark" is checked, exported findings get status
        <b>exported</b> and an export batch ID.</p></div>
        <h2>Recent export batches</h2>
        <table><tr><th>Batch</th><th>Created</th><th>Rows</th><th>Filters</th></tr>{rows}</table>
        """
        return page("Export", body)

    @app.get("/export.csv")
    def export_csv(
        market: str = "", usage_type: str = "", min_confidence: str = "",
        period_from: str = "", period_to: str = "", no_mark: str = "",
    ):
        out = Path(tempfile.mkdtemp(prefix="rum-export-")) / (
            f"findings_{date.today().isoformat()}.csv"
        )
        with db() as s:
            export_findings(
                s, out,
                market=market or None,
                usage_type=usage_type or None,
                min_confidence=float(min_confidence) if min_confidence else None,
                period_from=period_from or None,
                period_to=period_to or None,
                mark_exported=not no_mark,
            )
            s.commit()
        return FileResponse(out, filename=out.name, media_type="text/csv")

    return app


def __getattr__(name):
    # Lazy so "uvicorn rum.webapp:app" works without importing side effects.
    if name == "app":
        return create_app()
    raise AttributeError(name)
