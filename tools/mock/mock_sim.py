#!/usr/bin/env python3
"""Mock RTL simulator.

The unit suite always hits the known SIM-ERR-007 fifo overflow in u_fifo_rx
(a waivable testbench artifact). Other failures only appear when flaking.

Env knobs:
  GAUNTLET_SEED=<int>    deterministic output (byte-identical runs)
  GAUNTLET_FLAKE=<prob>  chance of an extra unwaivable ERROR and exit 1
"""
import argparse
import os
import random
import sys
import time

TESTS = [
    "reset_seq", "reg_rw", "fifo_fill", "fifo_drain", "irq_mask",
    "burst_write", "burst_read", "backpressure", "clk_gate", "dma_short",
    "dma_long", "err_inject", "parity", "timeout_cnt", "addr_wrap",
    "arb_fair", "low_power", "wake_event", "csr_lock", "bist_smoke",
    "mixed_traffic", "rand_stall", "overflow_guard", "soak_mini",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="mock RTL simulator")
    parser.add_argument("--suite", required=True, choices=["unit", "integration"])
    parser.add_argument("--design", required=True)
    args = parser.parse_args()

    seed = os.environ.get("GAUNTLET_SEED")
    rng = random.Random(f"{seed}:sim:{args.suite}:{args.design}" if seed else None)
    flake_p = float(os.environ.get("GAUNTLET_FLAKE", "0"))
    flaky = rng.random() < flake_p

    time.sleep(rng.uniform(0.5, 3))

    sim_seed = rng.randint(1000, 9999)
    print(f"INFO: compiling testbench tb_{args.design} (suite={args.suite})")
    print(f"INFO: elaborating top tb_{args.design} ... done")
    print(f"INFO: running {len(TESTS)} tests, seed={sim_seed}")

    known_fail = args.suite == "unit"      # the waivable TB artifact
    failed = []
    for name in TESTS:
        if known_fail and name == "fifo_fill":
            print(
                "[SIM-ERR-007] ERROR: assertion failed at 1240ns: "
                "fifo overflow in u_fifo_rx"
            )
            print(f"TEST {name:<16} FAIL")
            failed.append(name)
        elif flaky and name == "backpressure":
            t = rng.randint(2000, 9000)
            print(
                f"[SIM-ERR-007] ERROR: assertion failed at {t}ns: "
                "fifo overflow in u_fifo_tx"
            )
            print(f"TEST {name:<16} FAIL")
            failed.append(name)
        else:
            print(f"TEST {name:<16} PASS")

    if rng.random() < 0.5:
        print("[SIM-WRN-003] WARNING: X-propagation on bus 'data_out' at 880ns")

    passed = len(TESTS) - len(failed)
    print(f"INFO: {passed}/{len(TESTS)} tests passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
