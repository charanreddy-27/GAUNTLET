"""End to end through the real CLI and the dashboard server — no mocks."""
import json
import threading
import urllib.error
import urllib.request

import pytest

from gauntlet import __version__
from gauntlet.cli import main
from gauntlet.server import make_server
from probe import cmd


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A scratch project with runs/ under tmp and a two-step flow
    (build → check). Tests break `check` by rewriting its command."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GAUNTLET_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    flow = tmp_path / "flow.yaml"
    flow.write_text(
        "name: tiny\n"
        "steps:\n"
        f"  - id: build\n    cmd: '{cmd('echo', 'building')}'\n"
        f"  - id: check\n    cmd: '{cmd('ok')}'\n    depends_on: [build]\n"
    )
    return tmp_path, flow


def test_run_report_diff_graph_stats(workspace, capsys):
    tmp, flow = workspace
    assert main(["run", str(flow), "--junit", "out/j.xml", "--markdown", "out/s.md", "--html", "out/r.html"]) == 0
    assert (tmp / "out/j.xml").read_text().startswith("<?xml")
    assert "GAUNTLET · tiny" in (tmp / "out/s.md").read_text()
    html = (tmp / "out/r.html").read_text()
    assert 'href="../runs/' in html  # log links resolve from the report's folder

    # second run, then break `check` and run a third
    assert main(["run", str(flow)]) == 0
    flow.write_text(flow.read_text().replace(cmd("ok"), cmd("fail")))
    assert main(["run", str(flow)]) == 1
    capsys.readouterr()

    assert main(["diff", "latest~1", "latest"]) == 1
    out = capsys.readouterr().out
    assert "NEW FAILURES (1)" in out and "check" in out
    assert main(["diff", "latest~2", "latest~1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"].startswith("CLEAN")

    assert main(["report", "latest", "--markdown", "-"]) == 0
    assert capsys.readouterr().out.startswith("## GAUNTLET · tiny — ❌ FAIL")

    assert main(["stats"]) == 0
    stats = capsys.readouterr().out
    assert "✓✓✗" in stats and "needs an owner: check" in stats

    assert main(["graph", str(flow), "--format", "mermaid"]) == 0
    assert "n_build --> n_check" in capsys.readouterr().out

    assert main(["report", "latest~9"]) == 2
    assert "no run at 'latest~9'" in capsys.readouterr().err


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def _get(base, path):
    try:
        with urllib.request.urlopen(base + path) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


def test_dashboard_pages_api_and_log_containment(workspace, capsys):
    tmp, flow = workspace
    assert main(["run", str(flow)]) == 0
    assert main(["run", str(flow)]) == 0
    capsys.readouterr()

    server = make_server(tmp / "runs" / "gauntlet.db", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, body = _get(base, "/")
        assert status == 200 and "Compare two runs" in body and 'class="chart trend"' in body
        status, body = _get(base, "/runs/latest")
        assert status == 200 and 'class="chart dag"' in body and "Diff vs previous run" in body
        status, body = _get(base, "/runs/latest/log/build")
        assert status == 200 and "building" in body
        status, body = _get(base, "/diff?a=latest~1&b=latest")
        assert status == 200 and "NO REGRESSION" in body
        status, body = _get(base, "/stats")
        assert status == 200 and "Step stability" in body

        status, body = _get(base, "/api/runs?limit=1")
        assert status == 200 and len(json.loads(body)["runs"]) == 1
        status, body = _get(base, "/api/diff")
        assert json.loads(body)["new_failures"] == []
        status, body = _get(base, "/api/stats")
        assert [s["step_id"] for s in json.loads(body)["steps"]] == ["build", "check"]

        assert _get(base, "/runs/nope")[0] == 404
        assert _get(base, "/api/runs/nope")[0] == 404
        assert _get(base, "/runs/latest/log/..%2F..%2F..%2Fetc%2Fpasswd")[0] == 404
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_refuses_logs_outside_runs_dir(workspace, capsys):
    """A tampered database must not turn the log viewer into a file server."""
    import sqlite3

    tmp, flow = workspace
    assert main(["run", str(flow)]) == 0
    capsys.readouterr()
    secret = tmp / "secret.txt"
    secret.write_text("top secret")
    db = tmp / "runs" / "gauntlet.db"
    conn = sqlite3.connect(db)
    conn.execute("UPDATE step_results SET log_path=? WHERE step_id='build'", (str(secret),))
    conn.commit()
    conn.close()

    server = make_server(db, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        status, body = _get(f"http://127.0.0.1:{server.server_address[1]}", "/runs/latest/log/build")
        assert status == 404 and "top secret" not in body
    finally:
        server.shutdown()
        server.server_close()
