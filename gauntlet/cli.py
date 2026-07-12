"""argparse entrypoint. Subcommands: run (more added in later phases).

Exit codes: 0 = all steps PASS/WAIVED, 1 = any FAIL/TIMEOUT, 2 = config error.
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime
from pathlib import Path

from .diff import diff_runs
from .flow import FlowValidationError, load_flow
from .models import PASSING_STATUSES, FlowSpec, RunRecord, StepResult
from .parsing.parser import LogEvaluator
from .parsing.rules import Rulepack, RulepackError, load_rulepack
from .parsing.waivers import WaiverError, load_waivers
from .report import render_diff, render_history, render_run
from .scheduler import Scheduler
from .store import RunNotFoundError, RunStore

RUNS_DIR = Path("runs")
DB_PATH = RUNS_DIR / "gauntlet.db"
CONFIG_ERRORS = (FlowValidationError, RulepackError, WaiverError)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gauntlet", description="every commit runs the gauntlet"
    )
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

    p_history = sub.add_parser("history", help="list recent runs")
    p_history.add_argument("-n", type=int, default=10, dest="limit")

    p_report = sub.add_parser("report", help="re-render a stored run's report")
    p_report.add_argument("run_id")

    p_diff = sub.add_parser("diff", help="compare two runs (exit 1 on new failures)")
    p_diff.add_argument("run_a")
    p_diff.add_argument("run_b")

    args = parser.parse_args(argv)
    commands = {
        "run": cmd_run,
        "history": cmd_history,
        "report": cmd_report,
        "diff": cmd_diff,
    }
    return commands[args.command](args)


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
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    started_at = _now()

    def on_complete(result: StepResult) -> None:
        print(f"[{result.duration_s:6.2f}s] {result.status.value:<8} {result.step_id}")

    scheduler = Scheduler(
        flow,
        max_workers=args.workers,
        keep_going=args.keep_going,
        evaluator=evaluator,
        on_complete=on_complete,
    )
    results = scheduler.execute(run_dir)

    all_ok = all(r.status in PASSING_STATUSES for r in results.values())
    record = RunRecord(
        run_id=run_id,
        flow_name=flow.name,
        started_at=started_at,
        finished_at=_now(),
        status="PASS" if all_ok else "FAIL",
        results=results,
    )
    _write_manifest(run_dir, record)
    store = RunStore(DB_PATH)
    try:
        store.save(record)
    finally:
        store.close()
    print()
    print(render_run(record))
    return 0 if all_ok else 1


def cmd_history(args: argparse.Namespace) -> int:
    store = RunStore(DB_PATH)
    try:
        print(render_history(store.list_runs(args.limit)))
    finally:
        store.close()
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    store = RunStore(DB_PATH)
    try:
        record = store.load(args.run_id)
    except RunNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        store.close()
    print(render_run(record))
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    store = RunStore(DB_PATH)
    try:
        run_a = store.load(args.run_a)
        run_b = store.load(args.run_b)
    except RunNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        store.close()
    diff = diff_runs(run_a, run_b)
    print(render_diff(diff))
    return 1 if diff.new_failures else 0


def _load_rulepacks(flow: FlowSpec, rulepacks_dir: Path) -> dict[str, Rulepack]:
    """Load every rulepack the flow references, once each, up front."""
    names = {s.rulepack for s in flow.steps if s.rulepack}
    return {name: load_rulepack(rulepacks_dir / f"{name}.yaml") for name in names}


def _new_run_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    return f"run_{stamp}_{uuid.uuid4().hex[:4]}"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _write_manifest(run_dir: Path, record: RunRecord) -> None:
    import json

    (run_dir / "manifest.json").write_text(json.dumps(record.to_dict(), indent=2))


if __name__ == "__main__":
    sys.exit(main())
