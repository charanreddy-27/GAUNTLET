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

IS_WINDOWS = os.name == "nt"

# Put the child in its own process group so a timeout kill takes down the
# whole tree, not just the shell wrapper. POSIX gets a new session; Windows
# gets a new process group (the closest thing it has, and the only way to
# deliver CTRL_BREAK_EVENT to a child).
_GROUP_KWARGS = (
    {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    if IS_WINDOWS
    else {"start_new_session": True}
)


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
    with a polite signal -> grace period -> hard kill on the whole group."""

    GRACE_S = 3.0

    def run(self, run_dir: Path) -> StepResult:
        step_dir = run_dir / self.spec.id
        step_dir.mkdir(parents=True, exist_ok=True)
        log_path = step_dir / "output.log"

        start = time.monotonic()
        with open(log_path, "wb") as log:
            proc = subprocess.Popen(
                self.spec.cmd,
                shell=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                **_GROUP_KWARGS,
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
        """Signal the group, give it GRACE_S to clean up, then kill it hard."""
        if IS_WINDOWS:
            self._kill_windows(proc)
        else:
            self._kill_posix(proc)

    def _kill_posix(self, proc: subprocess.Popen) -> None:
        """SIGTERM the process group, wait GRACE_S, then SIGKILL it."""
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

    def _kill_windows(self, proc: subprocess.Popen) -> None:
        """CTRL_BREAK the group, wait GRACE_S, then `taskkill /T /F` the tree.

        Windows has no SIGTERM. CTRL_BREAK_EVENT is the closest polite
        equivalent (a console app gets a chance to unwind); it needs a
        console, so a headless parent falls straight through to taskkill,
        which is the only call that reliably reaps grandchildren.
        """
        try:
            os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
            proc.wait(timeout=self.GRACE_S)
            return
        except (OSError, subprocess.TimeoutExpired):
            pass
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        proc.wait()
