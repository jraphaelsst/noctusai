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
- **ai** -- property descriptions, lead scoring, price suggestions. Delegates to `noctusai_lib.llm.chat_completion`. Model pinned `gpt-4o-mini`. No direct SDK use — never `from openai import ...` in product code.
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

## Frontend Pages

Dashboard, Imoveis, ImovelDetalhes, Clientes, ClienteDetalhes, Funil, Contratos, ContratoDetalhes, Agenda, Financeiro, Comissoes, Banco, BI, Relatorios, Configuracoes, Equipe, Filiais, Emails, Documentos, Assinaturas, Locacoes, Vistorias, Campo, Distribuicao, Gamificacao, Dimob, AnaliseCredito, Certidoes, Chaves, Condominios, Marketing, Admin, and more.

## Development Guidelines

- Follow shared patterns from noctusai_lib (auth, roles, invitations, responses, exceptions)
- Router -> Service -> Schema pattern; routers are thin, business logic in services
- RLS policies use `(SELECT auth.uid())` pattern on all tables
- Portuguese for business domain names, English for technical/framework code
- Use `get_org_id(user)` for org extraction -- never access metadata directly
- N+1 zero tolerance: batch all reads and writes
- DELETE endpoints require pre-check for related data before deletion
- Search endpoints accept `busca` query parameter for full-text search

## Testing

```bash
cd products/erp-imobiliario/backend && pytest
```

1,661 tests. DELETE tests must provide mock data with matching ID for pre-check and separate `test_delete_not_found` with empty data returning 404. Search tests: mock `.or_()` is no-op, tests verify endpoint accepts `busca` and returns 200.

## Dependencies

- Shared backend: `noctusai_lib` (including `noctusai_lib.llm` for all AI access + `noctusai_lib.credentials` for 3-tier key resolution)
- Shared frontend: `@noctusai/lib` + `@noctusai/lib/design-system`
- LLM access: via `noctusai_lib.llm` only (OpenAI real; Anthropic + Gemini stubs). Per-org key resolution is automatic — services don't handle credentials.
- WAHA: WhatsApp Business API messaging
- ClickSign / D4Sign: digital signature providers
- Meta API: Facebook/Instagram Ads integration
- yfinance: (indirect, via shared patterns)
- Supabase: Auth, database, storage, RLS
