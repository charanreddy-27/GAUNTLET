"""Store v0.2: in-place migration of v0.1 databases, DAG + timing round-trip,
and `latest` / `latest~N` run references."""
import sqlite3

import pytest

from gauntlet.models import RunRecord, StepResult, StepStatus, Violation
from gauntlet.store import RunNotFoundError, RunStore

V01_SCHEMA = """
CREATE TABLE runs(run_id TEXT PRIMARY KEY, flow_name TEXT, started_at TEXT,
  finished_at TEXT, status TEXT);
CREATE TABLE step_results(run_id TEXT, step_id TEXT, status TEXT, exit_code INT,
  duration_s REAL, log_path TEXT, flaky INT DEFAULT 0, PRIMARY KEY(run_id, step_id));
CREATE TABLE violations(run_id TEXT, step_id TEXT, rule_id TEXT, severity TEXT,
  line_no INT, message TEXT, waived INT, waive_reason TEXT);
"""


def _record(run_id, started, status=StepStatus.PASS):
    return RunRecord(
        run_id=run_id,
        flow_name="smoke",
        started_at=started,
        finished_at=started,
        status="PASS" if status == StepStatus.PASS else "FAIL",
        results={
            "lint": StepResult("lint", StepStatus.PASS, 0, 1.0, "l.log", start_s=0.0, end_s=1.0),
            "sim": StepResult(
                "sim", status, 0, 2.0, "s.log", start_s=1.0, end_s=3.5, attempts=2,
                violations=[Violation("SIM-1", "ERROR", 3, "boom", True, "known", "charan")],
            ),
        },
        dag={"lint": [], "sim": ["lint"]},
        git_commit="abc123",
        git_branch="main",
    )


def test_v01_database_is_migrated_in_place(tmp_path):
    db = tmp_path / "gauntlet.db"
    conn = sqlite3.connect(db)
    conn.executescript(V01_SCHEMA)
    conn.execute("INSERT INTO runs VALUES ('run_old','smoke','2026-07-14T09:00:00','2026-07-14T09:00:05','PASS')")
    conn.execute("INSERT INTO step_results VALUES ('run_old','lint','PASS',0,1.5,'x.log',0)")
    conn.commit()
    conn.close()

    with RunStore(db) as store:
        old = store.load("run_old")
        assert old.results["lint"].start_s is None
        assert old.results["lint"].attempts == 1
        assert old.dag == {}
        assert old.git_commit is None
        # and new runs land in the same, upgraded database
        store.save(_record("run_new", "2026-07-15T09:00:00"))
        assert [r["run_id"] for r in store.list_runs()] == ["run_new", "run_old"]


def test_dag_timing_and_waiver_owner_round_trip(tmp_path):
    with RunStore(tmp_path / "g.db") as store:
        store.save(_record("run_a", "2026-07-14T09:00:00"))
        back = store.load("run_a")
    assert back.dag == {"lint": [], "sim": ["lint"]}
    assert list(back.results) == ["lint", "sim"]  # flow order survives
    sim = back.results["sim"]
    assert (sim.start_s, sim.end_s, sim.attempts) == (1.0, 3.5, 2)
    assert sim.violations[0].waive_owner == "charan"
    assert (back.git_commit, back.git_branch) == ("abc123", "main")


def test_list_runs_reports_precise_duration(tmp_path):
    with RunStore(tmp_path / "g.db") as store:
        store.save(_record("run_a", "2026-07-14T09:00:00"))
        row = store.list_runs()[0]
    assert row["duration_s"] == 3.5  # from step windows, not second-precision stamps
    assert row["total_steps"] == 2


def test_latest_refs_resolve_newest_first(tmp_path):
    with RunStore(tmp_path / "g.db") as store:
        store.save(_record("run_1", "2026-07-14T09:00:00"))
        store.save(_record("run_2", "2026-07-14T10:00:00"))
        store.save(_record("run_3", "2026-07-14T11:00:00"))
        assert store.resolve("latest") == "run_3"
        assert store.resolve("latest~1") == "run_2"
        assert store.load("latest~2").run_id == "run_1"
        assert store.resolve("run_2") == "run_2"  # literal ids pass through
        with pytest.raises(RunNotFoundError, match="holds 3 run"):
            store.resolve("latest~3")


def test_step_history_is_oldest_first_and_per_flow(tmp_path):
    with RunStore(tmp_path / "g.db") as store:
        store.save(_record("run_1", "2026-07-14T09:00:00"))
        store.save(_record("run_2", "2026-07-14T10:00:00", StepStatus.FAIL))
        other = _record("run_x", "2026-07-14T11:00:00")
        other.flow_name = "other"
        store.save(other)
        history = store.step_history("smoke", 10)
        assert store.flows() == ["other", "smoke"]
    assert [r.run_id for r in history] == ["run_1", "run_2"]
