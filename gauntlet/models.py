"""Domain model: the single source of truth for every other module.

Enums for statuses, frozen dataclasses for specs (inputs), mutable
dataclasses for results (outputs). Serialization helpers live next to the
data so manifest.json and the SQLite store agree on one format.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class StepStatus(str, Enum):
    """Terminal state of one step in a run."""

    PASS = "PASS"
    FAIL = "FAIL"          # nonzero exit OR unwaived ERROR violations
    WAIVED = "WAIVED"      # would have failed, all ERRORs waived
    TIMEOUT = "TIMEOUT"
    SKIPPED = "SKIPPED"    # upstream dependency failed


#: Statuses that satisfy a downstream dependency.
PASSING_STATUSES = frozenset({StepStatus.PASS, StepStatus.WAIVED})

#: Statuses that block downstream dependents (they become SKIPPED).
BLOCKING_STATUSES = frozenset({StepStatus.FAIL, StepStatus.TIMEOUT, StepStatus.SKIPPED})


@dataclass(frozen=True)
class StepSpec:
    """Declarative description of one step, straight from the flow YAML."""

    id: str
    cmd: str
    depends_on: tuple[str, ...] = ()
    rulepack: str | None = None
    timeout_s: int = 60
    retries: int = 0         # extra immediate attempts on failure


@dataclass(frozen=True)
class FlowSpec:
    """A validated, cycle-free collection of StepSpecs."""

    name: str
    description: str
    steps: tuple[StepSpec, ...]


@dataclass
class Violation:
    """One rule match found in a step's log file."""

    rule_id: str
    severity: str            # "ERROR" | "WARNING" | "INFO"
    line_no: int
    message: str
    waived: bool = False
    waive_reason: str | None = None
    waive_owner: str | None = None   # who signed the waiver (audit trail)


@dataclass
class StepResult:
    """Everything we know about one executed (or skipped) step."""

    step_id: str
    status: StepStatus
    exit_code: int | None
    duration_s: float
    log_path: str
    violations: list[Violation] = field(default_factory=list)
    flaky: bool = False      # passed, but only after at least one retry
    # Wall-clock window relative to run start, first attempt to last. None for
    # SKIPPED steps (they never ran) and for runs recorded before v0.2.
    start_s: float | None = None
    end_s: float | None = None
    attempts: int = 1        # 0 for SKIPPED; >1 when retries were spent

    @property
    def errors(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == "ERROR"]

    @property
    def unwaived_errors(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == "ERROR" and not v.waived]

    @property
    def warnings(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == "WARNING"]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> StepResult:
        violations = [Violation(**v) for v in d.get("violations", [])]
        return cls(
            step_id=d["step_id"],
            status=StepStatus(d["status"]),
            exit_code=d["exit_code"],
            duration_s=d["duration_s"],
            log_path=d["log_path"],
            violations=violations,
            flaky=d.get("flaky", False),
            start_s=d.get("start_s"),
            end_s=d.get("end_s"),
            attempts=d.get("attempts", 1),
        )


@dataclass
class RunRecord:
    """One full flow execution: identity, timing, verdict, per-step results."""

    run_id: str              # e.g. "run_20260714_0932_a1b2"
    flow_name: str
    started_at: str
    finished_at: str
    status: str              # "PASS" | "FAIL"
    results: dict[str, StepResult]
    # The flow's dependency graph as it was when this run executed, so reports
    # can draw the DAG long after the YAML has changed. step_id -> deps.
    dag: dict[str, list[str]] = field(default_factory=dict)
    # Which commit ran the gauntlet, when the run happened inside a git repo.
    git_commit: str | None = None
    git_branch: str | None = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "flow_name": self.flow_name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "git_commit": self.git_commit,
            "git_branch": self.git_branch,
            "dag": {sid: list(deps) for sid, deps in self.dag.items()},
            "results": {sid: r.to_dict() for sid, r in self.results.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> RunRecord:
        return cls(
            run_id=d["run_id"],
            flow_name=d["flow_name"],
            started_at=d["started_at"],
            finished_at=d["finished_at"],
            status=d["status"],
            results={sid: StepResult.from_dict(r) for sid, r in d["results"].items()},
            dag={sid: list(deps) for sid, deps in (d.get("dag") or {}).items()},
            git_commit=d.get("git_commit"),
            git_branch=d.get("git_branch"),
        )
