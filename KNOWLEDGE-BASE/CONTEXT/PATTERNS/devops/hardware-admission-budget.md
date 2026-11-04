# Hardware admission budget — push the machine, behind a gate

> Mechanism: `noctus.dev.hw_admission` (`mcp/noctusai/tools/noctus/dev/hw_admission.py`)
> · config `deploy/fleet/hardware-budget.json` · capacity log `~/.noctus/hw-admission.ndjson`.
> Born 2026-11-04 (owner: "push the machine, but with safety gates … measure our actual
> system's capacity … make it dynamic … multiple setups and different machines").

## 1 · Why

One 8-core / 8 GB laptop runs many Claude sessions, and each one fans out agents and
gates. On 2026-11-04:
- The load average reached 74, swap usage hit 5.4 of 6 GB, and about 31 Claude processes were running.
- The noctusai MCP server dropped.
- Two heavy suites overlapping starved each other. The RG integrate went false-red with 40
  vitest timeouts in tests the diff never touched, plus an e2e `page.goto` timeout.

Every heavy suite that ran **alone** was green. Overlap destroys verdicts, wastes the hardware,
and buys a rewrite instead of a save. A false-red is a reliability failure for us, and later for
clients.

## 2 · The rule

**Heavy work runs only when a machine-wide slot is free and the machine's measured
capacity admits it.**
- Heavy means: product pytest suites, vitest, playwright/e2e, vite build, and every
  `gate_sweep` leg, `task_branch` merged-tip gate and `predeploy_check` run.
- Light work never takes a slot: git, single tests, keepers, MCP reads, editing.

| Knob (phase `build`, owner-approved 2026-11-04; 2 slots since ~20:35Z) | Value |
|---|---|
| Heavy jobs at once, machine-wide | 2 (was 1 until 2026-11-04 ~20:35Z) |
| Workers inside one heavy job (`job_workers`) | 2 (vitest `--maxWorkers`, playwright `--workers`) |
| Admit when | CPU idle ≥ 15 % over 10 s **and** free + reclaimable memory ≥ 1 GB **and** swap-out < 50 pages/s; a 2nd job also needs memory left after the running job's expected peak (memory-aware veto) |
| Claude sessions | ≤ 3 (advisory: surfaced, not enforced) |
| Wait before giving up | 30 min, polling every 20 s |

**Two slots is the normal shape (owner, 2026-11-04 ~20:35Z: "make the 2-slot the normal
methodology" · "lower the cpu limit to 15%, not 25%").** Evidence: trial-mh2-mem
(17:10–17:57Z) ran 40.6 jobs/h with 2 failed and 0 timeouts, against 21.8 jobs/h with 13 failed
+ 6 timeouts at one slot (06:30–16:52Z). Its auto-abort came from swap while ZERO slots were
held — ungated load — which is why aborts now count gated samples only (§7). Memory stays the
binding limit: the memory-aware veto refuses the 2nd job when free memory minus the running
job's expected peak falls under the floor. Every session uses both slots; nothing to opt into.

**The slot bounds how many jobs run; `job_workers` bounds how wide each one fans out.**
With one slot, a single `vitest run` still started about 7 workers on the 8-core M2. The cap
is applied where real gate subprocesses launch (`gate_sweep._default_run_gate` via
`hw_admission.cap_worker_argv`). An explicit cap already in the command wins. Without the knob
the default is cores / (2 × `max_heavy`), and an unreadable budget gives 1. `hw_admission.py run`
caps a known fan-out command too. Every `ran` / `not_admitted` row carries a top-level
`job_workers`: the cap the job ran with, or null for a job with no fan-out. That field is the
contract `usage_eval` reads; never parse it out of argv. Pytest runs
single-process here (no xdist), so it needs no cap.

**Don't gate on load average alone on macOS.** It counts threads blocked on I/O and memory,
and it decays slowly. On 2026-11-04 the load was 21–29 while the CPU sat 89 % idle. Memory
is the binding limit on this machine.

**Swap-out is a rate over the MEASURED interval, in pages.** `swapout_per_s` is
pages/s (16 KB pages on Apple Silicon); `swapout_mb_per_s` is the same rate in MB, and
`elapsed_s` is the interval it was divided by. Until `probe_version` 2 (2026-11-04) the
probe divided by the nominal `sample_s`. Under load the interval stretches (`top`'s
startup alone can take many seconds), so the old rows read about 10× high: 35669/s at
04:02Z. Read any row without `probe_version`, or with version 1, as an upper bound.
Every log row carries `probe_version`, and `usage_eval`'s sync copies it into
`dev_telemetry_os.extra`. Bump it whenever a metric changes meaning.

## 3 · Guarantees

- **No silent start.** A job that isn't admitted is **not run**:
  - `gate_sweep` records it as `waiting_for_slot`, and the verdict is `inconclusive`.
  - `task_branch integrate` returns `waiting_for_slot` and does not push. There is no
    accept-anyway path.
  - Shell runners get exit code 75.

  This replaces the per-session "wait ≤ 15 min for load < 12, then start anyway" fallback,
  which was a silent bypass.
- **Machine-wide.** Slots are `flock`s under `~/.noctus/hw-slots`, shared by every session
  and worktree. The OS frees a slot when its holder dies. Child processes inherit the
  parent's slot (`NOCTUS_HW_SLOT_HELD`), so a nested run never deadlocks.
- **Fail closed.** If the budget is missing or malformed, the result is `budget_error`
  (not admitted). There is never a fallback to "no gate".
- **Tests stay real.** The gate wraps real subprocess runs only. An injected test runner
  passes `admit=None` as a declared parameter, so nothing is patched.

## 4 · Dynamic per machine

- Phase resolution: `NOCTUS_HW_PHASE` > `hosts[<hostname>].phase` > top-level `phase`.
- `hosts[<hostname>].overrides` changes individual knobs for one machine. A new machine adds
  its own `hosts` row.
- The `stable` and `big-box` phases are placeholders. Set them from data:
  `noctus.dev.hw_admission action=report` summarizes every admitted run (wait, duration,
  peak child RSS, metrics at admit) and every refusal.
- The same file becomes the owner-editable setting in core admin. That's queued under platform
  observability (memory `project-platform-observability`).

## 5 · Adaptive re-check timer

`action=sample` logs one monitoring tick. `recheck_timer()` then works from the measured
overload episodes:
- **Window:** 7 days, so it sees both the daily and the weekday rhythm and still adapts
  within a week.
- **Re-check interval:** the median overload episode length × 1.1 (a little longer than the
  typical episode), clamped to 60–1800 s.
- **Pattern change:** `pattern_changed` is set when the last 24 h median differs from the
  7-day median by more than 30 %.
- With no data yet, the interval defaults to 900 s.

This is the first instance of the platform observability organ: telemetry, then a baseline,
then change detection, then alerts.

## 6 · How to use

- **Status:** `noctus.dev.hw_admission` (or `python mcp/noctusai/tools/noctus/dev/hw_admission.py status`).
- **Any heavy shell run:**
  `python mcp/noctusai/tools/noctus/dev/hw_admission.py run --job <kind:target> -- <cmd…>`
- **Self-gating tools — don't wrap them.** `gate_sweep`, `task_branch` integrate and
  `predeploy_check` take the slot themselves, and they do it AFTER their cheap preconditions
  (stale tree, measured tree identity). An outer `hw_admission.py run` wrapper waits first and
  checks second: on 2026-11-04 a wrapped `gate_sweep` waited 57 min, then was refused as
  `refused_stale_tree`. A wrapper is harmless (the inner call inherits the slot) but costs
  the wait.
- **Time-boxes count running time, never slot-wait.** The `task_branch` merged-tip ceiling
  (`NOCTUS_GATE_OVERALL_CEILING_S`, default 3600 s) runs on an active clock that advances only
  while one of the sweep's gates is running. Before 2026-11-04 it was a wall-clock deadline.
  Once gates had to wait for the slot, a ~25-gate integrate at `max_heavy` 1 timed out with 6
  gates never run. Admission must never turn a runaway guard into a guaranteed timeout: wait
  limits belong to `heavy_slot` (`wait_s`), run limits to the ceiling.
- **An e2e gate must serve its OWN tree.** Every `playwright.config.ts` here uses a fixed
  `webServer.port` with `reuseExistingServer: !process.env.CI`. When something already listens
  on that port (another worktree's dev server, a baseline run, another session's e2e),
  Playwright silently reuses it and the spec tests a different tree. That gives a false red
  (e2e:core, two integrates in a row, 2026-11-04), or a false green for code never served.
  `gate_sweep` therefore checks the port before the slot wait AND right before launch. If the
  port is busy, the gate reports `HARNESS INVALID` (`webserver_port_free`, naming the pid),
  does not run, and is not counted. It also runs e2e with `CI=1`: reuse is off, and the config's
  CI settings apply (retries 2, github reporter), the same as CI.
- **Waiters queue first-come, first-served; an integrate waits its turn instead of quitting.**
  Before 2026-11-04 every waiter polled for a free slot independently, which is a race with no
  fairness. noctusai-04's integrate 6 lost that race to another session's 9 predeploys, gave up
  after `wait_s` (1800 s) as `waiting_for_slot`, and needed a human to relaunch it. Now:
  - Every `heavy_slot` waiter drops a ticket in `~/.noctus/hw-queue/`. Only the oldest live
    tickets (as many as there are free slots) may try a slot. Tickets of dead pids are swept.
  - Each move in line writes a `queued` row to the capacity log, with `queue_position`, `ahead`
    and `eta_s` (median recent run duration × rounds ahead). `status` lists the `queue`, and
    `Admission.queue_position` lands on the `ran` and `not_admitted` rows.
  - `task_branch` integrate's merged-tip gates queue against ONE shared deadline
    (`hw_admission.shared_deadline_admit`): `NOCTUS_INTEGRATE_SLOT_WAIT_S`, default 4 h. Only
    after that is the result `waiting_for_slot`.
  - The queue is best-effort across code versions: a waiter on older code still races, but it
    can only jump queued waiters, never an admitted job.
- **An integrate retry runs only what changed.** Before 2026-11-04 every retry re-ran all ~30
  merged-tip gates from zero (~45 min), including gates already green on identical inputs. Each
  retry was a new lottery against load, on a moving `dev`. Now `task_branch` integrate (the
  merged-tip check and its baseline) turns on `gate_verdict_cache`, and a GREEN is reused when
  its key is unchanged. The key combines:
  - the gate's argv and cwd;
  - the git tree ids at HEAD of its input closure, plus every root-level tracked file;
  - a runner fingerprint: the `gate_sweep` and `harness_signatures` source, the interpreter and
    `node` stamps, the e2e CI flag, and `job_workers`.

  The input closure depends on the gate:
  - product gates use `products/<slug>/`, `seed/`, `templates/` and `deploy/`;
  - seed gates use `seed/` and `templates/`;
  - mcp, keeper and contract gates read the whole repo, so they are never cached.

  The cache only stores unambiguous greens: no harness flag, timeout, slot wait or `false_red`.
  A dirty closure is never looked up or stored. A hit costs no slot. It carries `cached_from`
  (tip, ts, original duration), and the sweep warns with the list of reused gates. The store is
  `~/.noctus/gate-verdicts.ndjson` (machine-local); the kill switch is
  `NOCTUS_GATE_VERDICT_CACHE=off`.
- **A red under load re-runs its failing tests once, alone, before it counts.** At
  `max_heavy` 1, integrates 4 and 5 (2026-11-04) each failed on a DIFFERENT timing-sensitive
  test that passed in isolation: one vitest assertion at 2333 ms, and one pytest failure that
  nobody could name. `gate_sweep` now handles this in two ways:
  - Pytest gates carry `failing_tests`, the node ids parsed from the `FAILED`/`ERROR` lines.
  - When load/core is at least `LOAD_PER_CORE_SUSPECT` (1.5), a vitest or pytest red with at
    most `RERUN_MAX_FAILING` (10) named failures re-runs ONLY those tests once, in the same slot.
    - Green on the rerun: the gate is not red, and it is marked `false_red` plus
      `flaky_under_load`. The `false_red` flag also lands on the capacity log's `ran` row
      (`outcome.false_red`) for usage_eval.
    - Red again: it is a real red, carrying the rerun's names.
    - No verdict (usage error, nothing collected): the first red stands.

  On a quiet host a red stays red with no rerun, because a failure there is signal. The vitest
  timeout-shaped rerun (all failures are timeouts) is separate and fires on any host.
- **Pin the tree for evidence runs.** Run predeploy against a tree nothing will
  fast-forward under it: `--predeploy-check <slug> --worktree-path <detached worktree>`.
  The result carries `tree.head_start` / `head_end` / `behind_origin_dev`. A HEAD that moves
  mid-run makes it `inconclusive` (`tree_moved`), because a straddled run judges neither tree.
- **Before dispatching agents:** check status. If the result is `would_wait`, hold and
  re-check on the timer instead of dispatching.

## 6a · Enforcement: the heavy-run PreToolUse guard

The wrap rule used to be discipline-only (one agent file + this doc), so on 2026-11-04 several
sessions ran suites ungated (1,253 + 273 + 568 tests) and the 8 GB machine swapped. Gate and
methodology ship together: `scripts/hooks/claude-guard-heavy-run.py` (fail-closed via
`_guard_failclosed`, marker `[noc-guard:heavy-run]`, PreToolUse on `Bash`) over the pure
`mcp/noctusai/tools/noctus/dev/heavy_run_guard.py::decide`.

- **Matched** (per command segment, shlex token scan, so `cd x && pytest`, `a | pytest`,
  `(pytest)` and `bash -c "..."` are seen): `pytest` / `py.test` / `python -m pytest`,
  `vitest`, `playwright test`, `vite build`, `npm|pnpm|yarn [run] test|build[:x]`, and the
  same behind `npx` / `pnpm exec`.
- **Allowed:** a segment that runs `hw_admission.py` (the wrapped command is its argument);
  `--collect-only` / `--co` / `--version` / `--help` / `-h`; commands that merely mention the
  word (`grep pytest f`, `echo "pytest"`).
- **Deny message** prints the exact wrapped command with a suggested `--job`
  (`pytest:<dir>` / `vitest:<product>` / `build:<product>`).
- **Escape:** inline `NOC_HW_UNGATED_OK=<non-empty reason> <cmd>`; the reason is echoed to
  stderr. An empty reason is still a deny. Use it only when the gate itself is what is being
  debugged.
- **Self-gating tools are untouched:** `task_branch` integrate, `gate_sweep` and
  `predeploy_check` spawn their gates inside the MCP server process; a PreToolUse hook only
  sees the agent's own tool calls, never an MCP server's subprocesses.
- **Limits (stated):** `$(...)`, backticks, `xargs pytest`, aliases and wrapper scripts are not
  resolved; the hardware gate and CI stay the backstops.

## 7 · Load experiments: time-boxed trials

To find this machine's real limit (the point where adding concurrency stops adding throughput,
or starts producing false-reds), raise the limit in **scheduled, measured steps**:

- **Where the steps live.** `schedule` entries in the budget file
  (`{phase, from, until, hosts, abort}`), applied to the whole machine. While an entry is
  active it overrides `hosts[].phase`; the env var `NOCTUS_HW_PHASE` still wins.
- **First run, 2026-11-04.**
  - Baseline A: `build`, 03:45Z–05:45Z.
  - B: `trial-mh2` (two heavy jobs at once, CPU-idle floor lowered to 25 %), 05:45Z–07:45Z.
  - C: `trial-mh3`, 07:45Z–08:25Z.
  - A step with 4 heavy jobs runs only if `trial-mh3` comes out clean.
- **Every row is tagged.** `sample`, `ran` and `not_admitted` rows all carry `phase`. `ran`
  rows also carry `outcome` (exit code, harness_suspect, timed_out).
  `report(since, until)['by_phase']` compares the steps.
- **Automatic abort.** If `consecutive` samples in a row breach the limits (reclaimable
  memory under 500 MB, or swap-out at or above 50 pages/s), the trial is aborted. The abort is
  stored in `~/.noctus/hw-trial-aborts.json`, keyed to that step (`phase@from`), and the
  machine goes back to its normal phase for the rest of that window. **Every later step chained
  to it** (its `from` equals the previous step's `until`) is cancelled with it, by construction
  (`cancelled_steps` on the `trial_aborted` row). A stepped experiment never climbs past a
  failed step: on 2026-11-04, `trial-mh3` had to be cancelled by hand after `trial-mh2` swapped.
- **The slot count is a ceiling; memory decides the second job.** A heavy job joining others
  is admitted only if `reclaimable − expected peak ≥ min_reclaimable_mb`. The expected peak is
  the p90 of that job's measured `children_peak_rss_mb`, else its kind's (`gate:pytest`), else
  `default_job_peak_mb` (1024). The measure is the largest single child, so multi-process jobs
  are under-counted: treat it as a floor. The first heavy job is judged by the plain
  thresholds only.
- **How to read verdicts during a trial.** A red under `trial-*` is a data point. It still
  blocks the integrate, because reds always block. Re-run it at `build` before trusting it or
  fixing anything. A green under load can be trusted: overlap produces false-reds, not
  false-greens.
- **The output.** The knee: the highest concurrency where throughput still rises and the
  false-red rate stays near 0. Write it into the budget as a durable phase row, and record
  the rationale here.

- **Only gated samples count toward an abort** (owner, 2026-11-04). trial-mh2-mem aborted at
  17:57Z partly on a sample that held ZERO slots but swapped at 3023 pages/s from Chrome and
  ungated sessions. That penalized the gate for load it never admitted. A sample with
  `busy_slots == 0` now neither counts nor breaks the streak, and admission still refuses new
  work on a swapping machine. Machine-wide counting comes back with `"count_ungated": true` in
  the rule.
- **Results so far (usage_eval, noctusai-3d).**
  - 1 slot, 06:30–16:52Z: 21.8 jobs/h, 13 failed + 6 timeouts, swap max 396 MB/s.
  - 2 slots + memory-aware admission (trial-mh2-mem), 17:10–17:57Z: 40.6 jobs/h, 2 failed,
    0 timeouts, same average wait, swap max 144 MB/s.
  - Next step: trial-mh3-mem (3 slots, memory veto, `job_workers` 2), 21:00–23:00Z (moved from 19:20Z: the stop-rule change could only land after the queue drained).

## 8 · Measured by

Every admission and sample in the capacity log is joined with Claude usage (tokens, cost, chars per session) by `noctus.dev.usage_eval` — before/after any phase change, `action=compare`. → `KB § PATTERNS/devops/usage-evaluation.md`
