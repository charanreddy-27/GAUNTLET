"""Scheduler: WHEN steps run.

A thread pool is the right tool here (not asyncio, not processes): workers
spend their time blocked in subprocess.wait(), where the GIL is released,
so N threads give real parallelism for the cost of none of the complexity.
"""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Callable, Protocol

from .models import (
    BLOCKING_STATUSES,
    PASSING_STATUSES,
    FlowSpec,
    StepResult,
    StepSpec,
    StepStatus,
)
from .steps import ShellStep, Step


class ResultEvaluator(Protocol):
    """Post-processes a raw StepResult (e.g. log parsing + waivers)."""

    def evaluate(self, spec: StepSpec, result: StepResult) -> StepResult: ...


class Scheduler:
    """Ready-set DAG executor over a ThreadPoolExecutor.

    A step is submitted only when every dependency is PASS/WAIVED. When a
    dependency FAILs or TIMEOUTs, dependents are marked SKIPPED
    (transitively). By default the first failure stops new submissions
    (in-flight steps still finish); --keep-going lets independent branches
    continue.
    """

    def __init__(
        self,
        flow: FlowSpec,
        max_workers: int = 4,
        keep_going: bool = False,
        evaluator: ResultEvaluator | None = None,
        on_complete: Callable[[StepResult], None] | None = None,
        step_factory: Callable[[StepSpec], Step] = ShellStep,
    ):
        self._flow = flow
        self._max_workers = max_workers
        self._keep_going = keep_going
        self._evaluator = evaluator
        self._on_complete = on_complete
        self._step_factory = step_factory

    def execute(self, run_dir: Path) -> dict[str, StepResult]:
        """Run the flow, returning a StepResult for every step in it."""
        pending: dict[str, StepSpec] = {s.id: s for s in self._flow.steps}
        statuses: dict[str, StepStatus] = {}
        results: dict[str, StepResult] = {}
        futures: dict[Future, str] = {}
        stop_submitting = False

        def record(result: StepResult) -> None:
            results[result.step_id] = result
            statuses[result.step_id] = result.status
            if self._on_complete:
                self._on_complete(result)

        def skip(sid: str) -> None:
            del pending[sid]
            record(StepResult(sid, StepStatus.SKIPPED, None, 0.0, ""))

        def flush_ready(pool: ThreadPoolExecutor) -> None:
            # Loop to a fixpoint so SKIPPED cascades through the DAG.
            progressed = True
            while progressed:
                progressed = False
                for sid, spec in list(pending.items()):
                    dep_statuses = [statuses.get(d) for d in spec.depends_on]
                    if any(ds in BLOCKING_STATUSES for ds in dep_statuses):
                        skip(sid)
                        progressed = True
                    elif not stop_submitting and all(
                        ds in PASSING_STATUSES for ds in dep_statuses
                    ):
                        futures[pool.submit(self._run_step, spec, run_dir)] = sid
                        del pending[sid]
                        progressed = True

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            flush_ready(pool)
            while futures:
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for fut in done:
                    del futures[fut]
                    result = fut.result()
                    record(result)
                    if result.status not in PASSING_STATUSES and not self._keep_going:
                        stop_submitting = True
                flush_ready(pool)

        # Anything never submitted (stop-on-failure) counts as SKIPPED.
        for sid in list(pending):
            skip(sid)
        return results

    def _run_step(self, spec: StepSpec, run_dir: Path) -> StepResult:
        """Run (and evaluate) one step, with naive immediate retries.

        A step that only passes on a retry is marked flaky=True — it still
        satisfies its dependents, but the wobble stays visible.
        """
        for attempt in range(spec.retries + 1):
            result = self._step_factory(spec).run(run_dir)
            if self._evaluator is not None:
                result = self._evaluator.evaluate(spec, result)
            if result.status in PASSING_STATUSES:
                result.flaky = attempt > 0
                return result
        return result
