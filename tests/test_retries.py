"""Phase 5 stretch: per-step naive immediate retries + flaky marking.

Commands run through tests/probe.py (see conftest) so retry timing and exit
codes are identical across operating systems.
"""
from probe import cmd
from gauntlet.flow import build_flow
from gauntlet.models import FlowSpec, StepSpec, StepStatus
from gauntlet.scheduler import Scheduler


def _run(steps, tmp_path, **kw):
    flow = FlowSpec(name="t", description="", steps=tuple(steps))
    return Scheduler(flow, **kw).execute(tmp_path)


def _fail_once_cmd(tmp_path):
    # First attempt creates the marker and fails; every later attempt passes.
    return cmd("fail-once", tmp_path / "marker")


def test_retry_turns_failure_into_flaky_pass(tmp_path):
    steps = [StepSpec(id="wobbly", cmd=_fail_once_cmd(tmp_path), retries=1)]
    results = _run(steps, tmp_path)
    assert results["wobbly"].status == StepStatus.PASS
    assert results["wobbly"].flaky is True


def test_flaky_pass_still_satisfies_dependents(tmp_path):
    steps = [
        StepSpec(id="wobbly", cmd=_fail_once_cmd(tmp_path), retries=1),
        StepSpec(id="child", cmd=cmd("ok"), depends_on=("wobbly",)),
    ]
    results = _run(steps, tmp_path)
    assert results["child"].status == StepStatus.PASS


def test_exhausted_retries_fail_and_are_not_flaky(tmp_path):
    steps = [StepSpec(id="doomed", cmd=cmd("fail"), retries=2)]
    results = _run(steps, tmp_path)
    assert results["doomed"].status == StepStatus.FAIL
    assert results["doomed"].flaky is False


def test_clean_pass_is_not_flaky(tmp_path):
    steps = [StepSpec(id="solid", cmd=cmd("ok"), retries=3)]
    results = _run(steps, tmp_path)
    assert results["solid"].status == StepStatus.PASS
    assert results["solid"].flaky is False


def test_retries_parsed_from_yaml():
    flow = build_flow(
        {
            "name": "t",
            "steps": [
                {"id": "a", "cmd": "true", "retries": 2},
                {"id": "b", "cmd": "true"},
            ],
        }
    )
    assert flow.steps[0].retries == 2
    assert flow.steps[1].retries == 0
