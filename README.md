# GAUNTLET

> *every commit runs the gauntlet.*

A miniature IP-regression platform, built in 2 days as a study project to
understand the problem space of Design Flow infrastructure tooling. It
recreates the core loop of an IP-regression product: **DAG-based flow
execution → EDA-style log parsing → waivers → run-to-run delta reporting.**

Pure Python 3.10+ on Linux/macOS. One dependency (PyYAML). No network, no
services, no Docker — real subprocesses, real signals, real exit codes,
logs as files on disk.

## Architecture

```
 flows/smoke.yaml          rulepacks/*.yaml         waivers/waivers.yaml
       │                          │                          │
       ▼                          ▼                          ▼
 ┌───────────┐            ┌──────────────┐          ┌───────────────┐
 │  flow.py  │            │   rules.py   │          │   waivers.py  │
 │ validate, │            │ compile regex│          │ rule_id+substr│
 │ cycle-chk │            │  rulepacks   │          │    matching   │
 └─────┬─────┘            └──────┬───────┘          └───────┬───────┘
       │ FlowSpec                └──────────┬───────────────┘
       ▼                                    ▼
 ┌──────────────────┐   StepResult   ┌──────────────┐
 │   scheduler.py   │───────────────▶│  parser.py   │  log → Violations,
 │ ThreadPool ready-│◀───────────────│ LogEvaluator │  waive, re-status
 │ set DAG executor │  final status  └──────────────┘
 └────────┬─────────┘
          │ runs Step.run() per step        ┌─────────────────────────┐
          ▼                                 │  runs/<run_id>/         │
 ┌──────────────────┐                       │    <step_id>/output.log │
 │     steps.py     │── subprocess, own ───▶│    manifest.json        │
 │ Step ABC         │   process group,      └─────────────────────────┘
 │ └── ShellStep    │   SIGTERM→3s→SIGKILL
 └──────────────────┘
          │ RunRecord
          ▼
 ┌──────────────────┐        ┌──────────────┐        ┌──────────────┐
 │     store.py     │───────▶│   diff.py    │───────▶│  report.py   │
 │ SQLite: runs,    │        │ NEW FAILURES │        │ terminal     │
 │ steps, violations│        │ FIXED / ...  │        │ rendering    │
 └──────────────────┘        └──────────────┘        └──────────────┘
```

## Quickstart

```bash
pip install -e ".[dev]"
pytest                       # 36 tests, ~3s, fully offline
gauntlet run flows/smoke.yaml
```

## Demo

```bash
# 1. clean run, deterministic (sim_unit hits a known, waived TB failure)
GAUNTLET_SEED=7 gauntlet run flows/smoke.yaml --workers 4

# 2. introduce a flake, run again (sim_unit now hits an UNWAIVED overflow)
GAUNTLET_SEED=7 GAUNTLET_FLAKE=0.3 gauntlet run flows/smoke.yaml --workers 4 --keep-going

# 3. the money shot
gauntlet history -n 2
gauntlet diff <run_1> <run_2>       # exits 1 → CI-usable
```

What to look at:

1. **Run 1:** both sims run in parallel after lint (DAG scheduling), and
   `sim_unit` shows `WAIVED` — its known fifo-overflow error is waived in
   `waivers/waivers.yaml` with an owner and a JIRA-style reason.
2. **Run 2:** the flake injects `fifo overflow in u_fifo_tx`. Same rule id
   (`SIM-ERR-007`) but the waiver's `match: u_fifo_rx` substring doesn't hit,
   so the step FAILs — waivers are precise, not blanket.
3. **The diff:** `NEW FAILURES: sim_unit`. That delta — not any single run's
   pass/fail — is what a regression platform exists to produce.

Mock-tool knobs: `GAUNTLET_SEED=<int>` makes tool output byte-identical
between runs; `GAUNTLET_FLAKE=<0..1>` is the probability each tool emits an
extra ERROR and exits 1.

## CLI

| command | purpose | exit codes |
|---|---|---|
| `gauntlet run <flow.yaml> [--workers N] [--keep-going]` | execute a flow | 0 all PASS/WAIVED · 1 any FAIL/TIMEOUT · 2 config error |
| `gauntlet history [-n 10]` | recent runs from SQLite | 0 |
| `gauntlet report <run_id> [--html out.html]` | re-render a stored run (optionally as a single-file HTML page) | 0 · 2 unknown run |
| `gauntlet diff <run_a> <run_b>` | run-to-run regression delta | 0 · 1 new failures · 2 unknown run |

## Design Notes

- **`Step` is an ABC** because the scheduler's contract is just
  `run() -> StepResult`. `ShellStep` is one implementation; a `PythonStep`
  or `RemoteStep` later touches zero scheduler code.
- **Threads, not asyncio/processes.** Workers spend their lives blocked in
  `subprocess.wait()`, where the GIL is released — a `ThreadPoolExecutor`
  gives real parallelism with none of the ceremony.
- **Timeouts kill the whole tree.** Steps launch with
  `start_new_session=True` (own process group); on timeout we
  `killpg(SIGTERM)`, wait 3s, then `SIGKILL`. A shell wrapper dying while
  its child simulator lives on is the classic infra bug this avoids.
- **A tool can exit 0 and still FAIL** if its log contains an unwaived
  ERROR — real EDA tools under-report via exit codes, so the log is the
  source of truth.
- **WAIVED is a distinct status,** not silently PASS: waived failures stay
  visible in every report, with owner and reason, because a waiver is a
  debt, not a fix.
- **Logs are streamed line by line,** never read whole — production EDA
  logs run to gigabytes.
- **`SKIPPED` is not a failure in diffs.** A skipped step gives no new
  evidence against the step itself; the diff blames the upstream step that
  actually failed.
- **Schema deviation:** the `violations` table adds a `waive_reason` column
  beyond the spec's minimum so `gauntlet report <run_id>` can reproduce the
  full report (including waiver reasons) from the DB alone.
- Scope guards honored: no plugins, no asyncio, no web UI, no config
  server. Built strictly Phase 1 → 4 first; the Phase 5 stretch items
  below were added only after the core was demo-complete.

## Stretch features (Phase 5)

- **HTML report** — `gauntlet report <run_id> --html out.html` writes one
  self-contained page (stdlib `string.Template`, zero new deps) with the
  step summary, per-step `output.log` links, and violation tables.
- **CI workflow** — `.github/workflows/gauntlet.yml` installs the package,
  runs the test suite and the seeded smoke flow, and uploads `runs/` as a
  build artifact (`if: always()`, so failing runs keep their evidence).
- **Per-step retries** — `retries: N` on a step in the flow YAML gives it
  N naive immediate re-attempts. A step that only passes on a retry gets
  `flaky=True`: it satisfies its dependents, but every report shows
  `(flaky: passed on retry)` — a flaky pass is information, not a pass.

## Layout

```
gauntlet/           the package: cli, models, flow, steps, scheduler,
                    parsing/{rules,parser,waivers}, store, diff, report
flows/              flow definitions (YAML DAGs)
rulepacks/          per-tool regex rulepacks
waivers/            documented exceptions with owners and reasons
tools/mock/         fake lint/sim/synth generating realistic logs
tests/              pytest suite (offline, deterministic, <10s)
runs/               created at runtime: per-step logs, manifest.json, gauntlet.db
```
