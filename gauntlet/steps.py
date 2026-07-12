"""Step execution: HOW a unit of work runs.

Step is an ABC because the scheduler's contract is just run() -> StepResult;
ShellStep is one implementation. A future PythonStep or RemoteStep would
touch zero scheduler code.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path

from .models import StepResult, StepSpec, StepStatus


class Step(ABC):
    """A unit of executable work in a flow. Subclasses define HOW to run;
    the Scheduler decides WHEN."""

    def __init__(self, spec: StepSpec):
        self.spec = spec

    @abstractmethod
    def run(self, run_dir: Path) -> StepResult:
        """Execute this step, writing artifacts under run_dir/<step_id>/."""


class ShellStep(Step):
    """Runs spec.cmd as a subprocess in its own process group, captures
    stdout+stderr to <run_dir>/<step_id>/output.log, and enforces timeout
    with SIGTERM -> grace period -> SIGKILL on the whole process group."""

    GRACE_S = 3.0

    def run(self, run_dir: Path) -> StepResult:
        step_dir = run_dir / self.spec.id
        step_dir.mkdir(parents=True, exist_ok=True)
        log_path = step_dir / "output.log"

        start = time.monotonic()
        with open(log_path, "wb") as log:
            # start_new_session=True puts the child in its own process group,
            # so a timeout kill takes down the whole tree, not just the shell.
            proc = subprocess.Popen(
                self.spec.cmd,
                shell=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                exit_code: int | None = proc.wait(timeout=self.spec.timeout_s)
                status = StepStatus.PASS if exit_code == 0 else StepStatus.FAIL
            except subprocess.TimeoutExpired:
                self._kill_process_group(proc)
                exit_code = None
                status = StepStatus.TIMEOUT

        return StepResult(
            step_id=self.spec.id,
            status=status,
            exit_code=exit_code,
            duration_s=round(time.monotonic() - start, 3),
            log_path=str(log_path),
        )

    def _kill_process_group(self, proc: subprocess.Popen) -> None:
        """SIGTERM the group, give it GRACE_S to clean up, then SIGKILL."""
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            return
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=self.GRACE_S)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
