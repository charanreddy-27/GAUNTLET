# GAUNTLET — Deep Dive

This document is the "how it actually works" companion to the README. It covers
the architecture, the data flow through one run, the folder structure, the key
decisions and their tradeoffs, and how the genuinely hard parts work.

---

## 1. The mental model

GAUNTLET is a pipeline of pure transformations wrapped around one impure core
(running subprocesses). Everything is built so the impure part is small and
quarantined, and everything around it is deterministic and testable.

```
YAML config ──▶ FlowSpec ──▶ [ Scheduler runs Steps ] ──▶ StepResults
                                     │                          │
                              (subprocess, logs)         parse + waive
                                                                │
                                                          RunRecord ──▶ SQLite
                                                                │
                                                    report / history / diff
```

The single source of truth is `models.py`: frozen dataclasses for **inputs**
(specs), mutable dataclasses for **outputs** (results), and one enum,
`StepStatus`, that the entire product's behavior pivots on.

---

## 2. Data flow through one run

Walk a single `gauntlet run flows/smoke.yaml` end to end:

1. **Load & validate** (`cli.cmd_run` → `flow.load_flow`, `rules.load_rulepack`,
   `waivers.load_waivers`). All config is parsed and validated *before any step
   runs*. A bad DAG, an unknown dependency, a malformed regex, or a broken
   waiver is a **config error (exit 2)** — never a surprise mid-run. Regexes are
   compiled exactly once here.

2. **Build the executor.** A `LogEvaluator` is constructed from the compiled
   rulepacks + waivers and injected into the `Scheduler` as a `ResultEvaluator`
   (a `Protocol` — the scheduler doesn't know or care what evaluation *is*).

3. **Schedule** (`scheduler.Scheduler.execute`). A ready-set loop over a
   `ThreadPoolExecutor`:
   - `flush_ready()` submits every step whose dependencies are all
     `PASS`/`WAIVED`, and marks `SKIPPED` (transitively, to a fixpoint) any step
     with a blocking dependency.
   - As futures complete, results are recorded and `flush_ready()` runs again.
   - On the first non-passing result, `stop_submitting` flips (unless
     `--keep-going`); in-flight steps still finish.

4. **Run one step** (`scheduler._run_step` → `steps.ShellStep.run`). The command
   runs as a real subprocess in its own process group, stdout+stderr streamed to
   `runs/<run_id>/<step_id>/output.log`. Timeout → group kill (see §5). Retries
   are naive immediate re-attempts; a pass after ≥1 retry sets `flaky=True`.

5. **Evaluate** (`parser.LogEvaluator.evaluate`). The raw `StepResult` (which
   only knows the exit code so far) is enriched: the log is streamed through the
   rulepack into `Violation`s, waivers are applied in place, and
   `finalize_status()` re-derives the final `StepStatus`.

6. **Persist.** A `RunRecord` (identity, timing, verdict, all `StepResult`s) is
   written to `runs/<run_id>/manifest.json` **and** to SQLite via `store.save`.

7. **Report / diff.** `report.render_run` prints the terminal summary.
   Later, `diff.diff_runs` compares two `RunRecord`s into regression buckets.

---

## 3. The status enum is the product

```python
class StepStatus(str, Enum):
    PASS     # clean
    FAIL     # nonzero exit OR unwaived ERROR violations
    WAIVED   # would have failed, all ERRORs waived
    TIMEOUT
    SKIPPED  # upstream dependency failed
```

Two derived sets drive scheduling:

```python
PASSING_STATUSES  = {PASS, WAIVED}                 # satisfy a dependent
BLOCKING_STATUSES = {FAIL, TIMEOUT, SKIPPED}       # block dependents → SKIPPED
```

Everything interesting is a consequence of these five states being distinct:

- `WAIVED` ≠ `PASS` → debt stays visible.
- `SKIPPED` ∉ "failing" in a diff → the diff blames the real culprit upstream,
  not the steps it starved.
- `TIMEOUT` is sticky and separate from `FAIL` → you can tell "hung" from "broke".

### The pass/fail policy (`parser.finalize_status`)

```
TIMEOUT / SKIPPED         → unchanged (sticky)
any unwaived ERROR        → FAIL
ERRORs exist, all waived  → WAIVED
no ERRORs, exit == 0      → PASS
no ERRORs, exit != 0      → FAIL
```

This is the "a tool can exit 0 and still fail" rule, and the inverse (a tool can
exit nonzero but be waived into `WAIVED`), which is exactly how real EDA flows
behave.

---

## 4. Folder / module structure

```
gauntlet/
  models.py        # dataclasses + StepStatus; the shared vocabulary
  flow.py          # YAML → validated FlowSpec (unique ids, known deps, no cycles)
  steps.py         # Step ABC + ShellStep (subprocess, process groups, timeouts)
  scheduler.py     # ready-set DAG executor over ThreadPoolExecutor + retries
  parsing/
    rules.py       # rulepack YAML → compiled regex Rules
    parser.py      # stream log → Violations; LogEvaluator; finalize_status
    waivers.py     # waiver YAML → Waivers; apply_waivers (in place)
  store.py         # SQLite persistence (4 tables, no ORM, in-place migration)
  diff.py          # RunRecord × RunRecord → RunDiff buckets
  graph.py         # DAG layering, critical path, ascii / mermaid / dot
  stats.py         # per-step stability across run history
  report.py        # terminal rendering (run / history / diff)
  term.py          # TTY-only status colors (NO_COLOR / FORCE_COLOR aware)
  junit.py         # JUnit XML for CI test tabs
  markdown.py      # GitHub-flavoured summaries ($GITHUB_STEP_SUMMARY)
  html_report.py   # single-file HTML reports (run + diff)
  ui/              # shared design system: theme.py, charts.py (SVG), pages.py
  server.py        # `gauntlet serve`: read-only stdlib dashboard
  cli.py           # argparse entrypoint; wires it all together

flows/  rulepacks/  waivers/     # declarative YAML inputs
tools/mock/                      # deterministic fake lint/sim/synth
tests/                           # pytest: offline, deterministic, cross-platform
web/                             # static showcase site (Vercel deploy target)
```

Dependency direction is strictly one-way: `models` ← everything; `cli` → all;
nothing in `parsing/` imports the scheduler; the scheduler talks to evaluation
only through the `ResultEvaluator` Protocol.

---

## 5. The hard parts (and how they work)

### 5.1 Killing the whole process tree on timeout

The classic infra bug: a step is `bash -c "run_sim ..."`. You time it out and
kill the `bash` PID — but `run_sim` was a child, gets orphaned, and keeps
running, holding a license and a worker slot. GAUNTLET avoids this by launching
each step as its **own process group / session** and killing the *group*:

- **POSIX:** `start_new_session=True` → new session; on timeout,
  `killpg(pgid, SIGTERM)`, wait `GRACE_S=3s`, then `killpg(pgid, SIGKILL)`.
- **Windows:** `CREATE_NEW_PROCESS_GROUP` → on timeout, send `CTRL_BREAK_EVENT`
  to the group, wait the grace period, then `taskkill /F /T /PID` — the only
  call that reliably reaps grandchildren on Windows (there is no `SIGTERM`).

The escalation (polite signal → grace → hard kill) means well-behaved tools get
a chance to flush and clean up, while a wedged tool still dies on schedule.

### 5.2 Real parallelism with threads

The instinct is asyncio or multiprocessing. But the workload is
*subprocess-bound*: each worker's job is to `Popen` and then block in
`.wait()`. During that blocking wait the **GIL is released**, so a
`ThreadPoolExecutor` gets true parallelism across steps with none of asyncio's
colored-function ceremony or multiprocessing's pickling. The scheduler stays
plain, synchronous, and trivially testable.

### 5.3 The ready-set loop and the SKIPPED fixpoint

Rather than topologically sorting up front, the scheduler keeps a `pending` set
and repeatedly asks "what's ready now?" This makes `--keep-going`, transitive
skips, and stop-on-first-failure fall out naturally. The skip cascade loops to a
fixpoint so that skipping a step immediately re-evaluates its dependents in the
same pass — a failure at the top of a chain marks the entire chain `SKIPPED`
before the next future is awaited.

### 5.4 Streaming logs, not slurping them

`parser.parse_log` iterates the file line by line (`for line_no, line in
enumerate(fh)`) and matches each line against the rulepack (first rule wins).
Real EDA logs are gigabytes; `f.read()` would be a memory bomb. The captured
rule id is preferred over the rulepack's own id when the pattern captures one
(e.g. `SIM-ERR-007` from a generic `SIM-ANY-ERROR` rule), so waivers can target
specific error codes.

### 5.5 Determinism as a test strategy

The mock tools (`tools/mock/*`) seed their RNG from
`GAUNTLET_SEED:tool:suite:design`, so with a seed the output is **byte-identical
between runs** — tests can assert on exact violations. A separate
`GAUNTLET_FLAKE=<prob>` knob injects an extra unwaived ERROR on demand. This is
what lets the test suite *prove the diff catches a regression* — the entire
reason the platform exists — without any nondeterminism.

### 5.6 Timing capture and the critical path (v0.2)

The scheduler stamps every step with `start_s`/`end_s` against one monotonic
origin taken in `execute()`, plus `attempts`. Three things fall out of that:

- **The timeline** in reports is drawn from real windows, so you can *see*
  that the two sims overlapped and synth waited for the slower one.
- **Peak parallelism** (`graph.max_parallelism`) is a sweep over start/end
  events, ends sorted before starts so touching windows don't count as overlap.
- **The critical path** (`graph.critical_path`) is the heaviest dependency
  chain weighted by duration — the chain that bounded wall-clock time, i.e. the
  one worth making faster. Unweighted, the same function gives the deepest chain.

Run duration now comes from the step windows (millisecond precision) and falls
back to the second-precision ISO stamps for v0.1 runs.

### 5.7 Serving logs without becoming a file server (v0.2)

The dashboard's log viewer takes a run and a step, looks the log path up in
the database, resolves it, and refuses anything that doesn't resolve inside
the runs directory. The URL never carries a path, and a tampered database
can't point it at `/etc/passwd` — there's a test that tries exactly that.
Logs are streamed with a line and byte cap, because the whole point of
streaming (§5.4) is that real logs are gigabytes.

---

## 6. Persistence schema

Four tables, no ORM (`store.py`):

```sql
runs(run_id PK, flow_name, started_at, finished_at, status, git_commit, git_branch)
step_results(run_id, step_id, status, exit_code, duration_s, log_path, flaky,
             start_s, end_s, attempts, PRIMARY KEY(run_id, step_id))
violations(run_id, step_id, rule_id, severity, line_no, message, waived,
           waive_reason, waive_owner)
run_edges(run_id, step_id, dep)   -- the DAG as it was when the run executed
```

**Migrations are additive and automatic.** v0.2 added the timing, attempt,
waiver-owner and git columns plus `run_edges`. Opening a v0.1 database runs
`ALTER TABLE … ADD COLUMN` for whatever is missing and nothing else — old runs
keep loading (their timing is simply `None`, and reports say so), new runs land
in the same file. `run_edges` stores one node row per step (`dep IS NULL`)
before its edges, so steps with no dependencies survive and flow order
round-trips.

`latest` and `latest~N` resolve to run ids in `RunStore.resolve`, ordered by
`started_at` and then insertion order — two runs that start in the same second
(common in CI) still have a well-defined "latest".

The `violations.waive_reason` column is a deliberate deviation beyond a minimal
schema: it lets `gauntlet report <run_id>` reproduce the *full* report —
including each waiver's reason — from the DB alone, long after `runs/` is
cleaned up. Saves are idempotent (delete-then-insert by `run_id`).

---

## 7. Tradeoffs and scope guards

Consciously **out of scope** (and why):

- **No plugin system / no config server** — would dwarf the core loop this
  project exists to illustrate.
- **No asyncio** — wrong tool for a subprocess-bound workload (see §5.2).
- **No control plane** — `gauntlet serve` (v0.2) is a *read-only* view over
  the SQLite file: no auth, no writes, no job queue, localhost by default. The
  CLI stays the only thing that runs flows. The `web/` showcase site is a
  separate static artifact.
- **Naive retries only** — immediate re-attempts, no backoff. Enough to model
  "flaky pass is information, not a pass"; a real system would add jittered
  backoff and per-tool policy.

What a production version would add next: distributed workers (the `Step` ABC is
already the seam), incremental/affected-only scheduling, artifact/log object
storage, auth + multi-user on top of the dashboard, and waiver expiry.

---

## 8. Where to start reading the code

1. [`gauntlet/models.py`](gauntlet/models.py) — the vocabulary. Read this first.
2. [`gauntlet/parsing/parser.py`](gauntlet/parsing/parser.py) — `finalize_status` is the product in 8 lines.
3. [`gauntlet/scheduler.py`](gauntlet/scheduler.py) — `execute()` and the ready-set loop.
4. [`gauntlet/steps.py`](gauntlet/steps.py) — `_kill_process_group` is the hard part.
5. [`gauntlet/diff.py`](gauntlet/diff.py) — the payoff.
6. [`gauntlet/graph.py`](gauntlet/graph.py) and [`gauntlet/stats.py`](gauntlet/stats.py) — what v0.2 learned to say about a run, and about history.
7. [`gauntlet/server.py`](gauntlet/server.py) — the whole dashboard, routes to containment check, in one file.
