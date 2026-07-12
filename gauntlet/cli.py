"""argparse entrypoint. Subcommands: run (more added in later phases).

Exit codes: 0 = all steps PASS/WAIVED, 1 = any FAIL/TIMEOUT, 2 = config error.
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime
from pathlib import Path

from .flow import FlowValidationError, load_flow
from .models import PASSING_STATUSES, FlowSpec, RunRecord, StepResult
from .parsing.parser import LogEvaluator
from .parsing.rules import Rulepack, RulepackError, load_rulepack
from .parsing.waivers import WaiverError, load_waivers
from .report import render_run
from .scheduler import Scheduler

RUNS_DIR = Path("runs")
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

    args = parser.parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    return 2


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
    print()
    print(render_run(record))
    return 0 if all_ok else 1


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
