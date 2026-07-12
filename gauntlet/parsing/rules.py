"""Rulepack loading: YAML -> compiled regex rules.

Regexes are compiled exactly once, at load time. An invalid pattern is a
config error at startup (exit 2), never a surprise mid-run.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

SEVERITIES = ("ERROR", "WARNING", "INFO")


class RulepackError(Exception):
    """A rulepack file is missing or structurally invalid (incl. bad regex)."""


@dataclass(frozen=True)
class Rule:
    """One classification rule: a compiled pattern with an id and severity."""

    id: str
    pattern: re.Pattern
    severity: str


@dataclass(frozen=True)
class Rulepack:
    """An ordered set of rules for one tool's log format (first match wins)."""

    tool: str
    rules: tuple[Rule, ...]


def load_rulepack(path: str | Path) -> Rulepack:
    """Load and compile one rulepack YAML file."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text())
    except FileNotFoundError:
        raise RulepackError(f"rulepack not found: {path}") from None
    except yaml.YAMLError as exc:
        raise RulepackError(f"invalid YAML in {path}: {exc}") from None
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise RulepackError(f"{path}: expected mapping with a 'rules' list")

    rules: list[Rule] = []
    for i, raw in enumerate(data["rules"]):
        if not isinstance(raw, dict) or "id" not in raw or "pattern" not in raw:
            raise RulepackError(f"{path}: rule #{i} needs 'id' and 'pattern'")
        severity = raw.get("severity", "ERROR")
        if severity not in SEVERITIES:
            raise RulepackError(
                f"{path}: rule '{raw['id']}': bad severity '{severity}'"
            )
        try:
            pattern = re.compile(raw["pattern"])
        except re.error as exc:
            raise RulepackError(
                f"{path}: rule '{raw['id']}': invalid regex: {exc}"
            ) from None
        rules.append(Rule(id=str(raw["id"]), pattern=pattern, severity=severity))

    return Rulepack(tool=str(data.get("tool", path.stem)), rules=tuple(rules))
