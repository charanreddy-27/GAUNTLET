"""Single-file HTML report rendering. stdlib only: string.Template + html.

Same data as the terminal report, but shareable: one self-contained file
with a step summary table and per-step log links + violation tables.
"""
from __future__ import annotations

import html
from string import Template

from .models import RunRecord, StepResult
from .report import run_duration_s

_PAGE = Template("""\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>gauntlet — $run_id</title>
<style>
  body { font-family: ui-monospace, Menlo, Consolas, monospace;
         margin: 2rem; background: #fafafa; color: #222; }
  h1 { font-size: 1.25rem; }
  h2 { font-size: 1rem; margin-top: 1.5rem; }
  table { border-collapse: collapse; margin: 0.8rem 0; background: #fff; }
  th, td { border: 1px solid #ccc; padding: 0.3rem 0.7rem; text-align: left; }
  th { background: #eee; }
  .PASS { color: #0a7a2f; font-weight: bold; }
  .FAIL { color: #c0182b; font-weight: bold; }
  .WAIVED { color: #b07300; font-weight: bold; }
  .TIMEOUT { color: #7a2fb0; font-weight: bold; }
  .SKIPPED { color: #777; font-weight: bold; }
  .waived-row { color: #888; }
</style>
</head>
<body>
<h1>FLOW $flow_name — $run_id — <span class="$status">$status</span></h1>
<p>$started_at → $finished_at (${duration}s)</p>
<table>
<tr><th>status</th><th>step</th><th>duration</th><th>exit</th>
<th>errors</th><th>warnings</th><th>log</th></tr>
$rows
</table>
$sections
</body>
</html>
""")

_ROW = Template(
    "<tr><td class=\"$status\">$status$flaky</td><td>$step_id</td>"
    "<td>${duration}s</td><td>$exit_code</td>"
    "<td>$errors</td><td>$warnings</td><td>$log_link</td></tr>"
)

_SECTION = Template("""\
<h2>$step_id — violations</h2>
<table>
<tr><th>rule</th><th>severity</th><th>line</th><th>message</th><th>waived</th></tr>
$vrows
</table>
""")

_VROW = Template(
    "<tr$cls><td>$rule_id</td><td>$severity</td><td>$line_no</td>"
    "<td>$message</td><td>$waived</td></tr>"
)


def render_html(record: RunRecord) -> str:
    """Render a full run as one self-contained HTML page."""
    rows = []
    sections = []
    for result in record.results.values():
        rows.append(_render_row(result))
        if result.violations:
            sections.append(_render_section(result))
    return _PAGE.substitute(
        run_id=html.escape(record.run_id),
        flow_name=html.escape(record.flow_name),
        status=html.escape(record.status),
        started_at=html.escape(record.started_at),
        finished_at=html.escape(record.finished_at),
        duration=f"{run_duration_s(record):.1f}",
        rows="\n".join(rows),
        sections="\n".join(sections),
    )


def _render_row(result: StepResult) -> str:
    errors = sum(1 for v in result.violations if v.severity == "ERROR")
    warnings = sum(1 for v in result.violations if v.severity == "WARNING")
    log_link = (
        f'<a href="{html.escape(result.log_path)}">output.log</a>'
        if result.log_path
        else "—"
    )
    return _ROW.substitute(
        status=html.escape(result.status.value),
        flaky=" (flaky)" if result.flaky else "",
        step_id=html.escape(result.step_id),
        duration=f"{result.duration_s:.2f}",
        exit_code="—" if result.exit_code is None else result.exit_code,
        errors=errors,
        warnings=warnings,
        log_link=log_link,
    )


def _render_section(result: StepResult) -> str:
    vrows = [
        _VROW.substitute(
            cls=' class="waived-row"' if v.waived else "",
            rule_id=html.escape(v.rule_id),
            severity=html.escape(v.severity),
            line_no=v.line_no,
            message=html.escape(
                v.message + (f" — waived: {v.waive_reason}" if v.waive_reason else "")
            ),
            waived="yes" if v.waived else "no",
        )
        for v in result.violations
    ]
    return _SECTION.substitute(
        step_id=html.escape(result.step_id), vrows="\n".join(vrows)
    )
