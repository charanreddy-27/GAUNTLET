"""Step stability across run history — the question a single run can't answer.

`diff` tells you what changed between two runs. Stats tells you which steps
keep changing: a step that flips PASS → FAIL → PASS across a week of nightlies
is noise until someone owns it, and noise is how real regressions hide.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import PASSING_STATUSES, RunRecord, StepStatus

FAILING = frozenset({StepStatus.FAIL, StepStatus.TIMEOUT})

GLYPH = {
    StepStatus.PASS: "✓",
    StepStatus.WAIVED: "w",
    StepStatus.FAIL: "✗",
    StepStatus.TIMEOUT: "T",
    StepStatus.SKIPPED: "·",
}
# For consoles that can't encode the above (a Windows pipe is cp1252).
GLYPH_ASCII = {
    StepStatus.PASS: "+",
    StepStatus.WAIVED: "w",
    StepStatus.FAIL: "x",
    StepStatus.TIMEOUT: "T",
    StepStatus.SKIPPED: ".",
}


@dataclass
class StepStats:
    """One step's track record over a window of runs, oldest first."""

    step_id: str
    statuses: list[StepStatus | None] = field(default_factory=list)  # None = absent
    durations: list[float] = field(default_factory=list)
    flaky: int = 0
    last_failure: str | None = None

    @property
    def executed(self) -> list[StepStatus]:
        return [s for s in self.statuses if s is not None and s != StepStatus.SKIPPED]

    @property
    def passed(self) -> int:
        return sum(1 for s in self.executed if s in PASSING_STATUSES)

    @property
    def failed(self) -> int:
        return sum(1 for s in self.executed if s in FAILING)

    @property
    def pass_rate(self) -> float | None:
        ran = self.executed
        return self.passed / len(ran) if ran else None

    @property
    def flips(self) -> int:
        """Pass/fail changes between consecutive executions."""
        outcome = [s in FAILING for s in self.executed]
        return sum(1 for a, b in zip(outcome, outcome[1:], strict=False) if a != b)

    @property
    def mean_duration(self) -> float | None:
        return sum(self.durations) / len(self.durations) if self.durations else None

    @property
    def p95_duration(self) -> float | None:
        if not self.durations:
            return None
        ordered = sorted(self.durations)
        return ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]

    @property
    def strip(self) -> str:
        return self.render_strip(GLYPH)

    def render_strip(self, glyphs: dict[StepStatus, str]) -> str:
        return "".join(" " if s is None else glyphs[s] for s in self.statuses)

    @property
    def verdict(self) -> str:
        ran = self.executed
        if not ran:
            return "never ran"
        if ran[-1] in FAILING:
            return "failing"
        if self.flips >= 2 or self.flaky:
            return "flaky"
        if self.failed:
            return "recovered"
        return "stable"


def compute_stats(runs: list[RunRecord]) -> list[StepStats]:
    """Per-step stability over `runs` (oldest first), in first-seen order."""
    order: list[str] = []
    for run in runs:
        for sid in (run.dag or run.results):
            if sid not in order:
                order.append(sid)
    table = {sid: StepStats(sid) for sid in order}
    for run in runs:
        for sid, stats in table.items():
            result = run.results.get(sid)
            stats.statuses.append(result.status if result else None)
            if result is None:
                continue
            if result.status != StepStatus.SKIPPED:
                stats.durations.append(result.duration_s)
            if result.flaky:
                stats.flaky += 1
            if result.status in FAILING:
                stats.last_failure = run.run_id
    return list(table.values())


def render_stats(
    flow_name: str, runs: list[RunRecord], stats: list[StepStats], ascii_only: bool = False
) -> str:
    """`gauntlet stats` as a fixed-width table."""
    glyphs = GLYPH_ASCII if ascii_only else GLYPH
    if not runs:
        return f"no runs recorded for flow {flow_name!r}"
    width = max([len(s.step_id) for s in stats] + [4])
    strip_w = max(len(runs), 7)
    lines = [
        f"STABILITY {flow_name} — last {len(runs)} run(s), oldest → newest",
        "",
        f"  {'STEP':<{width}}  {'HISTORY':<{strip_w}}  {'PASS%':>5}  {'FLIPS':>5}"
        f"  {'FLAKY':>5}  {'MEAN':>7}  {'P95':>7}  VERDICT",
    ]
    for s in stats:
        rate = "—" if s.pass_rate is None else f"{100 * s.pass_rate:.0f}%"
        mean = "—" if s.mean_duration is None else f"{s.mean_duration:.2f}s"
        p95 = "—" if s.p95_duration is None else f"{s.p95_duration:.2f}s"
        lines.append(
            f"  {s.step_id:<{width}}  {s.render_strip(glyphs):<{strip_w}}  {rate:>5}  {s.flips:>5}"
            f"  {s.flaky:>5}  {mean:>7}  {p95:>7}  {s.verdict}"
        )
    noisy = [s.step_id for s in stats if s.verdict in ("flaky", "failing")]
    legend = "  ".join(f"{glyphs[st]} {st.value.lower()}" for st in GLYPH)
    lines += ["", f"  legend: {legend}"]
    if noisy:
        lines.append(f"  needs an owner: {', '.join(noisy)}")
    return "\n".join(lines)
