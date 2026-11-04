# Hardware capacity calibration — a process the platform runs itself

> Authored 2026-11-04 by noctusai-86 · **process_version 2** · Methodology:
> `KB § PATTERNS/devops/hardware-admission-budget.md` (the gate) ·
> `KB § PATTERNS/devops/usage-evaluation.md` (the evaluation, owned by noctusai-3d).

## Origin

Owner, 2026-11-04: "put more load on the machine and evaluate its behaviour… build the ideal
(or optimized) setup… then use it on the app." And: "we might not find the ideal point this
session, so make this a continuous-improvement process the platform runs itself periodically…
this process might change over time, so we must always be updated… keep track of work being done."

So no capacity number is final. The machine changes, the work changes, and the number of
Claude sessions changes. This roadmap is where the CURRENT number, the process that produced
it, and every cycle's evidence live.

## Who owns what

| Leg | Owner | Source |
|---|---|---|
| Gate, budget, trials, abort rule, sampler | noctusai-86 | `hw_admission.py`, `deploy/fleet/hardware-budget.json`, `~/.noctus/hw-admission.ndjson` |
| Jobs/h, failures, token + cost join | noctusai-3d | `noctus.dev.usage_eval` |
| Approving a new normal shape | **the owner** | a trial's numbers → owner's word → budget commit quoting it |

## Process (process_version 2)

One **cycle** = baseline window → one trial window → evaluation → owner decision → budget commit.

1. **Baseline** is the current normal phase (`build`). Never compare a trial against an older
   normal shape.
2. **Trial** is a `schedule` entry in the budget (2 h, one host), with an `abort` rule. An abort
   counts only GATED samples (`busy_slots > 0`); ungated load neither counts nor breaks the
   streak (since e8e2d6bb0). An abort cancels every chained later step.
3. **Evaluate** with `usage_eval` over both windows: jobs/h, failed runs, timeouts,
   `false_red` / `flaky_under_load`, wait time, swap max, reclaimable min.
4. **Decide**: the owner picks the new normal. The commit quotes the owner's words.
5. **Record** a row in the cycle log below, and bump `process_version` with a changelog line
   whenever a step of THIS process changes (not when a number changes).

A red seen inside a trial window is a data point. Re-run it at the normal phase before calling
it real.

## Phase 1 (SHIPPED)

| Slice | Commit | Verify recipe |
|---|---|---|
| Gate + budget + capacity log | 0f8133907 | `hw_admission.py status` shows `holders` + `queue` |
| `job_workers` fan-out cap | a124b5020 + a58b88666 | a `ran` row carries top-level `job_workers` |
| Memory-aware admission (expected peak per job) | adb5c4c04 | a `not_admitted` row names `memory_veto` |
| Trial schedule + abort + chained-step cancel | (on dev) | `~/.noctus/hw-trial-aborts.json` lists `cancelled_steps` |
| Rerun-once-alone under load (`false_red`) | 322d6be1d | `outcome.false_red` on a capacity-log row |
| FIFO queue + shared integrate deadline | b3b749d82 | `status.queue` lists waiters in order |
| Gate verdict cache | bedf59a5d | a retried integrate warns which gates were reused |
| Abort counts gated samples only | e8e2d6bb0 | an ungated swap sample leaves the streak unchanged |
| **2 slots is the normal shape; CPU floor 15 %** | d474c0880 + 745bcb012 | `status` shows `max_heavy` 2 |

## Cycle log

| # | Window (UTC, 2026-11-04) | Shape | Result | Decision |
|---|---|---|---|---|
| 1 | A 03:45–05:45 vs B 05:45–07:45, C 07:45–08:25 | 1 → 2 → 3 slots, CPU 25 % | B aborted on swap; probe v1 swap rates read ~10× high (fixed: probe_version 2) | stay at 1 slot; add the memory veto + `job_workers` |
| 2 | 1 slot 06:30–16:52 vs trial-mh2-mem 17:10–17:57 | 2 slots, `job_workers` 2, reclaimable 1024 | 40.6 jobs/h, 2 failed, 0 timeouts vs 21.8 jobs/h, 13 failed + 6 timeouts; auto-aborted 17:57 on swap while ZERO slots were held | owner: "2x was kinda smooth" → abort counts gated samples only; then ~20:35 "make the 2-slot the normal methodology" + "lower the cpu limit to 15%" |
| 3 | trial-mh3-mem 21:00–23:00 vs build (2 slots) from 20:49 | 3 slots, CPU 15 %, reclaimable 1024 | 42 runs, 0 failed; auto-aborted 21:38:20 on GATED swap (84.4 / 24.6 / 65.2 MB/s); reclaimable 1175–1373 MB | back to 2-slot build; 3 slots needs a looser swap limit (owner's call) |
| 4 | build 2-slot 21:38–23:15 | 2 slots, CPU 15 %, reclaimable 1024 + memory veto | 2nd slot held EMPTY at 63–80 % CPU idle; FIFO head vetoed 36+ min, 5 waiters stuck | owner ~23:15: gate suspended, then gates = CPU % + slots only (memory floor 0, veto opt-in, swap stays the net) + `~/.noctus/hw-admission-suspended` switch |

## Trigger conditions

- **T1 — next cycle.** A cycle's decision lands, OR 7 days pass, OR `report.pattern_changed`
  is true. Then schedule the next trial one step up (or down after an abort).
- **T2 — auto-tune within guardrails.** Three consecutive cycles in which the owner accepted the
  proposed shape unchanged. Then the platform may move ONE knob ONE step on its own, inside the
  guardrails below, and tell the owner after.
- **T3 — observability organ.** A second signal (prod latency, WAHA, auth failures, job queue)
  needs the same baseline + change-point + alert loop the sampler already runs for hardware.
  Then build the seed organ (Phase 3).
- **T4 — another machine.** A second host appears in `hosts`. Then it gets its own baseline
  cycle; numbers never transfer between machines.

## Phase 2 (DEFERRED, T2) — auto-tune guardrails

- Knobs the platform may move: `max_heavy` ±1, `job_workers` ±1, `min_cpu_idle_pct` ±5,
  `min_reclaimable_mb` ±256.
- Never: below `max_heavy` 1, below `min_reclaimable_mb` 768, above `max_swapout_per_s` 50.
- Every move is a trial first (2 h, gated abort), never a direct edit of the normal phase.
- Every move is reported to the owner on the same day, and the owner can revert by saying so.

## Phase 3 (DEFERRED, T3) — seed observability organ

Owner, 2026-11-04: "monitor frequently and detect patterns and changes of those patterns. This
should be a seed feature and the whole platform should be under this surveillance … warned via
whatsapp and in-app notif. noc-level." (The term is observability: telemetry → baselines →
change-point detection → alerting.)

Design sketch, to verify against the tree before building (codebase is source of truth — grep
`prod_watchdog`, `latency_report`, `platform_metrics`, `noc-daily-ops`, core notifications first):
- **Series**: one append-only series per signal, shape `{ts, signal, value, labels}`.
- **Baseline + change detector**: generalise `recheck_timer()` / `pattern_changed` (24 h median
  vs 7-day baseline, > 30 %) into the organ; per-signal thresholds owner-editable in core admin.
- **Alerts**: `noctus.dev.notify` (WhatsApp, owner's own number only) + core in-app notifications.
- **Seed-first**: Protocol + Fake + Real + factory in the seed; products consume, never re-declare.

## Anti-goals

- Never gate on load average (macOS counts I/O-blocked threads; it read 21 with CPU 89 % idle).
- Never treat a trial red as a product verdict.
- Never change the normal phase without the owner's words in the commit.
- Never copy one machine's numbers to another.

## Open questions

- Whether `max_claude_sessions_advisory` should become enforced. Today's overloads were driven
  by ungated work in other sessions, not by the gate.
- Whether the sampler loop should read the repo budget directly instead of `~/.noctus` copies
  (two copies drifted once today: the trial window was edited only in the copy).

## Decision log

- 2026-11-04: capacity is a recurring, versioned process, never a one-off (owner).
- 2026-11-04: trial aborts count gated samples only (owner: "Count gated samples only").
- 2026-11-04 ~20:35Z: 2 slots + CPU idle ≥ 15 % + reclaimable ≥ 1024 MB is the normal `build`
  shape (owner). process_version 1 → 2 (gated-only abort changed step 2).
- 2026-11-04 ~23:15Z: admission gates = CPU idle % + slot count; memory floor + memory veto OFF
  (opt-in per phase); swap stays the memory net; machine-wide suspend file added (owner, after the
  veto stalled every session at 63 % CPU idle).

## Changelog (process_version)

- **v1** (2026-11-04): stepped trials, machine-wide abort.
- **v2** (2026-11-04): abort counts gated samples only; baseline = current normal phase.

## Retrospective

(Fill when T2 or T3 fires.)

## Composes with

`KB § PATTERNS/devops/hardware-admission-budget.md` · `KB § PATTERNS/devops/usage-evaluation.md` ·
`KB § PATTERNS/common/methodology-execution-discipline.md` (verdict-channel integrity).
