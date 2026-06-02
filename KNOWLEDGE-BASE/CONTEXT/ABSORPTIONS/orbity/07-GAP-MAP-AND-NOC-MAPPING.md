# 07 — Gap Map & Orbity → noc Mapping

Forward-looking artifact for the restructure (Gate 5+). Two parts: (A) the **overlap map** — where each Orbity domain already has a noc cousin to *consume/extend* vs *port* vs *net-new* (the "overlap is gold"); (B) the **gap/risk register** for later resolution. **Nothing here is a dev instruction yet — the user decides when to build.**

---

## A. Overlap map — Orbity domain → noc home

noc already fields deep structural cousins (several in the same pt-BR agency/sales space). Legend: **CONSUME** = a canonical organ/product already does this, wire to it · **EXTEND** = cousin exists, add a named seam · **PORT** = real logic to bring over · **NET-NEW** = no analog.

| Orbity domain | noc cousin (product / seed) | Overlap | Notes / what to preserve |
|---|---|---|---|
| Multi-tenant orgs + roles + RLS | **core** (`organizations`, `roles`, `team`) | EXTEND | `agency_id → org_id`; map `user_belongs_to_agency`/`is_agency_admin`/`get_user_agency_id` → `current_org_id()` family. Mostly a rename, RLS is compatible. |
| Agency SaaS subscription (Stripe) | **core** (`billing`, `subscriptions`, `stripe_service`, `plans`, `entitlements`) | CONSUME | Orbity's "Orbity→agency" Stripe rail ≈ core's billing. Plan limits (`max_users/clients/leads/tasks`) → `entitlements`. |
| Onboarding wizard + trial | **core** (`onboarding`) + seed onboarding | EXTEND | 8-step idempotent provision + 7-day trial + welcome-WhatsApp. |
| Master/vendor console + dogfood pipeline | **core** (`fleet_control`, `admin/*`) | EXTEND | Replace hardcoded `MASTER_AGENCY_ID` with a real platform-role/flag. `orbity_leads` = vendor's own CRM tenant. |
| Webhooks / OAuth / credentials vault | **core** (`webhooks`, `oauth`, `credentials`) + **social-wiring** (`credential_vault`, `integration_accounts`) | CONSUME | Per-agency DB-stored creds → credential_vault; encrypt (bytea-hex parity). |
| WhatsApp (UAZAPI) connect/send/inbound/conversations | **social-wiring** (`whatsapp_*`, WAHA seed) + **erp-imobiliario** (`whatsapp`, `whatsapp_webhook`) | PORT→EXTEND | Provider divergence UAZAPI↔WAHA (both QR/session). **Port `_shared/phone.ts` BR 9th-digit `phoneVariants()`** + defensive response-normalization into the WAHA seed. |
| **WhatsApp automation flow engine** | *(no direct analog — closest: erp `recorrencia`/`jobs`)* | **PORT (net-new organ)** | The crown jewel. Postgres-native durable queue + step machine + schedule windows + stop-rules. **Strong seed-organ candidate** (see Lessons). |
| Lead capture + CRM pipeline (funil) | **erp-imobiliario** (`funil`, `clientes`, `negociacoes`, `regras_pontuacao`) | EXTEND | Kanban stages, lead scoring rules, temperature. erp already has `regras_pontuacao` (scoring) + `funil`. |
| **Lead qualification + Meta CAPI feedback loop** | **erp-imobiliario** (`meta_api`, `meta_eventos`) | EXTEND→PORT | erp has `meta_eventos`; Orbity's accent-folded form-matching + CAPI quality-feedback (`QualifiedLead`/`ColdLead`) is richer — port the scoring + CAPI logic. |
| Paid-traffic ops (Controle de Tráfego) | **erp-imobiliario** (`meta_api`, `marketing`) + **social-wiring** (`meta_router`) | EXTEND | Ad-account sync, balance/spend, optimization cadence, per-client report. |
| Facebook Ads (accounts/campaigns/leads/insights/balance) | **seed Meta adapter** + **social-wiring** (`meta_router`) + **erp** (`meta_api_service`) | EXTEND | Lead-ads webhook ingestion + page-token flow likely net-new on the seed adapter. |
| Contracts (BR legal docs, snapshot) | **erp-imobiliario** (`contratos`, `assinaturas`, `pdf`) | EXTEND | Snapshot-on-signing pattern; PDF gen. erp has contratos + signature_provider. |
| Client billing — Asaas/Conexa (PIX/boleto/fiscal) | **adconnect** (`nfe_service`, `financial`) + **erp** (`financeiro`, `banco`, `impostos`) | PORT (Conexa/Asaas = NET-NEW adapters) | Conexa (NFS-e) + Asaas are new integrations. Webhook+reconcile-cron pattern. |
| Monthly closure + financial snapshots | **erp-imobiliario** (`financeiro`, `metas_fechamentos`) + **personal-finance** (`recorrentes`, `monthly_narrative`) | EXTEND | Idempotent per-agency closure → `monthly_snapshots`. erp has `metas_fechamentos`. |
| Recurring/installment expenses + salaries | **erp** (`recorrencia`, `financeiro`) + **personal-finance** (`recorrentes`) | CONSUME | |
| PPR profit-sharing + scorecards + NPS | **erp-imobiliario** (`gamificacao`, `metas`, `comissoes`) + **therapy-platform** (`commission_engine`) | EXTEND→PORT | Net-profit pool gated by revenue+NPS → weighted scorecards. commission_engine is the closest mechanism. |
| Tasks / agenda / reminders / routines | **daily-life** (`tasks`, `schedule`, `goals`, `notes`) + **erp** (`agenda`, `atividades`) | CONSUME | |
| Google Calendar two-way sync | **seed Google Calendar adapter** + **social-wiring** (`google_router`, `calendar_router`) + **erp** (`agenda`) | CONSUME | Seed already ships GCal. |
| Daily digest email + notifications fan-out | **seed digest base service** + **core** (`notification_service`, `audit_digest`) + **daily-life** (`daily_brief_service`) + **erp** (`metas_digest`, `notificacao`) | CONSUME→EXTEND | Multi-channel (email/push/Slack/Discord/webhook) + 5-min aggregation + per-event prefs. seed has BaseDigestService. |
| Email marketing (SendPulse) | **social-wiring** (`EmailMarketing` page, `email_service`) | EXTEND | SendPulse = new adapter (seed has Gmail/Resend-class). |
| Social content planning + approval workflow | **social-wiring** (`MediaCreation`, `chatbot`) + media-creator absorption | EXTEND | Content calendar, assignments, public approve/revision token links. |
| Push (FCM) + PWA | **seed PWA** + new FCM adapter | EXTEND | |
| AI assist / support chat | **seed `noctusai_lib.integrations.llm`** + **erp/social `ai_service`** | CONSUME | Re-point off Lovable gateway → our LLM lib **with cost-logging** (Orbity has none). |
| Public client report / approval (token links) | **erp-imobiliario** (`portal_externo`, `portal_cliente`) + **core consent routes** | EXTEND | Token-gated unauthenticated pages. |
| Bulk Excel import (smart-mapping) | *(no strong analog)* | PORT | Chunked-50 + AI column mapping. |

**Headline:** the vast majority is **CONSUME / EXTEND** against `core` + `erp-imobiliario` + `social-wiring`. True **NET-NEW**: Conexa (BR fiscal NFS-e) + Asaas adapters, UAZAPI provider variant, and the **automation flow engine** as a potential seed organ. `erp-imobiliario` is the single closest cousin — almost domain-isomorphic — and should be the primary reconciliation reference + likely **pilot** for the port (pilot-products-first cadence).

---

## B. Gap / risk register (for later resolution)

Tagged: 🔒 security · 🏗️ architecture · 🧹 hygiene · ❓ unknown-to-resolve.

### Security 🔒
1. **Tracked `.env` in the cloned repo** — may hold live Supabase/Stripe/Facebook/Conexa keys. Rotate any live key; scrub before any commit. (Not echoed in docs.)
2. **Plaintext third-party tokens** — `facebook_connections.access_token` (and other DB-stored creds) appear unencrypted. Wire through `credential_vault` with encryption; watch the **bytea `\x` hex-read parity trap**.
3. **Thin webhook signature verification** — FB uses a verify-token (no HMAC `x-hub-signature`); UAZAPI inbound is unauthenticated. Harden on absorption (run the noc `security` advisor + `keeper`).
4. **`profiles.role` overloaded** (agency job-role + platform super_admin on one column) → privilege-surface confusion. Split.
5. **Retrofit-residue RLS holes** — audit pre-retrofit tables for NULLABLE `agency_id` or leftover `USING (true)`. Run `get_advisors type=security` against the live project before trusting the surface.

### Architecture 🏗️
6. **Backend shape divergence** — Supabase edge functions + pg_cron + pg_net + PL/pgSQL triggers → must refactor to noc's FastAPI + seed-adapter + single-container (`serve_spa`, `FROM noctus-seed-*-base`) model. The 14 pg_cron jobs + DB triggers carry real behavior, not just the TS.
7. **Dual-implementation contract** — automation start/condition logic mirrored in TS (edge) AND PL/pgSQL (trigger). Pick ONE home on absorption (noc DRY / contract-first).
8. **Single-active-agency assumption** (`get_user_agency_id LIMIT 1`) — reconcile with noc's multi-org-per-user / org-switching; confirm no stale persisted client-side agency selector (the `activeAccountId` drift class).
9. **No shared admin-client factory** — ~60 inline `createClient(SERVICE_ROLE_KEY)`; consolidate.
10. **Lovable coupling** — AI via Lovable gateway (no cost-log), FE Lovable-hosted, hardcoded `sistema-orbity.lovable.app` / project-ref URLs in functions. Rehome + parameterize (env, not hardcoded URL/anon-key in `client.ts`).
11. **Mixed Graph API versions** (v18/v19) — unify.

### Hygiene 🧹
12. **3 deprecated stubs** (`process-whatsapp-queue`, `process-whatsapp-ghosting`, `process-lead-ghosting`) + 2 **dead cron schedules** still registered — don't port as live behavior.
13. **`_deprecated` tables** (`post_assignments_deprecated`) + CRM legacy permission fallbacks → data-model archaeology before wiring.
14. **No automated tests** found in the edge/back tier (FE has a small `src/__tests__`) — the port must add the seed's test discipline (status-pinned contracts, auth `==401`, Fake+Real parity).

### Unknowns to resolve before porting ❓
15. Conexa/Asaas **webhook→`client_payments.status='paid'`** exact flow + whether it retroactively feeds the current month's snapshot.
16. Agency **subscription dunning/suspension** behavior when an agency stops paying Orbity (vs trial expiry).
17. Whether a canonical **"ghosting" flow template** ships seeded or each agency authors its own.
18. **PPR scorecard math** — the function computing `weighted_average → max_share → final_bonus` + recalculation triggers.
19. **`crm_investments`** manual ad-spend entry + how it blends with Meta spend into cost-per-lead.
20. **Social-media approval routing** (`social_media_approval_rules`, `approval-decide/get`) — who approves what / escalation.

---

## C. Suggested restructure sequencing (draft — not started)

A *possible* order when the user greenlights dev (pilot-products-first, contract-first):
1. **Tenancy reconciliation** on `core` (agency→org rename map) — the foundation everything hangs off.
2. **`erp-imobiliario` as the pilot cousin** — port CRM/funil + Meta CAPI + contracts + financeiro/closure against it first (it's nearly isomorphic), prove the seams.
3. **Automation flow engine** — evaluate as a seed organ (durable-queue + step-machine); the highest-leverage net-new.
4. **Integrations** — UAZAPI→WAHA (port phone.ts), then NET-NEW Conexa + Asaas seed adapters; re-point AI to `noctusai_lib.integrations.llm`.
5. **Notifications/digest** — consume seed BaseDigestService + core notification_service; port multi-channel + 5-min aggregation.
6. **PPR/scorecards, social approval, bulk import** — last (most product-specific).
7. **Container refactor** to the house single-container shape; teardown with salvage-before-delete + KB/memory absorption of these docs.
