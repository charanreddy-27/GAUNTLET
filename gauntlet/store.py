"""SQLite persistence for runs. One file DB, three tables, no ORM.

The store is the memory of the platform: `history`, `report <run_id>` and
`diff` all work from the DB alone, long after runs/ logs are cleaned up.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import RunRecord, StepResult, StepStatus, Violation

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  run_id TEXT PRIMARY KEY, flow_name TEXT, started_at TEXT,
  finished_at TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS step_results(
  run_id TEXT, step_id TEXT, status TEXT, exit_code INT,
  duration_s REAL, log_path TEXT, flaky INT DEFAULT 0,
  PRIMARY KEY(run_id, step_id));
CREATE TABLE IF NOT EXISTS violations(
  run_id TEXT, step_id TEXT, rule_id TEXT, severity TEXT,
  line_no INT, message TEXT, waived INT, waive_reason TEXT);
"""


class RunNotFoundError(Exception):
    """The requested run_id is not in the database."""


class RunStore:
    """Owns the SQLite connection and the RunRecord <-> rows mapping."""

    def __init__(self, db_path: str | Path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def save(self, record: RunRecord) -> None:
        """Persist a full run (idempotent: re-saving replaces it)."""
        with self._conn:
            self._conn.execute("DELETE FROM runs WHERE run_id=?", (record.run_id,))
            self._conn.execute(
                "DELETE FROM step_results WHERE run_id=?", (record.run_id,)
            )
            self._conn.execute(
                "DELETE FROM violations WHERE run_id=?", (record.run_id,)
            )
            self._conn.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?)",
                (
                    record.run_id,
                    record.flow_name,
                    record.started_at,
                    record.finished_at,
                    record.status,
                ),
            )
            for result in record.results.values():
                self._conn.execute(
                    "INSERT INTO step_results VALUES (?,?,?,?,?,?,?)",
                    (
                        record.run_id,
                        result.step_id,
                        result.status.value,
                        result.exit_code,
                        result.duration_s,
                        result.log_path,
                        int(result.flaky),
                    ),
                )
                for v in result.violations:
                    self._conn.execute(
                        "INSERT INTO violations VALUES (?,?,?,?,?,?,?,?)",
                        (
                            record.run_id,
                            result.step_id,
                            v.rule_id,
                            v.severity,
                            v.line_no,
                            v.message,
                            int(v.waived),
                            v.waive_reason,
                        ),
                    )

    def load(self, run_id: str) -> RunRecord:
        """Rebuild a full RunRecord (with violations) from the DB."""
        row = self._conn.execute(
            "SELECT run_id, flow_name, started_at, finished_at, status"
            " FROM runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise RunNotFoundError(f"no such run: {run_id}")

        results: dict[str, StepResult] = {}
        for srow in self._conn.execute(
            "SELECT step_id, status, exit_code, duration_s, log_path, flaky"
            " FROM step_results WHERE run_id=? ORDER BY step_id",
            (run_id,),
        ):
            results[srow[0]] = StepResult(
                step_id=srow[0],
                status=StepStatus(srow[1]),
                exit_code=srow[2],
                duration_s=srow[3],
                log_path=srow[4],
                flaky=bool(srow[5]),
            )
        for vrow in self._conn.execute(
            "SELECT step_id, rule_id, severity, line_no, message, waived,"
            " waive_reason FROM violations WHERE run_id=?",
            (run_id,),
        ):
            results[vrow[0]].violations.append(
                Violation(
                    rule_id=vrow[1],
                    severity=vrow[2],
                    line_no=vrow[3],
                    message=vrow[4],
                    waived=bool(vrow[5]),
                    waive_reason=vrow[6],
                )
            )
        return RunRecord(
            run_id=row[0],
            flow_name=row[1],
            started_at=row[2],
            finished_at=row[3],
            status=row[4],
            results=results,
        )

    def list_runs(self, limit: int = 10) -> list[dict]:
        """Newest-first run summaries for `gauntlet history`."""
        rows = self._conn.execute(
            "SELECT r.run_id, r.flow_name, r.started_at, r.finished_at, r.status,"
            " (SELECT COUNT(*) FROM step_results s"
            "   WHERE s.run_id = r.run_id AND s.status IN ('FAIL','TIMEOUT'))"
            " FROM runs r ORDER BY r.started_at DESC, r.run_id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "run_id": r[0],
                "flow_name": r[1],
                "started_at": r[2],
                "finished_at": r[3],
                "status": r[4],
                "failed_steps": r[5],
            }
            for r in rows
        ]
