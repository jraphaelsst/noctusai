# 02 — Data Model, Multi-Tenancy & RLS

~296 migrations (2025-09 → 2026-06), **121 final tables**, 69 DB functions, **406 `CREATE POLICY`**, 108 triggers, 14 pg_cron jobs. Final shape is typed in `src/integrations/supabase/types.ts` (8,660 lines).

## 1. Tenancy model

**Tenant key = `agency_id` (UUID, FK → `public.agencies(id)`, `ON DELETE CASCADE`).** This is structurally the **same shape as noc's `org_id`**.

History matters: Orbity started single-tenant (first migration, Sept 2025) with no tenant column — just `profiles.role`. Multi-tenancy was **retrofitted at migration #9** (`20250924153557_…1dec0b95`) which created `agencies` + `agency_users` and `ALTER TABLE … ADD COLUMN agency_id` across the original tables. Every table since ships `agency_id NOT NULL` from birth.

**Hierarchy** is a *data* hierarchy, not a *security* one: `agency → clients → leads`. An agency's clients/leads are rows, not auth principals. So tenancy is effectively **single-level: agency = the tenant.**

**Derivation (the critical security question): `agency_id` is derived from the trusted `agency_users` table via `auth.uid()`, inside SECURITY DEFINER helpers — NEVER from JWT, NEVER from user_metadata.**
```sql
get_user_agency_id() → SELECT agency_id FROM agency_users WHERE user_id = auth.uid() LIMIT 1
```
`LIMIT 1` ⇒ effectively one agency per user; **no active-org switching at the DB layer.**

**Roles (two axes):**
- Within an agency — `agency_users.role ∈ {owner, admin, member}`, checked by `is_agency_admin(agency_uuid)`.
- Platform-global — `profiles.role ∈ {administrador, super_admin}`, checked by `is_master_user()` / `is_super_admin()` / `is_master_agency_admin()` / `is_master_admin()` (all read the trusted `profiles` table via `auth.uid()`). One specific super_admin UUID is hard-seeded by UPDATE.

## 2. Table inventory (121 tables, grouped)

| Group (~count) | Tables (representative) |
|---|---|
| **Auth / agency / platform-billing (~14)** | `agencies`, `agency_users`, `agency_invites`, `agency_subscriptions`, `agency_payment_settings`, `agency_billing_templates`, `agency_onboarding`, `agency_integrations`, `agency_webhooks`, `agency_ai_prompts`, `agency_notification_rules`, `subscription_plans`, `profiles`, `usage_metrics`; `orbity_leads` (vendor's own funnel) |
| **Clients / leads / CRM (~14)** | `clients`, `client_notes`, `client_files`, `client_credentials`, `client_credential_history`, `leads`, `lead_activities`, `lead_history`, `lead_statuses`, `lead_scoring_rules`, `lead_scoring_results`, `crm_investments`, `nps_*` (responses/settings/tokens) |
| **Contracts (~4)** | `contracts`, `contract_templates`, `contract_services_templates`, `email_templates` |
| **Payments / finance / subscriptions (~15)** | `client_payments`, `billing_history`, `billing_message_logs`, `expenses`, `expense_categories`, `salaries`, `monthly_closures`, `monthly_snapshots`, `employees`, `employee_scorecards`, `bonus_programs`/`bonus_periods`, `ppr_*`, `conexa_*` (api_logs, webhook_log) |
| **Tasks / agenda / routines (~16)** | `tasks`, `task_templates`, `task_types`, `task_statuses`, `task_assignments`, `task_clients`, `task_approvals`, `task_approval_items`, `personal_tasks`, `routines`, `routine_completions`, `reminders`, `reminder_lists`, `meetings`, `meeting_clients`, `meeting_calendar_events`, `google_calendar_connections`, `notes` |
| **Social media / content (~16)** | `social_media_posts` (+`_post_templates`/`_content_types`/`_custom_statuses`/`_platforms`/`_settings`/`_assignments`/`_approval_rules`/`_schedule_preferences`/`_notifications`), `post_assignments`, `post_clients`, `content_plans`, `content_plan_items`, `content_library`, `campaigns` |
| **Traffic / ads (~10)** | `traffic_controls`, `traffic_control_comments`, `ad_account_metrics`, `ad_account_balance_settings`, `selected_ad_accounts`, `facebook_connections`, `facebook_pixels`, `facebook_lead_integrations`, `facebook_lead_sync_log`, `facebook_api_audit`, `meta_conversion_events` |
| **WhatsApp / automation (~20 — hottest)** | `whatsapp_accounts`, `whatsapp_conversations`, `whatsapp_messages`, `whatsapp_message_templates`, `whatsapp_connection_logs`, `whatsapp_webhook_logs`, `whatsapp_conversation_resolution_logs`, `master_whatsapp_logs`; `automation_flows`, `automation_steps`, `automation_executions`, `automation_execution_logs`, `automation_pending_actions`, `whatsapp_automation_control`, `whatsapp_automation_logs` |
| **Notifications (~9)** | `notifications`, `notification_queue`, `notification_preferences`, `notification_event_preferences`, `notification_integrations`, `notification_delivery_logs`, `notification_tracking`, `user_notification_channels`, `push_subscriptions`, `user_achievements` |
| **System / import / admin (~7)** | `system_config`, `system_settings`, `admin_notes`, `import_jobs`, `import_logs`, `master_system_logs` |

## 3. RLS model assessment — **compatible with noc, good news**

131 `ENABLE ROW LEVEL SECURITY`, 406 policies.

- **No JWT-claim or user_metadata RLS keying — ZERO `auth.jwt()` in any migration.** `raw_user_meta_data` is read in exactly one place: the `handle_new_user()` signup trigger (to seed `profiles.role/name` at INSERT). **Never read in a policy.** ⇒ Orbity does NOT have the privilege-escalation anti-pattern noc memory flags (`feedback_rls_never_key_on_user_metadata`).
- **Isolation = trusted-table derivation** (functionally noc's `current_org_id()` pattern, different names): policies call `user_belongs_to_agency(agency_id)` (151 uses), `is_agency_admin(agency_id)` (116), `get_user_agency_id()` (12) — all SECURITY DEFINER STABLE, resolving the principal from `agency_users`/`profiles` via `auth.uid()`.
- **Child/junction tables** without their own `agency_id` (21 of 121) derive tenancy by `EXISTS (SELECT 1 FROM parent p WHERE p.id=<fk> AND user_belongs_to_agency(p.agency_id))`. The rest without `agency_id` are legitimately global (`agencies`, `subscription_plans`, `system_config`, `profiles`) or master-only (`orbity_leads`, `master_whatsapp_logs`).
- **Master bypass** is sparing/explicit: `is_master_agency_admin()` (14), `is_master_user()` (4), `is_super_admin()` (3), `is_master_admin()` (3).
- **Recursion safety:** `get_current_user_role()`/`is_admin()` were introduced as SECURITY DEFINER specifically to break RLS infinite-recursion on `profiles` — same trap + same fix noc uses.

## 4. DB-side logic (heavy — 69 functions, 108 triggers)

- **Trigger families:** `update_updated_at_column` (fleet-wide); `handle_new_user` (profile bootstrap on `auth.users` INSERT); lead lifecycle (`track_lead_changes`, `set_lead_won_at`, `notify_new_lead`, `find_lead_by_normalized_phone`, `propagate_lead_id_to_messages`); WhatsApp↔lead linking (`auto_link_lead_to_whatsapp_conversations`, `merge_whatsapp_conversations`, `relink_orphan_whatsapp_conversations`, `sync_whatsapp_message_lead_id`); automation engine (`start_automation_flows_for_lead`, `stop_automation_flows_for_lead_reply`, `automation_conditions_match`, `automation_next_schedule_run_at`, `validate_automation_status_transition`); notifications (`notify_task_assignment`, `notify_post_assignment`, `trigger_push_on_notification`, `should_notify_user_for_event`); PPR/finance staleness (`trg_stale_from_payment_like`, `trg_stale_from_scorecard`, `mark_ppr_periods_stale_by_date`); validation guards (`validate_client_billing_type`, `validate_payment_billing_type`, `validate_expense_subscription_fields`, `check_bonus_period_overlap`); subscription lifecycle (`start_agency_trial`, `initialize_agency_subscription`, `is_agency_subscription_valid/active`); `delete_agency_cascade`; `check_agency_limits` (plan-limit enforcement).
- **pg_cron + pg_net** drive most async work — see `01-PROCEDURES` §10 for the 14-job table.

## 5. Risks / reconciliation notes (for the restructure)

1. **RLS reconciliation is mostly a RENAME mapping**, not a security rewrite: `agency_id → org_id`, `user_belongs_to_agency()/is_agency_admin()/get_user_agency_id() → current_org_id()`-family. No user_metadata keying to remediate.
2. **Single-active-agency assumption** (`LIMIT 1`) — if noc supports multi-org-per-user / org-switching, this is a behavioral gap. Confirm no persisted client-side agency selector could drift (the stale-`activeAccountId` class noc has been bitten by).
3. **`profiles.role` overloaded** (agency job-role + platform super_admin on one column) — untangle on absorption.
4. **Retrofit residue** — audit any pre-retrofit table whose `agency_id` is NULLABLE or whose policy still has a permissive `USING (true)` from the single-tenant era (those are isolation holes). `orbity_leads` has a `WITH CHECK (true)` on one policy (intentional public-funnel insert — confirm). **Run `get_advisors type=security` against the live project before trusting the surface.**
5. **Architecture-external logic** — a large share of behavior lives in pg_cron + pg_net + Edge Functions, NOT in migrations alone. Migrations are necessary-not-sufficient to reconstruct runtime behavior.
6. **Credential storage** — `client_credentials`/`agency_integrations`/`agency_payment_settings` hold third-party tokens. Check encryption-at-rest shape and the `bytea \x` hex-read parity trap (noc memory `feedback_bytea_credential_hex_read_parity`) before wiring seed adapters. Orbity's FB tokens appear **plaintext** (`facebook_connections.access_token`) — a security-review item.

**Key reconciliation files:** initial schema `20250922193850_*.sql`; tenancy retrofit + helpers `20250924153557_*1dec0b95*.sql`; master-role fns `*_550f79d3*.sql` + `*_48b3654b*.sql`; active build `20260523123000_whatsapp_automation_flows.sql`; final shape `src/integrations/supabase/types.ts`.
