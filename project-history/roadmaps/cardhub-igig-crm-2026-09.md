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

**Today's status (2026-09-23 ~07:30 UTC)**: waves B–E BUILT + INTEGRATED on dev (19 commits, project `cardhub-igig-crm`, consent authored at 62f060cf1 from the owner's typed sentence — manifest: approved 19/19). igig catalog flipped `deploy_scope=live` on the owner's "go all the way to prod". Migrations 016–026 APPLIED to the live DB (025 backfilled the 2 legacy leads into negócios). Gates on the dev tip: igig backend 705 passed · FE tsc clean + 175 vitest + vite build · `predeploy_check igig` READY 12/12 · all 144 routes strict-401. **NOT YET IN PROD**: the joint cut (`release stage=bless mode=cut`) is refused because approved commits chain (seed `components/index.ts` code + INDEX.md prose) onto `noctus-release-tooling` (unapproved, another project) — clears only with the owner's `I approve shipping project noctus-release-tooling to production.` noctusai-1b holds deploy duty: cut → promote → `deploy_image igig` → `deploy_verify [igig]` → `spa_smoke [igig]` → browser smoke. Until then the 2026-08-13 prod container runs against the new schema (Esteira + public form error; public-form traffic ≈ 0 — 2 test leads ever).

## Phase 1 — Spec capture (SHIPPED with this commit)

| # | Title | Files | Status | Verify recipe |
|---|---|---|---|---|
| P1.1 | Owner spec + smoke-test findings + plan | NEW this file | **shipped** | none needed (doc) |

**Smoke-test findings (2026-09-22, local, real Supabase):** (1) 🔴 `GET /financeiro/excedentes/{YYYY-MM}` 500s in any <31-day month (`financeiro_service.py:82` builds `-31T23:59:59`; SQLite tests hide it). (2) 🔴 unauthenticated signature webhook activates contracts with a guessable dry-run id. (3) timer trusts payload `usuario_id`. (4) approval portal ignores current stage; link mint doesn't move to `aprovacao_cliente`; refação increment non-atomic; "agência notificada" never sent. (5) Esteira page overflows horizontally (scrollWidth 2049 @1688); cards show no cliente/pauta/responsável/prazo; no delete. (6) Calendário grid has no weekday offset/headers. (7) hooks without UI (agendar publicação, criar fatura, apontamentos). (8) `tarefa.responsavel_id`=profissional vs `apontamento.usuario_id`=auth user.

## Phase 2 — Wave A: seed CardHub + SW swap (SHIPPED — in prod 2026-09-22)

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

## Execution plan (2026-09-23, session 32f6dbc0)

Wave 1 (parallel, file-disjoint):
| slice | branch | scope |
|---|---|---|
| W1a | `feat/igig-crm-foundation` | igig BE spine: all new tables (pipeline_stages/movimentos comercial+esteira, negocio, lead enrichment, produto_servico, orcamento v1 + orcamento_item, tarefa→stage_id, pauta origin, contrato modalidade, integracao smtp/gmail/whatsapp/meta_leads, gmail_watch, orcamento_email, automacao), seed pipeline + card_hub mounts (cliente + negocio), move rules (Fechado needs orçamento → creates cliente; Esteira forward-1 / backward-with-motivo / refação), smoke bugs 1–4, 8 |
| W1b | `feat/seed-pipeline-before-move` | seed PipelineBoard `onBeforeMove` intercept + `MotivoMoveDialog` + server-rollback |
| W1c | `feat/seed-email-sender` | seed EmailSender Protocol + SMTP Real (attachments, Message-ID) + Fake + factory; SW EmailService shim |
| W1d | `feat/seed-gmail-watch` | seed Gmail watch/history/push-envelope/OIDC verify/Pub/Sub provisioning + reply matcher |

Wave 2 (after wave 1 integrates) — feature-vertical full-stack slices: Comercial funnel · Orçamentos + Produtos e Serviços + PDF · E-mail/Integrações/reply watcher · Clientes CardHub + marcas merge + calendário/esteira tabs · Esteira board + Calendário fix + portal · Financeiro alignment + report service + orphan hooks UI · Automations v1 + lead sources (WAHA, Meta) + AI assist. Mobile-first (R0) in every slice. Then: migrations → gate sweep → live browser smoke (desktop + 390px) → ship consent → prod.

## Phase 3 — Wave B: igig foundation (BUILT — on dev, awaiting cut)

Bugfixes 1–8; data model: `lead`, `negocio`(funnel card), `cliente` enrichment, `marca` N per cliente, `orcamento` + `orcamento_item` (recurrence: weekdays bitmask + qty/day), `produto_servico` catalog, pipeline_stages/movimentos for `comercial` + `esteira`; mobile-first shell.

## Phase 4 — Wave C: Comercial + Orçamentos + Produtos e Serviços (BUILT — on dev)
## Phase 5 — Wave D: e-mail (SMTP seam + PDF attach), reply watcher (Gmail API push, matching Message-ID), notifications, Integrações SMTP keys (BUILT — on dev; LIVE reply-watch needs owner GCP setup, see follow-ups)
## Phase 6 — Wave E: Clientes CardHub (marcas/calendário/esteira/financeiro tabs), calendar generation, Financeiro alignment + Report service, automations v1 (BUILT — on dev)

## Phase 2c — SW live e2e, extraction + contract ownership (IN PROGRESS — 2026-09-23, session 5297f35f)

**Why:** the owner asked for a live e2e (upload → auto-extraction → full contract) on prod. noctusai-39 (extraction) and noctusai-1c (contract/card) handed their workstreams to this session. Their state and blockers are in memory `project-sw-extraction-ownership-handover`.

**Live results (prod 755253934, synthetic set `tests/e2e_extracao`, texto variants, test card RICARDO AUGUSTO FERREIRA LIMA):**
- Persons: every core field OK (titular, cônjuge, vendedor).
- Imóvel: matrícula 4/5 (título texto is the human step), guia IPTU 1/1, CND IPTU 5/5.
- Scan variants and full generation are still pending.

**Owner decisions (2026-09-23):**
- Address comes from the property table and is mandatory at registration. The matrícula-read address is used only to WARN on divergence. Condo units need an internal address on the property table: Vista stores the gate address plus complemento.
- The agent may read all real document files to diagnose extraction. Migrations and a prod ship for this work are pre-approved. PII never leaves local scratch.
- The owner wants a data→file→source catalog (entry point: lead/card/party/imóvel page/matrículas/Vista/human). Architect design pending.
- Move Rodrigo's card from hand-registered EUROVILLE-535 to Vista ONE7515 (same matrícula 3917). The old matrícula link is write-once, so a new extraction is created for ONE7515.
- Ship bce607e74 (empreendimento title override, mig 158 already applied), 9bd6ac926 (stand-in-conformance gate) and 55ba0c313 (estado-civil equivalence) with this wave.
- Reference contracts (`products/social-wiring/contracts/`, git-ignored): 01→ONE9331 and 04→ONE10251 (unpublished, found only in the mirror), 08→ONE7515. Build 02, 03, 05, 06 and 07 from the contract addresses as manual registrations. The Vista key cannot read unpublished records.

**Slices (wave 1, file-disjoint, dispatched 2026-09-23):**
| Slice | Scope | Verify recipe |
|---|---|---|
| sw-card-ui-fixes (FE) | Cônjuge upload goes to the titular; stale panels after server-side extraction; lead Observações dropped; date-only TZ shift; /funil search debounce | Live: upload from the party panel lands on the party; panels refresh without reload |
| sw-imovel-pages-ui (FE) | Manual-code 404 toast; /matriculas?codigo prefill; IPTU/CND values + expired/positiva warning | Live on E2E-IMV-LIVRE |
| sw-matricula-pipeline-consolidation (BE) | Imóvel-page matrícula upload queues the full transcription (dedupe with /matriculas); doc-type labels leak internal LGPD notes | Live: an imóvel-page upload fills cartório/inscrição/ônus |
| sw-imovel-endereco-obrigatorio (full-stack) | Mandatory address at manual registration; condo internal address; divergence warning; endereco_curto per the rule; picker search covers bairro/empreendimento + near-match before "cadastrar novo" | Live: "Euroville" finds ONE7515; registration without an address is refused |
| sw-extracao-docs-reais (BE, seed parsers) | Real-corpus diagnosis (scans: CNH, certidão de casamento names/spouse split, nacionalidade, misfiles); synthetic layout fixtures | Before/after yield counts per tipo |
| catalog (architect → slices) | data→file→source catalog | Per-card field lineage view |

**Next (wave 2):**
1. Integrate, then run predeploy, CI, bless, deploy and verify.
2. Finish the test card to full generation (física + digital).
3. Move Rodrigo to ONE7515, re-validate extractions and generate v8, diffed against contract 08 with 1c's `diff_contrato.py`.
4. Take 1–2 real cards with files: fill gaps with fake data and report what was invented and why.
5. Build cards for reference contracts 01–08.
6. Build the 4 fake atendimentos 1c never finished (cv-parcelado/permuta/fgts).
7. Clean up the integrated sw-extr-* worktrees.

## Follow-ups after the 2026-09-23 build (named destinations)

Owner actions (not agent-doable):
- **F0** Type `I approve shipping project noctus-release-tooling to production.` — unblocks the joint cut (see status).
- **F1** SMTP: fill igig Integrações → E-mail SMTP (or set `SMTP_*` in the VPS `.env` as the platform fallback). Orçamento e-mail send answers 409 `smtp_nao_configurado` until then.
- **F2** Gmail reply-watch (R8) GCP one-time setup: enable Gmail + Pub/Sub APIs on the OAuth client's project; add `gmail.send`/`gmail.readonly` scopes + redirect `<PRODUCT_URL_IGIG>/api/integracoes/email/gmail/oauth/callback`; push-auth service account; env `GMAIL_PUSH_GCP_PROJECT/TOPIC/AUDIENCE/SERVICE_ACCOUNT` (topic/subscription provisioned idempotently by seed `ensure_push_subscription`). Then Integrações → Conectar Gmail. Full steps: `KB § INTEGRATIONS/google.md` §5a.
- **F3** `IGIG_ASSINATURA_WEBHOOK_SECRET` before any real signature provider (webhook fails closed without it); optional `IGIG_WAHA_WEBHOOK_HMAC_SECRET`, `IGIG_META_APP_SECRET`.
- **F4** OpenAI API credits exhausted (memory/kb embedding refresh 429s) — caches go stale until topped up.
- **F5** LGPD: the Assistente IA sends lead personal data to Anthropic with no per-org AI-consent gate (entry in LGPD-WARNINGS.md) — decide.

Seed/refinement (triage per recurrence rule):
- **R-a** Mobile full-screen-sheet classes now in 3+ copies (seed MotivoMoveDialog, CardHubDialog, igig `lib/mobileSheet.ts`, igig `SheetDialog`) → lift into seed `Dialog` (`NOC-REMEDIATE[seed-dialog-mobile-sheet]`).
- **R-b** Seed `Button` touch size (igig adds `max-sm:h-10` everywhere); seed confirm dialog (`NOC-REMEDIATE[seed-confirm-dialog]`, 5 igig sites); `useDebouncedValue`, `useCardHubGeral`, `useIsOrgAdmin` → `@noctusai/lib` when a 2nd product mounts the card organ.
- **R-c** Contract physical-signature modality at N=2 (SW + igig) → shared contract-signing module before a 3rd copy.
- **R-d** Seed `GmailClient.get_profile()` (N=2 SW + igig); seed `make_email_sender`/`make_gmail_client` `strict=True` (no silent Fake for transactional consumers).
- **R-e** ERP + SW certidão converters → seed `render_html_pdf` (N=4 lift done in seed; consumers not migrated).
- **R-f** igig cofre-key helper duplicated (`marca_router`, `integracoes_router`) → `app/services/cofre.py` at N=3; lead-source DELETE endpoints (UI can only edit); `noctus.dev.scan_wiring` misses generic `api.get<T>()` calls; `MockSupabaseClient.order()` is a no-op.
- **R-g** Toolkit: `branch_pointer` CLI from a worktree writes the primary ledger (rows stranded); commit-msg hook was not installed in this clone (fixed via `install-hooks.sh` 2026-09-23 — other clones?); `task_branch` wire_env links `.vite-temp` (dangles after primary `npm ci`); the cut's kb-counts false-coupling (noctusai-1b building `feat/release-derived-file-exempt`).
- **R-h** Esteira tarefa `etapa` column dropped in 017 without an expand/contract step — the schema-ahead-of-code window above is the cost; future breaking migrations ship expand → deploy → contract.

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
