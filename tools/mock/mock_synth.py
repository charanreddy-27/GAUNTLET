#!/usr/bin/env python3
"""Mock synthesis tool with timing-style summary output.

Env knobs:
  GAUNTLET_SEED=<int>    deterministic output (byte-identical runs)
  GAUNTLET_FLAKE=<prob>  chance of a negative-slack ERROR and exit 1
"""
import argparse
import os
import random
import sys
import time

PATHS = [
    "clk->data_out", "clk->irq_line", "fifo_rd->arb_grant",
    "csr_wr->cfg_shadow", "scan_en->bist_mux", "rst_sync->state_q",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="mock synthesis")
    parser.add_argument("--design", required=True)
    parser.add_argument("--effort", default="quick", choices=["quick", "high"])
    args = parser.parse_args()

    seed = os.environ.get("GAUNTLET_SEED")
    rng = random.Random(f"{seed}:synth:{args.design}:{args.effort}" if seed else None)
    flake_p = float(os.environ.get("GAUNTLET_FLAKE", "0"))
    flaky = rng.random() < flake_p

    time.sleep(rng.uniform(0.5, 3))

    print(f"INFO: synthesis starting for '{args.design}' (effort={args.effort})")
    print("INFO: reading liberty lib tsmc_mock_7nm_tt.lib")
    print("INFO: technology mapping ... done")
    cells = rng.randint(11000, 15000)
    area = round(rng.uniform(0.08, 0.15), 4)
    print(f"INFO: mapped {cells} cells, est. area {area} mm2")

    print("INFO: timing summary (setup, worst 6 paths):")
    for path in PATHS:
        slack = round(rng.uniform(0.05, 0.9), 2)
        print(f"  path {path:<22} slack +{slack:.2f}ns  MET")

    errors = 0
    if flaky:
        slack = round(rng.uniform(0.1, 0.6), 2)
        print(f"[SYN-ERR-011] ERROR: negative slack -{slack:.2f}ns on path clk->data_out")
        errors = 1
    if rng.random() < 0.4:
        print("[SYN-WRN-020] WARNING: high fanout net 'rst_sync' (fanout=412)")

    print(f"INFO: synthesis complete: {errors} timing errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
