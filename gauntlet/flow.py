"""Flow YAML loading and validation: unique ids, known deps, no cycles.

All structural errors are raised as FlowValidationError before anything
executes — a broken flow must fail fast, not mid-run.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .models import FlowSpec, StepSpec


class FlowValidationError(Exception):
    """The flow YAML is structurally invalid (bad schema, unknown dep, cycle)."""


def load_flow(path: str | Path) -> FlowSpec:
    """Parse a flow YAML file into a validated FlowSpec."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text())
    except FileNotFoundError:
        raise FlowValidationError(f"flow file not found: {path}") from None
    except yaml.YAMLError as exc:
        raise FlowValidationError(f"invalid YAML in {path}: {exc}") from None
    if not isinstance(data, dict):
        raise FlowValidationError(f"{path}: top level must be a mapping")
    return build_flow(data, source=str(path))


def build_flow(data: dict, source: str = "<memory>") -> FlowSpec:
    """Build and validate a FlowSpec from already-parsed YAML data."""
    name = data.get("name")
    if not name or not isinstance(name, str):
        raise FlowValidationError(f"{source}: 'name' is required")
    description = str(data.get("description", ""))
    defaults = data.get("defaults") or {}
    default_timeout = int(defaults.get("timeout_s", 60))

    raw_steps = data.get("steps")
    if not raw_steps or not isinstance(raw_steps, list):
        raise FlowValidationError(f"{source}: 'steps' must be a non-empty list")

    steps: list[StepSpec] = []
    for i, raw in enumerate(raw_steps):
        if not isinstance(raw, dict) or "id" not in raw or "cmd" not in raw:
            raise FlowValidationError(f"{source}: step #{i} needs 'id' and 'cmd'")
        deps = raw.get("depends_on") or []
        if not isinstance(deps, list):
            raise FlowValidationError(f"{source}: step '{raw['id']}': depends_on must be a list")
        steps.append(
            StepSpec(
                id=str(raw["id"]),
                cmd=str(raw["cmd"]),
                depends_on=tuple(str(d) for d in deps),
                rulepack=raw.get("rulepack"),
                timeout_s=int(raw.get("timeout_s", default_timeout)),
                retries=int(raw.get("retries", 0)),
            )
        )

    _validate_steps(steps, source)
    return FlowSpec(name=name, description=description, steps=tuple(steps))


def _validate_steps(steps: list[StepSpec], source: str) -> None:
    ids = [s.id for s in steps]
    seen: set[str] = set()
    for sid in ids:
        if sid in seen:
            raise FlowValidationError(f"{source}: duplicate step id '{sid}'")
        seen.add(sid)

    for step in steps:
        for dep in step.depends_on:
            if dep not in seen:
                raise FlowValidationError(
                    f"{source}: step '{step.id}' depends on unknown step '{dep}'"
                )

    cycle = _find_cycle({s.id: s.depends_on for s in steps})
    if cycle:
        raise FlowValidationError(f"{source}: dependency cycle: {' -> '.join(cycle)}")


def _find_cycle(deps: dict[str, tuple[str, ...]]) -> list[str] | None:
    """DFS three-color cycle search. Returns the cycle path (closed) or None."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {sid: WHITE for sid in deps}
    stack: list[str] = []

    def visit(sid: str) -> list[str] | None:
        color[sid] = GRAY
        stack.append(sid)
        for dep in deps[sid]:
            if color[dep] == GRAY:
                start = stack.index(dep)
                return stack[start:] + [dep]
            if color[dep] == WHITE:
                found = visit(dep)
                if found:
                    return found
        stack.pop()
        color[sid] = BLACK
        return None

    for sid in deps:
        if color[sid] == WHITE:
            found = visit(sid)
            if found:
                return found
    return None
