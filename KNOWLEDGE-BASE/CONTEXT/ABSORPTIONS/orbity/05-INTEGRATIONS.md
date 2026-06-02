# 05 — External Integrations

Multi-tenant boundary is the **agency**; most credentials are **DB-stored per-agency** (not env) — the key divergence from noc's env-based seed adapters.

## 1. Capability matrix

| Service | Auth | Capabilities | Credentials | Used by | Agency use-case |
|---|---|---|---|---|---|
| **Meta / Facebook Ads** | OAuth2 (Graph v18/v19) auth-code; user token per-agency; per-page tokens on demand | OAuth connect (popup), ad-account list/summary, campaign/adset/ad sync, **insights** (spend/impr/clicks/CPM/CPC/CTR/actions), **balance + spend_cap + amount_spent**, **Lead Ads webhook ingestion + on-demand pull**, heartbeat, cron sync | env `FACEBOOK_APP_ID/APP_SECRET/VERIFY_TOKEN/ACCESS_TOKEN`; per-agency token in `facebook_connections.access_token` (**plaintext**) | 10 `facebook-*` fns + `traffic`/`crm` FE | Paid-traffic management — the differentiator |
| **WhatsApp (UAZAPI)** | per-instance token + admin token; **QR session** (NOT Cloud API) | instance init/connect/status/disconnect/delete, QR, webhook config, send text, history, inbound→conversation→CRM promote→automation | env `UAZAPI_SERVER_URL/ADMIN_TOKEN`; per-instance `api_key` in DB | `whatsapp-*` + `_shared/uazapi|phone|whatsapp.ts` + `social-media`/`crm` | Client conversations, lead nurture, automation |
| **Google Calendar** | OAuth2 offline (refresh token), per-user scopes | two-way sync (create/PATCH/DELETE + import), calendar list, attendees | env `GOOGLE_CLIENT_ID/SECRET`; refresh tokens per user | 5 `google-calendar-*` + `agenda` | Team meeting/agenda sync |
| **Stripe (Orbity)** | secret key; webhooks | SaaS subscriptions (checkout, portal, status), sync-invoices, fast-track coupon | env `STRIPE_SECRET_KEY`, `STRIPE_FAST_TRACK_COUPON_ID` | create-checkout, customer-portal, check-subscription, onboarding-checkout, sync-invoices | Orbity's OWN billing of agencies |
| **Stripe (agency)** | per-tenant key; webhooks | agency charges its own clients (multi-currency) | **`agencies.stripe_secret_key` / `stripe_webhook_secret`** (per-tenant, isolated) | create-agency-stripe-charge, stripe-agency-webhook, test-agency-stripe | Agencies billing THEIR clients via card |
| **Asaas** (BR gateway) | `access_token` header; `api.asaas.com/v3` | customer create, **PIX + boleto** charges | `asaas_api_key` in agency settings (DB) | create-gateway-charge, settle-gateway-payment, payment-webhook | Agencies billing clients (PIX/boleto) |
| **Conexa** (BR fiscal/ERP) | `apiKey`; per-agency `baseUrl` | invoicing-method list/validate, `/sale` (nota fiscal), `/charge` (boleto + PIX copy-paste + QR), status poll, webhook + **cron reconciliation**, secret-stripped `conexa_api_logs` | `apiKey`+`baseUrl` in DB | conexa-*, invoice-conexa-sale, reconcile-conexa-payments, `_shared/conexa-client.ts` | Brazilian fiscal invoicing + reconciliation |
| **Resend** | API key | transactional email | env `RESEND_API_KEY` | send-email-notification, send-daily-digest | System/notification + digest email |
| **SendPulse** | per-agency OAuth client-creds | address books, senders, campaigns, SMTP send (20+ actions) | `sendpulse_client_id/secret` in `agency_integrations` | sendpulse-api | Email-marketing campaigns |
| **Slack** | per-agency incoming webhook | channel notifications + delivery logging | webhook URL in `notification_integrations` | send-slack | Internal alerts |
| **Discord** | per-agency webhook | channel notifications | DB-stored webhook | send-discord | Internal alerts |
| **Firebase FCM (v1)** | service-account JWT → OAuth2 | **web push** | env `FIREBASE_SERVICE_ACCOUNT`, `FIREBASE_PROJECT_ID` | send-push-notification + `pwa` | PWA push to agency users |
| **Custom webhooks** | user-supplied URL | outbound generic fan-out | DB-stored | send-custom-webhook | Customer integrations |
| **AI (Lovable AI Gateway)** | Bearer key; OpenAI-compatible | task/post prefill, analysis, contracts, captions, support chat; per-agency prompts | env `LOVABLE_API_KEY` | ai-assist, ai-support-chat | AI copilot/analysis |

**LLM provider:** `https://ai.gateway.lovable.dev`, model `google/gemini-3-flash-preview` (Gemini via Lovable's gateway — a Lovable lock-in artifact; re-point to `noctusai_lib.integrations.llm` on absorption, with cost-logging which Orbity lacks).

## 2. The big three (depth + cleverness worth learning)

**Facebook Ads — the differentiator.** Full OAuth2 with a twist: the `state` param carries base64-encoded `{supabase_jwt}` so the callback can persist the token under the user's own RLS context (`facebook_connections` upsert on `(agency_id, facebook_user_id)`) while ALSO `postMessage`-ing the token back to the opener popup as fallback. `facebook-leads` (901 ln) is BOTH the Meta webhook receiver (`hub.verify_token` challenge, `leadgen` filter, `leadgen_id`→`/leads` enrichment, `field_data` mapping, dedupe on PG `23505`, auto-creates the form integration on first hit) AND the authenticated app-API. Walks the official flow `/me/accounts → page token → /{page}/leadgen_forms` and auto-subscribes the page webhook (`subscribed_fields:['leadgen']`).

**WhatsApp — UAZAPI** (a Baileys-style QR session provider; the BR analog of WAHA). `_shared/uazapi.ts` is an excellent absorption study: very defensive provider-response normalization (token/QR/status/phone/messageId/JID each extracted from ~10 candidate paths), a domain status machine (`disconnected|provisioning|qr_pending|connected|error`), provisioning via `/instance/init` with `adminField01=agencyId` tagging + `/instance/all` fallback. **`_shared/phone.ts` solves the Brazilian 9th-digit problem** (`phoneVariants()` elastic matching) — directly portable into noc's WAHA seed.

**Payments — dual-rail BR billing.** TWO distinct domains, cleanly split: (a) **Stripe** = Orbity billing agencies for the SaaS; (b) **Asaas + Conexa** = agencies billing their own end-clients. `create-gateway-charge` (593 ln) branches on `billingType ∈ {asaas, conexa}`. `_shared/conexa-client.ts` is exemplary: timeout-wrapped HTTP, **recursive secret-stripping** before persisting every call, PIX/boleto URL parsing, method validation. **`reconcile-conexa-payments` is a cron safety-net** that polls charge status for payments the webhook missed and flips `pending→paid` — a robust **webhook-plus-reconciliation** pattern.

## 3. Full secrets / env footprint

`Deno.env.get`: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_FAST_TRACK_COUPON_ID`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `UAZAPI_SERVER_URL`, `UAZAPI_ADMIN_TOKEN`, `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`, `FACEBOOK_VERIFY_TOKEN`, `FACEBOOK_ACCESS_TOKEN`, `LOVABLE_API_KEY`, `RESEND_API_KEY`, `FIREBASE_SERVICE_ACCOUNT`, `FIREBASE_PROJECT_ID`.

**DB-stored per-agency credentials** (the multi-tenant model): `facebook_connections.access_token`, UAZAPI per-instance `api_key`, Google Calendar refresh tokens, `agency_settings.asaas_api_key`, Conexa `apiKey`+`baseUrl`, `agency_integrations.sendpulse_client_id/secret`, `notification_integrations` Slack/Discord/custom-webhook URLs.

> ⚠️ Also: the cloned repo has a **tracked `.env`** at root (`git ls-files | grep .env`). Treat any live keys there as potentially exposed → rotate before/at absorption. (Not echoed in these docs.)

## 4. BR-specific things noc doesn't have (learn from)

1. **Conexa fiscal/ERP** — BR nota-fiscal (NFS-e) + invoicing-methods + boleto/PIX with webhook **+ cron reconciliation**. (noc's closest is `adconnect`'s `nfe_service` — NF-e, a different fiscal document.) The reconcile-cron-as-webhook-backstop is the highlight.
2. **Asaas gateway** — native BR PIX + boleto, `access_token`-header auth.
3. **PIX copy-paste + QR-code** end-to-end (charge → copy-paste → QR → `client_payments`).
4. **BR 9th-digit phone normalization** (`_shared/phone.ts`) — concrete, portable to the WAHA seed.
5. **UAZAPI** as an alternative/complement to WAHA.
6. **Per-agency DB-stored integration credentials** model (vs env-based seed adapters) — relevant if noc goes multi-tenant-per-product.
7. **Dual-rail billing separation** (SaaS-billing vs end-client-billing).
