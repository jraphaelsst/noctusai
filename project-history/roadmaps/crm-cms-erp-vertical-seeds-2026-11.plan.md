# CRM · CMS · ERP vertical seeds — modules mounted per market product (architect plan, 2026-11-08)

Read-only advisory. Base `origin/dev` @ 22778f870. Evidence is file:line from the tree; prod facts for erp are
quoted from noctusai-51's measurements (`…/f7927f50…/scratchpad/erp-absorption-plan.md`), everything else is
UNMEASURED and named as such.

---

## 0 · What the tree actually says (verified, not trusted)

| # | Fact | Evidence |
|---|---|---|
| F1 | Catalog: **active** = `agents, core, nosnolimiar, seed, social-wiring` (all live). **Asleep** (ativo=false): `orbity`, `igig`, `erp-imobiliario`, `therapy-platform`, `community` (+9 others). The agencies canon **orbity is asleep today**. | `deploy/fleet/active-scope.txt` (refresh 2026-11-05) |
| F2 | Mônica's app = slug **`nosnolimiar`** in the repo and catalog from the rename cutover on (`nome='Nós no Limiar'`; the prod catalog row stays `monica` until core 120 is applied in the cutover window). The rename is re-cut on dev as `feat/nosnolimiar-rename-v3` (v2 retired; C4 re-cut to owner option B: MT's marca deleted, one branding per org); runbook `products/nosnolimiar/projects/rename-2026-11/RUNBOOK.md`. `nos-no-limiar/` (sibling repo) is Mônica's **content KB** (VOZ/TESE/OBRA/HOOKS/PIPELINE), not an app; `jraphaelsst/limiar-app` is an external repo whose safety pack `agents` vendors. | `products/core/backend/migrations/087_seed_nosnolimiar_product.sql:17` (frozen, original seed); `products/nosnolimiar/projects/rename-2026-11/RUNBOOK.md`; `~/…/NoctusAI/nos-no-limiar/CLAUDE.md`; `products/agents/backend/app/public_ask/safety_pack/SOURCE.lock` |
| F3 | The **funnel organ already exists** and is the right CRM core: `FunnelConfig` (pipeline, tenancy org/platform, lost_reasons, gates, actions, statuses aberto/ganho/perdido/arquivado, responsavel_field, card_hub). Consumers: core (`noc_funnel.py`), SW (`modules/pipeline`), igig, orbity (`crm_router.py`), erp-imob. | `seed/lib/backend/noctusai_lib/domain/pipeline/funnel/config.py:42,130-215`; `projects/noc-funnel/CONTRACT.md` |
| F4 | Stage mechanics are already "rows, not enum" with immutable `slug`, editable `label`, semantic `papel`, lazy per-org `ensure_default_stages`, and an FE `PipelineStagesManager`. **This is exactly "seed owns mechanics, market ships default, org edits".** | `domain/pipeline/__init__.py:1-30`, `defaults.py:36-70`; `seed/lib/frontend/src/components/pipeline/PipelineStagesManager.tsx` |
| F5 | But the **stage LIST is declared 5 different ways** (N=5 ⇒ MUST formalize): (a) leads-lite `LeadsConfig.stages` = code literal, `leads.stage TEXT`, **not org-editable** (nosnolimiar `app/crm.py:46-49`); (b) SQL function `social_wiring.ensure_default_pipeline_stages` (SW `migrations/060…sql:236-255`, erp `042`); (c) Python `ensure_default_stages` with product tuples (igig `pipelines.py:123-147`, SW esteira); (d) orbity's own `lead_stages` table with `is_won/is_lost` booleans (`orbity/migrations/005_crm_core.sql:140-146`); (e) core migration INSERT for the platform org (`core/migrations/107_noc_funnel.sql:142-147`). | as cited |
| F6 | Market funnels today: **SW/One** Qualificação · **Visitas** · Proposta Recebida · Negociação · Proposta Aceita/Rejeitada(`proposta_aceite`) + Processos de Venda (8 stages, `final`). **core/noc (SaaS)** Novo · Contatado · Qualificado · Proposta. **orbity (Senseys)** Novo · Contato · Qualificado · Proposta · Negociação · Fechado(won) · Perdido(lost). **igig** Leads · Qualificação · Negociação · Agendar briefing · Fechado. **nosnolimiar** Lead · Atendimento · Negociação · Fechado(→Paciente). Only real estate has a Visita stage. | F5 citations |
| F6b | "Senseys" = the agency that runs orbity (`02-LANDSCAPE`); "One" = SW's real-estate client. | `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md` |
| F7 | `scaffold_product(overlay=…)` takes ONE overlay string; `templates/product-erp/overlay.json` = organs + pages + 2 nav groups, `deploy_scope='dev'`. Existing products (SW, core, nosnolimiar, orbity) were **never scaffolded** from an overlay, so an overlay alone cannot deliver "a market product mounts CRM+ERP+CMS". | `templates/product-erp/overlay.json`, `OVERLAY.md` |
| F8 | FE has **no manifest-driven route mechanism**; each host hand-adds lazy routes + nav. `MODULE_GROUP_ORDER` / `MODULE_GROUP_LABELS` / `orderNavGroups` are enqueued (`origin/mq/seed-sidebar-module-groups--35824a6`, `design-system/components/nav-groups.ts`) — pure data, no routes/permissions. | `vertical-seed.md:113`; mq ref |
| F9 | BE organ binding exists: `noctusai_seed.organs.mount_*` → `MountedOrgan`, `create_product_app(organs=[…])`, `ORGAN_REGISTRY` (migration generator, guard probes, FE route). `mount_leads`/`mount_clients` exist (`organs.py:689,731`). | `seed/framework/backend/noctusai_seed/organs.py:233-1023` |
| F10 | CRM-shaped code duplicated across products (recurrence counts): **assignment/distribution** N=3 (igig `distribuicao_router.py` 362 LoC, erp `distribuicao.py` 170, SW `julia_roteamento_router.py`+`leads/routers/corretores.py`+`julia_equipes`); **activities/tasks** N=3 (erp `atividades.py`, orbity `tasks_router.py` 335, SW card_hub `lembretes`/julia notificações); **opt-out/consent** SW-only today (`julia_opt_outs_router.py`, `julia_opt_out_service.py`, `julia_solicitacoes_titular_service.py`) but every outbound-messaging market needs it; **lead intake** N≥3 (SW `leads/importer/*`+`meta_ingest`+`portal_leads/*`, igig `lead_webhooks_router.py`+`integracoes_leads_router.py`, core `marketing/coreLead.ts`); **content-production board** N=3 (SW `media_creation/esteira`, igig `esteira`/`pauta_router.py`, orbity `content_plans_router.py`+`social_content_router.py`). | as cited |
| F11 | CMS-ish seed pieces: `editorial` organ (workflow + store + DDL, **not wired to any product** — `domain/editorial/__init__.py:1-12`), FE `marketing/*` landing organs (Hero, FeatureGrid, Steps, Faq, CtaBand, LeadCaptureForm, LandingNav/Footer, productBrand, theme), `json-ld.ts`, `photo_editing` organ, `content_performance`. ERP-imob CMS pieces: `site_imoveis.py` 267, `portais.py` 193, `portal_externo.py` 350, `portal_cliente.py`. | as cited |

**Two consequences that shape everything below:**
- The CRM seed is **mostly a convergence job, not a green-field build**: funnel + pipeline + leads + clients + quotes + card_hub exist. The build is (i) one stage-list mechanism, (ii) a module-mount contract, (iii) four missing organs (assignment, activities, consent, lead-intake/agent seams).
- `vertical-seed.md` models "one vertical → many market products". The owner's shape is **"one market product = composition of several verticals (CRM+ERP+CMS…) + its market spec"**. The doc needs that revision (§ 6).

---

## 1 · Decisions (ADR-shaped, one-way doors only)

### ADR-1 · A "module" is a declared bundle mounted into a market product (T2 — new seam, seed default)
- **Context.** Owner: modules inside ONE product per market, sidebar groups in canonical order. Overlays only help at scaffold time (F7); the 4 canons already exist.
- **Drivers.** Modifiability (new market = spec only), consistency of nav/routes/permissions across 4 canons, zero per-product wiring.
- **Options.** (A) overlay-only (scaffold-time copy) · (B) separate product per module (crm.noctusai, erp.noctusai) · (C) **runtime `ModuleSpec` consumed by `create_product_app(modules=…)` + FE `defineModule`, with overlays generated FROM the same specs**.
- **Outcome: C.** B contradicts the owner's shape and multiplies containers/SSO hops; A cannot reach existing canons.
- **Contract (BE)** `noctusai_seed.modules.ModuleSpec(key: ModuleGroupKey, organs: list[MountedOrgan], page_keys: list[str], permissions: dict[str, Role], license_key: str | None = None)`; `create_product_app(modules=[crm_module(...), erp_module(...)])` flattens to `organs=` (reuse `mount_organs`, F9). A module's routers keep house auth (org staff reads, `is_org_admin` writes, strict 401).
- **Contract (FE)** `@noctusai/lib/modules`: `defineModule({ key, items: [{ label, path, pageKey, element (lazy), roles? , children? }] })` → `{ navGroup, routes, pageKeys }`; host does `createProductLayout({ navGroups: orderNavGroups([...modules.map(m => m.navGroup), ...productLocal]) })` and spreads `routes`. Page visibility stays `status_pagina` (`page-status.ts`); role gating via `roles.ts`.
- **Mount rules.** (1) A page lives in exactly one module group (F8 nav map is the SW instance). (2) Existing URLs never move (deep links); new module pages take the `/crm|/erp|/cms/…` prefix (SW nav-map D2 rule — adopt fleet-wide). (3) A market adds items to a seed module only through `extendModule(crmModule, { items })` — declared, never a forked copy.
- **Consequences.** + one place for nav/route/permission truth; + overlays become generated. − one more seed abstraction to learn; − SW `navGroups.ts` must migrate (collides with `feat/jl-s10a-sw-agente-card`, see § 5).
- **Fitness function.** New keeper `check_module_page_status_rows`: every `ModuleSpec.page_keys` entry has a `status_pagina` migration row in the mounting product (the "nav item silently hidden" class, nav-map L4/L6). Plus `check_canonical_organ_consumption` extended to the module organs.
- **Revisit.** First org asking to buy a module subset ⇒ activate `license_key` against the core license gate (T-LIC).

### ADR-2 · One stage-list mechanism: `pipeline_stages` rows seeded from a market preset (T2 — shared-DB schema change)
- **Context.** F5: five shapes, one of them (leads-lite) not org-editable, one (orbity) a private table with booleans.
- **Outcome.** Every CRM board uses `pipeline_stages`/`pipeline_movimentos` (`pipeline_migration`). The market ships a `CrmPreset` (data): `pipelines: {key: tuple[StageDefault]}`, `lost_reasons`, `origins`, `activity_types`, `qualification_schema`, `nouns`. `ensure_default_stages` seeds it lazily per org (already the seed behaviour). Orgs edit in **Configurações › Funil** via `PipelineStagesManager`.
- **Code keys on `papel`, never on slug or position.** Canonical CRM roles (seed): `entrada`, `qualificado`, `proposta`, `proposta_aceite`, `ganho`, `final`; market roles are declared per preset (`visita` for real estate, `sessao_experimental` for clinics, `briefing` for agencies). **A feature keyed on a role that the org's funnel lacks is a declared no-op, not an error** — this is the "One has Visita, Senseys doesn't" answer: Julia's "visit scheduled" event moves the card to the stage with `papel='visita'` if one exists, else records the activity only.
- **Migration (expand → migrate → contract).** E: leads organ validates `leads.stage` against the org's active `pipeline_stages` slugs (pipeline key `leads`), seeding rows from `LeadsConfig.stages` on first read; `LeadsConfig.stages` becomes the preset. M: SW/erp SQL seeding fn → preset (SQL fn kept until no caller); orbity `lead_stages` → rows (`is_won`→`papel='ganho'`, `is_lost`→`perdido` lost-status). C: drop leads-lite literal path; drop orbity `lead_stages`; drop SW SQL fn (owner-visible migration).
- **Fitness function.** New keeper `check_stage_list_not_in_code`: a `StageDefault(`/`LeadStage(` literal outside a product's `app/market/` preset module, or a `CREATE TABLE …stages` outside `pipeline_migration`, fails. `assert_organ_migration_current` covers the DDL.
- **Revisit.** A market needs per-stage fields (required fields per stage) ⇒ that is `FunnelGate` keyed on `papel`, not a new mechanism.

### ADR-3 · Absorb-then-erase is a ladder with owner gates (T3 — data destruction)
See § 4. Gates A6 (retire surfaces) and A7 (drop schema/buckets) are **owner-go only**; everything before is reversible.

Quality-attribute scenario (the one the whole plan optimizes): *"A new market product (e.g. a second clinic vertical) gets funnel, lead intake, assignment, activities, consent and its agent hook by writing ONLY `app/market/crm_preset.py` + its L2 pages; zero edits under `seed/`; measured by the `test_*_wiring` suite of the new product and an empty `git diff seed/`."* It spends: a live migration on SW (ADR-2 M/C) and one more seed abstraction (ADR-1).

---

## 2 · CRM vertical seed (first build)

### 2.1 Organs (BE `noctusai_lib/domain/*` · FE `@noctusai/lib`)

| Organ | State | BE | FE | Reuses / lifts from |
|---|---|---|---|---|
| **funnel** (boards, cards, lose/reopen/archive, gates, actions) | exists | `domain/pipeline/funnel` | `components/pipeline/funnel` (`FunnelBoard`, `FunnelCardDialog`) | — (consumers converge) |
| **pipeline stages + presets** | exists + **add** `presets.py` (`CrmPreset`, canonical roles, role-no-op helper) | `domain/pipeline/{stages,defaults,presets}` | `PipelineStagesManager` mounted in CRM settings | igig `pipelines.py`, SW `migrations/060` fn, orbity `005` |
| **leads** | exists (leads-lite) — **converge** to stage rows (ADR-2) | `domain/leads` | `leads/*` (`LeadsBoard`, `LeadsList`, `LeadDetailModal`) | — |
| **lead intake** | **new** sub-seam of leads: `LeadSource` Protocol + registry; Fake + Real adapters: `whatsapp` (exists via inbox), `meta_lead_ads`, `website_form`, `xlsx_import`, `email` | `domain/leads/intake/` + `integrations/meta` | `LeadImportDialog`, `LeadSourcesSettings` | SW `leads/importer/*` (shape_detector, resolvers, parsers — generic), SW `meta_ingest_service`, igig `lead_webhooks_router`, core `coreLead.ts` |
| **identity / dedupe** | partial — lift | `domain/parties` link + `primitives` phone/CPF | SW `Revisão de Duplicados` page → organ | SW `identificadores*.py`, `whatsapp_identity.py` |
| **clients** (people under recurring service) | exists | `domain/clients` | `clients/*` | — |
| **assignment** | **new** | `domain/assignment`: teams, members, strategies `round_robin`·`by_team`·`by_source`·`manual`, capacity, out-of-office; writes `FunnelConfig.responsavel_field` | `AssignmentRulesPage`, `TeamsManager` | igig `distribuicao_router.py` (richest, lift base), erp `distribuicao.py`, SW `julia_roteamento_router.py`, `leads/routers/corretores.py` |
| **activities** | **new** | `domain/activities`: task/call/meeting/visit rows linked to `(entity_kind, entity_id)`, due, assignee, done, market `activity_types` | `ActivitiesPanel` (card hub tab), `MyTasks` page | erp `atividades.py`, orbity `tasks_router.py`, SW card_hub `lembretes` |
| **scheduling / appointments** | exists (engine) | `domain/scheduling` | needs `AppointmentsCalendar` organ | SW `modules/scheduling`, therapy `scheduling.py` |
| **proposals** | exists as `quotes` | `domain/quotes` + funnel `FunnelAction` "aceitar" → `QuoteAcceptHandler` moves card to `papel=proposta_aceite` | `QuoteEditor`, `QuoteAcceptPage` | SW `card_hub/propostas/*` converges onto quotes |
| **consent / opt-out** | **new** | `domain/consent`: per-channel opt-out registry (whatsapp/email/sms), source (agent/human/link/import), reason, `OutboundGate.check(org, channel, address)` called by every outbound sender; titular requests (LGPD art. 18) | `OptOutsPage`, `TitularRequestsPage` | SW `julia_opt_out_service.py`, `julia_opt_outs_router.py`, `julia_solicitacoes_titular_service.py` |
| **agent hook** | **new seam** | `domain/leads/agent_hook.py`: `LeadAgentHook` Protocol (`on_inbound`, `on_stage_entered`, `on_created`) + Fake + Real (`AgentsBridge` HTTP to the agents product by agent key) | `AgentBindingSettings` (which agent per org/line) | SW `agents_bridge_router.py`, `julia_lead_dispatcher.py`; nosnolimiar `nosnolimiar-leads` specs |
| **campaigns / attribution** | partial — lift fields only | `leads.campanha_id`, UTM, CAPI event seam | — | SW `campanhas_*`, `julia_capi_service.py` |
| **inbox** | exists | `whatsapp-inbox` organ | `WhatsAppInbox` | SW keeps its own store for now (T-INBOX) |
| **card hub** | exists | `domain/card_hub` | `CardHubDialog` | — |

### 2.2 CRM named seams (same format as ERP seams)

| Seam | Values / shape | Where a market differs |
|---|---|---|
| `pipelines` | set of board keys per market (`CrmPreset.pipelines`) | RE: `funil` + `processos_venda`; SaaS: `funil_noc` (platform tenancy); agencies: `comercial` + `esteira`(CMS); clinics: `leads` |
| `stage_set` | `pipeline_stages` rows (org, pipeline, slug immutable, label, cor, posicao, papel); market default via preset, **org-editable in settings**; seed owns mechanics only | the default list + market roles (`visita`, `sessao_experimental`, `briefing`) |
| `stage_roles` | canonical `entrada`·`qualificado`·`proposta`·`proposta_aceite`·`ganho`·`final` + market-declared; code keys on role; missing role ⇒ declared no-op | which roles exist |
| `lost_reasons` | `FunnelConfig.lost_reasons` (`LostReason(codigo, label, exige_texto)`); preset default (rows, org-editable at T-LOST) | the list |
| `lead_origins` | open string slugs; preset default; org adds | RE: portais (ZAP/VivaReal/OLX/Imovelweb), placa; clinics: indicação/Instagram; SaaS: site/demo |
| `lead_source` adapters | `LeadSource` Protocol + Fake + Real per channel | RE-only adapters (OLX/Imovelweb webhooks) stay L2 in SW behind the seam |
| `qualification_schema` | JSON-schema per market fed to the agent + shown on card | RE: tipo, faixa, bairro, financiamento, FGTS; clinic: queixa, modalidade, horário, valor; SaaS: produto, porte; agency: serviço, verba |
| `agent_hook` | `LeadAgentHook` → agents product by agent key, per org/line | RE: **Julia**; clinic: `nosnolimiar-leads`; SaaS/agency: none at start (Fake = no-op) |
| `assignment_strategy` | `round_robin`·`by_team`·`by_source`·`manual` + capacity; named-hook for a custom strategy | RE: corretor por equipe/plantão; agency: account manager; clinic: single owner |
| `activity_types` | preset list (`ligacao`, `reuniao`, `visita`, `sessao`, `followup`) | which types; visita only RE |
| `proposal_accept` | `QuoteAcceptHandler` + funnel action → `papel=proposta_aceite` | what accept spawns: RE processo_venda card; agency contract (`contracts`); clinic client (`clients.ensure_from_lead`); SaaS org/subscription (core) |
| `on_won` | `LeadsConfig.on_stage_entered` / `FunnelAction ganhar` | conversion target (as above) |
| `consent_channels` | whatsapp · email · sms; `OutboundGate` mandatory on every sender; who decides opt-out = **the agent** (owner 2026-11-08, commit 3e87e9734), the seed records + enforces | none in mechanics; retention per market legal note |
| `nouns` | Lead/Cliente/Paciente, Corretor/Terapeuta/Account, Negociação/Atendimento | labels only |
| `card_gates` / `card_actions` | `FunnelGate` / `FunnelAction` keyed on `papel` | RE: certidões/partes prontas before Assinatura |

### 2.3 Market defaults (the four `CrmPreset`s — live in each canon's `app/market/crm_preset.py`)

| Market (canon) | Boards | Default stages (papel) | Origins | Agent | Won ⇒ |
|---|---|---|---|---|---|
| Real estate (SW, client One) | `funil`, `processos_venda` | Qualificação(qualificado) · **Visitas(visita)** · Proposta Recebida(proposta) · Negociação · Proposta Aceita/Rejeitada(proposta_aceite); Processos: 8 stages … Nota Fiscal(final) — **today's values, unchanged** | whatsapp, meta_lead_ads, portais (zap, vivareal, olx, imovelweb), site, placa, indicação | Julia | `processos_venda` card |
| SaaS (core/noc) | `funil_noc` (platform tenancy) | Novo(entrada) · Contatado · Qualificado(qualificado) · Proposta(proposta) — today's values | site (coreLead), indicação, outbound | none (Fake) | org + license (core) |
| Digital agencies (orbity, Senseys) | `comercial`, `esteira` (CMS) | Novo(entrada) · Contato · Qualificado · Proposta(proposta) · Negociação · Fechado(ganho) + Perdido as lost status (orbity today) — absorb igig's "Agendar briefing(briefing)" as optional preset row? **No**: orbity's list is the canon; briefing becomes an activity type | meta_lead_ads, site, indicação, whatsapp | none at start | client + contract (`contracts`) |
| Psychoanalysis clinics (Mônica) | `leads` | Lead(entrada) · Atendimento · Negociação(proposta) · Fechado(ganho) — today's values | whatsapp, instagram, indicação, outro | `nosnolimiar-leads` | paciente (`clients.ensure_from_lead`, exists) |

### 2.4 SW-local code: lift vs stays real-estate spec

| SW code | Verdict | Destination |
|---|---|---|
| `modules/pipeline/configs.py`, `routers/boards.py`, `stage_gate.py`, `aceite.py`, `funil_eventos.py` | already on the funnel organ — **keep in SW** as RE preset/gates; move stage defaults from SQL fn (`060`) into `app/market/crm_preset.py` | SW L2 |
| `modules/leads/importer/*` (xlsx reader, shape detector, parsers, resolvers) | **lift** (generic) | seed `leads/intake/xlsx_import` |
| `modules/leads/services/meta_ingest_service.py`, `routers/meta_ingest.py` | **lift** | seed `leads/intake/meta_lead_ads` |
| `modules/leads/routers/sources.py`, `dimensions_service.py`, `analytics_service.py` | lift sources; analytics later (T-ANALYTICS) | seed / SW |
| `modules/portal_leads/*` (OLX, Imovelweb webhooks, receiver tokens, forward) | **stays RE**, refit as `LeadSource` adapters | SW L2 |
| `routers/julia_roteamento_router.py`, `leads/routers/corretores.py`, `services/julia_equipes_service.py` | **lift mechanics** (teams, strategy, capacity); corretor nouns/plantão = preset | seed `assignment` |
| `services/julia_opt_out_service.py`, `routers/julia_opt_outs_router.py`, `julia_solicitacoes_titular_service.py` | **lift** registry + gate + titular requests; Julia's decision logic stays in the agent | seed `consent` |
| `routers/agents_bridge_router.py`, `services/julia_lead_dispatcher.py`, `julia_lead_turn_service.py` | **lift the bridge** (transport + contract); Julia turn logic stays | seed `agent_hook` Real; Julia in agents/SW |
| `modules/card_hub/propostas/*` | **converge** on seed `quotes` (51's plan agrees) | seed quotes; RE fields as quote metadata |
| `services/identificadores*.py`, `whatsapp_identity.py`, `identidade_*` | **lift** dedupe primitives (phone canonical exists in `phone.ts`/primitives); CPF/RG extraction stays RE/Emissões | seed parties/identity |
| `modules/atendimento_blocos/*`, `modules/supervisao/*` (Monitor, SLA alerts) | **triage N=1**; generic shape (SLA per stage) — defer to T-SLA (second market asks) | SW L2 for now |
| `card_hub/contrato_gerador/*`, certidões, matrículas, partes, financiamento | **stays RE** (Emissões + ERP › Comercial) | SW L2 |
| `services/campanhas_*`, `portal_roi_service.py`, `julia_capi_service.py` | lift `campanha_id`/UTM/CAPI seam; ROI per portal stays RE | seed fields / SW |
| `email_marketing/*`, `mailchimp/*` | out of CRM-seed v1 (T-EMAIL: second market wants campaigns) | SW L2 |

### 2.5 Template + module-mount contract

- **Seed modules (BE)** `noctusai_seed/modules/crm.py::crm_module(preset: CrmPreset, *, schema, auth_dependency, get_admin_client, get_core_client, agent_hook=None, lead_sources=(), assignment=None) -> ModuleSpec` (group `crm`, organs: funnel boards from preset, leads, assignment, activities, consent, quotes-as-proposals; page_keys `crm_*`).
- **Seed modules (FE)** `@noctusai/lib/modules/crm.tsx::crmModule(preset, overrides?)` → `{navGroup, routes, pageKeys}`: CRM › Pessoas (Contatos, Clientes, Duplicados) · Vendas (Leads, Funil, Distribuição, Agendamentos, Atividades) · Configurações (Funil, Origens, Distribuição, Opt-outs). Markets extend with `extendModule` (SW adds CRM › Julia, Atendimento, E-mail from its nav map).
- **Overlay.** `templates/product-crm/overlay.json` generated from the module spec (organs, pages, `status_pagina` rows, `crm_preset.py` stub = the seed's generic preset Novo·Qualificado·Proposta·Ganho/Perdido). **`scaffold_product(overlay=[...])` must accept a list** (`["crm","erp","cms"]`), applied in `OrganSpec.requires` order — tooling-engineer slice (today single string, F7).
- **Permissions.** House roles only: org staff read, `is_org_admin` writes/settings, `platform_admin` for platform-tenancy boards (core). Module item `roles?` filters nav; the API is the authority (strict 401/403). Every route declares its access tier (`check_access_tier_*`); module routes are `org` tier; intake webhooks are `service`/`public` per allowlist (leads are already allowlisted).
- **Per-org module licensing** reserved (`license_key`), not built (T-LIC, owner Q3).

---

## 3 · CMS vertical seed (second build)

### 3.1 Organs

| Organ | State | Shape | Reuses / lifts from |
|---|---|---|---|
| **site + pages** | new (assembles existing FE organs) | `domain/cms/pages`: page rows = ordered typed blocks referencing the landing organs (Hero, FeatureGrid, Steps, Faq, CtaBand, LeadCaptureForm, ProductCatalogGrid…); published version immutable; per-org theme (`theme`, `productBrand`); SEO + `json-ld.ts` | `marketing/*`, erp `site_imoveis.py` |
| **editorial / blog** | exists, **unwired** | `domain/editorial` workflow + router factory + FE (`ReviewQueue`, `EditorialTimeline`, `VersionDiff` exist) | `projects/seed-editorial-workflow` |
| **content production board** | exists via pipeline | an `esteira` pipeline preset + card hub (Ideação…Postado) | SW `media_creation/esteira_config.py:49-55`, igig esteira/`pauta_router.py`, orbity `content_plans_router.py` — N=3 |
| **media library** | partial | org-prefixed storage, signed URLs only (zero public buckets — `check_storage_no_public_buckets`), variants; photo editing as a plugin | `photo_editing`, SW `media_service.py` |
| **listing / catalog feeds** | new seam | `FeedPublisher` Protocol + Fake + Real; generic Real adapters: sitemap.xml, RSS, Google Merchant/Meta catalog; **portal formats are market adapters** | erp `portais.py` (+ xml_feeds) |
| **forms** | exists | `LeadCaptureForm` → CRM `website_form` lead source | core `coreLead.ts` |
| **external portal** | new (owner Q1) | token-scoped external-party pages (owner/patient/member/client portal), hashed tokens (erp `050` portal token hash) | erp `portal_externo.py`, `portal_cliente.py`; therapy patient app; community `portal_*_router.py` — N≥3 |
| **content performance** | exists | readouts per post | `content_performance` |

### 3.2 CMS named seams

| Seam | Values / shape | Where a market differs |
|---|---|---|
| `block_types` | seed block set = landing organs; market adds blocks via registry | RE: `ListingGrid`, `ListingDetail` (Vista catalog); clinic: `Agenda`/`Atendimento`; agency: `Cases` |
| `content_types` | `page` · `post` · `listing` · `case` (open string) | RE: listing; agency: case/portfolio |
| `editorial_policy` | `editorial` transitions + grants (separation of duties) | who approves (clinic: Mônica only; agency: client approval step) |
| `feed_publisher` | Protocol + adapters | RE: ZAP/VivaReal (VRSync XML), OLX, Imovelweb — L2 SW |
| `content_board` | pipeline preset `esteira` | stage list per market (CoreStudio today) |
| `portal_audience` | `proprietario` · `paciente` · `membro` · `cliente` | which data each audience sees (market) |
| `domain` | per-org subdomain/custom domain via tunnel ingress + DNS tools | none in mechanics |
| `public_tier` | published pages/feeds are `public`; portals are token-scoped | **owner Q1** |

### 3.3 Module
`cms_module(preset)` → group `cms`: Site (Páginas, Tema, Domínio) · Blog · Mídia · Feeds/Portais · Portal externo · (SW extends with Edição de Fotos; CoreStudio stays its own group `corestudio` per `MODULE_GROUP_ORDER`, consuming the `esteira` board).

---

## 4 · ERP consolidation — unfreezing noctusai-51's held items one by one

Existing ERP seed (built 2026-10-14): parties, items, inventory, purchasing, contracts, quotes, finance (+ reminders, reconciliation, DRE, Livro Caixa, DAS/MEI/Simples) — `templates/product-erp`. 68/83 erp tables empty ⇒ port **functionality, not data**, except the few non-empty tables in 51's list.

| 51's frozen item | Placement | Seam / destination | Owner of the slice |
|---|---|---|---|
| **Locação** (contract registry, rent, readjustment) | L1 | seed `contracts` (`billing_model=recurring`, index readjustment seam — IGP-M/IPCA as `finance/params`), installments `real_estate.parcelamento` | seed (E1) then 51 consumes |
| **Vistorias** | L2 RE | SW `app/market/locacao/vistorias` on card_hub checklist + CMS media library | 51 (after E1, C-media optional) |
| **Chaves** | L2 RE | SW `market/locacao/chaves` (custody log = activities organ rows type `chave_retirada/devolucao`) | 51 after CRM activities |
| **Manutenção** | L2 RE over L1 | activities (type `manutencao`) + supplier `parties` + payable in `finance`; promote to seed `work_orders` at T-WO (second market) | 51 after activities |
| **Seguros** | L2 RE | contract attachment + recurring finance entry | 51 |
| **Campo** | L1 via CRM | activities type `campo` + assignment | 51 consumes CRM |
| **Filiais** | L2 now, seam named | nullable `org_unit_id` convention on cards/leads/activities, assignment strategy `by_unit`; promote to L0 org setting at N=2 (T-UNIT) | 51 (decl.) + seed adds the column convention to assignment/activities |
| **Comissões** | L1 mechanism + L2 policy | seed `finance.commissions`: split a receivable into payables per beneficiary (party) by a `CommissionPolicy` hook; RE policy (corretor/captador/imobiliária/parceiro %) in SW preset | seed (E2) + 51 policy |
| **Banco** | drop ERP version | seed finance OFX + reconciliation (exists) | 51 (nav only) |
| **Impostos** | L1 exists | seed finance params / DAS / Simples views | 51 (nav only) |
| **DIMOB** | L2 RE | SW `market/fiscal/dimob` export **data** over contracts+finance (seed rule: export data, files are the accountant's); **accountant agent review before build** | 51 + `accountant` advisor |
| **CMS site / portais / xml_feeds** | L1 CMS + L2 adapters | CMS `pages`/`feed_publisher`; ZAP/VivaReal/OLX/Imovelweb adapters in SW | seed (CMS wave) then 51 |
| **Portal proprietário** | L1 CMS `external portal` | audience `proprietario` | seed after owner Q1 |
| **Metas / gamificação** | L1 exists | `domain/metas` + `engagement` (+ `erp-gamificacao-seed-lift-2026-09`) — mount in ERP › Metas e Desempenho | 51 (unfrozen now) |
| **CRM propostas** | L1 | seed `quotes` (proposal_accept seam) | seed C11 then 51 |
| **CRM funnel stages** | L1 mechanics + L2 preset | ADR-2; SW preset = today's stage values | seed C3 then 51 |
| BI / Matching IA | L2 RE | SW painel + `real_estate.matching` (exists) | 51 |
| Certidões / Matrículas / Agentes financeiros | L2 RE | stays SW (Emissões) | 51 |

**Unfreeze order for 51:** now → metas/gamificação, banco/impostos (nav-only), BI/matching; after C3 → funnel presets; after E1 → locação + seguros; after CRM activities/assignment → chaves, manutenção, campo, filiais(seam); after E2 → comissões; after accountant review → DIMOB; after CMS wave + Q1 → site/portais/feeds, portal proprietário.

---

## 5 · Canon / absorption map

### 5.1 Modules per canon

> **Owner correction 2026-11-08 — what "erp" means here.** The only product absorbed into SW is **erp-imobiliario** (its database schema happens to be named `erp`; the "erp schema drop" in 51's S8 is THAT schema). **`templates/product-erp/` is the ERP product TEMPLATE and STAYS** — never absorbed, never erased; it is the L1 ERP vertical seed every market ERP is scaffolded from. There is no `products/erp` and no `erp` row in `public.products`. Owner: "erp que erp é esse? só me lembro do erp-imob, e o template de produto erp. esse erp deve ficar."

| Canon | Market | CRM | ERP | CMS | Other groups | Absorbs |
|---|---|---|---|---|---|---|
| **social-wiring** (live) | real estate | ✓ (+Julia, Atendimento, E-mail ext.) | ✓ (+ locação/fiscal RE) | ✓ (+Edição de Fotos, RE feeds) | Redes Sociais, CoreStudio, Banib(stub), Emissões, Integrações, Configurações | **erp-imobiliario** |
| **orbity** (asleep → wake, owner go) | digital agencies | ✓ | ✓ (contracts, finance, quotes) | ✓ (esteira, content plans, client portal) | Redes Sociais (Meta Ads), Integrações | **igig** |
| **nosnolimiar** (live; rename = F2) | psychoanalysis clinics | ✓ (leads-lite → converged) | ✓ (finance mounted, clients/sessions) | ✓ (Nós no Limiar content, blog, member portal) | Comunidade (memberships, WhatsApp groups), Atendimento clínico | **therapy-platform**, **community** (+ content from `nos-no-limiar/` repo) |
| **core** (live) | SaaS (noc's own business) | ✓ (`funil_noc`, platform tenancy) | ✓ (finance/contracts for noc billing — later) | ✓ (noctusai.com landing → CMS pages) | Admin | — |

### 5.2 "Absorb then erase" ladder (per absorbed product)

| Step | What | Gate | Tool / skill |
|---|---|---|---|
| A0 Measure | prod row counts per table, storage objects per bucket, users/orgs, public fns referencing the schema, inbound webhooks/DNS/tunnel hosts, open findings | — | Supabase SELECT-only; `noctus.dev.product_scope_report`, `refs`, `findings_ledger open_for_scope` |
| A1 Salvage knowledge | product `projects/`, roadmaps, READMEs, ideas → canon's roadmap + KB; branches → salvage pointers | — | skill `noc-archive-absorb`; `salvage_before_delete`; `archive` (learn-before-archive gate) |
| A2 Capability map | every router/page → seed organ · canon L2 · duplicate (drop) · dead (drop); "salvage the idea behind bad code" | architect review | skill `noc-absorb-product` (learning-absorption refinement) |
| A3 Build in canon | seed-first; canon consumes | normal CI | `task_branch` |
| A4 Data | owner decides copy-vs-discard per non-empty table; copy = canon migration (expand) + verify counts | **owner per table** | `scaffold_migration`, `migration_replay`, `migrate_product` |
| A5 Decouple | public fns, triggers, RLS helpers, webhooks, OAuth redirect URIs pointing at the product | CI + `verify_db_guards` | (51's S6 is this for erp) |
| A6 Retire surfaces | `delete_product` + compose.prod, tunnel ingress/DNS, CI matrix, dependabot, cors registry, build-and-push, LANDSCAPE, findings → `accepted` (erased) | **owner go** | `delete_product`, `tunnel_config`, `cloudflare_dns`, `refresh_ci_matrix_coverage`, `refresh_dependabot_coverage`, `refresh_build_scope` |
| A7 Drop data | `pg_dump` of the schema kept off-repo (retention N days) → DROP SCHEMA + buckets | **owner go** (explicit, per schema) | `vps_exec_sql`/Management API; never automatic |

### 5.3 Per-absorption specifics

| Absorption | Known data | Value to carry | Special risk |
|---|---|---|---|
| erp-imobiliario → SW | measured (51): 15/83 tables non-empty; `erp-certidoes` 102 objects; hidden coupling `handle_new_user`, `assign_default_corretor_role`, `has_role` (50 RLS policies) | ERP-only modules per § 4 | A5 must land before A7 (51's Q5) |
| igig → orbity | **unmeasured** | `distribuicao` (→ seed assignment, lift base), esteira/pauta (→ CMS board), orçamento-por-email, marca, custos, relatórios | both asleep: orbity must be woken first (owner go); igig's lifted organs (quotes, contracts, pipeline) already in seed |
| therapy-platform → nosnolimiar | **unmeasured**; 162 open findings | anamnese, evolution notes, treatment plans, homework, mood/journals, LiveKit sessions, availability, wallets/payments, crisis protocol, consents | **clinical records**: if any real patient data exists, CFP Res. 001/2009 requires prontuário retention (≥5 yrs) and LGPD sensitive-data rules ⇒ A7 erase may be unlawful; `legal-advisor` + `compliance-reviewer` before A4/A7 (owner Q2) |
| community → nosnolimiar | scaffolded 2026-09-16, "domain modules planned, not built" (LANDSCAPE); `projects/ninho-vazio`; roadmap `community-modules-1-3-2026-09.md` | ideas + projects: tiered membership (Stripe+Asaas), member portal, WhatsApp group management/transmissões | mostly A1 (knowledge), little A4 |
| nos-no-limiar repo → nosnolimiar CMS | content KB (voz, tese, obra, hooks, pipeline sqlite) | becomes the clinic canon's editorial content + agent context | it is a sibling repo, not a product: absorb content, then the owner decides whether the repo is archived |

---

## 6 · Ordered slices

Owners: **SEED** = the requesting session (seed layer, dispatching specialists) · **S51** = noctusai-51 (SW consumer + erp absorption) · **TOOL** = tooling-engineer dispatch · later **ORB** / **MON** sessions. Collision class per `branching-dispatch.md`: C1 disjoint · C2 additive · C3 sequence.

| # | Slice | Owner | Paths (collision zone) | Depends on | Parallel with | Owner go? |
|---|---|---|---|---|---|---|
| W0-1 | KB: `vertical-seed.md` §2 CRM/CMS seams + "market product = module composition" revision; roadmap file | SEED (docs) | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/architect/vertical-seed.md`, `project-history/roadmaps/crm-cms-erp-vertical-seeds-2026-11.md`, `INDEX.md` | — | all | no |
| W0-2 | Land `mq/seed-sidebar-module-groups` | queue | — | — | — | no |
| W1-1 | BE `ModuleSpec` + `create_product_app(modules=)` | SEED → backend-engineer | `seed/framework/backend/noctusai_seed/modules/`, app factory | — | W1-2..W1-5 (C1) | no |
| W1-2 | FE `defineModule`/`extendModule` + routes + page keys | SEED → frontend-engineer | `seed/lib/frontend/src/modules/` | W0-2 | W1-1 (contract-first: freeze the `ModuleSpec`↔`defineModule` page-key contract first) | no |
| W1-3 | Pipeline presets + canonical roles + role-no-op | SEED → backend-engineer | `domain/pipeline/presets.py`, `config.py` | — | W1-1,2,4,5 | no |
| W1-4 | `assignment` organ (lift igig base) BE+FE | SEED → backend + frontend | `domain/assignment/`, `seed/lib/frontend/src/assignment/` | — | C1 | no |
| W1-5 | `activities` organ BE+FE | SEED → backend + frontend | `domain/activities/`, FE `activities/` | — | C1 | no |
| W1-6 | Keepers `check_module_page_status_rows`, `check_stage_list_not_in_code` (warn-first) | TOOL | `mcp/noctusai/tools/compliance*` | W1-1, W1-3 | W2 | no |
| W2-1 | `consent` organ + `OutboundGate` (lift SW logic, seed copy) | SEED → backend + security review | `domain/consent/`, FE `consent/` | — | W2-2,3 | no |
| W2-2 | Lead intake seam + xlsx/meta/website adapters | SEED → integrations-engineer | `domain/leads/intake/`, `integrations/meta` | — | C1 w/ W2-1 | no |
| W2-3 | Agent hook seam + AgentsBridge Real | SEED → ai-engineer | `domain/leads/agent_hook.py` | — | C1 | no |
| W2-4 | Leads-lite → stage rows (expand) + Nós no Limiar pilot | SEED → backend; MON consumer | `domain/leads/*`, `products/nosnolimiar/backend/app/crm.py` | W1-3 | W2-1..3 (C2 on `domain/leads` with W2-2/W2-3: sequence W2-4 last in `leads/`) | no |
| W2-5 | Quotes ↔ funnel accept binding | SEED → backend | `domain/quotes/handler.py`, `funnel/` actions | W1-3 | C1 | no |
| W2-6 | `crm_module()` BE + `crmModule()` FE + `templates/product-crm` + `scaffold_product(overlay=list)` | SEED + TOOL | `noctusai_seed/modules/crm.py`, FE `modules/crm.tsx`, `templates/product-crm/`, `mcp/.../scaffold*` | W1-*, W2-1..5 | — | no |
| W3-S1 | SW: nav → module manifests (CRM/ERP/CMS groups per nav map) | S51 | SW `frontend/src/nav/*`, `App.tsx` | W1-2, protected branches landed, `feat/jl-s10a-sw-agente-card` landed | W3-C1, W3-M1 | no |
| W3-S2 | SW: stage SQL fn → `crm_preset.py` (expand; fn kept) | S51 | SW `app/market/crm_preset.py`, pipeline module | W1-3 | — | no |
| W3-S3 | SW: opt-outs → consent; roteamento → assignment; propostas → quotes | S51 | SW services/routers listed § 2.4 | W2-1, W1-4, W2-5 | — | no |
| W3-S4 | SW: ERP unfreeze wave A (metas/gamif., banco/impostos nav, BI/matching) | S51 | SW ERP pages | W3-S1 | now-ish | no |
| W3-C1 | core: `funil_noc` → preset; core CRM on `crmModule` | SEED (core) | `products/core/backend/app/noc_funnel.py`, core admin nav | W1-3, W2-6 | W3-S* | no |
| W3-M1 | nosnolimiar: CRM module mount, stage rows live | MON | `products/nosnolimiar/*` | W2-4, W2-6, **Q4 (rename)** | — | no |
| W4-1 | ERP seed E1 locação (contracts recurring + readjustment index) | SEED | `domain/contracts`, `finance/params` | — | W4-2 | no |
| W4-2 | ERP seed E2 commissions split | SEED + accountant advisor | `domain/finance/commissions.py` | — | W4-1 | no |
| W4-S | SW: locação/seguros/chaves/manutenção/campo/filiais/comissões/DIMOB | S51 | SW `app/market/locacao`, `market/fiscal` | W4-1/2, CRM activities, accountant review | — | no |
| W5-1 | CMS: pages organ + editorial router + FE + media library + `FeedPublisher` | SEED | `domain/cms/`, `domain/editorial/router`, FE `cms/` | W1-1/2 | W4 | no |
| W5-2 | CMS: external portal organ | SEED + security | `domain/cms/portal` | **Q1** | — | Q1 |
| W5-S | SW CMS: site, portais RE adapters, portal proprietário, feeds | S51 | SW `app/market/feeds` | W5-1, W5-2 | — | no |
| W6-E | erp absorption A5–A7 (51's S6–S8) | S51 | core public fns, retirement surfaces | W4-S, W5-S done for what One uses | — | **A6, A7 owner go** |
| W7-O0 | Wake orbity (ativo=true, deploy_scope=dev) | owner via core admin | catalog | — | — | **owner go** |
| W7-O | igig → orbity: A0–A3; orbity `lead_stages` → pipeline rows (ADR-2 M/C) | ORB | `products/orbity/*` | W2-6, W7-O0 | W8 | A4 per table, A6/A7 owner go |
| W8-M | therapy-platform + community + nos-no-limiar → nosnolimiar: A0–A3 | MON + legal-advisor | `products/nosnolimiar/*` | W3-M1, **Q2**, Q4 | W7 | A4/A6/A7 owner go |
| W9 | Contract phase: drop leads-lite literal path, SW SQL stage fn, orbity `lead_stages`; keepers → blocking | SEED | seed + canon migrations | all consumers migrated | — | no (schema drops of live tables announced) |

**Parallel waves:** W1 is five C1 slices at once (W1-1..W1-5) once the page-key contract (W1-1↔W1-2) is frozen; W2-1/2/3/5 parallel, W2-4 serialized last on `domain/leads`; S51 runs W3-S4 immediately (no seed dependency) and W3-S1 once W1-2 lands; W4 (ERP) and W5 (CMS) parallel; W7 and W8 parallel (different products).

**Do not touch:** `feat/julia-v3-sw-catalogo`, `feat/sw-imovel-overlay-crud` (owner rule); SW `main.py`, `config.py`, `lifespan.py`, `imovel_hub/*`, `Imoveis.tsx`, `ImovelDetalhes.tsx`, `Settings.tsx`, SW migrations 314–317, 320 until they land (51's collision list).

---

## 7 · KB changes (drafts ready in this folder)

- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/architect/vertical-seed.md`: insert `VERTICAL-SEED-PATCH.md` (new § 1a "market product = composition of vertical modules", § 2 CRM seams + CMS seams tables, § "Mounting a module"). Keep ERP table; add the ERP market-spec rows from § 4.
- `project-history/roadmaps/crm-cms-erp-vertical-seeds-2026-11.md`: `ROADMAP.md` in this folder (noc-roadmap template sections).
- After W1-1/W1-2 land: `KB § GUIDES/new-product.md § Market products from a vertical seed` → "compose modules"; `products-consume-canonical-organs.md` lists the new organs; `02-LANDSCAPE` notes per canon (with the absorption status).

---

## 8 · Owner questions (max 4, each with a recommendation)

1. **Public surfaces for CMS and portals.** The `public` tier is a closed allowlist (landing, auth, checkout, legal, leads). CMS-published sites/feeds and external portals (proprietário, paciente, membro, cliente) need a place. **Recommend:** add `site` (published pages + feeds, read-only, anonymous) to the allowlist, and model portals as token-scoped external-party routes (hashed magic-link tokens, erp 050 shape) — not anonymous. This also answers 51's Q1.
2. **therapy-platform data before "erase for good".** If its prod schema holds any real patient records, clinical-record retention (CFP Res. 001/2009, ≥5 years) and LGPD sensitive-data rules may forbid deletion. **Recommend:** measure first (A0); if real records exist, migrate them into Nós no Limiar's schema under the same retention and erase only the code; legal-advisor signs off before A7.
3. **Who switches modules on — product or org?** **Recommend:** per product now (all orgs of a canon get its modules, pages gated by `status_pagina`); reserve `ModuleSpec.license_key` and turn on per-org licensing via the core license gate the first time a client wants a subset or a priced tier.
4. **Nós no Limiar's slug before the absorptions.** Owner 2026-11-08: finish the rename BEFORE any absorption (done in the repo by `feat/nosnolimiar-rename-v3`; the prod cutover window is the owner's call, runbook above). Absorbing therapy-platform + community into the product happens under the new slug only.

(Also needs an explicit owner go, no question needed: waking orbity W7-O0; each A6/A7 step; each A4 copy-vs-discard.)
