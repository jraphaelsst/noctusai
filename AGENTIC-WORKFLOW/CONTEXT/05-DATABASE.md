# 05 — Database Context

> Provider: **Supabase** (managed PostgreSQL)
> RLS: Row Level Security scoped to `org_id`
> Access: `get_admin_client()` (service role) or `get_user_client(token)` (RLS-respecting)

---

## Schema Architecture

Tables are separated into **product-scoped PostgreSQL schemas**:

| Schema | Purpose | Backend |
|--------|---------|---------|
| `public` | Core platform tables + auth hook functions | `core/backend` (default) |
| `erp` | ERP product tables + business logic functions | `products/erp-imobiliario/backend` (`ClientOptions(schema="erp")`) |

The ERP backend's `database.py` uses `ClientOptions(schema="erp")` so all `.table()` and `.rpc()` calls target the `erp` schema via PostgREST's `Accept-Profile` / `Content-Profile` headers.

**Auth hook functions** (`handle_new_user`, `assign_default_corretor_role`, `has_role`) stay in `public` because they are triggered by `auth.users` (a platform-level table). Their bodies reference `erp.*` tables with schema-qualified names.

---

## Core Platform Tables (`public` schema)

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `noctus_users` | User profiles (extends Supabase auth.users) | `id`, `nome`, `email`, `role`, `org_id`, `org_role` |
| `organizations` | Tenant definitions | `id`, `nome`, `slug`, `plano`, `category`, `is_active` |
| `org_members` | User-to-org mapping | `user_id`, `org_id`, `role` |
| `products` | Product catalog | `id`, `nome`, `slug`, `url_base`, `is_active` |
| `licenses` | Org-to-product access grants | `id`, `org_id`, `product_id`, `status` |
| `plans` | Subscription tier definitions | `id`, `name`, `slug`, `price_monthly`, `price_yearly`, `max_users`, `max_products`, `features`, `stripe_price_id_*` |
| `subscriptions` | Org subscriptions | `id`, `org_id`, `plan_id`, `status` (active/canceled/expired/trial), `current_period_end` |
| `api_keys` | Hashed API keys (noctus_k_*) | `id`, `org_id`, `key_hash`, `key_prefix`, `scopes`, `expires_at` |
| `roles` | System + custom org roles | `id`, `org_id` (NULL=system), `name`, `permissions[]` |
| `platform_settings` | Global platform config | `key`, `value`, `description`, `is_secret` |
| `org_settings` | Per-org configuration | `key`, `value`, `org_id`, `is_secret` |
| `invitations` | Team invitations | `email`, `org_id`, `role`, `token`, `status`, `expires_at` |
| `notifications` | In-app notifications | `id`, `user_id`, `type`, `title`, `message`, `is_read` |
| `webhooks` | Webhook endpoint config | `id`, `org_id`, `url`, `events[]`, `secret`, `is_active` |
| `webhook_deliveries` | Webhook delivery log | `webhook_id`, `event`, `status_code`, `response_body` |
| `audit_logs` | Action audit trail | `user_id`, `org_id`, `action`, `resource_type`, `resource_id` |
| `onboarding_status` | Org onboarding progress | `org_id`, step completions |

---

## ERP Tables (`erp` schema)

### Core Domain

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `erp.ativos` | Unified properties + exchange profiles | `id`, `org_id`, `natureza` (imovel/permuta_imovel/permuta_automovel), `tipo`, `titulo`, `valor`, `cidade`, `estado`, `bairro`, `embedding` (vector), `status` |
| `erp.clientes` | Clients/leads | `id`, `org_id`, `nome`, `email`, `telefone`, `etapa_funil`, `responsavel_id`, `probabilidade`, `valor_estimado` |
| `erp.matches` | Property-permuta match results | `imovel_id`, `permuta_id`, `score`, `score_regiao`, `score_preco`, `score_specs`, `score_interesses`, `embedding_similarity` |
| `erp.negociacoes` | Active negotiations | `id`, `org_id`, `cliente_id`, `ativo_id`, `status`, `valor` |
| `erp.profiles` | ERP user profiles (linked to auth.users) | `id`, `nome`, `email`, `telefone`, `last_activity_at` |
| `erp.user_roles` | ERP role assignments | `user_id`, `role` (admin/corretor/coordenador/dev) |

### Goals & Tracking

| Table | Purpose |
|-------|---------|
| `erp.metas` | Goals/targets with deadlines |
| `erp.metas_config` | Monthly target configurations |

### Sales & CRM

| Table | Purpose |
|-------|---------|
| `erp.funil_movimentos` | Sales funnel stage movements |
| `erp.atividades` | Client activity records |

### Real Estate Operations

| Table | Purpose |
|-------|---------|
| `erp.condominios` | Condominium data |
| `erp.imoveis` | Property listings (legacy) |
| `erp.perfis_permutas` | Exchange profiles (legacy) |
| `erp.imoveis_perfis_permutas` | Property-permuta N:N join |

### System

| Table | Purpose |
|-------|---------|
| `erp.status_pagina` | Page visibility per role (controls sidebar) |
| `erp.user_actions_log` | Audit trail for ERP actions |
| `erp.password_request_codes` | Admin temporary passwords |

---

## RLS Pattern

All ERP tables enforce tenant isolation:

```sql
CREATE POLICY "org_isolation" ON erp.ativos
  FOR ALL
  USING (org_id = auth.jwt() ->> 'org_id');
```

- **User queries** go through `get_user_client(token)` → RLS filters by org
- **Admin queries** go through `get_admin_client()` → service role bypasses RLS
- **Settings resolution**: org_settings → platform_settings → env fallback

---

## Key Field: `erp.ativos.natureza`

The `ativos` table is **unified** — it stores three entity types:

| Value | Meaning | Key Extra Fields |
|-------|---------|-----------------|
| `imovel` | Property listing | `tipo`, `area`, `quartos`, `suites`, `vagas`, `valor`, `fotos`, `tour_virtual`, `pois` |
| `permuta_imovel` | Real estate exchange profile | `tipo_desejado`, `regiao_preferida`, `faixa_preco_min/max`, `quartos_min`, `vagas_min` |
| `permuta_automovel` | Vehicle exchange profile | `veiculo_tipo`, `marca`, `modelo`, `motor`, `ano`, `km`, `preco` |

Matching algorithm pairs `imovel` entries with `permuta_*` entries.

---

## Embeddings

The `erp.ativos` table has an `embedding` column (vector, 1536 dimensions) populated by the embedding service using OpenAI `text-embedding-3-small`. Used for semantic similarity in the matching algorithm.

---

## Migration Files

| File | Purpose |
|------|---------|
| `products/erp-imobiliario/backend/migrations/001_erp_imobiliario.sql` | Full ERP schema (fresh deploys) — creates `erp` schema + all objects |
| `products/erp-imobiliario/backend/migrations/002_ai_matching.sql` | pgvector embeddings + `match_ativos` function |
| `products/erp-imobiliario/backend/migrations/003_schema_separation.sql` | Moves objects from `public` → `erp` (existing databases only) |
