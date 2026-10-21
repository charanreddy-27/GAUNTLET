# GAUNTLET — Interview Prep

Rehearse from this. It's written to be spoken, not just read. Practice the
2-minute walkthrough out loud until the *shape* is muscle memory — then you can
improvise the details.

---

## The 30-second elevator pitch

> GAUNTLET is a miniature IP-regression platform — the core loop of the
> infrastructure behind chip-design CI, rebuilt in pure Python. It runs a
> dependency graph of tools as real subprocesses, parses their logs the way real
> EDA tools force you to — where a tool can exit zero and still have failed —
> tracks known failures as *waivers*, and then does the thing that actually
> matters: a run-to-run **diff** that surfaces what newly broke and exits
> non-zero so CI can gate on it. One dependency, forty-three tests, fully
> offline.

---

## The 2-minute walkthrough

> **The problem.** In chip design, a nightly regression runs dozens of tools
> across a dependency graph. Two things make it hard that a normal task runner
> ignores: the logs are gigabytes and the exit codes lie — a tool can exit zero
> and still have failed, so the *log* is the source of truth. And what a team
> actually needs isn't "did tonight pass," it's "what broke that was working
> yesterday." I wanted to understand that infrastructure, so I rebuilt its core
> loop end to end.
>
> **The shape.** A flow is a YAML DAG. A scheduler submits a step only when all
> its dependencies have passed, runs it as a real subprocess in its own process
> group, and streams the log to disk. Then a log evaluator parses that log line
> by line against a regex rulepack, applies waivers, and derives a final status.
>
> **The status model is the whole design.** There are five states, not two:
> PASS, FAIL, and then WAIVED, TIMEOUT, SKIPPED. WAIVED means "this failed, but
> it's a known, owned debt" — it stays visible, never a silent pass. SKIPPED
> means an upstream step failed, so this step gives no new evidence about
> itself. Those distinctions are what make the diff meaningful.
>
> **The payoff.** I persist every run to SQLite, and `diff` compares two runs
> into buckets: NEW FAILURES, FIXED, STILL FAILING. It exits non-zero on a new
> failure, so it's CI-usable. To prove it works, the mock tools are seeded for
> byte-identical output, with a flake knob that injects a regression on demand —
> so a test can assert "the diff catches exactly this new failure."
>
> **The hard part.** Timeouts. If you kill the shell wrapper but its child
> simulator was a separate process, you orphan a running tool. So every step
> launches in its own process group and I kill the *group* — polite signal,
> grace period, then hard kill — and I made that work on both POSIX and Windows,
> which have completely different process-control models.
>
> **What I deliberately didn't build:** no plugin system, no asyncio, no web
> server in the core. Keeping it small enough to read was the point.

---

## STAR stories

### STAR 1 — Killing the process tree on timeout (the "it got hard" story)

- **Situation.** A timed-out step needs to actually stop. My first version
  called `proc.wait(timeout=...)` and killed `proc.pid` on expiry.
- **Task.** Guarantee that a timeout kills the tool *and everything it spawned*,
  with no orphans holding worker slots — on every OS the tests run on.
- **Action.** Launched each step in its own process group
  (`start_new_session=True` on POSIX, `CREATE_NEW_PROCESS_GROUP` on Windows) and
  killed the whole group with an escalation: `SIGTERM → 3s grace → SIGKILL` on
  POSIX; `CTRL_BREAK_EVENT → grace → taskkill /F /T` on Windows, since Windows
  has no SIGTERM and only `taskkill /T` reliably reaps grandchildren.
- **Result.** Timeouts are deterministic and leak-free; the timeout test asserts
  a `sleep 999` step ends in well under the timeout with no lingering process,
  and it passes identically on Linux, macOS, and Windows.

### STAR 2 — Making "the diff catches a regression" a provable test

- **Situation.** The product's whole reason to exist is the run-to-run delta,
  but subprocess output is nondeterministic, which makes it hard to test.
- **Task.** Prove, in an offline unit test, that introducing a specific failure
  produces exactly one NEW FAILURE in the diff.
- **Action.** Seeded the mock tools' RNG from
  `SEED:tool:suite:design` so a fixed seed yields byte-identical logs, and added
  an orthogonal `GAUNTLET_FLAKE` probability that injects one unwaived ERROR.
  Run once clean, once flaked, then diff.
- **Result.** A deterministic test that runs the real pipeline end to end and
  asserts `new_failures == [sim_unit]` with verdict `REGRESSION` — the feature
  is regression-tested by construction. (43 tests, ~3s, no network.)

### STAR 3 — Cross-platform test suite without coreutils

- **Situation.** The scheduler tests used `true`, `false`, `sleep`, `test -f` —
  which don't exist on Windows, so the suite was silently OS-locked and 7 tests
  failed there.
- **Task.** Make the exact same behavioral tests (exit codes, timing, marker
  files, fail-once retries) run identically on every OS.
- **Action.** Wrote a tiny `tests/probe.py` that reimplements those primitives
  in Python (`ok`, `fail`, `sleep`, `touch`, `exists`, `fail-once`, `echo`), and
  a `conftest` helper that builds a double-quoted command line valid in both
  `/bin/sh` and `cmd.exe`. Rewrote the scheduler and retry tests to use it.
- **Result.** 43/43 passing on Windows and POSIX from one codebase — and the
  tests now describe *intent* (`probe("fail")`) instead of shell trivia.

---

## Likely technical Q&A

**Q: Why threads instead of asyncio or multiprocessing?**
The workload is subprocess-bound — each worker's job is to spawn a process and
block in `.wait()`, during which the GIL is released. So threads give real
parallelism for free, without asyncio's function-coloring or multiprocessing's
pickling overhead. Asyncio would be right if I were doing many concurrent
network calls; here it's the wrong tool.

**Q: Why can a tool exit 0 but still FAIL?**
Because real EDA tools under-report through exit codes — they'll print `ERROR:
...` in the log and still exit 0. So the log is the source of truth:
`finalize_status` fails a step if any *unwaived* ERROR remains, regardless of
exit code. The inverse is also true — a nonzero exit whose errors are all waived
becomes WAIVED.

**Q: What's the difference between WAIVED and just passing?**
A waiver is a debt, not a fix. WAIVED is a distinct status that stays visible in
every report, with an owner and a reason. If you collapsed it into PASS, known
failures would go invisible and nobody would ever pay the debt down.

**Q: Why is SKIPPED not counted as a failure in the diff?**
A skipped step didn't run, so it gives you no new evidence about *itself*. If you
counted it as failing, one broken upstream step would light up its whole
subtree as "new failures" and bury the actual root cause. The diff blames the
step that actually broke.

**Q: How does the scheduler avoid deadlock / how does it know what's ready?**
It's a ready-set loop, not a pre-computed topo sort. Each pass, `flush_ready`
submits every step whose deps are all PASS/WAIVED and marks SKIPPED anything
with a blocking dep, looping to a fixpoint so skips cascade. Cycles can't happen
at runtime because `flow.py` rejects them at load time with a three-color DFS.

**Q: What happens on the first failure?**
By default `stop_submitting` flips — no *new* steps are submitted, but in-flight
steps finish (you don't kill healthy work). `--keep-going` overrides this so
independent branches complete, which is what you want for a nightly where you
want maximum signal per run.

**Q: How are regexes handled — performance, safety?**
Rulepacks compile to `re.Pattern` exactly once at load. An invalid pattern is a
config error at startup (exit 2), never a mid-run surprise. Matching is
first-rule-wins per line, and logs are streamed line by line so memory is O(1)
in log size.

**Q: How would this scale to real, distributed regressions?**
The `Step` ABC is the seam — its contract is just `run() -> StepResult`. A
`RemoteStep` that dispatches to a worker pool touches zero scheduler code. Beyond
that: affected-only/incremental scheduling, object storage for logs, and a web
dashboard reading from `store.py`.

**Q: How is it tested, and why should I trust the tests?**
43 pytest tests, fully offline, deterministic, cross-platform, under ~10s. They
cover DAG ordering, transitive skips, timeouts, keep-going, the log→status
policy, waiver precision, retries/flaky marking, the diff buckets, and the HTML
report. The mock tools are seeded so tests assert on exact output.

**Q: What about concurrency bugs in the shared results dict?**
Result recording happens on the main scheduler thread as futures complete
(`wait(..., FIRST_COMPLETED)`), not inside the worker threads — workers only
return values. So the shared `pending`/`results`/`statuses` state is mutated in
one place, single-threaded.

---

## "What I'd improve next" (growth & self-awareness)

- **Retry policy.** Today it's naive immediate re-attempts. I'd add jittered
  backoff and per-step configuration. (v0.2 already made "flaky" a cross-run
  metric — `gauntlet stats` counts flips and flaky retries per step.)
- **Structured log parsing.** Regex rulepacks are pragmatic but brittle for
  multi-line diagnostics. I'd add optional stateful/multi-line matchers.
- **Waiver lifecycle.** Real waivers should expire and nag. I'd add an expiry
  date and a report that flags stale waivers, so debt can't hide forever.
- **Incremental scheduling.** Right now every run is a full run. Affected-only
  scheduling (skip steps whose inputs are unchanged) is the obvious next win.
- **Observability.** Structured JSON events + timing histograms would make the
  scheduler's behavior legible under load.

---

## The v0.2 story — "what did you do after it worked?"

**Situation.** v0.1 answered "what changed between two runs?" well, but every
answer lived in a terminal. Nobody could *see* a run, CI couldn't render it,
and a step that flipped every other night looked fine in any single diff.

**Task.** Make the platform legible — to people, to CI, and across history —
without giving up the constraint that made it readable: one dependency.

**Action.** Recorded every step's window on one monotonic clock, which made a
timeline, peak parallelism and a duration-weighted critical path possible.
Rebuilt the HTML report as a design system with SVG laid out in Python (no JS
needed to read it), and put a read-only `http.server` dashboard over the same
SQLite file. Added JUnit and Markdown outputs so any CI can render a run, and
`stats` so flakiness is a number, not a feeling. Migrated old databases in
place instead of asking anyone to start over.

**Result.** 43 → 67 tests, still one dependency, and CI now gates on the delta
*and proves the gate trips* on an injected regression. Writing the
end-to-end tests also caught a real bug: two runs in the same second sorted by
their random id suffix, so `latest` could be the wrong run.

---

## Smart questions to ask the interviewer

- How does your team draw the line between a hard failure and a known,
  tracked-but-tolerated one — do you have a waiver/mute concept, and how do you
  keep it from becoming a graveyard?
- When a nightly regression goes red, what's the actual path from "red" to "the
  one person who should look at it"? How much of that is automated?
- Where does most of your CI *time* go — is it the tools themselves, scheduling
  overhead, or flaky-retry churn?
- For infrastructure like this, how do you test the platform itself? Do you have
  a determinism strategy for inherently nondeterministic tool output?
- What's the failure mode that wakes someone up at 2am — and what would it take
  to make it not do that?

---

## One-liners worth having ready

- *"A green build isn't the question — the delta is."*
- *"Exit codes lie; logs don't."*
- *"A waiver is a debt, not a fix — so WAIVED can't be silent."*
- *"Killing a process cleanly is harder than starting one."*
- *"The status enum is the design; everything else is plumbing."*
