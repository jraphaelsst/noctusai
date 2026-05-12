# Mailing — MASTER-PROMPT

> Authoritative development guide for the NoctusAI Mailing product.

## Purpose

Email marketing and automation platform. Helps organizations engage leads and clients through mass email campaigns, automated follow-up sequences, and tracked communications.

## Architecture

**Born from the seed framework.** Backend uses `create_product_app()` from `noctusai_seed`. Frontend will use `createProductApp()` from `@noctusai/seed`. All structural infrastructure (auth, team, notifications, health, layout, routing) is inherited — this product only contains domain code.

### Backend

```
products/mailing/backend/app/
  main.py              → create_product_app() with domain routers
  config.py            → MailingSettings(ProductSettings) + Resend/scheduler config
  database.py          → create_database_module(settings, "mailing")
  dependencies.py      → create_dependencies(db)
  rate_limit.py        → create_product_limiter(settings)
  scheduler.py         → APScheduler (send loop, automation processing, scheduled campaigns)
  routers/
    contacts.py        → CRUD, import CSV, sync, search/filter
    lists.py           → Static lists + dynamic segments
    templates.py       → CRUD, preview, send test
    campaigns.py       → Create, schedule, send, pause, cancel, stats
    automations.py     → CRUD, steps, reorder, activate/pause, enroll
    analytics.py       → Dashboard metrics, campaign stats, automation funnel
    webhooks.py        → Resend event receiver (no auth)
    unsubscribe.py     → Public unsubscribe (no auth, HMAC token)
    settings.py        → Domain verification, sender config
  services/
    contact_service.py
    list_service.py
    template_service.py
    campaign_service.py
    send_service.py        → Core engine: Resend Batch API, template rendering
    automation_service.py
    analytics_service.py
    webhook_service.py
    import_service.py
    sync_service.py
    unsubscribe_service.py
  schemas/
    contacts.py, lists.py, templates.py, campaigns.py, automations.py, analytics.py
```

### Frontend

```
products/mailing/frontend/src/
  App.tsx              → createProductApp() from seed framework
  pages/               → Dashboard, Contacts, Templates, Campaigns, Automations, Analytics, Settings
  components/          → Domain components (ContactTable, CampaignStats, StepBuilder, etc.)
  hooks/               → TanStack Query hooks (useContacts, useCampaigns, useAutomations, etc.)
```

### Database Schema: `mailing`

14 tables: contacts, contact_lists, contact_list_members, templates, campaigns, automations, automation_steps, automation_enrollments, send_logs, link_clicks, unsubscribes, sender_domains, status_pagina, invitations.

## Key Domain Logic

### Send Engine
1. `POST /campaigns/{id}/send` → resolve list → create send_logs (queued) → return immediately
2. APScheduler (30s interval) → pick 100 queued → render templates → Resend Batch API → update status
3. Resend webhooks → update send_logs (delivered, opened, clicked, bounced)

### Automations
- Trigger types: contact_added, tag_added, list_joined, manual, webhook
- Step types: send_email, wait, condition, add_tag, remove_tag, webhook
- Processing: APScheduler (5min interval) → check enrollments with next_action_at <= now()

### Compliance
- Every email includes unsubscribe link (HMAC token)
- List-Unsubscribe header (RFC 8058)
- Bounced/complained contacts auto-excluded from future sends

## Dependencies

- **Resend** — email sending (Batch API + webhooks)
- **APScheduler** — campaign send loop + automation processing
- **Seed framework** — all structural infrastructure
- **`noctusai_lib.llm`** — AI wrappers (see below)

## AI Features (ai-expansion Phases 14 + 8)

Six AI features split across two services. See `KNOWLEDGE-BASE/CONTEXT/backend/05-AI-FEATURES.md § Mailing AI Wrappers` for the authoritative tables.

**Phase 14 (2026-04-24)** — five `chat_completion` wrappers in `app/services/ai_service.py`:

| Code | Service fn | Purpose |
|---|---|---|
| M1 | `generate_subjects` | 3–5 subject-line variants with tone |
| M2 | `draft_template` | Responsive HTML body from prompt |
| M5 | `reengagement_variants` | 3 re-engagement email tones |
| M6 | `review_deliverability` | Spam / deliverability findings list |
| M7 | `translate_template` | PT → EN/ES/FR preserving HTML + `{{placeholders}}` |

**Phase 8 (2026-04-25)** — persisted P1 indicator in `app/services/segmentation_service.py`:

| Code | Service fn | Purpose |
|---|---|---|
| M3 | `segment_contacts` | embed → greedy cosine cluster → LLM-name → persist N `<AIIndicator/>` rows to `mailing.ai_outputs` |

**Phase 12 (2026-04-25)** — fourth platform-wide P3 digest adopter in `app/services/campaign_debrief_service.py`:

| Code | Service fn | Purpose |
|---|---|---|
| M4 | `build_debrief` / `send_campaign_debrief` | aggregate `send_logs` + `link_clicks` → LLM 3-paragraph PT debrief → render html/text → fan-out via `noctusai_lib.email.digest.send_digest`. **Auto-fired by `send_service._finalize_campaign_if_done` when the last queued `send_log` drains** (atomic `.neq('status','enviada')` flip is the idempotency boundary). Endpoints: `GET /api/ai/campaigns/{id}/debrief` (preview, no send) + `POST /api/ai/campaigns/{id}/debrief/send {recipient}` (manual re-run path). |

Frontend hooks in `src/hooks/useAI.ts`: `useGenerateSubjects`, `useDraftTemplate`, `useReengagementVariants`, `useDeliverabilityReview`, `useTranslateTemplate`, **`useSegmentContacts`**. M3 is wired with `<AIIndicator refType="contact" refId={c.id} hideIcon/>` in the email cell + a "Segmentar" trigger button in the `Contacts.tsx` header. Standard router opt-in: `standard_routers=["health", "notificacoes", "team", "ai_outputs"]`. Migration: `002_ai_outputs.sql`.

Per-page UI integration for M1/M2/M5/M6/M7 (buttons in campaign / template editors) is follow-up polish — hooks are consumable today; pages can mount buttons when convenient.

## Methodology evolution (2026-05-11 refresh)

This section snapshots platform-wide methodology pieces that landed today and how they apply to mailing. Open the cited KB depth on demand — do not pre-load.

### 1. Codification pipeline — Stage 4 is where rules become enforceable
Conversation rules graduate through 4 stages: **emerges → memory entry → KB pattern doc + CLAUDE.md pointer → `check_*` keeper detector with colocated regression test**. The keeper is the **codification layer** of the methodology (not a regulatory silo). Mailing-relevant criteria: deterministic predicate + recurrence ≥3 + clear remediation. When a slip surfaces inside mailing (services / routers / hooks), the right move is to route it through this pipeline rather than fix-and-forget. → `KB § PATTERNS/methodology-codification-pipeline.md`

### 2. Doc-code coherence — extension of three-way sync
When mailing tooling, scripts, or referenced MCP detectors change behavior (new flag, renamed mode, different severity), every doc that references them updates in the **same commit** — including this MASTER-PROMPT.md if it names the surface. "I'll update the doc later" is forbidden. Discovery: `grep -rn "<tool-name>" KNOWLEDGE-BASE/ CLAUDE.md CLAUDE/ projects/ products/mailing/MASTER-PROMPT.md`. Codification candidates: `check_doc_tool_reference_drift` (Stage 4 today, broader `check_mcp_tool_argument_drift` pending). → `KB § PATTERNS/methodology-codification-pipeline.md § 8`

### 3. Keeper detector population — what fires across mailing today
The keeper module at `mcp/noctusai/tools/noctus/dev/compliance.py` exports 32 `check_*` detectors (live count via `noctus.dev.outline_python compliance.py`). The 12 most recently codified — and the ones most likely to fire on routine mailing edits — are:

| Detector | What it catches in mailing context |
|---|---|
| `check_no_silent_ok_comment` | `# silent-ok` literal anywhere under `products/mailing/backend/app/` (escape hatch retired platform-wide) |
| `check_auth_dep_anti_pattern` | `Depends(ProductDependencies.get_org_id)` / `get_user_role` / `get_user_client` — must use `Depends(get_current_user_org)` factory |
| `check_section_7_placeholder_consistency` | mailing-scoped `PROJECT.md` files claiming "§7 all answered" while §2 still has placeholders |
| `check_test_status_assertion` | mailing test methods that assert on response body (`.text` / `.json()`) without `.status_code` in the same method |
| `check_slowapi_with_pep563` | mailing routers combining `@limiter.limit` with `from __future__ import annotations` (slowapi PEP-563 footgun) |
| `check_unknown_table_references` | `.table("name")` callsites under `app/` where `name` is not declared by mailing's `001_mailing.sql` |
| `check_function_search_path_pinned` | unpinned `search_path` on `CREATE FUNCTION` blocks in mailing migrations |
| `check_admin_endpoint_service_role_bypass` | `get_admin_client().table("T")` where T lacks an explicit `service_role_bypass` policy |
| `check_no_self_monkeypatch` | `monkeypatch.setattr(<mailing_module>, ...)` in mailing tests — use DI / `MockRequestBuilder.inserted_payloads` instead |
| `check_archive_staleness` / `check_dispatcher_staleness` / `check_branch_orphan` | repo-wide hygiene; fire if mailing project entries linger |
| `check_detector_has_regression_test` | meta-detector — every new keeper rule ships with `Test<CamelCase>` colocated |
| `check_doc_tool_reference_drift` | KB doc references to `bash scripts/<name>.sh <mode>` that don't resolve |

Run `noctus.dev.validate_product products/mailing` to fire the full battery against mailing. Triage results with formalize / refactor / accept-with-rationale.

### 4. Seed mock predicate fix — MockSupabaseClient now deep-copies inputs
`MockRequestBuilder.__init__` deep-copies `_data` at storage time so write-propagation (UPDATE / DELETE) on mailing tests no longer mutates module-level fixture dicts. Net effect for mailing test suites: fixture-pollution bugs disappear; if a mailing test was previously green by accident due to shared mutable state, the fix may surface a latent assertion. Diagnostic recipe when triaging: 2-second `pytest <single-test>` classifies pollution vs genuine bug.

### 5. Canonical rate-limit policies — `DEFAULT_AI_RL` is mailing's source of truth
`products/mailing/backend/app/routers/ai.py` now imports `DEFAULT_AI_RL` from `noctusai_lib.api.rate_limit_policies` and decorates 7 of 8 endpoints with `@limiter.limit(DEFAULT_AI_RL)`. The single intentional deviation (`@limiter.limit("10/minute")` at line 128) is a **carve-out**: surface it in the next robustness pass (formalize as `DEFAULT_AI_RL_TIGHT` policy, or document at `KB § PATTERNS/accept-with-rationale.md`). New mailing AI endpoints MUST default to `DEFAULT_AI_RL`; bespoke literals are a triage trigger.

### 6. Bootstrap auto-hydrate
Fresh worktrees hydrate via `scripts/bootstrap-worktree.sh` — pre-hydrate sweep removes stale `.claude/worktrees/agent-*/` (any whose branch is merged to `origin/main`). Mailing engineer briefs do not need a separate hydration step; the orchestrator's dispatch flow handles it.

### 7. Chatbot operational readiness — mailing is an N=2 inheritor candidate
Mailing is **explicitly named** as an N=2 inheritor candidate in `KB § PATTERNS/chatbot-operational-readiness.md` (alongside therapy / PF). First adopter is `imobi-scheduling`. The pattern is a 6-piece production-hardening checklist for chatbot products with external writes:

1. **Retries** on transient external writes via `retry_call` composing seed `RetryPolicy` (lift to seed at N=2 — mailing's outbound triggers it)
2. **Structured logs** auto-wired by `create_product_app`
3. **Health endpoint** via `standard_routers=["health"]` (mailing already opts in)
4. **`DEPLOYMENT.md`** shape — uniform across chatbot products
5. **Supabase managed backups** documented
6. **Metrics sink** seam wired at call sites; default `NoopCounter` (lift to platform-metrics project at N=2)

When mailing's send engine / webhook receiver / Resend Batch dispatcher acquires retry+metrics requirements, **do not rebuild from scratch** — inherit verbatim from imobi-scheduling's shape and trigger the seed-side lifts for retry (§2) + metrics (§6). The send engine's `app/services/send_service.py` Resend Batch API call is the most natural retry seam; `webhook_service.py` is the metrics-sink seam. → `KB § PATTERNS/chatbot-operational-readiness.md § 9 First adopter`

## Testing

```bash
cd products/mailing/backend && pytest
```

Implementation checklist: see `TODO-MAILING.md` at repo root.
