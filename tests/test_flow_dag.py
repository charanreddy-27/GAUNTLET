"""Flow loading and DAG validation."""
import pytest

from gauntlet.flow import FlowValidationError, build_flow, load_flow


def _flow(steps):
    return {"name": "t", "description": "", "steps": steps}


def test_valid_flow_parses(tmp_path):
    yaml_text = """
name: demo
description: d
defaults:
  timeout_s: 30
steps:
  - id: a
    cmd: "true"
  - id: b
    cmd: "true"
    depends_on: [a]
    timeout_s: 5
    rulepack: lint
"""
    path = tmp_path / "f.yaml"
    path.write_text(yaml_text)
    flow = load_flow(path)
    assert flow.name == "demo"
    assert [s.id for s in flow.steps] == ["a", "b"]
    assert flow.steps[0].timeout_s == 30  # default applied
    assert flow.steps[1].timeout_s == 5   # override wins
    assert flow.steps[1].depends_on == ("a",)
    assert flow.steps[1].rulepack == "lint"


def test_cycle_raises_with_cycle_path():
    steps = [
        {"id": "a", "cmd": "true", "depends_on": ["c"]},
        {"id": "b", "cmd": "true", "depends_on": ["a"]},
        {"id": "c", "cmd": "true", "depends_on": ["b"]},
    ]
    with pytest.raises(FlowValidationError) as exc:
        build_flow(_flow(steps))
    msg = str(exc.value)
    assert "cycle" in msg
    for sid in ("a", "b", "c"):
        assert sid in msg


def test_self_cycle_raises():
    with pytest.raises(FlowValidationError, match="cycle"):
        build_flow(_flow([{"id": "a", "cmd": "true", "depends_on": ["a"]}]))


def test_unknown_dep_raises():
    steps = [{"id": "a", "cmd": "true", "depends_on": ["ghost"]}]
    with pytest.raises(FlowValidationError, match="unknown step 'ghost'"):
        build_flow(_flow(steps))


def test_duplicate_id_raises():
    steps = [{"id": "a", "cmd": "true"}, {"id": "a", "cmd": "false"}]
    with pytest.raises(FlowValidationError, match="duplicate step id"):
        build_flow(_flow(steps))


def test_missing_steps_raises():
    with pytest.raises(FlowValidationError, match="steps"):
        build_flow({"name": "t"})


def test_missing_flow_file_raises(tmp_path):
    with pytest.raises(FlowValidationError, match="not found"):
        load_flow(tmp_path / "nope.yaml")
