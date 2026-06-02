# 03 — Backend: Supabase Edge Functions (73)

The whole backend is **Deno/TypeScript edge functions + Postgres (RLS) + pg_cron + pg_net**. No separate API server. Project ref `ovookkywclrqfmtumelw`.

## 1. Shared infra (`supabase/functions/_shared/`) — the de-facto "lib" (11 modules)

Every function instantiates its own Supabase client; **there is no shared admin-client factory** (`createClient(URL, SERVICE_ROLE_KEY)` is duplicated inline ~60× — consolidate on absorption).

| Module | Role |
|---|---|
| `auth.ts` | The auth contract. `assertAgencyAccess(req, supabase, agencyId, roles?)`: (1) Bearer == `SUPABASE_SERVICE_ROLE_KEY` → `{internal:true}` service bypass; (2) else `auth.getUser(token)` (JWT) then **membership check against `agency_users`** (the tenant gate). `assertOptionalSecret(req, env, 'x-cron-secret')` for cron workers. `HttpError` for status-coded throws. No row enforcement beyond this — relies on Postgres RLS. |
| `automation-engine.ts` (528 ln) | The entire no-code automation runtime (see `01-PROCEDURES` §2). Pure functions over an injected `db`. |
| `uazapi.ts` | **UAZAPI** WhatsApp gateway client (NOT Meta Cloud API). Instance lifecycle (`/instance/init|connect|status|disconnect|delete`), QR parsing, webhook config, `sendText` (`/send/text`), `findMessages` (`/message/find`), status/ack normalization. `UAZAPI_SERVER_URL` + `UAZAPI_ADMIN_TOKEN` + per-instance `api_key`. |
| `whatsapp.ts` + `phone.ts` | **Brazilian phone normalization** (the "9th digit" + country-code-55 variant fan-out, `phoneVariants()`), message-content extraction, `{{var}}` template rendering, `resolveConversation()` (find-or-create with variant matching + back-fill). **Directly portable to noc's WAHA seed.** |
| `whatsapp-conversation.ts` | conversation resolution helpers (consumed by webhook/queue). |
| `conexa-client.ts` | **Conexa** invoicing/fiscal API v2 client (`<sub>.conexa.app/.../api/v2`, Bearer). Invoicing-methods, charge create/get, Pix fetch; structured logging to `conexa_api_logs` with **recursive secret-stripping**. |
| `conexa-payment-update.ts` | settlement-detection / reconcile helper. |
| `notification-insert.ts` | `insertOrAggregateNotification()` — writes `notifications`, aggregating same-user/type/entity within a 5-min window. |
| `formatDailyDigest.ts` | digest HTML/text composition for `send-daily-digest`. |

## 2. Capability clusters

| Cluster | Funcs | External service | Invocation | Enables |
|---|---|---|---|---|
| Meta/Facebook Ads | 11 | Graph API | user + webhook + cron | Connect ad accounts, pull campaigns/spend/balance, receive lead-gen leads, ad analysis |
| WhatsApp | 11 | **UAZAPI** gateway | user + webhook + cron | Connect WA number (QR), send/receive, sync history, drive automation, master support line |
| Automation engine | 5 | internal → whatsapp-send | cron (every min) + service-call | No-code lead-nurture flows |
| Payments (agency→client) | 6 | **Asaas**, **Conexa**, agency-owned **Stripe** | user + webhook | Charge the agency's clients (boleto/Pix/card) via the agency's own creds |
| Subscription (Orbity→agency) | 4 | Orbity-owned **Stripe** | user + webhook | Orbity's own SaaS billing |
| Conexa (fiscal) | 4 | Conexa API v2 | user + cron (30 min) | Issue fiscal invoices, reconcile paid charges |
| Notifications fan-out | 8 | Resend, FCM, Slack, Discord, SendPulse | cron + service-call | Multi-channel delivery |
| AI | 2 | **Lovable AI gateway** (gemini-3-flash) | user | Task/post copilot + support chatbot "Orbi" |
| Google Calendar | 5 | Google Calendar + OAuth2 | user + OAuth callback | Two-way agenda sync |
| Agency/account mgmt | 6 | internal / auth-admin | user (master/admin) | Onboard agencies, invite/create users, password, master delete, demo seed |
| Approvals/reports/finance/misc | 8 | internal | user + cron + public-token | Client approvals, public reports, monthly closure, storage GC, lead capture |

## 3. Per-function one-liners (by cluster)

**Meta/Facebook Ads:** `facebook-auth` (OAuth exchange), `facebook-accounts` (list/save ad accounts), `facebook-campaigns` (campaigns+insights), `facebook-balance` (funding), `facebook-account-summary` (aggregate metrics), `facebook-analysis` (perf analysis), **`facebook-leads`** (901 ln — Page/lead-form listing + saves integration + subscribes Page webhook + receives lead-gen webhook + syncs leads to CRM; auto-creates the form integration on first webhook hit), `facebook-sync` (on-demand), `facebook-sync-cron` (scheduled), `facebook-heartbeat` (token health 4h).

**WhatsApp:** `whatsapp-connect` (instance state machine + QR), `whatsapp-send` (send + persist; called by engine + UI), `whatsapp-webhook` (inbound receiver → §6 of procedures), `whatsapp-sync-messages` (history backfill), `resolve-whatsapp-conversation` (find/create), `master-whatsapp` (Orbity's own support line, fixed master id), `process-whatsapp-queue` + `process-whatsapp-ghosting` (**deprecated stubs** `{disabled:true}`).

**Automation:** `automation-trigger` (entry — called by capture-lead/facebook-leads/whatsapp-webhook), `process-automation-pending-actions` (the cron worker — atomic claim, backoff retry), `process-lead-ghosting` (**deprecated stub**).

**Payments (agency charges its clients):** `create-gateway-charge` (593 ln — unified Asaas + Conexa boleto/Pix), `settle-gateway-payment`, `payment-webhook` (Asaas/Conexa status), `create-agency-stripe-charge` (uses the *agency's own* `agencies.stripe_secret_key`, multi-currency, never Orbity's), `stripe-agency-webhook` (agency-scoped, `agencies.stripe_webhook_secret`, isolated), `test-agency-stripe` (validate key, no persist).

**Subscription (Orbity bills the agency):** `create-checkout`, `customer-portal`, `check-subscription`, `onboarding-checkout` (all Orbity's own Stripe).

**Conexa:** `conexa-list-invoicing-methods` (boleto-method select; one of only 2 `verify_jwt=true`), `invoice-conexa-sale` (`/charge` + Pix enrich), `reconcile-conexa-payments` (30-min cron settlement detection), `sync-invoices`.

**Notifications:** `process-notifications` (1522 ln — dispatch hub, process-lock, batch builder, fans out to channels; cron 15/30 min), `send-email-notification` + `send-daily-digest` (**Resend**), `send-push-notification` (**FCM** HTTP v1, manually JWT-signs a service-account PEM), `send-slack`, `send-discord`, `send-custom-webhook`, `sendpulse-api` (**SendPulse** marketing proxy, 20+ actions).

**AI:** `ai-assist` (task/post extraction copilot, Lovable gateway `google/gemini-3-flash-preview`, OpenAI-style tool-calling, per-agency prompt overrides via `agency_ai_prompts`), `ai-support-chat` (in-app "Orbi" chatbot).

**Google Calendar:** `google-calendar-auth` (start OAuth), `google-calendar-callback` (code exchange, public, service-role), `google-calendar-list`, `google-calendar-import`, `google-calendar-sync` (544 ln, two-way).

**Agency/account mgmt:** `agency-onboarding` (provision agency — `01-PROCEDURES` §7), `create-user`/`update-user-password` (auth-admin CRUD), `complete-invite`, `master-delete-agency` (`verify_jwt=true`), `setup-demo-account` (568 ln, seed demo).

**Approvals/reports/finance/misc:** `capture-lead` (public ingestion → CRM → fires `automation-trigger`), `approval-get`/`approval-decide` (public-token client approvals), `public-client-report` (token-gated ad report, no auth), `monthly-closure` (financial closing — §4), `process-billing-reminders` (dunning — §3), `process-batch-import` (Excel mass-import, chunked 50), `storage-garbage-collector` (orphan cleanup), `process-lead-qualification` (Meta-lead scoring + CAPI — §1).

## 4. External integrations & auth model

Every function uses the **service-role key** for DB writes (except `facebook-auth`, `google-calendar-auth`, `test-agency-stripe` which are user-token-only). Tenant isolation = `assertAgencyAccess` membership check + Postgres RLS. **Public/unauthenticated surfaces** (`verify_jwt=false` + token/secret in body/header): all webhooks, `public-client-report` (report token), `approval-*` (approval token), `capture-lead` (open ingestion), and the cron workers (optional `x-cron-secret`). See `05-INTEGRATIONS.md` for the full matrix + secrets footprint.

## 5. Gaps / hardening notes

- **3 deprecated stubs** (`process-whatsapp-queue`, `process-whatsapp-ghosting`, `process-lead-ghosting`) → superseded by `automation_flows`. `process-whatsapp-queue` still has a live cron schedule (dead schedule).
- **WhatsApp = UAZAPI, not WAHA** — adapter divergence vs noc's WAHA seed (both are QR/session providers → WAHA is the natural target; port `phone.ts`).
- **Two Stripe surfaces** (Orbity-as-SaaS vs agency-charges-clients) with strict credential isolation — preserve; conflating them is a security regression.
- **Conexa** (BR fiscal) has no direct noc analog beyond `adconnect`'s `nfe_service` — likely net-new adapter.
- **No `_shared` admin-client factory** — consolidate the ~60 inline `createClient(SERVICE_ROLE_KEY)`.
- **Lovable coupling** — AI via Lovable's gateway (not OpenAI/our `noctusai_lib.integrations.llm`, and no cost-logging); FE Lovable-hosted; redirect URLs hardcode `sistema-orbity.lovable.app`. Rehome on absorption.
- **Thin webhook signature verification** — FB uses a verify-token (no HMAC `x-hub-signature` validation); UAZAPI inbound is unauthenticated. Harden.
- **Mixed Graph API versions** (v18 sync, v19 auth/accounts) — pick one.
- **Hardcoded project ref** in `facebook-leads` webhook URL + Lovable domains in `google-calendar-auth`/`send-push-notification` — environment leakage to fix.
