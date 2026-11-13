# CoreStudio: structure of the media creator

> **Status:** recommendation (product-architect, 2026-11-13). Scope, variety and priority are the owner's.
> **What this is:** the STRUCTURE of CoreStudio as THE media-creation module of social-wiring: which function lives where, what it shares, the pipeline states and their events, and the seams a future video worker plugs into.
> **What this is not:** the image or video EDITING specs. Those come from the owner's course material and fill the named empty slots in §1.3 and §3.
> **Owner direction (2026-11-13):** everything about creating posts (images and videos) lives in CoreStudio. Workflow: headline → roteiro → roteiro approval → media (carousel / image / video) → media approval → automated posting and management through Redes Sociais. `edicao_fotos` moves under CoreStudio. Existing URLs never move.
> All file:line references are against `origin/dev` @ `8f32496d2`. Paths are relative to `products/social-wiring/` unless they start with `seed/`.

---

## 0. Function structure (the jobs, in the owner's words)

1. Find what to talk about (pesquisa, virais, segundo cérebro).
2. Write the hook (headline).
3. Write the script from the hook (roteiro), then have it approved.
4. Make the media: carousel, single image, video. Edit photos and videos.
5. Have the media approved.
6. Schedule it, publish it, and manage it after publishing (Redes Sociais).
7. Keep the brand consistent (branding, brand kits) and keep the reference library (biblioteca).

---

## 1. Allocation

### 1.1 Function-to-organ allocation table

Layer key (proposal, the architect ratifies): **L0** seed, all families · **L1** market seed · **L2** this product, behind a seam · **L3** org setting or pack.
Status: **exists** · **extend via seam** · **new** · **slot** (empty until the owner's specs land).

| Submodule | Function | Allocated to (carried by) | Layer | Status |
|---|---|---|---|---|
| Pesquisa | research sources, extraction, viral subjects | `media_creation/routers/pesquisa*.py`, `services/pesquisa_extracao_service.py`, `services/assuntos_virais_service.py`; queue = seed `noctusai_lib.domain.jobs` (via `services/geracao_jobs.py:42-58`) | L2 | exists |
| Segundo Cérebro | per-brand knowledge base, synthesis, review | `routers/cerebro*.py`, `services/cerebro_*`, `cerebro_scheduler.py`; LLM = seed `noctusai_lib.integrations.llm` (budget `enforce_budget`, `geracao_jobs.py:40`); transcription = seed `noctusai_lib.integrations.transcription` | L2 | exists |
| Headlines / Roteiros | generate headlines in batches; generate roteiro from headline (questions → generation), edit with optimistic version, feedback, reprocess | `routers/headlines.py`, `routers/roteiros.py`, `services/headline_pipeline.py`, `services/roteiro_service.py:455-514`; jobs `headline.gerar`, `roteiro.perguntas`, `roteiro.gerar` (`geracao_jobs.py:60`); stale/dead-letter sweep `geracao_scheduler.py:1-20` | L2 | exists (no approval step, see §2) |
| Esteira | the board a post travels on (ideação → postado), gate before gravação, card hub (team, docs, timeline, reminders) | seed `noctusai_lib.domain.pipeline` (`PipelineConfig`, `move_card`) + seed `noctusai_lib.domain.card_hub` (`esteira_config.py:17-91`); service `services/esteira_service.py` | L0 organs, L2 config | exists |
| Carrosséis | slide design, render, publish carousel | `design/svg_slides.py`, `design/tokens.py`, `routers/posts.py`, `routers/generation.py`, `services/generation_service.py`, `services/publish_service.py`; publish adapter = seed `noctusai_lib.integrations.meta` (`publish_service.py:24-29`) | L2 over L0 adapter | exists |
| Imagens (= Edição de Fotos) | batches (lotes), AI edit per edit type, human review, style guides, rules, curators, models | `modules/edicao_fotos/*`; engine = seed `noctusai_lib.domain.photo_editing` (`ProcessingGate`, `build_worker`, `edicao_fotos/services/worker.py:35`), jobs = seed `domain.jobs`; storage = seed `integrations.storage` | L0 engine, L2 module | exists; **editing rules = SLOT `IMG-EDIT`** |
| Vídeos | cut, captions, overlays, preview, export | nothing today. Structure in §3 (worker seams). Editing operations = **SLOT `VID-EDIT`** | to decide (§3.8) | **new / slot** |
| Biblioteca | reference library of profiles and posts, classification, transcription, opt-out and retention purge | `routers/biblioteca.py`, `services/biblioteca_*`, `biblioteca_scheduler.py`; purge `services/biblioteca_service.py:240-290` | L2 | exists |
| Branding | brand tokens, brand kits, component previews (untrusted HTML guarded) | `branding/bundle.py`, `branding/tokens_schema.py`, `branding/html_guard.py:1-12`, `routers/brand_kits.py`, `routers/branding.py` | L2 | exists |
| (cross) Aprovação | approve roteiro; approve media | nothing generic in CoreStudio. Closest shape: the human review in `edicao_fotos/routers/revisao.py` + `services/review.py` (per-photo approve/reject) | candidate L0 (`domain.approvals`), see §2.3 | **new** |
| (cross) Agendar / publicar / gerir | schedule a post, publish at time T, read back metrics | publish now exists for carousels (`publish_service.py:65-154`); no scheduled publish; YouTube upload exists in `modules/youtube/services/upload.py`; the `modules/scheduling` module is VISIT scheduling (imóveis), not post scheduling (`modules/scheduling/engine.py:1-8`) | interface to Redes Sociais (§1.4) | **partial** |

### 1.2 Two post tables today (a structural finding)

- `cs_posts` is the esteira card (reels; `formato` hard-set to `"reel"`, `esteira_service.py:423`).
- `mc_posts` + `mc_post_slides` is the carousel post with its own `status ∈ {draft, ready, published}` (`schemas/posts.py:9`) and its own publish state (`publish_service.py:131-146`).

Two homes for one function ("a post being made") is a fork in waiting. **Recommendation:** `cs_posts` is THE post; `formato` becomes an enum (`reel | carrossel | imagem | video`) and a carousel's slides hang off the post. `mc_posts` stays readable until migrated. Hand-off to architect (schema). Owner question Q3.

### 1.3 Named empty slots (filled by the owner's course extraction)

| Slot | Holds | Plugs into |
|---|---|---|
| `IMG-EDIT` | photo-editing operations, edit types beyond today's (`cor_luz`, `ceu`, `declutter`, `staging_virtual`), style-guide rules, acceptance criteria | seed `domain.photo_editing` edit-type registry + `edicao_fotos` guias/regras |
| `VID-EDIT` | video operations (cut, captions, b-roll, overlays, music, aspect ratios), per-format presets, acceptance criteria | the `VideoEditJob` payload contract (§3.1) |
| `VID-TEMPLATES` | reusable video templates per brand | Branding tokens + brand kits |
| `MEDIA-APPROVAL-CRITERIA` | what a reviewer checks before approving media | the approval organ (§2.3) |

### 1.4 Capability interfaces to Redes Sociais

Link, never merge. CoreStudio produces an **approved media asset**; Redes Sociais publishes and manages it.

| Interface | Direction | Shape (capability level) |
|---|---|---|
| `PublishRequest` | CoreStudio → Redes Sociais | post id, approved asset version (storage paths), caption, target account (`conta_id`), target surface (IG carousel / IG reel / IG single / FB / YouTube / Shorts), `publicar_em` |
| `PublishOutcome` | Redes Sociais → CoreStudio | `agendado` / `publicado` (media id, permalink, published_at) / `falhou` (reason enum, incl. `meta_scope_pending_app_review`) |
| `PostMetrics` | Redes Sociais → CoreStudio | per published post: reach, views, likes, comments, saves (feeds Biblioteca and Segundo Cérebro) |
| `AccountCatalog` | Redes Sociais → CoreStudio | accounts a brand may post to (today read by `esteira_service._conta`, `esteira_service.py:162-174`) |

`publish_service.py` today lives inside media_creation and calls Meta directly: it is the Redes Sociais side of `PublishRequest`. Recommendation: keep its code where it is for now, but route it through the `PublishRequest` contract so a scheduled-publish worker in Redes Sociais can take it over without CoreStudio changing.

### 1.5 Variant matrix

| Varies by | Mechanism | Example |
|---|---|---|
| Org | setting (L3) | esteira stage names/order (stages are rows, code keys on ROLES only, `esteira_config.py:9-10`) |
| Org | setting (L3) | photo processing on/off (`fotos_platform_settings.processamento_ativo`, `edicao_fotos/services/worker.py:7-11`) |
| Brand (marca) | data | brand kit, tokens, cérebro, accounts |
| Format | enum on the post | reel / carrossel / imagem / video (proposed, §1.2) |
| Target surface | enum on `PublishRequest` | IG / FB / YouTube / Shorts |
| Tier | plan feature flag | video module, number of renders/month (owner question Q4) |
| Client pack | never a fork | an `if org == …` branch is refused |

### 1.6 Should `edicao_fotos` move physically under `media_creation`?

**Option A, physical move** (`app/modules/media_creation/edicao_fotos/…`):
- Touches 38 files / 102 import occurrences (`app.modules.edicao_fotos` across app, tests, lifespan, config, migrations' comments, contracts), plus `main.py:352,427,688,703` (register + body-size overrides) and `app/lifespan.py`.
- Gains nothing at runtime: routes, schema tables (`fotos_*`), storage bucket and status_pagina keys do not change either way.
- Risk: a large rename collides with the parallel nav move and any in-flight edicao_fotos work; `media_creation/__init__.py` grows a second worker lifecycle and a second set of platform switches.

**Option B, sibling package owned by CoreStudio** (recommended):
- `app/modules/edicao_fotos/` stays where it is. Ownership is declared, not moved: (1) a one-line ownership note in both packages' `__init__` docstrings ("part of CoreStudio"), (2) CoreStudio's nav group lists the edicao-fotos pages (the FE engineer's change in flight), (3) the module catalog / product docs list Imagens under CoreStudio.
- The seam between the two is the asset: a photo approved in Edição de Fotos becomes an asset a post can use (§2.3, media asset rows). Neither package imports the other's internals.
- Cost: near zero (docs + nav, already in flight).

**Recommendation: B.** Ownership is a product fact; the package path is an implementation detail. A move costs ~100 import edits and buys no behaviour. Revisit only if the two packages start sharing internals, which the asset seam is designed to avoid.

**status_pagina keys and URLs:** unchanged under both options. Keys stay `edicao-fotos`, `edicao-fotos-novo-lote`, `edicao-fotos-painel`, `edicao-fotos-processamento`, `edicao-fotos-configuracoes`, `edicao-fotos-referencias`, `edicao-fotos-guias`, `edicao-fotos-regras`, `edicao-fotos-curadores`, `edicao-fotos-modelos` (`frontend/src/nav/navGroups.ts:185-196`); URLs stay `/edicao-fotos/*`. Only the nav GROUP changes (cms → CoreStudio), which the `navGroups.ts` header allows because every item keeps its existing key (`navGroups.ts:10-13`). The new Vídeos slot gets NEW keys under a new prefix (proposal `/geracao/videos`, keys `geracao-videos*`), never by renaming an existing key.

---

## 2. Pipeline state machine

Target: `headline → roteiro → roteiro_aprovado → midia_em_producao → midia_aprovada → agendado → publicado` (+ `cancelado`, `falhou`).

### 2.1 What exists today

| Concern | Today | Evidence |
|---|---|---|
| Board states | esteira stages `ideacao → headline_roteiro → gravacao → edicao → pronto → postado`, `bloqueado_cancelado`; roles `gravacao`, `postado`, `cancelado` | `esteira_config.py:41-56` |
| Board move | seed `move_card` writes the stage change; backwards / cancel / leave-cancel need a `motivo` | `esteira_service.py:471-536`, motivo `:490-491` |
| Move event | every move lands in `social_wiring.pipeline_movimentos` (seed pipeline), surfaced as the `movimento` timeline kind | `migrations/034_pipeline_funil_processos.sql:159`, `esteira_config.py:86` |
| Gate | moving to `gravacao` or later needs a headline AND a roteiro whose status is `completo` | `esteira_service.py:352-385` |
| Headline batch status | `criando → processando → completo / falha` | `migrations/229_cs_geracao.sql:257` |
| Roteiro status | `criando → perguntas → processando → completo / falha`; edit with optimistic `versao`; feedback; reprocess creates a NEW roteiro | `229_cs_geracao.sql:333`; `roteiro_service.py:455-514` |
| Stale / dead-letter | rows in `criando`/`processando` untouched 15 min → `falha`; dead-lettered jobs reconcile the domain row | `geracao_scheduler.py:1-20` |
| Postado | moving to the `postado` role stamps `postado_em` and an optional manual `permalink` | `esteira_service.py:494-498` |
| Carousel publish | publish-now to IG carousel / IG single / FB photo; overwrites `mc_posts.status='published'` + media id + permalink | `publish_service.py:65-154`, write `:131-146` |
| Photo review | per-photo approve/reject in Edição de Fotos | `edicao_fotos/routers/revisao.py`, `services/review.py` |

### 2.2 What is missing

1. **Roteiro approval.** `completo` means "the AI finished", not "a human approved". The gate (`esteira_service.py:360`) accepts an unapproved roteiro.
2. **Media as a first-class, versioned thing on the post.** Reels have no media rows at all (production lives outside, `links_producao`); carousels live in the separate `mc_posts`.
3. **Media approval.** No approve/reject for a carousel, image or video.
4. **Agendado.** No `publicar_em`, no scheduled-publish worker; `postado` is a manual move.
5. **Publish link-back.** `publish_service` does not move the esteira card; manual `postado` does not call publish. Two truths.
6. **Events.** Headline, roteiro and `mc_posts` status changes are column overwrites, no event row. Publish is an overwrite (`publish_service.py:132-146`). Only the board move is evented.

### 2.3 Proposed states and transitions

The post (`cs_posts`) is the aggregate. The esteira board stays the visual; the states below are post-level facts the board gates on (code keys on ROLES, so new roles are added, never slugs).

| # | From → To | Trigger | Guard | Event recorded (append-only, same transaction) |
|---|---|---|---|---|
| T1 | — → `ideia` | create post | brand valid | `post_criado` (post, marca, formato, actor) |
| T2 | `ideia` → `headline_definida` | bind/create headline | headline not in another post | `headline_vinculada` (headline_id, origem ia/manual) |
| T3 | `headline_definida` → `roteiro_gerado` | roteiro job completes | status `completo` | `roteiro_gerado` (roteiro_id, versao, modelo, custo, duração) |
| T4 | `roteiro_gerado` → `roteiro_aprovado` | approve | approver has role; versao matches | `roteiro_aprovado` (roteiro_id, versao, aprovador) |
| T4r | `roteiro_gerado` → `roteiro_gerado` | reject / request changes | motivo required | `roteiro_reprovado` (versao, motivo enum + texto) |
| T5 | `roteiro_aprovado` → `midia_em_producao` | first media job queued or upload | approved roteiro bound | `midia_iniciada` (formato, job_id or upload) |
| T6 | `midia_em_producao` → `midia_pronta` | render/edit job succeeds | asset version stored | `midia_versao_criada` (asset_id, versao, job_id, duração, custo) |
| T6f | `midia_em_producao` → `midia_em_producao` | job fails / dead-letters | — | `midia_job_falhou` (job_id, reason enum, tentativa) |
| T7 | `midia_pronta` → `midia_aprovada` | approve | approves a specific asset version | `midia_aprovada` (asset_id, versao, aprovador) |
| T7r | `midia_pronta` → `midia_em_producao` | reject | motivo required | `midia_reprovada` (asset_id, versao, motivo) |
| T8 | `midia_aprovada` → `agendado` | schedule via `PublishRequest` | account valid; time in future; approved version | `publicacao_agendada` (conta, superfície, publicar_em) |
| T9 | `agendado` → `publicado` | Redes Sociais `PublishOutcome` | — | `publicado` (media id, permalink, published_at) |
| T9f | `agendado` → `falhou_publicacao` | `PublishOutcome` falhou | — | `publicacao_falhou` (reason enum) |
| T10 | any → `cancelado` | cancel | motivo required | `post_cancelado` (motivo) |

Board mapping (proposal): `headline_roteiro` stage gates on T4 (not on `completo`); `edicao` ⇄ `midia_em_producao`/`midia_pronta`; `pronto` ⇄ `midia_aprovada`; new role `agendado`; `postado` is set by T9, no longer by a hand move (the hand move stays for posts published outside, recording `publicado` with `origem=manual`).

Approval is generic across roteiro and media (and already exists ad hoc in photo review): **proposal** an L0 `approvals` organ (subject kind + id + version, decision enum, motivo, actor) that writes the event rows above. Hand-off to architect: placement (L0 vs L2), schema, EOA shape.

### 2.4 Metrics the events enable (measurement-by-design)

Time headline→roteiro aprovado; roteiro first-pass approval rate; reprovação reasons distribution; media versions per approved post; job failure rate and retries by job type; cost per approved post (LLM + render); time aprovado→publicado; scheduled-vs-published drift; publish failure reasons; post performance (from `PostMetrics`) by headline template, roteiro estrutura and formato.

---

## 3. Seams for a future video-editing worker (structure only)

Editing operations are slot `VID-EDIT`. This section names only the containers they run in.

| # | Seam | Exists today | Missing |
|---|---|---|---|
| 3.1 | **Job queue with retry** | seed `domain.jobs` (`Worker`, `RetryPolicy`, lease + reclaim + heartbeat `extend_lease`, `seed/lib/backend/noctusai_lib/domain/jobs/migrations/jobs.sql.template:21-22,98-107,195-210`); used by Geração (`geracao_jobs.py:42-60`, retry `:58`) and Edição de Fotos (`edicao_fotos/services/worker.py:35-36`) | a `video.*` job family (`video.editar`, `video.preview`, `video.export`) with a `VideoEditJob` payload contract (asset in, operations = `VID-EDIT`, asset out); a dedicated queue/worker so long renders never starve Geração |
| 3.2 | **One throwaway sandbox per edit** | docker fleet on the VPS; transcription runs as its own server (`seed/lib/backend/noctusai_lib/integrations/transcription/server/engine.py:16-26`) | a sandbox runner: one short-lived container per job (no network except storage; CPU/mem/time limits; removed on exit). Today workers run INSIDE the product process (`worker.py:13-17`), which is fine for API calls and wrong for ffmpeg |
| 3.3 | **Sandbox holds no secrets; gets a signed URL scoped to one org/job prefix** | seed storage `signed_url` (download) on Supabase/local/fake (`seed/lib/backend/noctusai_lib/integrations/storage/supabase.py:244`, `protocol.py:96`) | signed UPLOAD URLs, and a prefix convention `org/<org_id>/jobs/<job_id>/{in,out,preview}/`; the dispatcher (not the sandbox) mints them; TTL ≈ job timeout |
| 3.4 | **Live progress over SSE** | seed `seed/lib/backend/noctusai_lib/realtime/sse.py` (`sse_event_stream` `:84`, `create_sse_router` `:152`); seed SSE job progress is being built in parallel | job progress events (`fase`, `pct`, `eta`) written by the worker, streamed per job/org; FE subscribes instead of polling (Geração UI polls today, `geracao_scheduler.py:3-5`) |
| 3.5 | **H.264 preview proxies** | nothing | a `video.preview` job: low-res H.264/AAC MP4 proxy + poster frame, stored under `preview/`, used by the editor and by approval (T7) |
| 3.6 | **Orphan-job sweeper** | lease reclaim in seed jobs (`jobs.sql.template:107`); domain sweeps `geracao_scheduler.py` (15 min stale → `falha`, dead-letter reconcile) on the seed scheduler | the same sweep for `video.*` + reaping sandboxes whose job is gone + deleting `jobs/<job_id>/` prefixes past retention |
| 3.7 | **Redes Sociais hand-off** | `publish_service.py` (images/carousels to Meta); YouTube upload (`modules/youtube/services/upload.py`) | `PublishRequest`/`PublishOutcome` (§1.4) for video (IG reels via resumable container upload, YouTube/Shorts), triggered by T8 |
| 3.8 | **Placement** | — | proposal: job contract + sandbox runner + preview job are L0 (any product making media needs them; a seed `domain.video_editing` mirroring `domain.photo_editing`), the CoreStudio Vídeos submodule is L2. Architect ratifies |

---

## 4. Gap table: "Arquitetura de software para editar centenas de vídeos" (Pythonando) on our stack

The video's ideas are taken from the owner's summary in the brief; the video itself was not fetched (unverified, see Sources). Stack: FastAPI + Supabase/Postgres + VPS docker fleet + React/TanStack.

| Idea | Our state | Evidence | Buildable now? |
|---|---|---|---|
| Per-job isolation | **gap** | workers run in-process (`edicao_fotos/services/worker.py:13-17`); no sandbox runner | design now (runner contract); build with VID-EDIT |
| SSE vs polling | **partial** | seed SSE exists (`realtime/sse.py:84,152`); Geração UI polls (`geracao_scheduler.py:3-5`) | **in progress in parallel (seed SSE job progress)**; CoreStudio adopts when it lands |
| Async web tier | **exists** | FastAPI; handlers that never await are threadpooled per the platform codemod (`noctus.dev.async_handlers_to_def`); heavy work goes to the queue | yes, already |
| Chunked resumable uploads (4 parallel, retry, resume, honest progress) | **gap** | Edição de Fotos uploads whole files in one multipart request, 256 MB cap (`edicao_fotos/routers/lotes.py:66,147-151`) | **in progress in parallel (seed resumable chunked uploads)**; then wire lotes + video upload |
| Queued tasks with retry | **exists** | seed `domain.jobs` + `RetryPolicy` (`geracao_jobs.py:58`), lease reclaim (`jobs.sql.template:107`) | yes; add `video.*` family when VID-EDIT lands |
| Signed URLs scoped per user/org instead of secrets | **partial** | download `signed_url` (`storage/supabase.py:244`); photo ports sign too (`seed/lib/backend/noctusai_lib/domain/photo_editing/ports.py:109`) | **yes, now**: signed upload URLs + per-org/job prefix convention |
| Second worker for previews | **gap** | no preview job | blocked on VID-EDIT (needs the proxy spec), contract can be named now |
| Beat-style orphan sweep | **exists (for Geração)** | `geracao_scheduler.py:1-20` on seed `api.scheduler` | yes; extend to video + storage prefixes when jobs exist |
| Storage tiering | **partial, judged** | retention purges exist (`biblioteca_service.py:240-290`); owner deletes audio for LGPD | **recommend NO hot/cold tiering for inputs**: delete raw inputs (and audio) after export + approval window; keep only the approved export + preview. Tiering keeps personal data longer, which LGPD minimisation argues against. Retention per prefix is buildable now |
| Blue-green deploy | **partial (equivalent)** | `noctus.dev.deploy_image` swaps with health probe + auto-rollback + boot smoke | no change needed for the web tier; long-running video jobs need drain-on-shutdown (seed `WorkerHandle` stop timeout 10 s, `worker.py:44`) or lease reclaim, which exists |
| Signed webhooks | **exists** | seed `security/webhook_signatures.py:176,224`; Meta `X-Hub-Signature-256` (`meta_ads/routers/leadgen_router.py:15,50`) | yes, already; reuse for any render-provider callback |
| Secrets encrypted at rest | **exists** | seed `security/encrypted_tokens.py:105,122` | yes, already |
| AI output treated as untrusted | **partial** | branding previews validated + sandboxed iframe (`branding/html_guard.py:1-12`) | **yes, now**: validate AI roteiro/caption output against a schema and length caps before it can reach publish; never let model output name storage paths or URLs the sandbox fetches |

**Buildable now (not blocked on VID-EDIT):** (1) roteiro approval + approvals organ + post events (§2.3); (2) `formato` enum + one post table (§1.2); (3) `PublishRequest`/`PublishOutcome` + scheduled publish (`agendado`) for images and carousels; (4) signed upload URLs + per-org/job storage prefixes + retention per prefix; (5) AI-output validation before publish.
**Already in flight (parallel):** seed resumable chunked uploads; seed SSE job progress.
**Blocked on VID-EDIT:** sandbox runner implementation, preview proxy job, video job payloads.

---

## 5. Hand-offs

- **architect:** ratify layer placements (approvals organ L0?, `domain.video_editing` L0?); schema for `cs_posts.formato` + media assets + event tables; sandbox runner shape on the fleet; `mc_posts` → `cs_posts` convergence.
- **product-designer:** approval screens (roteiro, media version compare), Agendar flow, Vídeos editor shell (after VID-EDIT).
- **product-manager:** sequencing vs other social-wiring work; tier gating of video.
- **tech-lead:** slices for the five buildable-now items; nav group move is already with the frontend engineer.
- **security / compliance-reviewer:** sandbox no-secrets rule, signed-URL TTLs, LGPD retention of raw video/audio.

## 6. Questions for the owner

1. Who approves a roteiro and media: the author, a brand role, or a client user? (a) any member · (b) a named approver role per brand · (c) the client via a share link.
2. Is approval one step or can it be skipped per brand? (a) always required · (b) brand setting · (c) only for client brands.
3. Merge carousels (`mc_posts`) into the esteira post (`cs_posts`)? (a) yes, one post with `formato` · (b) keep separate.
4. Is Vídeos a plan feature (tier) or for every org? (a) all · (b) higher tiers · (c) per-org add-on.
5. Retention for raw video inputs after approval: (a) delete at publish · (b) keep N days · (c) keep until the post is archived.

## Sources

- Ulrich, K. (1995) "The role of product architecture in the manufacturing firm", Research Policy 24(3) (via `KNOWLEDGE-BASE/CONTEXT/PATTERNS/product/product-architecture-canon.md`).
- Platform rules: `KB § PATTERNS/architect/event-oriented-architecture.md`, `KB § PATTERNS/architect/measurement-by-design.md`, `KB § PATTERNS/architect/vertical-seed.md`.
- Code: the file:line citations above, read at `origin/dev` `8f32496d2`.
- **Not verified:** the Pythonando video "Arquitetura de software para editar centenas de vídeos" was not watched; its ideas are taken from the owner's list in the brief. Semantic code search was unavailable (embedding provider quota exhausted), so organ discovery used the graph cache, outlines and grep; a near-fit seed organ for approvals or video could exist unseen, re-run `find_reusable_component` before building §2.3 and §3.
