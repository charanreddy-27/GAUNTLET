"""Scheduler behavior: ordering, skip cascades, timeouts, keep-going."""
import time

from gauntlet.models import FlowSpec, StepSpec, StepStatus
from gauntlet.scheduler import Scheduler


def _run(steps, tmp_path, **kw):
    flow = FlowSpec(name="t", description="", steps=tuple(steps))
    return Scheduler(flow, **kw).execute(tmp_path)


def test_dependency_order_respected(tmp_path):
    marker = tmp_path / "a_done"
    steps = [
        StepSpec(id="a", cmd=f"touch {marker}"),
        # b only passes if a's marker already exists -> proves ordering
        StepSpec(id="b", cmd=f"test -f {marker}", depends_on=("a",)),
    ]
    results = _run(steps, tmp_path, max_workers=4)
    assert results["a"].status == StepStatus.PASS
    assert results["b"].status == StepStatus.PASS


def test_independent_steps_run_in_parallel(tmp_path):
    steps = [
        StepSpec(id="s1", cmd="sleep 0.6"),
        StepSpec(id="s2", cmd="sleep 0.6"),
    ]
    start = time.monotonic()
    results = _run(steps, tmp_path, max_workers=2)
    elapsed = time.monotonic() - start
    assert all(r.status == StepStatus.PASS for r in results.values())
    assert elapsed < 1.1  # serial would be >= 1.2s


def test_failed_dep_skips_dependents_transitively(tmp_path):
    steps = [
        StepSpec(id="bad", cmd="false"),
        StepSpec(id="child", cmd="true", depends_on=("bad",)),
        StepSpec(id="grandchild", cmd="true", depends_on=("child",)),
    ]
    results = _run(steps, tmp_path)
    assert results["bad"].status == StepStatus.FAIL
    assert results["child"].status == StepStatus.SKIPPED
    assert results["grandchild"].status == StepStatus.SKIPPED


def test_timeout_marks_timeout_and_skips_dependents(tmp_path):
    steps = [
        StepSpec(id="slow", cmd="sleep 999", timeout_s=1),
        StepSpec(id="after", cmd="true", depends_on=("slow",)),
    ]
    start = time.monotonic()
    results = _run(steps, tmp_path)
    assert time.monotonic() - start < 3  # SIGTERM ends it well before 999s
    assert results["slow"].status == StepStatus.TIMEOUT
    assert results["slow"].exit_code is None
    assert results["after"].status == StepStatus.SKIPPED


def test_default_stops_new_work_after_failure(tmp_path):
    steps = [
        StepSpec(id="bad", cmd="false"),
        # gate only becomes ready after bad fails -> must not be submitted
        StepSpec(id="slow", cmd="sleep 0.3"),
        StepSpec(id="gate", cmd="true", depends_on=("slow",)),
    ]
    results = _run(steps, tmp_path, max_workers=1)
    assert results["bad"].status == StepStatus.FAIL
    assert results["gate"].status == StepStatus.SKIPPED


def test_keep_going_runs_independent_branches(tmp_path):
    steps = [
        StepSpec(id="bad", cmd="false"),
        StepSpec(id="slow", cmd="sleep 0.3"),
        StepSpec(id="gate", cmd="true", depends_on=("slow",)),
    ]
    results = _run(steps, tmp_path, max_workers=1, keep_going=True)
    assert results["bad"].status == StepStatus.FAIL
    assert results["slow"].status == StepStatus.PASS
    assert results["gate"].status == StepStatus.PASS


def test_logs_written_to_run_dir(tmp_path):
    steps = [StepSpec(id="hello", cmd="echo hi there")]
    results = _run(steps, tmp_path)
    log = tmp_path / "hello" / "output.log"
    assert log.read_text().strip() == "hi there"
    assert results["hello"].log_path == str(log)
