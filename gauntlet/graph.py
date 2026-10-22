"""DAG shape: layering, critical path, and text renderings of a flow.

Everything here works on a plain `{step_id: [deps]}` mapping, so the same
code draws a FlowSpec straight from YAML and a RunRecord from SQLite.
"""
from __future__ import annotations

from .models import FlowSpec, RunRecord, StepStatus


def dag_of(flow: FlowSpec) -> dict[str, list[str]]:
    """The dependency mapping of a flow, in definition order."""
    return {s.id: list(s.depends_on) for s in flow.steps}


def layers(dag: dict[str, list[str]]) -> list[list[str]]:
    """Group steps by longest-path depth from an entry step.

    Layer k holds every step whose deepest dependency chain is k long, which
    is exactly the order a ready-set scheduler with unlimited workers would
    start them in. Within a layer, definition order is preserved.
    """
    depth: dict[str, int] = {}

    def visit(sid: str, trail: tuple[str, ...] = ()) -> int:
        if sid in depth:
            return depth[sid]
        if sid in trail:  # defensive: flows are cycle-checked at load
            raise ValueError(f"cycle through {sid}")
        deps = [d for d in dag.get(sid, []) if d in dag]
        depth[sid] = 1 + max((visit(d, trail + (sid,)) for d in deps), default=-1)
        return depth[sid]

    for sid in dag:
        visit(sid)
    out: list[list[str]] = [[] for _ in range(max(depth.values(), default=-1) + 1)]
    for sid in dag:
        out[depth[sid]].append(sid)
    return out


def critical_path(
    dag: dict[str, list[str]], weight: dict[str, float] | None = None
) -> list[str]:
    """The heaviest dependency chain through the DAG.

    With no weights every step counts 1, so this is the deepest chain; with
    durations it is the chain that bounded the run's wall-clock time — the
    one worth making faster.
    """
    weight = weight or {}
    best: dict[str, tuple[float, list[str]]] = {}

    def visit(sid: str) -> tuple[float, list[str]]:
        if sid not in best:
            own = weight.get(sid, 1.0)
            deps = [visit(d) for d in dag.get(sid, []) if d in dag]
            head = max(deps, key=lambda t: t[0], default=(0.0, []))
            best[sid] = (head[0] + own, head[1] + [sid])
        return best[sid]

    chains = [visit(sid) for sid in dag]
    return max(chains, key=lambda t: t[0], default=(0.0, []))[1]


def dependents(dag: dict[str, list[str]]) -> dict[str, list[str]]:
    """Invert the mapping: step_id -> the steps that wait on it."""
    out: dict[str, list[str]] = {sid: [] for sid in dag}
    for sid, deps in dag.items():
        for dep in deps:
            out.setdefault(dep, []).append(sid)
    return out


def to_ascii(name: str, dag: dict[str, list[str]], statuses: dict[str, StepStatus] | None = None) -> str:
    """A layered text view: what runs when, and what each step waits on."""
    statuses = statuses or {}
    grouped = layers(dag)
    width = max((len(s) for s in dag), default=4)
    widest = max((len(layer) for layer in grouped), default=0)
    lines = [
        f"{name}  ·  {len(dag)} steps · {len(grouped)} layers · "
        f"max parallelism {widest}",
        "",
    ]
    for depth, layer in enumerate(grouped):
        for i, sid in enumerate(layer):
            label = f"L{depth}" if i == 0 else "  "
            tag = f"{statuses[sid].value:<8} " if sid in statuses else ""
            deps = dag[sid]
            wait = f"  ← {', '.join(deps)}" if deps else "  (entry)"
            lines.append(f"  {label}  {tag}{sid:<{width}}{wait}")
        if depth < len(grouped) - 1:
            lines.append("       │")
    chain = critical_path(dag)
    if len(chain) > 1:
        lines += ["", f"  longest chain: {' → '.join(chain)}  ({len(chain)} steps deep)"]
    return "\n".join(lines)


def _node_id(sid: str) -> str:
    return "n_" + "".join(c if c.isalnum() else "_" for c in sid)


def to_mermaid(dag: dict[str, list[str]], statuses: dict[str, StepStatus] | None = None) -> str:
    """Mermaid flowchart source — GitHub renders it inline in Markdown."""
    statuses = statuses or {}
    lines = ["flowchart LR"]
    for sid in dag:
        lines.append(f'  {_node_id(sid)}["{sid}"]')
    for sid, deps in dag.items():
        for dep in deps:
            lines.append(f"  {_node_id(dep)} --> {_node_id(sid)}")
    if statuses:
        palette = {
            StepStatus.PASS: "fill:#dcfce7,stroke:#16a34a,color:#14532d",
            StepStatus.WAIVED: "fill:#fef3c7,stroke:#d97706,color:#78350f",
            StepStatus.FAIL: "fill:#ffe4e6,stroke:#e11d48,color:#881337",
            StepStatus.TIMEOUT: "fill:#f3e8ff,stroke:#9333ea,color:#581c87",
            StepStatus.SKIPPED: "fill:#f1f5f9,stroke:#94a3b8,color:#475569",
        }
        used = {statuses[s] for s in dag if s in statuses}
        for status in StepStatus:
            if status in used:
                lines.append(f"  classDef {status.value.lower()} {palette[status]}")
        for sid in dag:
            if sid in statuses:
                lines.append(f"  class {_node_id(sid)} {statuses[sid].value.lower()}")
    return "\n".join(lines)


def to_dot(name: str, dag: dict[str, list[str]]) -> str:
    """Graphviz DOT source, for `dot -Tsvg`."""
    safe = name.replace('"', "'")
    lines = [f'digraph "{safe}" {{', "  rankdir=LR;", '  node [shape=box, style=rounded, fontname="monospace"];']
    for sid in dag:
        lines.append(f'  "{sid}";')
    for sid, deps in dag.items():
        for dep in deps:
            lines.append(f'  "{dep}" -> "{sid}";')
    lines.append("}")
    return "\n".join(lines)


def record_dag(record: RunRecord) -> dict[str, list[str]]:
    """A run's DAG, falling back to edgeless when it predates DAG capture."""
    if record.dag:
        return {sid: list(record.dag.get(sid, [])) for sid in record.dag}
    return {sid: [] for sid in record.results}


def max_parallelism(record: RunRecord) -> int:
    """Most steps that were actually running at the same instant."""
    events: list[tuple[float, int]] = []
    for r in record.results.values():
        if r.start_s is not None and r.end_s is not None and r.end_s > r.start_s:
            events.append((r.start_s, 1))
            events.append((r.end_s, -1))
    # Ends sort before starts at the same instant: touching is not overlapping.
    events.sort(key=lambda e: (e[0], e[1]))
    running = peak = 0
    for _, delta in events:
        running += delta
        peak = max(peak, running)
    return peak
