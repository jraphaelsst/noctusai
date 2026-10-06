# CoreStudio — Mechanisms behind the pages

How CoreStudio works behind each screen, reconstructed 2026-10-06 from the fresh crawl (`captures/crawl-2026-10-06/`), the earlier captures (`captures/js/*`, `captures/raw/*`) and the earlier specs. Page-level detail is in `specs/page-map-v2.md`; read-only follow-up fetches are in `specs/xhr-to-fetch.md`.

**Tags:** **C** = CONFIRMED (seen in code, HTML or captured JSON) · **I** = INFERRED (reasoned, not seen working) · **U** = UNKNOWN. A claim without a tag inherits the tag of its section heading line.

The goal here is the *intelligence*, not the shell: what each mechanism stores, how state moves, what triggers it, where an LLM is called and with which inputs, and what we still cannot see.

---

## 0 · Platform architecture

| Layer | What | Tag |
| --- | --- | --- |
| App | Laravel monolith on the MagicAI SaaS base; Blade views on the Tabler 1.0 template; jQuery + Alpine; **Livewire 3 only for the chat** (`document-chat` component) | C |
| Jobs | Every generation except chat is a queued job polled by the browser (5–20 s), with fake progress bars | C |
| Realtime | Pusher + Laravel Echo on every page. Private channels seen: `questions-validation.{APP_ENV}.user.{USER_ID}` (brain answer validation, event `.validation-completed`) and `chat.{env}.user.{id}` (legacy floating chat, event `.nova-mensagem`). Chat answers stream over **SSE** (`POST chat/stream`), not websockets | C |
| Storage | S3 bucket `corestudio-ai` (`storage/app/public/eng_reversa/…` viral thumbnails, `instagram/thumbs/…`, `instagram/avatars/…`); Bunny Stream (libraries 478875 trainings, 399061 cérebro tutorial) | C |
| Second database | The questionnaire script waits for the brain to be "synced" and comments `// Tudo pronto — só após sync do Postgres`. The app DB is therefore not the only store: the synthesized brain is copied into a **Postgres** store before it counts as ready | C (comment) |
| …its role | That Postgres is the retrieval store (embeddings) the chat agents query | I |
| LLMs | `ai_provider: 'claude'` default for Roteiro Avançado; GPT-4o-mini for search-query translation (code comment); an "assistant" for answer validation (`HAS_ASSISTANT` flag) — naming suggests an OpenAI Assistant | C / C / I |
| External APIs | Serper (web search), PubMed, Instagram Platform API (Business Login), Instagram embed, YouTube audio download | C |
| Tenancy | Customer (`customer_id`) → Workspace (`workspace_id` 1619 "My Workspace") → User (1667). Workspace creation posts to `/dashboard/admin/customers/workspace/create` even from the user area. An agency layer exists (`/dashboard/make-headlines/*`, `/dashboard/box-headlines/*`, "customers", Box → customer/week) | C |
| Plans | Biblioteca is marked "Exclusivo para o Plano Premium"; Blade has empty sidebar sections **Avatar** and **Estudio de Edicao** (plan-gated or retired); Twin credits/recharges for avatar videos | C / I |

### 0.1 Two ID spaces for brains (C)

| Core id (definition) | Brain id (user instance) | Name | Kind |
| --- | --- | --- | --- |
| 8 | 8772 | História de Criação | Sistema |
| 9 | 8773 | Histórias de Vida do Especialista | Sistema |
| 14 | 8774 | Método do Especialista | Sistema |
| 3081 | 8775 | Núcleo de Influência | Sistema |
| 3741 | 8522 | Call de diagnóstico | Personalizado |
| 4191 | 9385 | Formulário | Personalizado |
| 4192 | 9386 | Narrativa | Personalizado |

Evidence: the YouTube box carries `data-core="3081" data-brain="8775"`; the Roteiro Avançado select and "Núcleo Especifico" use the left column; the Favoritas "Criar Roteiro" `core[]` select uses the right column with the same names. The mapping by name is **C**; that *every* surface uses one space consistently is **I**. Custom brains also get a core row (3741/4191/4192), so "core" is the definition (name, type, question set) and "brain" is the user's instance (content, status, sync). **I** for the exact table split.

---

## 1 · Research variables (Pesquisa)

### 1.1 Three vocabularies — do not merge them by name

| Vocabulary | Members | Where | Tag |
| --- | --- | --- | --- |
| **DB variables** (`ID|SLUG`) | 29 with slugs: 17 avatar (`who=public`, "Meu Público") + 12 especialista (`who=me`, "Sobre mim"); plus 4 type-`null` globals (22 Verbos Poderosos, 23 Adjetivos Poderosos, 24 Momento do dia, 29 GPT) that have no slug in any capture and are never read | headline form options (`value="18|DESEJOS-TANGIVEIS-DO-AVATAR"`), `variables/type/{who}`, `profile-viral-search` `variable_name` | C |
| **Classifier slugs** | 13 `{{SLUG}}`s in the Inserir itens prompt (5 equal a DB slug, 1 spelling variant, 7 with no DB variable) | `searches/add-item-prompt` | C |
| **Pseudo-variable `ASSUNTOS_VIRAIS`** | viral *topics* ("empreendedorismo"), a separate entity with its own approve/reject | Biblioteca wizard payload, `who=viral` form | C |

Full lists: `specs/variables-usage.md`, `specs/variables-live-findings.md`. The 2026-10-05 decision (40 distinct concepts, no overlaps) stands.

### 1.2 Data model

| Entity (inferred name) | Fields seen | Tag |
| --- | --- | --- |
| `variables` | `id`, `slug`, label, `type ∈ {avatar, especialista, null}`, `has_structures` (0/1 per variable; Sobre mim 27 = 0 → "(Sem estruturas disponíveis)") | C |
| `user_variable_pending` (extracted items) | `id, user_id, workspace_id, variable_id, eng_reversa_result_id, content, status (0 pending, 1 approved), plays (string), created_at, updated_at, deleted_at (soft delete)` | C (live JSON 2026-10-05) |
| `user_variable_contents` (manual/AI-classified items) | `id, content, source='content'`, no plays / no video | C shape / I table |
| `viral_topics` | `id, topic (≤255), total_plays, eng_reversa_result_id (null ⇒ "Manual")`, status pending/approved | C |
| `add_item_prompt` config | `prompt_system, is_active, include_variables` (per user or global **U**) | C |

The API merges both stores into `{approved_manual, approved, pending}` per variable; ids are unique per store, so remove/approve calls carry `source ∈ {content, pending}`. **C**

### 1.3 State machine (C statuses, I transitions)

```
(platform extraction job | profile-viral-search/save | auto-suggestion)
        └─► PENDING (status 0, has plays + eng_reversa_result_id)
               ├─ approve (user) ─► APPROVED (status 1, keeps source=pending)
               └─ reject  (user) ─► soft-deleted (deleted_at)
(Inserir itens: prompt off | AI-classified lines) ─► APPROVED_MANUAL (source=content)
APPROVED / APPROVED_MANUAL ─ delete ─► soft-deleted
empty-all ─► everything deleted, pending included
```

### 1.4 Triggers — where items come from

1. **Extrair Pesquisa** (user): pick phrases from a profile's precomputed extraction → `profile-viral-search/save`. **C**
2. **Inserir itens** (user): pasted lines → LLM classifier (`add-items-sync`, 90 s, fallback queued job polled 2 s) or direct insert under one variable. **C**
3. **Per-profile extraction job** (user, hidden modals): `POST searches/extract-profile {type: myPublic|topic_virais, eng_reversa_search_id}` → job with `step`, `progress`, `saved_count`, `skipped_items` ("já existentes" dedup) → pending items or pending topics. **C**
4. **Automatic suggestion** (system): Meu Perfil warns "O sistema precisa da bio preenchida juntamente com os nichos e profissões para poder **sugerir itens da pesquisa** para você." So bio + niches + professions drive server-side suggestion of pending items. **C** that it exists; **I** that it works by matching approved profiles on niche/profession and copying their extracted phrases as pending (the pending items carry `eng_reversa_result_id` + `plays` of real virals, and the training lesson 2 is "Como aprovar itens da Pesquisa (automático e manual)"). Schedule (on profile save vs cron) **U**.

### 1.5 How items feed generation

| Consumer | Mechanism | Tag |
| --- | --- | --- |
| Gerar Headlines (`who=public|me`) | Selecting variables (`variables_id[]` as `ID|SLUG`) calls `get-variables-values` → one multi-select per variable listing the user's **approved** items (`variable_values[]` = `varId|content`). Checkbox `complete_with_research` "Criar as headlines usando apenas os itens da minha pesquisa." restricts the batch to those items | C |
| Structure matching | `has_structures` per variable + "Exibindo somente perfis que possuem estruturas com as variáveis selecionadas." + per-profile `is_structure` + result warning "poucas estruturas compatíveis" ⇒ a **structure** (headline template from a viral) is indexed by the variables it contains | C (signals) / I (index) |
| Chat | `@` → "Minha Pesquisa" tab (`searchMyResearch(q, group, page, sort, variable)`), attached as references; agent tool labels `consultar_variaveis_perfil`, `find_variables`/`validate_variables` | C |
| Biblioteca wizard | only `ASSUNTOS_VIRAIS` (approved viral topics) | C |
| Roteiros | no research variable is read by any roteiro form | C |

**Open:** how a structure stores its variable slots (`{{SLUG}}` placeholders? a tag list?) — no structure text has been captured. **U**

---

## 2 · Viral topics (Assuntos Virais)

- **Model:** `viral_topics` (§1.2). Pending topics come from `extract-profile {type:'topic_virais'}` on a profile; each keeps the summed views of its source virals (`viral-data/{topicId}` returns `{plays, likes, comments, post_date, url, thumbnail}` per video). **C**
- **States:** pending → approve (`GET viral/topics/approve/{id}`) → approved; reject → removed; manual add → approved with no source ("Manual"). **C**
- **Consumers:** the `who=viral` headline form ("Assuntos Virais:" select; empty for the owner because 0 approved, `hasViralTopics=false`), and the Biblioteca "Gerar headline" wizard (`library/viral-topics {workspace_id}` → approved topics). **C**
- **Owner state:** 10 pending (321.2K–2.5M views), 0 approved. **C**

---

## 3 · Brains (Segundo Cérebro)

### 3.1 Data model

| Entity | Fields | Tag |
| --- | --- | --- |
| core (definition) | `id`, `name`, `core_type ∈ {custom (Personalizado), beliefs (Crença), sistema}`; Sistema cores own a question set | C (types/ids) / I (sistema as a type value) |
| core_question | `id` (1583–1597 for 3081; 1609–1617 for 8), text with markdown bold + italic hint, `group` (0–4, 3 per group) | C |
| brain (user instance) | `id` (8772…), `core_id`, `content` (markdown, e.g. 3,844 chars), status `Vazio/Pronto`, `brain_status ∈ {syncing, synced, error}`, lock while a job runs ("Cérebro liberado") | C / I (lock) |
| brain_answer | `question_id`, `response`, validation `status ∈ {completed, failed}`, `rejection_reason`; draft vs final | C |
| youtube_job | `job_id`, `status (…, done, error)`, `phase ∈ {downloading, transcribing_audio}`, `videos_found`, `videos_done`, `error` | C |

### 3.2 Questionnaire → validation → synthesis (C unless noted)

```
VAZIO ──answer (groups of 3 unlock progressively)──► draft (save-draft)
      ──Finalizar (all answered ∧ HAS_ASSISTANT)──► POST questions/store → {status:'validating'}
             chips "Validando..."
             ├─ Echo private questions-validation.{env}.user.{id} .validation-completed
             └─ poll GET cores/brain-status/{coreId} every 3 s
                   → {validation_status: pending|completed|failed,
                      brain_status: syncing|synced|error,
                      responses:[{question_id, status: completed|failed, rejection_reason}]}
       failed ──► chips Rejeitada + "Motivo: …" → user edits → Finalizar again
       completed ──► brain_status syncing ("Sincronizando seu cérebro...")
                   ──► synced (after the Postgres sync) ──► /cores?brain_synced=1, badge PRONTO
       error ──► "Ocorreu um erro ao gerar o cérebro."
```

- **AI calls:** (1) one validation pass judging each answer, returning approve/reject + a reason; (2) a synthesis pass turning approved answers into the brain markdown. Prompts are server-side. **I** for two separate calls (validation result arrives before `syncing`).
- **Synthesis shape (C for 3081):** the 15 Núcleo de Influência answers became four sections: *Perfil Profissional* (nome, profissão, experiência, missão, especialidades) · *Público-Alvo e Desafios* (quem ajuda, dor, inimigo, tentativas frustradas, crença errada) · *Solução e Transformação* (segredo/abordagem, transformação, método, argumentos de defesa) · *Histórias de Sucesso*. The questions map one-to-one onto those headings. The "Narrativa" brain shows the roteiro beat names (`### MOVIMENTO IDENTIFICADO`, `### BIO`, `### APRESENTAÇÃO MAGNÉTICA`) (2026-10-05). **C**
- **Other inputs to a brain:** file upload (PDF/DOCX/TXT/MD/CSV ≤ 20 MB, appended below), YouTube links (`cores/youtube/extract {core_id, brain_id, links[]}` → job: download audio → transcribe → append; polled every 6 s; one link may expand to several videos, `videos_found` **I**), direct markdown edits (Aplicar Alterações). Voice answers per question (`upload-audio-chunk`, `cores/update`) exist in `brains.js` but no mic UI renders → dormant. **C**

### 3.3 How brains are used

| Consumer | Field | ID space | Tag |
| --- | --- | --- | --- |
| Roteiro Avançado | `core_id` "Segundo Cérebro (opcional)" | core | C |
| Favoritas/Sugeridas "Criar Roteiro" | `core[]` "Adicionar Cérebro como fonte de informação:" + `core[]` "Adicionar Crenças:" (beliefs brains; none exist) | brain | C |
| Legacy headline modal | `specific_core_id` "Núcleo Especifico:" | core | C |
| Chat (ROTEIRO agent only) | `@` "Meu Cérebro" (`searchMyCerebro`), tool label `nucleo_influencia` | ? | C |
| Legacy roteiro progress | "2. Extraindo Núcleo — Agora estamos extraindo o seu núcleo de influência..." between "1. Pesquisando" and "3. Método" | — | C (labels) |

**I:** the Núcleo de Influência brain is a default input of roteiro generation even when no brain is picked (step 2 names it explicitly). **U:** whether brains are injected whole into the prompt or retrieved by chunks from the Postgres store; context-size rules.

---

## 4 · "Extrair" — three different mechanisms with similar names

| Name in UI | Route | Input | What is extracted | Output | Tag |
| --- | --- | --- | --- | --- | --- |
| **Extrair Pesquisa** | `/searches/extract-profile` | an approved viral profile | nothing at click time: shows the **precomputed** phrase-per-variable extraction of that profile's virals (`headline` = the video's opening sentence; `value` = the phrase; per variable slug) | ticked phrases → user research items | C |
| **Extrair Assuntos Virais** / per-profile research job | modals on `/searches` | `{type: myPublic|topic_virais, eng_reversa_search_id}` | runs (or re-runs) extraction for one profile into the user's pending items / pending topics, deduplicating existing ones | pending items or topics + counts | C |
| **Minhas extrações** (Nova Extração) | `/cores/extract` (hidden) | name + target brains (`nucleos[]`) + a YouTube/Dropbox URL or a pasted transcript | transcription (`cores/transcrible`), then an LLM "Pesquisa Gerada" | a text applied to brains, or to variables via "Selecione o Tipo de Variável" | C (form) / I (apply semantics) |

The platform-side pipeline that feeds the first two (**I** except where marked): curated profile (`eng_reversa_search`, status pending/approved, tagged with niches/professions **C**) → scrape posts → thumbnails to S3 **C** → transcribe (`transcription_text` **C**) → extract the hook headline **C** → classify formats (15-format multi-label rubric **C**) → extract research phrases per variable **C** (result shape) → extract headline **structures** (`is_structure` flag per profile **C**) → (optional) viral topics **C**. "eng_reversa" = *engenharia reversa*. The "Minhas extrações" table shows `recordsTotal 192` to a user with 0 rows, i.e. the total counts every user's rows (**I**, a leak not to copy).

---

## 5 · Headline generation

### 5.1 Entry points (all produce `headline` batches or rows)

| Path | Inputs | Endpoint | Lands in | Tag |
| --- | --- | --- | --- | --- |
| Form `who=public|me` | `variables_id[]` (`ID|SLUG` or `all`), `variable_values[]`, `assuntos[]`, `reference-type-me-public ∈ {profile, format, attention}` → `profile_ids_me_public[]` (≤2) / `format_video_ids_me_public[]` / `attention_trigger_ids_me_public[]`, `complete_with_research`, `thermometer ∈ {0,50,100}`, `disable_creativity` | `POST headlines/store` | history `headlines/list`; results modal | C |
| Form `who=viral` | approved topic or `custom_subject`, `reference-type ∈ {profile, format}`, then a second step "Tom de Comunicação" (`structures_category_items[]` 10–15) | `POST headlines/store-custom-subject` (`add_input=2`) → `type:'subject_action'` subject-picker step | same | C |
| Hidden busca inteligente | `who=search`, `intelligent_search=1` — "buscar headlines virais para seu nicho e profissão" | `headlines/store` | **U** | C (form) |
| Legacy modal (Dashboard/Favoritas/Sugeridas) | `who`, `variables_id[]`, `specific_core_id`, `structures_category_items[]` (9 Estrutura; 2–7 Gatilho), `thermometer`, `profile_ids[]` XOR `format_video_ids[]` | same endpoints | same | C |
| Biblioteca "Gerar headline" | viral + workspace + approved viral topics (`ASSUNTOS_VIRAIS`) + optional manual text | `POST headlines/suggested/store` | Headlines sugeridas, "1 ou 2 minutos" | C |
| Daily suggestions | none (system) | `POST headlines/generate-sugeridas-day` fires on every page load that includes `headlines.js` (server-side idempotent per day **I**) | Headlines sugeridas, Mode `Automático` | C |
| Chat HEADLINE agent | free text + references | SSE | chat messages (not stored as headline rows **I**) | C |

### 5.2 State machine (C)

```
created / created_subjected ("Criando")
   → in_subjected / in_gpt ("Processando")   [subject step only for who=viral]
   → in_gpt2 ("Processando")                  [second pass]
   → completed ("Completo") | error ("Falha")
```
Client polls `GET headlines/status/{id}` every **20 s**, then reloads with `?headline={id}` to auto-open the result. **C**

### 5.3 The two-pass pipeline (C labels, I semantics)

`#viewHeadlineFlowModal` shows four stored blobs per suggested headline: **Payload Primeira Criação**, **Callback Primeira Criação**, **Payload Revisão**, **Callback Revisão** (`payload_headline_old_1`, `callback_headline_old_1`, `payload_headline`, `headline` from `GET headlines/suggested/view/{id}`). So each batch is: build prompt payload → LLM create → build revision payload (containing the first answer) → LLM revise → store. The payloads are the actual prompt requests — **the cheapest way to read CoreStudio's real headline prompts** without spending a credit (see `xhr-to-fetch.md`).

### 5.4 What a headline carries

`{{ ID: <structure_id> }} <headline>` is the edit format; favorites store `structure_id`, `headline`, `headline_id` (batch), `roadmap`, `eng_reversa_result_id`; suggested rows add `Mode`, `Result` (source viral views), `Likes`, `Comments`. **C**. The **structure id is a viral id** (`/library?viral_id=…`). **C**

### 5.5 Generation controls — vocabularies (keep separate)

| Control | Values | Field | Tag |
| --- | --- | --- | --- |
| Gatilho da Atenção (current) | 1 Recompensa · 2 Reconhecimento · 3 Popularidade · 4 Autoridade · 5 Mistério · 6 Crença · 7 Disrupção | `attention_trigger_ids[]` | C |
| Gatilho da Atenção (legacy) | 2 Recompensa · 3 Mistério · 4 Popularidade / Autoridade · 5 Reconhecimento · 6 Crença · 7 Disrupção | `structures_category_items[]` | C |
| Estrutura de Roteiro | 9 Lista com Argumentação Poderosa | `structures_category_items[]` | C |
| Tom de Comunicação | 10 Chocante e Disruptiva · 11 Futuro e Possibilidades · 12 Curiosidade e Mistério · 13 Cultura e Sociedade · 14 Crítica e Denúncia · 15 Reflexão e Profundidade | `structures_category_items[]` | C |
| Formato do Vídeo | 15 formats (rubric in `platform-study.md`) | `format_video_ids[]` | C |
| Criatividade objetiva | 0 Essencial · 50 Equilibrado · 100 Explorador | `thermometer` | C |

How each value changes the prompt: **U** (visible only in the payloads).

### 5.6 Favorites, Box, suggested

- Heart = `POST headlines/like {structure_id, headline, headline_id}` / `unlike`. **C**
- **Headlines na Box** = a cart (offcanvas on every page) saved to a *customer + week* (`box-headlines/customer/{id}/save`, `headline_week_id`) — an agency planning feature. **C** code; whether this plan can reach the save step **U**.
- Suggested headlines on the Dashboard are ordered by source-viral views and link to the source Instagram post. **C**

---

## 6 · Roteiros (roadmaps)

### 6.1 Five creation paths — not the same mechanism

| Path | Inputs | Endpoint / poll | Pipeline signals | Tag |
| --- | --- | --- | --- | --- |
| A. Legacy "Criar Roteiro" (Favoritas/Sugeridas) | `headline`, `structure_id`, `headline_id`, `referer`, brains `core[]` (+ Crenças), dynamic questions (`get-questions` / `get-question-roadmap {agent_id}`) | `POST roadmaps/store` → `roadmap_ids[]` (several = "Opção 1/2/…") → `POST roadmaps/check-progress` every 5 s | progress **1. Pesquisando → 2. Extraindo Núcleo → 3. Método** | C |
| B. "Criar Roteiro" new (Favoritas) | `headline_id`, `observations` ("Qual ideia você quer defender nesse roteiro?") | `POST roadmaps/favorites/store` → `POST roadmaps/favorites/show-favorites {id}` ≤ 60 polls, until `roadmap_engreversa` ≠ "Roteiro não disponível" | — | C |
| C. Dashboard suggested "Criar roteiro" | `headline_id`, `observations` | `POST roadmaps/reversa/store` → **synchronous** `roadmap_engreversa.text` (now disabled in the widget; link goes to Sugeridas) | — | C |
| D. **Roteiro Avançado** (all pages) | headline (id or text), Instruções, source `none|links (≤4)|serper (+PubMed, pt/en)`, `duration_minutes`, `core_id`, `viral_video_id`, `ai_provider=claude`, `save_to ∈ {user_roadmaps, eng_reversa_headlines}`, `is_reprocess` | `list-search` (LLM plans N queries, each run on Serper) → user picks ≤2 links per category → `store (mode:'steps')` → `show/{id}` every 5 s ≤ 120 | "passa por 2 etapas de análise"; result `roadmap_advanced` + `search_text` (Fontes) | C |
| E. Chat ROTEIRO agent | free text, references, brains, memory | SSE | retrieve → structure → write → review, reviewers with retries | C |

`save_to` tells which table the roteiro attaches to: a user roteiro row (`user_roadmaps`) or the suggested headline itself (`eng_reversa_headlines`). The favorites/suggested route prefixes (`headlines/{favorites|suggested}/advanced-roadmap/*`) point to the same modal config; whether they hit different controllers **U**.

### 6.2 State + feedback (C)

Roteiro statuses: `created` Criando → `in_gpt` Processando → `completed` Completo | `error` Falha. Feedback: `setFeedback {roadmap_id, feedback}` (Gostei 1 / Não Gostei) + `set/reason {reason_unliked}`. Edit with Quill (`roadmap_gpt`), reprocess via the advanced modal (`is_reprocess=1`). "Modo chat": `POST chat/start {resource_id, resource_type}` opens a chat seeded with that roteiro.

### 6.3 Inputs not used

No roteiro form reads research variables. Apresentação magnética and CTAs (Meu Perfil) are injected "Dentro da Tag Apresentação Magnética / CTAs" in roteiro generation (popover text, **C**). Captured roteiro `params` (41428): `headline_text, ai_provider, mode, save_to, observations, roadmap_source_type, roadmap_use_pubmed, is_reprocess, duration_minutes`; `payload` empty for that row. **C**

---

## 7 · Biblioteca de virais

### 7.1 Data model

| Entity | Fields | Tag |
| --- | --- | --- |
| `eng_reversa_search` (viral profile) | `id` (e.g. 1735), `profile` (handle), `social`, status pending/approved/rejected, niches, professions, `is_structure`, ≤3 thumbnails | C |
| `eng_reversa_result` (viral) | `id`, `eng_reversa_search_id`, `profile`, `social`, `thumbnail` (S3), `post_link_public`, `plays`, `likes`, `comments`, `post_date`, duration (card), `transcription_text`, hook `headline`, `is_core` (staff gold standard), approved flag ("Nenhum viral aprovado…") | C |
| relations | `relations[{niche, profession}]` (M:N), `engReversaFormatVideoRelation[{format_video}]` (M:N, via a classification run) | C |
| `format_video` | 15 rows `{id, name, definition, signals, alias, status}` | C |
| `niche` (28) · `profession` (102) | `{id, name}` | C |
| library reference (Minha Biblioteca) | `{id (3602…), mode profile|video, eng_reversa_search_id | video_id, auto_refresh, posts_until, updated_at}` | C / I (`posts_until` meaning) |
| profile request | `{profile, social, status pending|approved|rejected, notes}` | C |

### 7.2 Listing logic (C)

Server-side filters; auto niche/profession filter from Meu Perfil unless `view_all=1` or `profile=` is given; sort `plays` (default) or `recent`; 24/page; only approved virals. Corpus sizes: 514 handles in the profile filter; 485 approved profiles for research (`approved-profiles`); 281 pages ≈ 6.7k virals in the owner's 3 niches + 3 professions; the 6 allow-listed profiles hold 23–156 virals each (431 total).

### 7.3 How the library feeds generation

1. **Structures for headlines.** Every chat headline cites `(estrutura #ID)` = a viral id. In the 29 saved conversations, **47 of 52 distinct structure IDs (182 of 190 citations) are videos of 3 of the account's 6 Minha Biblioteca profiles** (psifernandosegredo 133 citations, veridiana_cavalheri 25, elias.maman 24); the 5 others (124684, 124700, 147089, 147091, 148727) are not in any captured profile page. **C** (correlation). So **the HEADLINE agent's structure pool is the Minha Biblioteca allow-list**, not a house default. **I** (mechanism). `@perfil` narrows but does not hard-filter: a "10 baseadas no @elias.maman" answer used 8 elias.maman + 2 psifernandosegredo structures. **C**
2. **Structures cross niches.** Videos of `psifernandosegredo` (a psychology-themed profile by its handle and transcripts' topics, **I**) supplied structures for the real-estate account's headlines ("A reforma não destrói o erro…" on structure 124688, 2026-10-05 study). The structure is syntactic, not topical. **C** (citation) / **I** (profile's niche)
3. **Profile-level structure flag.** `headlines/profiles` returns `{id, profile, is_structure}`; profiles with `is_structure=0` cannot be picked as "Perfil de Referência". **C**
4. **Research phrases** (Extrair Pesquisa) and **viral topics** come from the same virals (§1, §2). **C**
5. **Roteiro structure reference:** `viral_video_id` in Roteiro Avançado; the picker reads `library/videos` (`id, title, description, thumbnail_url, plays, likes, comments, format_name, transcription_text`). **C**
6. **Daily suggested headlines** come from top virals in the user's niches (views shown are the source viral's). **C** views / **I** selection rule.
7. **Chat references:** `cite_viral` (one viral) and `cite_profile` (all videos of a profile) deep links. **C**

### 7.4 Open

How a viral's skeleton is stored (text with slots vs on-the-fly LLM abstraction) **U**; how `has_structures` per variable is computed **U**; what `is_core` changes in retrieval **U**; why 5 cited IDs are absent from the allow-listed profile pages (unapproved virals? another profile?) **U**.

---

## 8 · Instagram integration (Minha conta › Instagram / Integrações)

### 8.1 Connection model (C, inline `meta_account` on `/profile/integrations`; token redacted)

`{id, user_id, meta_account_id, account_type:'instagram', account_name, account_username, biography, website, profile_picture (S3 copy), access_token, expires_in (≈ 60 days ahead), token_type:'bearer', granted_scopes:[instagram_business_basic, instagram_business_content_publish, instagram_business_manage_insights], status:'active', media_count, followers_count, follows_count, request_count, start_metrics (JSON snapshot of the account at connection time), fetch_new_posts_time, fetch_metrics_posts_time, fetch_metrics_profile_time, last_synced_at}`.

- **Login type:** Instagram API with **Instagram Login** (business scopes), long-lived token (~60 days). **C**
- **Publish scope granted** (`content_publish`) but no publishing UI exists anywhere. **C** / purpose **U**.
- **Sync model:** three separate timestamps (new posts, post metrics, profile metrics), all written just after 00:00 → a **nightly cron** with three jobs. **I** (timestamps **C**). `start_metrics` = baseline captured at connect ("As métricas começam a ser monitoradas a partir da integração"). **C**
- **Removal:** `GET profile/integrations/delete` (older `profile/remove?user_id&meta_account_id` commented out). **C**

### 8.2 What is shown (C)

- **KPIs** (`profileInsights`): `followers_count, new_followers, views, accounts_engaged{,_day,_week,_month}, reach{,_day,_week,_month}, comments, likes, media_count, updatedAt`. Tiles: Seguidores, Novos Seguidores, Visualizações, Engajamento (= accounts engaged), Comentários.
- **Charts:** Engajamento (%) and Alcance (K) for `30 dias / 7 dias / Hoje` (three points, not a time series). In the snapshot the three periods are identical, so either only one sync has run or the periods are not computed separately. **I**
- **Posts** (`instagramPosts`, 9 per page, 168 stored of 1,592 on the account): `post_id` (local, sequential), `media_id` (null), `media_url` (Instagram CDN, expiring), `thumbnail_url` (S3 copy), `media_type`, `caption`, `permalink`, `timestamp`, `engagement`, `reach`, `impressions` (always 0 — a metric Instagram retired), `saved`, `likes`, `comments`, `shares`, `views`. Only a recent window of posts is imported. **C** counts / **I** window rule.
- **Dormant:** `?period=` select and a "select up to 60 posts" modal (`posts/all` returns posts with `selected`; `posts/set` stores the choice). Purpose **U** — plausibly choosing the user's own posts as AI references or for the dashboard "Diagnóstico" card (both **I**).

### 8.3 Use in generation

No surface reads Instagram data into headline/roteiro generation in the captured code. **C** (absence) / **U** server-side.

---

## 9 · Integrações

One provider (Instagram) with one connected account card. Connect button `#start-integration` navigates to a server-provided URL (null when connected). No TikTok/YouTube integration, although the library and the profile form model TikTok handles. **C**

---

## 10 · Treinamentos

Static: 1 module, 5 Bunny Stream lessons; the first-access modal pushes users here and records `first-access-seen`. No progress tracking endpoint seen. **C**

---

## 11 · Chat (stream, documents, memory)

- **Component state** (Livewire `document-chat`, C): `messages[{id (UUIDv7), role, content, isRoteiro}]`, `messagesLimit 100`, `hasMoreMessages`, `conversations[{id, title, updated_at}]` (15 per page), `selectedAgentId`, **`activeRunId`** (a run entity per generation), `attachedReferences[{id, source, …}]`, `contextCharCount` (warning above 600k), `streamUrl`, `traceMessageId`.
- **Agents:** `headline = 1`, `roteiro = 2`, `headline_express = 3` (hidden). **C**
- **Streaming:** `POST chat/stream` SSE with `token, progress, rag_step, tool_start/end, refining_*, review_start/end/retry/warn, completed, error`. Reviewer agents can reject and force a rewrite (`max_attempts`). **C** (`frontend-js-analysis.md` §2.2).
- **Documents:** `POST chat/documents` (PDF/DOCX/TXT/MD/CSV ≤ 20 MB) → `{id, title, meta, status pending|processing|ready}`; listed under "Referências anexadas"; retrievable by `@`. **C**
- **Memory:** ≤ 500-char facts applied to every HEADLINE and ROTEIRO chat; tools `salvar_memoria_tool` / `esquecer_memoria_tool`. **C**
- **Legacy:** floating aiChat via `/api/return/integration/ai/chat` + Pusher `.nova-mensagem`; the Dashboard "MamanAI" box (`mamanai/proccess`) is dead code. **C**
- **Use pattern seen (C):** this one account runs content for two people (Gilson, real estate; Mônica, psychoanalysis) by switching context inside chats — the persona-per-account limit noted on 2026-10-05.

---

## 12 · Consolidated inferred data model

| Table (inferred) | Key fields | Relations |
| --- | --- | --- |
| customers / workspaces / users | ids, names; user `niches[] (≤3)`, `professions[] (≤3)`, `bio`, `presentation_magnetic`, `ctas`, handles, `layoutVersion` | customer 1–N workspace; user ↔ workspace |
| variables / user_variable_pending / user_variable_contents / viral_topics / add_item_prompts | §1.2, §2 | user+workspace scoped |
| cores / core_questions / brains / brain_answers / brain_jobs | §3.1 | core 1–N brain (per user) |
| core_extractions (Minhas extrações) | `id, name, status (pending_gpt…), content, document_url[], document_text`, target cores | user |
| eng_reversa_searches / eng_reversa_results / niches / professions / format_videos / pivots | §7.1 | profile 1–N viral; M:N taxonomies |
| library_references / library_requests | §7.1 | user ↔ profile/video |
| headlines (batches) / headline items | inputs, `status`, two-pass payloads, `structure_count` | batch 1–N items |
| eng_reversa_headlines (suggested) | `headline, mode, eng_reversa_result_id, structure, roadmap, search_text`, two-pass payloads | viral 1–N suggested |
| favorite_headlines | `headline, headline_id, structure_id, roadmap, eng_reversa_result_id` | — |
| user_roadmaps | `name, headline, observations, brain_id/core_id, viral_id, params{…}, roadmap_gpt, roadmap_advanced, search_id, search_text, status, roadmap_liked, reason_unliked` | from favorite/suggested/headline |
| chat_conversations / chat_messages / chat_runs / rag_documents / user_memories / chat_agents | §11 | — |
| meta_accounts / instagram_posts / instagram_insights | §8 | user 1–N account |
| box_headlines / headline_weeks | agency cart | customer |
| notifications / activity_log / twin credits & packages | — | user |

All **I** as table names; field names are **C** where listed in the sections above.

---

## 13 · Alignment with our Método Audience (flags only)

Source: `products/social-wiring/backend/app/modules/media_creation/prompts/methodology.py`.

| Point | CoreStudio | Método Audience | Status |
| --- | --- | --- | --- |
| Attention triggers | current form: 7 — Recompensa, Reconhecimento, Popularidade, Autoridade, Mistério, Crença, Disrupção | 7 — Recompensa, Mistério, Reconhecimento, Popularidade, Crença, Autoridade, Disrupção | **Same 7 names** (C). Their definitions on the CoreStudio side are not visible, so equality of meaning is **U**. The legacy 6-item list (Popularidade/Autoridade merged) is a different vocabulary. |
| Headline templates | structures = real viral skeletons, cited by viral id | 32 written templates | Different kinds of object (C); both are "template" — do not merge by name. |
| Post skeleton | roteiro beats (Headline, História Magnética, CTA de Salvar, Valor Prático, Apresentação Magnética, CTA de Comentar…) | capa · identificação · virada · nome · prova · valor · cta | Overlapping intent (I); vocabularies differ. |
| Invented numbers | CoreStudio output fabricated stats (2026-10-05) | quality rule 7: no invented result numbers | our rule is stricter (C). |
| CTA | CTA de Salvar / Compartilhar / Comentar / Seguir | salvar + marcar/enviar | compatible (I). |

Decision on how to merge stays with the owner (DECISIONS.md: "aligned with our in-home Método Audience").

---

## 14 · Open questions (for the owner, or for the next read-only fetch)

1. **Headline prompts:** can we read `GET headlines/suggested/view/{id}` for 2–3 of the 20 dashboard suggestions (ids 201755–201775)? It returns the stored *payloads* of both passes — likely the real prompts — without spending credits. (`xhr-to-fetch.md` #1)
2. **Structure storage:** is a structure a stored template with variable slots, or does the agent abstract the skeleton on the fly from the transcript? Only `library/result/{id}` + headline payloads can tell.
3. **Auto-suggested research items:** when do they run (on profile save, nightly) and from which profiles?
4. **Brains in roteiros:** is Núcleo de Influência always used ("2. Extraindo Núcleo") even when no brain is picked?
5. **Instagram data:** what is the dormant "select up to 60 posts" for, and does any generation read the user's own posts or metrics? What is the Dashboard "Diagnóstico — a preencher" card?
6. **Plan gating:** what do the hidden **Avatar** and **Estudio de Edicao** sections contain, and which features are Premium-only besides Biblioteca?
7. **Rebuild scope (carried from DECISIONS.md):** keep the legacy paths (Box, Minhas extrações, legacy headline modal, legacy roteiro A/C) or only the current ones (form page, Roteiro Avançado, chat)?
8. **Allow-list as structure pool:** do we reproduce "Minha Biblioteca = the agent's structure pool" deliberately (it explains why the account's headlines reuse ~50 structures)?
