# CoreStudio — Mechanisms behind the pages

How CoreStudio works behind each screen, reconstructed 2026-10-06 from the fresh crawl (`captures/crawl-2026-10-06/`), the earlier captures (`captures/js/*`, `captures/raw/*`) and the earlier specs. Page-level detail is in `specs/page-map-v2.md`; read-only follow-up fetches are in `specs/xhr-to-fetch.md`.

**Tags:** **C** = CONFIRMED (seen in code, HTML or captured JSON) · **I** = INFERRED (reasoned, not seen working) · **U** = UNKNOWN. A claim without a tag inherits the tag of its section heading line.

The goal here is the *intelligence*, not the shell: what each mechanism stores, how state moves, what triggers it, where an LLM is called and with which inputs, and what we still cannot see.

**Update 2026-10-06 (read-only XHRs, `captures/xhr-2026-10-06/`).** Sections 1, 3, 4, 5, 7, 8 and 14 now say what those responses **confirm** or **refute**. Look for the "2026-10-06 XHR" notes. Main changes:
- The real headline payload is now known: Núcleo line + a per-viral **blueprint** with `{{DB-SLUG}}` slots. See §5.7 and `prompts/headline-engenharia-reversa-DRAFT.md`.
- Suggested headlines have **no second pass**.
- The headline "NÚCLEO DE INFLUENCIA" is the profile **bio text**, not the Núcleo de Influência brain.
- Research items are literal extractor phrases of virals.
- Instagram import keeps **videos only**.
- A cross-tenant read exists in CoreStudio (§15).

Extracted prompts are **drafts**, not validated (owner instruction 2026-10-06).

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

**2026-10-06 XHR — how research items relate to virals (C unless noted).**
- An item is a **copy of one extractor pair** of one viral. `searches/variables/items?type=avatar` returns 263 owner items: 108 approved, 155 pending, 0 manual. 257 of them point at 227 distinct virals; 6 have a null `eng_reversa_result_id`.
- Where the source viral's extraction was fetched (`profile-viral-search`), the item's `content` equals the extractor's `value` for the same `(eng_reversa_result_id, variable_id)`, character for character. The extraction then shows `already_added=true` (9 such matches).
- `plays` on the item = the source viral's views.
- 238 of the 263 items were created on **2026-06-16** in one batch, eight days after the workspace was created (2026-06-08). This fits the automatic suggestion at onboarding. **I**
- The other 254 items come from profiles outside the six fetched extractions, i.e. from the wider approved-profile pool (485 profiles). **I**
- The owner has 0 especialista items (`type=especialista`: 12 variables, all empty). **C**

### 1.5 How items feed generation

| Consumer | Mechanism | Tag |
| --- | --- | --- |
| Gerar Headlines (`who=public|me`) | Selecting variables (`variables_id[]` as `ID|SLUG`) calls `get-variables-values` → one multi-select per variable listing the user's **approved** items (`variable_values[]` = `varId|content`). Checkbox `complete_with_research` "Criar as headlines usando apenas os itens da minha pesquisa." restricts the batch to those items | C |
| Structure matching | `has_structures` per variable + "Exibindo somente perfis que possuem estruturas com as variáveis selecionadas." + per-profile `is_structure` + result warning "poucas estruturas compatíveis" ⇒ a **structure** (headline template from a viral) is indexed by the variables it contains | C (signals) / I (index) |
| Chat | `@` → "Minha Pesquisa" tab (`searchMyResearch(q, group, page, sort, variable)`), attached as references; agent tool labels `consultar_variaveis_perfil`, `find_variables`/`validate_variables` | C |
| Biblioteca wizard | only `ASSUNTOS_VIRAIS` (approved viral topics) | C |
| Roteiros | no research variable is read by any roteiro form | C |

~~**Open:** how a structure stores its variable slots — no structure text has been captured. **U**~~

**2026-10-06 XHR — answered for suggested headlines:**
- A structure is stored as a **blueprint document per viral** (`eng_reversa_headline_text`, §5.7). Its slots are literal `{{DB-SLUG}}` placeholders using the **DB slugs** (`ID|SLUG` vocabulary). They are **not** the classifier slugs: the blueprint writes `PESSOAS-PERSONAGENS-CONHECIDOS-PELO-AVATAR`, never the classifier's `PESSOAS-E-PERSONAGENS-…-MEU-PUBLICO`. **C**
- One extra slot, `{{GPT}}`, means "verbs/actions the model adapts". No DB slug for it is known. Global id 29 is *labelled* "GPT", but its definition was never seen, so the two are **not** merged. **U**
- How `has_structures` per variable is computed is still **U**. Plausibly: some blueprint contains that slug. **I**
- Whether form batches (`headlines/store`) read the same blueprints is **U**: only suggested-headline rows were readable.
- Slot ↔ variable table, mapped by definition: `prompts/headline-engenharia-reversa-DRAFT.md` §3.

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

### 3.4 2026-10-06 XHR — brain status contract and where "Núcleo de Influência" comes from

**`GET cores/brain-status/{coreId}`** (C, 7 cores):

| Core | Badge | Response |
| --- | --- | --- |
| 3081 Núcleo de Influência | Pronto | `brain_status: synced`, `validation_status: completed`, 15 `responses` (questions 1583–1597, all `completed`, `rejection_reason: null`) |
| 8, 9, 14 (Sistema) | **Vazio** | `brain_status: synced`, `validation_status: pending`, `responses: []` |
| 3741, 4191, 4192 (Personalizado) | Pronto | same as above: `synced`, `pending`, `[]` |

- So `brain_status` is the sync state of the store, **not** the Vazio/Pronto badge: an empty brain is also `synced`. **C**
- `validation_status` is `pending` for every brain that never went through the questionnaire. **C**
- The badge must come from `content` being empty or not. **I**

**The headline "NÚCLEO DE INFLUENCIA" is not the Núcleo de Influência brain.** Two objects share the name:

| Object | What it is | Tag |
| --- | --- | --- |
| The `###NÚCLEO DE INFLUENCIA:` line in the headline payload | For the owner, word for word the **Meu Perfil `bio`** ("Eu sou … / Falo sobre … / Ajudo … / Porque …"). The same text is also the `### BIO` section of the custom brain **Narrativa** (4192) | C (text equality) |
| Brain 3081 "Núcleo de Influência" | the questionnaire synthesis ("### Perfil Profissional de Gilson Tangerino …", four sections) | C |

- The bio is the more likely source. Meu Perfil says the bio is required for suggestions, and another tenant's line is a 4,256-char free text. **I**
- So **no brain answer reaches the suggested-headline payload**. **C** for the stored payload; **U** for the hidden system prompt.
- The earlier inference "the HEADLINE agent uses the Núcleo de Influência (brain) for identity" (from chat transcripts) still stands for the **chat agent** (tool `nucleo_influencia`), but it does **not** carry over to the suggested-headline job. **Refuted** for that job.

**Custom brains** (`cores/edit/{3741,4191,4192}`): free markdown content (12,226 / 5,472 / 2,759 chars), no questionnaire. 4192 is sectioned `### MOVIMENTO IDENTIFICADO`, `### BIO`, `### APRESENTAÇÃO MAGNÉTICA`, `### NARRATIVA`. **C**

---

## 4 · "Extrair" — three different mechanisms with similar names

| Name in UI | Route | Input | What is extracted | Output | Tag |
| --- | --- | --- | --- | --- | --- |
| **Extrair Pesquisa** | `/searches/extract-profile` | an approved viral profile | nothing at click time: shows the **precomputed** phrase-per-variable extraction of that profile's virals (`headline` = the video's opening sentence; `value` = the phrase; per variable slug) | ticked phrases → user research items | C |
| **Extrair Assuntos Virais** / per-profile research job | modals on `/searches` | `{type: myPublic|topic_virais, eng_reversa_search_id}` | runs (or re-runs) extraction for one profile into the user's pending items / pending topics, deduplicating existing ones | pending items or topics + counts | C |
| **Minhas extrações** (Nova Extração) | `/cores/extract` (hidden) | name + target brains (`nucleos[]`) + a YouTube/Dropbox URL or a pasted transcript | transcription (`cores/transcrible`), then an LLM "Pesquisa Gerada" | a text applied to brains, or to variables via "Selecione o Tipo de Variável" | C (form) / I (apply semantics) |

**2026-10-06 XHR — the extractor confirmed (`profile-viral-search/{id}`, 6 profiles).**
- Response: `{success, profile, data:[{variable_id, variable_name (DB slug), label, items:[{result_id, plays, thumbnail, post_link, headline, value, already_added}]}]}`. **C**
- `headline` is the viral's spoken hook (median 19 words). `value` is a **literal substring of that hook** in **641 of 643** items. The extractor tags spans of the hook; it does not paraphrase. **C**
- Only DB slugs appear: 18 of the 29, including the especialista slugs 1, 2, 3, 6, 12. No classifier-only slug appears, and no `GPT`. **C**
- Per profile: 15–108 virals and 19–175 items. The most frequent variables are 13 Pessoas/personagens (133), 17 Dores (86), 18 Desejos (81) and 14 Instituições (76). **C**
- The same extractor output is what the blueprint step marks as "conteúdos literais fornecidos pelo extrator" (§5.7). **I** (strong: same slugs, same literal spans)

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

**2026-10-06 XHR — corrected.**
- The four blobs come from **`GET roadmaps/reversa/show/{id}`** (its `data` object). `headlines/suggested/view/{id}` returns only a roteiro status. **C**
- For suggested headlines there is **no revision pass**: `payload_headline` is `null` and `callback_headline` equals `callback_headline_old_1` in 6/6 samples (manual and automatic). **C**. "Two-pass" is **refuted** for this job.
- Whether form batches (`in_gpt2`) run a real second pass is still **U**.
- `payload_headline_old_1` is the **user message only**. It has no task or format instructions, yet the output is always `{"headline_1","headline_2"}`. So a hidden system prompt exists and is not readable read-only. **C** (absence) / **I** (system prompt)
- One call → two rows (`number_headline` 1 and 2). **C**

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
- **Correction 2026-10-06:** the owner's 20 dashboard suggestions are ids **201486–201503, 201774, 201775**, not "201755–201775". The 2026-10-05 map interpolated a range. 201755/201760/201765/201770 belong to other customers (§15). **C**

### 5.7 How a viral becomes a blueprint, and a blueprint a headline (2026-10-06 XHR)

```
viral (eng_reversa_result)
  → transcription_text + hook "headline"                                   C
  → extractor: (DB slug, literal span of the hook) pairs                   C  (profile-viral-search)
       └─► copied into users' research items (pending/approved)            C  (same content, same result id)
  → blueprint step (LLM): hook with spans replaced by {{DB-SLUG}},         C output / I input
     per-viral slot definitions, 3 modeled headlines in other niches,
     self-check (automatic variant)
     stored as eng_reversa_headline_text, run id eng_reversa_flow_result_id  C (field) / I (run)
  → headline job (LLM): "###NÚCLEO DE INFLUENCIA: <bio>\n\n<blueprint>"   C
     [+ "\n\n<assunto>" in manual mode]                                    C
     + hidden system prompt                                                I
  → {"headline_1","headline_2"} → two suggested rows                       C
```

- The same column `eng_reversa_flow_result_id` also links a viral to its **format classification** (`library/result` → `engReversaFormatVideoRelation`). The ids grow with the viral id (virals 7145–7153 → about 26.9k; 105038 → 703,411; 157591 → 1,012,840). So it looks like **one analysis run per viral** produces format + blueprint. **C** (shared column, monotonic) / **I** (one run)
- **Research items are not in the payload.** Generated words come from the bio. The blueprint's own rule "use apenas conteúdos literais fornecidos pelo extrator" is overridden in generation. **C** (payload, outputs) / **I** (instruction)
- **Daily suggestions use old virals**: tenants' automatic rows came from virals 7145–7153. The selection rule is still **U**. **C** ids
- Full template, diff table and worked examples: `prompts/headline-engenharia-reversa-DRAFT.md` (**DRAFT**).

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

**2026-10-06 XHR (41429).**
- `params` adds `viral_video_id`, `serper_search_in_portuguese`, `serper_query` (an English PubMed query) and `source_links[]`. `payload` is empty again, so **no roteiro prompt is readable**. **C**
- 41428 and 41429 share the headline and the draft. 41429 copies the **rhetorical device of the reference viral** ("Isso aqui é você…"). 41428 invents statistics. **C**
- 41429 ignores its off-topic PubMed source. **C**
- Contract and gaps: `prompts/roteiro-DRAFT.md` (**DRAFT**).

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

### 7.5 2026-10-06 XHR — what the library data confirms or refutes

| Point | Finding | Tag |
| --- | --- | --- |
| Skeleton storage | Text with `{{DB-SLUG}}` slots, stored per viral (the blueprint, §5.7). Seen through suggested headlines; `library/result/{id}` itself does **not** return it | C |
| `library/result/{id}` shape | `{id, pode_usar_core, is_core, eng_reversa_search_id, thumbnail, plays, likes, comments, post_date, transcription_text, post_link_public, relations[{niche_id, profession_id, niche, profession}], engReversaFormatVideoRelation[{format_video_id, eng_reversa_flow_result_id, format_video{name, definition, signals, alias}}], profile, social}`. **No hook-headline field, no blueprint, no variables.** `is_core` is null and `pode_usar_core` false in all 14 found | C |
| The 5 unexplained structure ids | 124684 → "Viral não encontrado" (also absent from `/library?viral_result_id=124684`; not in the approved library). 124700 → `dr.marcelo.santos` (search 1424). 147089 → `veridiana_cavalheri` under search **1439**. 147091 and 148727 → `veridiana_cavalheri` under search **1442**. 147089 and 147091 are **the same video** (same hook and views) stored twice under two profile records of one handle. So the chat pool includes profile records other than the ones the library pages showed | C |
| Duplicate profile records | One handle can have several `eng_reversa_search` rows (veridiana: 1439, 1442, 1640), and the same post can come back as a new viral id. Only 1439 is in `headlines/profiles` (`is_structure=1`) and in `approved-profiles`. 1442 and 1640 are in neither list, yet `profile-viral-search/1640` answers with 87 virals. So which record the lists show and which records feed extraction/structures differ | C |
| `is_structure` | `headlines/profiles` = 514 profiles, **161** with `is_structure=1`. The two most-cited chat structure sources, psifernandosegredo (1702) and elias.maman (1735), have **`is_structure=0`**. So the flag does **not** decide which virals the chat HEADLINE agent can use as structures. It still disables profiles in the form's "Perfil de Referência" (code). The earlier claim "profiles with is_structure=0 cannot be picked" stays true for the form only; its meaning remains **U** | C / U |
| Approved profiles | `approved-profiles` = 485, and `approved-profiles-viral-topics` = the **same 485** (same ids, same fields: profile, social, search id, ≤ 3 thumbnails, niche_ids, profession_ids). 29 of the 514 headline profiles are not approved | C |
| Corpus size | `/library?view_all=1` = **1,689 pages** × 24 ≈ 40.5k virals. The 281 pages measured before were the owner's niche-filtered view | C |
| Core filter | `/library?view_all=1&core=1` returns the same first page and page count as without it: the filter is ignored for this (non-staff) user | C |
| `library/videos` picker | `{id, eng_reversa_search_id, profile, title (= Instagram caption), thumbnail_url, plays, likes, comments, shares (0), video_url (Instagram CDN), format_name, post_date, transcription_text}`, `count` and `total_available` capped at 100. `title` is the **caption**, not an extracted headline. `description` is absent or empty | C |
| `library/profiles` | `{id, profile, social, total_plays, total_likes, total_comments, video_count, thumbnail_url}`; elias.maman = 105 videos | C |
| Viral topic ↔ video | `viral-data/{topicId}` returns **one** video per topic here (`{id, title (caption), description null, plays, likes, comments, created_at, url, thumbnail, post_date}`) | C |

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
- **Posts** (`instagramPosts`, 9 per page, 168 stored of 1,592 on the account): `post_id` (local, sequential), `media_id` (null), `media_url` (Instagram CDN, expiring), `thumbnail_url` (S3 copy), `media_type`, `caption`, `permalink`, `timestamp`, `engagement`, `reach`, `impressions` (always 0 — a metric Instagram retired), `saved`, `likes`, `comments`, `shares`, `views`. ~~Only a recent window of posts is imported.~~ Refuted 2026-10-06: only **videos** are imported, back to 2024-04-03 (see below). **C** counts.
- **Dormant:** `?period=` select and a "select up to 60 posts" modal (`posts/all` returns posts with `selected`; `posts/set` stores the choice). Purpose **U** — plausibly choosing the user's own posts as AI references or for the dashboard "Diagnóstico" card (both **I**).

**2026-10-06 XHR — refined.**

*Stored posts* (`/profile/instagram?page=N`, inline `instagramPosts`):
- 168 posts, 9 per page, 19 pages. **C**
- **Every stored post is `media_type: VIDEO`** (15 of 15 on pages 2 and 19). **C**
- The oldest stored post (page 19) is from **2024-04-03**, so it is **not** a recent window. **Refuted.** **C**
- The import keeps **videos (reels) only**: 168 of the account's 1,592 media. Whether it is all videos or the last N videos is **U**. **I**
- `post_id` is local and sequential (23760…); `media_id` is null; thumbnails are S3 copies named after the Instagram media id. **C**

*`GET profile/instagram/posts/all`* (the 60-post modal's source):
- Returns a **bare array of 100** live Instagram Graph media objects, newest first. **C**
- Fields: `id` (Instagram media id), `caption`, `media_type`, `media_product_type`, `media_url`, `thumbnail_url`, `permalink`, `timestamp`, `is_shared_to_feed`, plus CoreStudio's `selected` (0/1). **C**
- Window **2025-12-03 → 2026-10-06**. Mix: 67 REELS (VIDEO), 30 CAROUSEL_ALBUM, 3 IMAGE. **C**
- No metrics. These are not the stored rows: the ids are Instagram ids. **C**
- 100 is the Graph API page size (one page, no paging seen). **I**

*The `selected` flag*:
- **66** posts are `selected=1`. They are exactly the 66 REELS with `is_shared_to_feed=true`. The single reel with `is_shared_to_feed=false` and all 33 FEED posts are `0`. **C**
- So `selected` is **set by the server by rule** (reels shown in the feed), not by the user. 66 is also more than the modal's own 60 limit. **I** (rule) / **C** (counts)
- With selection = reels, the "select up to 60" modal most plausibly picks **which of the user's own videos** to analyse (e.g. as references or for the "Diagnóstico" card). **I**. Purpose still **U**.

### 8.3 Use in generation

No surface reads Instagram data into headline/roteiro generation in the captured code. **C** (absence) / **U** server-side.

**2026-10-06 XHR:**
- The stored suggested-headline payloads (6) and roteiro params (2) contain **no Instagram data**. **C**
- The hidden system prompts remain **U**.

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
| eng_reversa_headlines (suggested) | `user_id, workspace_id, eng_reversa_result_id, eng_reversa_flow_result_id, niche_id, eng_reversa_headline_text (blueprint), headline, number_headline, payload_headline_old_1, callback_headline_old_1, payload_headline, callback_headline, roadmap_payload, roadmap_response, roadmap, roadmap_id, status, mode, link_viral, approved, admin_id, search_id, search_text, use_article, use_article_niche` (2026-10-06 XHR, C) | viral 1–N suggested; one LLM call → 2 rows |
| eng_reversa_flow_results (blueprint / analysis run) | id only; referenced by suggested headlines and format relations | viral 1–1 run (I) |
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

1. ~~**Headline prompts:** read `headlines/suggested/view/{id}`.~~ **Done 2026-10-06** via `roadmaps/reversa/show/{id}` (§5.3, §5.7).
   - Still open: the **hidden system prompt** of the headline job, and the prompt of the **blueprint step**.
   - Do we rebuild those from the observed contract (`prompts/headline-engenharia-reversa-DRAFT.md`), or design ours from the Método Audience?
2. ~~**Structure storage.**~~ **Answered:** a stored per-viral blueprint with `{{DB-SLUG}}` slots (§5.7). Still open: do form batches and the chat agent read the same blueprints?
3. **Auto-suggested research items:** when do they run (on profile save, nightly) and from which profiles?
4. **Brains in roteiros:** is Núcleo de Influência always used ("2. Extraindo Núcleo") even when no brain is picked?
5. **Instagram data:** what is the dormant "select up to 60 posts" for, and does any generation read the user's own posts or metrics? What is the Dashboard "Diagnóstico — a preencher" card?
6. **Plan gating:** what do the hidden **Avatar** and **Estudio de Edicao** sections contain, and which features are Premium-only besides Biblioteca?
7. **Rebuild scope (carried from DECISIONS.md):** keep the legacy paths (Box, Minhas extrações, legacy headline modal, legacy roteiro A/C) or only the current ones (form page, Roteiro Avançado, chat)?
8. **Allow-list as structure pool:** do we reproduce "Minha Biblioteca = the agent's structure pool" deliberately (it explains why the account's headlines reuse ~50 structures)?
9. **Núcleo input (new):** CoreStudio feeds the headline job the **bio** under the label "Núcleo de Influência", not the brain of that name. Which should our build use: the bio, the brain, or both?
10. **Research items in generation (new):** in CoreStudio they are suggested from virals but **not used** by the suggested-headline job. Do we want our generator to fill slots from the user's approved items (the original intent of the blueprint rule "conteúdos literais do extrator")?
11. **`{{GPT}}` slot (new):** keep a "model-free" slot in our blueprints, or force every slot to a research variable?
12. **Cross-tenant data (new, §15):** the captures hold four records of two other CoreStudio customers. Delete them locally? Report the leak to CoreStudio?

---

## 15 · Cross-tenant read in CoreStudio (found 2026-10-06)

- `GET /roadmaps/reversa/show/{id}` and `GET /headlines/suggested/get/{id}` returned suggested-headline rows of **other customers** to the owner's session. **C**
  - 201755 → user 603 / workspace 601.
  - 201760, 201765, 201770 → user 1639 / workspace 1591.
  - The ids were guessed by interpolating the dashboard range.
- What leaked: the full payload, including those users' **bio / persona text**, real names and their generated headlines. **C**
- `headlines/suggested/view/{id}` (`b1`) answered for 201760 too, with status only. **C**
- So these endpoints check authentication, not ownership (an IDOR). **C** (behaviour)
- **Do not copy this into our build:** every read by id must be scoped to the caller's workspace.
- Handling of the captured data: the four `c14_*` and `c13_*` files for those ids and `b1_suggested_view_201760.json` are **kept out of git**. The prompt draft names those users only as "tenant B/C" and does not quote their persona text. Deleting the local copies and reporting the issue to CoreStudio are owner decisions (§14 Q12).
