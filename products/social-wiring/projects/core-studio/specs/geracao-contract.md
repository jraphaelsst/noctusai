# Geração — Dashboard, Chat, Biblioteca, Headlines, Roteiros, Treinamentos, Meu Perfil — build contract v1 (2026-10-10)

> Authored by the tech-lead session (noc6) on 2026-10-10, after the owner said: *"go all the way and
> build everything, then we validate all at once"*. It covers what is left of CoreStudio's tree after
> Minha Pesquisa (+ Assuntos Virais), Extrair Pesquisa and Segundo Cérebro (+ voice answers, Minhas
> extrações). The shape follows `pesquisa-wave2-contract.md` and `cerebro-contract.md`. **§12 lists
> every tech-lead default the owner still has to validate.** Where the defaults leave a gap, §12
> applies. Where this file disagrees with CoreStudio, this file wins (§11).

Behaviour reference: `page-map-v2.md` §2, §3, §10, §14–§21, §24 · `mechanisms.md` §5–§11, §13, §15 ·
`biblioteca-roteiros-analysis.md` §1–§6 · `frontend-js-analysis.md` §1.7–§1.9, §2.2, §3.4 ·
`prompts/headline-engenharia-reversa-DRAFT.md` · `prompts/roteiro-DRAFT.md` · `DECISIONS.md` rounds 1–9.

---

## 0 · Before you dispatch: what the code says (verified 2026-10-10 on `origin/dev` @ 44c5168a7)

1. **The migration number is 229.** `noctus.dev.next_migration_number` reports 225–228 as taken
   (`225_transcricoes`, `226_imovel_captacao_manual`, `227_campanha_veiculacoes_nivel_not_null`,
   `228_imovel_duplicatas`). There is **one shared migration**, `229_cs_geracao.sql`, written by BE-0
   in wave 0, with every DDL statement in §2. No other slice writes a migration. Run
   `noctus.dev.scaffold_migration` again at integrate time, because another session may take 229
   first. If it does, renumber the file; never edit a number by hand after integrate.
2. **A fourth lifespan worker is not allowed (DRY, N=3 already).** `app/lifespan.py` already starts
   three seed `Worker`s by hand: edicao_fotos, pesquisa_extracao and transcricoes. The comment in
   `pesquisa_extracao_worker.py` said to formalize at the third case, and that did not happen. Each one
   also copies the same `_task/_stop` globals and start/stop/is_running code. This contract adds two
   more workers (`geracao`, `biblioteca`). So **BE-0 formalizes the pattern first**:
   - `ModuleRegistration` gets `startup: list[async callable]` and `shutdown: list[async callable]`, and the lifespan iterates over them;
   - the seed gets a `WorkerHandle` (S0a, see below);
   - the three existing workers move onto both, with no change in behaviour.
3. **The seed LLM layer has no tool calling.** `noctusai_lib.integrations.llm` exposes
   `chat_completion` and `chat_completion_stream` (messages in, text out). No provider takes `tools=`.
   The only tool-using agent runtime is product-local: `products/agents` runs the Claude Agent SDK.
   So in v1 the chat "tools" (search my research, my brains, library virals) are **server-side
   retrievers that run before generation** (§6.3), not model tool calls. This is
   `NOC-REMEDIATE[llm-tool-use]`: once the seed gets tool calling (Fake + Real for every provider),
   the retrievers become tools with no change to the API.
4. **Streaming already exists, so reuse its wire format.** `chat_completion_stream`, `StreamOutcome`
   (truncation) and the seed `help_chat` organ (`domain/help_chat/router.py`) define the SSE frames
   `data: {"delta"}`, `{"truncated"}`, `{"done"}` and `{"error":{code,message}}`, plus continuation
   rounds when the reply is cut off. The new chat uses **the same frames and the same continuation
   logic**. It does **not** mount the help_chat router: that organ is deliberately knowledge-only and
   never reads tenant data, which is the opposite of this chat. The front-end stream reader currently
   lives inline in `HelpChatBubble.tsx`; the new chat makes it N=2, so S0b extracts it into
   `@noctusai/lib` (`readSseStream`) and moves HelpChatBubble onto it.
5. **Model choice.** The newest Claude model in the seed catalog (`llm/models.py`, priced) is
   **`claude-opus-5`**. The process default is `gpt-4o-mini`. Generation code pins
   `provider="anthropic"` and reads the model from config (`GERACAO_LLM_MODEL=claude-opus-5`).
   Library classification is a high-volume, simple task, so it uses `claude-haiku-4-5`
   (`BIBLIOTECA_LLM_MODEL`). Never pin a model that is not in the catalog: an unregistered model is
   recorded as costing 0, and that silently disarms `enforce_budget`. Without `ANTHROPIC_API_KEY`
   resolvable for the org, every generation endpoint answers 503 `ia_nao_configurada` (same code as
   help_chat).
6. **Instagram: the marcas' usual connection cannot do Business Discovery.**
   - SW's Instagram insights use **Instagram Login** (`integration_accounts.provider='instagram'`, `graph.instagram.com`). That API **has no Business Discovery**.
   - Business Discovery (`GET /{ig-user-id}?fields=business_discovery.username(h){…}`) exists only on the **Facebook-Login** connection (`provider='meta'`, `graph.facebook.com`).
   - That connection's pinned scopes (`META_IA_OAUTH_SCOPES` in `routers/integration_accounts_router.py`) already include `instagram_basic`, `pages_show_list`, `pages_read_engagement` and `instagram_manage_insights`.
   - The seed Meta adapter has **no** business-discovery call (S0a adds it: Protocol + Fake + Real).
   - Business Discovery returns `like_count`, `comments_count`, caption, permalink, timestamp, media type and `media_url`/`thumbnail_url`. It **does not return views**, so the viral metric falls back to likes + comments (§3.3). S0a verifies this live.
   - Consequence: monitoring works only through an org account with `provider='meta'`. The page says so (§7.4).
7. **The transcription quotas would let library work starve voice answers.**
   - `reservar_transcricao` (migration 225) charges every row against per-user (≤ 30 min/24 h), per-org (≤ 120 min/24 h) and global (≤ 600 min, depth ≤ 20) limits, and the queue is FIFO (`claim_next_job ORDER BY created_at`).
   - Library Reels sent through that path would use up the org's 120 minutes and the global depth, and voice answers would then get 429/503.
   - **Owner decision (relayed by noc6, 2026-10-10):** the "only one queue drains the transcriber" rule is gone. SW `transcricoes` and core's `transcricao_api_habilitada` queue are **both on**.
     - The transcriber still runs one job at a time (`Semaphore(1)`) and answers 503 when busy.
     - SW turns that 503 into `RescheduleLater`, which does not use up a retry.
   - Library transcription is therefore specified (§3.4) as a **lower-priority consumer with its own budget**:
     - it has its own `origem` and its own reservation RPC;
     - its rows are not counted in the user, org or global voice counters;
     - its own Worker claims a job only while no voice-answer job is pending or processing.
   - Owned by BE-3. This sits under `NOC-REMEDIATE[transcription-fairness]`, the marker the transcription contract already defined. **noctusai-fe (owner of the core transcription API) reviews §3.4 before it ships.**
8. **`require_platform_admin` lives in `app/modules/transcricoes/router.py`.** Treinamentos admin is
   its second consumer, so BE-0 moves it to `app/dependencies.py`, and transcricoes imports it from there.
9. **No web-search provider exists in the seed or in core.** The only one is the `WebSearch` tool of
   the Claude Agent SDK inside `products/agents`, which is product-local. Roteiro Avançado's
   **"Pesquisar na web" is phase 2**: it shows "Em breve", and `NOC-REMEDIATE[roteiro-web-search]`
   names the next step. That step is a seed web-search seam, or the Anthropic server-side web-search
   tool once seed tool calling exists (item 3). **"Link específico" is also phase 2**, behind the same
   security review as the cérebro URL sources (`cerebro-contract.md` §10.3).
10. **No SSRF-safe downloader exists in the seed.** Library media (thumbnails, and Reels for
    transcription) are fetched by `noctusai_lib.integrations.media.safe_fetch` (S0a, §9.2).
11. **The research slugs are already CoreStudio's blueprint slugs.** `pesquisa_variables.py` stores
    the DB slugs (`DORES-TANGIVEIS-DO-AVATAR`, `PESSOAS-PERSONAGENS-CONHECIDOS-PELO-AVATAR`, …), so a
    blueprint `{{SLUG}}` joins `cs_research_items.variable_slug` directly. The blueprint slot
    `{{GPT}}` is **not** the global variable `GPT` (id 29, purpose unknown). It stays a slot the model
    fills freely (DRAFT §3).
12. **`cs_marca_perfil` (224) holds only `bio`.** The other Meu Perfil fields are added to it (§2.1).
    The cérebro bio card and the new Meu Perfil page edit **the same row**: one service, two callers.
13. **The `FONTES` seam** (`pesquisa_fontes.py`) can later take monitored-profile posts as an Extrair
    Pesquisa source (wave-2 contract §8 Q8). That is out of scope here and listed in §13.

---

## 1 · Scope and decisions encoded

### 1.1 Pages (all `status_pagina = 'desenvolvimento'`, owner-only until validated)

| # | Page (CoreStudio label) | Route | `status_pagina` key | Sidebar position |
|---|---|---|---|---|
| P1 | **Dashboard** | `/media-creation/dashboard` | `media-creation-dashboard` | Criação de mídia › Dashboard |
| P2 | **Criar Headlines e Roteiros** | `/media-creation/chat` (`?c=`, `?cite_viral=`, `?cite_perfil=`) | `media-creation-chat` | Criação de mídia › Criar Headlines e Roteiros |
| P3 | **Biblioteca** (Biblioteca de virais) | `/media-creation/biblioteca` (`?viral=`, `?perfil=`) | `media-creation-biblioteca` | Criação de mídia › Biblioteca |
| P4 | **Meu Perfil** (Minha conta › Meu Perfil, per marca) | `/media-creation/perfil` | `media-creation-perfil` | Criação de mídia › Configurações › Meu Perfil |
| P5 | **Minha Biblioteca** | `/media-creation/minha-biblioteca` | `media-creation-minha-biblioteca` | › Configurações › Minha Biblioteca |
| P6 | **Treinamentos** | `/media-creation/treinamentos` | `media-creation-treinamentos` | › Configurações › Treinamentos |
| P7 | **Gerar Headlines** (landing + form/history) | `/media-creation/headlines/gerar` and `/media-creation/headlines?who=me\|public\|viral` (`&lote=`) | `media-creation-headlines-gerar` (both routes) | › Configurações › Headlines › Gerar Headlines |
| P8 | **Headlines Favoritas** | `/media-creation/headlines/favoritas` (`?hid=`) | `media-creation-headlines-favoritas` | › Configurações › Headlines › Headlines Favoritas |
| P9 | **Headlines sugeridas** | `/media-creation/headlines/sugeridas` (`?hid=`) | `media-creation-headlines-sugeridas` | › Configurações › Headlines › Headlines sugeridas |
| P10 | **Roteiros** (Meus roteiros) | `/media-creation/roteiros` (`?open=`) | `media-creation-roteiros` | › Configurações › Roteiros |
| — | **Roteiro Avançado** (a modal, not a page) | opened from P1, P2, P7, P8, P9, P10 | — | — |

- **Sidebar.** Both nav configs in `App.tsx` get one link per page. The labels are CoreStudio's, and
  the tree is 4 levels deep (`Criação de mídia › Configurações › Headlines › Gerar Headlines`, which
  the seed `NavGroup` supports).
- **Order inside Criação de mídia:**
  - items: Criação de mídia (the old page, unchanged) · Dashboard · Criar Headlines e Roteiros · Biblioteca
  - groups: Pesquisa · Segundo Cérebro · **Configurações** (Meu Perfil · Minha Biblioteca · Treinamentos · group **Headlines** › Gerar Headlines · Headlines Favoritas · Headlines sugeridas · then Roteiros)
- **Brand switcher.** Every page is per marca and reuses `components/pesquisa/MarcaSwitcher.tsx` and
  `hooks/useMarcaPesquisa.ts` unchanged. The remembered marca (`sw.pesquisa.marca`) is shared across
  the whole module, on purpose.

### 1.2 Owner decisions this contract encodes

- Keep CoreStudio's structure, mechanisms and labels; use our design system (2026-10-05).
- The headline system prompt **merges** the reverse-engineered payload with Método Audience (round 7).
  It is DRAFT (§5.4).
- The Núcleo de Influência source is the marca's **bio** (round 7).
- The viral library comes from high-performing Instagram posts. The source is decided by a tech-lead
  default (§12): **monitored profiles**, read through the official Business Discovery API.
- Voice transcription is **on in prod** (`transcricao_habilitada=true`, round 9). Library Reels are
  transcribed through the shared layer as a lower-priority, separately budgeted consumer (§3.4).
- Build everything, then validate everything at once (round 9).

### 1.3 Dropped (deliberately, not deferred)

- **Workspaces / customers agency layer.** No workspace switch and no "Adicionar Workspace". The
  Biblioteca wizard's step 1 "Selecione o workspace" is gone: the marca switcher plays that role.
- **"Headlines na Box"**: the offcanvas cart, saving to a customer and week, and the
  "Adicionar na Box" button.
- **Credits / twin billing**: `twin/api/credits`, recharges, faturamento. Spend is bounded by caps (§9.4) and the seed org LLM budget.
- **Dead or legacy UI from the page map:**
  - `#modal-report` (Tabler demo)
  - the "O que vamos criar hoje?" / `mamanai/proccess` box
  - the floating legacy aiChat
  - the hidden `who=search` "busca inteligente" form
  - the legacy `#modal-make-headlines` copy
  - legacy roteiro paths A/B/C (`roadmaps/store`, `favorites/store`, `reversa/store`); Roteiro Avançado is the one roteiro path
  - `headline_express` (agent 3)
  - the debug `#viewHeadlineFlowModal` and the payload/params tabs
  - the `Versão do Layout` field
  - the Dashboard **"Diagnóstico — a preencher"** card (its meaning was never found)
  - the dormant "select up to 60 posts" Instagram modal
  - the first-access tutorial modal and `first-access-seen`
  - notifications polling (SW has its own NotificationBell)
- **Meu Perfil personal fields**: Nome, Sobrenome, Email, Senha, Telefone, Instagram/TikTok handle
  text. The platform account and Conexões › Marcas already own these.
- **Staff "Core" (gold-standard) flag** and the `core=` filter. **TikTok/YouTube** as library networks
  (Instagram only; the `rede` column allows extension).
- **Mutating GETs** (CoreStudio's `delete/{id}`, `reprocess/{id}`). Every mutation here is POST/PUT/PATCH/DELETE.

---

## 2 · Data — migration `229_cs_geracao.sql` (schema `social_wiring`, one file, BE-0)

- Forward-only and idempotent. It carries the same guard block as 217/224: `public.current_org_id_for(text)` exists, and 217, 221, 224 and 225 are applied, which it checks by table existence.
- **RLS on every `org_id` table matches 217:**
  - authenticated select/write `USING (org_id = (SELECT public.current_org_id_for('social_wiring')))`;
  - `service_role` ALL.
- **Exceptions:**
  - Static taxonomies and `cs_treinamentos`: authenticated select `true`, service_role ALL.
  - `cs_chat_*` and `cs_memorias` add `AND user_id = (SELECT auth.uid())`. Chats and memories are private to their user.
- `updated_at` triggers use `social_wiring.set_updated_at_media_creation()`.
- Every CHECK listed below is in the DDL; services validate too, but the DB is the last word.

### 2.1 Meu Perfil — `ALTER TABLE cs_marca_perfil`
`nichos int[] NOT NULL DEFAULT '{}'` CHECK `cardinality(nichos) <= 3` · `profissoes int[] NOT NULL
DEFAULT '{}'` CHECK `<= 3` · `apresentacao_magnetica text NOT NULL DEFAULT ''` CHECK `char_length <= 3000` ·
`ctas text NOT NULL DEFAULT ''` CHECK `<= 3000`. The service checks the ids against the taxonomy
tables, because Postgres has no array FK (unknown id → 422). `bio` is unchanged (≤ 5 000).

### 2.2 Static taxonomies (seeded; SQL generated by `app/modules/media_creation/geracao_taxonomias.py :: seed_sql()`; a test asserts the migration carries that exact text, as with `pesquisa_variables.py`)

| Table | Rows | Columns |
|---|---|---|
| `cs_nichos` | 28 (CoreStudio ids and labels, `biblioteca-roteiros-analysis.md` §1.4) | `id int PK`, `nome`, `sort_order` |
| `cs_profissoes` | 102 (same source; sorted alphabetically for display) | `id int PK`, `nome` |
| `cs_formatos_video` | 15 (1 Lista de Valor Prático … 15 Websérie) | `id int PK`, `nome`, `definicao` (from `docs/platform-study.md` rubric; where none was captured, written here and marked DRAFT) |

These are kept as Python constants only, with no table:
- **gatilhos**: the 7 Método Audience names. Slugs `recompensa, misterio, reconhecimento, popularidade, crenca, autoridade, disrupcao`; formulas from `METODO_TRIGGERS`.
- **tons de comunicação**: 6 values (10–15 from `mechanisms.md` §5.5).
- **criatividade**: `essencial | equilibrado | explorador`.

All three are stored as text with a CHECK where they are persisted.

### 2.3 Biblioteca (org-scoped corpus + per-marca allow-list)

**`cs_perfis_monitorados`**: the corpus source, one row per handle per org.
| column | type / rule |
|---|---|
| `id` uuid PK · `org_id` | |
| `rede` | text CHECK `('instagram')` |
| `handle` | text, lowercase, CHECK `handle ~ '^[a-z0-9._]{1,30}$'`; unique `(org_id, rede, handle)` |
| `conta_descoberta_id` | uuid FK `integration_accounts` ON DELETE SET NULL. The `provider='meta'` account whose token runs Business Discovery |
| `ig_user_id`, `nome`, `foto_path`, `seguidores`, `media_count` | from Business Discovery |
| `status` | CHECK `('aguardando','ativo','pausado','nao_encontrado','sem_conta','erro')` |
| `erro_codigo`, `erro_mensagem` | pt-BR |
| `ultima_sync_em`, `proxima_sync_em` | timestamptz |
| `metrica_base` | CHECK `('views','engajamento')`, chosen per profile (§3.3) |
| `mediana_metrica` | numeric NULL; NULL means fewer than 10 posts, "dados insuficientes" |
| `created_by`, `created_at`, `updated_at` | |

**`cs_virais`**: one row per post of a monitored profile. Every ingested post gets a row; `e_viral` flags the outliers.
| column | type / rule |
|---|---|
| `id` uuid PK · `org_id` · `perfil_id` FK CASCADE | |
| `codigo` | bigint identity, unique per org. A short human id shown as "estrutura #codigo" and used in chat citations and deep links |
| `ig_media_id` text; unique `(perfil_id, ig_media_id)` | |
| `permalink`, `media_type`, `media_product_type`, `caption` (≤ 5 000), `publicado_em` | |
| `likes`, `comments`, `views` | bigint NULL (NULL = not served, never 0) |
| `duracao_s` | numeric NULL (from the transcriber probe) |
| `thumbnail_path` | private bucket `sw-biblioteca` (§2.7) |
| `metricas_em` | timestamptz |
| `score_viral` | numeric NULL; `e_viral` bool default false |
| `transcricao_status` | CHECK `('nao_aplicavel','pendente','na_fila','concluida','falhou','grande_demais','longa_demais','sem_orcamento')` |
| `transcricao_id` | uuid FK `transcricoes` ON DELETE SET NULL |
| `transcricao_texto` | text ≤ 50 000 |
| `classificacao_status` | CHECK `('pendente','processando','concluida','falhou')` |
| `gancho` | the spoken or written hook, ≤ 1 000 |
| `blueprint` | text ≤ 10 000. The CoreStudio "blueprint document": HEADLINE ORIGINAL / BLUEPRINT with `{{DB-SLUG}}` / PROMPT EXPLICATIVO (DRAFT §1.2 variant A, without the self-check block) |
| `blueprint_slots` | text[]: distinct slugs in the blueprint (`GPT` allowed) |
| `formato_ids`, `nicho_ids`, `profissao_ids` | int[] (≤ 3 each) |
| `gatilho` | text CHECK in the 7 slugs, NULL allowed |
| `classificado_em`, `classificacao_modelo`, `classificacao_erro` | |
| `created_at`, `updated_at` | |

Indexes:
- `(org_id, e_viral, score_viral DESC)`
- `(perfil_id, publicado_em DESC)`
- GIN on `nicho_ids`, `profissao_ids`, `formato_ids`, `blueprint_slots`
- `to_tsvector('portuguese', coalesce(gancho,'') || ' ' || coalesce(transcricao_texto,''))` GIN for keyword search

**`cs_biblioteca_referencias`** (Minha Biblioteca; the per-marca allow-list):
- Columns: `id` · `org_id` · `marca_id` FK CASCADE · `modo` CHECK `('perfil','video')` · `perfil_id` FK CASCADE NULL · `viral_id` FK CASCADE NULL · `auto_atualizar` bool default true · `posts_ate` date NULL · `created_by`, `created_at`, `updated_at`.
- CHECK `(modo='perfil') = (perfil_id IS NOT NULL AND viral_id IS NULL)` and the converse for `video`.
- Unique `(marca_id, perfil_id) WHERE modo='perfil'`; unique `(marca_id, viral_id) WHERE modo='video'`.

### 2.4 Headlines

**`cs_headline_lotes`** (one generation request):
| column | type / rule |
|---|---|
| `id` · `org_id` · `marca_id` FK CASCADE · `created_by` | |
| `origem` | CHECK `('form_me','form_public','form_viral','biblioteca','sugestao_auto')` |
| `parametros` | jsonb NOT NULL. The validated request (§4.4 `LoteParams`), kept for reprocessing and audit |
| `status` | CHECK `('criando','processando','completo','falha')` (UI: Criando / Processando / Completo / Falha) |
| `etapa` | text NULL, the real step ("Gerando headlines — estrutura 2 de 5") |
| `estruturas_total`, `estruturas_processadas`, `estruturas_com_erro` | int |
| `aviso_poucas_estruturas` | bool (fewer than 3 compatible structures) |
| `fallback_metodo` | bool (no library structure was available, so Método Audience templates were used, §5.2) |
| `erro` | pt-BR |
| `queue_job_id`, `modelo`, `prompt_versao` | |
| `started_at`, `finished_at`, `created_at`, `updated_at` | |

Indexes `(marca_id, created_at DESC)` and `(created_by, created_at DESC)`. A partial unique index on
`(created_by) WHERE status IN ('criando','processando') AND origem <> 'sugestao_auto'` allows **one
active manual batch per user**.

**`cs_headlines`**:
| column | type / rule |
|---|---|
| `id` · `org_id` · `marca_id` · `lote_id` FK CASCADE NULL (NULL means it was saved from the chat) | |
| `viral_id` | FK `cs_virais` ON DELETE SET NULL. The structure used; NULL for a Método template or a chat headline |
| `template_metodo` | int NULL (1..32, when it fell back to Método Audience) |
| `texto` | ≤ 1 000, trimmed, non-empty |
| `texto_original` | the model's text before user edits (set once) |
| `angulo` | int 1/2 (headline_1 / headline_2) |
| `itens_usados` | jsonb `[{slot, item_id, conteudo}]`. Only literal matches the server could verify (§5.3) |
| `favorita` bool default false · `favoritada_em` | |
| `modo` | CHECK `('manual','automatico')` NULL. Set for suggested headlines (origem `biblioteca` → manual, `sugestao_auto` → automatico) |
| `created_by`, `created_at`, `updated_at` | |

Indexes `(marca_id, favorita, favoritada_em DESC)` and `(marca_id, modo, created_at DESC)`.
"Roteiro criado" is derived: a roteiro exists with `headline_id = id`.

### 2.5 Roteiros — `cs_roteiros`
| column | type / rule |
|---|---|
| `id` · `org_id` · `marca_id` · `created_by` | |
| `nome` | 1..160, default `Roteiro: <headline truncated>` |
| `headline_id` | FK `cs_headlines` ON DELETE SET NULL; `headline_texto` 1..1 000 (copied, so it survives a deleted headline) |
| `instrucoes` | ≤ 5 000 |
| `fonte` | CHECK `('ia','web','link')`. v1 accepts only `ia` (422 otherwise, §4.6) |
| `duracao` | CHECK `('auto','1','2','3')` |
| `brain_id` | FK `cs_brains` ON DELETE SET NULL · `viral_id` FK `cs_virais` ON DELETE SET NULL |
| `perguntas` | jsonb `[{id, pergunta, resposta}]` (≤ 5 questions, answers ≤ 1 000) |
| `status` | CHECK `('criando','perguntas','processando','completo','falha')` |
| `etapa`, `erro` | |
| `conteudo` | text ≤ 30 000 (markdown) · `conteudo_original` (first generation) · `versao` int (bumped on each user save) |
| `fontes` | text NULL (always NULL in v1; filled when web/link sources land) |
| `feedback` | CHECK `('gostei','nao_gostei')` NULL · `feedback_motivo` ≤ 1 000 |
| `queue_job_id`, `modelo`, `prompt_versao`, `created_at`, `updated_at`, `finished_at` | |

Index `(marca_id, created_at DESC)`.

### 2.6 Chat and memory
- **`cs_chat_conversas`**: `id` · `org_id` · `marca_id` FK CASCADE · `user_id` · `agente` CHECK `('headline','roteiro')` · `titulo` 1..100 · `last_message_at` · audit columns. Index `(user_id, marca_id, agente, last_message_at DESC)`.
- **`cs_chat_mensagens`**: `id` · `org_id` · `conversa_id` FK CASCADE · `role` CHECK `('user','assistant')` · `conteudo` ≤ 100 000 · `referencias` jsonb (the resolved `@` references: `[{tipo, id, rotulo}]`) · `status` CHECK `('completa','parcial','erro')` · `truncada` bool · `modelo` · `contexto_chars` int · `created_at`. Index `(conversa_id, created_at)`.
- **`cs_memorias`**: `id` · `org_id` · `user_id` · `marca_id` FK CASCADE · `texto` 1..500 trimmed · `created_at`. At most 50 per `(user_id, marca_id)` (service, 409).

### 2.7 Treinamentos, storage, nav
- **`cs_treinamentos`** (platform-wide, no `org_id`): `id` uuid · `ordem` int unique · `titulo` 1..160 · `descricao` ≤ 1 000 · `video_url` text NULL CHECK `video_url ~ '^https://'` · `ativo` bool default true · `updated_by`, `updated_at`.
  - It is seeded with CoreStudio's **5 lessons** (titles and descriptions verbatim from `biblioteca-roteiros-analysis.md` §4) with `video_url = NULL`.
  - Writes go through the backend only (platform admin).
- **Bucket** `sw-biblioteca`, `public=false` (ON CONFLICT DO NOTHING). It holds thumbnails only, under `{org}/{perfil}/{ig_media_id}.jpg`. Signed URLs live 900 s. `check_storage_no_public_buckets` must stay green.
- **Transcription lane (§3.4)**, applied to `social_wiring.transcricoes`:
  - `ADD COLUMN origem text NOT NULL DEFAULT 'usuario' CHECK (origem IN ('usuario','biblioteca'))`.
  - `user_id` stays NOT NULL. A library row carries the `created_by` of the monitored profile, so the existing RLS still holds, and it is excluded from the per-user quota (below).
  - New RPC `reservar_transcricao_biblioteca(p_id, p_org, p_user, p_duracao_s, p_bytes, p_formato, p_contexto_ref, p_storage_path)`: advisory lock, then the library caps of §3.4, then insert with `origem='biblioteca'`, `contexto_tipo='biblioteca_viral'`.
  - `reservar_transcricao` is redefined (CREATE OR REPLACE) so that **every one of its counters adds `AND origem = 'usuario'`**: per user, per org, global minutes and global depth. Library rows can never cause a 429 or `fila_cheia` for a voice answer.
- **`status_pagina`**: `INSERT … ('<key>','desenvolvimento') ON CONFLICT DO NOTHING` for the 10 keys in §1.1. `filterNavByPageStatus` hides any page that is absent from the table.

---

## 3 · Async work: jobs, workers, schedules

### 3.1 Workers (seed `domain.jobs.Worker` over `social_wiring.jobs`, registered through the BE-0 `ModuleRegistration.startup` hooks)

| Worker | Types | Concurrency | Lease | Switch |
|---|---|---|---|---|
| `geracao` | `headline.gerar`, `roteiro.perguntas`, `roteiro.gerar` | 1 per process | 600 s + heartbeat | `GERACAO_WORKER_ENABLED` (env, default true). Submit returns 503 `geracao_indisponivel` when it is off |
| `biblioteca` | `biblioteca.sync_perfil`, `biblioteca.classificar`, `biblioteca.transcrever` | 1 | 600 s | platform setting `biblioteca_ingestao_habilitada` (DB first, then env, **default OFF**, §9.2), checked in `claim_gate` |
| `transcricao.biblioteca` (inside the transcricoes module, BE-3) | `transcricao.biblioteca` | 1 | 300 s | `transcricao_habilitada` ∧ no user voice job pending (§3.4) |

Handlers are registered by type in `services/geracao_jobs.py` (BE-0): `register_handler(job_type, fn)`.
The services register their own handlers at import. Retry policy is `max_retries=2, backoff 5 s`.
`DeadLetterError` covers a missing row. A reconcile sweep turns a dead-lettered queue row's domain
row to `falha`.

### 3.2 Status machines (real status only, never fake progress)

| Thing | States | Notes |
|---|---|---|
| Headline batch | `criando → processando → completo \| falha` | `etapa` and the counters update after every structure. If at least one structure produced headlines the batch ends `completo`, with `estruturas_com_erro` shown. If all failed it ends `falha` |
| Roteiro | `criando → perguntas → processando → completo \| falha` (with "Pular perguntas": `criando → processando`) | `perguntas` waits for the user, so it is not stale |
| Profile sync | `aguardando → ativo \| nao_encontrado \| sem_conta \| erro` | `pausado` is set by the user |
| Viral classification | `pendente → processando → concluida \| falhou` | |
| Viral transcription | §2.3 values | mirrors the shared `transcricoes` row via the completion hook |

The FE polls every 3 s while any visible row is non-terminal, and stops otherwise. Copy says "Isto
pode levar 1–2 minutos." No percentage is shown unless it comes from the counters.

**Stale sweep** (`geracao_scheduler.py`, the cerebro idiom, cron on a free minute set): `criando` or
`processando` older than 15 min → `falha` "Tempo esgotado — tente novamente."; classification
`processando` older than 15 min → `falhou`.

### 3.3 Library ingestion (`biblioteca.sync_perfil`, BE-2)

1. Business Discovery through `conta_descoberta_id`, using the S0a adapter. Page size is 25. The
   first sync reads up to **50** posts. Later syncs read until the newest stored `ig_media_id`, and
   re-read the last 30 days for fresh metrics.
   - Unknown handle (error 100/110) → `nao_encontrado`.
   - Account missing, invalid or lacking scope → `sem_conta`.
   - Rate limit (4/17/32/613) → `RescheduleLater(900)`.
2. Upsert into `cs_virais`. Thumbnails go through `safe_fetch` (image magic bytes, ≤ 2 MB) into `sw-biblioteca`.
3. **Viral metric.**
   - `metrica_base='views'` if `views` is non-null on ≥ 80 % of the profile's window; otherwise `engajamento = coalesce(likes,0) + coalesce(comments,0)`, which is NULL when both are NULL.
   - `mediana_metrica` is the median over the profile's last 50 posts with a non-null metric. It needs ≥ 10 such posts; otherwise it is NULL and nothing is viral.
   - `score_viral = metrica / greatest(mediana, 1)`.
   - `e_viral = score_viral ≥ BIBLIOTECA_VIRAL_RATIO (3.0) ∧ age ≥ 48 h`. The age rule waits for metrics to settle.
   - Everything is recomputed on every sync.
4. For each **new** `e_viral` post: `classificacao_status='pendente'`.
   - If `media_product_type ∈ {REELS}` or `media_type=VIDEO`: `transcricao_status='pendente'` and enqueue `biblioteca.transcrever`.
   - Otherwise: `nao_aplicavel` and enqueue `biblioteca.classificar` right away.
5. `biblioteca.transcrever`:
   - `safe_fetch(media_url)` with Instagram-CDN hosts only and a 15 MB cap; over the cap → `grande_demais`.
   - Probe; longer than 3 min → `longa_demais`.
   - `TranscricaoService.submit_sistema(...)` (§3.4). Out of budget → `sem_orcamento`, retried by the next daily sync.
   - The completion hook `biblioteca_viral` writes `transcricao_texto`, then enqueues `biblioteca.classificar`.
   - Every terminal non-success state still classifies, from the caption.
6. `biblioteca.classificar` (LLM `BIBLIOTECA_LLM_MODEL`, prompt `prompts/biblioteca_classificador.py`, DRAFT): one call per viral. Input: caption, transcript, the 28 niches, 102 professions, 15 formats, 7 triggers, and the classifiable research slugs with their descriptions. Strict JSON output:
   `{gancho, formato_ids[≤3], nicho_ids[≤3], profissao_ids[≤3], gatilho, blueprint, substituicoes:[{slug, definicao}], slots[]}`.
   - The parser drops unknown ids and slugs.
   - A blueprint slug that is not in `pesquisa_variables` (other than `GPT`) causes the blueprint to be **rejected**: blueprint NULL, structure unusable, with the error recorded.
   - The blueprint must reproduce `gancho` with only the slotted spans replaced (checked server-side by stripping the slots and comparing token overlap ≥ 0.8). If the check fails, the blueprint is NULL.
7. **Scheduler** `biblioteca_scheduler.py`:
   - Daily at 03:20 BRT, enqueue `sync_perfil` for each `ativo` profile referenced by at least one `auto_atualizar` reference, with `dedupe_key = sync:{perfil}:{date}`.
   - Manual "Atualizar agora" is allowed at most once per hour per profile (429).

### 3.4 Library transcription lane (BE-3, `app/modules/transcricoes/**`; **reviewed by noctusai-fe, owner of the core transcription API, before it ships**)

- **Lower priority, its own budget, never starves voice answers or core jobs.**
- `TranscricaoService.submit_sistema(data, contexto_ref, *, user_id)` follows the same validation order as `submit` (size → magic bytes → hook `validar` → probe), then calls `reservar_transcricao_biblioteca`.
- **Library caps** are config with finite defaults:
  - ≤ **60 min / 24 h** across the platform (`BIBLIOTECA_TRANSCRICAO_MIN_DIA_GLOBAL`)
  - ≤ **30 min / 24 h per org**
  - ≤ **3 min per reel**
  - ≤ **5 library rows** queued or processing
- These counters see only `origem='biblioteca'`. The voice counters see only `origem='usuario'` (§2.7).
- It enqueues job type **`transcricao.biblioteca`**, not `transcricao`.
- **Claim priority.** A second seed `Worker` in the transcricoes module handles only `transcricao.biblioteca`. Its `claim_gate` returns true only when:
  - `transcricao_habilitada` is on; and
  - no `jobs` row of type `transcricao` is `pending` (due) or `running`.

  It therefore takes the transcriber only when the voice-answer queue is empty.
- **Busy transcriber.** It still runs one job at a time (`Semaphore(1)`) and is shared with core's `transcricao_api_habilitada` queue. A 503 `ocupado` becomes `RescheduleLater(retry_after)` and does not use up a retry, exactly like the voice worker.
- **Worst case for a voice answer** submitted while a library job runs: it waits for that one job, which is ≤ 3 min of audio (about ≤ 5 min at the measured RTF). It never waits behind a library *queue*. Core jobs compete only through the semaphore, as they do today.
- `NOC-REMEDIATE[transcription-fairness]` is the named destination for the real fix: a platform-level priority queue across SW and core (`transcription-contract.md` §6). Keep the marker at the `claim_gate`.
- The voice and core paths keep their own behaviour: audio is deleted right after transcription, and the retention sweep and kill switch are unchanged. The library hook (`contexto_tipo='biblioteca_viral'`, `contexto_ref=viral_id`) is registered by BE-2 (`services/biblioteca_transcricao.py`). Its `validar` checks that the viral belongs to the org.

### 3.5 Headlines sugeridas automáticas (BE-4)
- `headline_scheduler.py`, daily at 06:10 BRT. Per marca that has a bio **and** at least 1 niche (otherwise skip and log), create one `sugestao_auto` batch.
- **Structures:** the top `HEADLINES_SUGERIDAS_POR_DIA_MARCA` (**5**, giving 10 headlines/day) `e_viral` virals with a usable blueprint, ranked by `score_viral`. Candidates are, in order:
  - virals of the marca's Minha Biblioteca profiles and videos, then
  - org virals whose `nicho_ids` overlap the marca's nichos.

  Virals used by this marca in the last 30 days are excluded.
- `dedupe_key = sug:{marca}:{date}`. No structures → no batch, logged (never an empty "completo").
- A **"Gerar sugestões agora"** button on P9 (rate limit 1 per marca per day, 429) lets the owner test it on prod without waiting for the cron.

---

## 4 · Endpoints — prefix `/api/media-creation`, auth `get_current_user_org`

Conventions:
- `success_response` envelope, pt-BR `detail`, `StrictHttpModel` bodies.
- A foreign or unknown marca, headline, roteiro, viral, profile, conversation or memory → **404** (never 403; ids are not enumerable).
- Forbidden state → **409**. Validation → **422**. Caps → **429** with `Retry-After`. Worker or AI unavailable → **503** `{code}`.
- Every LLM-triggering route has `@limiter.limit(DEFAULT_AI_RL)`. Every read by id is scoped to `org_id` **and** the caller's marca rights. This is the CoreStudio IDOR lesson, `mechanisms.md` §15.

### 4.1 Perfil + taxonomias (`routers/perfil_criacao.py`, BE-1)
| # | Method + path | Request | `data` |
|---|---|---|---|
| 1 | `GET /taxonomias` | — | `Taxonomias` |
| 2 | `GET /perfil` | `marca_id` | `PerfilCriacao` (empty defaults if no row) |
| 3 | `PUT /perfil` | `{marca_id, bio?, nichos?, profissoes?, apresentacao_magnetica?, ctas?}` (PATCH semantics) | `PerfilCriacao`; more than 3 → 422 "Selecione até 3 nichos" / "Selecione até 3 profissões" |

`cerebro` `GET/PUT /cerebro/perfil` stays as it is and **delegates** to `perfil_service` (BE-1 edits
those two handlers only).

### 4.2 Treinamentos (`routers/treinamentos.py`, BE-1)
| 4 | `GET /treinamentos` | — | `Treinamento[]` (active, by `ordem`) |
| 5 | `PUT /treinamentos/{id}` | admin; `{titulo?, descricao?, video_url?, ativo?, ordem?}` | `Treinamento`; `video_url` host not in `TREINAMENTO_VIDEO_HOSTS` (`iframe.mediadelivery.net`, `player.vimeo.com`, `www.youtube.com`, `www.youtube-nocookie.com`) → 422 |
| 6 | `POST /treinamentos` · `DELETE /treinamentos/{id}` | admin | 201 · 204 |

Admin means `require_platform_admin` (moved to `app/dependencies.py` by BE-0); anyone else gets 403.
`GET /treinamentos/admin` returns `{is_admin: bool}` so the FE can show the edit controls.

### 4.3 Biblioteca + Minha Biblioteca (`routers/biblioteca.py`, BE-2)
| # | Method + path | Request | `data` |
|---|---|---|---|
| 7 | `GET /biblioteca/virais` | `marca_id`, `nichos[]?`, `profissoes[]?`, `ver_todos?` (default false ⇒ auto-filter by the marca's nichos ∪ profissões, `filtro_automatico: true` in the response), `ordem ∈ {mais_vistos, mais_recentes}`, `q?` (comma-separated keywords), `buscar_em ∈ {gancho, transcricao}` (default gancho), `data_de?`, `data_ate?`, `views_min?`, `likes_min?`, `comments_min?`, `perfil_id?`, `formato_id?`, `codigo?`, `somente_virais` (default true), `page` (24 per page) | `{items: ViralCard[], total, page, filtro_automatico}` |
| 8 | `GET /biblioteca/virais/{id}` | `marca_id` | `ViralDetalhe` (signed thumbnail URL, transcript, badges, `blueprint` hidden unless `?debug=1` for platform admin) |
| 9 | `GET /biblioteca/perfis` | `q?` | `PerfilMonitorado[]` (org) |
| 10 | `GET /biblioteca/perfis/verificar` | `handle` | `{status: 'disponivel'\|'ja_monitorado'\|'na_minha_biblioteca'\|'sem_conta_descoberta', perfil?}` |
| 11 | `POST /biblioteca/perfis` ("Solicitar Perfil") | `{marca_id, handle, conta_descoberta_id?}` | 201 `PerfilMonitorado` (`aguardando`, sync enqueued) + a `perfil` reference for this marca. Normalization as in CoreStudio (strip, URL → handle, reserved segments rejected, `^@?[a-zA-Z0-9._]{1,30}$`). More than `BIBLIOTECA_MAX_PERFIS_ORG` (30) → 409. Ingestion switch off → 201 with status `aguardando` and a banner (never a silent no-op) |
| 12 | `POST /biblioteca/perfis/{id}/sincronizar` | — | 202; once per hour per profile → 429 |
| 13 | `PATCH /biblioteca/perfis/{id}` | `{status: 'ativo'\|'pausado', conta_descoberta_id?}` | `PerfilMonitorado` |
| 14 | `DELETE /biblioteca/perfis/{id}` | — | 204; deletes its virals, thumbnails and transcripts (LGPD, §9.3); 409 if another marca of the org still references it ("Perfil em uso por outra marca") |
| 15 | `GET /biblioteca/contas-descoberta` | — | the org's `provider='meta'` validated accounts `[{id, nome, ig_username}]` |
| 16 | `GET /biblioteca/referencias` | `marca_id`, `q?` | `Referencia[]` |
| 17 | `POST /biblioteca/referencias` | `{marca_id, modo:'perfil', perfil_ids[1..20], auto_atualizar}` or `{marca_id, modo:'video', viral_ids[1..50]}` | `{criadas, ja_existentes}` |
| 18 | `PATCH /biblioteca/referencias/{id}` | `{auto_atualizar?, posts_ate?}` | `Referencia` |
| 19 | `DELETE /biblioteca/referencias/{id}` | — | 204 |

The Biblioteca wizard's topics reuse the existing `GET /pesquisa/assuntos-virais?status=approved`. No new endpoint is needed.

### 4.4 Headlines (`routers/headlines.py`, BE-4)
| # | Method + path | Request | `data` |
|---|---|---|---|
| 20 | `POST /headlines/lotes` | `LoteCreate` (below) | 202 `HeadlineLote`. Second active batch → 409 "Já existe uma geração em andamento"; more than `HEADLINE_LOTES_DIA_USUARIO` (30) → 429; empty bio → 422 "Preencha a bio em Meu Perfil antes de gerar headlines" |
| 21 | `GET /headlines/lotes` | `marca_id`, `origem_in?` (default the three `form_*`), `q?`, `limit≤50`, `offset` | `{items: HeadlineLote[], total}` |
| 22 | `GET /headlines/lotes/{id}` | — | `HeadlineLoteDetalhe` (with its headlines) |
| 23 | `POST /headlines/lotes/{id}/reprocessar` | — | 202 a **new** batch with the same `parametros` (the old one is kept) |
| 24 | `POST /headlines/lotes/excluir` | `{ids[1..100]}` | `{excluidos}` (cascades its headlines; favorites included, with a confirm in the UI) |
| 25 | `GET /headlines` | `marca_id`, `lista ∈ {favoritas, sugeridas}`, `modo?` (sugeridas), `q?`, `limit≤50`, `offset` | `{items: Headline[], total}`; sugeridas sorted by `viral.metrica DESC` then `created_at DESC` |
| 26 | `GET /headlines/{id}` | — | `Headline` |
| 27 | `PATCH /headlines/{id}` | `{texto}` | `Headline` (keeps `texto_original`) |
| 28 | `POST /headlines/{id}/favoritar` · `/desfavoritar` | — | `Headline` |
| 29 | `POST /headlines` | `{marca_id, texto, favoritar: true}` (save from chat or own headline) | 201 `Headline` (`lote_id` NULL) |
| 30 | `POST /headlines/excluir` | `{ids[1..100]}` | `{excluidos}` |
| 31 | `POST /headlines/sugestoes/gerar-agora` | `{marca_id}` | 202 `HeadlineLote` (`sugestao_auto`); once per marca per day → 429 |

`LoteCreate` (discriminated on `origem`):
```
{ marca_id, origem: 'form_me'|'form_public',
  variaveis: string[] (slugs of grupo especialista for me / publico for public; ['*'] = todas),
  valores?: {slug: item_id[]}  (approved items picked per variable; omitted = all approved),
  assunto?: string ≤ 300,
  referencia?: {tipo:'perfil', perfil_ids[1..2]} | {tipo:'formato', formato_ids[1..3]} | {tipo:'gatilho', gatilhos[1..3]},
  somente_pesquisa: bool,             // CoreStudio complete_with_research
  criatividade: 'essencial'|'equilibrado'|'explorador' }
{ marca_id, origem: 'form_viral', assunto_ids?: uuid[≤5], assunto_livre?: string ≤300 (≥1 of the two),
  tom?: 10..15, referencia?: perfil|formato, criatividade }
{ marca_id, origem: 'biblioteca', viral_id, assunto_ids?: uuid[≤5], assunto_livre?: string ≤300 }
```
The approved research values for the form come from the existing `GET /pesquisa/items?marca_id&status=approved&variable=`.
`GET /headlines/estruturas/contagem?marca_id&variaveis[]` returns `{compativeis: n, por_perfil: [{perfil_id, n}]}`.
It drives the CoreStudio alert "Exibindo somente perfis que possuem estruturas com as variáveis
selecionadas." and greys out profiles with 0.

### 4.5 Roteiros (`routers/roteiros.py`, BE-5)
| # | Method + path | Request | `data` |
|---|---|---|---|
| 32 | `POST /roteiros` | `{marca_id, headline_id?, headline_texto, instrucoes?, fonte:'ia', duracao, brain_id?, viral_id?, gerar_perguntas: bool (default true)}` | 202 `Roteiro` (`criando`). `fonte` web or link → 422 "Fonte ainda não disponível"; more than `ROTEIROS_DIA_USUARIO` (20) → 429; foreign brain or viral → 404 |
| 33 | `GET /roteiros` | `marca_id`, `q?`, `limit≤50`, `offset` | `{items: RoteiroResumo[], total}` |
| 34 | `GET /roteiros/{id}` | — | `Roteiro` |
| 35 | `PUT /roteiros/{id}/perguntas` | `{respostas: [{id, resposta ≤1000}]}` | `Roteiro`; only while `perguntas` (409 otherwise) |
| 36 | `POST /roteiros/{id}/gerar` | `{pular_perguntas?: bool}` | 202 `Roteiro` (`processando`) |
| 37 | `PUT /roteiros/{id}` | `{nome?, conteudo?, expected_versao}` | `Roteiro`; version mismatch → 409 |
| 38 | `POST /roteiros/{id}/feedback` | `{feedback, motivo?}` | `Roteiro` |
| 39 | `POST /roteiros/{id}/reprocessar` | `{instrucoes_adicionais? ≤2000}` | 202 a new roteiro with the same inputs plus the additional instructions |
| 40 | `POST /roteiros/excluir` | `{ids[1..100]}` | `{excluidos}` |

### 4.6 Chat (`routers/chat.py`, BE-6)
| # | Method + path | Request | `data` |
|---|---|---|---|
| 41 | `GET /chat/conversas` | `marca_id`, `agente`, `limit≤15`, `offset` | `{items: Conversa[], tem_mais}` |
| 42 | `POST /chat/conversas` | `{marca_id, agente, titulo?}` | 201 `Conversa` |
| 43 | `PATCH /chat/conversas/{id}` · `DELETE` | `{titulo 1..100}` | `Conversa` · 204 |
| 44 | `GET /chat/conversas/{id}/mensagens` | `antes?` (cursor), `limit≤100` | `{items: Mensagem[], tem_mais}` |
| 45 | `POST /chat/conversas/{id}/mensagens` | `{conteudo 1..8000, referencias: [{tipo, id}] ≤ 10}` | **`text/event-stream`**: frames `{"meta":{"mensagem_usuario_id","contexto_chars"}}` · `{"delta"}` · `{"truncated":true}` · `{"done":{"mensagem_id"}}` · `{"error":{"code","message"}}` (help_chat vocabulary + `meta`). Pre-stream refusals are plain HTTP: 409 `stream_em_andamento` (one stream per user), 429 caps, 503 `ia_nao_configurada` / `orcamento_ia_excedido` |
| 46 | `GET /chat/mencoes` | `marca_id`, `tipo ∈ {pesquisa, cerebro, biblioteca, headline}`, `q?`, `variavel?`, `page` | `Mencao[]` (`{tipo, id, rotulo, detalhe}`); `biblioteca` lists only the marca's allow-list (videos + virals of referenced profiles + one entry per profile "@perfil — Todos os vídeos") |
| 47 | `GET /chat/memorias` · `POST` · `DELETE /chat/memorias/{id}` | `marca_id` · `{marca_id, texto 1..500}` | `Memoria[]` · 201 (more than 50 → 409) · 204 |
| 48 | `GET /chat/contexto` | `conversa_id` | `{contexto_chars, limite: 60000}` (the composer meter) |

The title of a new conversation is the first 60 characters of the first message (no LLM call).

### 4.7 Dashboard (`routers/dashboard_criacao.py`, BE-1)
| 49 | `GET /dashboard` | `marca_id`, `historico_ordem ∈ {data_desc, data_asc, tipo}` | `DashboardCriacao` |

- **KPIs:** Headlines geradas (count of `cs_headlines` of the marca) · Roteiros gerados (`completo`) · **Itens de pesquisa pendentes** (replaces "Diagnóstico", §1.3; links to Minha Pesquisa).
- **Histórico:** derived, with no activity table. It is a UNION of the latest 30 events across `cs_headline_lotes` (created), `cs_roteiros` (completed), `cs_brains` (`synthesized_at`), `cs_marca_perfil` (`updated_at`) and `cs_research_items` (approved, grouped per day). Shape `{tipo, texto, ator, em}`.
- **Sugeridas:** the top 20 suggested headlines (as in #25).

### 4.8 TS types (FE-0 writes these verbatim to `src/types/geracao.ts`; BE schemas mirror them)
```ts
type LoteOrigem = 'form_me' | 'form_public' | 'form_viral' | 'biblioteca' | 'sugestao_auto'
type GeracaoStatus = 'criando' | 'processando' | 'completo' | 'falha'
type RoteiroStatus = 'criando' | 'perguntas' | 'processando' | 'completo' | 'falha'
type Criatividade = 'essencial' | 'equilibrado' | 'explorador'
type Gatilho = 'recompensa'|'misterio'|'reconhecimento'|'popularidade'|'crenca'|'autoridade'|'disrupcao'
type Taxon = { id: number; nome: string }
type Taxonomias = { nichos: Taxon[]; profissoes: Taxon[]; formatos: (Taxon & { definicao: string })[];
                    gatilhos: { slug: Gatilho; nome: string; formula: string }[]; tons: Taxon[] }
type PerfilCriacao = { marca_id: string; bio: string; nichos: number[]; profissoes: number[];
                       apresentacao_magnetica: string; ctas: string; updated_at: string | null }
type Treinamento = { id: string; ordem: number; titulo: string; descricao: string; video_url: string | null; ativo: boolean }
type PerfilStatus = 'aguardando'|'ativo'|'pausado'|'nao_encontrado'|'sem_conta'|'erro'
type PerfilMonitorado = { id: string; handle: string; nome: string | null; foto_url: string | null; seguidores: number | null;
                          status: PerfilStatus; erro_mensagem: string | null; ultima_sync_em: string | null;
                          metrica_base: 'views' | 'engajamento' | null; mediana_metrica: number | null;
                          virais: number; posts: number }
type TranscricaoViralStatus = 'nao_aplicavel'|'pendente'|'na_fila'|'concluida'|'falhou'|'grande_demais'|'longa_demais'|'sem_orcamento'
type ViralCard = { id: string; codigo: number; perfil: { id: string; handle: string }; thumbnail_url: string | null;
                   permalink: string; publicado_em: string; views: number | null; likes: number | null; comments: number | null;
                   duracao_s: number | null; score_viral: number | null; e_viral: boolean; trecho: string | null }
type ViralDetalhe = ViralCard & { caption: string | null; gancho: string | null; transcricao_texto: string | null;
                   transcricao_status: TranscricaoViralStatus; classificacao_status: 'pendente'|'processando'|'concluida'|'falhou';
                   nichos: Taxon[]; profissoes: Taxon[]; formatos: Taxon[]; gatilho: Gatilho | null;
                   estrutura_utilizavel: boolean; blueprint?: string | null }
type Referencia = { id: string; modo: 'perfil' | 'video'; perfil: PerfilMonitorado | null; viral: ViralCard | null;
                    auto_atualizar: boolean; posts_ate: string | null; updated_at: string }
type ItemUsado = { slot: string; item_id: string; conteudo: string }
type Headline = { id: string; marca_id: string; lote_id: string | null; texto: string; texto_original: string | null;
                  angulo: 1 | 2 | null; viral: ViralCard | null; template_metodo: number | null; itens_usados: ItemUsado[];
                  favorita: boolean; modo: 'manual' | 'automatico' | null; roteiro_id: string | null; created_at: string }
type HeadlineLote = { id: string; marca_id: string; origem: LoteOrigem; status: GeracaoStatus; etapa: string | null;
                      estruturas_total: number; estruturas_processadas: number; estruturas_com_erro: number;
                      aviso_poucas_estruturas: boolean; fallback_metodo: boolean; erro: string | null;
                      resumo: string; created_at: string; finished_at: string | null }
type HeadlineLoteDetalhe = HeadlineLote & { parametros: Record<string, unknown>; headlines: Headline[] }
type RoteiroPergunta = { id: string; pergunta: string; resposta: string | null }
type RoteiroResumo = { id: string; nome: string; headline_texto: string; headline_id: string | null;
                       status: RoteiroStatus; created_at: string }
type Roteiro = RoteiroResumo & { instrucoes: string; fonte: 'ia' | 'web' | 'link'; duracao: 'auto'|'1'|'2'|'3';
                 brain_id: string | null; viral: ViralCard | null; perguntas: RoteiroPergunta[]; etapa: string | null;
                 conteudo: string | null; fontes: string | null; versao: number; feedback: 'gostei'|'nao_gostei'|null;
                 feedback_motivo: string | null; erro: string | null }
type Agente = 'headline' | 'roteiro'
type Conversa = { id: string; marca_id: string; agente: Agente; titulo: string; last_message_at: string | null }
type MencaoTipo = 'pesquisa' | 'cerebro' | 'biblioteca' | 'headline'
type Mencao = { tipo: MencaoTipo; id: string; rotulo: string; detalhe: string | null }
type Mensagem = { id: string; role: 'user' | 'assistant'; conteudo: string; referencias: Mencao[];
                  status: 'completa' | 'parcial' | 'erro'; truncada: boolean; created_at: string }
type Memoria = { id: string; texto: string; created_at: string }
type EventoHistorico = { tipo: string; texto: string; ator: string | null; em: string }
type DashboardCriacao = { saudacao_nome: string; kpis: { headlines_geradas: number; roteiros_gerados: number; itens_pendentes: number };
                          historico: EventoHistorico[]; sugeridas: Headline[] }
```

---

## 5 · Headline generation (BE-4) — pipeline, slot filling, prompt

### 5.1 Pipeline (`headline.gerar`, payload `{lote_id}`)
1. **Select structures** (deterministic, no LLM). The candidates are virals with
   `classificacao_status='concluida' ∧ blueprint IS NOT NULL`.
   - **Pool, in order:**
     1. the virals the marca's Minha Biblioteca allows: profile references' virals newer than `posts_ate`, plus video references. CoreStudio did the same (`mechanisms.md` §7.3.1: the allow-list is the structure pool);
     2. if that pool is empty, org virals whose `nicho_ids ∩ marca.nichos ≠ ∅`;
     3. if that is empty too, all org virals.
   - **Filters:**
     - `referencia.perfil_ids` → only those profiles;
     - `formato_ids` → overlap;
     - `gatilhos` → equal.
   - **Variable compatibility (form_me / form_public):** a structure is compatible when `blueprint_slots ∩ variaveis ≠ ∅`. When `somente_pesquisa=true`, it must also have **every non-`GPT` slot fillable** from the approved items the user picked (§5.3).
   - **Ranking:** compatible structures first, then `score_viral DESC`. Take **5** (`HEADLINE_ESTRUTURAS_POR_LOTE`). Fewer than 3 compatible sets `aviso_poucas_estruturas`.
   - `form_viral`: no variable filter. `biblioteca`: exactly the chosen viral (its blueprint must exist, else 409 "Este viral ainda não tem estrutura — aguarde a classificação"). `sugestao_auto`: §3.5.
2. **No structure at all** (empty library, ingestion switched off): fall back to Método Audience.
   - `fallback_metodo=true`. The five structures become 5 of the 32 `METODO_TEMPLATES`, picked by `criatividade`:
     - essencial → 12, 14, 22, 25, 30
     - equilibrado → 5, 11, 13, 28, 31
     - explorador → 6, 7, 18, 19, 32
   - The UI shows "Sem estruturas da biblioteca — usando templates do Método Audience". This is honest about the source, not a silent substitute.
3. **One LLM call per structure.** The output is exactly `{"headline_1": {...}, "headline_2": {...}}` (§5.4), so one call yields two `cs_headlines` rows (`angulo` 1/2), as in CoreStudio.
   - Failure of one structure → `estruturas_com_erro += 1`; continue with the rest.
   - `etapa` is updated per structure.
4. Write the rows. Batch status follows §3.2.

### 5.2 User message (per structure)
```text
###NÚCLEO DE INFLUENCIA: <cs_marca_perfil.bio>

###ELEMENTOS DOS CÉREBROS:
<the "### Elementos para conteúdo" section of each non-empty Sistema brain of the marca, ≤ 4 000 chars total; omitted if none>

###MATERIAL DA PESQUISA (itens aprovados — use literalmente):
- [<item_id>] {{<SLUG>}} <content>          (one line per offered item, ≤ 40 items, only slugs present in the blueprint
                                             or selected in `variaveis`; picked values first, then by plays desc)

###ASSUNTO: <assunto | approved viral topics joined by "; " | omitted>
###TOM: <tom label, form_viral only>
###MODO: <somente_pesquisa ? "SOMENTE_PESQUISA" : "PESQUISA_PREFERENCIAL">
###CRIATIVIDADE: <essencial|equilibrado|explorador>

<blueprint document of the viral, DRAFT §1.2 variant A, without the CONFORMIDADE block>
   — or, in Método fallback —
###TEMPLATE MÉTODO AUDIENCE #<n>: <template line>
```

### 5.3 Slot filling — the rule, the verification, and a worked example
**Rule** (tech-lead default, §12 D2):
- `{{DB-SLUG}}` slots **are filled from the marca's approved Pesquisa items when present**.
- `somente_pesquisa=true` (CoreStudio "Criar as headlines usando apenas os itens da minha pesquisa"):
  - every non-`GPT` slot must use an offered item **literally**;
  - structures that cannot be fully filled are excluded before the LLM (§5.1);
  - a returned headline whose claimed items are not literally in its text is **discarded** and counted.
- `somente_pesquisa=false`:
  - items are preferred;
  - a slot with no item, or no fitting item, is generated by the model from the Núcleo (bio) and the brains' "Elementos para conteúdo".
- `{{GPT}}` is always filled freely by the model.

**Verification** (server, pure function `verificar_itens(texto, itens_declarados, oferecidos)`):
- Keep a declared `item_id` only if it was offered **and** its `content` occurs in `texto`. The comparison is case-insensitive and accent-insensitive.
- `itens_usados` stores only the kept ones. The UI shows them as "Itens da pesquisa usados".
- In SOMENTE_PESQUISA, a headline with any non-GPT slot not backed by a kept item is discarded.

**Worked example** (illustrative; the items are examples, not owner data):
- Marca **Gilson Tangerino**. Bio = the 4-paragraph Núcleo from DRAFT §7.1.
- Approved items:
  - `PESSOAS-PERSONAGENS-CONHECIDOS-PELO-AVATAR`: "seus pais" [i1], "o gerente do banco" [i2]
  - `DORES-TANGIVEIS-DO-AVATAR`: "aluguel que nunca acaba" [i3]
  - none for `MOMENTO-DE-VIDA-DO-AVATAR`
- Blueprint (abridged): `Como {{PESSOAS-PERSONAGENS-CONHECIDOS-PELO-AVATAR}} falava com você se tornou sua {{DORES-TANGIVEIS-DO-AVATAR}}. Na {{MOMENTO-DE-VIDA-DO-AVATAR}} você {{GPT}}…`

Offered block:
```text
###MATERIAL DA PESQUISA (itens aprovados — use literalmente):
- [i1] {{PESSOAS-PERSONAGENS-CONHECIDOS-PELO-AVATAR}} seus pais
- [i2] {{PESSOAS-PERSONAGENS-CONHECIDOS-PELO-AVATAR}} o gerente do banco
- [i3] {{DORES-TANGIVEIS-DO-AVATAR}} aluguel que nunca acaba
```
- **PESQUISA_PREFERENCIAL:** the structure is eligible. Expected output shape:
  ```json
  {"headline_1":{"texto":"Como seus pais falavam de dinheiro se tornou o aluguel que nunca acaba na sua vida. Na hora de sair da casa deles, você repetiu a mesma decisão sem perceber.","itens":["i1","i3"]},
   "headline_2":{"texto":"Como o gerente do banco falava com você virou o seu medo de financiar. Na primeira proposta, você travou — e o patrimônio ficou para depois.","itens":["i2"]}}
  ```
  - Server check: i1 ("seus pais") and i3 ("aluguel que nunca acaba") occur literally → kept. i2 occurs → kept.
  - `MOMENTO-DE-VIDA` became "Na hora de sair da casa deles" and "Na primeira proposta", which the model generated. That is allowed in this mode.
- **SOMENTE_PESQUISA:** the same structure is **excluded before the LLM**, because `MOMENTO-DE-VIDA-DO-AVATAR` has no approved item.
  - If no other structure qualifies, the batch ends `falha`: "Nenhuma estrutura pode ser preenchida só com os itens da sua pesquisa. Aprove itens em Minha Pesquisa (faltam: Momentos de vida do meu público) ou desmarque «usar apenas os itens da minha pesquisa»."
  - The missing variables are listed. The batch never silently returns zero headlines.

### 5.4 System prompt (`prompts/headline_geracao.py`, **DRAFT for owner validation**, `PROMPT_VERSAO='headline-v1-draft'`)
The prompt merges:
- **(a)** the behaviour the reverse engineering inferred (DRAFT §4):
  - keep the blueprint's syntax (frames, rhythm, contrasts) and refill the slots for the Núcleo's niche;
  - give the two headlines different angles;
  - adapt the length (shorten long hooks, never pad);
  - no emoji, no hashtags, no CTA in the headline;
- **(b)** Método Audience (`METODO_TRIGGERS`, `METODO_QUALITY` rules 1–5 and 7 *only* "no invented result numbers");
- **(c)** the slot rules of §5.3.

Additional rules:
- **Quality rule 7's anonymity/placeholder clause does not apply.** The Núcleo is the marca's own identity, so real names from the bio may appear. Recorded in §12.
- **Third-party content is data.** The blueprint and hook are third-party material, delimited, and never instructions to the model (§9.1).
- **Output** is strict JSON `{"headline_1":{"texto","itens":[ids]},"headline_2":{…}}`. The parser:
  - accepts the bare CoreStudio form `{"headline_1":"…"}` as `itens=[]`;
  - rejects a non-JSON reply → that structure is counted as an error.
- `criatividade` maps to temperature: essencial 0.4, equilibrado 0.7, explorador 1.0.

---

## 6 · Roteiro Avançado and Chat (BE-5, BE-6)

### 6.1 Roteiro pipeline
- `roteiro.perguntas` (when `gerar_perguntas`): one call (`prompts/roteiro_perguntas.py`, DRAFT) → 3–5 strategic questions as JSON → status `perguntas`. A failure goes straight to `processando` with no questions, and the UI is told: "Não foi possível gerar perguntas; o roteiro será criado sem elas."
- `roteiro.gerar` (`prompts/roteiro_geracao.py`, DRAFT, `roteiro-v1-draft`). The context is:
  - headline, instruções, answered questions, duration target;
  - `###BIO`, `<Apresentação Magnética>` and `<CTAs>` from Meu Perfil, in tags, as CoreStudio's popovers promise;
  - the chosen brain's content (≤ 20 000 chars, truncation marked);
  - when a viral is chosen, its transcript or caption as **"estrutura de referência — modele o recurso retórico, não o assunto"**. This was observed on 41429 (`roteiro-DRAFT.md` §3).
- **Beats** = CoreStudio's observed order aligned to Método Audience:
  Headline (capa) → CTA de salvar → identificação → virada → nome → prova (specificity, **never invented numbers**; an explicit rule, because 41428 fabricated statistics) → valor → CTA de compartilhar/comentar (from `<CTAs>` when filled) → Apresentação Magnética (from the profile when filled, otherwise omitted, never invented).
- **Duration** in words at about 150 words/min: auto ≈ 150–220, ~1 ≈ 150, ~2 ≈ 300, ~3 ≈ 450.
- Output is markdown with beat headings. `fontes` stays NULL in v1.

### 6.2 Chat agents
- Two agents. **HEADLINE** (`prompts/chat_headline.py`) and **ROTEIRO** (`prompts/chat_roteiro.py`), both DRAFT, Método Audience-aligned, with model `GERACAO_LLM_MODEL` and temperature 0.7.
- Streaming uses `chat_completion_stream` with `StreamOutcome`. Up to 2 continuation rounds (help_chat's `PEDIDO_CONTINUACAO` idea, not its code). Then `truncated`.
- The user message is persisted before the stream. The assistant message is persisted on `done` (`completa`), on client disconnect (`parcial`), or on error (`erro`, with the partial text kept).
- History sent to the model: the last 20 messages, capped at 40 000 chars, oldest dropped first.

### 6.3 Retrieval (the v1 "tools", `services/chat_contexto.py`)
Assembled server-side **per message**, in order, with a hard total of 60 000 chars (`contexto_chars` is
returned in `meta`; the FE warns at ≥ 50 000):
1. Meu Perfil: bio, nichos, profissões, apresentação, CTAs.
2. Memórias of (user, marca).
3. Explicit `@` references, resolved by id **with ownership checks**:
   - `pesquisa` → the item, or all approved items of a variable;
   - `cerebro` → the brain content (≤ 20 000);
   - `biblioteca` → the viral transcript and blueprint, or "@perfil — todos os vídeos" → the top 15 virals' hooks and blueprints;
   - `headline` → the headline text.
4. Automatic retrieval (stands in for CoreStudio's `consultar_variaveis_perfil` / `searchMyResearch` / `searchMyCerebro`):
   - **HEADLINE:** up to 12 structures from the marca's allow-list pool (§5.1 pool, ranked by `score_viral`, narrowed to a profile if one was `@`-mentioned), each as `estrutura #<codigo>: <blueprint>`; plus approved research items (≤ 150 items / 8 000 chars).
   - **ROTEIRO:** Núcleo + Método brains' "Elementos para conteúdo"; plus the cited viral's transcript.

The system prompt tells HEADLINE to cite `(estrutura #<codigo>)` for each headline. The FE turns a
citation into a link to the viral modal **only** if the code belongs to a viral returned in this
context (`meta` carries the allowed codes). Any other code is rendered as plain text.

---

## 7 · Frontend

All pages follow these rules:
- `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`, `placeholderData` on key changes, never `isLoading`.
- Error state with **Tentar novamente**. Empty states with CoreStudio's copy where it exists.
- Mutations invalidate `["sw","geracao", <area>, marcaId]`.
- Our design system plus seed organs (run `noc-organ-consume-check` at slice start: table, modal, confirm dialog, multi-select, VoiceAnswerInput).
- Components live under `src/components/geracao/<area>/`, pages under `src/pages/geracao/`, hooks under `src/hooks/geracao/`.

### 7.1 Dashboard (P1, `pages/geracao/Dashboard.tsx`)
- "Olá, {nome}!" and the switcher.
- KPI cards **Headlines geradas · Roteiros gerados · Itens pendentes** (the last links to `/media-creation/pesquisa?status=pending`).
- **Histórico**: "Linha do tempo do seu uso." with the select Data decrescente / Data crescente / Tipo.
- **Headlines Sugeridas** widget: "ver todas as headlines" → P9; 20 rows (truncated text + `title`, metric pill "3.1M views" or "12.4K engajamento"); **Ações** ▾ **Criar roteiro** (opens RoteiroAvancadoModal prefilled) · **Editar** (EditarHeadlineModal) · **Abrir link** (the viral's permalink).
- Empty: "Nenhuma headline sugerida ainda — elas aparecem aqui todos os dias quando sua Biblioteca tem virais."

### 7.2 Chat (P2, `pages/geracao/Chat.tsx`)
- **Agent tabs** HEADLINE / ROTEIRO.
- **Conversation rail:** "Conversas", `+`, rename inline (max 100, "Salvando..."), "Apagar conversa" (confirm), "Ver mais conversas", empty "Nenhuma conversa para este agente."
- **Links:** "Segundo cérebro" → `/media-creation/cerebro`; **Memória** modal with CoreStudio's copy ("O que a IA sabe sobre você em todos os chats de Roteiro e Headline…", textarea max 500, placeholder "Ex.: Meu público são donos de clínica de estética.", list + Apagar, "Nada salvo ainda.").
- **Messages:** markdown, sanitized, no raw HTML. On assistant messages: copy · **Favoritar** (per headline line, POST #29) · **Criar roteiro a partir desta headline** (RoteiroAvancadoModal) · "Criar roteiro com headline editável" (same modal, headline field focused). `(estrutura #N)` links open ViralModal.
- **Composer:**
  - `@` opens the mention picker with 4 tabs **Minha Pesquisa · Segundo Cérebro · Biblioteca · Headlines** (#46). Chips show the attached references.
  - Mic: the seed `VoiceAnswerInput` dictation. The transcript fills the composer and never auto-sends. Contexto `chat_ditado`, registered by BE-6.
  - Context meter "N caracteres de contexto" (warning ≥ 50 000).
  - Send, and Stop (aborts the fetch; the message is saved `parcial`).
  - Streaming uses the S0b `readSseStream`.
- **Deep links:** `?c=` selects the conversation. `?cite_viral=<viral_id>` pre-attaches that viral. `?cite_perfil=<perfil_id>` pre-attaches "@perfil — Todos os vídeos".
- **Documents upload ("Chat com Documentos") is phase 2.** It is not shown.

### 7.3 Biblioteca (P3, `pages/geracao/Biblioteca.tsx` + `components/geracao/biblioteca/ViralModal.tsx`)
- **Header:** "Biblioteca de virais" / "Biblioteca de virais disponíveis", the sort toggle **Mais vistos ↔ Mais recentes**, **Filtros**.
- **Auto-filter banner:** CoreStudio's copy, with "seus nichos e profissões" → "os nichos e profissões desta marca". Shown when `filtro_automatico`. Quick filters: Nichos, Profissões, **Meus nichos e profissões**, **Ver todos os virais**.
- **Grid "Virais Encontrados":** 24 per page. A card shows checkbox, `@handle`, 9:16 thumbnail, overlay metrics ("—" for null), duration, date, **Ver post**. Classic pagination.
- **Filter drawer** "Filtros de Virais": the CoreStudio fields minus Rede Social and Core, plus a **"Mostrar só virais"** switch (default on).
- **Selection bar:** "N vídeo(s) selecionado(s)" · Limpar seleção · **Adicionar à Minha Biblioteca** (#17 video).
- **Empty:**
  - no monitored profiles → "Sua biblioteca ainda está vazia — cadastre perfis em Minha Biblioteca › Solicitar Perfil.";
  - ingestion switch off → "A ingestão da biblioteca está desligada (aguardando revisão de segurança)."
- **ViralModal** "Informações do Viral":
  - header `@handle` + **Gerar headline** · **Citar no Chat** · **Citar perfil no Chat**;
  - left: Instagram **embed iframe** (`https://www.instagram.com/p/{shortcode}/embed/`, shortcode parsed with `/(p|reel|tv)/([A-Za-z0-9_-]+)/`, nothing else accepted) with the "Não consegue ver o vídeo?" fallback;
  - right: Métricas · Transcrição (status chip for non-`concluida`, **Copiar Transcrição**, copy internal link `/media-creation/biblioteca?viral=<id>`) · badges Nicho / Profissão / Formato do Vídeo / Gatilho.
- **Gerar headline wizard**, 3 steps (the workspace step is dropped):
  1. "Escolha os assuntos virais": the marca's approved topics, multi-select with counter, plus "Escreva o assunto viral manualmente (opcional)";
  2. "Revisar e Enviar": the summary;
  3. **Criar Headline** → #20 `origem:'biblioteca'` → "Headline enviada para criação!" / "Em 1 ou 2 minutos sua headline será criada…" with **Ver Headlines Sugeridas** / **Continuar na Biblioteca**.
  - The button is disabled with a tooltip when `estrutura_utilizavel=false`.
- `?viral=` opens the modal. `?perfil=` filters by profile with no auto-filter banner.

### 7.4 Meu Perfil (P4, `pages/geracao/MeuPerfil.tsx`)
- Header "Minha conta" / "Informações de criação desta marca".
- **Nichos** (multi, max 3, "Selecione até 3 nichos", tooltip "Preencha com os nichos que você deseja gerar Headlines").
- **Profissões** (same, max 3).
- **Bio**: the CoreStudio template popover verbatim; the same field as the Cérebro bio card.
- **Apresentação magnética** and **CTAs**: popovers "Esse campo será incluso nas gerações de Roteiros…".
- **Atualizar**. The incomplete-profile modal "Atenção" uses CoreStudio's copy, with the same bio XOR (nichos ∧ profissões) rule.
- **Instagram** card (read-only): shows the marca's IG connection(s) and whether a **Facebook-Login (Meta)** connection exists for monitoring. It links to Conexões › Marcas. It does not duplicate those pages: the in-page Instagram and Integrações tabs are **not** rebuilt, because `/meta` (IgOverview) and `/marcas` exist.

### 7.5 Minha Biblioteca (P5, `pages/geracao/MinhaBiblioteca.tsx`)
- "Minha Biblioteca" — "Gerencie seus perfis e vídeos de referência para usar no Chat."
- **Adicionar referência**, three tabs:
  - **Perfil completo**: a remote multi-select of the org's monitored profiles (`@handle`, "N virais"), excluding those already referenced; switch **Atualização automática**; Salvar.
  - **Vídeos específicos**: info text + "Ir para a Biblioteca de Virais".
  - **Solicitar Perfil**: "Perfil do Instagram (deve começar com @)", with CoreStudio's normalization and messages and a live check (#10, 500 ms debounce).
    - Status messages: "✓ Username válido" / "⚠️ Este perfil já está na biblioteca (monitorado)" / "⚠️ Este perfil já está na sua biblioteca." / "✗ Nenhuma conta Meta (Facebook Login) conectada — conecte em Conexões › Marcas para monitorar perfis."
    - A select **"Conta usada para monitorar"** (#15) appears when the org has more than one.
    - **Enviar** → #11.
    - The "Minhas solicitações" table becomes **Perfis monitorados**: Perfil · Status (Aguardando / Ativo / Pausado / Não encontrado / Sem conta / Erro + message) · Virais · Última atualização · actions **Atualizar agora**, Pausar/Retomar, Remover.
- **Minhas referências** table: search "Buscar por ID ou headline...", Tipo (Perfil/Vídeo + "Auto"), Perfil / Detalhe (link to `?perfil=`), Posts até, Atualizado, delete with the "Remover referência" confirm.

### 7.6 Treinamentos (P6, `pages/geracao/Treinamentos.tsx`)
- "Treinamentos" / "Primeiros passos: da Bio aos primeiros roteiros". Player on the left and "Aulas" on the right, 5 numbered lessons.
- Lesson without `video_url` → empty state "Vídeo em produção — em breve." (honest). With a URL → an iframe built only from an allow-listed embed host.
- Admin (`is_admin`): a pencil per lesson → modal Título / Descrição / URL do vídeo / Ativo → #5.

### 7.7 Headlines (P7–P9)
- **Gerar landing** (`HeadlinesGerar.tsx`): "Gerar headlines" — "Selecione o assunto que deseja gerar suas headlines". Three cards (verbatim copy) **Sobre mim** · **Sobre meu público** · **Assuntos do Virais** → `?who=me|public|viral`.
- **Form + history** (`Headlines.tsx`; an unknown or absent `who` behaves as `viral`, like CoreStudio). Header "Gerar headlines sobre Mim / Meu publico / Assuntos virais" + Voltar.
  - **me/public:**
    - **Selecionar Assuntos** (Todos + variables of the group). Each selected variable gets "Valor das variável" (approved items).
    - Selecione o Assunto (optional free text).
    - **Opções Avançadas** "Quero criar headlines com base em:" Modelagem de um Perfil (≤ 2; profiles with 0 compatible structures disabled "(Sem estruturas disponíveis)" + the alert) · Formato de Roteiro · Gatilho da Atenção.
    - Checkbox **"Criar as headlines usando apenas os itens da minha pesquisa."**
    - Slider **Criatividade objetiva** Essencial / Equilibrado / Explorador.
  - **viral:** "Assuntos Virais:" (approved topics, or "Nenhum assunto viral disponível no momento. Digite abaixo um assunto personalizado…"), "Sobre o que você deseja falar:", step 2 **Tom de Comunicação** (6 radios) → **Gerar Headlines**.
  - **Progress:** "Processando suas Headlines" with the real `etapa` and counters (no rotating fake messages, no fake bar). Poll 3 s.
  - **History** `#myHeadlines`: search, "Excluir Selecionados (N)", columns ☐ · Data · Tipo · Status (Criando/Processando/Completo/Falha) · 👁 (enabled on completo/falha) · 🗑.
  - **"Headlines Geradas"** modal: per headline text, ♥ favoritar, ✎ editar, "Criar roteiro", the structure link `#codigo` → ViralModal, "Itens da pesquisa usados" chips, warnings (`aviso_poucas_estruturas`, `fallback_metodo`, `estruturas_com_erro`), **Reprocessar**.
  - `?lote=` auto-opens it.
- **Favoritas** (`HeadlinesFavoritas.tsx`): table ☐ · Data · Headline (+ "Roteiro criado" badge → `/media-creation/roteiros?open=`) · actions Criar roteiro · Editar · Desfavoritar · Excluir; "Excluir Selecionados"; `?hid=` highlights and scrolls.
- **Sugeridas** (`HeadlinesSugeridas.tsx`): title "Headline sugeridas"; table ☐ · Data · Headline · Modo (Automático/Manual) · Métrica (source viral) · actions Criar roteiro · Editar · ♥ · Abrir link · Excluir; **Gerar sugestões agora**; filter Modo.

### 7.8 Roteiros (P10) and RoteiroAvancadoModal
- **List** (`Roteiros.tsx`): "Meus roteiros" — "Edite suas headlines favoritas ou crie roteiros a partir delas."; **Criar roteiro** (modal with an empty headline); search "Pesquisar..."; "Excluir Selecionados"; columns ☐ · Data · Nome · H. Origem (links to `?hid=` when it comes from a headline) · Status · 👁 · 🗑; `?open=` auto-opens.
- **Editar Roteiro** modal:
  - tabs **Roteiro** · **Fontes da Pesquisa** (hidden while `fontes` is NULL);
  - Nome, Roteiro (markdown editor, **Copiar Roteiro**);
  - "O que achou deste roteiro?" **Gostei / Não Gostei** → "Não gostou do roteiro?" reason + Enviar;
  - ⋯ **Reprocessar** ("Informação Adicional:");
  - footer Cancelar / **Atualizar** (409 → "O roteiro mudou; recarregue").
- **RoteiroAvancadoModal** (`components/geracao/roteiro/RoteiroAvancadoModal.tsx`): "Roteiro Avançado — Crie um roteiro avançado em 3 passos".
  - **Headline:** prefilled when the modal comes from a headline. Placeholder "Ex: 3 alimentos que aumentam testosterona".
  - **Instruções:** CoreStudio help and placeholder.
  - **Fonte das informações:** three cards. **Deixe a IA pensar** is selectable. **Link específico** and **Pesquisar na web** are shown disabled with the badge "Em breve".
  - **Duração do vídeo:** Auto (recomendado) / ~1 / ~2 / ~3 min.
  - **Segundo Cérebro (opcional):** the marca's brains with content.
  - **Vídeo da biblioteca (opcional):** "Abrir biblioteca e escolher vídeo" → picker (Buscar por texto · Formato · Perfil · Views mínimas 100k+/500k+/1M+/5M+ · Likes mínimas 10k+/50k+/100k+/500k+ · Nicho) over #7, scoped to the allow-list pool. The chosen card shows "remover".
  - Checkbox "Responder perguntas estratégicas antes (recomendado)" (default on).
  - **States:**
    - Criando ("…pode levar até 2 minutos", real `etapa`)
    - "Gerando perguntas estratégicas..." → questions form (Headline Base + "Responda as perguntas abaixo para personalizar seu roteiro", **Pular perguntas**, **Gerar Roteiro**)
    - Processando
    - **Criado**: "Roteiro criado com sucesso!", tabs Roteiro / Fontes, Copiar Roteiro, Atualizar Roteiro (→ #37), and the Gostei/Não gostei block
    - Falha + Tentar novamente
  - Closing the modal mid-run is safe: the run continues and appears in Roteiros.

---

## 8 · Tests (minimum)

**Backend** (`tests/modules/media_creation/test_geracao_*.py`; `FakeJobRepository`, `FakeStorageBackend`, fake LLM callables, fake BD adapter, fake transcription service)
- **Migration:** text == `geracao_taxonomias.seed_sql()`; counts 28/102/15; 5 lessons; 10 `status_pagina` keys; `reservar_transcricao` counters filter `origem='usuario'` (static SQL assertion and RPC test in the migration test harness).
- **All routes:**
  - strict `== 401` without a session, AST-checked (never `in (401, …)`);
  - cross-org 404 for every id-taking route (marca, headline, batch, roteiro, viral, profile, reference, conversation, memory, brain/viral referenced in a roteiro or `@` mention);
  - `DEFAULT_AI_RL` on every LLM route.
- **Perfil:** more than 3 nichos/profissões → 422; unknown id → 422; PATCH semantics; cerebro `/perfil` still round-trips bio.
- **Treinamentos:** non-admin PUT → 403; host outside allow-list → 422.
- **Biblioteca:**
  - handle normalization table, including reserved segments and URL forms;
  - `sem_conta` without a meta account;
  - viral math: median over 50, NULL metrics skipped, fewer than 10 → nothing viral, ratio threshold, 48 h age, views vs engagement choice;
  - classifier parser: unknown ids dropped, foreign slug → blueprint NULL, overlap check;
  - transcription states (`grande_demais`, `longa_demais`, `sem_orcamento`) still classify;
  - completion hook idempotent;
  - delete profile cascades storage, and 409 when referenced by another marca;
  - sync rate limit 429;
  - switch off → claim_gate false and the POST response says so.
- **`safe_fetch` (seed):** host allow-list, https only, private/loopback/link-local IPs refused (including DNS rebinding: the resolved IP is pinned), cross-host redirect refused, size cap aborts the stream, content-type/magic mismatch refused.
- **Transcription lane (BE-3):**
  - library rows never count toward the user/org/global voice counters, and vice versa;
  - library caps (60/30/3 min, depth 5);
  - `claim_gate` false while a `transcricao` job is pending or running;
  - busy 503 → `RescheduleLater` without a retry spent;
  - voice path unchanged (the existing transcricoes tests stay green).
- **Headlines:**
  - structure selection (pool order, filters, compatibility, `somente_pesquisa` exclusion, fewer than 3 → warning, no structure → Método fallback with `fallback_metodo`);
  - one call → 2 rows;
  - `verificar_itens` (literal, accent/case-insensitive, unoffered id dropped);
  - SOMENTE_PESQUISA discard;
  - partial failure → `completo` with errors; all fail → `falha`;
  - empty bio 422; second active batch 409; daily cap 429;
  - auto suggestions dedupe per day, skip without bio or niches;
  - "gerar agora" once per day;
  - favoritar/editar keeps `texto_original`;
  - the §5.3 worked example as a golden test of user-message assembly.
- **Roteiros:**
  - `fonte` web/link 422;
  - questions → answers → gerar; pular;
  - questions failure → generates without them;
  - version conflict 409;
  - feedback;
  - reprocess creates a new row;
  - prompt includes the apresentação/CTAs tags only when filled.
- **Chat:**
  - SSE frames order (`meta` → `delta`… → `done`);
  - continuation on truncation, then `truncated`;
  - disconnect → `parcial` saved;
  - one stream per user 409;
  - context cap 60 000 with priority order;
  - foreign `@` reference 404 before streaming;
  - the citation allow-list in `meta`;
  - memory 500/50 limits;
  - private conversations (another user of the same org → 404).
- **Dashboard:** KPIs and history union ordering (3 orders).
- **Workers (BE-0):** the 3 existing workers start and stop through the hooks exactly as before (existing tests stay green); a hook that raises is logged and never aborts startup.

**Frontend** (vitest, mocked API; one test file per page)
- loading two-signal on marca switch;
- every empty and error state;
- Dashboard actions open the modals;
- chat stream rendering, stop, and `@` picker attaching chips;
- citation links only for allowed codes;
- dictation fills the composer without sending;
- Biblioteca filters → query params, auto-filter banner, selection bar, ViralModal deep link, wizard 3 steps, embed URL builder rejects non-Instagram;
- Minha Biblioteca handle validation messages and live-check states;
- Meu Perfil max-3 and incomplete-profile modal;
- Treinamentos empty video state and admin edit;
- Headlines form per `who`, compatible-profile disabling, progress uses real `etapa`, history actions, result modal chips/warnings;
- Favoritas/Sugeridas tables and actions;
- RoteiroAvancadoModal disabled sources, questions flow, picker, result tabs, feedback.

---

## 9 · Security and LGPD (**flag: `security` agent reviews BE-2 + BE-3 + S0a before integrate**)

### 9.1 Prompt injection and output handling
Captions, transcripts and blueprints of third-party profiles are **untrusted text**. They are placed
inside delimited data blocks, and every prompt states that the block's content is material, never
instructions. Model output is never executed and never used as a URL, SQL or file path. The chat
renders sanitized markdown (no raw HTML). Citation links resolve only to the allowed viral codes of
that context.

### 9.2 Ingestion (Business Discovery + media download)
- **Official API only:** `business_discovery` through the org's own `provider='meta'` token. No scraping, no unofficial endpoints, no logged-in session reuse.
- Tokens never leave the backend and are never logged. The BD call is rate-limited per account (Meta's BUC limits): back off on codes 4/17/32/613 via `RescheduleLater`.
- **`safe_fetch`** (S0a, `noctusai_lib.integrations.media.safe_fetch`):
  - `https` only;
  - host allow-list passed by the caller. Library: `*.cdninstagram.com`, `*.fbcdn.net`. Suffix match on a dot boundary;
  - DNS is resolved once, and every resolved address must be public (no private, loopback, link-local, multicast or reserved; IPv6 included); the connection is pinned to that IP with SNI and Host preserved;
  - redirects are followed only to allow-listed hosts (≤ 3);
  - streaming byte cap: thumbnails 2 MB, videos 15 MB (the transcription cap);
  - connect/read timeouts 10/30 s;
  - the caller declares the expected magic bytes (jpeg/png/webp; mp4 `ftyp`).
- Downloaded video bytes go straight into `submit_sistema` (validated again there). They are never stored outside the `sw-transcricoes` lifecycle, so audio is deleted right after transcription.
- **Kill switch** `biblioteca_ingestao_habilitada` (platform_settings, then env, default **OFF**). It ships OFF and is turned on by the tech-lead **after** the security review passes, as part of the "validate all at once" run.
  - If the review blocks, the rest of the module still works: headlines fall back to Método Audience templates (§5.1).
- **Meta platform terms:** storing third-party public media metadata and transcripts must be reviewed against the Meta Platform Terms (data use limited to the app's stated purpose; delete on request).
  - Also check whether `instagram_basic` Advanced Access (App Review) covers Business Discovery for the owner's app, since monitored handles are not app users.
  - Both go on the security checklist and are verified live in S0a. If BD is not granted, the page shows `sem_conta` with the Meta error, never empty success.

### 9.3 LGPD
Monitored profiles are third parties. Their public posts, and their **voices** in Reels, are personal data.
- **Purpose:** analysing the structure of viral content for this org's own content creation.
- **Minimization:** only the public fields listed in §2.3; no follower lists, no comments' authors.
- **Retention:**
  - audio is deleted immediately (shared layer);
  - transcripts and metadata are kept while the profile is monitored;
  - **deleting a profile deletes its virals, thumbnails and transcripts** (#14);
  - a paused profile keeps its data; a profile with no references for 90 days is purged by the scheduler (`NOC-REMEDIATE[biblioteca-retention]` until the owner confirms 90).
- **Tech-lead action:** file `noctus.dev.lgpd_flag` for the library (legal basis: legitimate interest over public content, to be confirmed by the owner) when BE-2 integrates.
- **Chat:** conversations and memories are user-private (RLS + service checks). They are kept until the user deletes them (`NOC-REMEDIATE[chat-retention]`).

### 9.4 Spend and abuse caps (`app/config.py`, written by BE-0, finite defaults)
| Key | Default |
|---|---|
| `geracao_llm_model` / `biblioteca_llm_model` | `claude-opus-5` / `claude-haiku-4-5` |
| `headline_lotes_dia_usuario` · `headline_estruturas_por_lote` | 30 · 5 |
| `headlines_sugeridas_por_dia_marca` | 5 (10 headlines) |
| `roteiros_dia_usuario` | 20 |
| `chat_mensagens_dia_usuario` · `chat_mensagens_dia_org` · `chat_contexto_max_chars` | 100 · 400 · 60 000 |
| `biblioteca_max_perfis_org` · `biblioteca_classificacoes_dia_org` · `biblioteca_viral_ratio` | 30 · 300 · 3.0 |
| `biblioteca_transcricao_min_dia_global` · `_org` · `_max_s_por_reel` · `_max_fila` | 60 · 30 · 180 · 5 |
| `geracao_worker_enabled` | true |

The seed org LLM budget (`enforce_budget`) applies on top. A budget refusal reaches the user as 503
`orcamento_ia_excedido`.

---

## 10 · Slice plan (file-disjoint; each slice in its own `task_branch` off `origin/dev`)

**Migration plan:** **one shared migration (229) authored first by BE-0** in wave 0. No other slice
writes SQL. A schema gap found later becomes a BE-0 follow-up commit before wave 1 integrates, or a
new migration number scaffolded by the tech-lead. `APPLIED.md` gets one entry, written by BE-0. 229
requires 217, 221, 224 and 225 applied, and is applied to prod with owner consent through
`migrate_product` before the image deploy.

### Wave 0 (integrate before wave 1)
- **S0a (engineer-seed, backend):**
  - `noctusai_lib/domain/jobs/lifecycle.py` (`WorkerHandle`: start/stop/is_running over a `Worker`, stop timeout, cancel on timeout) + tests;
  - `integrations/meta`: `get_business_discovery(ig_user_id, username, *, fields, after=None) -> BusinessDiscoveryPage` on the Facebook-Login adapter Protocol + Fake + Real (`_meta_api` error mapping) + tests, including a recorded live shape check (views served or not);
  - `integrations/media/safe_fetch.py` + tests.
  - Do not edit unrelated `__init__` exports beyond adding the new names. The template sync is done by the pre-commit hook.
- **S0b (engineer-seed, frontend):** `seed/lib/frontend/src/realtime/readSseStream.ts` (+ export) and HelpChatBubble migrated onto it (its tests stay green).
- **BE-0 (backend):**
  - `migrations/229_cs_geracao.sql` + migration test + `APPLIED.md` entry;
  - `app/modules/media_creation/geracao_taxonomias.py`;
  - `app/main.py` (`ModuleRegistration.startup/shutdown`) + `app/lifespan.py` iterating them, with the 3 existing workers moved onto `WorkerHandle` + hooks (edits `edicao_fotos/services/worker.py`, `media_creation/services/pesquisa_extracao_worker.py`, `transcricoes/worker.py` start/stop only, `transcricoes/__init__.py`, `media_creation/__init__.py` registration);
  - `app/dependencies.py` (`require_platform_admin` moved; transcricoes router import updated);
  - `app/config.py` (all §9.4 keys);
  - `media_creation/services/geracao_jobs.py` (handler registry + the `geracao` and `biblioteca` WorkerHandles registered as startup hooks; `claim_gate` for the library switch);
  - `media_creation/geracao_scheduler.py` (stale sweeps).
- **FE-0 (frontend):**
  - `src/types/geracao.ts` (§4.8 verbatim, first commit);
  - `src/components/geracao/{StatusBadge.tsx, labels.ts, MetricaPill.tsx}`;
  - `src/components/geracao/headlines/EditarHeadlineModal.tsx` + `src/hooks/geracao/useHeadlineMutations.ts` (edit / favoritar / excluir; used by P1, P2, P7–P9).

### Wave 1 (parallel)
- **BE-1:** `schemas/perfil_criacao.py`, `services/perfil_service.py`, `routers/perfil_criacao.py`, `routers/treinamentos.py` (+ service), `routers/dashboard_criacao.py` (+ service), the two-handler delegation in `routers/cerebro.py`, tests.
- **BE-2:** `schemas/biblioteca.py`, `services/biblioteca_service.py`, `services/biblioteca_ingestao.py` (sync, metrics, thumbnails, transcrever, classificar handlers), `services/biblioteca_transcricao.py` (contexto hook), `prompts/biblioteca_classificador.py`, `biblioteca_scheduler.py`, `routers/biblioteca.py`, tests. It calls `TranscricaoService.submit_sistema` per the §3.4 signature, faked in tests.
- **BE-3:** `app/modules/transcricoes/**` only: `submit_sistema`, the library worker + `claim_gate`, `reservar_transcricao_biblioteca` call, tests. **noctusai-fe reviews §3.4 and this diff before integrate.**
- **BE-4:** `schemas/headlines.py`, `services/headline_service.py`, `services/headline_pipeline.py` (selection, assembly, `verificar_itens`, handler), `prompts/headline_geracao.py`, `headline_scheduler.py`, `routers/headlines.py`, tests.
- **BE-5:** `schemas/roteiros.py`, `services/roteiro_service.py` (+ handlers), `prompts/roteiro_perguntas.py`, `prompts/roteiro_geracao.py`, `routers/roteiros.py`, tests.
- **BE-6:** `schemas/chat.py`, `services/chat_service.py`, `services/chat_contexto.py`, `services/chat_transcricao.py` (`chat_ditado` hook), `prompts/chat_headline.py`, `prompts/chat_roteiro.py`, `routers/chat.py`, tests.
- **FE-1:** `pages/geracao/{MeuPerfil,Treinamentos}.tsx`, `hooks/geracao/{usePerfilCriacao,useTreinamentos,useTaxonomias}.ts`, tests.
- **FE-2:** `pages/geracao/{Biblioteca,MinhaBiblioteca}.tsx`, `components/geracao/biblioteca/**` (ViralModal + wizard, ViralCard, filters, VideoPicker exported for FE-3), `hooks/geracao/useBiblioteca.ts`, tests.
- **FE-3:** `pages/geracao/Roteiros.tsx`, `components/geracao/roteiro/**` (RoteiroAvancadoModal, EditarRoteiroModal), `hooks/geracao/useRoteiros.ts`, tests. It imports FE-2's VideoPicker. If FE-2 is not merged yet, it builds against the FE-0 types and imports at integrate; the tech-lead integrates FE-2 before FE-3.

### Wave 2 (parallel; FE-3 and FE-2 integrated)
- **FE-4:** `pages/geracao/{HeadlinesGerar,Headlines,HeadlinesFavoritas,HeadlinesSugeridas}.tsx`, `components/geracao/headlines/**` (except FE-0's modal), `hooks/geracao/useHeadlines.ts`, tests.
- **FE-5:** `pages/geracao/Chat.tsx`, `components/geracao/chat/**`, `hooks/geracao/useChat.ts`, tests.
- **FE-6:** `pages/geracao/Dashboard.tsx`, `hooks/geracao/useDashboardCriacao.ts`, tests.

### Wave 3 (tech-lead, inline)
- **FE-Z:** `App.tsx`. The 11 routes (P7 has two) and both nav configs (§1.1), in one commit.
- Re-run `gate_sweep` on the **merged tip**, then `predeploy_check social-wiring`. The `schema_drift` leg fails until 229 is applied.
- Security review (BE-2/BE-3/S0a) result recorded. Then decide on `biblioteca_ingestao_habilitada`.

### Collision classes
| Class | File(s) | Rule |
|---|---|---|
| C1 | `frontend/src/App.tsx` | FE-Z only |
| C2 | `media_creation/__init__.py` (router list + module imports) | BE-0 sets up the hooks; BE-1/2/4/5/6 each **append** their router and import lines (additive; the integrator resolves conflicts) |
| C3 | `app/config.py`, `app/main.py`, `app/lifespan.py` | BE-0 only |
| C4 | `migrations/229_*.sql`, `migrations/APPLIED.md` | BE-0 only |
| C5 | `app/modules/transcricoes/**` | BE-0 (start/stop move only) in wave 0, then BE-3 only |
| C6 | `seed/lib/**`, `templates/product-seed/**` | S0a / S0b only |
| C7 | `routers/cerebro.py` | BE-1, two handlers only |
| C8 | `projects/core-studio/*.md` (TEST-CHECKLIST, DECISIONS) | tech-lead only |
| C9 | `components/pesquisa/MarcaSwitcher.tsx`, `hooks/useMarcaPesquisa.ts` | read-only reuse; nobody edits them |

---

## 11 · Deliberate differences from CoreStudio

- Per marca, not per user/workspace. No agency layer.
- The library is **the org's own monitored profiles via the official API**, not a staff-curated scraped corpus of about 40k virals.
- "Viral" is defined per profile: views or engagement over that profile's median.
- Minha Biblioteca's "Solicitar Perfil" **registers** a monitored profile right away, instead of asking staff.
- Every read by id is ownership-scoped (CoreStudio's IDOR, `mechanisms.md` §15).
- Real job status. No rotating fake progress capped at 90 %.
- Research items **are** used in headline generation, with literal verification. CoreStudio's suggested-headline job ignored them.
- One Roteiro path (Avançado) with optional strategic questions. Web and link sources come later.
- The chat "tools" are server-side retrievers (§0.3). No documents upload in v1.
- No credits. Explicit caps instead.
- The Dashboard "Diagnóstico" is replaced by a pending-items KPI.
- No mutating GETs.

---

## 12 · Tech-lead defaults — validate with owner

| # | Default | Where |
|---|---|---|
| D1 | **Headline system prompt** = merge of the reverse-engineered payload (DRAFT §4) + Método Audience; the anonymity/placeholder clause of quality rule 7 dropped for headlines. **DRAFT** | §5.4 |
| D2 | **`{{DB-SLUG}}` slots filled from approved Pesquisa items**; "usar apenas os itens da minha pesquisa" = structures that can't be fully filled are excluded, and claims are verified literally; unchecked = items preferred, gaps generated from Núcleo + brains; `{{GPT}}` always free. Worked example included | §5.3 |
| D3 | **Viral library source = monitored Instagram profiles**, registered per marca via Minha Biblioteca › Solicitar Perfil; corpus shared by the org; ingestion by **Business Discovery through a `provider='meta'` (Facebook-Login) account** (the Instagram-Login connection cannot do it); no scraping | §0.6, §3.3 |
| D4 | **Viral metric** = views when served on ≥ 80 % of the window, else likes + comments; viral = ≥ 3× the profile's median over its last 50 posts, post ≥ 48 h old, ≥ 10 posts of history | §3.3 |
| D5 | **Library Reels transcription** = lower-priority lane with its own budget (60 min/day platform, 30 min/day org, ≤ 3 min/reel); claims only when no voice job is pending; reviewed by noctusai-fe; `NOC-REMEDIATE[transcription-fairness]` | §3.4 |
| D6 | **Media download** only from Instagram CDN hosts via seed `safe_fetch` (SSRF-safe, 2 MB / 15 MB caps); ingestion behind `biblioteca_ingestao_habilitada`, OFF until the security review passes | §9.2 |
| D7 | **Library classification by LLM** (Haiku 4.5): niche/profession/format/trigger/hook/blueprint stored on the viral row. **DRAFT prompt** | §3.3.6 |
| D8 | **Chat**: two agents on `claude-opus-5`, SSE streaming (seed), "tools" as server-side retrievers (research, brains, library, headlines), **Memória per user and per marca** (≤ 500 chars, ≤ 50 items: the owner runs several personas from one login), conversations per user and marca, dictation via the shared transcription layer, documents upload phase 2 | §6.2–6.3 |
| D9 | **Roteiro Avançado**: only "Deixe a IA pensar" in v1; "Pesquisar na web" phase 2 (`NOC-REMEDIATE[roteiro-web-search]`, no provider in seed/core); "Link específico" phase 2 pending the URL-source security review; strategic questions on by default; beats = CoreStudio order aligned to Método Audience, no invented numbers. **DRAFT prompts** | §6.1 |
| D10 | **Headlines sugeridas automáticas**: daily per marca with bio + niche, 5 structures (10 headlines), top virals of the allow-list then niche-matching, 30-day no-repeat; "Gerar sugestões agora" button (1/day) for testing; Manual = the Biblioteca wizard | §3.5 |
| D11 | **Async** via the existing jobs queue, statuses Criando / Processando / Completo / Falha, real `etapa`, 3 s polling; worker lifecycle formalized (fourth worker forbidden otherwise) | §3 |
| D12 | **Caps** as in §9.4 (30 batches, 20 roteiros, 100 chat messages per user per day; 400 chat messages per org per day) | §9.4 |
| D13 | **Treinamentos**: DB-backed, platform-admin editable, the 5 CoreStudio lessons seeded without video ("Vídeo em produção") | §2.7, §7.6 |
| D14 | **Meu Perfil per marca**: Nichos ≤ 3, Profissões ≤ 3, Bio (same field as the Cérebro bio card), Apresentação magnética, CTAs; personal-data fields and the Instagram/Integrações tabs not rebuilt (existing `/meta`, `/marcas`) | §2.1, §7.4 |
| D15 | **Fallback**: no library structure → Método Audience templates, labelled | §5.1.2 |
| D16 | **Dashboard**: "Diagnóstico" dropped and replaced by "Itens pendentes"; history derived from existing tables | §4.7 |
| D17 | **All new pages `desenvolvimento`**; one sidebar link per page with CoreStudio labels under Criação de mídia (4 levels) | §1.1 |
| D18 | **Dropped**: workspaces/agency layer, Headlines na Box, credits/twin billing, the dead UI list | §1.3 |
| D19 | **Library retention**: profile delete purges its data; an unreferenced profile is purged after 90 days | §9.3 |

## 13 · Open questions (owner) and phase 2

1. D1–D19 above, validated while testing (`TEST-CHECKLIST.md` "Geração").
2. **Legal basis** for storing third-party public content and transcripts (LGPD flag filed with BE-2).
3. **Which Meta (Facebook-Login) account** runs Business Discovery per org, and whether the app's `instagram_basic` access covers it (verified live in S0a).
4. **Treinamentos videos**: record our own, or ask CoreStudio for permission to reuse theirs (Bunny GUIDs are in `biblioteca-roteiros-analysis.md` §4)?
5. **Phase 2:**
   - web search (seed seam or LLM tool use) and link sources for roteiros;
   - chat documents upload;
   - seed LLM tool calling (`NOC-REMEDIATE[llm-tool-use]`);
   - monitored profiles as an Extrair Pesquisa source (`FONTES`);
   - TikTok/YouTube library networks;
   - a platform-level transcription priority queue (`NOC-REMEDIATE[transcription-fairness]`);
   - notifications on batch completion.
