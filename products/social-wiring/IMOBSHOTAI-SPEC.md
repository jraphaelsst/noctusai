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
| Nav | `frontend/src/nav/navGroups.ts` `CORESTUDIO_GROUP.groups` (sub-group pattern on unmerged `feat/corestudio-edicao-imagem-nav`) | Sub-group `imobshotai` **absorbs** the "Edição de Imagem" sub-group (D2, §9); each page needs a `status_pagina` row (migration) or it stays hidden. |
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
- The card is **created at the first upload** for that ref (D1) and shows "em edição" right away. A second upload for the same ref reuses the card (get-or-create).

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

Access tier: **org-member** for reads and creation. The `decisao` routes (photo and video approval) require **org admin or platform admin** (D6). No `public`. Strict `== 401` tests on every route, plus `403` for a non-admin member on `decisao`.

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
| S8 | Absorb Edição de Imagem (§9): wiring audit, nav move, config sub-group, `/edicao-fotos/*` redirects | S3, S4 | FE nav + redirects |
| S9 | Manual photo editor (§10): promote the editor shell to `@noctusai/lib` if needed, then photo tools + manual versions | video-editor module located; S4 | FE (+ lib) |
| S10 | Music library (D5): track table + licensed source adapter (Fake+Real+factory) + picker in video step 3 | Q7 decided; S6 | BE + FE |

Pilot-first: S2–S5 ship for One's org only (it is the only real-estate client with the data), then open up.

## 8 · Owner decisions (2026-11-13)

| # | Question | Decision |
|---|---|---|
| D1 | When is the card created? | **At the first upload.** The card shows "em edição" from the start (§3.3 updated). |
| D2 | ImobShotAI vs "Edição de Imagem" | ImobShotAI **absorbs** Edição de Imagem. It is not a "replace": everything of value there is carried into ImobShotAI (§9). |
| D3 | Manual editing | A **manual photo-editing module**, the photo twin of the CoreStudio video-editing module (tools from the real CoreStudio app), for hand-editing one or two photos (§10). |
| D4 | Video formats v1 | **Both** 9:16 and 16:9 (1:1 optional). |
| D5 | Music | A **built-in library** of tracks free of copyright claims. Research in flight → `_private-studies/one-imoveis/MUSIC-LIBRARIES.md`; the key test is a license that allows use in videos a SaaS renders for its clients. |
| D6 | Who approves (photos and video) | **Org admin and platform admin only**, for now. Approval endpoints check that role, and the strict-auth tests cover a non-admin member (`403`). |
| D7 | Direction | CoreStudio's processes will be **enhanced with the new agents and methodologies** (general video-editing agent, real-estate photo/video agents). ImobShotAI is the first place they land, not a dead end. |

Still open: **Q6** — the third-party ImobShotAI app study (`_private-studies/imobshotai/STUDY-app.md`, pending) gets reviewed when it lands, as reference only.

## 9 · Absorbing "Edição de Imagem" (D2)

Absorb means its value moves into ImobShotAI, and nothing useful is lost or duplicated. Inventory (from `modules/edicao_fotos/`, pages `/edicao-fotos/*`):

| Asset in Edição de Imagem | Fate in ImobShotAI |
|---|---|
| Lotes + photo state machine + `fotos_eventos` | **Kept as the engine** of the photo funnel (§2). |
| Worker (seed `domain.jobs`), engine `domain.photo_editing`, urgente/econômico (OpenAI direct/Batch), `ProcessingGate` | Kept as is. |
| Guias, regras, referências, modelos | Kept. They become **"Estilos"** in the funnel's step 3, and the real-estate photo agent writes the default guia. |
| Curadores, revisão (`LoteRevisao`), decisões, avaliações | Kept, merged into step 5 and the approval rule (D6). |
| Aprendizado / `fotos_dataset` | Kept and fed by One's dataset (`dataset/photos.csv`) plus every approve/reject. It is the training loop for good-edit and room recognition. |
| Painel, processamento, configurações | They move to an "ImobShotAI · Configurações" sub-group (admin only). |
| Routes `/edicao-fotos/*` | Redirect to `/imobshotai/*` (the existing redirect-page pattern, e.g. `RedirectMediaCreation`). No dead links. |

Before the redirect lands, `noc-wiring-audit` runs on every current Edição de Imagem page so we know what is really wired (real data + own CRUD) and nothing working is dropped.

## 10 · Manual photo editor (D3)

- **Shape:** the photo twin of the CoreStudio **Twin video editor**, which is a design spec and not built yet: `projects/core-studio-build/specs/twin-editor-design.md` (W3-1, deferred to T3). Its principle carries over as is: **"the AI edits, you adjust"**. Every control opens already filled by the AI (marked as the AI's choice), with "outra opção" next to the manual override, and a photo that needs no change is approved without opening the editor.
- **Reused from the twin spec, and built once as shared `@noctusai/lib` components** (whichever editor is built first creates them; the other consumes them): header with `SaveIndicator` + undo/redo, a preview canvas plus a tab panel, the **command stack** (each edit is a command; ⌘Z/⇧⌘Z), **autosave** (800 ms debounced PATCH with If-Match, "não salvo" + retry, `beforeunload` guard), and `RenderPanel`. The photo version has no scene strip; it has a **photo strip** of the property's photos (by room).
- **Edit preset** (twin §0.2 analog): a per-workspace, versioned real-estate preset (per-room recipes from the photo agent). It is the same object as the funnel's "Estilo" (§9).
- **AI self-check** (twin §0.3 analog) flags a photo as "precisa de atenção" when the fidelity gate fails (geometry, windows or fixtures moved vs the original), the room is uncertain, an exterior sky was replaced on an interior, or a declutter happened without the "imagem ilustrativa" label.
- **Opens from:** the funnel's review step and the card detail ("editar à mão"), on one photo at a time.
- **Tools v1 (real-estate set):** crop/aspect, straighten + vertical correction (perspective), exposure/contrast/highlights/shadows, white balance, window pull (balance blown windows), sky replace, object removal / clean-up, before/after toggle. AI tools (sky, removal) call the same `photo_editing` engine. Manual sliders are client-side and only persist the result.
- **Data:** a manual edit is a new version of the photo (`fotos_edicoes`, with `origem = manual`) plus an event. It never overwrites, so the dataset can learn from human corrections against AI output.

## 11 · Lessons from the third-party app study (reference only)

Source: `_private-studies/imobshotai/STUDY-app.md` (outside git; nothing copied). Its edit is one fixed OpenAI prompt per photo, with no room logic and no QC. Its video is a plain ffmpeg Ken Burns slideshow and is switched **off** in production. Properties live only on the phone. What we take as **our own design decisions**:

| Lesson | Lands in |
|---|---|
| Per-photo **idempotent job id** + ledger: reserve → process → store → confirm, or refund; "recover, don't recharge" before a retry | photo events: `foto_edicao_reservada / _concluida / _estornada` in `fotos_eventos`; cost per property (§3.4) |
| **Room first, then a per-room recipe**, plus a **fidelity gate** (edge/structure diff vs the input) before human review | photo agent `.md` + engine step; self-check (§10) |
| Keep the **original and the edit side by side**; never overwrite | card detail + review (already the model in `fotos_edicoes`) |
| **Watermark at delivery, not in storage** (agency logo, per viewer/role) | card export/download path |
| Preserve input aspect and resolution; **pin the model version** + content hash on every event | engine config + events |
| **Deterministic video baseline**: the motion cycle (push-in / pan / pull-out), eased zoom, 0.5 s crossfades, music fade in/out, x264 + faststart. The agent picks the move per room and the order; it does not generate pixels | video agent `.md` + the `video.render` job |
| **9:16 and 16:9 from the same timeline**, with per-photo crop and pans along the long axis; upscale stills before zoompan | D4; video step 3 |
| Story: opening card (ref, bairro, price), room captions, end card with logo + broker CTA, −14 LUFS, cuts on the beat | video framework (to be confirmed against One's real videos in `STUDY-videos.md`) |
| Explicit **consent naming the AI vendor** before upload | photo funnel step 2 (with an LGPD check by `legal-advisor`) |
| Real raw broker photos + an approved "golden" per room as the **eval set** | photo agent eval; One dataset |
| Later: **level-gated mobile capture** (auto-shutter when level, ultra-wide) fixes verticals cheaper than AI | roadmap only (no mobile app today) |

## 12 · Open questions

- **Q6** Third-party app study impact (above).
- **Q7** Music: pick the tier once `MUSIC-LIBRARIES.md` lands (free CC0/AI-generated set vs a paid partner API).
