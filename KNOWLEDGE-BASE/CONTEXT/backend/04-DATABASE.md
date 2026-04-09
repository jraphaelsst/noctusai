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
| `personal-finance` | Personal finance tables | `products/personal-finance/backend` (`ClientOptions(schema="personal-finance")`) |

The ERP backend's `database.py` uses `ClientOptions(schema="erp")` so all `.table()` and `.rpc()` calls target the `erp` schema via PostgREST's `Accept-Profile` / `Content-Profile` headers.

**Auth hook functions** (`handle_new_user`, `assign_default_corretor_role`, `has_role`) stay in `public` because they are triggered by `auth.users` (a platform-level table). Their bodies reference `erp.*` tables with schema-qualified names.

---

## Core Platform Tables (`public` schema — 15 tables)

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `noctus_users` | User profiles (extends Supabase auth.users) | `id`, `nome`, `email`, `role`, `org_id`, `org_role` |
| `organizations` | Tenant definitions | `id`, `nome`, `slug`, `plano`, `category`, `onboarding_completed`, `onboarding_steps` |
| `products` | Product catalog | `id`, `nome`, `slug`, `url_base`, `ativo` |
| `licenses` | Org-to-product access grants | `id`, `org_id`, `product_id`, `status`, `inicio`, `fim` |
| `plans` | Subscription tier definitions | `id`, `name`, `slug`, `price_monthly`, `price_yearly`, `max_users`, `max_products`, `features`, `stripe_price_id_*` |
| `subscriptions` | Org subscriptions | `id`, `org_id`, `plan_id`, `status` (active/canceled/expired/trial), `expires_at` |
| `api_keys` | Hashed API keys (noctus_k_*) | `id`, `org_id`, `key_hash`, `key_prefix`, `scopes`, `expires_at`, `created_by` |
| `roles` | System + custom org roles | `id`, `org_id` (NULL=system), `name`, `slug`, `permissions[]`, `is_system` |
| `invitations` | Team invitations | `id`, `org_id`, `email`, `role`, `token`, `status`, `expires_at`, `invited_by` |
| `notifications` | In-app notifications | `id`, `user_id`, `org_id`, `type` (team_invite/subscription_change/usage_alert/system), `title`, `message`, `read`, `metadata` |
| `audit_logs` | Action audit trail | `id`, `user_id`, `org_id`, `action`, `resource_type`, `resource_id`, `details`, `ip_address`, `user_agent` |
| `webhook_endpoints` | Webhook endpoint config | `id`, `org_id`, `url`, `secret`, `events[]`, `is_active` |
| `webhook_deliveries` | Webhook delivery log | `id`, `endpoint_id`, `event_type`, `payload`, `response_status`, `response_body`, `attempts`, `status` |
| `platform_settings` | Global platform config (service role only) | `key` (PK), `value`, `description`, `is_secret`, `updated_by` |
| `org_settings` | Per-org configuration | `id`, `org_id`, `key`, `value`, `is_secret`, UNIQUE(`org_id`, `key`) |

Note: Onboarding status is stored as fields on `organizations` (`onboarding_completed`, `onboarding_steps`), not a separate table.

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

### Sales & Proposals

| Table | Purpose |
|-------|---------|
| `erp.propostas` | Property proposals with status flow and history |
| `erp.contratos` | Sales/rental contracts |
| `erp.parcelas_contrato` | Contract installment payments |

### Financial

| Table | Purpose |
|-------|---------|
| `erp.lancamentos` | Revenue/expense entries with vencimento tracking |
| `erp.impostos` | Property tax management (IPTU, ITBI, etc.) |
| `erp.extratos_bancarios` | Bank statement imports |
| `erp.movimentacoes_bancarias` | Bank transaction records with reconciliation |
| `erp.remessas` | CNAB banking remittance files |

### Commissions

| Table | Purpose |
|-------|---------|
| `erp.comissoes` | Commission calculations per sale |
| `erp.comissoes_splits` | Commission splits between agents |

### Rentals

| Table | Purpose |
|-------|---------|
| `erp.contratos_locacao` | Rental contracts with reajuste tracking |

### Calendar & Activities

| Table | Purpose |
|-------|---------|
| `erp.eventos` | Calendar events (visits, meetings, inspections) |

### Documents & Signatures

| Table | Purpose |
|-------|---------|
| `erp.documentos` | Document storage with metadata |
| `erp.document_templates` | Document templates with variables |
| `erp.assinaturas` | Digital signature tracking (internal/ClickSign/DocuSign/D4Sign) |

### Email & Marketing

| Table | Purpose |
|-------|---------|
| `erp.emails` | Email history (sent/received) |
| `erp.email_templates` | Email templates |
| `erp.campanhas` | Marketing campaigns (email/WhatsApp/alerts) |
| `erp.envios_email` | Campaign delivery tracking per recipient |

### WhatsApp

| Table | Purpose |
|-------|---------|
| `erp.whatsapp_messages` | Message history (sent/received) |
| `erp.whatsapp_config` | Provider config (Meta Business API or WAHA) |

### Inspections & Maintenance

| Table | Purpose |
|-------|---------|
| `erp.vistorias` | Property inspections with checklists |
| `erp.checkins` | GPS check-ins for field agents |
| `erp.vistorias_rapidas` | Quick field inspections |
| `erp.ordens_servico` | Maintenance work orders |

### Insurance

| Table | Purpose |
|-------|---------|
| `erp.seguros` | Insurance policy tracking |

### Credit Analysis

| Table | Purpose |
|-------|---------|
| `erp.analises_credito` | Credit analysis records (Serasa/Boa Vista/manual) |

### Key Management

| Table | Purpose |
|-------|---------|
| `erp.chaves` | Property key tracking |
| `erp.chaves_historico` | Key checkout/return history |

### Portals & Site

| Table | Purpose |
|-------|---------|
| `erp.portal_acessos` | Client portal access tokens |
| `erp.chamados_portal` | Portal support tickets |
| `erp.portal_tokens` | External portal tokens (owners/tenants) |
| `erp.site_config` | Property website configuration |

### Gamification

| Table | Purpose |
|-------|---------|
| `erp.pontuacoes` | Agent point scoring |
| `erp.conquistas` | Achievement badges |

### Distribution & Branches

| Table | Purpose |
|-------|---------|
| `erp.distribuicao_config` | Lead distribution configuration |
| `erp.filiais` | Branch office management |

### Notifications

| Table | Purpose |
|-------|---------|
| `erp.notificacoes` | User notification records |
| `erp.notificacao_preferencias` | Notification channel preferences |

### Meta API (Facebook/Instagram)

| Table | Purpose |
|-------|---------|
| `erp.meta_config` | Meta API credentials per org |
| `erp.meta_leads` | Imported leads from Facebook Lead Ads |
| `erp.meta_campanhas_sync` | Synced campaign metrics from Ads Manager |

### System

| Table | Purpose |
|-------|---------|
| `erp.status_pagina` | Page visibility per role (controls sidebar) |
| `erp.user_actions_log` | Audit trail for ERP actions |
| `erp.password_request_codes` | Admin temporary passwords |

---

## Personal Finance Tables (`personal-finance` schema)

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `contas` | Bank accounts (corrente, poupança, investimento, carteira) | `id`, `org_id`, `nome`, `tipo`, `saldo`, `instituicao`, `cor` |
| `categorias` | Transaction categories (custom per org) | `id`, `org_id`, `nome`, `tipo` (receita/despesa), `cor`, `icone` |
| `transacoes` | Financial transactions | `id`, `org_id`, `conta_id`, `categoria_id`, `valor`, `tipo` (receita/despesa/transferencia), `data`, `descricao` |
| `orcamentos` | Monthly budgets with category limits | `id`, `org_id`, `nome`, `mes`, `ano`, `valor_total` |
| `orcamento_categorias` | Budget category breakdown | `id`, `orcamento_id`, `categoria_id`, `valor_limite` |
| `metas` | Savings goals and debt payoff targets | `id`, `org_id`, `nome`, `valor_alvo`, `valor_atual`, `prazo`, `tipo` |
| `recorrentes` | Recurring transactions (salary, rent, subscriptions) | `id`, `org_id`, `conta_id`, `categoria_id`, `valor`, `frequencia`, `proximo_vencimento` |
| `carteiras` | Investment portfolios | `id`, `org_id`, `nome`, `descricao` |
| `ativos` | Individual asset positions | `id`, `org_id`, `carteira_id`, `ticker`, `quantidade`, `preco_medio`, `tipo` |
| `watchlist` | Stock watchlist items | `id`, `org_id`, `ticker`, `nome`, `preco_alerta` |

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

### Core (`core/backend/migrations/`)

| File | Purpose |
|------|---------|
| `001_noctusai_core.sql` | Full core schema — 15 tables, RLS policies, service role policies, seed data (fresh deploys) |
| `002_missing_tables.sql` | Adds 6 tables (notifications, audit_logs, webhook_endpoints, webhook_deliveries, platform_settings, org_settings) to existing databases that only ran 001 |

### ERP (`products/erp-imobiliario/backend/migrations/`)

| File | Purpose |
|------|---------|
| `001_erp_imobiliario.sql` | Full ERP schema (fresh deploys) — creates `erp` schema + all objects |
| `002_ai_matching.sql` | pgvector embeddings + `match_ativos` function |
| `003_schema_separation.sql` | Moves objects from `public` → `erp` (existing databases only) |
| `004_mvp_expansion.sql` | 42 new tables for MVP expansion (existing databases) |
| `005_fix_sidebar_pages.sql` | Fix `set_timestamps_sp()` trigger, seed all 42 sidebar routes, set admin role |
| `006_lead_scoring.sql` | Adds lead_score columns to erp.clientes |
| `007_certidoes_negativas.sql` | Certidões negativas table and indexes |
| `007_drop_legacy_tables.sql` | Drops legacy tables no longer in use |

### Personal Finance (`products/personal-finance/backend/migrations/`)

| File | Purpose |
|------|---------|
| `001_personal_finance.sql` | Full PF schema — accounts, transactions, categories, budgets, goals, portfolios, assets, watchlists, recurring transactions |
| `002_seed_product.sql` | Seeds the personal-finance product record in the core `products` table |
| `003_fix_schema_permissions.sql` | Fixes schema permissions for PostgREST access |

### Trigger Function: `erp.set_timestamps_sp()`

Shared trigger attached to most tables. Automatically sets `created_at` on INSERT and `updated_at` on INSERT/UPDATE. **Safely checks** `information_schema.columns` before touching `updated_at`, so tables without that column (e.g. `user_roles`, `password_request_codes`) don't crash.

### Sidebar Visibility: `erp.status_pagina`

Controls which pages appear in the sidebar. Each route must have a row in this table. RLS policies:
- `tipo_pagina = 'geral'` + `status = 'producao'` → visible to all authenticated users
- `tipo_pagina = 'administrativa'` → visible only to admins (`has_role(auth.uid(), 'admin')`)
- `status = 'desenvolvimento'` → visible to admins and devs only

The table is seeded with all 42 sidebar routes in migration 005 (and in 001 for fresh deploys).
