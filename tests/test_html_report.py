"""Phase 5 stretch: single-file HTML report."""
from gauntlet.html_report import render_html
from gauntlet.models import RunRecord, StepResult, StepStatus, Violation


def _record():
    results = {
        "lint": StepResult(
            "lint", StepStatus.FAIL, 1, 1.5, "runs/run_x/lint/output.log",
            violations=[
                Violation("LINT-201", "ERROR", 4, "latch <inferred> & bad"),
            ],
        ),
        "sim": StepResult("sim", StepStatus.PASS, 0, 2.0,
                          "runs/run_x/sim/output.log", flaky=True),
        "synth": StepResult("synth", StepStatus.SKIPPED, None, 0.0, ""),
    }
    return RunRecord(
        run_id="run_x", flow_name="smoke",
        started_at="2026-07-14T09:32:00", finished_at="2026-07-14T09:32:04",
        status="FAIL", results=results,
    )


def test_html_report_contains_steps_links_and_violations():
    page = render_html(_record())
    assert "<!DOCTYPE html>" in page
    assert 'href="runs/run_x/lint/output.log"' in page
    assert "LINT-201" in page
    assert "latch &lt;inferred&gt; &amp; bad" in page  # escaped
    assert "(flaky)" in page
    assert "SKIPPED" in page


def test_html_report_no_link_for_skipped_step():
    page = render_html(_record())
    # skipped step has no log; renders an em-dash cell, not an empty href
    assert 'href=""' not in page
