"""Waiver matching matrix and WAIVED status computation."""
from gauntlet.models import StepResult, StepStatus, Violation
from gauntlet.parsing.parser import finalize_status
from gauntlet.parsing.waivers import Waiver, apply_waivers, load_waivers

WAIVER = Waiver(
    rule_id="SIM-ERR-007",
    match="u_fifo_rx",
    reason="Known TB artifact",
    owner="charan",
)


def _violation(rule_id="SIM-ERR-007", message="fifo overflow in u_fifo_rx"):
    return Violation(rule_id=rule_id, severity="ERROR", line_no=1, message=message)


def test_matching_rule_and_substring_waives():
    v = _violation()
    apply_waivers([v], (WAIVER,))
    assert v.waived is True
    assert v.waive_reason == "Known TB artifact"


def test_wrong_rule_id_does_not_waive():
    v = _violation(rule_id="SIM-ERR-999")
    apply_waivers([v], (WAIVER,))
    assert v.waived is False


def test_wrong_substring_does_not_waive():
    v = _violation(message="fifo overflow in u_fifo_tx")
    apply_waivers([v], (WAIVER,))
    assert v.waived is False


def test_all_errors_waived_gives_waived_status():
    v = _violation()
    apply_waivers([v], (WAIVER,))
    result = StepResult("s", StepStatus.FAIL, 1, 0.1, "x", violations=[v])
    assert finalize_status(result) == StepStatus.WAIVED


def test_mixed_waived_and_unwaived_still_fails():
    waived = _violation()
    unwaived = _violation(message="fifo overflow in u_fifo_tx")
    apply_waivers([waived, unwaived], (WAIVER,))
    result = StepResult("s", StepStatus.PASS, 0, 0.1, "x",
                        violations=[waived, unwaived])
    assert finalize_status(result) == StepStatus.FAIL


def test_load_waivers_missing_file_is_empty(tmp_path):
    assert load_waivers(tmp_path / "nope.yaml") == ()


def test_load_waivers_yaml(tmp_path):
    path = tmp_path / "waivers.yaml"
    path.write_text(
        "waivers:\n"
        "  - rule_id: LINT-042\n"
        "    match: clk_en\n"
        "    reason: legacy\n"
        "    owner: charan\n"
    )
    waivers = load_waivers(path)
    assert waivers == (
        Waiver(rule_id="LINT-042", match="clk_en", reason="legacy", owner="charan"),
    )
