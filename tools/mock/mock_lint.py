#!/usr/bin/env python3
"""Mock RTL lint tool (Verilator-ish output).

Env knobs:
  GAUNTLET_SEED=<int>    deterministic output (byte-identical runs)
  GAUNTLET_FLAKE=<prob>  chance of emitting an extra ERROR and exiting 1
"""
import argparse
import os
import random
import sys
import time

WARNING_POOL = [
    ("LINT-042", "signal 'clk_en' declared but never read", "ctrl.v", 118),
    ("LINT-107", "implicit wire declaration 'rst_sync'", "top.v", 44),
    ("LINT-113", "unused parameter 'DEPTH_LOG2'", "fifo.v", 12),
    ("LINT-088", "case statement without default branch", "decode.v", 77),
    ("LINT-129", "port 'scan_en' unconnected in instance u_bist", "top.v", 152),
]

FILES = ["top.v", "ctrl.v", "fsm.v", "fifo.v", "decode.v", "regs.v"]


def main() -> int:
    parser = argparse.ArgumentParser(description="mock RTL lint")
    parser.add_argument("--design", required=True)
    args = parser.parse_args()

    seed = os.environ.get("GAUNTLET_SEED")
    rng = random.Random(f"{seed}:lint:{args.design}" if seed else None)
    flake_p = float(os.environ.get("GAUNTLET_FLAKE", "0"))
    flaky = rng.random() < flake_p

    time.sleep(rng.uniform(0.5, 3))

    print(f"INFO: Verilator-style lint pass starting for design '{args.design}'")
    print(f"INFO: reading filelist {args.design}/rtl.f ({len(FILES)} files)")
    for f in FILES:
        print(f"INFO: parsing {args.design}/{f}")

    warnings = rng.sample(WARNING_POOL, k=rng.randint(2, 4))
    for rule, msg, fname, line in warnings:
        print(f"[{rule}] WARNING: {msg} ({args.design}/{fname}:{line})")

    errors = 0
    if flaky:
        print(
            f"[LINT-201] ERROR: latch inferred on 'state_q' — missing else branch "
            f"({args.design}/fsm.v:203)"
        )
        errors = 1

    print("INFO: elaboration complete, 14 modules, 3121 nets")
    print(f"INFO: lint complete: {len(warnings)} warnings, {errors} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
