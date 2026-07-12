"""Log classification: stream a log file through a rulepack -> Violations.

Logs are streamed line by line, never read whole — real EDA logs run to
gigabytes. Also home of the pass/fail policy: a tool can exit 0 and still
FAIL on log content, which is exactly how real EDA flows behave.
"""
from __future__ import annotations

from pathlib import Path

from ..models import StepResult, StepSpec, StepStatus, Violation
from .rules import Rulepack
from .waivers import Waiver, apply_waivers


def parse_log(log_path: str | Path, rulepack: Rulepack) -> list[Violation]:
    """Classify each log line against the rulepack; first matching rule wins.

    The reported rule id is the one *captured* from the line when the
    pattern captures one (e.g. LINT-201), else the rulepack rule's own id.
    """
    violations: list[Violation] = []
    with open(log_path, "r", errors="replace") as fh:
        for line_no, line in enumerate(fh, start=1):
            for rule in rulepack.rules:
                match = rule.pattern.search(line)
                if not match:
                    continue
                message = match.groupdict().get("msg") or line.strip()
                captured_id = None
                if match.lastindex and match.group(1) != message:
                    captured_id = match.group(1)
                violations.append(
                    Violation(
                        rule_id=captured_id or rule.id,
                        severity=rule.severity,
                        line_no=line_no,
                        message=message,
                    )
                )
                break
    return violations


def finalize_status(result: StepResult) -> StepStatus:
    """Pass/fail policy after parsing + waivers.

    FAIL if exit code != 0 or any unwaived ERROR remains. If ERRORs exist
    but every one is waived, the step is WAIVED — visible, not silently
    PASS. TIMEOUT is sticky. WARNINGs never fail a step.
    """
    if result.status in (StepStatus.TIMEOUT, StepStatus.SKIPPED):
        return result.status
    errors = [v for v in result.violations if v.severity == "ERROR"]
    if any(not v.waived for v in errors):
        return StepStatus.FAIL
    if errors:
        return StepStatus.WAIVED
    return StepStatus.PASS if result.exit_code == 0 else StepStatus.FAIL


class LogEvaluator:
    """Scheduler plug-in: parse a finished step's log with its rulepack,
    apply waivers, and re-derive the final status."""

    def __init__(self, rulepacks: dict[str, Rulepack], waivers: tuple[Waiver, ...]):
        self._rulepacks = rulepacks
        self._waivers = waivers

    def evaluate(self, spec: StepSpec, result: StepResult) -> StepResult:
        if spec.rulepack and result.log_path:
            rulepack = self._rulepacks[spec.rulepack]
            result.violations = parse_log(result.log_path, rulepack)
            apply_waivers(result.violations, self._waivers)
        result.status = finalize_status(result)
        return result
