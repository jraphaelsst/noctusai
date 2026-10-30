# Overnight platform run — 2026-10 roadmap

> Owner grant 2026-10-29 (night): "go all the way with all i've said to prod … u cant keep stopping for approvals" · "ship it to prod". No real customer data yet — only daily operational use. Tech-lead = the orchestrating session; engineers per slice via `task_branch`.
> Sources of the decisions: memories `project-org-brand-identity-in-core`, `project-product-vision-agentic-business-app`, `project-usage-billing-credits-model`; roadmap `product-agents-platform-2026-10.md` (D-numbers); architect review 2026-10-29 (agentic LLM handoff); KB `PATTERNS/devops/owner-operations.md`.

## Status legend
`done` shipped to prod · `dev` integrated on dev · `wip` engineer working · `next` queued · `later` named destination, not tonight

## Wave 1 — org brand identity (done)
- core `public.org_brand_identities` (089) + `/api/brand` + ingestion (Sonnet 5.5) · core Identidade visual page · seed `BrandProvider` · org picker without reload · status-token recolor (SW+core). `done` @ 90aabe170 (2026-10-30); 094 NULL-safe tokens CHECK found by the prod probe, shipped 2026-10-30.

## Wave 2 — `done` (prod 1fb913ea1, 2026-10-30)
| Slice | What | Status |
|---|---|---|
| seed-ai-usage-ledger | D25 central `public.ai_usage` (org·product·feature·purpose·user, price_version, partial-stream emission) + attribution context + admin usage reads central + D26 keeper | wip |
| core-operations-section | platform timezone setting · `public.scheduler_runs` ledger + job-failure bell · 07:00 zero-LLM owner brief (+dead-man) · core admin **Operação** page | wip |
| agents-unified-model | W0 `products/agents/projects/agents-unified/CONTRACT.md` · `/api/studio/modelo` · painel DTO · key-pin removal · one card → one dynamic agent page | wip |
| seed-journey-wizard | seed `JourneyWizard` organ (steps · subtabs · progress · animated · skip-optional) | wip |
| sw-leftovers-fix | status_pagina gaps · campanhas update · built pages promoted · retention sweeps scheduled · crednet dangling file · snapshots at 06:00/18:00 · docs drift | wip |
| overnight-roadmap | this file · agent `ops-steward` · skill `noc-daily-ops` · KB `owner-operations.md` | wip |

## Wave 3 — items 1–3 `done` (prod 1fb913ea1, 2026-10-30) except Renata; 4–6 `next`
1. **Credits wallet** (core billing): per-org prepaid wallet, entries `source = purchase | grant | adjustment`, debit from `ai_usage` per product at a credit price; admin **grant credits** UI (owner grants e.g. US$100 to a consultoria — noc pays via its own key, debited exactly as if paid); prepaid/grant orgs fail CLOSED at zero; usage screen shows credits + R$ + tokens per org → product → feature; BYOK tier flag (org key, no usage debit). Price formula and margins: memory `project-usage-billing-credits-model`.
2. **Agent creation wizard** (agents FE on `JourneyWizard`, 10 steps from the W0 contract) → **Renata** created through the wizard in the logged-in UI (replaces academia Bia; history moved) → **new Bia** (marketing/social: Core Studio, posting schedules, analytics, YouTube, comments analyze/summarize/report only) like Julia.
3. **Templates admin** (core): DB-backed, editable, per product × kind — design-system template, agent templates/prompts, messages/documents, repo/workflow templates.
4. **D27 caps** + per-request guard + server-side context trimming (help-chat).
5. **Purpose routing** (`purpose=` → model, platform default + per-org override; explicit, never failover).
6. **SSE `stream_reply` extraction** (help-chat + SW media chat) before agents builds a 3rd.

## Agent creation wizard — refinement (owner 2026-10-30: "this needs a refining … we'll do that later")
Live test in prod on 2026-10-30, creating Renata at `/agentes/novo`:
- **Blank mode collects nothing past Identidade.** "Começar vazio" hides every briefing field; Personalidade, Regras say "Nada a responder", Conhecimento, Ferramentas, Rotinas are notes. The persona questions (objetivo, público, tom, idioma, exemplos, canal, limites) only appear in "Gerar com IA" (≤US$5). Target: both modes ask the same questions; blank mode writes the answers straight into the draft's sections/texts (no AI), generate mode feeds them to the AI.
- **Ferramentas + Rotinas take no input in either mode.** Pick tools (incl. the academia group, claude_sdk only) in the wizard; Rotinas at least a preview of per-org controls.
- **Papel in blank mode shows only qualification fields** (BANT/scope) — meaningless for a non-SDR agent.
- **Button label**: last step says "Publicar" but creates a draft (`Criar rascunho`).
- **Revisão → Continuar once jumped back to step 6** (not reproduced deterministically) — check `primeiroPassoInvalido` / step indexing.
- **Agent page after create**: toast `[404] Agente não encontrado` from `GET /api/studio/agents/{key}/controle` when the platform org has no instance — an expected state rendered as an error. Completeness lists raw keys (`compilador.conhecimento_intro` …) — show human labels + where to fill each.
- **Renata state**: draft `renata` v1 exists in prod (inactive, no instance). History NOT transferred, legacy Bia NOT archived — academia keeps the working legacy Bia. Finish RENATA-CUTOVER.md §1–§5 with the refined wizard (or delete the draft and recreate).

## Later — named destinations
- SW brand scoping (brands = the org's content clients; content/social/integrations brand-scoped, leads/CRM org-level with tags; per-brand RLS access; unified switcher; default-brand backfill; per-brand + consolidated views).
- Signup brand step backend hook (form UX designed with the owner) · zip intake · `resolve_org_brand_voice` (voice/brand_book treated as untrusted) · Nós no Limiar import into core · retire SW 210 `is_primary`.
- Guardrails lift to seed (agents `safety_pack` engine as pilot #1) · knowledge/RAG lift (agents retriever, help-chat first; semantic cache deferred).
- Seed eval harness in CI · tool-permission tiers · per-agent kill switch.
- **AI agents acting on the mechanical time-based reports** — owner 2026-10-29: "we'll work on that later … remind me" → remind at the morning report.
- Telegram channel (D33) · due-dated pushable reminder store · n8n workflows into the repo.
- Leftovers scans of core, monica, commerce, agents, igig, orbity, academia-de-reciclagem, seed · then the fix-in-flight gate for the six uncaught shapes (comment-with-no-reader, nav route without status_pagina row, no-op status insert, page stuck in desenvolvimento, docs vs code, owner decision with no code).
- Follow-ups: chart literals → `--chart-*`; darker status-text tokens; `end()` via `swapOrgScope`; design-system OrgPicker tests asserting reload; verify coreApi sends the acting-org header; SSE pin header live check.
