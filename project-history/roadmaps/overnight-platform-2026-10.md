# Overnight platform run — 2026-10 roadmap

> Owner grant 2026-10-29 (night): "go all the way with all i've said to prod … u cant keep stopping for approvals" · "ship it to prod". No real customer data yet — only daily operational use. Tech-lead = the orchestrating session; engineers per slice via `task_branch`.
> Sources of the decisions: memories `project-org-brand-identity-in-core`, `project-product-vision-agentic-business-app`, `project-usage-billing-credits-model`; roadmap `product-agents-platform-2026-10.md` (D-numbers); architect review 2026-10-29 (agentic LLM handoff); KB `PATTERNS/devops/owner-operations.md`.

## Status legend
`done` shipped to prod · `dev` integrated on dev · `wip` engineer working · `next` queued · `later` named destination, not tonight

## Wave 1 — org brand identity (done → shipping)
- core `public.org_brand_identities` (089) + `/api/brand` + ingestion (Sonnet 5.5) · core Identidade visual page · seed `BrandProvider` · org picker without reload · status-token recolor (SW+core). `dev` @ 90aabe170 → prod tonight (migration 089 + fleet redeploy).

## Wave 2 — in flight
| Slice | What | Status |
|---|---|---|
| seed-ai-usage-ledger | D25 central `public.ai_usage` (org·product·feature·purpose·user, price_version, partial-stream emission) + attribution context + admin usage reads central + D26 keeper | wip |
| core-operations-section | platform timezone setting · `public.scheduler_runs` ledger + job-failure bell · 07:00 zero-LLM owner brief (+dead-man) · core admin **Operação** page | wip |
| agents-unified-model | W0 `products/agents/projects/agents-unified/CONTRACT.md` · `/api/studio/modelo` · painel DTO · key-pin removal · one card → one dynamic agent page | wip |
| seed-journey-wizard | seed `JourneyWizard` organ (steps · subtabs · progress · animated · skip-optional) | wip |
| sw-leftovers-fix | status_pagina gaps · campanhas update · built pages promoted · retention sweeps scheduled · crednet dangling file · snapshots at 06:00/18:00 · docs drift | wip |
| overnight-roadmap | this file · agent `ops-steward` · skill `noc-daily-ops` · KB `owner-operations.md` | wip |

## Wave 3 — next (after wave 2 lands)
1. **Credits wallet** (core billing): per-org prepaid wallet, entries `source = purchase | grant | adjustment`, debit from `ai_usage` per product at a credit price; admin **grant credits** UI (owner grants e.g. US$100 to a consultoria — noc pays via its own key, debited exactly as if paid); prepaid/grant orgs fail CLOSED at zero; usage screen shows credits + R$ + tokens per org → product → feature; BYOK tier flag (org key, no usage debit). Price formula and margins: memory `project-usage-billing-credits-model`.
2. **Agent creation wizard** (agents FE on `JourneyWizard`, 10 steps from the W0 contract) → **Renata** created through the wizard in the logged-in UI (replaces academia Bia; history moved) → **new Bia** (marketing/social: Core Studio, posting schedules, analytics, YouTube, comments analyze/summarize/report only) like Julia.
3. **Templates admin** (core): DB-backed, editable, per product × kind — design-system template, agent templates/prompts, messages/documents, repo/workflow templates.
4. **D27 caps** + per-request guard + server-side context trimming (help-chat).
5. **Purpose routing** (`purpose=` → model, platform default + per-org override; explicit, never failover).
6. **SSE `stream_reply` extraction** (help-chat + SW media chat) before agents builds a 3rd.

## Later — named destinations
- SW brand scoping (brands = the org's content clients; content/social/integrations brand-scoped, leads/CRM org-level with tags; per-brand RLS access; unified switcher; default-brand backfill; per-brand + consolidated views).
- Signup brand step backend hook (form UX designed with the owner) · zip intake · `resolve_org_brand_voice` (voice/brand_book treated as untrusted) · Nós no Limiar import into core · retire SW 210 `is_primary`.
- Guardrails lift to seed (agents `safety_pack` engine as pilot #1) · knowledge/RAG lift (agents retriever, help-chat first; semantic cache deferred).
- Seed eval harness in CI · tool-permission tiers · per-agent kill switch.
- **AI agents acting on the mechanical time-based reports** — owner 2026-10-29: "we'll work on that later … remind me" → remind at the morning report.
- Telegram channel (D33) · due-dated pushable reminder store · n8n workflows into the repo.
- Leftovers scans of core, monica, commerce, agents, igig, orbity, academia-de-reciclagem, seed · then the fix-in-flight gate for the six uncaught shapes (comment-with-no-reader, nav route without status_pagina row, no-op status insert, page stuck in desenvolvimento, docs vs code, owner decision with no code).
- Follow-ups: chart literals → `--chart-*`; darker status-text tokens; `end()` via `swapOrgScope`; design-system OrgPicker tests asserting reload; verify coreApi sends the acting-org header; SSE pin header live check.
