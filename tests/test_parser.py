"""Log classification: fixture log -> exact expected Violations."""
import pytest

from gauntlet.models import StepResult, StepStatus, Violation
from gauntlet.parsing.parser import finalize_status, parse_log
from gauntlet.parsing.rules import RulepackError, load_rulepack

LINT_RULEPACK = """
tool: lint
rules:
  - id: LINT-ANY-ERROR
    pattern: '\\[(LINT-\\d+)\\] ERROR: (?P<msg>.+)'
    severity: ERROR
  - id: LINT-ANY-WARNING
    pattern: '\\[(LINT-\\d+)\\] WARNING: (?P<msg>.+)'
    severity: WARNING
"""

FIXTURE_LOG = """INFO: lint pass starting for design 'ip_block_a'
[LINT-042] WARNING: signal 'clk_en' declared but never read (ctrl.v:118)
INFO: chatter line that matches nothing
[LINT-201] ERROR: latch inferred on 'state_q' (fsm.v:203)
INFO: lint complete: 1 warnings, 1 error
"""


@pytest.fixture
def rulepack(tmp_path):
    path = tmp_path / "lint.yaml"
    path.write_text(LINT_RULEPACK)
    return load_rulepack(path)


def test_fixture_log_yields_exact_violations(tmp_path, rulepack):
    log = tmp_path / "output.log"
    log.write_text(FIXTURE_LOG)
    violations = parse_log(log, rulepack)
    assert violations == [
        Violation(
            rule_id="LINT-042",
            severity="WARNING",
            line_no=2,
            message="signal 'clk_en' declared but never read (ctrl.v:118)",
        ),
        Violation(
            rule_id="LINT-201",
            severity="ERROR",
            line_no=4,
            message="latch inferred on 'state_q' (fsm.v:203)",
        ),
    ]


def test_rule_without_capture_uses_rulepack_id(tmp_path):
    path = tmp_path / "generic.yaml"
    path.write_text(
        "tool: generic\nrules:\n"
        "  - id: GEN-FATAL\n"
        "    pattern: 'FATAL: (?P<msg>.+)'\n"
        "    severity: ERROR\n"
    )
    rulepack = load_rulepack(path)
    log = tmp_path / "output.log"
    log.write_text("FATAL: segfault in optimizer\n")
    violations = parse_log(log, rulepack)
    assert violations == [
        Violation(
            rule_id="GEN-FATAL",
            severity="ERROR",
            line_no=1,
            message="segfault in optimizer",
        )
    ]


def test_first_matching_rule_wins(tmp_path):
    path = tmp_path / "overlap.yaml"
    path.write_text(
        "tool: overlap\nrules:\n"
        "  - id: SPECIFIC\n"
        "    pattern: 'ERROR: timing'\n"
        "    severity: ERROR\n"
        "  - id: BROAD\n"
        "    pattern: 'ERROR:'\n"
        "    severity: ERROR\n"
    )
    rulepack = load_rulepack(path)
    log = tmp_path / "output.log"
    log.write_text("ERROR: timing loop found\n")
    violations = parse_log(log, rulepack)
    assert len(violations) == 1
    assert violations[0].rule_id == "SPECIFIC"


def test_invalid_regex_is_config_error(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        "tool: bad\nrules:\n"
        "  - id: BROKEN\n"
        "    pattern: '(unclosed'\n"
        "    severity: ERROR\n"
    )
    with pytest.raises(RulepackError, match="invalid regex"):
        load_rulepack(path)


def _result(exit_code, violations, status=StepStatus.PASS):
    return StepResult(
        step_id="s", status=status, exit_code=exit_code,
        duration_s=0.1, log_path="x", violations=violations,
    )


def test_exit_zero_with_unwaived_error_fails():
    violations = [Violation("E-1", "ERROR", 3, "boom")]
    assert finalize_status(_result(0, violations)) == StepStatus.FAIL


def test_warnings_never_fail():
    violations = [Violation("W-1", "WARNING", 3, "meh")]
    assert finalize_status(_result(0, violations)) == StepStatus.PASS


def test_nonzero_exit_without_violations_fails():
    assert finalize_status(_result(3, [])) == StepStatus.FAIL


def test_timeout_is_sticky():
    assert (
        finalize_status(_result(None, [], status=StepStatus.TIMEOUT))
        == StepStatus.TIMEOUT
    )
