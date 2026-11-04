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

| Knob (phase `build`, owner-approved 2026-11-04) | Value |
|---|---|
| Heavy jobs at once, machine-wide | 1 |
| Admit when | CPU idle ≥ 50 % over 10 s **and** free + reclaimable memory ≥ 1.5 GB **and** swap-out < 50 pages/s |
| Claude sessions | ≤ 3 (advisory: surfaced, not enforced) |
| Wait before giving up | 30 min, polling every 20 s |

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
- **Pin the tree for evidence runs.** Run predeploy against a tree nothing will
  fast-forward under it: `--predeploy-check <slug> --worktree-path <detached worktree>`.
  The result carries `tree.head_start` / `head_end` / `behind_origin_dev`. A HEAD that moves
  mid-run makes it `inconclusive` (`tree_moved`), because a straddled run judges neither tree.
- **Before dispatching agents:** check status. If the result is `would_wait`, hold and
  re-check on the timer instead of dispatching.

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
  machine goes back to its normal phase for the rest of that window.
- **How to read verdicts during a trial.** A red under `trial-*` is a data point. It still
  blocks the integrate, because reds always block. Re-run it at `build` before trusting it or
  fixing anything. A green under load can be trusted: overlap produces false-reds, not
  false-greens.
- **The output.** The knee: the highest concurrency where throughput still rises and the
  false-red rate stays near 0. Write it into the budget as a durable phase row, and record
  the rationale here.

## 8 · Measured by

Every admission and sample in the capacity log is joined with Claude usage (tokens, cost, chars per session) by `noctus.dev.usage_eval` — before/after any phase change, `action=compare`. → `KB § PATTERNS/devops/usage-evaluation.md`
