# 10 · Conversion & leads

## Conversion surfaces

| Surface | Where | Behaviour |
|---|---|---|
| **WhatsApp** | Header icon, one floating button (after the consent decision), hero primary, product and pricing CTAs, closing band | Opens `wa.me/<number>?text=<prefill>`, where the prefill depends on context: page, product, plan, section. **Before redirecting**, it records a `whatsapp_click` lead event server-side, with no PII: page, product, UTM, anonymous visitor id |
| **Sign-up** | Header primary (when enabled), product and pricing CTAs, audience cards | Goes to the existing sign-up mode of `/login` (`POST /api/auth/signup`), with `?plan=&product=&utm_*` carried through |
| **Waitlist** | Replaces sign-up when it's disabled; also per product in state `lista de espera` | Form: nome, e-mail, WhatsApp (+55 default), perfil (SMB / empresa / dev / autônomo), product interest, plus an explicit opt-in checkbox with purpose text. Turnstile |
| **Custom-build brief** | `/solucoes`, home §4, `/contato` | ≤ 5 fields (nome, WhatsApp, empresa, tipo de projeto, mensagem). On success: "Continuar no WhatsApp" with the brief prefilled |
| ~~Demo booking~~ | — | **Not built** (owner decision) |

## Sign-up switch

`website_settings.signup_enabled` controls two things:
1. **The UI:** every sign-up CTA turns into the waitlist.
2. **The backend:** `/api/auth/signup` returns `403 signup_closed` when the switch is off.

The UI swap alone would be cosmetic, since the endpoint would still accept sign-ups. Invites (`/invite/:token`) are **not** affected. Every change to the switch is audit-logged: who, when, from → to.

## Lead model (core DB)

Scope note: `orbity.leads` + activities already exist product-locally. With the website this is the **second instance**, so a **triage** decides between a seed `domain/leads` and a core-local model *before* the backend slice ([08 §8](08-technical-architecture.md#8-seed-first-inventory-what-exists-vs-whats-built)). The shape below is the contract either way.

**`leads`**

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | — |
| `created_at`, `updated_at` | timestamps | — |
| `source` | enum: `waitlist \| brief \| whatsapp_click \| signup \| contact \| assistant` | — |
| `name`, `email`, `phone_e164` | text | Phone normalised to E.164 (+55…) |
| `company`, `profile`, `product_interest[]`, `message` | — | — |
| `locale` | `pt-BR` \| `en` | — |
| `utm`, `landing_path`, `referrer` | jsonb, text | — |
| `consent` | `{marketing: bool, text_version, at, ip_hash}` | LGPD proof |
| `stage` | enum: `novo → contatado → qualificado → proposta → ganho \| perdido \| descartado` | — |
| `owner_user_id` | FK, nullable | — |
| `owner_agent` | text, nullable | For the future AI agent |
| `score` | int, nullable | — |
| `next_action_at`, `next_action` | timestamp, text | — |
| `lost_reason` | text, nullable | — |
| `dedupe_key` | text | Normalised phone or e-mail; repeat submissions merge into the same lead as a new activity |

**`lead_activities`** (append-only)
- `id`, `lead_id`, `at`
- `kind`: `created | note | stage_change | whatsapp_out | whatsapp_in | email_out | call | form_submit | agent_action | handoff`
- `actor`: user id or `agent:<name>` or `system`
- `payload`: jsonb

**`site_events`** (first-party analytics, [12](12-privacy-lgpd-tracking.md#first-party-events))
- `id`, `at`, `anon_id`, `session_id`, `event`, `path`, `props`
- No PII.

## Fan-out on new lead (all Fake + Real + factory, all async after commit)

1. **Core DB**: the source of truth, committed first.
2. **Team notification by e-mail**: after the e-mail organ is formalized (Protocol + Fake + Real + factory).
3. **WAHA**: an internal WhatsApp alert to the sales number *(owner to confirm the target number)*. An automated message to the lead is sent **only** if they opted in, and only as a template (no spam).
4. **n8n**: through the seed `outbound_webhook` (signed payload), to a follow-up workflow.

A fan-out failure never loses the lead. It's recorded as a failed activity and retried; there's no silent failure.

## Follow-up management UI (Website → Leads)

Specified in [11 §Leads](11-admin-website-section.md#leads). In short:
- a pipeline board by stage, plus a table view;
- a lead detail with timeline, quick actions (open WhatsApp, e-mail, change stage, assign, schedule the next action) and consent state;
- filters (source, product, profile, stage, owner, date);
- CSV export (admin only, audit-logged).

## Agent-ready design

The owner plans an AI agent that talks to leads and closes deals. Designing for it now means nothing needs rework later:
- **The agent is just another actor.** Every agent step is a `lead_activities` row with `actor = agent:<name>`. The `owner_agent` field hands a lead to the agent, and a `handoff` activity returns it to a human.
- **A stable, documented API contract** (contract-first): list and claim leads, append activity, change stage, send a WhatsApp message via WAHA, schedule the next action. The admin UI uses the same endpoints, so the agent gets no private back door.
- **Guardrails, decided now and enforced later:**
  - the agent never messages leads without marketing consent;
  - it identifies itself as automated;
  - a human approves prices and discounts above a threshold;
  - it has per-lead rate limits;
  - everything is logged.
- **Entry points:** the v1.1 home "Pergunte à IA" section and inbound WhatsApp replies (WAHA webhooks) route into the same pipeline.
