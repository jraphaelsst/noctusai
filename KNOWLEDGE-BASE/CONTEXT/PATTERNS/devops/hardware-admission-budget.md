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
  `gate_sweep` leg and `task_branch` merged-tip gate.
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
- **Before dispatching agents:** check status. If the result is `would_wait`, hold and
  re-check on the timer instead of dispatching.
