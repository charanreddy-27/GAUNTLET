"""DAG layering / critical path, step stability, and timing capture."""
from gauntlet.graph import critical_path, layers, max_parallelism, to_ascii, to_dot, to_mermaid
from gauntlet.models import FlowSpec, RunRecord, StepResult, StepSpec, StepStatus
from gauntlet.scheduler import Scheduler
from gauntlet.stats import compute_stats, render_stats
from probe import cmd

SMOKE = {"lint": [], "sim_u": ["lint"], "sim_i": ["lint"], "synth": ["sim_u", "sim_i"]}


def test_layers_follow_longest_path_depth():
    assert layers(SMOKE) == [["lint"], ["sim_u", "sim_i"], ["synth"]]
    # a step depending on layer 0 and layer 2 lands in layer 3
    assert layers({**SMOKE, "sign": ["lint", "synth"]})[3] == ["sign"]


def test_critical_path_uses_weights_when_given():
    assert critical_path(SMOKE, {"lint": 1, "sim_u": 1, "sim_i": 5, "synth": 1}) == [
        "lint", "sim_i", "synth",
    ]
    assert critical_path(SMOKE, {"lint": 1, "sim_u": 9, "sim_i": 5, "synth": 1})[1] == "sim_u"


def test_text_renderings_mention_every_edge():
    mermaid = to_mermaid(SMOKE, {"lint": StepStatus.PASS, "synth": StepStatus.SKIPPED})
    assert mermaid.startswith("flowchart LR")
    assert "n_sim_u --> n_synth" in mermaid and "n_sim_i --> n_synth" in mermaid
    assert "class n_synth skipped" in mermaid
    assert '"lint" -> "sim_u"' in to_dot("smoke", SMOKE)
    ascii_view = to_ascii("smoke", SMOKE)
    assert "3 layers" in ascii_view and "max parallelism 2" in ascii_view
    assert "← sim_u, sim_i" in ascii_view


def _rec(run_id, statuses, flaky=()):
    return RunRecord(
        run_id, "smoke", "2026-07-14T09:00:00", "2026-07-14T09:00:01", "PASS",
        {sid: StepResult(sid, st, 0, 1.0, "", flaky=sid in flaky) for sid, st in statuses.items()},
        dag={"a": [], "b": ["a"]},
    )  # fmt: skip


def test_stats_strip_flips_and_verdicts():
    P, F, S, W = StepStatus.PASS, StepStatus.FAIL, StepStatus.SKIPPED, StepStatus.WAIVED
    runs = [
        _rec("r1", {"a": P, "b": P}),
        _rec("r2", {"a": F, "b": S}),
        _rec("r3", {"a": P, "b": W}, flaky={"b"}),
        _rec("r4", {"a": P, "b": P}),
    ]
    a, b = compute_stats(runs)
    assert a.strip == "✓✗✓✓" and a.flips == 2 and a.verdict == "flaky"
    assert a.last_failure == "r2" and a.pass_rate == 0.75
    assert b.strip == "✓·w✓" and b.flips == 0 and b.flaky == 1 and b.verdict == "flaky"
    assert b.pass_rate == 1.0  # SKIPPED is not evidence against the step
    text = render_stats("smoke", runs, [a, b])
    assert "needs an owner: a, b" in text


def test_stats_failing_wins_over_flaky():
    P, F = StepStatus.PASS, StepStatus.FAIL
    (a, _) = compute_stats([_rec("r1", {"a": P, "b": P}), _rec("r2", {"a": F, "b": P})])
    assert a.verdict == "failing"


def test_scheduler_records_windows_and_attempts(tmp_path):
    flow = FlowSpec("t", "", (
        StepSpec("s1", cmd("sleep", 0.4)),
        StepSpec("s2", cmd("sleep", 0.4)),
        StepSpec("wobbly", cmd("fail-once", tmp_path / "m"), depends_on=("s1",), retries=1),
        StepSpec("bad", cmd("fail")),
        StepSpec("after_bad", cmd("ok"), depends_on=("bad",)),
    ))  # fmt: skip
    results = Scheduler(flow, max_workers=3, keep_going=True).execute(tmp_path)
    s1 = results["s1"]
    assert s1.start_s is not None and s1.end_s >= s1.start_s + 0.35
    assert results["wobbly"].attempts == 2 and results["wobbly"].flaky
    assert results["wobbly"].start_s >= s1.end_s - 0.05  # waited for its dependency
    skipped = results["after_bad"]
    assert skipped.status == StepStatus.SKIPPED
    assert (skipped.start_s, skipped.end_s, skipped.attempts) == (None, None, 0)
    record = RunRecord("r", "t", "x", "x", "FAIL", results)
    assert max_parallelism(record) >= 2  # s1 and s2 really overlapped
