"""Diff categorization from synthetic RunRecords, plus store round-trip."""
from gauntlet.diff import diff_runs
from gauntlet.models import RunRecord, StepResult, StepStatus, Violation
from gauntlet.store import RunStore


def _record(run_id: str, statuses: dict[str, StepStatus]) -> RunRecord:
    results = {
        sid: StepResult(sid, status, 0 if status == StepStatus.PASS else 1,
                        1.0, f"runs/{run_id}/{sid}/output.log")
        for sid, status in statuses.items()
    }
    return RunRecord(
        run_id=run_id,
        flow_name="smoke",
        started_at="2026-07-14T09:32:00",
        finished_at="2026-07-14T09:32:04",
        status="FAIL",
        results=results,
    )


def test_buckets_are_correct():
    a = _record("run_a", {
        "lint": StepStatus.FAIL,       # -> fixed
        "sim_u": StepStatus.PASS,      # -> new failure
        "sim_i": StepStatus.TIMEOUT,   # -> still failing
        "synth": StepStatus.PASS,      # -> unchanged pass
        "gone": StepStatus.PASS,       # -> removed
    })
    b = _record("run_b", {
        "lint": StepStatus.PASS,
        "sim_u": StepStatus.FAIL,
        "sim_i": StepStatus.FAIL,
        "synth": StepStatus.WAIVED,
        "fresh": StepStatus.PASS,      # -> new step
    })
    diff = diff_runs(a, b)
    assert [r.step_id for r in diff.new_failures] == ["sim_u"]
    assert [r.step_id for r in diff.fixed] == ["lint"]
    assert [r.step_id for r in diff.still_failing] == ["sim_i"]
    assert [r.step_id for r in diff.unchanged_pass] == ["synth"]
    assert diff.new_steps == ["fresh"]
    assert diff.removed_steps == ["gone"]
    assert "REGRESSION" in diff.verdict_line()


def test_timeout_counts_as_new_failure():
    a = _record("run_a", {"s": StepStatus.PASS})
    b = _record("run_b", {"s": StepStatus.TIMEOUT})
    diff = diff_runs(a, b)
    assert [r.step_id for r in diff.new_failures] == ["s"]


def test_skipped_is_not_a_new_failure():
    a = _record("run_a", {"s": StepStatus.PASS})
    b = _record("run_b", {"s": StepStatus.SKIPPED})
    diff = diff_runs(a, b)
    assert diff.new_failures == []
    assert [r.step_id for r in diff.unchanged_pass] == ["s"]


def test_waived_to_fail_is_a_new_failure():
    a = _record("run_a", {"s": StepStatus.WAIVED})
    b = _record("run_b", {"s": StepStatus.FAIL})
    diff = diff_runs(a, b)
    assert [r.step_id for r in diff.new_failures] == ["s"]


def test_clean_verdict_when_nothing_fails():
    a = _record("run_a", {"s": StepStatus.PASS})
    b = _record("run_b", {"s": StepStatus.PASS})
    assert "CLEAN" in diff_runs(a, b).verdict_line()


def test_store_round_trip(tmp_path):
    record = _record("run_x", {"lint": StepStatus.FAIL, "sim": StepStatus.WAIVED})
    record.results["lint"].violations.append(
        Violation("LINT-201", "ERROR", 4, "latch inferred", waived=False)
    )
    record.results["sim"].violations.append(
        Violation("SIM-ERR-007", "ERROR", 9, "fifo overflow in u_fifo_rx",
                  waived=True, waive_reason="Known TB artifact")
    )
    record.results["sim"].flaky = True  # exercise flaky persistence too
    store = RunStore(tmp_path / "g.db")
    store.save(record)
    loaded = store.load("run_x")
    store.close()
    assert loaded == record


def test_history_counts_failed_steps(tmp_path):
    store = RunStore(tmp_path / "g.db")
    store.save(_record("run_1", {"a": StepStatus.PASS, "b": StepStatus.FAIL,
                                 "c": StepStatus.TIMEOUT}))
    rows = store.list_runs()
    store.close()
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run_1"
    assert rows[0]["failed_steps"] == 2
