"""Waivers: known, documented exceptions to failing violations.

A waiver hits when rule_id matches exactly AND its 'match' string appears
in the violation message. Waived ERRORs turn a would-be FAIL into WAIVED.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ..models import Violation


class WaiverError(Exception):
    """The waiver file is structurally invalid."""


@dataclass(frozen=True)
class Waiver:
    """One documented exception, with an owner and a reason (audit trail)."""

    rule_id: str
    match: str
    reason: str
    owner: str = ""

    def applies_to(self, violation: Violation) -> bool:
        return self.rule_id == violation.rule_id and self.match in violation.message


def load_waivers(path: str | Path) -> tuple[Waiver, ...]:
    """Load waivers YAML. A missing file simply means no waivers."""
    path = Path(path)
    if not path.exists():
        return ()
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise WaiverError(f"invalid YAML in {path}: {exc}") from None
    if not data:
        return ()
    if not isinstance(data, dict) or not isinstance(data.get("waivers"), list):
        raise WaiverError(f"{path}: expected mapping with a 'waivers' list")

    waivers: list[Waiver] = []
    for i, raw in enumerate(data["waivers"]):
        if not isinstance(raw, dict) or "rule_id" not in raw or "match" not in raw:
            raise WaiverError(f"{path}: waiver #{i} needs 'rule_id' and 'match'")
        waivers.append(
            Waiver(
                rule_id=str(raw["rule_id"]),
                match=str(raw["match"]),
                reason=str(raw.get("reason", "")),
                owner=str(raw.get("owner", "")),
            )
        )
    return tuple(waivers)


def apply_waivers(violations: list[Violation], waivers: tuple[Waiver, ...]) -> None:
    """Mark each violation matched by a waiver (in place)."""
    for violation in violations:
        for waiver in waivers:
            if waiver.applies_to(violation):
                violation.waived = True
                violation.waive_reason = waiver.reason
                violation.waive_owner = waiver.owner or None
                break
