"""JUnit XML output: the lingua franca every CI system already renders.

One run becomes one <testsuite>; each step becomes a <testcase>. FAIL maps to
<failure>, TIMEOUT to <error> (the step never finished, so it has no verdict),
SKIPPED to <skipped>. WAIVED has no JUnit equivalent and must not vanish into
a plain pass, so it passes with the waived errors spelled out in <system-out>
and a `gauntlet.status` property — debt stays visible in every report.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from .models import RunRecord, StepResult, StepStatus
from .report import run_duration_s


def render_junit(record: RunRecord) -> str:
    results = list(record.results.values())
    failures = sum(1 for r in results if r.status == StepStatus.FAIL)
    errors = sum(1 for r in results if r.status == StepStatus.TIMEOUT)
    skipped = sum(1 for r in results if r.status == StepStatus.SKIPPED)
    total_time = f"{run_duration_s(record):.3f}"

    suites = ET.Element(
        "testsuites",
        name="gauntlet",
        tests=str(len(results)),
        failures=str(failures),
        errors=str(errors),
        skipped=str(skipped),
        time=total_time,
    )
    suite = ET.SubElement(
        suites,
        "testsuite",
        name=record.flow_name,
        tests=str(len(results)),
        failures=str(failures),
        errors=str(errors),
        skipped=str(skipped),
        time=total_time,
        timestamp=record.started_at,
    )
    props = ET.SubElement(suite, "properties")
    for key, value in (
        ("run_id", record.run_id),
        ("verdict", record.status),
        ("git_commit", record.git_commit),
        ("git_branch", record.git_branch),
    ):
        if value:
            ET.SubElement(props, "property", name=f"gauntlet.{key}", value=value)

    for result in results:
        suite.append(_testcase(record, result))

    ET.indent(suites)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(suites, encoding="unicode") + "\n"


def _testcase(record: RunRecord, result: StepResult) -> ET.Element:
    case = ET.Element(
        "testcase",
        classname=f"gauntlet.{record.flow_name}",
        name=result.step_id,
        time=f"{result.duration_s:.3f}",
    )
    props = ET.SubElement(case, "properties")
    ET.SubElement(props, "property", name="gauntlet.status", value=result.status.value)
    if result.flaky:
        ET.SubElement(props, "property", name="gauntlet.flaky", value="true")
    if result.attempts > 1:
        ET.SubElement(props, "property", name="gauntlet.attempts", value=str(result.attempts))

    if result.status == StepStatus.FAIL:
        unwaived = result.unwaived_errors
        if unwaived:
            first = unwaived[0]
            fail = ET.SubElement(case, "failure", message=f"[{first.rule_id}] {first.message}", type=first.rule_id)
            fail.text = "\n".join(
                f"line {v.line_no}: [{v.rule_id}] {v.message}" for v in unwaived
            )
        else:
            ET.SubElement(
                case, "failure", message=f"exit code {result.exit_code}", type="ExitCode"
            )
    elif result.status == StepStatus.TIMEOUT:
        ET.SubElement(case, "error", message="step timed out and was killed", type="Timeout")
    elif result.status == StepStatus.SKIPPED:
        ET.SubElement(case, "skipped", message="upstream dependency failed")

    notes = []
    for v in result.violations:
        if v.severity == "ERROR" and v.waived:
            owner = f" · owner {v.waive_owner}" if v.waive_owner else ""
            notes.append(f"WAIVED line {v.line_no}: [{v.rule_id}] {v.message} — {v.waive_reason}{owner}")
        elif v.severity == "WARNING":
            notes.append(f"WARNING line {v.line_no}: [{v.rule_id}] {v.message}")
    if result.flaky:
        notes.insert(0, f"FLAKY: passed only on attempt {result.attempts}")
    if result.log_path:
        notes.append(f"log: {result.log_path}")
    if notes:
        ET.SubElement(case, "system-out").text = "\n".join(notes)
    return case
