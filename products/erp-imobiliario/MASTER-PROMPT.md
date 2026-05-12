# ERP Imobiliario -- Master Prompt

## Purpose

Full-featured real estate CRM for Brazilian property management companies. Handles property listings, client CRM, sales funnel, AI-powered matching, financial operations (commissions, contracts, insurance), WhatsApp messaging, digital signatures, PDF generation, Meta Ads integration, and compliance reporting (DIMOB). Largest product in the platform.

## Architecture

- Schema: `erp`
- Backend port: 8001 | Frontend port: 8080
- Tenant key: `org_id`
- Auth: SSO (from Core) + direct login
- Backend path: `products/erp-imobiliario/backend/app/`
- Frontend path: `products/erp-imobiliario/frontend/src/`

## Key Domains

### Core Domain
- **ativos** (imoveis) -- property listings with full metadata, photos, status lifecycle
- **clientes** -- client CRM with contact history, documents, preferences
- **funil** -- sales funnel stages, lead tracking, conversion metrics
- **metas** -- sales goals and targets per agent/team
- **condominios** -- condo management (common areas, fees)

### AI and Matching
- **ai** -- property descriptions, lead scoring, price suggestions, **lead follow-up draft (E4 from ai-expansion Phase 15)**, **P1 indicators E2/E6/E7/E8/E10 from ai-expansion Phase 6**. Delegates to `noctusai_lib.llm.chat_completion`. Model pinned `gpt-4o-mini`. No direct SDK use — never `from openai import ...` in product code. E4 endpoint: `POST /api/ai/leads/{lead_id}/follow-up-draft`; hook: `useFollowUpDraft()` in `frontend/src/hooks/useAI.ts`. **P1 indicators (Phase 6)**: services persist `AIOutput` rows to `erp.ai_outputs` via `noctusai_lib.ai.persist_output`; reads happen through the seed `/api/ai/outputs` standard router (opted in via `standard_routers=[..., "ai_outputs"]`). Endpoints: `POST /api/ai/whatsapp-intent` (E2 cliente classification), `POST /api/ai/clientes/{cliente_id}/certidoes-score` (E6 cliente score), `POST /api/ai/metas/coach-tip` (E7 user_metas narrative), `POST /api/ai/imoveis/{imovel_id}/photo-compliance` (E8 ativo flag), `POST /api/ai/search-relevance` (E10 ativo score). Hooks: `useWhatsAppIntent`, `useCertidoesScore`, `useMetasCoachTip`, `usePhotoCompliance`, `useSearchRelevance`. Prompt versions: `erp-whatsapp-intent@v1` / `erp-certidoes-score@v1` / `erp-metas-coach@v1` / `erp-photo-compliance@v1` / `erp-search-relevance@v1`. Read-side wires: `<AIIndicator refType="cliente" refId/>` on `ClienteDetalhes.tsx`; `<AIIndicator refType="ativo" refId/>` on `ImovelDetalhes.tsx`. Migration: `021_ai_outputs.sql`.
- **matching** -- property-to-client and property-to-permuta matching algorithm
- **embedding_service** -- vector embeddings for semantic property search. Delegates to `noctusai_lib.llm.generate_embedding`; the old local `generate_embedding` was absorbed into the shared lib during the multi-provider migration.

### Real Estate Operations
- **locacoes** -- rental contracts and management
- **vistorias** -- property inspections with photo documentation
- **contratos** -- contract lifecycle (draft, active, terminated)
- **propostas** -- offer/proposal management
- **chaves** -- key handoff tracking
- **assinaturas** -- digital signatures via ClickSign/D4Sign (`signature_provider` abstraction)

### Financial
- **financeiro** -- general financial operations, payment tracking
- **comissoes** -- agent commission calculation and splits
- **banco** -- bank account reconciliation
- **impostos** -- tax calculations
- **manutencao** -- property maintenance costs
- **seguros** -- insurance policy tracking
- **recorrencia** -- recurring financial transactions

### Marketing and Portals
- **marketing** -- campaign management
- **portais** -- property portal syndication (ZAP, OLX, VivaReal)
- **portal_cliente** -- client-facing portal
- **portal_externo** -- external partner portal
- **site_imoveis** -- property website/XML feeds
- **emails** -- email campaigns and templates
- **whatsapp** / **whatsapp_webhook** -- WhatsApp messaging via WAHA, HMAC-SHA256 webhook verification
- **meta_api** -- Meta/Facebook Ads integration

### Analytics and Compliance
- **relatorios** -- reports (sales, financial, occupancy)
- **bi** -- business intelligence dashboards
- **dimob** -- DIMOB compliance reporting (Brazilian tax authority)
- **analise_credito** -- credit analysis for tenants/buyers
- **gamificacao** -- sales gamification/leaderboards
- **certidoes** -- certificate/document verification

### Organization
- **filiais** -- branch office management
- **distribuicao** -- lead distribution rules
- **campo** -- field operations
- **agenda** -- scheduling and appointments
- **documentos** -- document management
- **storage** -- file storage operations
- **pdf** -- PDF generation for contracts, reports

### Logging
- **action_log** -- user action audit trail
- **atividades** -- activity feed

## Services (41)

Each router has a corresponding service. Key specialized services:
- `signature_provider` -- abstracts ClickSign vs D4Sign digital signature providers
- `xml_feeds` -- generates XML feeds for property portals
- `embedding_service` -- manages vector embeddings for AI features; calls `noctusai_lib.llm.generate_embedding`

Credential resolution (per-org → platform → env) now lives in `noctusai_lib.credentials.resolve_credential`. The old `app/services/credential_resolver.py` was deleted during the LLM consolidation; import from the shared lib instead.

## ERP-Specific Patterns

- **Org ID extraction**: Always use `get_org_id(user)` from `dependencies.py`. Never inline `user.user_metadata.get("org_id")`. Raises 400 if missing.
- **Webhook HMAC**: `whatsapp_webhook.py` verifies HMAC-SHA256 via `x-hub-signature` header when org's `webhook_secret` is configured.
- **Production safety**: `jwt_secret` defaults empty and raises `RuntimeError` at startup if empty in production.
- **Portal scoping**: Portal endpoints scope all queries by `org_id` from JWT.
- **Legacy data**: 264 migrated properties from old Django platform, marked with `titulo_anuncio LIKE '[MOCK]%'`.
- **Canonical rate-limit policies (2026-05-11).** ERP routers now consume named policies from `noctusai_lib.api.rate_limit_policies` instead of inline literal strings — `whatsapp.py` uses `DEFAULT_AUTH_RL`, `portal_cliente.py` + `portal_externo.py` use `DEFAULT_PORTAL_RL`, `ai.py` uses `DEFAULT_AI_RL`. Never re-inline `@limiter.limit("5/minute")` — bump the named constant in `noctusai_lib` if a tier needs adjustment.

## Frontend Pages

Dashboard, Imoveis, ImovelDetalhes, Clientes, ClienteDetalhes, Funil, Contratos, ContratoDetalhes, Agenda, Financeiro, Comissoes, Banco, BI, Relatorios, Configuracoes, Equipe, Filiais, Emails, Documentos, Assinaturas, Locacoes, Vistorias, Campo, Distribuicao, Gamificacao, Dimob, AnaliseCredito, Certidoes, Chaves, Condominios, Marketing, Admin, and more.

## Development Guidelines

- Follow shared patterns from noctusai_lib (auth, roles, invitations, responses, exceptions)
- Router → Service → Schema pattern; routers thin, business logic in services
- RLS policies use `(SELECT auth.uid())` pattern on all tables
- Portuguese for business domain names, English for technical/framework code
- Use `get_org_id(user)` for org extraction — ¬ access metadata directly
- N+1 zero tolerance: batch all reads ∧ writes
- DELETE endpoints require pre-check for related data before deletion
- Search endpoints accept `busca` query parameter for full-text search

## Methodology evolution (2026-05-11)

### Codification pipeline
**s1 emerges → s2 memory → s3 KB+CLAUDE.md → s4 `check_*` keeper detector with colocated test.** Promote when: deterministic predicate ∧ N≥3 ∧ remediation defined. Rules legitimately at s3 (judgment / context-dependent / aesthetic / pilot) catalogued. New ERP-specific rule emerges ⇒ route it; ¬ stall at memory. → `KB § PATTERNS/methodology-codification-pipeline.md`.

### Doc-code coherence rule (CLAUDE.md §1)
Tool Δ ⇒ doc Δ SAME commit. New flag ∨ new mode ∨ renamed detector ∨ different severity ⇒ every doc references it updates in same commit: KB pattern docs, Situation→Tool maps, CLAUDE.md pointers, INDEX.md, inline `--help`, README ∧ MASTER-PROMPT refs. Discovery: `grep -rn "<tool-name>" KNOWLEDGE-BASE/ CLAUDE.md CLAUDE/ projects/ products/*/README.md`. **This MASTER-PROMPT counts** — any ERP-targeted tool rename triggers an update here.

### 10 new keeper detectors today (live discovery)
Run `noctus.dev.outline_python mcp/noctusai/tools/noctus/dev/compliance.py` for the canonical list. Notable additions relevant to ERP touch-zones:

- `check_test_status_assertion` — body-assertion without status-code assertion (the YouTube-Crawler false-green slip).
- `check_function_search_path_pinned` — `CREATE FUNCTION` blocks must pin `SET search_path` (matters for ERP's many SQL migrations).
- `check_admin_endpoint_service_role_bypass` — admin-client `.table("T")` callsites where T lacks a `service_role_bypass` RLS policy.
- `check_slowapi_with_pep563` — `from __future__ import annotations` + `@limiter.limit` is broken; ERP rate-limit-policy adoption was exercised against this.
- `check_archive_staleness` — date-stamped archive folders older than retention.
- `check_dispatcher_staleness` — stale `## Pending` entries in `dispatcher-inbox.md`.
- `check_branch_orphan` — local branches >30 days old AND fully merged.
- `check_gitignore_drift` — expected transient-coordination paths missing from `.gitignore`.
- `check_no_silent_ok_comment` — the retired `# silent-ok` escape hatch.
- `check_auth_dep_anti_pattern` — `Depends(ProductDependencies.get_org_id)` / `get_user_role` / `get_user_client` shapes (the 422 query-param trap — directly relevant to ERP's 41 routers).
- `check_mcp_path_via_settings` — MCP tool modules must import `REPO_ROOT` from `settings`, never compute via `Path(__file__).parents[N]`.
- `check_mcp_write_tool_worktree_arg` — MCP tools with write-verb names must accept `worktree_path`.
- `check_pipefail_grep_q` — SIGPIPE-141 footgun under `set -o pipefail`.
- `check_doc_tool_reference_drift` — KB doc references to `bash scripts/<name>.sh <mode>` whose mode doesn't exist.
- `check_detector_has_regression_test` — every `check_*` ships colocated `Test<CamelCase>`.
- `check_section_7_placeholder_consistency` — PROJECT.md §7 says "all answered" but §2 still has placeholders.

### Bootstrap auto-hydrate (closes the defusedxml gap)
`bootstrap-worktree.sh` now installs `products/erp-imobiliario/backend/requirements.txt` automatically on worktree creation. This closes the **940 ERP collection errors** that previously blocked test discovery when `defusedxml` (and other ERP-specific deps) weren't hydrated. Do not bypass — never paste deps into an ad-hoc `pip install` line.

## Testing

```bash
cd products/erp-imobiliario/backend && pytest
```

1,661 tests. DELETE tests must provide mock data with matching ID for pre-check and separate `test_delete_not_found` with empty data returning 404. Search tests: mock `.or_()` is no-op, tests verify endpoint accepts `busca` and returns 200.

**Status-code assertion rule (codified 2026-05).** Every test asserting on response BODY (`.text` / `.json()` / `.content`) MUST also assert on `.status_code` in the same method. Enforced by keeper detector `check_test_status_assertion`.

**Seed mock predicate fix (2026-05-11, Engineer Q).** `MockRequestBuilder` in the seed now deep-copies caller inputs at storage time so write-propagation (UPDATE/DELETE) no longer mutates module-level fixture dicts. ERP test suite was the largest impact: **29 ERP tests fixed by Engineer E in commit `80786e9`**; `test_list_active_members` was incidentally fixed by the seed-side change. Diagnostic recipe for pollution vs genuine bug: 2-second `pytest <single-test>` classifier.

**ERP-specific outstanding (NOT in current scope).** 20 pre-existing failures in WAHA webhook / router fixtures filed as a separate follow-up project; do not chase here.

## Dependencies

- Shared backend: `noctusai_lib` (including `noctusai_lib.llm` for all AI access + `noctusai_lib.credentials` for 3-tier key resolution)
- Shared frontend: `@noctusai/lib` + `@noctusai/lib/design-system`
- LLM access: via `noctusai_lib.llm` only (OpenAI real; Anthropic + Gemini stubs). Per-org key resolution is automatic — services don't handle credentials.
- WAHA: WhatsApp Business API messaging
- ClickSign / D4Sign: digital signature providers
- Meta API: Facebook/Instagram Ads integration
- yfinance: (indirect, via shared patterns)
- Supabase: Auth, database, storage, RLS
