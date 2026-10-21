"""argparse entrypoint: run, history, report, diff, graph, stats, serve.

Exit codes: 0 = all steps PASS/WAIVED, 1 = any FAIL/TIMEOUT (or, for diff,
any new failure), 2 = config error / unknown run.

Anywhere a run id is accepted, `latest` and `latest~N` work too, so CI can
say `gauntlet diff latest~1 latest` without knowing either id.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

from . import __version__
from .diff import diff_runs
from .flow import FlowValidationError, load_flow
from .graph import dag_of, to_ascii, to_dot, to_mermaid
from .models import PASSING_STATUSES, FlowSpec, RunRecord, StepResult
from .parsing.parser import LogEvaluator
from .parsing.rules import Rulepack, RulepackError, load_rulepack
from .parsing.waivers import WaiverError, load_waivers
from .report import render_diff, render_history, render_run
from .scheduler import Scheduler
from .store import RunNotFoundError, RunStore
from .term import paint

CONFIG_ERRORS = (FlowValidationError, RulepackError, WaiverError)


def runs_dir() -> Path:
    """Where run artifacts and the database live (GAUNTLET_RUNS_DIR overrides)."""
    return Path(os.environ.get("GAUNTLET_RUNS_DIR", "runs"))


def db_path() -> Path:
    return runs_dir() / "gauntlet.db"


def main(argv: list[str] | None = None) -> int:
    # Reports use → · ✓ ✗. A Windows pipe defaults to cp1252, which can't
    # encode them; degrade a glyph rather than crash the command.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(
        prog="gauntlet", description="every commit runs the gauntlet"
    )
    parser.add_argument("--version", action="version", version=f"gauntlet {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="execute a flow YAML")
    p_run.add_argument("flow_file", help="path to the flow YAML")
    p_run.add_argument("--workers", type=int, default=4)
    p_run.add_argument(
        "--keep-going",
        action="store_true",
        help="continue independent branches after a failure",
    )
    p_run.add_argument("--rulepacks-dir", default="rulepacks")
    p_run.add_argument("--waivers", default="waivers/waivers.yaml")
    _add_outputs(p_run)

    p_history = sub.add_parser("history", help="list recent runs")
    p_history.add_argument("-n", type=int, default=10, dest="limit")
    p_history.add_argument("--flow", help="only runs of this flow")

    p_report = sub.add_parser("report", help="re-render a stored run's report")
    p_report.add_argument("run_id", help="run id, `latest` or `latest~N`")
    _add_outputs(p_report)

    p_diff = sub.add_parser("diff", help="compare two runs (exit 1 on new failures)")
    p_diff.add_argument("run_a", help="baseline run (id, `latest~1`, ...)")
    p_diff.add_argument("run_b", help="candidate run (id, `latest`, ...)")
    p_diff.add_argument("--markdown", metavar="PATH", help="write a Markdown diff ('-' = stdout)")
    p_diff.add_argument("--html", metavar="PATH", help="write a single-file HTML diff")
    p_diff.add_argument("--json", action="store_true", help="print the diff as JSON")

    p_graph = sub.add_parser("graph", help="show a flow's dependency graph")
    p_graph.add_argument("flow_file")
    p_graph.add_argument(
        "--format", choices=("ascii", "mermaid", "dot"), default="ascii",
        help="ascii (default), mermaid (GitHub renders it) or dot (graphviz)",
    )

    p_stats = sub.add_parser("stats", help="per-step stability across recent runs")
    p_stats.add_argument("-n", type=int, default=20, dest="limit")
    p_stats.add_argument("--flow", help="flow name (default: flow of the latest run)")

    p_serve = sub.add_parser("serve", help="browse run history in a local web dashboard")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--open", action="store_true", help="open it in a browser")

    args = parser.parse_args(argv)
    commands = {
        "run": cmd_run,
        "history": cmd_history,
        "report": cmd_report,
        "diff": cmd_diff,
        "graph": cmd_graph,
        "stats": cmd_stats,
        "serve": cmd_serve,
    }
    try:
        return commands[args.command](args)
    except BrokenPipeError:
        # `gauntlet history | head` closed the pipe early — not an error. Point
        # stdout at devnull so the interpreter's final flush doesn't raise too.
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
        return 0


def _add_outputs(p: argparse.ArgumentParser) -> None:
    p.add_argument("--html", metavar="PATH", help="write a single-file HTML report")
    p.add_argument("--junit", metavar="PATH", help="write JUnit XML for CI test reporting")
    p.add_argument(
        "--markdown", metavar="PATH",
        help="write a Markdown summary ('-' = stdout; e.g. >> $GITHUB_STEP_SUMMARY)",
    )


def cmd_run(args: argparse.Namespace) -> int:
    try:
        flow = load_flow(args.flow_file)
        rulepacks = _load_rulepacks(flow, Path(args.rulepacks_dir))
        waivers = load_waivers(args.waivers)
    except CONFIG_ERRORS as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    evaluator = LogEvaluator(rulepacks, waivers)

    run_id = _new_run_id()
    run_dir = runs_dir() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    started_at = _now()
    commit, branch = _git_context()

    print(paint(f"gauntlet {__version__} · {flow.name} · {run_id} · {len(flow.steps)} steps"))

    def on_complete(result: StepResult) -> None:
        retry = f"  (attempt {result.attempts})" if result.attempts > 1 else ""
        print(
            paint(f"[{result.duration_s:6.2f}s] {result.status.value:<8} {result.step_id}{retry}"),
            flush=True,
        )

    scheduler = Scheduler(
        flow,
        max_workers=args.workers,
        keep_going=args.keep_going,
        evaluator=evaluator,
        on_complete=on_complete,
    )
    results = scheduler.execute(run_dir)

    all_ok = all(r.status in PASSING_STATUSES for r in results.values())
    # Report in flow order, not completion order: the DAG reads top-down.
    ordered = {s.id: results[s.id] for s in flow.steps if s.id in results}
    record = RunRecord(
        run_id=run_id,
        flow_name=flow.name,
        started_at=started_at,
        finished_at=_now(),
        status="PASS" if all_ok else "FAIL",
        results=ordered,
        dag=dag_of(flow),
        git_commit=commit,
        git_branch=branch,
    )
    _write_manifest(run_dir, record)
    with RunStore(db_path()) as store:
        store.save(record)
    print()
    print(paint(render_run(record)))
    _write_outputs(args, record)
    return 0 if all_ok else 1


def cmd_history(args: argparse.Namespace) -> int:
    with RunStore(db_path()) as store:
        print(paint(render_history(store.list_runs(args.limit, flow_name=args.flow))))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    try:
        with RunStore(db_path()) as store:
            record = store.load(args.run_id)
    except RunNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.markdown != "-":
        print(paint(render_run(record)))
    _write_outputs(args, record)
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    try:
        with RunStore(db_path()) as store:
            run_a = store.load(args.run_a)
            run_b = store.load(args.run_b)
    except RunNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    diff = diff_runs(run_a, run_b)
    if args.json:
        print(json.dumps(_diff_json(diff), indent=2))
    elif args.markdown != "-":
        print(paint(render_diff(diff)))
    if args.markdown:
        from .markdown import render_diff_markdown

        _emit(args.markdown, render_diff_markdown(diff), "markdown diff")
    if args.html:
        from .html_report import render_diff_html

        _emit(args.html, render_diff_html(diff, run_a, run_b), "html diff")
    return 1 if diff.new_failures else 0


def cmd_graph(args: argparse.Namespace) -> int:
    try:
        flow = load_flow(args.flow_file)
    except FlowValidationError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    dag = dag_of(flow)
    if args.format == "mermaid":
        print(to_mermaid(dag))
    elif args.format == "dot":
        print(to_dot(flow.name, dag))
    else:
        print(to_ascii(flow.name, dag))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    from .stats import compute_stats, render_stats

    with RunStore(db_path()) as store:
        flow_name = args.flow
        if flow_name is None:
            flows = store.flows()
            if not flows:
                print("no runs recorded yet")
                return 0
            flow_name = flows[0]
        runs = store.step_history(flow_name, args.limit)
    ascii_only = not _can_encode("✓✗·")
    print(paint(render_stats(flow_name, runs, compute_stats(runs), ascii_only=ascii_only)))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve

    return serve(db_path(), host=args.host, port=args.port, open_browser=args.open)


def _write_outputs(args: argparse.Namespace, record: RunRecord) -> None:
    if args.html:
        from .html_report import relative_log_href, render_html

        log_href = None if args.html == "-" else relative_log_href(args.html)
        _emit(args.html, render_html(record, log_href), "html report")
    if args.junit:
        from .junit import render_junit

        _emit(args.junit, render_junit(record), "junit xml")
    if args.markdown:
        from .markdown import render_run_markdown

        _emit(args.markdown, render_run_markdown(record), "markdown summary")


def _emit(path: str, text: str, label: str) -> None:
    """Write `text` to `path`, or to stdout when path is '-'."""
    if path == "-":
        sys.stdout.write(text)
        return
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"{label} written: {path}")


def _can_encode(text: str) -> bool:
    try:
        text.encode(sys.stdout.encoding or "utf-8")
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def _diff_json(diff) -> dict:
    return {
        "run_a": diff.run_a,
        "run_b": diff.run_b,
        "flow": diff.flow_name,
        "verdict": diff.verdict_line(),
        "new_failures": [r.step_id for r in diff.new_failures],
        "fixed": [r.step_id for r in diff.fixed],
        "still_failing": [r.step_id for r in diff.still_failing],
        "unchanged_pass": [r.step_id for r in diff.unchanged_pass],
        "new_steps": diff.new_steps,
        "removed_steps": diff.removed_steps,
    }


def _load_rulepacks(flow: FlowSpec, rulepacks_dir: Path) -> dict[str, Rulepack]:
    """Load every rulepack the flow references, once each, up front."""
    names = {s.rulepack for s in flow.steps if s.rulepack}
    return {name: load_rulepack(rulepacks_dir / f"{name}.yaml") for name in names}


def _git_context() -> tuple[str | None, str | None]:
    """The commit and branch being tested, if we're inside a git checkout.

    GAUNTLET_GIT_COMMIT / GAUNTLET_GIT_BRANCH override detection — useful when
    the flow runs outside the checkout, or the CI system knows better.
    """
    env_commit = os.environ.get("GAUNTLET_GIT_COMMIT")
    env_branch = os.environ.get("GAUNTLET_GIT_BRANCH")
    if env_commit and env_branch:
        return env_commit, env_branch

    def git(*cmd: str) -> str | None:
        try:
            proc = subprocess.run(
                ["git", *cmd], capture_output=True, text=True, timeout=5
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        out = proc.stdout.strip()
        return out if proc.returncode == 0 and out else None

    commit = env_commit or git("rev-parse", "HEAD")
    branch = env_branch or git("rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":  # detached, as in most CI checkouts
        branch = next(
            (
                os.environ[var]
                for var in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "CI_COMMIT_REF_NAME", "BRANCH_NAME")
                if os.environ.get(var)
            ),
            None,
        )
    return commit, branch or None


def _new_run_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    return f"run_{stamp}_{uuid.uuid4().hex[:4]}"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _write_manifest(run_dir: Path, record: RunRecord) -> None:
    (run_dir / "manifest.json").write_text(json.dumps(record.to_dict(), indent=2))


if __name__ == "__main__":
    sys.exit(main())
