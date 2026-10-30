---
name: noc-daily-ops
description: Use for the owner's daily operating routine — triggers "bom dia", "good morning", "daily brief", "what needs my attention", "how is the platform", "status do dia", "anything broken?", "morning routine", "weekly ops review". Turns watchdog, jobs, cost, deploy drift, reminders and debt into a ≤3-item today list; performs only pre-approved L3 actions.
version: 1.0.0
---

# noc-daily-ops — the morning routine, mechanical first

Agent `ops-steward` owns this; the tech-lead session can run it inline (it is all read-only tool calls).

## Workflow (daily)

1. **Reminders first** — open `MEMORY-reminders.md` items + any reminder the tech-lead owes in this session's memory (e.g. "AI agents on mechanical reports").
2. **Health** — `noctus.dev.prod_watchdog` (state), `noctus.dev.deploy_verify` (revision drift), `noctus.dev.smoke_fleet`. A check that cannot run ⇒ `inconclusive`, never green.
3. **Jobs** — core admin Operação data (`public.scheduler_runs`): failed or missing runs in the last 24h; the 07:00 brief's own run (dead-man: none in 26h ⇒ exception).
4. **Cost** — yesterday's LLM spend per org → product from `public.ai_usage`; flag any org/product > 2× its 7-day average or past 80% of its cap.
5. **Debt** — `noctus.dev.branch_pointer action=list` (leftover/stale), `noctus.dev.scan_remediation_markers` (age-ranked top 5), `noctus.dev.findings`.
6. **Compose** the return in the `ops-steward` short form: Today (≤3) · Exceptions · Done for you · Reminders · Debt top-5 · Inconclusive.
7. **Act** only on L3 actions (`KB § PATTERNS/devops/owner-operations.md` §2); everything else becomes an L1 suggestion with the exact command.

## Weekly (Monday)
Add: `noctus.dev.supabase_advisors`, `noctus.dev.latency_report`, `noctus.dev.detect_stale_caches`, skill `noc-hygiene`, and the alert-usefulness review (prune alert classes acted on <50%).

## Guardrails
- Changes and exceptions only — never paste a full status wall.
- `noctus.dev.notify` stays plan-only (no `confirm=True`) unless the owner asks in chat.
- Promote/demote an action's autonomy level only by recording it in `owner-operations.md` §5.

## Depth
`KB § PATTERNS/devops/owner-operations.md` · `KB § PATTERNS/devops/prod-watchdog.md` · agent `ops-steward`.
