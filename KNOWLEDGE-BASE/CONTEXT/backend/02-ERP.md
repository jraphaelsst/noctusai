# 02 — ERP Backend Context

> Path: `products/erp-imobiliario/backend/app/`
> Server: FastAPI on port **8001**
> Tests: `products/erp-imobiliario/backend/tests/` (87 test files, 1432 tests)

---

## Overview

Full real estate CRM backend with 48 routers and 40 services. Handles property management, client CRM, sales funnel, AI-powered matching, financial operations, WhatsApp messaging, digital signatures, PDF generation, notifications, Meta Ads integration, and compliance reporting.

---

## Routers (48)

### Core Domain

| Router | Prefix | Purpose |
|--------|--------|---------|
| `ativos.py` | `/api/ativos` | Properties & exchange profiles (unified: imóveis + permutas) |
| `clientes.py` | `/api/clientes` | Client/lead management |
| `funil.py` | `/api/funil` | Sales funnel stages and pipeline |
| `metas.py` | `/api/metas` | Goals and targets |
| `condominios.py` | `/api/condominios` | Condominium management |
| `profiles.py` | `/api/profiles` | User profiles within ERP |

### AI & Matching

| Router | Prefix | Purpose |
|--------|--------|---------|
| `ai.py` | `/api/ai` | AI descriptions, lead scoring, price suggestions |
| `matching.py` | `/api/matching` | Property ↔ permuta matching with embeddings |

### Real Estate Operations

| Router | Prefix | Purpose |
|--------|--------|---------|
| `locacoes.py` | `/api/locacoes` | Lease/rental management |
| `vistorias.py` | `/api/vistorias` | Property inspections |
| `contratos.py` | `/api/contratos` | Contract management |
| `propostas.py` | `/api/propostas` | Proposals |
| `chaves.py` | `/api/chaves` | Key custody management |
| `assinaturas.py` | `/api/assinaturas` | Digital signatures |

### Financial

| Router | Prefix | Purpose |
|--------|--------|---------|
| `financeiro.py` | `/api/financeiro` | Financial transactions |
| `comissoes.py` | `/api/comissoes` | Commission tracking |
| `banco.py` | `/api/banco` | Bank account operations |
| `impostos.py` | `/api/impostos` | Tax management |
| `manutencao.py` | `/api/manutencao` | Maintenance costs |
| `seguros.py` | `/api/seguros` | Insurance policies |

### Marketing & Portals

| Router | Prefix | Purpose |
|--------|--------|---------|
| `marketing.py` | `/api/marketing` | Marketing campaigns |
| `portais.py` | `/api/portais` | Portal integrations |
| `portal_cliente.py` | `/api/portal-cliente` | Client-facing portal |
| `portal_externo.py` | `/api/portal-externo` | External portal |
| `site_imoveis.py` | `/api/site-imoveis` | Property website |
| `emails.py` | `/api/emails` | Email management |
| `whatsapp.py` | `/api/whatsapp` | WhatsApp messaging |

### Analytics & Compliance

| Router | Prefix | Purpose |
|--------|--------|---------|
| `relatorios.py` | `/api/relatorios` | Reports |
| `bi.py` | `/api/bi` | Business intelligence |
| `dimob.py` | `/api/dimob` | DIMOB tax compliance |
| `analise_credito.py` | `/api/analise-credito` | Credit analysis |
| `gamificacao.py` | `/api/gamificacao` | Gamification / performance scoring |
| `certidoes.py` | `/api/certidoes` | Certidões negativas (negative certificates) management |

### Organization

| Router | Prefix | Purpose |
|--------|--------|---------|
| `filiais.py` | `/api/filiais` | Branch management |
| `distribuicao.py` | `/api/distribuicao` | Lead/asset distribution |
| `campo.py` | `/api/campo` | Custom fields |
| `agenda.py` | `/api/agenda` | Calendar/scheduling |
| `documentos.py` | `/api/documentos` | Document management |

### Integrations & Automation

| Router | Prefix | Purpose |
|--------|--------|---------|
| `storage.py` | `/api/storage` | File upload/delete via Supabase Storage (dry-run when unconfigured) |
| `pdf.py` | `/api/pdf` | PDF generation for contracts, proposals, financial reports, DIMOB |
| `jobs.py` | `/api/jobs` | Background job submission and status tracking |
| `recorrencia.py` | `/api/recorrencia` | Recurring transaction automation (rent generation, overdue detection) |
| `notificacoes.py` | `/api/notificacoes` | Notification system with channel preferences |
| `whatsapp_webhook.py` | `/api/whatsapp` | WAHA webhook receiver + session management |
| `meta_api.py` | `/api/meta` | Facebook/Instagram Lead Ads + campaign sync |

### Logging

| Router | Prefix | Purpose |
|--------|--------|---------|
| `action_log.py` | `/api/action-log` | Action audit log |
| `atividades.py` | `/api/atividades` | User activities |

### Utilities

| Router | Prefix | Purpose |
|--------|--------|---------|
| `webhook_utils.py` | N/A | Webhook utility helpers (not a router, but routing-adjacent) |

---

## Services (40)

### AI & Matching

| Service | Purpose |
|---------|---------|
| `ai_service.py` | GPT-4o-mini: descriptions, lead scoring, price suggestions |
| `embedding_service.py` | text-embedding-3-small: vector embeddings for ativos |
| `matching.py` | Composite scoring: region + price + specs + interests + embeddings |

### Domain Services

| Service | Purpose |
|---------|---------|
| `ativos_service.py` | Property/asset CRUD and business logic |
| `clientes_service.py` | Client management |
| `agenda_service.py` | Scheduling logic |
| `analise_credito_service.py` | Credit analysis |
| `assinatura_service.py` | Digital signature management |
| `banco_service.py` | Bank account operations |
| `bi_service.py` | Business intelligence metrics |
| `campo_service.py` | Custom field management |
| `comissoes_service.py` | Commission calculations |
| `contratos_service.py` | Contract management |
| `dimob_service.py` | DIMOB compliance |
| `distribuicao_service.py` | Distribution logic |
| `document_service.py` | Document handling |
| `email_service.py` | Email operations |
| `financeiro_service.py` | Financial transactions |
| `gamificacao_service.py` | Gamification scoring |
| `impostos_service.py` | Tax calculations |
| `locacoes_service.py` | Rental management |
| `manutencao_service.py` | Maintenance tracking |
| `marketing_service.py` | Marketing campaign logic |
| `portal_cliente_service.py` | Client portal logic |
| `propostas_service.py` | Proposal management |
| `relatorios_service.py` | Report generation |
| `seguros_service.py` | Insurance management |
| `vistorias_service.py` | Inspection logic |
| `whatsapp_service.py` | WhatsApp messaging via Meta Business API or WAHA |
| `xml_feeds.py` | XML feed generation for portals |

### Integrations & Automation

| Service | Purpose |
|---------|---------|
| `storage_service.py` | Supabase Storage: upload, delete, signed URLs (6 bucket categories, MIME validation, dry-run mode) |
| `pdf_service.py` | PDF generation via reportlab (contracts, proposals, financial reports, DIMOB) |
| `job_service.py` | In-memory async background jobs with named handlers and auto-cleanup |
| `signature_provider.py` | Digital signature dispatch: ClickSign, DocuSign, D4Sign, or internal mock |
| `recorrencia_service.py` | Recurring transactions: rent generation, lancamentos, overdue detection (idempotent) |
| `notificacao_service.py` | Multi-channel notification delivery (app, email, WhatsApp) |
| `meta_api_service.py` | Meta Graph API: Lead Ads sync, campaign metrics import |
| `certidoes_service.py` | Certidões negativas: issuance, renewal, status tracking |
| `credential_resolver.py` | Credential resolution chain: org_settings → platform_settings → env vars |
| `metas_service.py` | Goals/targets business logic and aggregation |

---

## Legacy Data Migration

The ERP database contains migrated records from an old Django permutas system. Migration scripts live in `migratingDB/` (see `../00-LANDSCAPE.md`). Key facts for development:

- **264 imóveis** and **13 permutas** were migrated into `erp.ativos`, along with ~214 placeholder `erp.clientes` and ~147 placeholder `erp.condominios`
- Migrated imóveis have `titulo_anuncio LIKE '[MOCK]%'` — these need real titles, fotos, and descriptions
- Migrated clientes/condominios originally had placeholder names (`Proprietário #N`, `Condomínio #N`), enriched in Phase 2 with real names/contacts (marked `[MIGRADO-ENRIQUECIDO]`)
- `erp.ativos.interesses` is a JSONB array storing exchange preferences (tipo_imovel, zona, valor range) — used by the matching algorithm
- `erp.matches` table is NOT populated by migration — it's filled by the `/api/matching/gerar` endpoint

---

## Exception Handling

Same handler stack as Core: `AppException`, `HTTPException`, `ValidationError`, `PostgRESTError` (PGRST116 → 404), generic fallback. Additionally includes `CorrelationIdMiddleware` and `RequestLoggingMiddleware`.

---

## Auth Pattern

Same as core: `authorization: Optional[str] = Header(None)` → `get_current_user(authorization)` → `(user, token)`.

SSO flow: Core platform issues SSO token → ERP validates via `/api/sso/validate` → creates local session.

**Org ID extraction**: Use `get_org_id(user)` from `dependencies.py` — never inline `user.user_metadata.get("org_id")`. Raises 400 if missing.

---

## Response Patterns

- `paginated_response(data, total, page, page_size)` — List endpoints
- `success_response(data)` — Single items
- `ok_response(message)` — Deletes and actions

---

## Security Patterns

### Rate Limiting
Public and AI endpoints use `@limiter.limit("30/minute")` from `app.rate_limit`. The shared `limiter` instance lives in `rate_limit.py` to avoid circular imports. Applied to: `ai.py` (3 endpoints), `whatsapp.py` `/send`, `portal_externo.py` (5 public endpoints).

### Webhook HMAC Verification
`whatsapp_webhook.py` verifies HMAC-SHA256 signatures via `x-hub-signature` header when the org's `webhook_secret` is configured. Unverified requests are rejected with 403.

### Production Safety
- `jwt_secret` defaults to empty string — server raises `RuntimeError` at startup if empty in production (`not debug`)
- `debug` defaults to `False` — docs/redoc endpoints are only exposed when `debug=True`
- Portal endpoints (`portal_externo.py`) scope all queries by `org_id` from the JWT token

---

## Router Patterns

### DELETE Pre-checks
All DELETE endpoints verify the record exists before attempting deletion:
```python
check = db.table("x").select("id").eq("id", entity_id).execute()
if not check.data:
    raise HTTPException(status_code=404, detail="Entidade não encontrada")
db.table("x").delete().eq("id", entity_id).execute()
```

### Server-side Search
List endpoints with a `busca` query param apply `.or_()` with `ilike` for server-side filtering BEFORE pagination:
```python
if busca:
    query = query.or_(f"nome.ilike.%{busca}%,email.ilike.%{busca}%,telefone.ilike.%{busca}%")
    count_query = count_query.or_(...)
```

### Router → Service Delegation
Business logic belongs in services, not routers. Routers are thin: auth + validation + delegation.
- `bi.py` → `BIService.get_dashboard_resumo()` for dashboard aggregation
- `whatsapp.py` → `whatsapp_service.send_via_waha()` for message sending
- Financial batch operations → `financeiro_service`, `recorrencia_service`

---

## Performance Patterns

### N+1 Prevention (Zero Tolerance)
**Every DB operation touching multiple rows MUST be batched. No workarounds, no exceptions.** If a loop contains `db.table(...)`, it's almost certainly an N+1 bug.

**Patterns:**
- **Batch SELECT**: `.in_("id", ids)` + build lookup dict — never `.eq("id", id).single()` in a loop
- **Batch INSERT**: `.insert([row1, row2, ...])` — never `.insert(single_row)` in a loop
- **Batch UPDATE**: `.update(data).in_("id", ids)` — never `.update(data).eq("id", id)` in a loop
- **Batch UPSERT**: `.upsert(rows, on_conflict=...)` — never `.upsert(single_row)` in a loop
- **Enrichment**: Fetch related records with `.in_()`, build `{id: record}` dict, iterate in Python

**Examples in codebase:**
- `financeiro_service.mark_overdue()` — Single bulk UPDATE for all overdue lancamentos
- `recorrencia_service.gerar_alugueis_mes()` — Batch fetch existing, build set, batch insert
- `contratos_service.gerar_parcelas()` — Batch INSERT for all installments
- `contratos_service.mark_overdue()` — `.update().in_("id", overdue_ids)` instead of loop
- `certidoes router /fila-tjsp` — `.in_("id", consulta_ids)` to enrich queue items
- `filiais router /consolidado` — `.in_("filial_id", ids)` to count per-branch
- `meta_api router /sync-leads` — `.in_("lead_id", ids)` to check existing, then batch insert new
- `embedding_service.embed_ativos_batch()` — `.in_("id", ativo_ids)` to fetch all ativos at once

### Query Scoping
- `bi.py` dashboard queries include `year_start` filter on all table queries
- `financeiro.py` `/resumo` defaults to current year start if no date provided
- `financeiro.py` `/fluxo-caixa` uses month-based cutoff

---

## Test Structure

```
tests/
├── conftest.py                    # MockSupabaseClient, AuthClient fixtures
├── test_postgrest_handler.py      # PostgREST PGRST116 → 404 regression test
├── routers/                       # 49 router test files
│   ├── test_ativos_router.py
│   ├── test_clientes_router.py
│   ├── test_dimob_router.py
│   ├── test_matching_router.py
│   ├── test_storage_router.py
│   ├── test_pdf_router.py
│   ├── test_jobs_router.py
│   ├── test_recorrencia_router.py
│   ├── test_bi_dashboard_router.py
│   ├── test_notificacoes_router.py
│   ├── test_meta_api_router.py
│   └── ... (49 files)
├── services/                      # 25 service test files
│   ├── test_dimob_service.py
│   ├── test_embedding_service.py
│   ├── test_email_service.py
│   ├── test_matching_service.py
│   ├── test_financeiro_service.py
│   └── ... (25 files)
└── integration/
    ├── conftest.py                # StatefulMockClient
    └── test_clientes_integration.py
```

### Test Patterns

- **DELETE tests**: Must provide mock data with matching ID so the pre-check passes. Add a separate `test_delete_not_found` that sets empty data and expects 404.
- **Search tests**: Mock `.or_()` doesn't filter — tests verify the endpoint accepts `busca` param and returns 200, not the filtered count.
- **Mock builder**: `MockSelectBuilder` supports `.or_()`, `.gte()`, `.lte()`, `.ilike()` etc. as no-op chainable methods (return self without filtering).
