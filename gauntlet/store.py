"""SQLite persistence for runs. One file DB, four tables, no ORM.

The store is the memory of the platform: `history`, `report <run_id>`,
`diff`, `stats` and `serve` all work from the DB alone, long after runs/ logs
are cleaned up.

Databases written by older versions are migrated in place on open: new
columns are added with defaults, nothing is rewritten or dropped.
"""
from __future__ import annotations

import re
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
CREATE TABLE IF NOT EXISTS run_edges(
  run_id TEXT, step_id TEXT, dep TEXT);
CREATE INDEX IF NOT EXISTS idx_runs_flow ON runs(flow_name, started_at);
"""

# Columns added after v0.1, as (table, column, declaration). Applied with
# ALTER TABLE when an older database is opened.
_MIGRATIONS = (
    ("runs", "git_commit", "TEXT"),
    ("runs", "git_branch", "TEXT"),
    ("step_results", "start_s", "REAL"),
    ("step_results", "end_s", "REAL"),
    ("step_results", "attempts", "INT DEFAULT 1"),
    ("violations", "waive_owner", "TEXT"),
)

_REF = re.compile(r"^latest(?:~(\d+))?$")


def _iso_delta_s(start: str, end: str) -> float:
    from datetime import datetime

    try:
        return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
    except (ValueError, TypeError):
        return 0.0


class RunNotFoundError(Exception):
    """The requested run_id is not in the database."""


class RunStore:
    """Owns the SQLite connection and the RunRecord <-> rows mapping."""

    def __init__(self, db_path: str | Path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: `gauntlet serve` hands requests to worker
        # threads, but each request opens and closes its own store.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        for table, column, decl in _MIGRATIONS:
            have = {row[1] for row in self._conn.execute(f"PRAGMA table_info({table})")}
            if column not in have:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> RunStore:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def save(self, record: RunRecord) -> None:
        """Persist a full run (idempotent: re-saving replaces it)."""
        with self._conn:
            for table in ("runs", "step_results", "violations", "run_edges"):
                self._conn.execute(f"DELETE FROM {table} WHERE run_id=?", (record.run_id,))
            self._conn.execute(
                "INSERT INTO runs(run_id, flow_name, started_at, finished_at, status,"
                " git_commit, git_branch) VALUES (?,?,?,?,?,?,?)",
                (
                    record.run_id,
                    record.flow_name,
                    record.started_at,
                    record.finished_at,
                    record.status,
                    record.git_commit,
                    record.git_branch,
                ),
            )
            # One node row (dep NULL) per step, in flow order, then its edges —
            # so steps without dependencies survive, and order round-trips.
            for step_id, deps in record.dag.items():
                self._conn.execute(
                    "INSERT INTO run_edges VALUES (?,?,NULL)", (record.run_id, step_id)
                )
                for dep in deps:
                    self._conn.execute(
                        "INSERT INTO run_edges VALUES (?,?,?)", (record.run_id, step_id, dep)
                    )
            for result in record.results.values():
                self._conn.execute(
                    "INSERT INTO step_results(run_id, step_id, status, exit_code,"
                    " duration_s, log_path, flaky, start_s, end_s, attempts)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        record.run_id,
                        result.step_id,
                        result.status.value,
                        result.exit_code,
                        result.duration_s,
                        result.log_path,
                        int(result.flaky),
                        result.start_s,
                        result.end_s,
                        result.attempts,
                    ),
                )
                for v in result.violations:
                    self._conn.execute(
                        "INSERT INTO violations(run_id, step_id, rule_id, severity,"
                        " line_no, message, waived, waive_reason, waive_owner)"
                        " VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            record.run_id,
                            result.step_id,
                            v.rule_id,
                            v.severity,
                            v.line_no,
                            v.message,
                            int(v.waived),
                            v.waive_reason,
                            v.waive_owner,
                        ),
                    )

    def resolve(self, ref: str) -> str:
        """Turn a run reference into a run_id.

        Accepts a literal run_id, `latest` (newest run) or `latest~N` (the run
        N before the newest), so CI can say `gauntlet diff latest~1 latest`
        without knowing either id.
        """
        match = _REF.match(ref)
        if not match:
            return ref
        offset = int(match.group(1) or 0)
        row = self._conn.execute(
            "SELECT run_id FROM runs ORDER BY started_at DESC, rowid DESC LIMIT 1 OFFSET ?",
            (offset,),
        ).fetchone()
        if row is None:
            have = self._conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            raise RunNotFoundError(
                f"no run at {ref!r} — the database holds {have} run(s)"
            )
        return row[0]

    def load(self, run_id: str) -> RunRecord:
        """Rebuild a full RunRecord (with violations) from the DB."""
        run_id = self.resolve(run_id)
        row = self._conn.execute(
            "SELECT run_id, flow_name, started_at, finished_at, status,"
            " git_commit, git_branch FROM runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise RunNotFoundError(f"no such run: {run_id}")

        results: dict[str, StepResult] = {}
        for srow in self._conn.execute(
            "SELECT step_id, status, exit_code, duration_s, log_path, flaky,"
            " start_s, end_s, attempts FROM step_results WHERE run_id=?"
            " ORDER BY COALESCE(start_s, 1e18), step_id",
            (run_id,),
        ):
            results[srow[0]] = StepResult(
                step_id=srow[0],
                status=StepStatus(srow[1]),
                exit_code=srow[2],
                duration_s=srow[3],
                log_path=srow[4],
                flaky=bool(srow[5]),
                start_s=srow[6],
                end_s=srow[7],
                attempts=1 if srow[8] is None else srow[8],
            )
        for vrow in self._conn.execute(
            "SELECT step_id, rule_id, severity, line_no, message, waived,"
            " waive_reason, waive_owner FROM violations WHERE run_id=?"
            " ORDER BY rowid",
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
                    waive_owner=vrow[7],
                )
            )
        dag: dict[str, list[str]] = {}
        for erow in self._conn.execute(
            "SELECT step_id, dep FROM run_edges WHERE run_id=? ORDER BY rowid", (run_id,)
        ):
            deps = dag.setdefault(erow[0], [])
            if erow[1] is not None:
                deps.append(erow[1])
        if dag:
            # Present steps in flow order — the DAG reads top-down.
            ordered = {sid: results[sid] for sid in dag if sid in results}
            ordered.update({sid: r for sid, r in results.items() if sid not in ordered})
            results = ordered
        return RunRecord(
            run_id=row[0],
            flow_name=row[1],
            started_at=row[2],
            finished_at=row[3],
            status=row[4],
            results=results,
            dag=dag,
            git_commit=row[5],
            git_branch=row[6],
        )

    def list_runs(self, limit: int = 10, flow_name: str | None = None) -> list[dict]:
        """Newest-first run summaries for `gauntlet history`."""
        where, params = ("WHERE r.flow_name = ?", [flow_name]) if flow_name else ("", [])
        rows = self._conn.execute(
            "SELECT r.run_id, r.flow_name, r.started_at, r.finished_at, r.status,"
            " (SELECT COUNT(*) FROM step_results s"
            "   WHERE s.run_id = r.run_id AND s.status IN ('FAIL','TIMEOUT')),"
            " (SELECT COUNT(*) FROM step_results s WHERE s.run_id = r.run_id),"
            " r.git_commit, r.git_branch,"
            " (SELECT MAX(end_s) FROM step_results s WHERE s.run_id = r.run_id)"
            f" FROM runs r {where} ORDER BY r.started_at DESC, r.rowid DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [
            {
                "run_id": r[0],
                "flow_name": r[1],
                "started_at": r[2],
                "finished_at": r[3],
                "status": r[4],
                "failed_steps": r[5],
                "total_steps": r[6],
                "git_commit": r[7],
                "git_branch": r[8],
                # Millisecond step windows when recorded, else the ISO stamps.
                "duration_s": r[9] if r[9] is not None else _iso_delta_s(r[2], r[3]),
            }
            for r in rows
        ]

    def flows(self) -> list[str]:
        """Every flow name that has at least one run, most recently run first."""
        rows = self._conn.execute(
            "SELECT flow_name FROM runs GROUP BY flow_name ORDER BY MAX(started_at) DESC"
        ).fetchall()
        return [r[0] for r in rows]

    def step_history(self, flow_name: str, limit: int = 20) -> list[RunRecord]:
        """The last `limit` runs of one flow, oldest first, fully loaded.

        Oldest first because stability is a story told in order: a status
        strip reads left to right, and a "flip" is a change between neighbours.
        """
        ids = [row["run_id"] for row in self.list_runs(limit, flow_name=flow_name)]
        return [self.load(run_id) for run_id in reversed(ids)]
