# 05 — Database Context

> Supabase PostgreSQL · RLS per org/role · 5 schemas
> RLS rules and access patterns: see CLAUDE.md

## Schema Architecture

| Schema | Tables | Backend | Tenant Key |
|--------|--------|---------|------------|
| `public` | 15 | Core | `org_id` |
| `erp` | 60+ | ERP | `org_id` |
| `personal-finance` | 10 | PF | `org_id` |
| `therapy` | 39+ | Therapy | `clinic_id` |
| `seed` | 2 | Seed | `org_id` |
| `daily_life` | 14 | Daily Life | `org_id` |

Each backend uses `ClientOptions(schema="<schema>")`. Auth hook functions stay in `public` (triggered by `auth.users`).

## Core Tables (`public` — 15)

Key tables: `noctus_users` (extends auth.users, has `org_id`, `org_role`), `organizations` (tenant defs, onboarding state), `products` (catalog), `licenses` (org→product access), `plans`, `subscriptions`, `api_keys` (SHA256 hashed), `roles` (system + custom), `invitations`, `notifications`, `audit_logs`, `webhook_endpoints`, `webhook_deliveries`, `platform_settings`, `org_settings`.

Onboarding is stored as fields on `organizations` (`onboarding_completed`, `onboarding_steps`), not a separate table.

## ERP Tables (`erp` — 60+)

**Core domain**: `ativos` (unified properties + exchange profiles via `natureza` field), `clientes` (leads), `matches` (AI match results), `negociacoes`, `profiles`, `user_roles`

**Key field — `ativos.natureza`**: `imovel` (property listing), `permuta_imovel` (real estate exchange), `permuta_automovel` (vehicle exchange). Matching pairs `imovel` entries with `permuta_*` entries.

**Embeddings**: `ativos.embedding` (vector 1536d, what it IS) + `ativos.embedding_interesses` (what it WANTS). Used for bilateral semantic matching.

**Other groups**: goals/tracking (metas, metas_config, funil_movimentos, atividades), real estate ops (condominios, vistorias, chaves, contratos, propostas, parcelas), financial (lancamentos, impostos, extratos, comissoes), rentals (contratos_locacao), documents/signatures (documentos, assinaturas, templates), marketing/email (campanhas, emails, templates), WhatsApp (messages, config), portals (portal_acessos, chamados, tokens, site_config), Meta API (meta_config, meta_leads, meta_campanhas_sync), gamification (pontuacoes, conquistas), system (status_pagina, user_actions_log, password_request_codes).

## PF Tables (`personal-finance` — 10)

`contas` (multi-type accounts), `categorias` (custom per org), `transacoes`, `orcamentos` + `orcamento_categorias`, `metas` (savings goals), `recorrentes`, `carteiras` (portfolios), `ativos` (positions with ticker), `watchlist`.

## Therapy Tables (`therapy` — 39+)

**Identity**: clinics, therapist_profiles, patient_profiles. **Clinic config**: clinic_settings, clinic_branding, clinic_rules. **Financial**: patient_wallets, therapist_wallets, wallet_movements, transactions, invoices, refund_requests, stripe_subscriptions, payout_requests/batches, no_show_charges. **Scheduling**: appointment_slots, appointments, appointment_cancellations, sessions (LiveKit), recurring_schedules/skips. **Clinical**: anamnese, treatment_plans, treatment_plan_goals, evolution_notes, rooms, room_bookings. **Communication**: notifications, notification_preferences, email_logs. Plus reviews, messaging, attachments, patient notes, journaling tables.

**RLS**: 4-role system via `therapy.current_user_role()` and `therapy.current_clinic_id()` SECURITY DEFINER helpers: platform_admin (full), clinic_admin (own clinic), therapist (own + assigned patients), patient (own only).

## Trigger: `erp.set_timestamps_sp()`

Shared trigger on most ERP tables. Sets `created_at` on INSERT, `updated_at` on INSERT/UPDATE. Safely checks `information_schema.columns` before touching `updated_at`.

## Sidebar: `status_pagina`

Each product schema has this table. Controls page visibility per role. See CLAUDE.md for page_status pattern.
