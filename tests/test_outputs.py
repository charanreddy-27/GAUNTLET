"""CI-facing outputs: JUnit XML, Markdown summaries, HTML report, terminal color."""
import xml.etree.ElementTree as ET

from gauntlet.diff import diff_runs
from gauntlet.html_report import relative_log_href, render_diff_html, render_html
from gauntlet.junit import render_junit
from gauntlet.markdown import render_diff_markdown, render_run_markdown
from gauntlet.models import RunRecord, StepResult, StepStatus, Violation
from gauntlet.term import paint


def _record(run_id="run_x", sim=StepStatus.WAIVED):
    sim_violations = [Violation("SIM-ERR-007", "ERROR", 6, "overflow in u_fifo_rx", True, "known TB", "charan")]
    if sim == StepStatus.FAIL:
        sim_violations.append(Violation("SIM-ERR-007", "ERROR", 9, "overflow | in u_fifo_tx <x>"))
    return RunRecord(
        run_id=run_id, flow_name="smoke",
        started_at="2026-07-14T09:32:00", finished_at="2026-07-14T09:32:04",
        status="FAIL" if sim == StepStatus.FAIL else "PASS",
        results={
            "lint": StepResult("lint", StepStatus.PASS, 0, 1.2, "runs/x/lint/output.log",
                               [Violation("LINT-088", "WARNING", 10, "no default")], start_s=0, end_s=1.2),
            "sim": StepResult("sim", sim, 1 if sim == StepStatus.FAIL else 0, 0.8,
                              "runs/x/sim/output.log", sim_violations, start_s=1.2, end_s=2.0),
            "slow": StepResult("slow", StepStatus.TIMEOUT, None, 5.0, "runs/x/slow/output.log",
                               start_s=1.2, end_s=6.2),
            "synth": StepResult("synth", StepStatus.SKIPPED, None, 0.0, "", attempts=0),
            "flaky": StepResult("flaky", StepStatus.PASS, 0, 0.3, "runs/x/flaky/output.log",
                                flaky=True, attempts=2, start_s=0, end_s=0.9),
        },
        dag={"lint": [], "sim": ["lint"], "slow": ["lint"], "synth": ["sim", "slow"], "flaky": []},
        git_commit="0123456789abcdef", git_branch="main",
    )  # fmt: skip


def test_junit_maps_every_status_and_parses():
    root = ET.fromstring(render_junit(_record(sim=StepStatus.FAIL)))
    suite = root.find("testsuite")
    assert (suite.get("tests"), suite.get("failures"), suite.get("errors"), suite.get("skipped")) == ("5", "1", "1", "1")
    cases = {c.get("name"): c for c in suite.findall("testcase")}
    fail = cases["sim"].find("failure")
    assert fail.get("type") == "SIM-ERR-007"
    assert "u_fifo_tx <x>" in fail.get("message")  # escaped on write, intact on read
    assert cases["slow"].find("error") is not None
    assert cases["synth"].find("skipped") is not None
    assert cases["lint"].find("failure") is None
    assert "WAIVED line 6" in cases["sim"].find("system-out").text
    props = {p.get("name"): p.get("value") for p in cases["flaky"].iter("property")}
    assert props["gauntlet.flaky"] == "true" and props["gauntlet.attempts"] == "2"


def test_junit_waived_step_passes_but_says_so():
    root = ET.fromstring(render_junit(_record()))
    sim = [c for c in root.iter("testcase") if c.get("name") == "sim"][0]
    assert sim.find("failure") is None
    status = [p.get("value") for p in sim.iter("property") if p.get("name") == "gauntlet.status"]
    assert status == ["WAIVED"]
    assert "owner charan" in sim.find("system-out").text


def test_markdown_summary_escapes_table_cells_and_draws_dag():
    md = render_run_markdown(_record(sim=StepStatus.FAIL))
    assert md.startswith("## GAUNTLET · smoke — ❌ FAIL")
    assert "`0123456789`" in md and "on `main`" in md
    assert "overflow \\| in u_fifo_tx" in md  # a raw | would break the table
    assert "```mermaid" in md and "class n_sim fail" in md
    assert "waived (charan): known TB" in md


def test_markdown_diff_lists_buckets():
    md = render_diff_markdown(diff_runs(_record("run_a"), _record("run_b", StepStatus.FAIL)))
    assert "REGRESSION" in md and "🔴 new failures | `sim`" in md


def test_html_report_has_dag_timeline_and_waiver_debt():
    page = render_html(_record(sim=StepStatus.FAIL))
    assert 'class="chart dag"' in page and 'class="chart gantt"' in page
    assert "Waiver debt" in page and "charan" in page
    assert "overflow | in u_fifo_tx &lt;x&gt;" in page
    assert 'id="violations"' in page and 'data-filter="unwaived"' in page
    assert "critical path" in page


def test_html_report_without_timing_degrades_gracefully():
    record = _record()
    for r in record.results.values():
        r.start_s = r.end_s = None
    record.dag = {}
    page = render_html(record)
    assert "No timing for this run" in page


def test_relative_log_href_resolves_from_the_report_location(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    href = relative_log_href(tmp_path / "reports" / "nightly" / "r.html")
    result = StepResult("lint", StepStatus.PASS, 0, 1.0, "runs/x/lint/output.log")
    assert href(result) == "../../runs/x/lint/output.log"
    assert href(StepResult("s", StepStatus.SKIPPED, None, 0, "")) is None


def test_html_diff_page():
    page = render_diff_html(diff_runs(_record("run_a"), _record("run_b", StepStatus.FAIL)), _record("run_a"), _record("run_b", StepStatus.FAIL))
    assert "REGRESSION" in page and "NEW FAILURE" in page


def test_paint_colors_status_words_only_when_enabled(monkeypatch):
    plain = "[  1.20s] FAIL     sim_unit"
    assert paint(plain, enabled=False) == plain
    colored = paint(plain, enabled=True)
    assert "\033[1;31mFAIL\033[0m" in colored and "sim_unit" in colored
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    assert paint(plain) == plain
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert paint(plain) != plain
