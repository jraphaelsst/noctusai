# cardhub-igig-crm-2026-09 — Seed CardHub (SW swap) → IgIg cliente-first agency CRM/ERP

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: 2026-09-22 igig live smoke test + owner interview (session 5297f35f).
> Decision: **Wave A first — extract social-wiring's card hub into the seed and swap SW (live) onto it with zero behaviour change; only then rebuild igig on the seed CardHub + PipelineBoard (waves B–E).** SW is the canonical consumer reference igig copies.

## Origin

Owner asked to smoke-test igig end-to-end, make the Esteira drag-and-drop, add a sales funnel (Leads → Qualificação → Negociação → Agendar briefing → Fechado), and make both boards + one centralized client card seed organs "consumed by both". Research showed the board already lives in the seed (`PipelineBoard`/`createPipelineHooks`/`noctusai_lib.domain.pipeline`); the rich card (SW `ClienteCardDialog` + `useCardHub` + `modules/card_hub`) does not — its seed extraction was planned as P2.1 of `lead-card-hub-2026-08.md` and never done. Owner mandate: do the extraction + SW swap FIRST and come back only when SW and igig are fully functional.

## Hard requirements (owner, verbatim intent)

- **R0 Mobile-first.** igig will be used mostly on a smartphone. Every page/modal/board is designed at 360–414px first; every smoke test includes a phone-width pass (no horizontal page scroll, touch drag on boards, modals as full-screen sheets). Desktop is the enhancement.
- **R1 Cliente-first app.** Separate objects: **Lead** (simple contact + specs) ≠ **Cliente** (rich, wired to marcas/orçamentos/contratos/calendário/esteira/financeiro). igig clientes follow the SW *marcas* reference (the business whose channels/credentials we manage); **a cliente has N marcas**; Marca UI merges into the single **Clientes** sidebar link.
- **R2 Comercial = sales funnel page.** "Comercial" contains only the pré-qualificação form link + the leads funnel. New/public-form leads appear in the first stage ("Leads"). Button to create leads manually.
- **R3 Boards (Comercial + Esteira) on the seed PipelineBoard:** card drag-and-drop changes stage (no stage dropdown); columns editable in-header — add icon, remove icon, inline rename, drag-to-reorder columns; system-role stages (Comercial `fechado`; Esteira `aprovacao_cliente`, `agendado`) renamable/reorderable but NOT deletable. Esteira rule: forward one step by drag; backwards allowed with a reason (logged; from approval = refação).
- **R4 Closing requires an orçamento.** Accepting an orçamento moves the lead's card to Fechado and **creates the Cliente**. Dragging to Fechado opens "which orçamento was accepted?" — no close without an orçamento.
- **R5 Orçamentos page** (new sidebar link under Clientes): listing of orçamento cards with filters; main list = active/pending; accepted/rejected under sub-tabs. Card opens a modal with data + calculator + contract generator; accept/reject icon buttons. "Novo orçamento" button; lead cards have a "Gerar orçamento" icon opening the same modal. DB table `orcamento` (+ items). An orçamento belongs to exactly 1 lead; a lead has N orçamentos.
- **R6 Orçamento items:** sections **Criação de conteúdo** (deliverables) and **Gestão de conta** (e.g. Gestão de conteúdo R$500, Gestão de DMs R$500). Items come from the **Produtos e Serviços** catalog page (new sidebar link, CRUD). Each content item has recurrence: tap weekday icons (seg…dom) + quantity per day, per item. Calculator redesigned modern/minimalist.
- **R7 Generate orçamento → pretty professional PDF** (table of items, frequencies, quantities, totals) stored in DB with all lines; **e-mailed to the lead with the PDF attached**, using SW's working SMTP mechanism; SMTP keys configurable in igig **Integrações** page (dev: noc keys, owner swaps later).
- **R8 Reply watcher:** detect the lead's e-mail reply to the orçamento → in-app notification + e-mail notification to the owner.
- **R9 Cliente card = the funnel card component** (same seed CardHub, same content) opened from Clientes listing and funnel. Cliente subtabs include: dados, marcas, calendário (auto-created pautas from accepted orçamento recurring items — **pautas only, esteira tasks on demand**), **Esteira filtered to that cliente**. Esteira page gets a cliente filter.
- **R10 Financeiro aligned with orçamento acceptance** (accepted orçamento ⇒ contract/retainer ⇒ faturas). **Report button** (date/period spec) whose generator is a callable service/API so future agents can run it on a schedule. Payment tracking manual for now.
- **R12 Contract signing modality (Digital | Física)** on the funnel card's contract — the gate: Digital ⇒ e-mail/e-signature flow; Física ⇒ no e-mail/e-sign, template gets manual signature lines + "N vias" closing, human prints + "Marcar como assinado" (+ scanned upload). Built first in SW (slice `sw-contrato-modalidade-assinatura`, 2026-09-22); igig contracts (wave C) consume the same behaviour.
- **R11 Automations v1:** stage-entry actions (tasks/checklists/owner/SLA), WhatsApp/e-mail touchpoints, stale/SLA alerts, AI assist (Claude via `noctusai_lib.integrations.llm`, provider=anthropic).

## Trigger conditions (the "when")

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | Wave A verified | SW local live smoke: card opens from /funil + /clientes, every subpage loads, notes/checklist/docs CRUD, timeline; SW test suite green on merged tip | igig must copy a proven consumer, not a moving target |
| T2 | Owner prod consent for SW | owner's explicit "promote SW" in chat | SW is live; prod exposure is the owner's decision |
| T3 | Wave B shipped | igig bugfix + domain migrations green, lead/cliente/marca model live locally | C–E build on the new model |

**Today's status**: none fired; roadmap authored, wave A design dispatched.

## Phase 1 — Spec capture (SHIPPED with this commit)

| # | Title | Files | Status | Verify recipe |
|---|---|---|---|---|
| P1.1 | Owner spec + smoke-test findings + plan | NEW this file | **shipped** | none needed (doc) |

**Smoke-test findings (2026-09-22, local, real Supabase):** (1) 🔴 `GET /financeiro/excedentes/{YYYY-MM}` 500s in any <31-day month (`financeiro_service.py:82` builds `-31T23:59:59`; SQLite tests hide it). (2) 🔴 unauthenticated signature webhook activates contracts with a guessable dry-run id. (3) timer trusts payload `usuario_id`. (4) approval portal ignores current stage; link mint doesn't move to `aprovacao_cliente`; refação increment non-atomic; "agência notificada" never sent. (5) Esteira page overflows horizontally (scrollWidth 2049 @1688); cards show no cliente/pauta/responsável/prazo; no delete. (6) Calendário grid has no weekday offset/headers. (7) hooks without UI (agendar publicação, criar fatura, apontamentos). (8) `tarefa.responsavel_id`=profissional vs `apontamento.usuario_id`=auth user.

## Phase 2 — Wave A: seed CardHub + SW swap (IN PROGRESS)

| # | Title | Files | Trigger | Verify recipe |
|---|---|---|---|---|
| A.1 | Seed BE card_hub router factory + canonical tables template | `seed/lib/backend/noctusai_lib/domain/card_hub/` | now | seed tests; SW routes byte-identical contract diff |
| A.2 | Seed FE CardHubDialog + createCardHubHooks + subpage registry | `seed/lib/frontend/src/components/cardhub/` | now | vitest + vite build |
| A.3 | Seed pipeline: editable columns (add/remove/rename in header, reorder drag, protected roles) | seed pipeline FE/BE | now | vitest; stages CRUD live |
| A.4 | SW swap BE + FE onto seed | `products/social-wiring/...card...` | after A.1/A.2 | local live smoke on /funil + /clientes (desktop + 390px) |

## Phase 2b — Wave A follow-ups (DEFERRED — fire when wave A is prod-verified, T2)

| # | Title | Files | Trigger | Verify recipe |
|---|---|---|---|---|
| A.5 | Seed `card_hub_routers` accepts `max_upload_bytes: Callable[[], int]` → SW drops its local upload-route override and uses `documento_upload_hook` | seed card_hub router + SW `card_hub/router.py` `_LOCAL_OVERRIDES` | T2 | SW route inventory identical; oversized-upload test green |
| A.6 | Unify SW `DocumentoStore` with seed card-hub documentos (marker `NOC-REMEDIATE[dry-documento-store]` points here) | `products/social-wiring/backend/app/services/documento_store.py` | T2 | SW documentos suites + LGPD access-log rows unchanged |
| A.7 | SW `app/services/table_reads.py` → shim over seed `integrations.persistence.table_reads` (only `resolve_actors` signature differs) | SW services | T2 | SW backend pytest |
| A.8 | `.organ.yaml` for card-hub sub-organs (AnexosSection, Timeline, ChecklistExtrasSection, …) so `check_canonical_organ_consumption` sees forks | `seed/lib/frontend/src/components/card-hub/` | T2 | keeper flags a planted local fork |
| A.9 | SW tests: drop remaining `@/components/ui/select` mocks (ContratosPanel, NegociacaoEstruturadaPanel, TermosNegocioSection) now that SW test setup has pointer-events + user-event | SW frontend tests | T2 | those suites green on real Radix |
| A.10 | Pre-existing SW vitest flake: 13 files time out at 15s under full-suite load (17 failures on baseline bef5ab17a) | SW vitest config | T2 | full SW vitest green twice in a row |

## Phase 3 — Wave B: igig foundation (DEFERRED — T1)

Bugfixes 1–8; data model: `lead`, `negocio`(funnel card), `cliente` enrichment, `marca` N per cliente, `orcamento` + `orcamento_item` (recurrence: weekdays bitmask + qty/day), `produto_servico` catalog, pipeline_stages/movimentos for `comercial` + `esteira`; mobile-first shell.

## Phase 4 — Wave C: Comercial + Orçamentos + Produtos e Serviços (DEFERRED — T3)
## Phase 5 — Wave D: e-mail (SMTP seam + PDF attach), reply watcher (IMAP poll matching Message-ID), notifications, Integrações SMTP keys (DEFERRED — T3)
## Phase 6 — Wave E: Clientes CardHub (marcas/calendário/esteira/financeiro tabs), calendar generation, Financeiro alignment + Report service, automations v1 (DEFERRED — T3)

## Anti-goals

- ❌ No behaviour change in SW during wave A (pure refactor onto seed).
- ❌ No SW prod deploy without owner consent (T2).
- ❌ No gateway/NFS-e/e-signature provider integration now (payments manual per owner).
- ❌ No autonomous report agents yet — only the callable report service they will use.
- ❌ No new per-product kanban/card forks (p-studio fork remains a known N=1 debt, tracked separately).

## Open questions

- **Q1** Reply-watch mechanism: IMAP polling of the sending mailbox (works with SW's Gmail app-password SMTP) vs Gmail API watch — proposed IMAP, seed Fake+Real+factory.
- **Q2** Where SW's working SMTP credentials live (root `.env` has no `SMTP_*`; SW prod env?).
- **Q3** Items to confirm with owner at wave C: orçamento validity/versions, discount approval, scope/revision limits (research MUSTs).

## Decision log

- **2026-09-22**: Sales card = opportunity tied to a lead; Fechado converts to cliente (owner).
- **2026-09-22**: Both boards editable, system-role stages protected (owner).
- **2026-09-22**: Accept closes; drag-to-Fechado requires choosing an accepted orçamento — no close without orçamento (owner).
- **2026-09-22**: Calendar generates pautas only; esteira tasks on demand (owner).
- **2026-09-22**: CardHub extraction + SW swap first, igig after (owner, overriding "igig first").
- **2026-09-22**: Mobile-first is a hard requirement (owner).
- **2026-09-22**: Reply watch = Gmail API **push** (users.watch → Pub/Sub push → our webhook; weekly watch renewal, no inbox polling). Provider-global DNS/MX inbound = later phase (owner). Resolves Q1.
- **2026-09-22**: Orçamento v1 includes validity/auto-expiry (no date = never expires), versions (only one acceptable), scope limits + excedentes, live estimated margin (owner). Resolves Q3.
- **2026-09-22**: Lost deals = "Marcar como perdido" archive with required reason + stage-lost + value + dwell time recorded (tech-lead rec; owner wants loss statistics — archive gives cleaner funnel math than a column).
- **2026-09-22**: Lead sources v1: form, manual, WAHA (configured exactly like SW), Meta Lead Ads; One Chat agent reads/answers WhatsApp and feeds the system (owner).
- **2026-09-22**: Wave A design → `cardhub-igig-crm-2026-09.wave-a-design.md` (D-A1 PostgREST seam, D-A2 desktop-identical/mobile additive, D-A3 SW contract byte-identical).

## Composes with

`project-history/roadmaps/lead-card-hub-2026-08.md` (P2.1) · `KB § PATTERNS/architect/products-consume-canonical-organs.md` · `KB § PATTERNS/backend/seed-fake-real-adapter.md` · `project-history/roadmaps/igig-2026-08.md`.
