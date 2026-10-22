"""`gauntlet serve` — a local, read-only dashboard over the run database.

stdlib only (http.server + sqlite3). It binds to localhost by default and
never writes: every page is rendered from the same SQLite file the CLI uses,
so it can stay open on a second monitor while flows run — the runs page
reloads itself when a new run lands.

Routes
  /                         runs: trend, compare form, history table
  /runs/<id>                one run's full report (`latest`, `latest~N` work)
  /runs/<id>/log/<step>     a step's log, violation lines highlighted
  /diff?a=<id>&b=<id>       run-to-run diff
  /stats?flow=<name>&n=20   per-step stability
  /api/runs, /api/runs/<id>, /api/diff?a=&b=, /api/stats   JSON
"""
from __future__ import annotations

import json
import re
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import __version__
from .diff import diff_runs
from .models import StepResult
from .stats import compute_stats
from .store import RunNotFoundError, RunStore
from .ui.pages import FILTER_SCRIPT, diff_body, log_body, page, run_body, runs_body, stats_body

MAX_LOG_LINES = 20_000
MAX_LOG_BYTES = 8 * 1024 * 1024

# Reload the runs page when the newest run id changes. Cheap: one tiny JSON
# request every few seconds, and only while the tab is visible.
LIVE_JS = r"""
(function(){
  var seen=document.body.getAttribute('data-latest');
  setInterval(function(){
    if(document.visibilityState!=='visible') return;
    fetch('/api/runs?limit=1').then(function(r){return r.json();}).then(function(d){
      var id=d.runs&&d.runs[0]&&d.runs[0].run_id;
      if(id&&id!==seen) location.reload();
    }).catch(function(){});
  },4000);
})();
"""


def run_href(run_id: str) -> str:
    return f"/runs/{quote(run_id)}"


def _nav(current: str) -> list[tuple[str, str, bool]]:
    return [
        ("Runs", "/", current == "runs"),
        ("Latest", "/runs/latest", current == "latest"),
        ("Diff", "/diff?a=latest~1&b=latest", current == "diff"),
        ("Stability", "/stats", current == "stats"),
    ]


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = f"gauntlet/{__version__}"
    db_path: Path = Path("runs/gauntlet.db")

    # ------------------------------------------------------------ plumbing

    def log_message(self, fmt: str, *args) -> None:  # quieter than the default
        sys.stderr.write(f"  {self.command} {self.path} → {args[1] if len(args) > 1 else ''}\n")

    def _send(self, status: int, body: str, content_type: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _html(self, body: str, status: int = 200) -> None:
        self._send(status, body, "text/html")

    def _json(self, payload: object, status: int = 200) -> None:
        self._send(status, json.dumps(payload, indent=2), "application/json")

    def _not_found(self, message: str, api: bool) -> None:
        if api:
            self._json({"error": message}, HTTPStatus.NOT_FOUND)
            return
        body = (
            '<section class="card"><div class="empty" style="padding:56px 18px">'
            f"<b>Not found</b>{_esc(message)}<br><br><a href=\"/\">← all runs</a></div></section>"
        )
        self._html(page("not found — gauntlet", body, nav=_nav(""), home="/", subtitle="dashboard"), 404)

    def do_HEAD(self) -> None:  # noqa: N802 — http.server naming
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        query = {k: v[-1] for k, v in parse_qs(url.query).items()}
        path = unquote(url.path).rstrip("/") or "/"
        api = path.startswith("/api/")
        routes = (
            (r"/", self.page_runs),
            (r"/runs/(?P<run_id>[^/]+)", self.page_run),
            (r"/runs/(?P<run_id>[^/]+)/log/(?P<step_id>[^/]+)", self.page_log),
            (r"/diff", self.page_diff),
            (r"/stats", self.page_stats),
            (r"/api/runs", self.api_runs),
            (r"/api/runs/(?P<run_id>[^/]+)", self.api_run),
            (r"/api/diff", self.api_diff),
            (r"/api/stats", self.api_stats),
        )
        for pattern, handler in routes:
            match = re.fullmatch(pattern, path)
            if match:
                try:
                    with RunStore(self.db_path) as store:
                        handler(store, query, **match.groupdict())
                except RunNotFoundError as exc:
                    self._not_found(str(exc), api)
                except BrokenPipeError:
                    pass
                return
        self._not_found(f"no page at {path}", api)

    # --------------------------------------------------------------- pages

    def page_runs(self, store: RunStore, query: dict) -> None:
        flow = query.get("flow") or None
        rows = store.list_runs(_int(query.get("n"), 40), flow_name=flow)
        latest = store.list_runs(1)
        body = runs_body(rows, store.flows(), flow, run_href)
        html = page("runs — gauntlet", body, nav=_nav("runs"), live=True, home="/",
                    subtitle="dashboard", scripts=LIVE_JS)
        html = html.replace("<body>", f'<body data-latest="{_esc(latest[0]["run_id"]) if latest else ""}">', 1)
        self._html(html)

    def page_run(self, store: RunStore, query: dict, run_id: str) -> None:
        record = store.load(run_id)
        rows = store.list_runs(500, flow_name=record.flow_name)
        ids = [r["run_id"] for r in rows]
        idx = ids.index(record.run_id) if record.run_id in ids else -1
        older = ids[idx + 1] if 0 <= idx < len(ids) - 1 else None
        newer = ids[idx - 1] if idx > 0 else None
        actions = ['<div style="display:flex;gap:8px;flex-wrap:wrap">']
        if older:
            actions.append(f'<a class="btn" href="/diff?a={quote(older)}&amp;b={quote(record.run_id)}">Diff vs previous run</a>')
            actions.append(f'<a class="btn ghost" href="{run_href(older)}">← older</a>')
        if newer:
            actions.append(f'<a class="btn ghost" href="{run_href(newer)}">newer →</a>')
        actions.append('<a class="btn ghost" href="/">all runs</a></div>')

        def log_href(result: StepResult) -> str | None:
            if not result.log_path:
                return None
            return f"/runs/{quote(record.run_id)}/log/{quote(result.step_id)}"

        body = run_body(record, log_href, actions="".join(actions))
        current = "latest" if run_id == "latest" else ""
        self._html(page(f"{record.status} · {record.run_id} — gauntlet", body, nav=_nav(current),
                        home="/", subtitle="dashboard", scripts=FILTER_SCRIPT))

    def page_log(self, store: RunStore, query: dict, run_id: str, step_id: str) -> None:
        record = store.load(run_id)
        result = record.results.get(step_id)
        if result is None or not result.log_path:
            self._not_found(f"no log for step {step_id!r} in {record.run_id}", api=False)
            return
        log = self._contained(Path(result.log_path))
        if log is None or not log.is_file():
            self._not_found(
                f"the log for {step_id} is no longer on disk (the database outlives raw logs)", api=False
            )
            return
        lines, truncated, size = [], False, 0
        with open(log, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                size += len(line)
                if len(lines) >= MAX_LOG_LINES or size > MAX_LOG_BYTES:
                    truncated = True
                    break
                lines.append(line)
        body = log_body(record, result, lines, truncated, run_href(record.run_id))
        self._html(page(f"{step_id} log · {record.run_id} — gauntlet", body, nav=_nav(""), home="/",
                        subtitle="log"))

    def page_diff(self, store: RunStore, query: dict) -> None:
        a = store.load(query.get("a", "latest~1"))
        b = store.load(query.get("b", "latest"))
        body = diff_body(diff_runs(a, b), a, b, run_href)
        self._html(page(f"diff {a.run_id} → {b.run_id} — gauntlet", body, nav=_nav("diff"), home="/",
                        subtitle="dashboard"))

    def page_stats(self, store: RunStore, query: dict) -> None:
        flows = store.flows()
        flow = query.get("flow") or (flows[0] if flows else "")
        runs = store.step_history(flow, _int(query.get("n"), 20)) if flow else []
        body = stats_body(flow, len(runs), compute_stats(runs), flows)
        self._html(page(f"stability · {flow} — gauntlet", body, nav=_nav("stats"), home="/",
                        subtitle="dashboard"))

    # ----------------------------------------------------------------- api

    def api_runs(self, store: RunStore, query: dict) -> None:
        self._json({"runs": store.list_runs(_int(query.get("limit"), 20), flow_name=query.get("flow"))})

    def api_run(self, store: RunStore, query: dict, run_id: str) -> None:
        self._json(store.load(run_id).to_dict())

    def api_diff(self, store: RunStore, query: dict) -> None:
        from .cli import _diff_json

        a = store.load(query.get("a", "latest~1"))
        b = store.load(query.get("b", "latest"))
        self._json(_diff_json(diff_runs(a, b)))

    def api_stats(self, store: RunStore, query: dict) -> None:
        flows = store.flows()
        flow = query.get("flow") or (flows[0] if flows else "")
        runs = store.step_history(flow, _int(query.get("n"), 20)) if flow else []
        self._json({
            "flow": flow,
            "runs": [r.run_id for r in runs],
            "steps": [
                {"step_id": s.step_id, "history": [x.value if x else None for x in s.statuses],
                 "pass_rate": s.pass_rate, "flips": s.flips, "flaky": s.flaky,
                 "mean_duration_s": s.mean_duration, "p95_duration_s": s.p95_duration,
                 "verdict": s.verdict, "last_failure": s.last_failure}
                for s in compute_stats(runs)
            ],
        })  # fmt: skip

    # -------------------------------------------------------------- safety

    def _contained(self, log: Path) -> Path | None:
        """Only serve files inside the runs directory — never an arbitrary path
        that happens to be stored in the database."""
        root = self.db_path.resolve().parent
        candidate = log if log.is_absolute() else Path.cwd() / log
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except (OSError, ValueError):
            return None
        return resolved


def _int(value: str | None, default: int) -> int:
    try:
        return max(1, min(int(value), 1000)) if value else default
    except ValueError:
        return default


def _esc(text: str) -> str:
    from html import escape

    return escape(str(text), quote=True)


def make_server(db_path: Path, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """Build (but don't start) the dashboard server. Port 0 picks a free one."""
    handler = type("BoundDashboardHandler", (DashboardHandler,), {"db_path": Path(db_path)})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def serve(db_path: Path, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> int:
    try:
        server = make_server(db_path, host, port)
    except OSError as exc:
        print(f"error: cannot listen on {host}:{port} — {exc.strerror or exc}", file=sys.stderr)
        return 2
    url = f"http://{host if host not in ('0.0.0.0', '::') else '127.0.0.1'}:{server.server_address[1]}/"
    print(f"gauntlet {__version__} dashboard → {url}")
    print(f"  database: {db_path}")
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("  ! listening beyond localhost: anyone who can reach this port can read your run logs")
    print("  ctrl-c to stop")
    if open_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        server.server_close()
    return 0
