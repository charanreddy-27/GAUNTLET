"""GitHub-flavoured Markdown reports — for $GITHUB_STEP_SUMMARY and PR comments.

The same facts as the terminal report, shaped for where CI results are read:
a verdict line, a step table, the DAG as Mermaid (GitHub renders it inline),
and each step's violations folded away under <details>.
"""
from __future__ import annotations

from .diff import RunDiff
from .graph import record_dag, to_mermaid
from .models import RunRecord, StepResult, StepStatus
from .report import run_duration_s

ICON = {
    StepStatus.PASS: "🟢",
    StepStatus.WAIVED: "🟡",
    StepStatus.FAIL: "🔴",
    StepStatus.TIMEOUT: "🟣",
    StepStatus.SKIPPED: "⚪",
}


def _cell(text: str) -> str:
    """Make arbitrary log text safe inside a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ").replace("`", "'")


def render_run_markdown(record: RunRecord) -> str:
    results = list(record.results.values())
    counts = {s: sum(1 for r in results if r.status == s) for s in StepStatus}
    verdict = "✅ PASS" if record.status == "PASS" else "❌ FAIL"
    commit = f" · `{record.git_commit[:10]}`" if record.git_commit else ""
    branch = f" on `{record.git_branch}`" if record.git_branch else ""

    out = [
        f"## GAUNTLET · {record.flow_name} — {verdict}",
        "",
        f"`{record.run_id}` · {run_duration_s(record):.1f}s{commit}{branch}",
        "",
        " · ".join(
            f"{ICON[s]} {counts[s]} {s.value.lower()}" for s in StepStatus if counts[s]
        ),
        "",
        "| | step | duration | errors | warnings | notes |",
        "|---|---|---:|---:|---:|---|",
    ]
    for r in results:
        out.append(
            f"| {ICON[r.status]} **{r.status.value}** | `{r.step_id}` | "
            f"{r.duration_s:.2f}s | {len(r.errors)} | {len(r.warnings)} | {_cell(_note(r))} |"
        )

    dag = record_dag(record)
    if any(dag.values()):
        statuses = {sid: r.status for sid, r in record.results.items()}
        out += ["", "<details><summary>Flow graph</summary>", "", "```mermaid",
                to_mermaid(dag, statuses), "```", "", "</details>"]

    for r in results:
        if not r.violations:
            continue
        out += ["", f"<details><summary><code>{r.step_id}</code> — "
                    f"{len(r.violations)} violation(s)</summary>", "",
                "| rule | severity | line | message | waiver |",
                "|---|---|---:|---|---|"]
        for v in r.violations:
            waiver = ""
            if v.waived:
                owner = f" ({v.waive_owner})" if v.waive_owner else ""
                waiver = f"waived{owner}: {v.waive_reason or ''}"
            out.append(
                f"| `{v.rule_id}` | {v.severity} | {v.line_no} | {_cell(v.message)} | {_cell(waiver)} |"
            )
        out += ["", "</details>"]
    return "\n".join(out) + "\n"


def render_diff_markdown(diff: RunDiff) -> str:
    regress = bool(diff.new_failures)
    head = "❌ " if regress else "✅ "
    out = [
        f"## GAUNTLET diff — {head}{diff.verdict_line()}",
        "",
        f"`{diff.run_a}` → `{diff.run_b}` · flow `{diff.flow_name}`",
        "",
        "| bucket | steps |",
        "|---|---|",
    ]
    for label, items in (
        ("🔴 new failures", [r.step_id for r in diff.new_failures]),
        ("🟢 fixed", [r.step_id for r in diff.fixed]),
        ("🟠 still failing", [r.step_id for r in diff.still_failing]),
        ("⚪ unchanged pass", [r.step_id for r in diff.unchanged_pass]),
        ("➕ new steps", diff.new_steps),
        ("➖ removed steps", diff.removed_steps),
    ):
        if items:
            out.append(f"| {label} | {', '.join(f'`{s}`' for s in items)} |")
    return "\n".join(out) + "\n"


def _note(r: StepResult) -> str:
    if r.status == StepStatus.SKIPPED:
        return "upstream failure"
    if r.status == StepStatus.TIMEOUT:
        return "timed out"
    first = next(iter(r.unwaived_errors), None)
    if r.status == StepStatus.FAIL:
        return f"[{first.rule_id}] {first.message}" if first else f"exit code {r.exit_code}"
    parts = []
    if r.status == StepStatus.WAIVED:
        parts.append(f"{len(r.errors)} error(s) waived")
    if r.flaky:
        parts.append(f"flaky: passed on attempt {r.attempts}")
    return " · ".join(parts)
