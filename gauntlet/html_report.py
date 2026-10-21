"""Single-file HTML reports. stdlib only.

`report <run> --html out.html` writes one self-contained page — KPIs, the flow
graph, a timeline of what ran when, every violation (filterable) and the
waiver debt with owners. It opens offline and survives being emailed or
attached to a CI run; `gauntlet serve` renders the same page live.
"""
from __future__ import annotations

import os
from pathlib import Path

from .diff import RunDiff
from .models import RunRecord, StepResult
from .ui.pages import FILTER_SCRIPT, LogHref, diff_body, page, run_body


def relative_log_href(html_path: str | Path) -> LogHref:
    """Log links that resolve from wherever the HTML file is written."""
    base = Path(html_path).resolve().parent

    def href(result: StepResult) -> str | None:
        if not result.log_path:
            return None
        target = Path(result.log_path).resolve()
        try:
            rel = os.path.relpath(target, base)
        except ValueError:  # different drive on Windows
            return target.as_uri()
        return Path(rel).as_posix()

    return href


def _raw_log_href(result: StepResult) -> str | None:
    return result.log_path or None


def render_html(record: RunRecord, log_href: LogHref | None = None) -> str:
    """Render a full run as one self-contained HTML page.

    By default log links are the stored paths as-is (relative to where the run
    happened); pass `relative_log_href(out_path)` to make them resolve from the
    report's own location.
    """
    body = run_body(record, log_href or _raw_log_href)
    return page(
        f"{record.status} · {record.flow_name} · {record.run_id} — gauntlet",
        body,
        scripts=FILTER_SCRIPT,
    )


def render_diff_html(diff: RunDiff, run_a: RunRecord, run_b: RunRecord) -> str:
    """Render a run-to-run diff as one self-contained HTML page."""
    body = diff_body(diff, run_a, run_b, run_href=lambda run_id: f"#{run_id}")
    return page(f"diff {diff.run_a} → {diff.run_b} — gauntlet", body, subtitle="diff")
