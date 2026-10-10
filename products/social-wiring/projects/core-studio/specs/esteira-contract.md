# Esteira de Reels + absorption of "Criação de mídia" — build contract v1 (2026-10-10)

> Authored by the tech-lead session (noc6) on 2026-10-10 from two owner requests:
>
> 1. *"make sure the prompt on criacao de midia is absorbed into the corestudio's app in-house. if so
>    and we wont lose any content/structure/functionality, please delete the criacao de midia page,
>    remove the sidebar nav link and rename the group 'criacao de midia' to 'CoreStudio'."*
> 2. *"i want an Esteira page just like we have on igig, but use the sw funnel and card's structure
>    for this kanban. we need a 'reel' object on the db representing the post we're gonna build […]
>    headline and roteiro must be fks […] both nested inside post. stages initially are ideação,
>    headline + roteiro, gravação, edição, pronto, postado, bloqueado/cancelado. posts must be
>    attached to brands (marcas) […]"*
>
> §A is the absorption audit (request 1). §0–§10 are the Esteira build contract (request 2) and
> the slices that carry out §A's moves. The shape follows `geracao-contract.md`. **§11 lists every
> tech-lead default the owner still has to validate; §12 lists the owner questions.**

Verified on `origin/dev` @ `a259fd139` and against prod (`social_wiring`, read-only queries,
2026-10-10).

---

## A · Absorption audit — can the "Criação de mídia" page be deleted?

### A.1 Verdict

**Not yet.** The Método Audience prompts are absorbed, but deleting the page today would lose
three things that are live in production:

1. **Branding / Kits de marca.** 5 kits linked to marcas plus 1 template, 26 components and 17
   references, across 4 orgs.
2. **Carousel and image generation.** That is storyboard → image prompts → render (raster/SVG)
   → copy → score. 6 drafts exist in one org.
3. **Production visibility.** The legacy page is `status_pagina='producao'`. Every CoreStudio page
   is `desenvolvimento`, so it is owner-only.

Two small FE moves (A-1, A-2 in §A.5) remove all three losses. After them the legacy page, its
nav link and its route can go, and the group is renamed **CoreStudio**. No backend code or table
is deleted (§A.4).

### A.2 Inventory and where each item lives after the moves

**Backend** (`backend/app/modules/media_creation/`). Important: this module **also holds every
CoreStudio feature** (Geração, Pesquisa, Cérebro, Biblioteca). Only the legacy slice is
inventoried here.

| # | Capability | Legacy code | Absorbed by CoreStudio? | After this contract |
|---|---|---|---|---|
| 1 | **Método Audience** (`METODO_TRIGGERS`, `_STRUCTURE`, `_TEMPLATES` ×32, `_QUALITY`, `_AUDIENCE`) | `prompts/methodology.py` | **Yes, by import (not copy).** See §A.3 | Unchanged; it is the single source |
| 2 | Storyboard (slides + methodology roles) | `prompts/storyboard.py`, `GenerationService.generate_storyboard`, `POST /posts/{id}/generate/storyboard` | No. CoreStudio produces text only | Kept, served by the **Carrosséis** page (A-2) |
| 3 | Image prompts per slide (Nano Banana / Galileo / Midjourney) | `prompts/image_prompts.py`, `generate_image_prompts` | No | Kept (Carrosséis) |
| 4 | Render: raster (Gemini, Fake fallback) and brand-locked SVG | `generation_service.render_post`, `design/{tokens,svg_slides}.py` | No | Kept (Carrosséis) |
| 5 | Copy: caption, hashtags, alt text, first comment | `prompts/copy.py`, `generate_copy` | No | Kept (Carrosséis). **Its reel version is absorbed into the Esteira card** (§6.4, `legenda`) |
| 6 | Score: 8-criteria Método Audience audit | `prompts/score.py`, `score_post` | No | Kept (Carrosséis). An Esteira roteiro audit is phase 2 (§12 Q6) |
| 7 | Publish to Instagram/Facebook | `services/publish_service.py`, `POST /posts/{id}/publish` | No | **Not lost.** The FE never calls it, and it 422s `requires_app_review` without the Meta scope. Kept as-is for Esteira phase 2 (§12 Q5) |
| 8 | Scheduling | — | — | **Does not exist** (no scheduled-time field, no job). Nothing to lose. The Esteira adds a planned posting date (§2.3) |
| 9 | Brand kits CRUD | `routers/brand_kits.py`, `brand_kit_service.py` | No | Kept. Used by Carrosséis' Novo post and by Pesquisa's `mc_post` source |
| 10 | Branding: tokens, brand book, components, assets, design-system import | `routers/branding.py`, `branding_service.py`, `branding/` | No | Kept. Served by the new **Branding** page under CoreStudio › Configurações (A-1) |
| 11 | References per kit | `routers/references.py`, `reference_service.py` | No | Kept (Branding panel) |
| 12 | Posts CRUD | `routers/posts.py`, `post_service.py` | No (the Esteira is a new object, §2) | Kept (Carrosséis) |

**Data in prod** (counted 2026-10-10). **Nothing is dropped.**

| Table | Rows | Notes |
|---|---:|---|
| `mc_posts` | 6 | All `draft`, none published. 4 `reels` + 2 `carousel`, one org (`fd169d29…`), last touched 2026-07-27 |
| `mc_post_slides` | 26 | |
| `mc_brand_kits` | 6 | 5 linked to marcas (4 orgs), 1 `is_template`. Last update 2026-10-10, so in active use |
| `mc_brand_components` / `mc_brand_references` | 26 / 17 | |
| `mc_brand_owners_legacy` | 0 | Dead since 007/046. Hygiene drop is **out of scope** here (`NOC-REMEDIATE[mc-brand-owners-legacy]`, filed by BE-0 in the 241 header) |

**Live dependencies of CoreStudio on the legacy tables.** These are why the BE stays:

- `pesquisa_fontes.py` (Extrair Pesquisa) reads `mc_posts`, `mc_post_slides` and `mc_brand_kits`.
  - It serves the source "Posts criados" (`kind="mc_post"`, registered in `FONTES`).
  - It also serves the caption join of the Instagram source (`_published_posts`, `_mc_text_parts`).
  - The kind string also appears in `pesquisa_wave2_constants.py`, `schemas/pesquisa_extracao.py`, `hooks/usePesquisa*.ts` and `pages/ExtrairPesquisa.tsx`.
- `prompts/__init__.py` re-exports the legacy prompts next to `chat_*`. This is harmless and stays.

**Frontend.**

- `pages/MediaCreation.tsx` (792 lines) has 3 tabs:
  - **Biblioteca** (`LibraryTab`): posts plus the detail view with generation, render and score.
  - **Novo post** (`ComposeTab`): kit, idea, format, tone.
  - **Branding** (`BrandingTab` from `components/branding/**`).
- Hooks: `hooks/useMediaCreation.ts` and `hooks/useBranding.ts`.
- There is no separate "Kits de marca" tab. Kits are the Novo post dropdown plus the Branding tab.
- Route `/media-creation` (`App.tsx:587`). Nav item `App.tsx:253` (`route: "media_creation"`) plus its fallback twin at `:453`.
- The group `key:"media-creation"`, `label:"Criação de mídia"` is at `App.tsx:248–300` and `:448–500`, and the header comment at `App.tsx:10`.
- `status_pagina.nome_pagina='media_creation'` is `producao`.

### A.3 Método Audience: how the new prompts use it

| Prompt (CoreStudio) | TRIGGERS | STRUCTURE | TEMPLATES | QUALITY | Verdict |
|---|---|---|---|---|---|
| `headline_geracao.py` (`headline-v1-draft`) | verbatim import | — (headlines have no beats) | parsed into `TEMPLATES_METODO`; one template is injected per call as the empty-library fallback (`template_blob`, by criatividade) | rules 1–5 imported (regex-filtered); rule 6 restated; rule 7's anonymity clause dropped on purpose (Núcleo = the marca's own identity, geracao D1) | absorbed |
| `roteiro_geracao.py` (`roteiro-v1-draft`) | full `METODO_AUDIENCE` | full, plus its own 9-beat order | full | full | absorbed (see drift 1) |
| `roteiro_perguntas.py` | — | — | — | — | names the method in prose only; acceptable for a questions-only stage |
| `chat_headline.py` | verbatim | verbatim | — | paraphrased "no invented data" | absorbed for its job |
| `chat_roteiro.py` | — | verbatim | — | paraphrased | absorbed for its job |
| `perfil_service.py` | parses the 7 formulas for `/taxonomias` | | | | absorbed |

Two drifts to fix on contact. Both are **owner decisions, not blockers**:

1. **Beat order.** `roteiro_geracao.py` imports `METODO_STRUCTURE` (which says the CTA is last)
   and then gives its own 9-beat order: Headline → CTA salvar → … → CTA compartilhar →
   Apresentação Magnética. That splits the CTA in two and adds a closing beat.
   - The model receives two orders, which is a contradiction.
   - BE-2 adds one explicit line to `roteiro_geracao.py`: "a ordem abaixo substitui a ESTRUTURA DO MÉTODO para roteiros de vídeo".
   - It bumps `PROMPT_VERSAO` to `roteiro-v1.1-draft`.
   - The owner validates the 9-beat order (§12 Q7).
2. **The legacy reel storyboard is slide-based.** It has a `reels` format with `capa…cta` roles
   per slide. The new roteiro is a spoken script. They are different artefacts, and both are
   kept: the reel *script* lives in the Esteira, and the *slide* reel stays in Carrosséis.

**Conclusion on request 1's precondition.** The prompt is absorbed: the Método Audience text is
imported, not duplicated, by every CoreStudio generator. The only prompts that are *not* absorbed
are the legacy page's own carousel prompts (storyboard, image prompts, copy, score). They stay
alive behind the Carrosséis page (A-2), and copy is also reborn for reels as the Esteira `legenda`
(§6.4).

### A.4 Recommendation: move / keep / delete

| Item | Action |
|---|---|
| `MediaCreation.tsx` | **Split, then delete.** `LibraryTab` + `ComposeTab` → `pages/geracao/Carrosseis.tsx`; `BrandingTab` → `pages/geracao/Branding.tsx`; delete the file |
| Nav item "Criação de mídia" (`/media-creation`) | **Delete** (both nav configs) |
| Route `/media-creation` | **Redirect** to `/media-creation/carrosseis`, and `?tab=brand` to `/media-creation/branding`. Old bookmarks keep working |
| Group label "Criação de mídia" | **Rename to "CoreStudio"** (both configs plus the header comment). The key stays `media-creation`, so no URL changes |
| `status_pagina` | **New keys** `media-creation-carrosseis` and `media-creation-branding` as **`producao`**, because they carry an existing production feature and must stay visible to non-dev users. `media_creation` is set to `desativado` (kept, never deleted: history) |
| All legacy BE routers, services, prompts, `branding/`, `design/` | **Keep** |
| All `mc_*` tables, bucket `social-wiring-branding` | **Keep** |
| Legacy tests | **Keep**. A new FE test per new page (§8) |

### A.5 Moves, as slices (all in §10)

- **A-1 Branding page.** `pages/geracao/Branding.tsx` hosts the existing `BrandingTab` unchanged,
  with the CoreStudio page header "Branding" — "Identidade visual por marca".
  - Nav: CoreStudio › Configurações › **Branding** (after Meu Perfil).
- **A-2 Carrosséis page.** `pages/geracao/Carrosseis.tsx` keeps the Biblioteca and Novo post tabs
  as they are today, titled "Carrosséis e posts de imagem".
  - Its kit dropdown gets a link "Gerenciar branding →" to `/media-creation/branding`.
  - Nav: CoreStudio › **Carrosséis** (after Esteira).
- **A-3 Delete and rename** (FE-Z, tech-lead): routes, redirect, nav, rename, and the delete of `MediaCreation.tsx`.

All three ride the 241 migration for their `status_pagina` rows. A-1 and A-2 are one FE slice
(FE-A). A-3 is part of FE-Z.

---

## 0 · Before you dispatch: what the code says

1. **The migration number is 241.** `noctus.dev.next_migration_number` says 241. The last file is
   `240_spawn_funil_card_sem_descarte_silencioso.sql`, and 236/237 were retracted.
   - There is **one migration**, `241_cs_esteira.sql`, written by BE-0.
   - Re-run `scaffold_migration` at integrate and renumber if another session took 241. Never hand-edit a number after integrate.
2. **There is no `kanban_pos_fracionario` column.** That is the name of migration 087, which turned
   `kanban_pos` into `numeric`. The Esteira card uses `kanban_pos numeric`, and the server
   computes positions with the seed `ordering.position_for_index` / `position_on_top`. The client
   sends only an integer `novo_indice`.
3. **SW's funnel IS the seed pipeline organ.**
   - Backend: `noctusai_lib.domain.pipeline` (`PipelineConfig`, `move_card`, `group_into_colunas`, `pipeline_stages_router`).
   - Frontend: `@noctusai/lib/components` (`PipelineBoard` over `KanbanBoard`, `createPipelineHooks`, `MotivoMoveDialog`).
   - igig's Esteira runs on the same organ.
   - **"Use SW's funnel structure" therefore means one more `PipelineConfig` on the shared `social_wiring.pipeline_stages` and `pipeline_movimentos` tables**, not a fork.
4. **The pipeline CHECKs must widen.** In prod:
   - `pipeline_stages_pipeline_check` and `pipeline_movimentos_pipeline_check` are `IN ('funil','processos_venda')`;
   - `pipeline_stages_papel_check` is `IN ('proposta_aceite','final')`.
   - 241 drops and re-adds them by name (§2.1). `PipelineConfig.stage_roles` documents that the DB CHECK must match the API tuple.
5. **SW's card structure IS the seed card hub.**
   - Backend: `noctusai_lib.domain.card_hub` (`CardHubConfig`, `card_hub_routers`, `card_hub_migration`).
   - Frontend: `CardHubDialog`, `CardSidebarNav`, `Timeline`, `ChecklistsSection`, `MembrosPopover`, `EtiquetasPopover`, `createCardHubHooks`.
   - SW's `ClienteCardDialog` is its consumer.
   - **SW has no single assignee column.** Assignees are the hub's `membros` link table, and due dates are the hub's "Datas" columns on the entity row (`data_inicio`, `data_entrega`, `entrega_concluida`, `lembrete_minutos_antes`, `recorrencia`).
   - The Esteira card adopts the card hub whole, generated by `card_hub_migration` exactly as igig's `019_card_hub.sql` was. So the post gets SW's card structure for free: comments, checklists, labels, members, dates, reminders, attachments and timeline.
6. **The card hub needs a member table.**
   - `MemberSource` must point at a `social_wiring` table with `id, org_id, nome, cor`.
   - SW's only one is `lead_corretores`, the real-estate brokers. That is the wrong domain for a content team.
   - 241 creates **`cs_equipe`**: the org's content team (videomaker, editor, roteirista, …), with an optional `user_id`, because freelancers are often not platform users. This is default D5.
7. **Default stages: the lazy seeding is N=2, so lift it.**
   - igig seeds its board defaults lazily in Python (`app/pipelines.py :: garantir_etapas_padrao`, first board read).
   - SW's funil does it in SQL (`ensure_default_pipeline_stages`, 037).
   - The Esteira would be the second Python copy, so **S0 lifts `garantir_etapas_padrao` into the seed** (`noctusai_lib.domain.pipeline.defaults`: `StageDefault`, `ensure_default_stages`) and moves igig onto it with no behaviour change.
8. **`PipelineBoard` always renders `formatValue(valorTotal)`.** igig passes `formatValue={() => ""}`, which leaves an empty `<p>` under every column header. The Esteira would be the second board with no money.
   - S0b adds `showValue?: boolean` (default `true`).
   - igig and the Esteira pass `false`.
   - `PipelineConfig.value_field` stays required; the Esteira passes `value_of=lambda _: 0` to `group_into_colunas`.
9. **The headlines and roteiros already carry the marca.** Both `cs_headlines.marca_id` and `cs_roteiros.marca_id` exist (229).
   - The post→headline and post→roteiro FKs are **composite on `(id, marca_id)`**, so a post can never point at another marca's headline. That needs `UNIQUE (id, marca_id)` on both tables.
   - Prod is **Postgres 17.6**, so `ON DELETE SET NULL (headline_id)` (a column-list SET NULL, PG ≥ 15) is available. It nulls only the FK column, never `marca_id`.
10. **The target account.** `integration_accounts.marca_id` exists. The post carries an optional
    `conta_id` (the marca's Instagram account to publish on), which the service checks belongs to
    the same marca. When it is absent, the UI shows the marca's default IG account.
11. **RLS helpers.**
    - The 229 tables use `public.current_org_id_for('social_wiring')`. `cs_equipe` and `cs_posts` follow 229.
    - The card hub section is **generated** and uses `public.current_org_id()` with service-role writes, like igig 019. Both helpers exist in prod.
    - The backend always uses the service-role client plus explicit `.eq("org_id", …)`, as SW pipeline tests assert.

---

## 1 · Scope and decisions encoded

### 1.1 Pages

| # | Page | Route | `status_pagina` | Sidebar |
|---|---|---|---|---|
| E1 | **Esteira** (reels kanban) | `/media-creation/esteira` (`?marca=`, `?post=`, `?busca=`) | `media-creation-esteira` (**desenvolvimento**) | CoreStudio › **Esteira** (2nd item, after Dashboard) |
| — | Post card (dialog, not a page) | `?post=<id>` deep link | — | — |
| A-1 | **Branding** | `/media-creation/branding` | `media-creation-branding` (**producao**) | CoreStudio › Configurações › Branding |
| A-2 | **Carrosséis** | `/media-creation/carrosseis` | `media-creation-carrosseis` (**producao**) | CoreStudio › Carrosséis (after Esteira) |

**CoreStudio group order after FE-Z** (both nav configs):
- items: Dashboard · **Esteira** · **Carrosséis** · Criar Headlines e Roteiros · Biblioteca
- groups:
  - Pesquisa
  - Segundo Cérebro
  - Configurações: Meu Perfil · **Branding** · Minha Biblioteca · Treinamentos · Roteiros · group Headlines

### 1.2 Owner decisions this contract encodes

- A `reel` object (`cs_posts`) is the kanban card. It is attached to a **marca** (required), which gives per-client filtering and the target account.
- `headline_id` → `cs_headlines` and `roteiro_id` → `cs_roteiros` are FKs **on the post** ("both nested inside post").
- Initial stages, in order: **Ideação · Headline + roteiro · Gravação · Edição · Pronto · Postado · Bloqueado/cancelado**.
- UX reference: igig's Esteira (board, marca filter in the URL, card face, detail dialog, move rules with reason). Structure: SW's funnel and card (seed pipeline + seed card hub), reused, never forked.
- The headline and roteiro mechanisms move **inside the post card**, reusing the existing generation, `EditarHeadlineModal` and `RoteiroAvancadoModal`.

### 1.3 Not in v1 (named destinations)

- Publishing from the card. `PublishService` exists but needs Meta App Review (§12 Q5), `NOC-REMEDIATE[esteira-publicar]`.
- Video file storage. Raw footage and edits are links (Drive/Frame.io) in the card, because the hub's document cap is 25 MB (§2.4).
- Roteiro score/audit (§12 Q6).
- Carrossel and story formats as Esteira cards. `formato` is a CHECK with only `reel`, so it can be extended later.
- Backfill of the 4 legacy `reels` drafts (§12 Q8).

---

## 2 · Data — migration `241_cs_esteira.sql` (schema `social_wiring`, one file, BE-0)

The migration is forward-only and idempotent. Its guard block requires 034, 087, 224 and 229 to be
applied, checked by the existence of `pipeline_stages`, `cs_headlines` and `cs_roteiros`. Its header
names the GuardProbe tuple `_SW_241_PROBES` (§2.6).

### 2.1 Pipeline widening (on `pipeline_stages` / `pipeline_movimentos`)

```
ALTER TABLE pipeline_stages     DROP CONSTRAINT IF EXISTS pipeline_stages_pipeline_check;
ALTER TABLE pipeline_stages     ADD  CONSTRAINT pipeline_stages_pipeline_check
  CHECK (pipeline IN ('funil','processos_venda','esteira'));
ALTER TABLE pipeline_movimentos DROP CONSTRAINT IF EXISTS pipeline_movimentos_pipeline_check;
ALTER TABLE pipeline_movimentos ADD  CONSTRAINT pipeline_movimentos_pipeline_check
  CHECK (pipeline IN ('funil','processos_venda','esteira'));
ALTER TABLE pipeline_stages     DROP CONSTRAINT IF EXISTS pipeline_stages_papel_check;
ALTER TABLE pipeline_stages     ADD  CONSTRAINT pipeline_stages_papel_check
  CHECK (papel IN ('proposta_aceite','final','gravacao','postado','cancelado'));
```

The existing partial unique `uq_sw_pipeline_stages_papel (org_id, pipeline, papel)` already makes
each role unique per board.

### 2.2 `cs_equipe` (the card hub's member source)

| column | type / rule |
|---|---|
| `id` uuid PK · `org_id` uuid NOT NULL | |
| `nome` | text, trimmed, 1..80 |
| `funcao` | text NULL ≤ 60 (free text: "Videomaker", "Editor") |
| `cor` | text NULL, CHECK in the seed `STAGE_COLOR_OPTIONS` set (`primary, secondary, success, warning, destructive, muted`) |
| `user_id` | uuid NULL (a platform user, when the person has a login) |
| `ativo` | bool default true |
| `created_by`, `created_at`, `updated_at` | |

- Unique `(org_id, lower(nome))`.
- RLS as in 229 (authenticated select/write on `org_id = (SELECT public.current_org_id_for('social_wiring'))`, plus service_role ALL).

### 2.3 `cs_posts` (the reel)

| column | type / rule |
|---|---|
| `id` uuid PK · `org_id` uuid NOT NULL | |
| `marca_id` | uuid **NOT NULL** FK `marcas` ON DELETE CASCADE (a deleted marca takes its board with it, like every 229 table) |
| `formato` | text NOT NULL DEFAULT `'reel'` CHECK `('reel')` |
| `titulo` | text, trimmed, 1..200 (working title; defaults to the headline text when created from one) |
| `descricao` | (none; the hub's `descricao` note is the description) |
| `etapa_id` | uuid NOT NULL FK `pipeline_stages` (ON DELETE RESTRICT, which is the seed delete-stage guard's precondition) |
| `kanban_pos` | numeric NOT NULL DEFAULT 0 |
| `headline_id` | uuid NULL. **Composite FK** `(headline_id, marca_id) → cs_headlines (id, marca_id)` ON DELETE SET NULL (`headline_id`) |
| `roteiro_id` | uuid NULL. **Composite FK** `(roteiro_id, marca_id) → cs_roteiros (id, marca_id)` ON DELETE SET NULL (`roteiro_id`) |
| `conta_id` | uuid NULL FK `integration_accounts` ON DELETE SET NULL (same marca: checked by the service, 422 `conta_de_outra_marca`) |
| `gravacao_em` | date NULL ("Gravação agendada") |
| *(card hub "Datas")* | `data_inicio`, `data_entrega` (**label "Postagem prevista"**), `entrega_concluida`, `lembrete_minutos_antes`, `recorrencia` are added by the generated card hub section (§2.4) |
| `legenda` | text NULL ≤ 2 200 (the Instagram caption limit) |
| `hashtags` | text[] NOT NULL DEFAULT '{}' CHECK `cardinality(hashtags) <= 30` |
| `primeiro_comentario` | text NULL ≤ 2 200 |
| `links_producao` | jsonb NOT NULL DEFAULT '[]' (`[{rotulo, url}]`, ≤ 10, `https` only; service-validated, CHECK `jsonb_typeof = 'array'`) |
| `postado_em` | timestamptz NULL (stamped when entering the `postado` role stage) |
| `permalink` | text NULL CHECK `permalink ~ '^https://(www\.)?instagram\.com/'` |
| `ig_media_id` | text NULL (joins `ig_media` for insights later) |
| `motivo_bloqueio` | text NULL ≤ 1 000 (the `motivo` of the last move into the `cancelado` role stage) |
| `arquivado` | bool NOT NULL DEFAULT false (same semantics as `atendimentos.arquivado`) |
| `created_by`, `created_at`, `updated_at` | `updated_at` via `set_updated_at_media_creation()` |

Constraints and indexes:
- **UNIQUE `(headline_id)` WHERE `headline_id IS NOT NULL`**: a headline belongs to at most one post.
- **UNIQUE `(roteiro_id)` WHERE `roteiro_id IS NOT NULL`**: same for roteiros.
- `cs_headlines` and `cs_roteiros` get **`UNIQUE (id, marca_id)`**, the composite FK targets (`ALTER TABLE … ADD CONSTRAINT … UNIQUE`, idempotent through a `pg_constraint` existence check).
- Indexes:
  - `(org_id, etapa_id, kanban_pos)` (board read, as in igig 017);
  - `(marca_id, arquivado, created_at DESC)`;
  - `(org_id, data_entrega)`.
- RLS as in 229.

**`ALTER TABLE cs_headline_lotes ADD COLUMN post_id uuid NULL REFERENCES cs_posts ON DELETE SET NULL`**,
plus an index `(post_id)`. A batch generated from inside a post remembers it, so the card can show
"Gerando headlines…" and the batch's results (§6.2). The batch never binds a headline by itself;
the user picks one.

### 2.4 Card hub for the post (generated section)

`CS_POST_HUB = CardHubConfig(...)` is declared in `app/modules/media_creation/esteira_config.py`:

| Field | Value |
|---|---|
| `entity_kind` | `"post"` |
| `entity_table` | `"cs_posts"` |
| `entity_fk` | `"post_id"` |
| `id_param` | `"post_id"` |
| `table_prefix` | `"cs_post"` |
| `member_source` | `MemberSource(table="cs_equipe", fk="equipe_id", label="nome", cor="cor")` |
| `bucket` | `"sw-esteira"` (private) |
| `entity_datas` | `True` |
| `lembretes_crud` | `True` |
| `stage_table` | `"pipeline_stages"` |
| `timeline_gatherers` | `{**SEED_GATHERERS, "movimento": gather_movimentos_esteira}` |
| `documentos` | `DocumentoPolicy(storage_segment="posts")` |
| `entity_label` | `"Post"` |

- The section of 241 between the markers `-- BEGIN GENERATED card_hub(post)` / `-- END GENERATED` is
  **generated** by `card_hub_migration(CS_POST_HUB, "social_wiring", documento_tipos=ESTEIRA_DOC_TIPOS)`.
  A test asserts the text is equal (the igig `test_card_hub_wiring` pattern). Never hand-edit it.
- It creates `cs_post_notas`, `_tags`, `_tag_links`, `_membros`, `_lembretes`, `_checklists`,
  `_checklist_itens`, `_documento_tipos`, `_documentos`, `_documento_acessos`, `_checklist_extras`,
  the Datas columns on `cs_posts`, and the bucket with its object RLS.
- `ESTEIRA_DOC_TIPOS`:
  - `("referencia","nao_classificado",365,False,True,"Referências visuais e briefings")`
  - `("outro","nao_classificado",365,False,True,"Outro documento")`
  - No identity types: a post is not a person.
- `check_storage_no_public_buckets` must stay green.

### 2.5 Default stages (seeded lazily per org by the S0 seed helper)

`ESTEIRA_PADRAO` (in `esteira_config.py`), as `StageDefault(slug, label, cor, papel)`:

| posição | slug | label (pt-BR) | cor | papel |
|---|---|---|---|---|
| 0 | `ideacao` | Ideação | secondary | — (entry stage = first by position, seed `resolve_initial_stage`) |
| 1 | `headline_roteiro` | Headline + roteiro | primary | — |
| 2 | `gravacao` | Gravação | warning | `gravacao` |
| 3 | `edicao` | Edição | warning | — |
| 4 | `pronto` | Pronto | success | — |
| 5 | `postado` | Postado | success | `postado` |
| 6 | `bloqueado_cancelado` | Bloqueado/cancelado | destructive | `cancelado` |

- `PIPELINE_ESTEIRA = PipelineConfig(pipeline="esteira", card_table="cs_posts", value_field="kanban_pos",
  entity_label="post", entity_label_plural="posts", entity_kind="cs_post", cliente_field=None,
  stage_roles=("gravacao","postado","cancelado"))`.
- `status_field` stays `None`: it is meant for text lifecycle statuses. The board query filters `arquivado=false` itself, and an archived post still counts for the stage-delete guard, which is the safe side.
- `value_field` is irrelevant because the board passes `value_of=lambda _: 0`. It is set to an existing numeric column so a missing-column read is impossible.
- **Stages are editable per org** through the seed stage manager (rename, recolour, reorder, add, deactivate), admins only, as in the funil. Slugs are immutable.
- Code keys only on **roles**, never on slugs or labels. So a renamed "Gravação" keeps its gate.

### 2.6 GuardProbes (`_SW_241_PROBES` in `mcp/noctusai/tools/noctus/dev/verify_db_guards.py`, BE-0)

| id | kind | asserts |
|---|---|---|
| `sw241_post_headline_outra_marca` | write_refusal | insert a `cs_posts` row whose `headline_id` belongs to another marca → composite FK refuses |
| `sw241_post_roteiro_outra_marca` | write_refusal | same for `roteiro_id` |
| `sw241_headline_unico_por_post` | write_refusal | a second post with the same `headline_id` → unique refuses |
| `sw241_roteiro_unico_por_post` | write_refusal | same for `roteiro_id` |
| `sw241_post_formato` | write_refusal | `formato='story'` → CHECK |
| `sw241_post_titulo_vazio` | write_refusal | `titulo='  '` → CHECK |
| `sw241_post_hashtags_max` | write_refusal | 31 hashtags → CHECK |
| `sw241_post_permalink` | write_refusal | `permalink='http://evil'` → CHECK |
| `sw241_stage_esteira_ok` | write_allowed | a `pipeline_stages` row `pipeline='esteira', papel='postado'` (rolled back) |
| `sw241_stage_pipeline_invalido` | write_refusal | `pipeline='xyz'` → CHECK still refuses |
| `sw241_equipe_nome_unico` | write_refusal | duplicate `lower(nome)` in one org |
| `sw241_headline_delete_nulls_only_fk` | state_assertion | deleting a bound headline leaves `cs_posts.marca_id` intact and `headline_id` NULL (column-list SET NULL) |
| `sw241_status_pagina` | state_assertion | `media-creation-esteira`=desenvolvimento, `-branding`/`-carrosseis`=producao, `media_creation`=desativado |

The probes use the self-provisioned builders (`_self_provisioned_insert_check_probe`), which create
their own marca, headline and stage inside the probe transaction and roll back.

### 2.7 `status_pagina`

```
INSERT … ('media-creation-esteira','desenvolvimento','CoreStudio — Esteira de reels')
INSERT … ('media-creation-branding','producao','CoreStudio — Branding por marca')
INSERT … ('media-creation-carrosseis','producao','CoreStudio — Carrosséis e posts de imagem')
UPDATE status_pagina SET status='desativado' WHERE nome_pagina='media_creation';
```

The inserts use `ON CONFLICT (nome_pagina) DO NOTHING`. The UPDATE runs with FE-Z's deploy, in the
same migration. The redirect covers the old route.

---

## 3 · Relationship rules (the post owns its headline and roteiro)

1. **1:1 and optional.** A post has at most one headline and one roteiro. A headline or roteiro
   belongs to at most one post (the unique indexes). The relationship lives on the post (FK
   columns), so "the post's headline" is one join and the library rows need no new column.
2. **The library keeps every row.** Headlines and roteiros are not moved or copied into the post.
   - Unbinding (`DELETE /posts/{id}/headline`) only nulls the FK. The row stays in Favoritas/Sugeridas/Meus roteiros.
   - Deleting a post leaves its headline and roteiro in the library, unbound.
   - Deleting a bound headline or roteiro nulls the post's FK (column-list SET NULL). The card then shows "Headline removida da biblioteca", never a crash.
3. **Existing standalone headlines (11) and roteiros (1)** stay standalone. No backfill.
4. **Creating a post from a headline.** "Criar post" on Favoritas, Sugeridas, the "Headlines Geradas" modal or the chat headline card does `POST /posts {marca_id, headline_id}`.
   - It creates the post in the **Headline + roteiro** stage, at the top.
   - `titulo` defaults to the headline text (truncated to 200).
   - 409 `headline_ja_em_post` (with `post_id`) if the headline is bound. The UI offers "Abrir post".
5. **A roteiro created inside a post binds to it.**
   - `RoteiroAvancadoModal` opened from the card sends `post_id` with `POST /roteiros`.
   - The service sets `cs_posts.roteiro_id` in the same request, after the roteiro row exists, and before the job is enqueued.
   - Its `headline_id` is the post's headline.
   - If the post already has a roteiro, 409 `post_ja_tem_roteiro`, unless `substituir=true`. Then the old one is unbound and stays in Meus roteiros.
   - **Reprocessar** a bound roteiro creates a new row (229 behaviour). If the source was bound, the new row **takes over the binding** in the same transaction (an RPC `cs_rebind_roteiro(p_post, p_old, p_new)` with a row lock; 409 if the post moved on).
6. **Binding an existing roteiro** (`PUT /posts/{id}/roteiro {roteiro_id}`).
   - It must be the same marca (composite FK; the service answers 422 `roteiro_de_outra_marca` before the DB does).
   - If the roteiro's `headline_id` differs from the post's, the binding is allowed and the card shows the warning "Este roteiro foi escrito para outra headline". Never silent.
7. **Headline generation from the card** creates a batch with `post_id` (§6.2). The 10 resulting headlines are ordinary library rows. Picking one binds it (`PUT /posts/{id}/headline`), and the other 9 stay in the library.

---

## 4 · Move rules (stage gate)

The server is the authority (`services/esteira_service.py :: mover_post`). The FE mirrors it in
`moveRules.ts` only to open the right dialog.

| Move | Rule | Error |
|---|---|---|
| Same column (reorder) | always | — |
| Forward, any number of steps | allowed (D3: reels skip stages often, unlike igig's one-step agency flow) | — |
| Into a stage at or after the **`gravacao`** role's position, except the `cancelado` role | requires `headline_id` **and** `roteiro_id` with `cs_roteiros.status='completo'` | 409 `pendencias` `{faltando:["headline","roteiro"\|"roteiro_incompleto"]}` (SW `stage_gate.pendencias` shape) |
| Into the **`postado`** role | stamps `postado_em=now()` if NULL. `permalink` is optional but asked for in the dialog | — |
| Into the **`cancelado`** role | `motivo` **required**, stored in `motivo_bloqueio` and in `pipeline_movimentos.motivo` | 422 `motivo_obrigatorio` |
| Backward (to a lower position) | `motivo` required | 422 `motivo_obrigatorio` |
| Out of `cancelado` | allowed backward with `motivo` (reactivation); `motivo_bloqueio` is kept for history and cleared from the face | — |
| Target stage inactive or of another org/pipeline | refused | 409 `etapa_invalida` / 404 |

- Every move goes through seed `move_card`, which writes `pipeline_movimentos` with `pipeline='esteira'`, `entidade_id=post.id` and `responsavel_id` = the user.
- The timeline gatherer `gather_movimentos_esteira` renders those rows ("Movido de Gravação para Edição · motivo").
- Stage delete and deactivate use the seed guard (`count_cards_in_stage`). A stage with posts cannot be deleted.

---

## 5 · Endpoints — prefix `/api/media-creation/esteira`, auth `get_current_user_org`, all org-scoped

### 5.1 Board and posts (`routers/esteira.py`, BE-1)

| # | Method + path | Body / query | Notes |
|---|---|---|---|
| 1 | `/etapas` (seed `pipeline_stages_router(PIPELINE_ESTEIRA)`) | seed | Writes need the same guard as SW `modules/pipeline/routers/stages.py`. Defaults are seeded on first read (S0 helper) |
| 2 | `GET /board` | `marca_id?`, `busca?` (titulo/headline ilike), `membro_id?`, `incluir_arquivados=false`, `limite_por_etapa=50` | `{colunas:[{etapa, stage, cards, total, exibidos}], orfaos:int}`; cards = `PostCard` (§5.4). `marca_id` of another org → 404 |
| 3 | `POST /posts` | `PostCreate {marca_id, titulo?, headline_id?, etapa_id?, conta_id?, gravacao_em?, data_entrega?}` | `titulo` is required unless `headline_id` is given. Default stage: the entry stage, or the 2nd position when `headline_id` is given. Placed on top. 201 `PostDetalhe` |
| 4 | `GET /posts/{id}` | | `PostDetalhe` (with `headline`, `roteiro` summaries, `conta`, `marca`) |
| 5 | `PATCH /posts/{id}` | `PostUpdate {titulo?, conta_id?, gravacao_em?, legenda?, hashtags?, primeiro_comentario?, links_producao?, permalink?, ig_media_id?, arquivado?}` | **never** `etapa_id`, `marca_id`, `headline_id`, `roteiro_id` (422 `campo_nao_editavel`). The Datas go through the hub's `/card` route |
| 6 | `DELETE /posts/{id}` | | hard delete; the hub tables CASCADE; headline and roteiro stay unbound in the library; 204 |
| 7 | `POST /posts/{id}/mover-etapa` | `MoverEtapaRequest {para_etapa_id, novo_indice?, motivo?, permalink?}` (SW shape + `permalink`) | §4 rules; 200 `PostCard` |
| 8 | `PUT /posts/{id}/headline` | `{headline_id}` or `{texto}` (≤ 1 000; creates a `cs_headlines` row with `lote_id NULL`, `marca_id` of the post) | §3.4/§3.7; 409 `headline_ja_em_post`; 422 other marca |
| 9 | `DELETE /posts/{id}/headline` | | unbind; 204 |
| 10 | `PUT /posts/{id}/roteiro` | `{roteiro_id}` | §3.6 |
| 11 | `DELETE /posts/{id}/roteiro` | | unbind; 204 |
| 12 | card hub routes | seed `card_hub_routers(CS_POST_HUB, …)` mounted under `/api/media-creation/esteira/posts/{post_id}/…` | notas, tags, membros, lembretes, checklists, checklist-extras, documentos, timeline, `/card` (resumo + Datas) |

### 5.2 Equipe (`routers/equipe.py`, BE-1)

`GET /api/media-creation/equipe` (`?incluir_inativos`) · `POST` `{nome, funcao?, cor?, user_id?}` ·
`PATCH /{id}` · `DELETE /{id}`.

- DELETE is a soft delete: it sets `ativo=false` when the member is on any post, and hard-deletes otherwise.
- A duplicate name answers 409 `membro_duplicado`.

### 5.3 Changes to existing Geração endpoints (BE-2)

- `POST /api/media-creation/headlines/lotes`: `LoteParams` gains `post_id?`.
  - It must be the same org and marca as `marca_id` (422 `post_de_outra_marca`), and is stored on the batch.
  - `GET /headlines/lotes?post_id=` filters by it.
- `POST /api/media-creation/roteiros`: `RoteiroCreate` gains `post_id?` and `substituir=false` (§3.5).
- `POST /roteiros/{id}/reprocessar` takes over the binding (§3.5).
- `GET /headlines` and `GET /roteiros` (lists) and `GET /headlines/{id}` / `GET /roteiros/{id}`: each row gains `post: {id, titulo, etapa_label} | null`, from a left join on `cs_posts`.
- `POST /api/media-creation/esteira/posts/{id}/legenda/gerar` (`routers/esteira_legenda.py`):
  - LLM `GERACAO_LLM_MODEL` with `DEFAULT_AI_RL`;
  - input = roteiro `conteudo` plus headline plus `cs_marca_perfil` (bio, CTAs);
  - output `{legenda, hashtags[], primeiro_comentario}` is **returned, not saved**. The user edits it, then PATCHes #5;
  - 422 `sem_roteiro` without a completed roteiro;
  - cap `legendas_dia_usuario=40` (config).

### 5.4 TS types (FE-0 writes these verbatim to `src/types/esteira.ts`; BE schemas mirror them)

```ts
export type PapelEsteira = "gravacao" | "postado" | "cancelado";
export interface ResumoHeadline { id: string; texto: string; favorita: boolean }
export interface ResumoRoteiro { id: string; nome: string; status: "criando"|"perguntas"|"processando"|"completo"|"falha"; headline_id: string | null; headline_diferente: boolean }
export interface LinkProducao { rotulo: string; url: string }
export interface PostCard {
  id: string; marca_id: string; marca_nome: string; titulo: string; formato: "reel";
  etapa_id: string; kanban_pos: string;               // numeric serialized as string
  headline: ResumoHeadline | null; roteiro: ResumoRoteiro | null;
  membros: { id: string; nome: string; cor: string | null }[];
  gravacao_em: string | null; data_entrega: string | null; entrega_concluida: boolean;
  postado_em: string | null; motivo_bloqueio: string | null; arquivado: boolean;
  checklist: { feitos: number; total: number };      // from the hub badges
  comentarios: number;
}
export interface PostDetalhe extends PostCard {
  conta: { id: string; account_label: string } | null;
  legenda: string | null; hashtags: string[]; primeiro_comentario: string | null;
  links_producao: LinkProducao[]; permalink: string | null; ig_media_id: string | null;
  lote_ativo: { id: string; status: string; etapa: string | null } | null; // latest batch with post_id still criando/processando
  created_at: string; updated_at: string;
}
export interface PostCreate { marca_id: string; titulo?: string; headline_id?: string; etapa_id?: string; conta_id?: string; gravacao_em?: string; data_entrega?: string }
export type PostUpdate = Partial<Pick<PostDetalhe, "titulo"|"legenda"|"hashtags"|"primeiro_comentario"|"links_producao"|"permalink"|"ig_media_id"|"gravacao_em"|"arquivado">> & { conta_id?: string | null };
export interface MembroEquipe { id: string; nome: string; funcao: string | null; cor: string | null; user_id: string | null; ativo: boolean }
export interface LegendaGerada { legenda: string; hashtags: string[]; primeiro_comentario: string }
export interface PendenciasErro { code: "pendencias"; faltando: ("headline"|"roteiro"|"roteiro_incompleto")[] }
```

The existing `Headline` and `Roteiro` types in `types/geracao.ts` gain `post?: {id, titulo, etapa_label} | null` (FE-0).

---

## 6 · Frontend

### 6.1 Esteira page (E1, `pages/geracao/Esteira.tsx`, FE-1)

- **Header.** "Esteira" — "Do roteiro ao post: acompanhe cada reel por etapa." The toolbar holds:
  - **Marca** select ("Todas as marcas" plus the org's marcas from `useMarcas`; URL `?marca=`). A first visit defaults to the remembered `sw.pesquisa.marca` if it is set, otherwise Todas.
  - Busca (`?busca=`, debounced).
  - Membro filter.
  - "Mostrar arquivados".
  - **Equipe** (opens `EquipeDialog`: list, add, edit, deactivate).
  - **Novo post**.
- **Board.** `components/geracao/esteira/EsteiraBoard.tsx` uses seed `<PipelineBoard>`:
  - `hooks={esteiraPipeline}` (`createPipelineHooks<PostCard>` with board `/api/media-creation/esteira/board`, stages `/…/etapas`, move `/…/posts`);
  - `filtros={{marca_id, busca, membro_id, incluir_arquivados}}`;
  - `renderCard={PostCardFace}`, `showValue={false}`;
  - `editableHeaders`, `reorderableColumns`, `canEditStages` (org admin);
  - `roleLabels={{gravacao:"Início da produção", postado:"Publicado", cancelado:"Encerrado"}}`;
  - `onBeforeMove={decidirMovimento}`;
  - `onMoveError` → toast. A 409 `pendencias` shows "Para entrar em Gravação o post precisa de headline e roteiro concluído" plus "Abrir post".
- **Move dialogs.**
  - `moveRules.ts` mirrors §4.
  - A backward move or a move into cancelado opens the seed `MotivoMoveDialog` ("Por que este post está voltando?" / "Motivo do bloqueio ou cancelamento").
  - A move into postado opens `PostadoDialog` ("Link do post (opcional)", validated as an `instagram.com` URL).
- **Card face** (`PostCardFace.tsx`, seed `CardHubFace` building blocks):
  - marca chip (hidden when filtered by one marca);
  - título;
  - headline excerpt (2 lines) or "Sem headline";
  - roteiro status badge (`StatusBadge` from geracao);
  - members' avatars;
  - "Postagem prevista" date with the seed `resolveDueState` (red when overdue, unless postado or cancelado);
  - checklist n/m;
  - comment count;
  - `motivo_bloqueio` excerpt in the cancelado column.
- **Novo post** (`NovoPostDialog.tsx`):
  - Marca (required; prefilled from the filter);
  - Título (required unless a headline is chosen);
  - "Começar com uma headline" (optional picker over the marca's Favoritas, then Sugeridas);
  - Conta de destino (the marca's IG accounts; hidden when there is only one);
  - Postagem prevista.
  - The post lands on top of its stage.
- **Deep link.** `?post=<id>` opens the card. Closing it removes the param.
- **States.** Skeleton on first load only (`showSkeleton = isPending && !data`; refetch keeps data, never `isLoading`). Empty board: "Nenhum post ainda. Crie o primeiro ou transforme uma headline favorita em post."

### 6.2 Post card (`components/geracao/esteira/PostCardDialog.tsx`, FE-2)

The card is the seed `CardHubDialog` (SW `ClienteCardDialog` is the reference consumer), on
`createCardHubHooks` with the base `/api/media-creation/esteira/posts`. Its header has the título
(inline edit), the marca chip, the stage select (it goes through `mover-etapa` and the same move
rules and dialogs), the Datas popover (seed), the members popover (seed `MembrosPopover` over
`cs_equipe`), the labels popover (seed) and ⋯ (Arquivar · Excluir, with confirm).

`CardSidebarNav` sections, in order:

1. **Geral.** The seed `DescricaoSection` (the post's idea/brief), the conta de destino, "Gravação agendada", and the seed `ChecklistsSection` (stage-required checklists come for free).
2. **Headline** (`secoes/HeadlineSecao.tsx`). This is the headline mechanism, moved inside the post.
   - **With a headline:**
     - shows the text, ♥ state and "Editar" (opens the **existing `EditarHeadlineModal`** unchanged, so `texto_original` is kept);
     - "Trocar headline" opens the picker;
     - "Desvincular";
     - a link "Ver na biblioteca" (→ `/media-creation/headlines/favoritas?hid=`).
   - **Without a headline,** three actions:
     - **Escolher da biblioteca:** a picker with tabs Favoritas / Sugeridas / Geradas recentemente for the post's marca. It reuses `useHeadlinesLista`, and rows already bound to another post are disabled with "No post: <título>".
     - **Gerar headlines:** opens `GerarHeadlinesDialog`. It **reuses the existing form components** `FormMePublico` / `FormViral` from `components/geracao/headlines/` inside a dialog, with the marca fixed and `post_id` sent. Progress uses the existing `ProgressoLote`. On completion it shows the existing `HeadlinesGeradasModal`, where each headline gets a new action **"Usar neste post"** (prop `onUsarNoPost?`) that binds it and closes.
     - **Escrever a minha:** a textarea that sends `PUT /headline {texto}`.
   - While a batch with this `post_id` is running, the section shows "Gerando headlines — <etapa>" (`lote_ativo`, 3 s poll).
3. **Roteiro** (`secoes/RoteiroSecao.tsx`). This is the roteiro mechanism, moved inside the post.
   - Without a roteiro: **"Criar roteiro"** opens the **existing `RoteiroAvancadoModal`** with `headlineInicial` = the post's headline and the new prop `postId`. "Vincular roteiro existente" opens a picker over Meus roteiros of the marca.
   - With a roteiro:
     - status badge plus real `etapa`;
     - the rendered markdown (read-only) with "Copiar roteiro";
     - "Editar" opens the existing `EditarRoteiroModal`;
     - "Reprocessar" (the binding follows, §3.5);
     - "Desvincular";
     - the `headline_diferente` warning when it applies.
4. **Produção** (`secoes/ProducaoSecao.tsx`): `links_producao` (rótulo + https URL, ≤ 10; "Pasta do Drive", "Corte final"…) plus the seed `AnexosSection` (images/PDF references, 25 MB).
5. **Publicação** (`secoes/PublicacaoSecao.tsx`):
   - Legenda (≤ 2 200 with a counter), Hashtags (chips, ≤ 30) and Primeiro comentário;
   - **"Gerar legenda com IA"** (§5.3; fills the fields, the user edits, then "Salvar"; disabled with a tooltip until the roteiro is complete);
   - Permalink and `postado_em` (read-only once in postado).
6. **Lembretes:** the seed `LembretesSubpage`.
7. **Atividade:** the seed `Timeline` (comments composer, moves, checklist events, notes).

### 6.3 The standalone Headlines / Roteiros pages: **keep them as libraries, linked to posts** (D2)

**Reasoning.**
- One batch produces 10 headlines, and the daily suggestions produce 10 more per marca. Most never become a reel. Favoritas and Sugeridas are the idea bank that feeds the **Ideação** column.
- Removing the pages would lose the batch history, the suggestions flow and the bulk actions.
- The chat also saves headlines without a post.
- Moving the mechanisms *inside* the card (§6.2) and keeping the library *outside* gives one data model with two entry points, and no copy.

**Changes (FE-3).**
- `ListaHeadlinesPage` (Favoritas/Sugeridas) and `HeadlinesGeradasModal`:
  - a new action **"Criar post"** (→ §3.4, then opens `/media-creation/esteira?post=<id>`);
  - a badge **"No post: <título> · <etapa>"** linking to `?post=` when bound.
- `Roteiros.tsx`: a new column **Post** (link or "—").
- `RoteiroAvancadoModal` gains `postId?: string` (sent on create; the "Criado" state says "Vinculado ao post <título>").
- The Dashboard's "Roteiros recentes" shows the same Post link.

---

## 7 · Live-test items (tech-lead appends to `TEST-CHECKLIST.md` as "Esteira + CoreStudio rename (migration 241)")

**Rename and absorption**
- [ ] The sidebar group reads **CoreStudio**. There is no "Criação de mídia" link anywhere.
- [ ] `/media-creation` redirects to Carrosséis, and `/media-creation?tab=brand` redirects to Branding.
- [ ] A non-dev user still sees **Carrosséis** and **Branding** and nothing else of CoreStudio.
- [ ] Carrosséis: the 6 existing drafts are listed; open one and run storyboard → prompts → render → copy → score with the same results as before.
- [ ] Branding: the kits per marca show tokens, brand book, components and assets; import a design-system folder; the template still exists.
- [ ] Extrair Pesquisa still lists "Posts criados" with the same count.

**Board**
- [ ] Owner sees CoreStudio › Esteira. The first visit seeds the 7 columns in order with pt-BR labels.
- [ ] Marca filter: "Todas" shows every marca's posts with a marca chip; picking a marca hides the others; reload keeps it (`?marca=`).
- [ ] Novo post: marca required; it lands on top of Ideação. With a headline picked it lands in "Headline + roteiro" and the title is the headline.
- [ ] Reorder inside a column persists after reload. A drag forward from Ideação to Edição without headline/roteiro is refused with the pendências message and "Abrir post".
- [ ] A drag back asks for a motivo; Cancel restores the card. A drag into Bloqueado/cancelado asks for the motivo, and the face shows it.
- [ ] A drag into Postado asks for the optional link; `postado_em` is set. The overdue colour never shows on postado or cancelado cards.
- [ ] Admin renames "Gravação" to "Filmagem": the gate still applies. Deleting a column with posts is refused.

**Card**
- [ ] Headline → Escolher da biblioteca → pick a favorite: it is bound, and Favoritas shows "No post: …". A second post cannot pick the same one (disabled row).
- [ ] Headline → Gerar headlines: the form runs inside the dialog; progress shows the real etapa; "Usar neste post" binds one; the other 9 are in the library.
- [ ] Editar headline keeps the original (Editar modal shows "Original").
- [ ] Roteiro → Criar roteiro: questions → roteiro; closing the modal mid-run is safe; the section shows the roteiro when complete; Meus roteiros shows the Post column.
- [ ] Reprocessar the roteiro: the post now shows the new version; the old one remains in Meus roteiros, unbound.
- [ ] Delete the bound headline from Favoritas: the card says "Headline removida da biblioteca" and the marca is intact.
- [ ] Publicação → Gerar legenda: a reasonable pt-BR caption, hashtags and first comment; edit and save; reload keeps it. **Judge the DRAFT legenda prompt.**
- [ ] Membros: add "Editor" in Equipe; assign them; the avatar shows on the face; the filter by member works.
- [ ] Datas: Postagem prevista + reminder; Lembretes fire (seed behaviour).
- [ ] Comments, checklist and attachments (image) work; Atividade lists the moves with motivos.
- [ ] Cross-org: another org's post id in `?post=` → "Post não encontrado".

**Owner decisions while testing:** D1–D12 (§11), Q1–Q8 (§12).

---

## 8 · Tests (minimum)

**Backend** (`tests/modules/media_creation/test_esteira_*.py`; `MockSupabaseClient`, fake LLM)
- **Migration (`tests/test_migration_241_cs_esteira.py`):**
  - CHECKs widened (static SQL);
  - the composite FKs use the column-list SET NULL;
  - the generated card hub section == `card_hub_migration(CS_POST_HUB, "social_wiring", documento_tipos=ESTEIRA_DOC_TIPOS)`;
  - the status_pagina rows/updates;
  - the guard block.
- **Auth and scoping:**
  - every route strict `== 401` without a session (AST-checked; never `in (401, …)`);
  - cross-org 404 for post, marca filter, etapa, equipe member, headline/roteiro bind, and the hub routes;
  - `DEFAULT_AI_RL` on legenda.
- **Board:** grouping by stage; `marca_id` filter; `busca`; `membro_id`; `arquivado` excluded by default; orphan count; default stages seeded once and never re-seeded after an admin deactivates them.
- **Create:** default stage with and without a headline; on-top position; 409 `headline_ja_em_post`; 422 other-marca headline or conta; titulo required without a headline.
- **Move (`mover_post`):**
  - reorder midpoint;
  - forward skip allowed;
  - the gate at or after the `gravacao` role (missing headline / missing roteiro / roteiro not completo) → 409 `pendencias` with the exact list;
  - backward without motivo → 422;
  - cancelado without motivo → 422;
  - postado stamps `postado_em` once;
  - inactive stage → 409;
  - history row written with `pipeline='esteira'`;
  - **a renamed role stage keeps the gate** (keys on roles, not slugs).
- **Bind/unbind:** headline by id and by texto; roteiro by id; `headline_diferente` flag; unbind keeps the rows; post delete keeps the rows; headline delete nulls only the FK (realdb test in `tests/realdb/`).
- **Geração changes (BE-2):**
  - lote with `post_id` (other marca → 422);
  - roteiro create with `post_id` binds;
  - `post_ja_tem_roteiro` 409, and `substituir=true` rebinds;
  - reprocessar moves the binding atomically (and 409 if the post's roteiro changed meanwhile);
  - list rows carry `post`;
  - legenda: `sem_roteiro` 422, output parse, prompt fences the roteiro as data, nothing saved, daily cap 429.
- **Equipe:** CRUD, duplicate 409, soft delete when in use.
- **Card hub:** the seed contract tests parametrized for `CS_POST_HUB` (notas, membros over `cs_equipe`, checklists, documentos policy, timeline with `movimento`).
- **S0 (seed):** `ensure_default_stages` seeds only when the pipeline has zero rows (including inactive); idempotent upsert; igig's existing pipeline tests stay green unchanged.

**Frontend** (vitest, mocked API)
- `Esteira.test.tsx`: marca filter ↔ URL, `?post=` opens the card, empty state, skeleton only without data, toolbar actions.
- `moveRules.test.ts`: every row of §4.
- `PostCardFace.test.tsx`: overdue rule (not on postado/cancelado), marca chip visibility, roteiro badge.
- `PostCardDialog.test.tsx`: sections render; Headline picker disables bound rows; "Usar neste post" binds; Roteiro opens `RoteiroAvancadoModal` with `postId`; legenda fills and saves; pendências toast.
- FE-3: "Criar post" action and the "No post" badge on Favoritas/Sugeridas; the Post column on Roteiros.
- FE-A: `Branding.test.tsx` (renders BrandingTab), `Carrosseis.test.tsx` (both tabs). The existing `BrandingTab.test.tsx` stays green.
- S0b: `PipelineBoard` with `showValue={false}` renders no value line; the default is unchanged.

---

## 9 · Security and LGPD

- **Prompt injection.** The roteiro, headline and bio go into the legenda prompt inside the existing `dados_nao_confiaveis` fence (`REGRAS_MATERIAL`). The output is plain text, never executed or used as a URL.
- **URLs.**
  - `links_producao` and `permalink` are `https` only, max 2 048 chars, and rendered with `rel="noopener noreferrer"` `target="_blank"`. They are never fetched server-side (no SSRF surface).
  - `permalink` is restricted to `instagram.com` by CHECK.
- **Documents.** The seed hub `DocumentoPolicy` applies (magic bytes, 25 MB, signed URLs 300 s, private bucket `sw-esteira`, object RLS on the org folder).
- **IDOR.** Every id-taking route resolves through `org_id`, plus the marca where relevant. The composite FKs make cross-marca binding impossible even for a service-role bug.
- **LGPD.** `cs_equipe` holds names of team members (personal data of the org's own staff and contractors). Purpose: task assignment. Retention: until the org deletes them. Low risk; the tech-lead records it with `noctus.dev.lgpd_flag` when BE-1 integrates. There is no third-party personal data beyond what the 229 tables already hold.
- **Spend.** `legendas_dia_usuario=40`, plus the seed org LLM budget (`enforce_budget`). A refusal is 503 `orcamento_ia_excedido`.

---

## 10 · Slice plan (file-disjoint; each slice in its own `task_branch` off `origin/dev`)

**Migration plan.**
- **BE-0 owns `241_cs_esteira.sql`** and `APPLIED.md` (C4). No other slice writes SQL.
- A schema gap found later becomes a BE-0 follow-up commit before wave 1 integrates.
- 241 is applied to prod with owner consent through `migrate_product` **before** the image deploy, because FE-Z's `media_creation → desativado` must ship together with the redirect.
- Order: 241 → image deploy, the same release.

### Wave 0 (integrate before wave 1)

- **S0 (engineer-seed, backend + frontend):**
  - `seed/lib/backend/noctusai_lib/domain/pipeline/defaults.py` (`StageDefault`, `ensure_default_stages(db, cfg, defaults, *, org_id)`, lifted from igig `garantir_etapas_padrao`) plus its export and tests;
  - igig `backend/app/pipelines.py` moved onto it (no behaviour change; igig tests green);
  - `seed/lib/frontend/src/components/pipeline/PipelineBoard.tsx` `showValue?: boolean` plus a test; igig `EsteiraBoard.tsx` passes `showValue={false}` instead of `formatValue={() => ""}`.
  - The template sync is done by the pre-commit hook.
- **BE-0 (backend):**
  - `migrations/241_cs_esteira.sql` (§2, with the generated card hub section), `tests/test_migration_241_cs_esteira.py` and the `APPLIED.md` entry;
  - `app/modules/media_creation/esteira_config.py` (`PIPELINE_ESTEIRA`, `ESTEIRA_PADRAO`, `CS_POST_HUB`, `ESTEIRA_DOC_TIPOS`, `gerar_migration_card_hub()`);
  - `mcp/noctusai/tools/noctus/dev/verify_db_guards.py` `_SW_241_PROBES` plus its registration and a probe test;
  - `app/config.py` `legendas_dia_usuario`;
  - the `NOC-REMEDIATE[mc-brand-owners-legacy]` note in the 241 header.
- **FE-0 (frontend):**
  - `src/types/esteira.ts` (§5.4 verbatim, first commit) plus the `post?` field on `types/geracao.ts`;
  - `src/lib/pipelines.ts` gains `esteiraPipeline` (`createPipelineHooks<PostCard>`);
  - `src/hooks/geracao/useEsteira.ts` (post CRUD, bind/unbind, legenda, equipe hooks; query keys exported).

### Wave 1 (parallel)

- **BE-1:**
  - `schemas/esteira.py`, `services/esteira_service.py` (board, create, update, delete, `mover_post` + gate, bind/unbind headline/roteiro, `gather_movimentos_esteira`), `routers/esteira.py` (incl. the stages router and the card hub mount), `schemas/equipe.py`, `services/equipe_service.py`, `routers/equipe.py`;
  - the **append** of its routers to `media_creation/__init__.py` (C2);
  - tests.
- **BE-2:**
  - `schemas/headlines.py` + `services/headline_service.py` (`post_id` on batches, `post` on rows);
  - `schemas/roteiros.py` + `services/roteiro_service.py` (`post_id`/`substituir`, rebind on reprocess via the RPC, `post` on rows);
  - `prompts/roteiro_geracao.py` (the beat-order line + version bump, §A.3 drift 1);
  - `prompts/legenda_reel.py` (**DRAFT**, built from `COPY_SYSTEM_PROMPT`'s rules with reel input), `services/legenda_service.py`, `routers/esteira_legenda.py` (+ C2 append);
  - tests.
  - The rebind RPC `cs_rebind_roteiro` is in **BE-0's** migration (BE-2 gives its signature to BE-0 in wave 0: `(p_org uuid, p_post uuid, p_old uuid, p_new uuid) returns boolean`).
- **FE-A:** `pages/geracao/Branding.tsx`, `pages/geracao/Carrosseis.tsx` (moving `LibraryTab`/`ComposeTab` out of `MediaCreation.tsx` into `components/geracao/carrosseis/{LibraryTab,ComposeTab}.tsx`), tests. It **does not** delete `MediaCreation.tsx` (FE-Z does, together with the route).
- **FE-1:** `pages/geracao/Esteira.tsx`, `components/geracao/esteira/{EsteiraBoard,PostCardFace,NovoPostDialog,PostadoDialog,EquipeDialog,moveRules}.tsx|ts`, tests.
- **FE-3:** `components/geracao/headlines/{ListaHeadlinesPage,HeadlinesGeradasModal}.tsx` ("Criar post", "No post" badge, `onUsarNoPost`), `pages/geracao/Roteiros.tsx` (Post column), `components/geracao/roteiro/RoteiroAvancadoModal.tsx` (`postId`), `pages/geracao/Dashboard.tsx` (Post link), tests.

### Wave 2 (FE-1 and FE-3 integrated)

- **FE-2:** `components/geracao/esteira/PostCardDialog.tsx`, `components/geracao/esteira/secoes/**`, `components/geracao/esteira/GerarHeadlinesDialog.tsx`, `hooks/geracao/useCardHubPost.ts` (`createCardHubHooks`), tests. It imports FE-1's `moveRules`, plus FE-3's `onUsarNoPost` and `postId` props.

### Wave 3 (tech-lead, inline)

- **FE-Z (`App.tsx`, C1):**
  - routes `/media-creation/esteira`, `/branding`, `/carrosseis`;
  - the `/media-creation` redirect (with `?tab=brand`);
  - delete the "Criação de mídia" item and `MediaCreation.tsx` and its lazy import;
  - **rename the group label to "CoreStudio"** in both nav configs and the header comment;
  - the §1.1 order, the `route:` keys, and the `TEST-CHECKLIST.md` section (§7).
- Re-run `gate_sweep` on the **merged tip**, then `predeploy_check social-wiring` (the `schema_drift` leg is red until 241 is applied), then `verify_db_guards` for `_SW_241_PROBES` after the apply.

### Collision classes

| Class | File(s) | Rule |
|---|---|---|
| C1 | `frontend/src/App.tsx` | FE-Z only |
| C2 | `media_creation/__init__.py` | BE-1 / BE-2 **append** router lines only (integrator resolves) |
| C3 | `app/config.py` | BE-0 only |
| C4 | `migrations/241_*.sql`, `migrations/APPLIED.md`, `verify_db_guards.py` | BE-0 only |
| C5 | `seed/lib/**`, `templates/product-seed/**`, `products/igig/**` | S0 only |
| C6 | `components/geracao/headlines/**`, `components/geracao/roteiro/**`, `pages/geracao/{Roteiros,Dashboard}.tsx` | FE-3 only |
| C7 | `components/geracao/esteira/**` | FE-1 (board files) / FE-2 (`PostCardDialog`, `secoes/**`, `GerarHeadlinesDialog`); disjoint by file |
| C8 | `pages/MediaCreation.tsx`, `components/branding/**` | FE-A reads/moves; only FE-Z deletes `MediaCreation.tsx`; nobody edits `components/branding/**` |
| C9 | `services/{headline,roteiro}_service.py`, `schemas/{headlines,roteiros}.py`, `prompts/roteiro_geracao.py` | BE-2 only |
| C10 | `projects/core-studio/*.md` | tech-lead only |
| C11 | `pesquisa_fontes.py` and the `mc_post` source | nobody (read-only; the legacy tables stay) |

---

## 11 · Tech-lead defaults — validate with owner

| # | Default | Where |
|---|---|---|
| D1 | **Absorption:** keep the legacy BE and tables; split the page into **Carrosséis** (prod) + **Branding** (prod, under Configurações); delete the page, link and route (redirect); rename the group **CoreStudio** | §A.4 |
| D2 | **Headlines/Roteiros pages stay as libraries**, linked to posts ("Criar post", "No post" badge, Post column) | §6.3 |
| D3 | **Move rules:** free forward moves (no igig one-step rule); a gate requires headline + completed roteiro from the Gravação role on; backward and cancel require a motivo | §4 |
| D4 | **Stage slugs** `ideacao, headline_roteiro, gravacao, edicao, pronto, postado, bloqueado_cancelado`; roles `gravacao`, `postado`, `cancelado`; admins may rename/add/reorder | §2.5 |
| D5 | **Assignees = card hub members from a new `cs_equipe`** (content team, optional login), not platform users only and not `lead_corretores` | §0.6, §2.2 |
| D6 | **Full SW card hub on the post** (comments, checklists, labels, Datas, reminders, attachments, timeline), generated by the seed emitter | §2.4 |
| D7 | **Dates:** "Postagem prevista" = hub `data_entrega`; plus `gravacao_em`; `postado_em` stamped on Postado | §2.3 |
| D8 | **1:1 post ↔ headline and post ↔ roteiro** (unique), same marca enforced by composite FKs; the library keeps every row; unbind ≠ delete | §3 |
| D9 | **Roteiro reprocess moves the binding** to the new version | §3.5 |
| D10 | **Legenda by AI** (DRAFT prompt from the legacy copy rules), returned for editing, never auto-saved; 40/day/user | §5.3 |
| D11 | **Target account** = optional `conta_id` among the marca's connected IG accounts | §0.10 |
| D12 | **Marca filter** with "Todas as marcas" (unlike the per-marca switcher of the other pages), remembered in the URL | §6.1 |

## 12 · Open questions (owner)

1. **Carousel generation (Carrosséis):** keep it as its own CoreStudio page (default), or retire it?
   Its 6 drafts belong to one org and have been untouched since 2026-07-27. Retiring loses storyboard, image and render, and is irreversible in UX terms; the data would stay.
2. **Production visibility:** confirm Branding and Carrosséis stay `producao` for all users while the
   rest of CoreStudio is `desenvolvimento`.
3. **Team (D5):** is a separate content team (`cs_equipe`, freelancers without a login) right, or
   should assignees be platform users only?
4. **Move rules (D3):** free forward, or igig's one-step-at-a-time?
5. **Publishing:** in phase 2, should "Postado" publish to Instagram from the card (needs Meta App Review
   of the publish scope; `PublishService` exists), or stay manual with a permalink?
6. **Roteiro audit:** do you want the legacy **score** (8-criteria Método Audience audit) adapted to
   roteiros inside the card (phase 2)?
7. **Roteiro beat order:** the roteiro prompt uses its own 9-beat order (CTA split in two +
   Apresentação Magnética at the end), which contradicts the Método's "CTA last". Which one is right?
8. **Legacy reel drafts:** import the 4 `reels` drafts of `mc_posts` into the Esteira as Ideação cards,
   or leave them in Carrosséis (default)?
