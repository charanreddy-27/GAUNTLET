"""Inline SVG charts: the flow DAG, the run timeline, and the history trend.

Layout is computed here, in Python, so charts are plain markup: they render
in any browser, survive printing, and need no JavaScript.
"""
from __future__ import annotations

import math
from html import escape

from ..graph import critical_path, layers, record_dag
from ..models import RunRecord, StepResult, StepStatus

NODE_W, NODE_H, COL_GAP, ROW_GAP, PAD = 184, 52, 64, 16, 14


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _fmt_s(seconds: float) -> str:
    if seconds >= 60:
        m, s = divmod(seconds, 60)
        return f"{int(m)}m{s:04.1f}s"
    return f"{seconds:.2f}s"


def run_critical_path(record: RunRecord) -> list[str]:
    """The dependency chain that bounded this run's wall-clock time."""
    dag = record_dag(record)
    weight = {sid: r.duration_s for sid, r in record.results.items()}
    if not any(dag.values()):
        return []
    return critical_path(dag, weight)


def dag_svg(record: RunRecord, anchor_prefix: str = "step-") -> str:
    """The flow graph, nodes colored by status, critical path highlighted."""
    dag = record_dag(record)
    grouped = layers(dag)
    if not grouped:
        return ""
    crit = run_critical_path(record)
    crit_edges = set(zip(crit, crit[1:], strict=False))

    tallest = max(len(layer) for layer in grouped)
    height = PAD * 2 + tallest * NODE_H + (tallest - 1) * ROW_GAP
    width = PAD * 2 + len(grouped) * NODE_W + (len(grouped) - 1) * COL_GAP

    pos: dict[str, tuple[float, float]] = {}
    for col, layer in enumerate(grouped):
        col_h = len(layer) * NODE_H + (len(layer) - 1) * ROW_GAP
        y0 = (height - col_h) / 2
        for row, sid in enumerate(layer):
            pos[sid] = (PAD + col * (NODE_W + COL_GAP), y0 + row * (NODE_H + ROW_GAP))

    parts = [
        f'<svg class="chart dag" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Flow dependency graph with {len(dag)} steps" '
        f'style="min-width:{min(width, 560)}px;max-width:{width}px;margin:0 auto">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse"><path d="M0 0 10 5 0 10z" '
        'fill="currentColor"/></marker></defs>',
        '<style>svg.dag text.stat{stroke:none}</style>',
    ]
    for sid, deps in dag.items():
        for dep in deps:
            if dep not in pos:
                continue
            x1, y1 = pos[dep][0] + NODE_W, pos[dep][1] + NODE_H / 2
            x2, y2 = pos[sid][0] - 3, pos[sid][1] + NODE_H / 2
            mid = (x1 + x2) / 2
            cls = "edge crit" if (dep, sid) in crit_edges else "edge"
            color = "var(--cyan)" if (dep, sid) in crit_edges else "var(--border-strong)"
            parts.append(
                f'<path class="{cls}" style="color:{color}" marker-end="url(#arrow)" '
                f'd="M{x1:.1f} {y1:.1f} C{mid:.1f} {y1:.1f} {mid:.1f} {y2:.1f} {x2:.1f} {y2:.1f}"/>'
            )
    for sid in dag:
        x, y = pos[sid]
        result = record.results.get(sid)
        status = result.status.value if result else "SKIPPED"
        detail = status
        if result and result.status != StepStatus.SKIPPED:
            detail += f" · {_fmt_s(result.duration_s)}"
        if result and result.flaky:
            detail += " · flaky"
        title = escape(f"{sid} — {detail}")
        parts.append(
            f'<a href="#{escape(anchor_prefix + sid)}"><g class="node">'
            f"<title>{title}</title>"
            f'<rect class="box" x="{x}" y="{y:.1f}" width="{NODE_W}" height="{NODE_H}" rx="10"/>'
            f'<rect class="s-{status}" x="{x}" y="{y:.1f}" width="4" height="{NODE_H}" rx="2"/>'
            f'<text class="name" x="{x + 16}" y="{y + 22:.1f}">{escape(_clip(sid, 20))}</text>'
            f'<text class="stat s-{status}" x="{x + 16}" y="{y + 39:.1f}">{escape(detail)}</text>'
            "</g></a>"
        )
    parts.append("</svg>")
    return "".join(parts)


def _nice_step(total: float, target: int = 6) -> float:
    raw = max(total, 1e-6) / target
    mag = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5, 10):
        if raw <= mult * mag:
            return mult * mag
    return 10 * mag


def gantt_svg(record: RunRecord, anchor_prefix: str = "step-") -> str | None:
    """When each step ran — parallelism, idle gaps and stragglers at a glance.

    Returns None for runs recorded before step windows were captured.
    """
    results = list(record.results.values())
    timed = [r for r in results if r.start_s is not None and r.end_s is not None]
    if not timed:
        return None
    order = {sid: i for i, sid in enumerate(record.dag or record.results)}
    timed.sort(key=lambda r: (r.start_s, order.get(r.step_id, 0)))
    skipped = [r for r in results if r.status == StepStatus.SKIPPED]
    rows: list[StepResult] = timed + skipped

    total = max(r.end_s for r in timed) or 1e-3
    label_w, row_h, bar_h, top, right = 156, 32, 16, 26, 64
    width = 1160
    plot_w = width - label_w - right
    height = top + len(rows) * row_h + 8
    scale = plot_w / total
    step = _nice_step(total)

    parts = [
        f'<svg class="chart gantt" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Run timeline: when each of {len(rows)} steps ran" style="min-width:640px">',
        '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)"><rect width="3" height="6" fill="rgba(255,255,255,.28)"/>'
        "</pattern></defs>",
    ]
    tick = 0.0
    while tick <= total + 1e-9:
        x = label_w + tick * scale
        parts.append(f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{top - 6}" y2="{height - 6}"/>')
        parts.append(f'<text class="tick" x="{x:.1f}" y="{top - 11}" text-anchor="middle">{_fmt_tick(tick, step)}</text>')
        tick += step
    for i, r in enumerate(rows):
        cy = top + i * row_h + row_h / 2
        parts.append(
            f'<a href="#{escape(anchor_prefix + r.step_id)}"><text class="lbl" x="{label_w - 14}" '
            f'y="{cy + 4:.1f}" text-anchor="end">{escape(_clip(r.step_id, 20))}</text></a>'
        )
        status = r.status.value
        if r.status == StepStatus.SKIPPED:
            parts.append(
                f'<rect class="bar-skip" x="{label_w + 1}" y="{cy - bar_h / 2:.1f}" '
                f'width="{min(plot_w, 70)}" height="{bar_h}" rx="4"/>'
                f'<text class="tick" x="{label_w + 10}" y="{cy + 4:.1f}">skipped</text>'
            )
            continue
        x = label_w + r.start_s * scale
        w = max(3.0, (r.end_s - r.start_s) * scale)
        title = escape(
            f"{r.step_id}: {status}, {r.start_s:.2f}s → {r.end_s:.2f}s"
            + (f", {r.attempts} attempts" if r.attempts > 1 else "")
        )
        parts.append(
            f'<g><title>{title}</title><rect class="bar s-{status}" x="{x:.1f}" '
            f'y="{cy - bar_h / 2:.1f}" width="{w:.1f}" height="{bar_h}" rx="4"/>'
        )
        if r.flaky or r.attempts > 1:
            parts.append(
                f'<rect x="{x:.1f}" y="{cy - bar_h / 2:.1f}" width="{w:.1f}" height="{bar_h}" '
                'rx="4" fill="url(#hatch)"/>'
            )
        parts.append(
            f'<text class="tick" x="{x + w + 6:.1f}" y="{cy + 4:.1f}">'
            f"{_fmt_s(r.end_s - r.start_s)}</text></g>"
        )
    parts.append("</svg>")
    return "".join(parts)


def _fmt_tick(value: float, step: float) -> str:
    if step >= 1:
        return f"{value:.0f}s"
    decimals = max(0, -math.floor(math.log10(step)))
    return f"{value:.{decimals}f}s"


def trend_svg(rows: list[dict], href) -> str:
    """Recent runs as bars: height is duration, color is verdict, click to open.

    `rows` are history rows (newest first, as the store returns them). Bars sit
    in fixed slots filled from the right, so time always flows left to right
    and a short history doesn't balloon into a few giant bars.
    """
    from ..report import _iso_delta_s

    if not rows:
        return ""
    data = list(reversed(rows))
    durations = [
        max(r["duration_s"] if r.get("duration_s") is not None
            else _iso_delta_s(r["started_at"], r["finished_at"]), 0.0)
        for r in data
    ]  # fmt: skip
    peak = max(durations) or 1.0
    width, height, bottom, top, left = 1160, 170, 26, 18, 52
    slots = max(len(data), 24)
    slot_w = (width - left - 8) / slots
    bar_w = max(4.0, slot_w * 0.68)
    plot_h = height - bottom - top
    base_y = height - bottom
    parts = [
        f'<svg class="chart trend" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Duration and verdict of the last {len(data)} runs" style="min-width:560px">',
        f'<line class="grid" x1="{left}" x2="{width}" y1="{top}" y2="{top}"/>',
        f'<line class="grid" x1="{left}" x2="{width}" y1="{top + plot_h / 2:.1f}" y2="{top + plot_h / 2:.1f}"/>',
        f'<text class="tick" x="{left - 10}" y="{top + 4}" text-anchor="end">{_fmt_s(peak)}</text>',
        f'<text class="tick" x="{left - 10}" y="{top + plot_h / 2 + 4:.1f}" text-anchor="end">{_fmt_s(peak / 2)}</text>',
        f'<line class="axis" x1="{left}" x2="{width}" y1="{base_y}" y2="{base_y}"/>',
    ]
    first_slot = slots - len(data)
    for i, (row, dur) in enumerate(zip(data, durations, strict=True)):
        h = max(3.0, plot_h * dur / peak)
        x = left + (first_slot + i) * slot_w + (slot_w - bar_w) / 2
        status = "PASS" if row["status"] == "PASS" else "FAIL"
        title = escape(
            f"{row['run_id']} · {row['status']} · {dur:.1f}s · "
            f"{row['failed_steps']} failing step(s) · {row['started_at']}"
        )
        parts.append(
            f'<a href="{escape(href(row["run_id"]))}"><g><title>{title}</title>'
            f'<rect class="trend-bar s-{status}" x="{x:.1f}" y="{base_y - h:.1f}" width="{bar_w:.1f}" '
            f'height="{h:.1f}" rx="3"/></g></a>'
        )
    last = data[-1]["started_at"].replace("T", " ")
    first = data[0]["started_at"].replace("T", " ")
    parts.append(f'<text class="tick" x="{width - 4}" y="{height - 6}" text-anchor="end">newest · {escape(last)}</text>')
    if len(data) > 1:
        parts.append(f'<text class="tick" x="{left}" y="{height - 6}">{len(data)} runs since {escape(first)}</text>')
    parts.append("</svg>")
    return "".join(parts)
