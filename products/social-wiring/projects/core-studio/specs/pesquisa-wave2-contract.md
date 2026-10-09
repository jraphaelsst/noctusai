# Pesquisa wave 2: Extrair Pesquisa + Assuntos Virais — build contract (2026-10-09)

> Authored by the architect advisor, adopted by the tech-lead. §9 records the tech-lead defaults for §8; the owner may override any of them.

This is the build contract for wave 2. It extends `pesquisa-contract.md` v1 and keeps its shape: §1 decisions · §2 data · §3 endpoints · §4 FE · §5 tests · §6 differences. It adds §7 slice plan and §8 open questions. 

## Before you dispatch

- **Migration number is 221, not 218.** `noctus.dev.next_migration_number` reports 218–220 already claimed on in-flight branches (`feat/sw-s1-campanha-intake`, `feat/sw-l2c-s3-visita`, `feat/sw-propostas-crud`). Scaffold it with `noctus.dev.scaffold_migration`, not by hand.
- **The job queue already exists.** `social_wiring.jobs` (migration 121) and the seed `noctusai_lib.domain.jobs` (Worker, repository, Fake/Real) are already used by edicao_fotos. This needs no new queue, only a second `Worker` limited to type `pesquisa.extrair`.
  - It can't reuse the fotos worker: that worker's `claim_gate` is the fotos "processamento_ativo" pause, which would also pause Pesquisa.
- **Starting the worker from `app/lifespan.py` is the second case of the same pattern** (edicao_fotos is the first). Two cases means triage: accept a direct addition now. At the third case (likely the Segundo Cérebro YouTube-transcribe job), `ModuleRegistration` should get startup/shutdown hooks.
  - "A user-visible progress row on top of seed jobs" is also at two cases (fotos batches, Pesquisa extractions). It should be formalized in the seed at the third.
- **The v1 save path drops source data.** `PesquisaService._save` (`services/pesquisa_service.py:148-183`) never writes `source_ref` or `plays`. Wave 2 must extend it; that's in BE-3's scope.
- **Existing debt, fix while there.** `POST /items/classify` has no rate limit, while email_marketing uses `@limiter.limit(DEFAULT_AI_RL)`. BE-3 adds it to classify and to the new extraction submit.

---

## 1 · Owner decisions this contract encodes

- **Extraction sources in v1 = our own content only, per marca:**
  - (a) Instagram media from the marca's connected Instagram accounts;
  - (b) YouTube videos and shorts from the marca's connected YouTube accounts;
  - (c) posts created in Criação de mídia (`mc_posts`).
  - No third-party scraping. A future "monitored profiles" source plugs into the same `FonteExtracao` seam (§2.5) with no endpoint or front-end change beyond a new tab.
- **An extraction is an LLM reading one post** (text plus metrics) and proposing:
  - research items per variable → saved as `pending`, `origin='extraction'`, with `source_ref` = the post and `plays` = its views; or
  - viral topics → saved as `pending` topics.
  - Duplicates are dropped by the existing unique indexes.
- **Assuntos Virais is rebuilt now and refined later.** It covers: viral topics per marca with summed plays, pending/approved, manual add, bulk actions and empty, and a "ver virais" modal listing the source posts with their metrics.
- **Extraction runs as an async job:** submit → job id → poll. It is capped per user and per org.
  - The LLM goes through `noctusai_lib.integrations.llm.chat_completion` behind the existing `PesquisaLlm` seam.
  - Both new prompts are **DRAFT for owner validation**.

## 2 · Data

### 2.1 Existing tables that supply post text and metrics (read-only for this module)

| Source kind | Marca link | Text the LLM reads | Metrics (`plays` = views) | Thumbnail / link |
|---|---|---|---|---|
| `instagram_media` | `integration_accounts` with `provider='instagram'`, `status='validated'`, `marca_id = :marca` → `ig_media.account_id` | `ig_media.caption`. If an `mc_posts` row has `published_media_id = ig_media.ig_media_id`, its `title`, `copy_caption` and slide `headline`/`body` are appended | plays = `ig_media.latest_metrics->>'views'` (NULL when Meta did not return it, never 0); `like_count`, `comments_count`; `latest_metrics` `reach`, `shares`, `saved`; `latest_snapshot_date` | `thumbnail_url` (or `media_url` for images), `permalink`, `published_at`, `media_product_type` (REELS/FEED) |
| `youtube_video` | `integration_accounts` with `provider='youtube'`, `marca_id = :marca` → `youtube_videos` ∪ `youtube_shorts`, merged on `(account_id, youtube_video_id)`; the shorts row wins and sets `is_short` | `title` + `description` (truncated) + `tags` | `view_count`, `like_count`, `comment_count` | `thumbnail_url`, `https://youtube.com/watch?v={id}` (shorts: `/shorts/{id}`), `published_at` |
| `mc_post` | `mc_posts.brand_kit_id` → `mc_brand_kits.marca_id = :marca` | `title`, `idea`, `key_message`, `copy_caption`, plus `mc_post_slides` `headline`/`body` in `slide_n` order | none (plays NULL) | `published_permalink` if set; `created_at` / `published_at` |

- **Instagram/created-post overlap:** an `mc_post` whose `published_media_id` matches an `ig_media` row of the marca is **left out of the `mc_post` list**. It is the same real post, reachable through Instagram with real metrics and the created-post text appended.
- **Transcripts:** none exist in the platform for IG or YouTube (`ig_media` and `youtube_videos` have no transcript column). v1 reads caption and description only; see §8 Q1.
- **Posts with too little text:** a post whose assembled text is under 20 characters gets `analisavel=false`. No LLM call is made for it.

### 2.2 Migration **221** `221_cs_research_extraction.sql` (schema `social_wiring`)

Forward-only and idempotent. It has the same guard block as 217 (`public.current_org_id_for(text)`) plus a guard that `cs_research_items` exists (217 applied first). RLS on every table follows 217 exactly:
- authenticated select/write `USING (org_id = (SELECT public.current_org_id_for('social_wiring')))`;
- `service_role` ALL.

**`cs_viral_topics`**

| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `org_id` | uuid NOT NULL FK organizations ON DELETE CASCADE | |
| `marca_id` | uuid NOT NULL FK marcas ON DELETE CASCADE | |
| `topic` | text NOT NULL | `char_length` 1..255, `= btrim(topic)` |
| `status` | text | CHECK `pending`/`approved`/`rejected` |
| `origin` | text | CHECK `manual`/`extraction`. Manual ⇒ starts `approved`, `total_plays` NULL (UI shows "Manual") |
| `total_plays` | bigint NULL | sum of `plays` over its sources (NULLs skipped). Recomputed by the service whenever sources are added |
| `created_by` | uuid NULL | |
| `created_at`, `updated_at` | timestamptz | `set_updated_at_media_creation` trigger |

- Unique `(marca_id, lower(topic))`.
- Index `(marca_id, status, total_plays DESC NULLS LAST)`.

**`cs_viral_topic_sources`**: the posts behind a topic, for the "ver virais" modal.

| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `org_id` | uuid NOT NULL | |
| `topic_id` | uuid NOT NULL FK `cs_viral_topics` ON DELETE CASCADE | |
| `source_kind` | text | CHECK `instagram_media`/`youtube_video`/`mc_post` (extend the CHECK when monitored profiles land) |
| `account_id` | uuid NULL | |
| `source_id` | text NOT NULL | |
| `url` | text | |
| `thumbnail_url` | text | |
| `published_at` | timestamptz | |
| `plays`, `likes`, `comments` | bigint NULL | snapshot at extraction time |
| `excerpt` | text NULL | sentence the topic came from |
| `extracao_id` | uuid NULL FK `cs_extraction_jobs` ON DELETE SET NULL | |
| `created_at` | timestamptz | |

- Unique `(topic_id, source_kind, coalesce(account_id::text,''), source_id)`.

**`cs_extraction_jobs`**: user-facing job state. The queue row lives in `social_wiring.jobs`.

| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `org_id` | uuid NOT NULL | |
| `marca_id` | uuid NOT NULL FK marcas CASCADE | |
| `created_by` | uuid NOT NULL | |
| `tipos` | text[] NOT NULL | each ∈ `{pesquisa, assuntos_virais}`, 1..2 |
| `status` | text | CHECK `queued`/`running`/`completed`/`completed_with_errors`/`failed`/`cancelled` |
| `cancel_requested` | bool default false | |
| `posts` | jsonb NOT NULL | `[{kind, account_id, id}]`, the submitted selection |
| `total_tarefas` | int | posts × tipos actually sent to the LLM |
| `tarefas_processadas` | int default 0 | |
| `tarefas_com_erro` | int default 0 | |
| `step` | text NULL | e.g. "Analisando post 3 de 12" |
| `itens_salvos`, `itens_ignorados` | int default 0 | skipped = duplicate |
| `itens_descartados` | int default 0 | not a literal span, unknown slug, or too long |
| `assuntos_salvos`, `assuntos_ignorados` | int default 0 | |
| `ja_extraidos_pulados` | int default 0 | |
| `erro` | text NULL | pt-BR, job-level |
| `queue_job_id` | uuid NULL | id in `social_wiring.jobs` |
| `started_at`, `finished_at`, `created_at`, `updated_at` | timestamptz | |

- **Partial unique index `(created_by) WHERE status IN ('queued','running')`.** This enforces "one active extraction per user" in the database, so two concurrent submits can't both pass.
- Index `(org_id, created_at DESC)`; index `(marca_id, created_at DESC)`.

**`cs_extraction_post_runs`**: one row per (job, tipo, post). It drives the "Já extraído" badge and keeps the LLM from being spent twice on the same post.

| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `org_id`, `marca_id` | uuid NOT NULL | |
| `extracao_id` | uuid FK `cs_extraction_jobs` CASCADE | |
| `tipo` | text | CHECK `pesquisa`/`assuntos_virais` |
| `source_kind` | text | |
| `account_id` | uuid NULL | |
| `source_id` | text | |
| `status` | text | CHECK `done`/`failed`/`skipped` |
| `motivo` | text NULL | `sem_texto` / `llm_erro` / `cancelado` |
| `itens_salvos`, `assuntos_salvos` | int | |
| `created_at` | timestamptz | |

- Unique `(extracao_id, tipo, source_kind, coalesce(account_id::text,''), source_id)`.
- Index `(marca_id, tipo, source_kind, source_id) WHERE status='done'`.

**`cs_research_items`: no DDL change.** `source_ref` gets a fixed shape (amends v1 §2, where it was `{kind:'instagram_media'|'post', id, url, plays}`; v1 never wrote any, so no data migrates):

```json
{"kind":"instagram_media|youtube_video|mc_post", "account_id":"uuid|null", "id":"string",
 "url":"string|null", "thumbnail_url":"string|null", "published_at":"iso|null",
 "plays":123, "likes":4, "comments":1, "excerpt":"frase de origem", "extracao_id":"uuid"}
```

When the same phrase comes from two posts, the first source wins and the second is `skipped` (the unique index decides). See §8 Q4.

### 2.3 Config (`app/config.py`, finite defaults, never "unlimited by omission")

`pesquisa_extracao_worker_enabled=True` (hard switch: off means submit returns 503) · `pesquisa_extracao_max_posts_por_job=30` · `pesquisa_extracao_jobs_por_dia_usuario=10` · `pesquisa_extracao_posts_por_dia_org=300` (counts posts × tipos) · `pesquisa_extracao_texto_max_chars=6000` · `pesquisa_extracao_poll_seconds=2.0` · `pesquisa_extracao_lease_seconds=600`.

### 2.4 Job lifecycle

```
submit ─► queued ─(worker claims pesquisa.extrair)─► running ─► completed
   │                                                   ├──► completed_with_errors  (≥1 done, ≥1 failed)
   │                                                   ├──► failed                 (0 done / infra dead-letter)
   └─(cancel)──────────────────────────────────────────┴──► cancelled              (checked between tasks)
```

- **Submit** inserts the `cs_extraction_jobs` row (`queued`), then calls `repo.enqueue(type='pesquisa.extrair', payload={extracao_id}, dedupe_key='pesquisa.extrair:{id}', max_retries=2)` and stores `queue_job_id`. If the enqueue fails, the row is set to `failed` and the API returns 503 `"Falha ao iniciar a extração"`.
- **Handler.** If the row is gone, it raises `DeadLetterError`. If `cancel_requested` is set, it marks `cancelled`. Otherwise it sets `running` and `started_at`, then for each post × tipo not yet in `post_runs` for this job (so a retried job resumes rather than restarting):
  1. check for cancel;
  2. assemble the text through the source;
  3. skip with `sem_texto` if the post isn't analysable;
  4. call the LLM;
  5. parse and save;
  6. write the `post_run` row;
  7. update the counters, `step` and `tarefas_processadas`.
  A per-post LLM exception becomes a `post_run` with `failed`/`llm_erro`, and the loop continues. A database or infrastructure exception propagates so the Worker retries.
- **Reconcile (no stuck jobs).** `GET /extracoes/{id}` and the list check the queue row. If the extraction is `queued`/`running` but its `social_wiring.jobs` row is `dead_letter`/`failed`, it is set to `failed` with `erro="Falha interna na extração"`.
- **Progress** = `round(100 * tarefas_processadas / max(total_tarefas,1))`, computed server-side.

### 2.5 Source seam: `app/modules/media_creation/pesquisa_fontes.py`

```python
@dataclass(frozen=True) class PostFonte:
    kind: str; account_id: str | None; id: str; url: str | None; thumbnail_url: str | None
    published_at: str | None; texto: str; analisavel: bool
    plays: int | None; likes: int | None; comments: int | None; extra: dict  # e.g. is_short, media_product_type

class FonteExtracao(Protocol):
    kind: str
    def contas(self, org_id, marca_id) -> list[dict]          # [{account_id|None, label, total_posts, last_synced_at}]
    def listar(self, org_id, marca_id, *, account_id, cursor, limit, busca) -> tuple[list[PostFonte], str|None]  # newest first, keyset
    def obter(self, org_id, marca_id, refs: list[tuple[str|None,str]]) -> dict[tuple, PostFonte]  # marca-scoped; missing ⇒ absent

FONTES: dict[str, Callable[[db], FonteExtracao]] = {"instagram_media": ..., "youtube_video": ..., "mc_post": ...}
```

- Instagram reuses `IgInsightsRepository.list_media_page` / `get_media` keyset logic from `app/modules/instagram/repository.py`. Import it; don't fork it.
- A future `monitored_profile` source is one more entry in `FONTES` plus one value in the two CHECKs.

## 3 · Endpoints

Prefix `/api/media-creation/pesquisa`, auth `get_current_user_org`, `success_response`, pt-BR `detail`. A `marca_id` outside the caller's org returns **404**.

### Extrair

| # | Method + path | Request | `data` |
|---|---|---|---|
| 11 | `GET /fontes` | `marca_id` | `Fonte[]` (one entry per Instagram account, per YouTube account, plus one `mc_post`) |
| 12 | `GET /fontes/posts` | `marca_id`, `kind`, `account_id?` (required for IG/YT), `cursor?`, `limit` 1–50 (default 24), `busca?` (case-insensitive match on text) | `{posts: PostFonte[], next_cursor: string\|null}`, newest first |
| 13 | `GET /extracoes/limites` | `marca_id` | `{worker_ativo, max_posts_por_job, extracoes_restantes_hoje, tarefas_restantes_hoje_org, extracao_ativa_id: string\|null}` |
| 14 | `POST /extracoes` | `{marca_id, tipos: ('pesquisa'\|'assuntos_virais')[1..2], posts: {kind, account_id, id}[1..max], reextrair?: false}` | **202** `ExtractionJob` |
| 15 | `GET /extracoes` | `marca_id`, `limit` 1–20 (default 10) | `ExtractionJob[]`, newest first, reconciled |
| 16 | `GET /extracoes/{id}` | — | `ExtractionJob`, reconciled (poll every 2 s) |
| 17 | `POST /extracoes/{id}/cancel` | — | `ExtractionJob` (only from `queued`/`running`, else 409) |

**Submit (14) refusals, all before anything is enqueued:**
- worker disabled → 503 `"Extração indisponível no momento"`;
- user already has an active job (index violation) → **409** `"Já existe uma extração em andamento"`;
- daily user/org cap exceeded → **429** `"Limite diário de extrações atingido"`;
- more posts than `max` → 422;
- any post not found for this marca → 422 `"Post não encontrado para esta marca"`;
- after skipping already-extracted posts (`reextrair=false`), nothing left → 422 `"Todos os posts selecionados já foram extraídos"`.

Submit also carries `@limiter.limit(DEFAULT_AI_RL)`.

### Assuntos Virais (prefix `/assuntos-virais`)

| # | Method + path | Request | `data` |
|---|---|---|---|
| 18 | `GET /assuntos-virais` | `marca_id`, `status=approved\|pending` (default approved), `sort=plays\|recent` (default plays), `limit` 1–200 (default 54), `offset` | `{items: ViralTopic[], total}` |
| 19 | `GET /assuntos-virais/counts` | `marca_id` | `{approved, pending}` |
| 20 | `POST /assuntos-virais` | `{marca_id, topics: string[1..100]}` (each trimmed, 1..255) | `{saved, skipped, items: ViralTopic[]}`. Manual ⇒ approved; a rejected duplicate flips back to approved (same rule as items) |
| 21 | `POST /assuntos-virais/{id}/approve` | — | `ViralTopic` |
| 22 | `POST /assuntos-virais/{id}/reject` | — | `ViralTopic` (soft, then hidden) |
| 23 | `DELETE /assuntos-virais/{id}` | — | 204 (hard delete, sources cascade) |
| 24 | `POST /assuntos-virais/bulk` | `{marca_id, action: 'approve'\|'reject'\|'delete', ids: uuid[1..500]}` | `{affected}` |
| 25 | `POST /assuntos-virais/empty` | `{marca_id, status: 'approved'\|'pending', confirm: true}` | `{deleted}`. Hard-deletes that status only (CoreStudio empties per tab); rejected rows stay as dedupe memory |
| 26 | `GET /assuntos-virais/{id}/fontes` | — | `ViralTopicSource[]`, plays desc. `thumbnail_url`/`url` refreshed from the live source row when it still exists (IG CDN URLs expire); metrics are the snapshot |

The service also exposes `AssuntosViraisService.salvar_extraidos(marca_id, extracao_id, topicos: list[tuple[str, PostFonte, str|None]]) -> {saved, skipped}`. BE-3's handler calls it. On a duplicate topic it adds the new source row and recomputes `total_plays`, and the topic counts as skipped.

### 3.1 TS types

```ts
type FonteKind = 'instagram_media' | 'youtube_video' | 'mc_post'
type Fonte = { kind: FonteKind; account_id: string | null; label: string; total_posts: number; last_synced_at: string | null }
type PostFonte = { kind: FonteKind; account_id: string | null; id: string; url: string | null; thumbnail_url: string | null;
  published_at: string | null; texto: string; analisavel: boolean; plays: number | null; likes: number | null;
  comments: number | null; extra: Record<string, unknown>;
  extraido: { pesquisa: string | null; assuntos_virais: string | null } }   // ISO of last 'done' run, else null
type ExtracaoTipo = 'pesquisa' | 'assuntos_virais'
type ExtractionStatus = 'queued' | 'running' | 'completed' | 'completed_with_errors' | 'failed' | 'cancelled'
type ExtractionJob = { id: string; marca_id: string; tipos: ExtracaoTipo[]; status: ExtractionStatus; step: string | null;
  progress: number; total_tarefas: number; tarefas_processadas: number; tarefas_com_erro: number;
  itens_salvos: number; itens_ignorados: number; itens_descartados: number; assuntos_salvos: number;
  assuntos_ignorados: number; ja_extraidos_pulados: number; erro: string | null;
  created_at: string; started_at: string | null; finished_at: string | null }
type ExtractionLimits = { worker_ativo: boolean; max_posts_por_job: number; extracoes_restantes_hoje: number;
  tarefas_restantes_hoje_org: number; extracao_ativa_id: string | null }
type SourceRef = { kind: FonteKind; account_id: string | null; id: string; url: string | null; thumbnail_url: string | null;
  published_at: string | null; plays: number | null; likes: number | null; comments: number | null;
  excerpt: string | null; extracao_id: string | null }
// Item.source_ref (v1 `object|null`) narrows to `SourceRef | null`
type ViralTopic = { id: string; marca_id: string; topic: string; status: 'pending' | 'approved';
  origin: 'manual' | 'extraction'; total_plays: number | null; fontes_count: number; created_at: string }
type ViralTopicSource = { source_kind: FonteKind; account_id: string | null; source_id: string; url: string | null;
  thumbnail_url: string | null; published_at: string | null; plays: number | null; likes: number | null;
  comments: number | null; excerpt: string | null }
```

### 3.2 Prompts (both DRAFT, module docstring says so; the LLM is the injected `PesquisaLlm`)

**`prompts/pesquisa_extractor.py`**
- **System prompt:** the 36 classifiable variables, rendered from `pesquisa_variables.CLASSIFIABLE` the way the classifier does it, never duplicated by hand.
- **Rule:** extract only **literal spans** of the post text. CoreStudio's extractor is literal in 641 of 643 cases (`mechanisms.md` §4).
- **Output:** the same `{{SLUG}}\n[conteúdo]` pairs, at most 15 per post.
- **User message:** a metrics header (`Plataforma · Publicado em · Views · Likes · Comentários`) followed by the text.
- **Parser `parse_extractor_output(reply, texto)`:**
  - accepts classifiable slugs only;
  - content 1..500 characters;
  - must be a substring of the text after normalization (casefold, collapsed whitespace, edge punctuation stripped);
  - everything else is counted in `descartados`.
  - It returns `(pairs, excerpt_by_pair, descartados)`. The excerpt is the source sentence, using CoreStudio's `truncateHeadline` rule (§2.4).

**`prompts/assuntos_virais_extractor.py`**
- Returns up to 5 short subjects per post (noun phrases, 2–60 characters, pt-BR, lowercase except proper nouns). An optional parenthesized variable hint like `(desejo)` is allowed, as in CoreStudio's samples (§5.6).
- **Output:** one per line.
- **Parser:** strips list markers, enforces length, dedupes within the post, drops chatter lines.

## 4 · Frontend

### 4.1 Sidebar and routes (both nav configs in `App.tsx`, around lines 228 and 391)

- Sub-group **Pesquisa** becomes **Minha Pesquisa** (`/media-creation/pesquisa`) plus **Extrair Pesquisa** (`/media-creation/pesquisa/extrair`, icon `Sparkles`).

### 4.2 Assuntos Virais placement: a tab on Minha Pesquisa (recommended)

Put it on Minha Pesquisa as tabs `Itens de pesquisa | Assuntos virais`, synced to `?tab=itens|assuntos-virais`. Reasons:
1. It is exactly CoreStudio's structure: `/searches?tab=subject-viral`, page-map-v2 §4b. DECISIONS (2026-10-05) says keep its structure and labels, and CoreStudio has no sidebar link for it.
2. It shares the per-marca switcher and the "research base" meaning, and it feeds the later headline `who=viral` form, as items do.
3. Every sidebar link is a promise of a full page, and the topics view is one pane.

Deliberate difference from CoreStudio: the tab is **visible** (CoreStudio reaches it only by URL parameter).

"Extrair Assuntos Virais" is **not** a second picker modal. Its CTA navigates to `/media-creation/pesquisa/extrair?tipo=assuntos_virais`, so there is one post picker and no duplicated surface.

### 4.3 Extrair Pesquisa page (`pages/ExtrairPesquisa.tsx`)

- **Header:** title **Extrair Pesquisa**; subtitle "Selecione posts do seu conteúdo para extrair itens de pesquisa e assuntos virais."; outline button "Minha Pesquisa".
- **Marca switcher:** the shared component, same localStorage key `sw.pesquisa.marca`.
- **"Extrair" checkboxes:** `Itens de pesquisa` (default on) and `Assuntos virais`. These come from `?tipo` and must have at least one checked.
- **Source tabs** from `GET /fontes`: one tab per Instagram account (`@label`), per YouTube account, and "Posts criados", each with `total_posts`.
  - No sources: empty state "Nenhuma conta conectada para esta marca" with a link to the marca's integrations.
  - An Instagram account with 0 posts: "Conta ainda não sincronizada".
- **Search** input "Buscar no texto do post...".
- **Post grid**, newest first, 3 columns, 24 per page, "Carregar mais" by cursor. Each card has:
  - checkbox, thumbnail (play-icon placeholder if missing), date dd/mm/aaaa;
  - 3-line text excerpt;
  - Views / Likes / Comentários in compact K/M ("—" when null, never 0);
  - badge `Reels`/`Short` from `extra`;
  - badge **"Já extraído"** (tooltip with the date) when `extraido[tipo]` is set for every chosen tipo;
  - "Ver post ↗".
  - A card with `analisavel=false` is disabled, with tooltip "Sem texto para analisar".
- **Sticky selection bar:** `N de {max} selecionado(s)` · "Selecionar os {max} mais recentes" · "Limpar" · checkbox "Reextrair posts já extraídos" · primary **Extrair (N)**.
  - Disabled when `!worker_ativo`, `extracao_ativa_id`, or caps reached (shown as text from `/extracoes/limites`).
- **Submit → progress panel.** Polls `GET /extracoes/{id}` every 2 s while `queued`/`running`; React Query `refetchInterval` returns `false` on a terminal status. It shows:
  - `step` and a progress bar `{progress}%`;
  - live counters;
  - "Cancelar".
  - On load, if `extracao_ativa_id` is set, the panel resumes that job (survives reloads).
- **Terminal result:**
  - `completed` → "Extração concluída!" with `{itens_salvos} item(ns) novo(s) · {itens_ignorados} já existente(s) · {assuntos_salvos} assunto(s)`, a line for discarded items when > 0, and links "Ver pendentes em Minha Pesquisa" (`/media-creation/pesquisa?status=pending`) and "Ver assuntos virais" (`?tab=assuntos-virais`).
  - `completed_with_errors` → warning "Extração concluída com avisos".
  - `failed` → error with `erro` and "Tentar novamente".
  - `cancelled` → info.
  - Toast on each terminal status. List, counts and limits are invalidated.
- **"Extrações recentes" panel** (`GET /extracoes`): date · tipos · posts · status badge · counts.
- **Error codes:** 409, 429 and 503 show `detail` as a toast and refetch limits.
- **Loading:** the two-signal rule (`showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`) and `placeholderData` on marca/source/search key changes.

### 4.4 Minha Pesquisa changes (`pages/Pesquisa.tsx`)

- Tabs as in 4.2.
- A header button "Extrair Pesquisa" linking to the new route.
- An `extraction` row gets meta `· extração` plus an icon link "Ver post ↗" (`source_ref.url`), with the excerpt as tooltip.
- `?status=pending` is honoured on load.

### 4.5 Assuntos Virais tab (`components/pesquisa/AssuntosVirais.tsx`; CoreStudio §1.6 behaviour with our design system)

- **Info card:** title "Extrair assuntos virais", text "Use esta opção para extrair assuntos virais dos seus posts e adicionar aos seus assuntos virais.", button "Extrair Assuntos Virais" → the Extrair route with `tipo=assuntos_virais`.
- **Sub-tabs** `Aprovado` · `Pendente (n)` from `/counts`.
- **Aprovado:**
  - "Selecionar todos" · "Excluir selecionados (N)" · "Esvaziar" (confirm "Você realmente deseja esvaziar TODOS os assuntos virais aprovados? Esta ação não pode ser desfeita.");
  - input "Digite um novo assunto viral..." (maxLength 255, Enter submits, empty → toast "Digite um tópico válido!") plus "Adicionar";
  - pill cloud: checkbox · topic · `{K/M} Views` or `Manual` · × (confirm "Você realmente deseja remover este tópico viral?", then DELETE);
  - clicking a pill opens the modal;
  - "Ver mais" pages 54 at a time.
- **Pendente:**
  - "Selecionar todos" · "Aprovar selecionados (N)" · "Excluir selecionados (N)" (= reject) · "Esvaziar" (confirm);
  - card per topic (orange accent): topic, views, "Pendente", ✓✓ Aprovar / 🗑 Rejeitar with no confirm (as CoreStudio);
  - clicking a card opens the modal ("Clique para ver os virais");
  - empty state "Nenhum item pendente".
- **Modal "Assuntos Virais — «topic»":** "Buscando dados dos virais..." while loading, then a 3-column grid of source cards (thumbnail, Views/Likes/Comentários, date, excerpt). Clicking a card opens `url` in a new tab. Empty: "Nenhum dado viral encontrado para este tópico."; error state with retry.

### 4.6 Shared pieces

- `components/pesquisa/MarcaSwitcher.tsx` and `hooks/useMarcaPesquisa.ts`. The `lerMarcaSalva`/`salvarMarca` + switcher logic is lifted from `Pesquisa.tsx:52-79` and consumed by both pages.
- New hooks: `hooks/usePesquisaExtracao.ts` and `hooks/useAssuntosVirais.ts`.
- `hooks/usePesquisa.ts` gets the `SourceRef` narrowing.

## 5 · Tests (minimum)

Backend, under `backend/tests/modules/media_creation/`.

**Migration**
- `test_pesquisa_wave2_migration.py`: 221 creates the 4 tables, the partial unique index and the RLS policies; CHECK enums match the Python constants (`FONTES` keys, `EXTRACAO_TIPOS`, job statuses), so they can't drift.

**Sources** (`test_pesquisa_fontes.py`)
- Each source is marca-scoped: another marca's or org's account is invisible.
- Instagram plays come from `latest_metrics.views` and are NULL when absent, never 0.
- YouTube merges videos and shorts on `youtube_video_id`, with the shorts row winning.
- An `mc_post` published to a connected Instagram account is excluded from the `mc_post` list and its text is appended to the IG post.
- Text under 20 characters → `analisavel=false`.
- Keyset paging is stable.

**Prompt parsers** (`test_pesquisa_extractor_prompt.py`, `test_assuntos_virais_prompt.py`)
- Valid pairs pass; unknown slug, non-literal span, over 500 characters, and model chatter are discarded and counted.
- Topic length and limit rules hold.
- The extractor prompt renders all 36 classifiable slugs.

**Assuntos Virais API** (`test_assuntos_virais.py`)
- CRUD and status transitions work; manual add is approved; manual re-add of a rejected topic flips it to approved.
- A cross-org `marca_id` → 404.
- Rejected topics are never listed.
- Empty only removes the given status.
- `salvar_extraidos` on a duplicate topic adds the source and recomputes `total_plays`, skipping NULL plays.
- `/fontes` sorts by plays desc.
- Auth returns exactly `== 401`.

**Extraction API and handler** (`test_pesquisa_extracao.py`)
- **Submit:** 202 queues a row and a `FakeJobRepository` job with the right `dedupe_key`; refusals 409 (second active job), 429 (daily caps), 422 (too many posts, foreign post, all already extracted), 503 (worker disabled, enqueue failure ⇒ row `failed`).
- **Handler** with the `PesquisaLlm` seam faked:
  - saves pending items with full `source_ref` and `plays`;
  - topics are saved with sources;
  - one post's LLM error → `completed_with_errors`, the other posts are saved;
  - all posts fail → `failed`;
  - `sem_texto` → no LLM call;
  - `cancel_requested` between tasks → `cancelled`;
  - a retried handler resumes, skipping posts that already have a `post_run`;
  - a missing row → `DeadLetterError`.
- **Reconcile:** a dead-lettered queue row turns the extraction `failed`.
- `extraido` timestamps appear on `/fontes/posts`.
- `DEFAULT_AI_RL` is applied on submit and on classify.
- Auth returns exactly `== 401`.
- The 202 response shape matches `ExtractionJob`.

Frontend (vitest, mocked API)

- **`ExtrairPesquisa.test.tsx`:** source tabs render; the grid shows metrics with "—" for null; selection respects the max; "Selecionar os N mais recentes" works; submit → progress panel polls until `completed` → result links; 409/429/503 show toasts; a non-analysable card is disabled; an active job resumes on mount.
- **`AssuntosVirais.test.tsx`:** both sub-tabs; add, approve, reject; bulk; empty with confirm; the modal lists sources.
- **`Pesquisa.test.tsx` additions:** the tab switch syncs `?tab`; an extraction row shows "Ver post".

## 6 · Deliberate differences from CoreStudio

- Sources are our own posts and connected accounts per marca, not a staff-curated catalogue of 485 third-party profiles.
- Extraction runs **at click time** as a capped job. CoreStudio's Extrair Pesquisa shows a precomputed extraction, and its hidden per-profile job is synchronous for topics.
- One post picker serves both items and topics (CoreStudio has two modals plus a page).
- Assuntos Virais is a visible tab.
- Topics reject softly (CoreStudio deletes).
- Topic "remove" deletes exactly one topic: the unique index makes CoreStudio's "remove all pills with the same text" moot.
- No mutating GETs.
- Per-user and per-org spend caps, plus the "Já extraído" skip by default.
- No niche/profession filters (they only made sense for the curated catalogue).

## 7 · File-disjoint slice plan

Parallel within a wave; each slice runs in its own `task_branch` off `origin/dev`.

**Wave 0** (small; integrate before wave 1)
- **BE-0** (backend-engineer): `backend/migrations/221_cs_research_extraction.sql` + the migration test. Nothing else.
- **FE-0** (frontend-engineer): `components/pesquisa/MarcaSwitcher.tsx`, `hooks/useMarcaPesquisa.ts`, refactor `pages/Pesquisa.tsx` to consume them (no behaviour change; existing `Pesquisa.test.tsx` stays green).

**Wave 1** (parallel)
- **BE-1** (Assuntos Virais): `schemas/assuntos_virais.py`, `services/assuntos_virais_service.py` (including `salvar_extraidos`), `routers/assuntos_virais.py`, `tests/.../test_assuntos_virais.py`, plus a one-line append to the `media_creation/__init__.py` router list.
- **BE-2** (sources and prompts, no router): `pesquisa_fontes.py`, `prompts/pesquisa_extractor.py`, `prompts/assuntos_virais_extractor.py`, and their three test files.
- **FE-1** (Minha Pesquisa tab and Assuntos Virais): `components/pesquisa/AssuntosVirais.tsx` (plus subcomponents in the same folder), `hooks/useAssuntosVirais.ts`, `pages/Pesquisa.tsx` (tabs, header button, "Ver post" row, `?status`), `hooks/usePesquisa.ts` (SourceRef), and tests.

**Wave 2** (parallel; BE-3 needs BE-1 and BE-2 integrated; FE-2 needs FE-0)
- **BE-3** (extraction jobs): `schemas/pesquisa_extracao.py`, `services/pesquisa_extracao_service.py` (submit, caps, reconcile, handler), `services/pesquisa_extracao_worker.py` (start/stop over seed `Worker`, types `["pesquisa.extrair"]`), `routers/pesquisa_extracao.py`, and `test_pesquisa_extracao.py`. Plus:
  - a `_save` extension in `services/pesquisa_service.py` taking `source_ref` and `plays` per pair, with `DEFAULT_AI_RL` on classify in `routers/pesquisa.py`;
  - the config keys in `app/config.py`;
  - start/stop lines in `app/lifespan.py`, guarded and logged like fotos;
  - a one-line append to the router list.
- **FE-2** (Extrair page): `pages/ExtrairPesquisa.tsx`, `components/pesquisa/extrair/*`, `hooks/usePesquisaExtracao.ts`, the route and both sidebar entries in `App.tsx`, and `ExtrairPesquisa.test.tsx`. It develops against mocked API types from §3.1.

**Collision notes**
- BE-1 and BE-3 both append one line to the `media_creation/__init__.py` router list (C2, additive only, sequential waves, so no conflict).
- FE-1 and FE-2 are disjoint: FE-2 never touches `Pesquisa.tsx`; FE-1 never touches `App.tsx`.

**Gates**
- Re-run `gate_sweep` on the merged tip after wave 2.
- `predeploy_check social-wiring` before bless. Its `schema_drift` leg will fail until 221 is applied.
- Applying 217 + 221 to prod needs owner consent through `migrate_product`.

## 8 · Open owner questions

1. **Transcripts.** v1 reads captions and descriptions only. Reels and YouTube videos carry most of their hook in speech. Should a later wave transcribe audio? It would cost one transcription per post and a media download for IG; CoreStudio's extractor runs on the spoken hook.
2. **Literal-span rule.** I copied CoreStudio: only exact phrases from the post are kept. Captions are often short or full of hashtags, so this may discard a lot. Keep it strict, or allow light paraphrase?
3. **Caps.** Are the defaults right: 30 posts per job, 10 jobs per user per day, 300 post-analyses per org per day, one active job per user?
4. **Same phrase from two posts.** Should it keep the first source (proposed), or sum plays and keep both sources as topics do? The second needs an `item_sources` table.
5. **Created posts (`mc_posts`).** Include drafts as a source? Proposed: all statuses, with a filter chip; or only `ready`/`published`?
6. **Plays snapshot.** Item and topic plays are frozen at extraction time. Should they be refreshed from the latest IG/YT metrics on a schedule?
7. **Auto-extraction.** Should newly synced IG posts above some views threshold be queued automatically (the CoreStudio "automatic suggestion" mechanism)? Not in v1; it would reuse this job.
8. **Monitored profiles (the future viral source).** When accounts the owner registers are added, they are third-party content: that needs an LGPD review and a Meta permissions check (Business Discovery only reaches business/creator accounts). Is the seam (`FONTES` plus the two CHECK values) acceptable as the hand-off point?
9. **Combined job.** Is "Itens de pesquisa + Assuntos virais" in one job (two LLM calls per post) desired, or should it be one tipo per job?

## 9 · Tech-lead defaults for §8 (until the owner says otherwise)

1. Transcripts: not in v1. A later wave feeds Reels/YouTube audio through the self-hosted transcription seam (`transcription-contract.md`), under its quotas.
2. Literal-span rule: strict in v1 (prototype first, refine from what the owner sees discarded; `itens_descartados` makes it visible).
3. Caps: as proposed (30 posts/job, 10 jobs/user/day, 300 analyses/org/day, one active job per user).
4. Same phrase from two posts: first source wins (no `item_sources` table in v1).
5. `mc_posts`: all statuses, with a status filter chip.
6. Plays: snapshot at extraction time; no scheduled refresh in v1.
7. Auto-extraction: not in v1.
8. Monitored profiles: the `FONTES` seam is the hand-off point; LGPD + Meta permission review happens when that source is designed.
9. Combined job (items + topics) allowed.

**Migration number:** never hard-code it. The slice scaffolds it with `noctus.dev.scaffold_migration` and `task_branch integrate` re-checks collisions after the rebase (other sessions hold 218–220 in flight).

