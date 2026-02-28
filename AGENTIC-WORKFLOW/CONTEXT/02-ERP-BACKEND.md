# 02 — ERP Backend Context

> Path: `products/erp-imobiliario/backend/app/`
> Server: FastAPI on port **8001**
> Tests: `products/erp-imobiliario/backend/tests/` (62 test files, 986 tests)

---

## Overview

Full real estate CRM backend with 46 routers and 37 services. Handles property management, client CRM, sales funnel, AI-powered matching, financial operations, WhatsApp messaging, digital signatures, PDF generation, notifications, Meta Ads integration, and compliance reporting.

---

## Routers (46)

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

---

## Services (37)

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

---

## Exception Handling

Same handler stack as Core: `AppException`, `HTTPException`, `ValidationError`, `PostgRESTError` (PGRST116 → 404), generic fallback. Additionally includes `CorrelationIdMiddleware` and `RequestLoggingMiddleware`.

---

## Auth Pattern

Same as core: `authorization: Optional[str] = Header(None)` → `get_current_user(authorization)` → `(user, token)`.

SSO flow: Core platform issues SSO token → ERP validates via `/api/sso/validate` → creates local session.

---

## Response Patterns

- `paginated_response(data, total, page, page_size)` — List endpoints
- `success_response(data)` — Single items
- `ok_response(message)` — Deletes and actions

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
├── services/                      # 12 service test files
│   ├── test_dimob_service.py
│   ├── test_embedding_service.py
│   ├── test_email_service.py
│   └── ... (12 files)
└── integration/
    ├── conftest.py                # StatefulMockClient
    └── test_clientes_integration.py
```
