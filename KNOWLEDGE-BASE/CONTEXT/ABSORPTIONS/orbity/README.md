# Orbity — Absorption Knowledge Base

> ℹ️ **Transient source-bridge (2026-06-02) — NOT permanent native knowledge.** This set is the foreign-source diagnostic bridge for the orbity rebuild. Per the **de-reference principle** (`KB § GUIDES/absorb-seed-workspace.md` Refinement 5): once each capability is *fully absorbed*, its durable value moves into a **native noc doc** (pattern/organ/guide) with **zero "Orbity" framing** — we learned from the source, but once it's ours, it's ours. So this `ABSORPTIONS/orbity/` corner is **temporary**: superseded by native docs as capabilities land, and **removed entirely at source-archival** (Gate 8). It carries external-source framing *only because it is the source analysis* — that framing must never leak into native noc docs. The `sistema-orbity/...` pointers are valid only until the user archives that transient workspace. Working notes mirror this under the source's `_NOC_ABSORPTION/`.

> **Purpose.** This folder is the faithful technical documentation of **Orbity** (`sistema-orbity`) — a production multi-tenant SaaS that a Brazilian marketing agency (Senseys) runs its entire business on, and resells to other agencies. It was reconstructed **read-only** from the actual source (React + Supabase; 296 migrations, ~121 tables, 73 edge functions, pt-BR) during the NoctusAI absorption process.
>
> **The mandate is knowledge preservation → capability uplift → propagation.** We (1) document Orbity's real code, flows, automations, procedures and rules; (2) compare *neutrally* against what noc ships today to find what we can learn (both ways); (3) restructure by **hardening each learned capability as a SEED organ** — improving our own mechanism — so the new orbity-noc product, *and the whole fleet*, consume it without drift or quality loss. **No knowledge is lost; the absorption is a platform-uplift engine, not a product port.** This doc set is the bridge — the rebuild reads from here. See [`12-ABSORPTION-STRATEGY-SEED-FIRST.md`](./12-ABSORPTION-STRATEGY-SEED-FIRST.md) for the loop.

## Status

| | |
|---|---|
| **Source HEAD** | `4ddc60e8` "Corrigiu mapeamento Conexa" |
| **Remote** | `github.com/senseysmarketing/sistema-orbity.git` |
| **noc slug** | `orbity` |
| **Absorption gate** | Gate 3 (Completeness audit / deep structural analysis) — **diagnostic done** |
| **Dev status** | ⛔ NOT started — user decides when to build. This is documentation only. |

## How to read this set

| Doc | What it covers | Read it when |
|---|---|---|
| [`00-ARCHITECTURE-OVERVIEW.md`](./00-ARCHITECTURE-OVERVIEW.md) | Stack, the three-tier multi-tenant model, the "four businesses an agency runs", scale metrics | Start here for the mental model |
| [`01-PROCEDURES-AND-WORKFLOWS.md`](./01-PROCEDURES-AND-WORKFLOWS.md) ⭐ | **The centerpiece.** Every automated procedure step-by-step: lead capture→qualification→Meta CAPI loop, the WhatsApp automation flow engine, billing reminders, monthly closure, daily digest, inbound-reply handling, onboarding, contract lifecycle, PPR profit-sharing | The business logic — this is the gold |
| [`02-DATA-MODEL.md`](./02-DATA-MODEL.md) | 121 tables grouped by domain, tenancy key, RLS model, DB-side triggers/functions/cron | Reconciling the schema to noc's org-RLS convention |
| [`03-BACKEND-EDGE-FUNCTIONS.md`](./03-BACKEND-EDGE-FUNCTIONS.md) | All 73 Supabase edge functions, grouped by capability, with the `_shared` lib layer | Mapping backend capabilities to noc FastAPI services |
| [`04-FRONTEND-FEATURE-MAP.md`](./04-FRONTEND-FEATURE-MAP.md) | App shell, routing, RBAC, the ~27 FE domains, data layer, craft worth keeping | Mapping FE to noc seed pages/components |
| [`05-INTEGRATIONS.md`](./05-INTEGRATIONS.md) | Every external service (Meta, UAZAPI, Google Cal, Stripe, Asaas, Conexa, SendPulse, Resend, FCM, Slack/Discord, AI), auth model, full secrets footprint | Mapping integrations to seed adapters |
| [`06-DOMAIN-GLOSSARY.md`](./06-DOMAIN-GLOSSARY.md) | pt-BR agency vocabulary → meaning | While reading any doc |
| [`07-GAP-MAP-AND-NOC-MAPPING.md`](./07-GAP-MAP-AND-NOC-MAPPING.md) | The gaps/risks for later resolution + Orbity-domain → noc-fleet overlap mapping (erp-imobiliario, social-wiring, core, …) | Planning the restructure |
| [`08-CAPABILITY-COMPARISON.md`](./08-CAPABILITY-COMPARISON.md) ⭐ | **Neutral** Orbity ⟷ noc comparison across 16 capability areas + ranked "what we can learn" (both directions) | The learning evaluation — read with 12 |
| [`09-DEEPDIVE-FINANCIAL-MANAGEMENT.md`](./09-DEEPDIVE-FINANCIAL-MANAGEMENT.md) | Faithful capture of the finance system (DRE, closure, recurring/installment, PPR, dunning) — the domain noc hasn't matured | Building the seed finance organ |
| [`10-DEEPDIVE-META-ADS.md`](./10-DEEPDIVE-META-ADS.md) | Faithful capture of the Meta/FB-Ads integration (CAPI loop, lead-ads, pixel, OAuth, spend/balance) | Extending the seed Meta adapter |
| [`11-DEEPDIVE-CHATBOT-AI-AUTOMATION.md`](./11-DEEPDIVE-CHATBOT-AI-AUTOMATION.md) | Faithful capture of the actual AI prompts, automation-flow defaults, scoring rules, message copy | Building the automation organ + AI patterns |
| [`12-ABSORPTION-STRATEGY-SEED-FIRST.md`](./12-ABSORPTION-STRATEGY-SEED-FIRST.md) ⭐ | The seed-first uplift loop: capability→seed organ→pilots→orbity-noc; the capability→organ map; no-drift guards; gate adaptation | The HOW of the restructure — read after 08 |

## Source-of-truth pointers (for any follow-up read)

All paths under `sistema-orbity`:

- The automation engine: `supabase/functions/_shared/automation-engine.ts`
- Lead scoring + Meta CAPI: `supabase/functions/process-lead-qualification/index.ts`
- Monthly financial closure: `supabase/functions/monthly-closure/index.ts`
- Billing reminders: `supabase/functions/process-billing-reminders/index.ts`
- WhatsApp adapter: `supabase/functions/_shared/uazapi.ts` + `_shared/phone.ts` + `_shared/whatsapp.ts`
- Conexa fiscal client: `supabase/functions/_shared/conexa-client.ts`
- Tenancy retrofit + RLS helpers: `supabase/migrations/20250924153557_*1dec0b95*.sql`
- Active build (automation flows): `supabase/migrations/20260523123000_whatsapp_automation_flows.sql`
- Final table shape (typed): `src/integrations/supabase/types.ts` (8,660 lines / 121 tables)
- Digest cron setup notes: `RESUMO_EMAIL_DIARIO.md` (in repo root)

> ⚠️ **Durability note (noc methodology — persistent-files-absorption).** This doc set lives inside the orbity workspace for working context. Before orbity is ever archived/retired (absorption Gate 9), these docs MUST be absorbed into noc `KNOWLEDGE-BASE/` + memory so the knowledge survives the source's deletion.
