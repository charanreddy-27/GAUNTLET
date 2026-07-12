"""Terminal report rendering. Pure formatting: data in, string out."""
from __future__ import annotations

from datetime import datetime

from .models import RunRecord, StepResult, StepStatus

_MAX_MSG = 60


def render_run(record: RunRecord) -> str:
    """Render the end-of-run (or stored-run) report."""
    lines = [
        f"FLOW {record.flow_name} — {record.run_id} — {record.status}"
        f" ({run_duration_s(record):.1f}s)"
    ]
    counts = {status: 0 for status in StepStatus}
    total_errors = total_waived = total_warnings = 0
    for result in record.results.values():
        counts[result.status] += 1
        errors = [v for v in result.violations if v.severity == "ERROR"]
        total_errors += len(errors)
        total_waived += sum(1 for v in errors if v.waived)
        total_warnings += sum(1 for v in result.violations if v.severity == "WARNING")
        lines.append(
            f"  {result.status.value:<8} {result.step_id:<18}{_detail(result)}"
        )
    lines.append(
        f"  totals: {counts[StepStatus.PASS]} pass, {counts[StepStatus.WAIVED]} waived,"
        f" {counts[StepStatus.FAIL]} fail, {counts[StepStatus.TIMEOUT]} timeout,"
        f" {counts[StepStatus.SKIPPED]} skipped"
        f" · {total_errors} errors ({total_waived} waived)"
        f" · {total_warnings} warnings"
    )
    return "\n".join(lines)


def run_duration_s(record: RunRecord) -> float:
    try:
        start = datetime.fromisoformat(record.started_at)
        end = datetime.fromisoformat(record.finished_at)
        return (end - start).total_seconds()
    except ValueError:
        return 0.0


def _detail(result: StepResult) -> str:
    errors = [v for v in result.violations if v.severity == "ERROR"]
    warnings = sum(1 for v in result.violations if v.severity == "WARNING")
    if result.status == StepStatus.SKIPPED:
        return "upstream failure"
    if result.status == StepStatus.TIMEOUT:
        return "timed out"
    if result.status == StepStatus.FAIL:
        unwaived = [v for v in errors if not v.waived]
        if unwaived:
            first = unwaived[0]
            noun = "error" if len(unwaived) == 1 else "errors"
            return (
                f"{len(unwaived)} {noun} [{first.rule_id}] "
                f"{_truncate(first.message)}"
            )
        return f"exit code {result.exit_code}"
    if result.status == StepStatus.WAIVED:
        noun = "error" if len(errors) == 1 else "errors"
        reason = next((v.waive_reason for v in errors if v.waive_reason), "")
        suffix = f" ({_truncate(reason, 48)})" if reason else ""
        return f"{len(errors)} {noun} waived{suffix}"
    if warnings:
        noun = "warning" if warnings == 1 else "warnings"
        return f"{warnings} {noun}"
    return "clean"


def _truncate(text: str, limit: int = _MAX_MSG) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."
