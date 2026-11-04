---
covers:
  - mcp/noctusai/tools/noctus/dev/usage_eval.py
  - products/core/backend/migrations/097_dev_telemetry.sql
---
# Usage evaluation — measure what our work costs the machine and Claude

**What it is.** A recurring, window-based evaluation of how development work uses resources, per job:
Claude tokens (input · output · thinking · cache read · cache write), API-equivalent cost, chars
(typed prompt · output · tool results), tool calls, active sessions and agents — joined with the
machine side: heavy jobs (ran · waited · duration · peak RSS · failed · not admitted) and OS samples
(CPU idle · reclaimable memory · swap-out · load · Claude processes · overloaded %).
Tool `noctus.dev.usage_eval`; tables `public.dev_telemetry_{claude,os,jobs,marks}` (core migration 097).

Owner, 2026-11-04: *"measure work now until then and from then on … seed this as a frequent
workflow/pattern/evaluation so we keep track as how our usage is going, say it per cost, machine usage,
tokens, chars and everything that's essential for a job"* · *"keep track of os data so we can keep track
and measure and decide on usage"*.

## 1 · Why

Capacity and spend decisions (how many sessions, how many heavy jobs at once, which phase of
`deploy/fleet/hardware-budget.json`) were made by feel. On 2026-11-04 the 8 GB laptop ran ~10 Claude
sessions, swap was nearly full and overlapping suites false-redded gates. The hardware-admission gate
fixes the overlap; this evaluation gives the numbers to tune it and to see what our work costs.

## 2 · Sources (machine-local, read-only)

| Source | Gives | Notes |
|---|---|---|
| `~/.claude/projects/<project>/<session>.jsonl` + `<session>/subagents/agent-<id>.jsonl` | per-request usage, model, content blocks | one request = several entries with the SAME `message.id` → usage counted **once per message id**; chars and tool calls summed over its blocks; `isMeta` entries and `<synthetic>` model skipped |
| `~/.noctus/hw-admission.ndjson` (owned by `noctus.dev.hw_admission`) | `sample` (OS, ~1/min), `ran` / `not_admitted` (heavy jobs) | name heavy jobs `<kind>:<target>` so jobs join cleanly |

**Swap-out has two probe versions.** `probe_version` 2 (from 2026-11-04T06:06:34Z, hw_admission `fb1edc561`)
divides the vm_stat delta by the measured interval (`metrics.elapsed_s`) and adds `swapout_mb_per_s`.
Rows without it are v1: they divided by the nominal `sample_s`, so under load the rate is inflated, an
UPPER BOUND only. The unit of `swapout_per_s` is PAGES/s (16 KB on Apple silicon). The report takes
`swapout_*_max` from v2 samples only and gives v1 apart as `swapout_per_s_max_v1_upper_bound`; sync
keeps the version in `dev_telemetry_os.extra.probe_version` (absent ⇒ 1).

**Cost** is the API-list-price equivalent from the seed rate card (`price_usage`), because Claude Code
runs on a subscription: comparable across windows, not an invoice. Cache-write cost is a lower bound
until the seed prices 1-hour cache writes separately (`NOC-REMEDIATE[anthropic-cache-ttl-pricing]`).
**Never** written to `public.ai_usage`: that is the product ledger that credits are charged from.
Counts only: no prompt or response text leaves the machine.

## 3 · How to use

- **One window:** `noctus.dev.usage_eval action=report since=<ISO> until=<ISO>` (default: the last 2 h).
- **Before/after (an experiment, a phase change, a new workflow):** `action=compare` with window A
  `since/until` and window B `b_since/b_until`. Unmeasured is `null`, never `0`.
- **Mark the change:** `action=mark kind=phase_change label=<what> since=<ISO>`, so the dashboard and
  every later compare split at that moment.
- **Keep the DB current:** `action=sync` upserts the last 30 min (idempotent; a still-filling 5-min
  bucket is completed by the next sync). Run it on a loop while working
  (`python mcp/noctusai/tools/noctus/dev/usage_eval.py sync` every 5 min, repo-root `.env` sourced).
- **Read it:** the usage dashboard reads the tables directly (prototype on real data →
  `KB § PATTERNS/frontend/prototype-on-real-data.md`).

## 4 · The evaluation cadence

Run a compare whenever the way we work changes: the hardware budget phase, the number of parallel
sessions or agents, a new skill or workflow, a model change. Record the verdict (keep / revert / tune)
with the numbers next to the decision, in the budget file's `_approved` note or the project's notes.
First instance: 2026-11-04 slot trial: window A 03:45Z–05:45Z (`build`, max_heavy 1) against the
stepped loosening from 05:45Z (max_heavy 2 + min CPU idle 25, the owner's "12→24", then 3 and 4).

## 5 · Composes with

`KB § PATTERNS/devops/hardware-admission-budget.md` (the machine side and its budget) ·
`KB § PATTERNS/backend/llm-usage.md` (the product LLM ledger: a different domain, never mixed) ·
`KB § PATTERNS/frontend/prototype-on-real-data.md` (how the dashboard is built).
