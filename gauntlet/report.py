"""Terminal report rendering. Pure formatting: data in, string out."""
from __future__ import annotations

from datetime import datetime

from .diff import RunDiff
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
        flaky = (
            f" (flaky: passed on attempt {result.attempts})" if result.flaky else ""
        )
        lines.append(
            f"  {result.status.value:<8} {result.step_id:<18}{_detail(result)}{flaky}"
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
    """Wall-clock length of a run.

    Step windows are measured on a monotonic clock to the millisecond, so they
    win when present; the ISO timestamps (second precision) are the fallback
    for runs recorded before v0.2.
    """
    ends = [r.end_s for r in record.results.values() if r.end_s is not None]
    if ends:
        return max(ends)
    return _iso_delta_s(record.started_at, record.finished_at)


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


def render_history(rows: list[dict]) -> str:
    """Render `gauntlet history` as a fixed-width table."""
    if not rows:
        return "no runs recorded yet"
    with_commit = any(row.get("git_commit") for row in rows)
    header = f"{'RUN':<24} {'FLOW':<20} {'STATUS':<7} {'DURATION':>9}  #FAIL"
    lines = [header + ("  COMMIT" if with_commit else "")]
    for row in rows:
        duration = row.get("duration_s")
        if duration is None:
            duration = _iso_delta_s(row["started_at"], row["finished_at"])
        line = (
            f"{row['run_id']:<24} {row['flow_name']:<20} {row['status']:<7}"
            f" {duration:>8.1f}s  {row['failed_steps']:<5}"
        )
        if with_commit:
            commit = (row.get("git_commit") or "")[:8]
            branch = row.get("git_branch") or ""
            line += f"  {commit} {branch}".rstrip()
        lines.append(line.rstrip())
    return "\n".join(lines)


def render_diff(diff: RunDiff) -> str:
    """Render `gauntlet diff` with the four regression buckets."""
    lines = [f"DIFF {diff.run_a} → {diff.run_b} (flow: {diff.flow_name})", ""]

    lines.append(f"NEW FAILURES ({len(diff.new_failures)})")
    for r in diff.new_failures:
        lines.append(f"  {r.step_id:<18}{_failure_detail(r)}")
    lines.append("")

    lines.append(f"FIXED ({len(diff.fixed)})")
    for r in diff.fixed:
        lines.append(f"  {r.step_id:<18}was failing, now {r.status.value}")
    lines.append("")

    lines.append(f"STILL FAILING ({len(diff.still_failing)})")
    for r in diff.still_failing:
        lines.append(f"  {r.step_id:<18}{_failure_detail(r)}")
    lines.append(f"UNCHANGED PASS ({len(diff.unchanged_pass)})")
    if diff.new_steps:
        lines.append(f"NEW STEPS ({len(diff.new_steps)}): {', '.join(diff.new_steps)}")
    if diff.removed_steps:
        lines.append(
            f"REMOVED STEPS ({len(diff.removed_steps)}): {', '.join(diff.removed_steps)}"
        )
    lines.append(f"verdict: {diff.verdict_line()}")
    return "\n".join(lines)


def _failure_detail(result: StepResult) -> str:
    if result.status == StepStatus.TIMEOUT:
        return "timed out"
    unwaived = [
        v for v in result.violations if v.severity == "ERROR" and not v.waived
    ]
    if unwaived:
        first = unwaived[0]
        return f"[{first.rule_id}] {_truncate(first.message)}"
    return f"exit code {result.exit_code}"


def _iso_delta_s(start: str, end: str) -> float:
    try:
        return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
    except (ValueError, TypeError):
        return 0.0
