# ImobShotAI — spec + slice plan (social-wiring · CoreStudio)

> **Status:** PLAN ONLY (2026-11-13). No product code until the owner says **go**.
> **Sequencing gate:** implementation starts AFTER the general video-editing agent (session aa2f7b) is done,
> and the real-estate photo/video agents (`.md`) are drafted from One's specs.
> Owner direction: memory `project_editing_agents_and_imobshotai`. Data study: `_private-studies/one-imoveis/` (outside git).

## 1 · What it is

An **"ImobShotAI" group in the CoreStudio nav** with two **separate** processes, both anchored to an existing property:

| Process | In | Out |
|---|---|---|
| **Fotos** | a few raw property photos | edited "beautiful" photos, tagged per room |
| **Vídeo** | the property's **approved edited photos** | the property video (per One's video framework) |

Every property that has finished photos gets a **property card** (funnel-like) that stores its photos and videos and shows which stage it is in.
Both pages are **funnels** (step-by-step creation wizards).

## 2 · Ground truth this spec builds on (verified on origin/dev, 2026-11-13)

| Need | Existing mechanism | Decision |
|---|---|---|
| Property-ref search | `GET /api/imoveis/busca?q=&limit=` (`routers/imoveis_router.py:115`, `imovel_hub/busca_service.py:439`; `q` ≥ 2 chars; mirror `social_wiring.imoveis.codigo` + `imovel_registry.codigo_canonical`) | **Reuse.** No new search endpoint. |
| Live-search dropdown | `frontend/src/components/card/ImovelCodigoPicker.tsx:94` (+ `ImovelBuscaTypeahead.tsx`) | **Reuse** in select-only mode: the value can only come from a result row, never free text. |
| Photo batches + editing | `edicao_fotos`: `fotos_lotes` already has `imovel_codigo` + `imovel_org_id` (mig 123); photo state machine `fotos_fotos.status`; events `fotos_eventos`; worker on seed `domain.jobs` + engine `noctusai_lib.domain.photo_editing`; guias/regras/referências/modelos | **Reuse the lote as the photo job.** ImobShotAI = a lote with a **mandatory** imóvel + the real-estate guia. No parallel photo pipeline. |
| Nav | `frontend/src/nav/navGroups.ts` `CORESTUDIO_GROUP.groups` (sub-group pattern on unmerged `feat/corestudio-edicao-imagem-nav`) | New sub-group `imobshotai`; each page needs a `status_pagina` row (migration) or it stays hidden. |
| Funnel/board UI | seed `components/pipeline/funnel/FunnelBoard.tsx`, `PipelineBoard.tsx`, `kanban/*`; used by `EsteiraBoard.tsx` | **Consume the seed organ** for the card board (`check_canonical_organ_consumption`). |
| Video | **Nothing exists.** `CORESTUDIO-STRUCTURE.md` §3 (unmerged `feat/corestudio-structure`) designs a `video.*` job family, one container per job, SSE progress, signed-URL prefixes, `domain.video_editing` at L0 | ImobShotAI Vídeo is the **first consumer** of that seam, not its own worker. Blocked on it. |
| Uploads / progress / approvals | seed `resumable_uploads`, `job_progress` (SSE), `approvals` organ: all three are **unmerged branches** | Consume once landed; prerequisite S0. |

## 3 · Domain model (EOA + measurement-by-design)

### 3.1 The property card: `imobshot_cards`
One row per `(org_id, imovel_codigo)`. It is the container and the funnel position.

| column | type | note |
|---|---|---|
| `id` | uuid pk | |
| `org_id` | uuid | RLS |
| `imovel_org_id`, `imovel_codigo` | | same pair as `fotos_lotes` (FK-by-value to the mirror/registry, validated on create) |
| `etapa` | enum | see 3.3 |
| `capa_foto_id` | uuid null | cover = best-scored approved fachada/sala |
| `created_at`, `updated_at`, `fotos_concluidas_at`, `video_concluido_at` | timestamptz | dated first-class |

- Photos live where they already live (`fotos_fotos`, via `fotos_lotes.imovel_codigo`). The card **does not copy them**; it links lotes by `card_id` (new nullable column on `fotos_lotes`).
- Videos: `imobshot_videos` (`id, card_id, org_id, formato (vertical_9_16|horizontal_16_9|quadrado_1_1), duracao_alvo_s, status, job_id, storage_key, poster_key, aprovado_at`), and `imobshot_video_fotos` (`video_id, foto_id, ordem, comodo`) for the ordered shot list.
- **Events:** `imobshot_eventos` (append-only, `tipo`, `card_id`, `video_id?`, `etapa_de`, `etapa_para`, `detalhe jsonb`, `actor`, `at`), written in the same transaction as every state change. No hand-written history table.

### 3.2 Hard gate: no property, no upload
- **Server-side (the real gate):** the ImobShotAI lote-create path rejects a missing ref or one that does not resolve in `imoveis`/`imovel_registry` for that org → `422 imovel_inexistente`. The dropdown is UX, not the gate.
- **Client:** `ImovelCodigoPicker` in select-only mode. Typing `ONE89` lists `ONE8990`. An unknown ref shows "Nenhum imóvel com esse código" and the upload step stays disabled.
- ⚠ To verify in S1: whether `POST /api/edicao-fotos/lotes` validates `imovel` existence today (not confirmed). If it does not, the fix belongs in the lote service (benefits plain Edição de Imagem too), not in an ImobShotAI fork.

### 3.3 Card funnel stages (`etapa`)
`fotos_enviadas → fotos_em_edicao → fotos_em_revisao → fotos_aprovadas → video_em_montagem → video_renderizando → video_em_revisao → concluido` (+ `arquivado`).
- Photo stages are **derived from the lote/photo states** (projection), not set by hand.
- The card is **created** when the first ImobShotAI lote for that ref is submitted. (The owner said "when photos are done". Open question Q1: create at the start and show progress, or only at `fotos_aprovadas`.)

### 3.4 Metrics enabled
Time from upload to approved photos per property; photo approval/rejection rate per room and per guia; re-edit count; video approvals on the first render; properties with photos but no video (funnel drop-off); and cost per property (OpenAI edit + render).

## 4 · The two funnels (pages)

### 4.1 `/imobshotai/fotos/novo`: photo funnel
1. **Imóvel**: live-search picker (required). Shows the title, bairro and cover photo of the match. If a card already exists: "continuar no card".
2. **Fotos**: resumable upload (seed). Optional pull of the property's Vista photos (existing `/{id}/vista` route).
3. **Estilo**: the real-estate guia, pre-selected (from the photo-agent spec). Velocidade urgente/econômico (existing field).
4. **Processando**: SSE progress per photo (seed `job_progress`), with the room tag shown as it is classified.
5. **Revisão**: before/after per room. Approve, reject with a reason, or re-edit (existing `LoteRevisao` behaviour, embedded).
6. **Pronto**: the card moves to `fotos_aprovadas`. CTA "Criar vídeo deste imóvel".

### 4.2 `/imobshotai/video/novo`: video funnel
1. **Imóvel**: picker limited to cards at `fotos_aprovadas` or later.
2. **Fotos e ordem**: approved photos pre-ordered by the One room order (from `STUDY-videos.md`). Drag to reorder and pick the cover.
3. **Formato**: 9:16 / 16:9 / 1:1, target duration, music, branding (logo, phone, ref), text overlays (price, metragem, dorms).
4. **Roteiro / timeline**: the video agent proposes a shot list (room, duration, motion such as Ken Burns push-in or pan, transition, overlays). The user edits it.
5. **Render**: `video.*` job with SSE progress and an H.264 preview + poster.
6. **Revisão**: approve or reject with a reason (seed `approvals`). Approval moves the card to `concluido`. Hand-off to Redes Sociais via `PublishRequest` is later.

### 4.3 `/imobshotai`: the board
Seed `FunnelBoard` with one column per `etapa` and one card per property (cover, ref, bairro, photo count, video count, age in stage). Opening a card shows a detail page with its photos (by room), videos and event timeline.

## 5 · Endpoint contract (draft, to be frozen in S1 via `noc-contract-first`)

| Method · path | Purpose |
|---|---|
| `GET /api/imoveis/busca?q=` | (existing) ref live search |
| `POST /api/imobshotai/cards` `{imovel_codigo}` | get-or-create card; 422 `imovel_inexistente` |
| `GET /api/imobshotai/cards?etapa=` | board |
| `GET /api/imobshotai/cards/{id}` | card detail: lotes, photos by room, videos, events |
| `POST /api/edicao-fotos/lotes` `{imovel, card_id, guia}` | (existing, extended) photo batch bound to the card |
| `POST /api/imobshotai/cards/{id}/videos` `{formato, duracao_alvo_s, fotos:[{foto_id, ordem}]}` | draft video |
| `POST /api/imobshotai/videos/{id}/roteiro` | agent proposes a timeline (sync or job) |
| `POST /api/imobshotai/videos/{id}/render` | enqueue `video.render`; returns `job_id` (cache-writes hand-off to polling/SSE) |
| `POST /api/imobshotai/videos/{id}/decisao` `{decisao, motivo}` | approval via the seed organ |

Access tier: **org-member** for all of them (no `public`). Strict `== 401` tests on every route.

## 6 · Agents (built before implementation, `.md` first)

| Agent | Built from | Lands as | Consumed by |
|---|---|---|---|
| General video editor ("Diretor de Edição") | course studies (aa2f7b) | `.claude/agents` + skills | reference shape |
| Real-estate **photo** editor | `_private-studies/one-imoveis/STUDY-fotos.md` + `dataset/photos.csv` | `.md` agent + skill | ImobShotAI photo step 3 → turned into the **real-estate guia + regras** of `edicao_fotos` (that engine already takes guias) |
| Real-estate **video** editor | `STUDY-videos.md` (room order, shot durations, motion, overlays, branding) | `.md` agent + skill | video step 4 (roteiro) |

Later, per the owner, both move into the agents product and are called via API. The `roteiro` endpoint is the seam where that swap happens.

## 7 · Slice plan

| # | Slice | Depends on | Collision class |
|---|---|---|---|
| S0 | Land prerequisites: `feat/corestudio-edicao-imagem-nav`, `feat/seed-resumable-uploads`, `feat/seed-sse-job-progress`, `feat/seed-approvals-organ`; settle `feat/corestudio-structure` | owners of those branches | n/a |
| S1 | Contract freeze (`noc-contract-first`) + verify/fix the server-side imóvel gate on lote create | S0 | BE lote service |
| S2 | BE: migration `imobshot_cards` / `imobshot_eventos` / `fotos_lotes.card_id` + RLS + tier + card service/router + etapa projection from lote states | S1 | BE new module |
| S3 | FE: nav sub-group + `status_pagina` rows + `/imobshotai` board (seed FunnelBoard) + card detail | S1 (contract) | FE, parallel with S2 |
| S4 | FE: photo funnel (picker select-only, upload, guia, progress, embedded revisão) | S2, S3, real-estate guia from the photo agent | FE |
| S5 | Real-estate guia/regras seeded into `edicao_fotos` from the photo agent spec; room classification output stored per photo | photo agent `.md` | BE data |
| S6 | Video: `imobshot_videos` tables + endpoints + video funnel UI | CoreStudio `video.*` seam built, general + real-estate video agents | BE + FE |
| S7 | Metrics view + latency_report + wiring audit | S4, S6 | — |

Pilot-first: S2–S5 ship for One's org only (it is the only real-estate client with the data), then open up.

## 8 · Open questions for the owner

- **Q1** Card creation: at the first upload (it shows "em edição") or only once the photos are approved?
- **Q2** Should ImobShotAI replace "Edição de Imagem" for real-estate orgs, or sit next to it? (Same engine either way.)
- **Q3** Video formats for v1: 9:16 only (reels/shorts) or also 16:9 for YouTube, like One's current videos?
- **Q4** Music: royalty-free library we pick, or a track the user uploads?
- **Q5** Who approves: any org member (the approvals-organ default) or a named curator (the `curadores` already in `edicao_fotos`)?
- **Q6** Should the third-party ImobShotAI app study (`_private-studies/imobshotai/STUDY-app.md`, pending) change anything here? It gets reviewed when it lands, as reference only.
