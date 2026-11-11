---
name: noc-daily-ops
description: Use for the owner's daily operating routine — triggers "bom dia", "good morning", "daily brief", "what needs my attention", "how is the platform", "status do dia", "anything broken?", "morning routine", "weekly ops review". Turns watchdog, jobs, cost, deploy drift, reminders and debt into a ≤3-item today list; performs only pre-approved L3 actions.
version: 1.1.0
---

# noc-daily-ops — the morning routine, mechanical first

Agent `ops-steward` owns this; the tech-lead session can run it inline (it is all read-only tool calls).

## Workflow (daily)

- **Gate alignment (daily, recurrent loop):** `python mcp/noctusai/cli.py --gate-alignment walls --file-walls` ranks gates firing in normal flow, files SARIF-shaped wall findings, and lists pending matrix legs; a wall is a missing construction leg, not an agent error. → `KB § PATTERNS/common/gate-methodology-sync.md` (Alignment loop)
1. **Reminders first** — open `MEMORY-reminders.md` items + any reminder the tech-lead owes in this session's memory (e.g. "AI agents on mechanical reports").
2. **Health** — `noctus.dev.prod_watchdog` (state), `noctus.dev.deploy_verify` (revision drift), `noctus.dev.smoke_fleet`. A check that cannot run ⇒ `inconclusive`, never green.
2a. **Supabase request budget** — `noctus.dev.supabase_request_budget` (window 24h): verdict ok|warn|critical|unknown, projected calls/day, top endpoint shapes, any 402. critical or a tripped fleet breaker (`noctus:breaker:fleet`; `prod_watchdog` trips it off-host) ⇒ Today, SEV2; re-arm only via `noctus.dev.supabase_breaker`. Unreadable ⇒ `inconclusive`. → `KB § PATTERNS/backend/polling-request-budget.md`
2b. **Exposure drift** — `noctus.dev.access_tier_exposure` (no args = the 3-4 read-only queries; run them through the supabase connector, pass the rows back): any browser grant / non-admin policy on a Platform-IP table, an anon policy on a secret/PII table, an inactive product's schema served ⇒ Exception (`KB § PATTERNS/security/access-tiers.md`). An unmeasured input ⇒ `inconclusive`, never green.
3. **Jobs** — core admin Operação data (`public.scheduler_runs`): failed or missing runs in the last 24h; the 07:00 brief's own run (dead-man: none in 26h ⇒ exception).
4. **Cost** — yesterday's LLM spend per org → product from `public.ai_usage`; flag any org/product > 2× its 7-day average or past 80% of its cap.
4b. **Backup age** — per store with a backup mechanism: age of the last successful backup vs its RPO (age > RPO ⇒ Exception; > 2× RPO ⇒ Today, SEV3 "lost safety net"). A store with NO backup (undefined RPO — Supabase DB, Supabase Storage, n8n as of 2026-11-05) stays in **Today** until the owner decides. Can't check ⇒ `inconclusive`. → `KB § PATTERNS/devops/ops-craft-canon.md` §6
4c. **Alert classification** — list alerts sent in the last 24 h whose outcome is unknown, each with a proposed `acted` / `noise` / `duplicate`; the owner confirms in ONE batched pick-one question. No outcome log exists yet (ops canon §3 design; tooling slice open) ⇒ report the step `inconclusive` rather than skipping it silently.
4d. **Fiscal parameters** — `noctus.dev.finance_params_staleness` (CLI `--finance-params-staleness`): roll up as ONE debt line "N parâmetros fiscais a reverificar"; `escalate: true` (a key with no successor ends within 15 days or already ended) goes to **Today** with skill `noc-tax-params` as the next step. Registry unreadable ⇒ `inconclusive`, never green. Optional `log=True` files the self-closing drift rows. Never blocks anything.
5. **Debt** — `noctus.dev.branch_pointer action=list` (leftover/stale), `noctus.dev.scan_remediation_markers` (age-ranked top 5), `noctus.dev.findings`.
6. **Compose** the return in the `ops-steward` short form: Today (≤3) · Exceptions · Done for you · Reminders · Debt top-5 · Inconclusive.
7. **Act** only on L3 actions (`KB § PATTERNS/devops/owner-operations.md` §2); everything else becomes an L1 suggestion with the exact command.

## Weekly (Monday)
Add: `noctus.dev.supabase_advisors`, `noctus.dev.latency_report`, `noctus.dev.detect_stale_caches`, skill `noc-hygiene`, `noctus.dev.tmp_cleanup` (dry-run, then `dry_run=False` — L3), and the alert-usefulness review (acted ÷ (acted+noise+duplicate) per class over 4 weeks; a class < 50% ⇒ prune · fold into the brief · retune — owner picks), toil counts, open problem records, memory trend.

## Monthly (first Monday) · Quarterly
- **Monthly:** SLO report per product (budget used, incidents, burn alerts) · DORA five · cost per product + month-over-month delta · toil budget · days since the last restore drill per store (> 90 ⇒ Today: schedule the drill, L1 to devops-engineer) · off-host copy exists per store · autonomy promotions/demotions due · open postmortem actions.
- **Quarterly:** restore drill for the rotation's store · one game day · access review (deploy keys, watchdog key, GHCR token, Supabase service role — still needed?) · review starter SLOs.
Same output shape every level. Table + owner decisions each level may produce → `KB § PATTERNS/devops/ops-craft-canon.md` §7.

## Guardrails
- Changes and exceptions only — never paste a full status wall.
- `noctus.dev.notify` stays plan-only (no `confirm=True`) unless the owner asks in chat.
- Promote/demote an action's autonomy level only by recording it in `owner-operations.md` §5.

## Depth
`KB § PATTERNS/devops/owner-operations.md` · `KB § PATTERNS/devops/ops-craft-canon.md` · `KB § PATTERNS/devops/prod-watchdog.md` · agent `ops-steward`.
