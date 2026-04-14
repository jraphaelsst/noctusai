# 02 — ERP Backend Context

> Path: `products/erp-imobiliario/backend/app/` · Port: 8001 · 50 routers · 42 services · 1,634 tests
> Standard backend patterns (auth, responses, exceptions, DELETE pre-checks, search, N+1, rate limiting): see CLAUDE.md

## Overview

Full real estate CRM backend. Handles property management, client CRM, sales funnel, AI-powered matching, financial operations, WhatsApp messaging, digital signatures, PDF generation, Meta Ads integration, and compliance reporting.

## Router Groups (50)

- **Core Domain**: ativos, clientes, funil, metas, condominios, profiles
- **AI & Matching**: ai (descriptions, lead scoring, price suggestions), matching (property↔permuta)
- **Real Estate Ops**: locacoes, vistorias, contratos, propostas, chaves, assinaturas
- **Financial**: financeiro, comissoes, banco, impostos, manutencao, seguros
- **Marketing & Portals**: marketing, portais, portal_cliente, portal_externo, site_imoveis, emails, whatsapp
- **Analytics & Compliance**: relatorios, bi, dimob, analise_credito, gamificacao, certidoes
- **Organization**: filiais, distribuicao, campo, agenda, documentos
- **Integrations**: storage, pdf, jobs, recorrencia, notificacoes, whatsapp_webhook, meta_api
- **Logging**: action_log, atividades

## ERP-Specific Patterns

**Org ID extraction**: Use `get_org_id(user)` from `dependencies.py` — never inline `user.user_metadata.get("org_id")`. Raises 400 if missing.

**Webhook HMAC**: `whatsapp_webhook.py` verifies HMAC-SHA256 via `x-hub-signature` header when org's `webhook_secret` is configured.

**Production safety**: `jwt_secret` defaults empty — raises `RuntimeError` at startup if empty in production. Portal endpoints scope all queries by `org_id` from JWT.

## Legacy Data

264 migrated imóveis from old Django platform. Markers: `titulo_anuncio LIKE '[MOCK]%'`. See `00-LANDSCAPE.md` for details.

## Test Patterns

- **DELETE tests**: Must provide mock data with matching ID for pre-check. Add separate `test_delete_not_found` with empty data → 404.
- **Search tests**: Mock `.or_()` is no-op — tests verify endpoint accepts `busca` and returns 200, not filtered count.
