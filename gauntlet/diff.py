"""Run-to-run comparison — the essence of regression tracking.

A step is 'failing' if FAIL or TIMEOUT. Steps present in both runs land in
exactly one bucket; steps only in one run go to NEW_STEPS/REMOVED_STEPS.
(PASS, WAIVED and SKIPPED all count as non-failing: SKIPPED means we have
no new evidence against the step itself.)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import RunRecord, StepResult, StepStatus

FAILING = frozenset({StepStatus.FAIL, StepStatus.TIMEOUT})


@dataclass
class RunDiff:
    """Categorized comparison of two runs of (usually) the same flow."""

    run_a: str
    run_b: str
    flow_name: str
    new_failures: list[StepResult] = field(default_factory=list)
    fixed: list[StepResult] = field(default_factory=list)
    still_failing: list[StepResult] = field(default_factory=list)
    unchanged_pass: list[StepResult] = field(default_factory=list)
    new_steps: list[str] = field(default_factory=list)
    removed_steps: list[str] = field(default_factory=list)

    def verdict_line(self) -> str:
        if self.new_failures:
            n = len(self.new_failures)
            noun = "failure" if n == 1 else "failures"
            return f"REGRESSION ({n} new {noun})"
        if self.fixed and not self.still_failing:
            return "IMPROVED (all previous failures fixed)"
        if self.still_failing:
            return f"NO NEW FAILURES ({len(self.still_failing)} still failing)"
        return "CLEAN (no failures either side)"


def diff_runs(a: RunRecord, b: RunRecord) -> RunDiff:
    """Compare run a (older/baseline) against run b (newer)."""
    diff = RunDiff(run_a=a.run_id, run_b=b.run_id, flow_name=b.flow_name)

    for step_id, result_b in b.results.items():
        result_a = a.results.get(step_id)
        if result_a is None:
            diff.new_steps.append(step_id)
            continue
        a_failing = result_a.status in FAILING
        b_failing = result_b.status in FAILING
        if b_failing and not a_failing:
            diff.new_failures.append(result_b)
        elif b_failing and a_failing:
            diff.still_failing.append(result_b)
        elif a_failing and not b_failing:
            diff.fixed.append(result_b)
        else:
            diff.unchanged_pass.append(result_b)

    diff.removed_steps = [sid for sid in a.results if sid not in b.results]
    return diff
