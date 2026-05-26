# 04 — Database Context

> Supabase PostgreSQL · RLS per org/role · **7 schemas · ~232 tables** (verified 2026-04-18)
> RLS rules and access patterns: see `../PATTERNS/backend/database-rls.md`.

## Schema Architecture

| Schema | Tables | Backend | Tenant Key |
|--------|--------|---------|------------|
| `public` | ~23 | Core | `org_id` |
| `erp` | 105 | ERP | `org_id` |
| `personal-finance` | 18 | PF | `org_id` |
| `therapy` | 54 | Therapy | `clinic_id` |
| `daily_life` | 14 | Daily Life | `org_id` |
| `mailing` | 14 | Mailing | `org_id` |
| `seed` | 4 | Seed | `org_id` |

Each backend uses `ClientOptions(schema="<schema>")`. Auth hook functions stay in `public` (triggered by `auth.users`).

## Core Tables (`public` — ~23)

Key tables: `noctus_users` (extends auth.users, has `org_id`, `org_role`), `organizations` (tenant defs, onboarding state), `products` (catalog), `licenses` (org→product access), `plans`, `subscriptions`, `api_keys` (SHA256 hashed), `roles` (system + custom), `invitations`, `notifications`, `audit_logs`, `webhook_endpoints`, `webhook_deliveries`, `platform_settings`, `org_settings`.

Onboarding is stored as fields on `organizations` (`onboarding_completed`, `onboarding_steps`), not a separate table.

## ERP Tables (`erp` — 105)

**Core domain**: `ativos` (unified properties + exchange profiles via `natureza` field), `clientes` (leads), `matches` (AI match results), `negociacoes`, `profiles`, `user_roles`

**Key field — `ativos.natureza`**: `imovel` (property listing), `permuta_imovel` (real estate exchange), `permuta_automovel` (vehicle exchange). Matching pairs `imovel` entries with `permuta_*` entries.

**Embeddings**: `ativos.embedding` (vector 1536d, what it IS) + `ativos.embedding_interesses` (what it WANTS). Used for bilateral semantic matching.

**Other groups**: goals/tracking (metas, metas_config, funil_movimentos, atividades), real estate ops (condominios, vistorias, chaves, contratos, propostas, parcelas), financial (lancamentos, impostos, extratos, comissoes), rentals (contratos_locacao), documents/signatures (documentos, assinaturas, templates), marketing/email (campanhas, emails, templates), WhatsApp (messages, config), portals (portal_acessos, chamados, tokens, site_config), Meta API (meta_config, meta_leads, meta_campanhas_sync), gamification (pontuacoes, conquistas), system (status_pagina, user_actions_log, password_request_codes).

## PF Tables (`personal-finance` — 20)

**Op tables (12)**: `contas`, `categorias` (per-org seeded copies; 19 starter rows from `app/services/onboarding_service.PF_DEFAULT_CATEGORIAS` at first signup, then user-customizable), `transacoes`, `orcamentos`, `metas`, `recorrentes`, `carteiras` (portfolios), `ativos` (positions with ticker), `operacoes`, `patrimonio_snapshots`, `watchlists`, `resumos_mensais` (UNIQUE `(org_id, mes)`).

**Child tables (4)**: `orcamento_itens` (parent=`orcamentos`), `meta_contribuicoes` (`metas`), `watchlist_itens` (`watchlists`), `alocacao_alvo` (`carteiras`). RLS traverses to parent's `org_id`.

**AI / shared (4)**: `ai_outputs` + `ai_feedback` (per-product AI indicator widget), `invitations`, `status_pagina`.

**Org scoping (post 2026-05-03)**: every op table is `org_id NOT NULL REFERENCES public.organizations(id) + created_by UUID NULL` (audit field). RLS uniform via `public.current_org_id()` JWT-claim helper. Solo users land in a `is_personal=true` org auto-created by `noctusai_lib.domain.org.ensure_personal_org` at first-PF-login. See `KB § backend/03-PF.md § Org scoping`.

## Therapy Tables (`therapy` — 54)

**Identity**: clinics, therapist_profiles, patient_profiles. **Clinic config**: clinic_settings, clinic_branding, clinic_rules. **Financial**: patient_wallets, therapist_wallets, wallet_movements, transactions, invoices, refund_requests, stripe_subscriptions, payout_requests/batches, no_show_charges. **Scheduling**: appointment_slots, appointments, appointment_cancellations, sessions (LiveKit), recurring_schedules/skips. **Clinical**: anamnese, treatment_plans, treatment_plan_goals, evolution_notes, rooms, room_bookings. **Communication**: notifications, notification_preferences, email_logs. Plus reviews, messaging, attachments, patient notes, journaling tables.

**RLS**: 4-role system via `therapy.current_user_role()` and `therapy.current_clinic_id()` SECURITY DEFINER helpers: platform_admin (full), clinic_admin (own clinic), therapist (own + assigned patients), patient (own only).

## Trigger: `erp.set_timestamps_sp()`

Shared trigger on most ERP tables. Sets `created_at` on INSERT, `updated_at` on INSERT/UPDATE. Safely checks `information_schema.columns` before touching `updated_at`.

## Sidebar: `status_pagina`

Each product schema has this table. Controls page visibility per role. See `../PATTERNS/backend/backend.md` for page_status pattern.
