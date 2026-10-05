# CoreStudio — page-script static analysis (reference)

Source folder: `scratchpad/corestudio/js/`. This is a static read only: nothing was executed and no requests were made.

**Files analyzed (all of them were present at start, and nothing new appeared later):**

| File | Size | What it is |
|---|---|---|
| `headlines.js` | 1,912 lines | Headlines pages: the generate modal, the view/reprocess modal, favorites (like/unlike/edit/delete), "Criar Roteiro" from a favorite, the suggested-headlines daily trigger, the "Box" of headlines, and profile suggestions |
| `roadmaps.js` | 1,004 lines | Roteiros (roadmaps) page: simple create, progress polling, the view/edit modal (Quill), feedback, reprocess, chat-mode launch, delete, agent questions |
| `dashboard.js` | 507 lines | Legacy/agency "make-headlines" modal (client → structures/variables cascade) and the "Box de headlines" save/remove |
| `advanced-roadmap-modal.js` | 3,458 lines | `AdvancedRoadmapModal` IIFE. It contains the current 3-step "Opções Avançadas" flow and several legacy flows (manual/auto/library, questions, list-search, Perplexity/GPT search) |
| `advanced-roadmap-library.js` | 764 lines | `AdvancedRoadmapLibrary`: a viral-video library picker used inside the advanced modal |
| `app-DLOM2UdR.js` | 120 lines (283 KB minified) | Vite bundle: axios + Alpine + Livewire 3 + `@microsoft/fetch-event-source`. App code sits in the last ~50 KB: the Alpine component `aiChat` (Pusher/Echo), `window.ragChat` (the SSE RAG chat at `/dashboard/user/chat`), and `marked` link config |

**Platform fingerprint.** The bundle reads `localStorage` keys `lqdDarkMode`, `lqdNavbarShrinked` and `docsViewMode`. It also has `workspace_id`, routes under `/dashboard/user/...`, `/api/return/integration/ai/chat` and `dashboard/user/ai/status/{id}`, plus credit packages and recharges. Together these strongly suggest CoreStudio is built on LiquidThemes' **MagicAI** Laravel SaaS script, with a large custom domain layer added on top (headlines/structures/variables, "eng_reversa", roteiros, cores/"cérebro", viral library, RAG agents). The Laravel conventions follow from that: CSRF meta, `419` handling, `422` `errors` bags, and server-rendered `<option>` HTML returned in `content_option`.

---

## 0. Cross-cutting conventions

### 0.1 Standard JSON "action envelope" (nearly every POST)
Server responses drive the UI through flags. Every handler checks these:

| Field | Effect |
|---|---|
| `success` (bool) | Gates the success path |
| `type` (`success`/`error`/`warning`/`info`/`subject_action`) | `toastr[type](message)` |
| `message` | Toast text |
| `redirect` (url) | `location.href` after 1000 ms |
| `refresh` / `reload_page` (bool) | `location.reload()` after 1000 ms |
| `button` (bool) | Re-enables the submit button and restores its label |
| `reset` (bool) | Resets the form and clears TomSelects |
| `modalOut` (bool) | Hides the modal |
| `open_modal`, `modal_data` | Stored in `localStorage.openModalAfterReload`. After reload, `headlineCreatorModal` opens (`modal_data.headline_id`, `modal_data.status`) |
| `show_progress` + `id_headline` | Calls `window.showProgressAnimation(id_headline)`, which is defined in Blade and not included here (async headline generation) |
| `fade_out` | Hides the Box icon and offcanvas |

Error handling:
- Status `419`, or a message containing "csrf", is ignored silently.
- `responseJSON.errors` gives one toast per entry.
- Otherwise `responseJSON.message` is shown, or a fixed fallback such as "Ocorreu um erro ao …".

### 0.2 Request style
- Requests are jQuery `$.ajax` with `FormData` (`contentType:false, processData:false`) or urlencoded. CSRF comes from `meta[name=csrf-token]`, sent either as a global ajaxSetup header (implied) or as an explicit `_token`.
- `fetch` is used only in the library and chat code.
- URLs are mixed relative (`dashboard/...`) and absolute (`/dashboard/...`), which implies a `<base href>`.
- Pickers use TomSelect throughout. Modals are Bootstrap 5, toasts use toastr, JSON display uses Prism, and the roteiro editor is Quill.

### 0.3 Async-job pattern (the app's core design)
Generation is **queued server-side**, and the client **polls**:
- **Roteiros, simple flow:** `POST roadmaps/store` returns `roadmap_ids[]`. The client then sends `POST roadmaps/check-progress` every **5 s** until `roadmapsSuccess.length == roadmap_ids.length`. There is no timeout.
- **Roteiros, advanced flow:** `POST advanced store` returns `headline_id|roadmap_id`. The client then sends `GET show/{id}` after 2 s, then every **5 s**, up to **120 polls (10 min)**, until `status==='completed' && roadmap_advanced`.
- **Headlines:** `store-custom-subject` may return `show_progress`. Progress UI then comes from Blade's `showProgressAnimation`, which is not in these files.
- **Legacy aiChat widget:** `POST /api/return/integration/ai/chat` returns `task_id`. The answer arrives through **Pusher** (`.nova-mensagem`). There is also a fallback poll, `GET dashboard/user/ai/status/{id}`, every 1 s up to 180 tries.
- **RAG chat:** answers are streamed over **SSE** (§2.2).

---

## 1. HTTP endpoints, grouped by feature

### 1.1 Headlines — generation
| Method | URL | Payload | Response fields used |
|---|---|---|---|
| GET | `/dashboard/user/variables/type/{who}` | — (`who` = the "Falar sobre" radio value) | `content_option` (HTML `<option>`s; some may be `disabled`) → subject TomSelect `#make-headlines-select-variables-user`. Requests are generation-counted and aborted on change |
| POST | `/dashboard/user/headlines/store-custom-subject` | `FormData(form#make-headlines-viral)` + `who` (= `who-choose` ‖ `who`) + `add_input` (`2` if who=`subject-moment`, otherwise `1`). The form fields come from Blade; see §3.1 for the known names | envelope + `type:'subject_action'` with `subject{success, subject(HTML)}` → renders a subject-picker step. Also `show_progress`, `id_headline`, `open_modal`, `modal_data` |
| POST | `/dashboard/user/headlines/store` | `FormData(form#make-headlines-me \| form#make-headlines-intelligent-search)` + `who` + `add_input=1` + `input_user` (from `form#make-headlines textarea[name=input_user]`) | Same envelope / `subject_action` |
| POST | `/dashboard/user/headlines/get-profile` | `variable_selected[]` (selected subject ids), `_token` | `success`, `profiles[{search_id, profile}]` → fills "perfis de referência" TomSelect `#make-headlines-profiles-me-public`, and shows `#profile-reference-alert-me-public` |
| POST | `dashboard/user/headlines/get-variables-values` | `customer_id` (`.user_id_input`), `variables[]` | `content_option` HTML → `.j_all_values` |
| POST | `/dashboard/user/headlines/generate-sugeridas-day` | none | Logged only. It **fires on every page load** that includes headlines.js and triggers the daily "Sugeridas" generation (server-side idempotent per day, presumably) |

### 1.2 Headlines — view / reprocess / delete
| Method | URL | Payload | Response |
|---|---|---|---|
| GET | `dashboard/user/headlines/view/{id}` | — | `success`, `headline_preview` (HTML list of generated headlines), `payload` (JSON shown pretty-printed with Prism, i.e. the generation request/params), `structure_count`, `headline_count` |
| GET | `/dashboard/user/headlines/reprocess/{headline_id}` | — | envelope (`type`, `message`, `refresh`) |
| GET (link) | `/dashboard/user/headlines/delete/{id}` | — | Plain navigation after a confirm modal |

### 1.3 Headlines — favorites ("Minhas favoritas")
| Method | URL | Payload | Response |
|---|---|---|---|
| POST | `/dashboard/user/headlines/like` | `structure_id`, `headline` (text), `headline_id` (generation batch id) | `success`, `type`, `message`. The button toggles to the filled heart / `.j_headline_unlike` |
| POST | `/dashboard/user/headlines/unlike` | same | same (toggles back) |
| GET | `/dashboard/user/headlines/favorites/get/{id}` | — | `success`, `roadmap` (text; the edit modal shows a roteiro textarea only if it is non-empty) |
| POST | `/dashboard/user/headlines/favorites/update` | `FormData(form#headline-favorite-edit)`: `id`, `headline`, `roadmap` | envelope |
| GET (link) | `/dashboard/user/headlines/favorites/delete/{id}` | — | navigation |
| POST | `/dashboard/user/headlines/favorites/get-questions` | `headline_id`, `_token` | `success`, `questions[{question}]` → dynamic inputs `question_id[]` (= the question text) + `questions[]` (the answers, required) |
| — | `/dashboard/user/headlines/suggested?hid={id}` / `/dashboard/user/headlines/favorites?hid={id}` | — | Deep links from a roteiro back to its source headline (`.js_view_headline_from_id`, `data-source` ∈ `suggested`/`favorite`) |

### 1.4 Box de headlines (a cart/collection, agency-style)
| Method | URL | Payload | Response |
|---|---|---|---|
| POST | `/dashboard/box-headlines/add` | `FormData(form#apply-headlines-box)` (Blade; headline(s) + structure) | `success`, `type`, `message`, `box_headlines` (HTML list → `.j_box-headlines-list`). Opens `#offcanvasEnd` |
| POST | `dashboard/box-headlines/remove` | `FormData(form#box-headlines-save)` | `success`, `box_headlines`, `fade_out` |
| GET | `dashboard/box-headlines/customer/{customer_id}/list` | `customer_id` | `options` (HTML for `select[name=headline_week_id]`), `message`, `type` |
| POST | `dashboard/box-headlines/customer/{customer_id}/save` | `FormData(form#form_box_headlines_save)` (`customer_id`, `headline_week_id`, …) merged with `FormData(#box-headlines-save)` | envelope. Reset placeholder: "Selecione um cliente primeiro." |
| POST | `/dashboard/box-headlines/make` | (commented-out legacy) | — |

### 1.5 Legacy / agency make-headlines (`dashboard.js`, multi-client "customers")
| Method | URL | Payload | Response |
|---|---|---|---|
| GET | `/dashboard/make-headlines/get-structures/{clientId}` | — | `[{id, name}]` → `select[name="structure_id[]"]` with default option "Todas" |
| POST | `dashboard/make-headlines/get-variables-type` | `customer_id` | `content_option` → `select[name=variable_type_id]` |
| POST | `dashboard/make-headlines/get-variables` | `customer_id`, `variable_type_id` | `content_option` → `#make-headlines-select-variables` |
| POST | `dashboard/make-headlines/get-variables-values` | `variables[]`, `customer_id`, `variable_type_id` | `content_option` → `.j_all_values` (only when `add_input==1`) |

`add_input` radio: `1` = "make software" (choose variables), `2` = free text (`.j_make_headlines_input_user`).

### 1.6 Roteiros (roadmaps) — simple flow & management
| Method | URL | Payload | Response |
|---|---|---|---|
| POST | `dashboard/user/roadmaps/store` (also `/dashboard/user/roadmaps/store` from favorites) | `FormData(form#make_roadmap)` or `form#favorites_make_roadmap`. Known fields: `headline` (URI-decoded), `structure_id`, `headline_id`, plus Blade fields such as agent (`#customer-headlines-select-agents`), core/brain selects (`select-core-brains`, `favorites-select-core-brains`, `favorites-select-core-beliefs`), `question_id[]`, `questions[]` | envelope + `roadmap_ids[]` (several ids means several **options** are generated in parallel; the result renders "Opção 1/2/…") |
| POST | `/dashboard/user/roadmaps/check-progress` | `roadmap_ids[]` | `roadmapsSuccess[{id, roadmap_content}]` |
| GET | `dashboard/user/roadmaps/view/{id}` | — | `success`, `name`, `payload` (JSON), `params` (`observations`, `brain_id`/`core_id`, `viral_id`/`viral_video_id`, `roadmap_source_type`, `source_links[]`, `selected_links[]`), `roadmap_gpt` (text or HTML), `roadmap_liked` (0 = no feedback, 1 = liked, other = disliked), `search_text` (sources dossier, rendered in a "Fontes" tab), and optionally `headline`, `observations`, `brain_id`, `viral_id`, `viral_video{title, description, plays, likes}` (consumed by `openForReprocess`) |
| POST | `dashboard/user/roadmaps/update` | `FormData(form#form-customer-roadmaps-edit)`: `id`, `name`, `roadmap_gpt` (Quill HTML) | envelope. Client-side validation: empty content is rejected with "O conteúdo do roteiro não pode estar vazio…" |
| POST | `dashboard/user/roadmaps/reprocess` | `FormData(form#form-roadmap-reprocess)`: `id` (legacy; the new reprocess goes through the advanced modal) | envelope |
| POST | `dashboard/user/roadmaps/setFeedback` | `roadmap_id`, `feedback` (int 1 or other) | `message` |
| POST | `dashboard/user/roadmaps/set/reason` | `roadmap_id`, `reason_unliked` | `message` |
| POST | `dashboard/user/roadmaps/get-question-roadmap` | `agent_id` | `questionRoadmap[{question}]` → dynamic `question_id[]` ("N - question") + `questions[]` |
| GET (link) | `/dashboard/user/roadmaps/delete/{id}` | — | navigation |
| — | `dashboard/user/roadmaps?open_id={id}` | — | Auto-clicks `.j_roadmaps_view[id=…]` after 2.5 s |

### 1.7 Roteiro Avançado ("Opções Avançadas") — `window.AdvancedRoadmapModalConfig`
Blade injects `{ csrfToken, routes: { store, show ('…/__ID__'), generateQuestions, listSearch, directSearch, translateSearchQuery, translateSearchResults, updateRoadmap, updateSuggested, chat ('…/__ID__') } }`. Hardcoded fallbacks:
- `/dashboard/user/headlines/suggested/advanced-roadmap/list-search`
- `/dashboard/user/headlines/suggested/advanced-roadmap/direct-search`
- `/dashboard/user/headlines/suggested/advanced-roadmap/translate-search-query`
- `/dashboard/user/headlines/suggested/advanced-roadmap/translate-search-results`

| Method | Route key | Payload | Response |
|---|---|---|---|
| POST | `store` (current, `mode:'steps'`) | `_token`, `ai_provider` (default `'claude'`), `mode:'steps'`, `save_to` (`user_roadmaps` \| `eng_reversa_headlines`), `roadmap_source_type` (`none`\|`links`\|`serper`), `observations`, `roadmap_use_pubmed` (`'0'`/`'1'`), `headline_id` **or** `headline_text`, `source_links[]` (≤4), `serper_query` (the effective query sent, possibly translated), `serper_search_in_portuguese` (`'0'`/`'1'`), `core_id` (Segundo Cérebro), `viral_video_id`, `duration_minutes` (default `'auto'`), `is_reprocess` (0/1) | `success`, `headline_id`, `roadmap_id`, `message` |
| POST | `store` (legacy `mode:'default'`) | the above minus steps-specific fields, plus `advanced_search` (`'0'`/`'1'`), `enable_review` (`'0'`/`'1'`, checkbox `#enableRoadmapReview`), `search_provider` (`perplexity`\|`gpt`\|`gpt-deep`), `search_type` (`resumo`\|`completo`), `viral_video_id`, `search_results_data{queries[], selected_links[]}`, `selected_links[{url,title,snippet,query_posicao,query_item_pt}]`, `brain[]` (multi-select `#select-brain-ids`), `observations` (+ "\n\n" + auto search direction) | same |
| POST | `store` (legacy `mode:'simple'`) | `observations` (required) + same options | same |
| POST | `store` (legacy questions) | `questions[]`, `answers[]` + options | same |
| GET | `show/{id}` | `headline_id` | `success`, `status` (`'completed'` \| other), `roadmap_advanced` (text), `roadmap_id`, `headline_id`, `roadmap_source` (resource type for chat), `search_id`, `search_text`, `use_article` (bool), `article_message`, `use_article_niche` |
| POST | `generateQuestions` | `save_to`, `headline_id` \| `headline_text` | `success`, `questions[]` (strings) |
| POST | `listSearch` | `autoSearchDirection`, `headlineText` | `success`, `data.queries[{posicao, item_pt, descricao, query, idioma, tipo, result[{link,title,snippet}]}]` (an LLM plans N research queries, each run via Serper) |
| POST | `directSearch` | `query`, `gl` (`us`/`br`), `hl` (`en`/`pt-br`) | `success`, `data.organic[{link,title,snippet}]` (raw Serper.dev response) |
| POST | `translateSearchQuery` | `query` | `success`, `data.query_en`, `message`. The code comment says "traduzir com GPT-4o-mini" |
| POST | `translateSearchResults` | `title`, `snippet` (one call per result, fanned out in parallel) | `success`, `data{title, snippet}` |
| POST | `updateRoadmap` | `id` (roadmap id), `name` (headline ≤255), `roadmap_gpt` | `success`, `message`, `errors` |
| POST | `updateSuggested` | `id` (headline id), `headline`, `roadmap` | `success`, `message` |

### 1.8 Viral library (Biblioteca)
| Method | URL | Query | Response |
|---|---|---|---|
| GET (fetch, `Accept: application/json`, `X-Requested-With`) | `/dashboard/user/library/videos` | `transcription_search` (comma-separated terms), `format_video`, `profile`, `views_min`, `likes_min`, `niche` | `videos[{id, title, description, thumbnail_url, plays, likes, comments, format_name, transcription_text}]` |

### 1.9 Chat
| Method | URL | Payload | Response |
|---|---|---|---|
| POST | `/dashboard/user/chat/start` | `resource_id`, `resource_type` (`user_roadmaps` \| `eng_reversa_headlines`), `_token` | `success`, `redirect` (chat URL), `message`. This starts a chat seeded with a roteiro ("Modo chat") |
| POST (SSE) | `ragChat` `_streamUrl` (Blade-injected) | JSON `{question, selected_agent_id, conversation_id, attached_reference_ids:[{source,id}]}`, `Accept: text/event-stream` | SSE events, see §2.2 |
| POST | `_docUploadUrl` | multipart `file` (pdf, docx, txt, md, csv; ≤20 MB) | `{id, title, meta, status}` (`pending`/`processing`/ready) |
| GET | `_creditsUrl` | — | `{has_payment_method, packages[{id,…}]}`. The default selection is `packages[1]` |
| POST | `_rechargesUrl` | JSON `{credit_package_id}` | `{message}`. Success: 'Recarga concluída! Clique em "Gerar vídeo" pra continuar.' |
| — | `_faturamentoUrl` | — | Redirect to billing |
| POST | `/api/return/integration/ai/chat` (legacy aiChat widget) | multipart: `message` \| `file` (pdf/txt/doc/docx/odt/rtf) \| `audio` (`audio.webm`), `workspace_id` (meta, default 3), `user_id` (meta), `app_env` (meta) | `{task_id}` or `{message}` on error |
| GET | `dashboard/user/ai/status/{task_id}` | — | `{status ('completed'\|'error'\|…), status_message, progress (%), response, error}` |
| POST | `/broadcasting/auth` | Pusher private-channel auth (`X-CSRF-TOKEN`) | — |

**Livewire `$wire` methods on the RAG chat component** (server-side component state and actions):
- `searchMentions(q, page)`, `searchUserDocuments(q, page)`, `searchMyResearch(q, group, page, sort, variable)`, `searchMyCerebro(q, page)`. Each returns `{items[], hasMore}`.
- `getResearchVariables(group)`, `attachReference(id, source)`, `detachReference(id, source)`, `set('question')`, `set('selectedAgentId')`.
- `get('conversationId')`, `get('attachedReferences')`, `call('refreshConversationList')`, `contextCharCount`.
- `loadToolDetail(messageId, round, idx)`, `loadCloneScript(messageId)`, `recordWithClone(messageId, profileId, script)`.

**Livewire browser events:**
- `update-url {conversationId}` updates `?c=`.
- `show-trace {trace}`, `copy-clean-script-result {text,error}`.
- `avatar-clone-result {status,message,errorCode}` (`errorCode==='insufficient_credits'` opens the recharge panel).
- `avatar-clone-confirm {messageId, profiles, selectedProfileId}`, `avatar-clone-script {text, fallback, error}`.
- Window event `conversations-updated {conversations}`.

Init data comes from `<script id="ragchat-init-data">` with `{conversations, actionAgentMap{roteiro:<agentId>,…}, roteiroAgentId}`. Deep links: `?cite_viral={id}` pre-inserts a mention tag for a library item (`source:'result'`), and `?cite_profile={id}` does the same for a research profile (`source:'search'`).

---

## 2. Realtime

### 2.1 Pusher / Laravel Echo (legacy floating `aiChat` widget only)
- `new Echo({ broadcaster:'pusher', key:'75830eeb9f5ab6e769a8', cluster:'us2', forceTLS:true, wsHost:'ws-us2.pusher.com', wsPort/wssPort:443, enabledTransports:['ws','wss'], authEndpoint:'/broadcasting/auth' })`. This is the public app key and is visible in the bundle.
- It connects only while the widget is open (`toggleChat`) and disconnects when closed.
- **Channel:** `private-chat.{app_env}.user.{user_id}` (Echo `.private('chat.{env}.user.{id}')`).
- **Event:** `.nova-mensagem`, a custom broadcastAs name (the leading dot disables namespacing). The payload is searched recursively for the first of `assistant_message` → `response` → `result.response` → `mensagem.mensagem` → any nested string. If the string looks like `{name:…,id:…}`, it renders as a file chip.
- Livewire's Echo bridge is present, so components can declare `echo:`/`echo-private:` listeners. None are visible in these scripts, and Blade may declare them.
- Livewire adds an `X-Socket-ID` header when `window.Echo` exists.
- **Headline/roteiro generation does NOT use websockets in these scripts**: it is all polling (§0.3).

### 2.2 SSE streaming (main RAG chat, `/dashboard/user/chat`)
The client uses `fetchEventSource` (`openWhenHidden:true`, an AbortController per stream, and a `streamId` guard). Events:

| Event | Data | UI effect |
|---|---|---|
| `token` | `{text}` | Appends to `streamedText`, re-renders markdown (`marked`) with a 40 ms debounce, and converts action-button markup |
| `progress` | `{message}` | Typing text shown while no tokens have arrived |
| `rag_step` | `{tool, status:'start'\|'done', data}` | Step timeline (labels in §4.6) |
| `tool_start` / `tool_end` | `{name}` / `{name, duration_ms}` | Step timeline |
| `refining_start` / `refining_end` | `{label}` | Step "{label}..." |
| `review_start` | `{reviewer_id, reviewer_name, reviewer_description, attempt, max_attempts}` | "Analisando: {name}" |
| `review_end` | `{reviewer_id, approved, feedback, duration_ms, metadata}` | "Aprovado: {name}" / "Reprovou: {name}" |
| `review_retry` | `{attempt, max_attempts, reason}` | "Refazendo texto (tentativa a/m)" and clears the streamed text |
| `review_warn` | `{reviewer_id, reviewer_name, feedback}` | "Aviso: {name}" |
| `completed` | `{message, message_html, message_id, conversation_id, context_chars}` | Final message. Sets `?c=`. Context warning when `context_chars > 600000`. Calls `refreshConversationList` |
| `error` | `{message}` | "Erro ao processar." The refining step becomes "Revisão bloqueada" |

This shows a **multi-agent pipeline with reviewer agents** (generate → N reviewers approve/reject → retry up to `max_attempts`). It is a key architectural element to replicate.

---

## 3. Feature flows

### 3.1 Generate headlines (modal `#modal-make-headlines`)
1. **"Falar sobre" radio `who`.** Values seen in the JS:
   - `ai` ("pensar por mim": forces subject `all` and hides `.thinkForMe`)
   - `choose` (shows a custom-subject textarea `.divCustomSubject`)
   - `viral` (shows the viral-topics TomSelect `#make-headlines-viral-topics`)
   - `public`, `me`, `search` (comment: "public, me, search, etc.")
   - `subject-moment` ("assunto do momento": hides advanced options, sends `add_input=2`, and returns a list of trending subjects to pick from)

   A secondary radio `who-choose` overrides `who` when present. Every change re-fetches the subject options via `GET /dashboard/user/variables/type/{who}`. Placeholders:
   - "Selecione o assunto que deseja gerar"
   - loading: "Carregando assuntos…"
   - error: 'Não foi possível carregar. Tente alterar "Falar sobre" acima.' with the disabled option "Erro ao carregar a lista de assuntos."
2. **Subject (assunto/variável) multi-select** `#make-headlines-select-variables-user`. Disabled options cannot be picked (plan/availability gating is rendered server-side). Choosing `all` inserts a textarea `input_user`, labelled "Sobre o que você deseja falar:" with placeholder "Digite o assunto", and hides `.input_two`.
3. On subject change → `POST get-profile` suggests **reference profiles** (Instagram profiles from the user's "Pesquisa"). If none match, the option is "Nenhum perfil compatível encontrado".
4. **Reference profiles** TomSelects (`#make-headlines-profiles`, `#make-headlines-profiles-me-public`): `maxItems: 2`, free creation allowed. New entries are sent as `new:<handle>`, rendered as "Adicionar **x**…".
5. **Video formats** TomSelects (`#make-headlines-format-videos[-me-public]`): fixed list from Blade, no creation.
6. **Advanced options** toggles (`#set_headlines_categories`, `#set_headlines_categories-2`) show/hide `#j_make_headlines_advanced_options[_me_public]`. They contain `window.tomSelects` (category filters: hook/structure categories rendered by Blade) and a **range slider `#customRange`** (most likely the quantity of headlines; min/max come from Blade, with a gradient fill of #0054A6). Hiding the panel clears its selects. "Limpar campos" (`.j_make_headlines_clear_fields`) clears everything.
7. **Submit.** There are three forms:
   - `form#make-headlines-viral` → `store-custom-subject` (button "Gerar Headlines", loading "Gerando Headlines...", overlay "Gerando suas Headlines... / Isso pode levar alguns segundos")
   - `form#make-headlines-me` → `store` ("Aguarde criando...")
   - `form#make-headlines-intelligent-search` → `store` ("Buscando..." / overlay "Buscando suas Headlines...", button "Buscar Headlines"). This is the "busca inteligente" over existing headlines.
8. **Subject-moment two-step.** The response is `type:'subject_action'` with HTML radios `subject_selected`. "Próximo" (`#make_headlines_button_subject_moment_next`) requires a selection ("Selecione um assunto para continuar."), then shows the TomSelect step (`…_tom`), then "Gerar" (`…_make`). "Voltar" returns to the form.
9. **Result.** Generation is async. The list page shows a generation row; `.j_headlines_view` opens `#modal-view-headline` with `headline_preview` (server-rendered list; each item carries like / box / roteiro buttons) and the request `payload` JSON (debug tab). Few-results warnings:
   - If `structure_count < 5 && headline_count < 10`: "Foram geradas poucas headlines porque há poucas estruturas compatíveis com as opções selecionadas. Ajuste os filtros e gere novamente para obter mais variações."
   - If both are 0: "Nenhuma headline foi gerada porque não há estruturas compatíveis com as opções atuais. Ajuste os filtros e gere novamente para ver resultados."

   **Inference:** headlines are produced by filling **structures** (templates with variables) that match the filters. The count of compatible structures caps the output.
10. **Per-headline actions:**
    - **Favoritar** (`like`/`unlike`, keyed by `structure_id + headline text + headline_id`)
    - **Adicionar na Box** (`box-headlines/add`)
    - **Reprocessar** the generation (`reprocess/{id}`)
    - **Excluir**
    - **Criar roteiro**: from a favorite → `#modal-favorites-make-roadmap` (simple) or `AdvancedRoadmapModal.open(id, headline)` (advanced)
    - **Editar favorita**: modal with tabs, "Roteiro" active by default; the `roadmap` field appears only if one exists
    - **Copy**: Blade-side
11. **Sugeridas ("Headlines sugeridas do dia")**: triggered on page load via `generate-sugeridas-day`. These are stored in `eng_reversa_headlines` ("engenharia reversa" = headlines reverse-engineered from viral content). Their roteiros save with `save_to=eng_reversa_headlines` and update via `updateSuggested`.

### 3.2 Roteiro — simple creation
1. From a favorite (`.j_headlines_favorites_make_roadmap`): hidden `headline` (URI-encoded in the attribute, decoded on submit), `structure_id`, `headline_id`. Alternatively, on the Roteiros page, pick a headline in `#customer-headlines-select-headline` (option data: `structureId`, `headline`), which adds hidden inputs.
2. Optional **agent** select `#customer-headlines-select-agents` → `get-question-roadmap` → agent-specific questions, each a required text answer ("Digite sua pergunta aqui..."). Or, for a favorite, `favorites/get-questions` with the label "Responda as perguntas abaixo para otimizar o roteiro :".
3. Optional **Segundo Cérebro / crenças** selects (`select-core-brains`, `favorites-select-core-brains`, `favorites-select-core-beliefs`).
4. Submit: "Gerando roteiro..." / "Aguarde criando...". On success, `#modal-show-roadmaps` opens and polls `check-progress` every 5 s.
5. **Result:** 1 roadmap gives a modal-lg with the content. More than 1 gives a modal-xl grid "Opção N", one card per option, each with "Ir para o Roteiro" → `roadmaps?open_id=`.

### 3.3 Roteiro — view / edit (`#modal-customer-roadmap-edit-roadmap`)
- **Tabs:** "Roteiro" (`#roadmap_finale`, Quill editor with bold/italic/underline, ordered/bullet lists and clean; placeholder "Digite seu texto aqui..."), "Payload" (Prism JSON), and "Fontes" (`#tab-search-sources`, shown only when `search_text` is non-empty).
- **`search_text` format:**
  - `=== Title ===` becomes h3, and `--- Sub ---` becomes h4
  - `[t](url)` becomes a link, and `**b**` becomes bold
  - `• item` becomes a list item
  - This is the research dossier assembled by the backend.
- **Copy:** the copy button uses `quill.getText()` ("Roteiro copiado com sucesso!", empty: "Nada para copiar! O roteiro está vazio."). A native copy event converts the selection to **Markdown** (custom htmlToMarkdown: `**`, `*`, `__`, lists).
- **Save:** `roadmaps/update` (button "Atualizar", "Aguarde atualizando...").
- **Feedback:** 👍/👎 (`setFeedback`).
  - Like: "Que bom que você gostou! 🎉  Sua opinião nos ajuda a continuar melhorando. 😊"
  - Dislike: "Obrigado pelo seu feedback! 🙏  Vamos trabalhar para melhorar sua experiência.", which opens a reason textarea → `set/reason`.
  - `roadmap_liked===0` shows the buttons; otherwise the message is shown.
- **Reprocessar** (`.j_reprocess_roadmap`): closes the modal and calls `AdvancedRoadmapModal.openForReprocess(currentRoadmapViewData)`. That pre-fills headline (editable), observations, core, viral video badge and source links, and sets `is_reprocess=1`. Title: "Roteiro reprocessado: {headline≤60}…". Prior Serper/link sources are converted to the "links" source type. Without an open roadmap: "Abra o roteiro antes de reprocessar."
- **Modo chat** (`#start_roadmap_chat_button`) → `chat/start` with `resource_type='user_roadmaps'`. Error: "Roteiro não encontrado para iniciar o modo chat." / "Não foi possível iniciar o modo chat."

### 3.4 Roteiro Avançado — "Opções Avançadas" (current 3-step flow)
`AdvancedRoadmapModal.open(headlineId, headlineText, editable=false)`, `openWithCustomHeadline(text)` (free headline, editable) and `openForReprocess(data)`.

Defaults on open:
- Title "Roteiro Avançado", AI provider `claude`
- `save_to` from hidden `#saveToTable` (default `user_roadmaps` in steps, `eng_reversa_headlines` in other contexts)
- `currentStep=1`, observations cleared, source reset to **`none`**
- core cleared, video cleared, links reset to 1 empty field
- The "Criar Roteiro" button appears once a source is selected

Steps (the step navigation itself is in Blade; the JS holds the state):
- **Step 1 – Headline + instruções:** `#advancedRoadmapHeadline` (readonly when coming from a headline id; editable for custom/reprocess) and `#advancedRoadmapObservations` (free-text instructions). Validation: "Informe a headline."
- **Step 2 – Contexto:**
  - **Segundo Cérebro** (`#selectCoreForRoadmap` → hidden `core_id`)
  - **Duração** `#roadmapDurationMinutes` (value sent as `duration_minutes`; default `'auto'`; the option list is in Blade)
  - **Vídeo modelo da Biblioteca** (`#btnOpenLibrary` → library picker; the badge `#selectedVideoBadge` shows "title≤50 / {plays} views • {likes} likes" with a clear button)
- **Step 3 – "De onde usar as informações"**, source cards `.roadmap-source-card[data-source]`:
  - `none` = "IA pensar" (the AI uses its own knowledge)
  - `links` = "Usar link específico": up to **4** URL inputs (`MAX_SOURCE_LINKS=4`), "+ adicionar" / "×" remove, toast "Máximo de 4 links." Validation: "Adicione pelo menos um link."
  - `serper` = "Pesquisar dinamicamente" (web search):
    - Query input `#serperQueryInput`, "Pesquisar" (`#btnSerperSearch`); empty query: "Digite o que deseja pesquisar."
    - Checkbox **"Usar PubMed"** (`#serperUsePubmed`): translate the query to English, append `site:pubmed.ncbi.nlm.nih.gov`, then search `gl=us, hl=en`
    - Checkbox **"Quero buscar em português"** (`#serperSearchInPortuguese`): direct search `gl=br, hl=pt-br`
    - **Default** (neither checked): translate to EN (GPT-4o-mini) and search `gl=us, hl=en`. **Searching in English is the default.**
    - Results list: checkbox + title link ↗ + snippet (≤200 chars). Up to **4** selected ("Máximo de 4 links selecionados."), with a selected list and counter badge `#serperSelectedCount`, and "Traduzir resultados" (`#btnTranslateSerperResults`, which fans out translateSearchResults per item: "N resultado(s) traduzido(s)." / "Alguns resultados não puderam ser traduzidos.")
    - Messages: "Nenhum resultado encontrado.", "Erro ao buscar na web. Tente novamente.", "Erro ao traduzir busca. Tente novamente."
    - Validation: "Digite algo e clique em Pesquisar." / "Selecione pelo menos um resultado da pesquisa."
  - Missing source: "Escolha de onde usar as informações (link específico, IA pensar ou pesquisar dinamicamente)."
- **Submit** `submitRoadmapSteps()` → the payload in §1.7 → state `creating` → long polling.

**Creating state (progress UX):**
- An initial fake progress runs 0→18% over 8 s with messages:
  - 'Iniciando processamento...'
  - 'Preparando análise com IA...'
  - 'Carregando dados do vídeo de referência...'
  - 'Processando informações...'
  - 'Aguarde, processamento em andamento...'
  - 'Gerando roteiro avançado...'
- Polling then maps poll#/120 to 18→100%, with status text by poll count:
  - ≤6 'Iniciando processamento...'
  - ≤12 'Processando com IA...'
  - ≤24 'Revisando conteúdo...'
  - ≤36 'Finalizando roteiro...'
  - ≤48 'Quase pronto...'
  - otherwise 'Aguarde, processamento em andamento...'
- If the server reports `use_article`, the client shows `article_message`, or "Buscando artigos específicos sobre {niche}..." / "Buscando artigos científicos confiáveis...". The progress floor becomes 25%, and the message auto-hides after 15 s. The **backend auto-detects a health niche and fetches scientific articles**.
- Timeout: "Timeout: O roteiro está demorando mais que o esperado. Tente novamente."
- Toasts: "Roteiro enviado para processamento!", then "Roteiro avançado criado com sucesso!"

**Result state:**
- `#advancedRoadmapResult` textarea (editable) and the headline shown
- "Fontes" tab (`#sources-tab-li`) when `search_text` is present
- Buttons:
  - **Copiar** ("Roteiro avançado copiado!")
  - **Atualizar Roteiro** (`updateRoadmap` → `updateRoadmap` route with `roadmap_id`, otherwise `updateSuggested` with `headline_id`; "Salvando..."; error "Nenhum ID disponível para atualizar (roteiro ainda não foi salvo ou contexto desconhecido).")
  - **Copiar fontes** ("Fontes copiadas para clipboard!")
  - **Modo chat** (`openChatMode` → `startChatMode(id, roadmap_source)`; "Nenhum roteiro disponível para o modo chat. Gere um roteiro primeiro.")
  - **Recriar** (`recreateRoadmap`, back to the form; the button label is "Criar Roteiro Padrão")
- On open, `checkExistingRoadmap(headlineId)` (GET show) jumps straight to the result if a completed roteiro already exists. There is one advanced roteiro per suggested headline.

**Legacy/alternate flows (still exported; they may be active in other Blade variants):**
- **Main options:**
  - `manual` ("Escrever Informações Diretamente" → `simpleObservationsText`, mode `simple`, required: "Por favor, adicione suas observações antes de continuar")
  - `auto` (manual Serper search boxes: "Busca N", input "Digite sua busca:", placeholder "Ex: estudos sobre testosterona, benefícios do jejum intermitente...", up to 3 auto-suggestions "💡 Sugestões:" built from the headline — the headline itself, "benefícios {w1} {w2}", and "estudos científicos {w1}" if the topic is health — with ≤2 selected links per query, "Faça pelo menos uma busca antes de continuar")
  - `library`
- `advanced` sub-option disabled: "Esta opção está temporariamente desabilitada. Use "Escrever Informações Diretamente" para criar seu roteiro."
- **Search provider cards:**
  - `perplexity` (purple)
  - `gpt` "GPT Search" (blue)
  - `gpt-deep` "GPT Deep Research [EXPERIMENTAL]" (orange)
- Search type: `resumo` ("Resumida") or `completo` ("Completa", the default).
- `enable_review` checkbox (a separate AI review pass).
- **AI-planned research** (`list-search`), with loading messages every 2 s:
  - 'Entendendo a busca necessária para seu roteiro...'
  - 'Preparando queries de pesquisa...'
  - 'Buscando informações relevantes...'
  - 'Extraindo links e informações...'
  - 'Organizando resultados por categoria...'
  - 'Quase pronto!'
- Results are grouped per category (`item_pt`, `descricao`, badge "N links encontrados", "x/2 selecionados", "Traduzir" when `idioma ∉ {pt, br}`). Limit: **2 links per category**. Continuing without selections is allowed.
- **Questions mode:** `generateQuestions` gives strategic questions; all are required ("Por favor, responda todas as perguntas antes de continuar"). Toast "Perguntas geradas! Responda para personalizar seu roteiro."
- Audio guard: "Aguarde o processamento do áudio terminar antes de continuar". **Voice-dictated observations** existed (`#audioProcessingStatus`).
- States: `form`, `generating_questions`, `questions`, `loading_links`, `select_links`, `creating`, `result`.

### 3.5 Viral library picker (inside the advanced modal)
- `open()` fades out the form and loads `/dashboard/user/library/videos`.
- **Filters panel** ("Mostrar Filtros"/"Esconder Filtros"):
  - search (Enter applies; matches the transcription, comma-separated terms, accent-insensitive)
  - format (`#filterFormat`)
  - profile (TomSelect single, "Selecione um perfil...", auto-applies)
  - views min, likes min, niche (`#filterNiche`)
  - Active-filter count badge and "Limpar Filtros".
- **Grid card:**
  - thumbnail (fallback `ui-avatars.com` purple #ae3ec9)
  - title (≤60)
  - plays/likes/comments formatted as k/M (1 decimal)
  - format badge
  - search snippet: label "Título" or "Trecho da transcrição" with ±120 chars of context and `<mark>` highlight
- Results count `#libraryResultsCount`.
- Empty states: "Nenhum vídeo encontrado com estes filtros. Tente ajustar os critérios." / "Nenhum vídeo viral encontrado na biblioteca."
- Error: "Erro ao carregar vídeos da biblioteca. Tente novamente." with a "Tentar Novamente" button.
- Click sets the hidden `selectedViralVideoId`, closes the picker, and shows the badge.

### 3.6 AI chat (`/dashboard/user/chat`, Livewire + Alpine `ragChat`)
- **Agents:** `selectedAgentId`; `actionAgentMap` maps actions (e.g. `roteiro`) to agent ids.
- Conversations sidebar (rename/delete confirm `deleteConfirm{open,id,title,busy}`), with `?c=<conversationId>` in the URL.
- **@-mentions** (typing `@` opens a modal) with tabs:
  - `references` (configured references/structures)
  - `documents` (user RAG documents, with upload/drag-drop and a 3 s status poll)
  - `research` (Pesquisa results: group filter default **"Meu Público"**, a sort filter (default `recent`), and a variable filter)
  - `cerebro` (Segundo Cérebro; only for the roteiro agent)
- Multi-select, then tags `@[Title]` are inserted into a contenteditable input. These are sent as `attached_reference_ids[{source:'config'|'result'|'search'|'rag_document'|…, id}]`.
- **Voice input** via Web Speech API (pt-BR, continuous) with a waveform visualizer.
- **Assistant action tokens** inside messages: `{{action:<name>|k=v|k=v}}` render as buttons:
  - `roteiro`: "Criar roteiro a partir desta headline" sends `Crie um roteiro para a headline: "{headline}" (estrutura_id: {id})` to the roteiro agent
  - `roteiro_edit`: "Criar roteiro com headline editável" pre-fills the input instead
  - `select_reel`: "Usar este reel como base" sends `Quero usar o reel {reel}: "{caption}"`
  - fallback: `Execute ação {name}: {json}`
- **Trace viewer** ("show-trace"): `rounds[].tool_calls`, `usage{prompt_tokens, completion_tokens, total_tokens}`, `rag_steps[]`, lazy `loadToolDetail`, and a JSON tree.
- **"Copiar roteiro limpo"** (`copy-clean-script-result`): an AI-cleaned script for teleprompter use.
- **Avatar clone video ("Gerar vídeo")** in 2 steps:
  - `script`: an AI-cleaned script, editable. Fallback warning: "Não deu pra limpar o roteiro com IA — revise o texto antes de gerar."
  - `avatar`: pick a clone profile, then `recordWithClone`.
  - If `insufficient_credits`, the **recharge panel** opens (credit packages, has-card check, "Faturamento" link).
- Typing phrases (rotating every 3 s): "Analisando sua pergunta", "Buscando nos documentos", "Consultando a base de conhecimento", "Processando na fila", "Quase la".
- Context-size warning store `contextWarning` when context exceeds 600k chars.

### 3.7 Legacy floating aiChat widget
`aiChat` handles text, a file (pdf/txt/doc/docx/odt/rtf; error "Tipo de arquivo não permitido. Por favor, selecione apenas arquivos PDF, TXT, DOC, DOCX, ODT ou RTF.") or recorded audio (webm) → `task_id`, with the reply over Pusher. Errors: "Desculpe, ocorreu um erro 😔", "Desculpe, ocorreu um erro ao enviar o áudio: …", "ID de processamento não recebido", "Tempo limite excedido", "Resposta vazia recebida do servidor".

---

## 4. Enums, labels and verbatim texts

### 4.1 Enums (wire values)
- `who` (Falar sobre): `ai`, `choose`, `viral`, `public`, `me`, `search`, `subject-moment` (UI labels are in Blade)
- `add_input`: `1` (choose variables/structures), `2` (free text / subject of the moment)
- `save_to` / resource_type: `user_roadmaps`, `eng_reversa_headlines`
- `mode`: `steps` (current), `default`, `simple`; the questions variant has no mode
- `roadmap_source_type`: `none`, `links`, `serper`
- `ai_provider`: `claude` (default; others are possible from Blade)
- `search_provider`: `perplexity`, `gpt`, `gpt-deep`
- `search_type`: `resumo`, `completo`
- `duration_minutes`: `auto` (default) or a number (options in Blade)
- Advanced status: `completed` and others (pending/processing)
- Roadmap feedback: `1` liked, other (e.g. `2`/`-1`) disliked, `0` none
- Library filters: `format_video`, `profile`, `views_min`, `likes_min`, `niche`, `transcription_search`
- Chat reference sources: `config` (default), `result` (viral library item), `search` (research profile), `rag_document`/`document`, plus the cerebro items
- Mention tabs: `references`, `documents`, `research`, `cerebro`
- Research group default: `Meu Público`; sort: `recent`
- Chat action tokens: `roteiro`, `roteiro_edit`, `select_reel`
- Clone steps: `script`, `avatar`

### 4.2 Limits
| Limit | Value |
|---|---|
| Reference profiles per generation | 2 |
| Source links (advanced steps) | 4 |
| Serper selections | 4 |
| Links per AI-planned category (legacy) | 2 |
| Advanced polling | 2 s first, then every 5 s × 120 (10 min) |
| Simple roteiro polling | every 5 s, no cap |
| Legacy AI status polling | every 1 s × 180 |
| Chat doc upload | pdf/docx/txt/md/csv, ≤20 MB |
| Chat context warning | 600,000 chars |
| Snippets | 200 chars (Serper), 150 (planned search), 120 (selected) |
| Title truncation | 60 (cards), 50 (badge) |
| Roteiro `name` | ≤255 |
| Search suggestions | 3 max; headline ≥10 chars |

### 4.3 Buttons / headings (verbatim)
"Gerar Headlines", "Gerando Headlines...", "Buscar Headlines", "Buscando...", "Aguarde criando...", "Adicionar na Box", "Aguarde adicionando...", "Criar Roteiro", "Gerar Roteiro", "Gerando roteiro...", "Ir para o Roteiro", "Opção {n}", "Atualizar", "Aguarde atualizando...", "Aguarde reprocessando...", "Salvar", "Aguarde salvando...", "Roteiro Avançado", "Roteiro reprocessado: …", "Criar Roteiro Padrão", "Atualizar Roteiro", "Salvando...", "Pesquisar", "Traduzir", "Traduzindo…", "Busca {n}", "Mostrar Filtros", "Esconder Filtros", "Limpar Filtros", "Tentar Novamente", "Adicionar <x>…", "Todas".

### 4.4 Toasts / messages (verbatim, not already quoted above)
- "Ocorreu um erro ao reprocessar a Headline." · "Ocorreu um erro ao adicionar na Box." · "Ocorreu um erro ao gerar Headlines." · "Ocorreu um erro ao buscar Headlines." · "Ocorreu um erro ao favoritar a Headline." · "Ocorreu um erro desfavoritar a Headline." · "Ocorreu um erro ao atualizar a Headline." · "Ocorreu um erro ao criar o roteiro." · "Ocorreu um erro ao gerar o roteiro." · "Ocorreu um erro ao salvar a pesquisa." · "Ocorreu um erro ao reprocessar o roteiro." · "Ocorreu um erro ao salvar as Headline."
- "Roteiro copiado com sucesso!" · "Não foi possível copiar o conteúdo."
- "Roteiro avançado enviado para processamento! Aguarde a conclusão." · "Erro ao criar roteiro." · "Erro ao criar o roteiro avançado" · "Erro ao gerar perguntas. Tente novamente." · "Erro ao verificar status do roteiro" · "Erro ao buscar links. Tente novamente." · "Erro ao buscar links na internet" · "Nenhum resultado encontrado" · "Erro: dados do roteiro não encontrados" · "Por favor, digite uma headline antes de continuar" · "Por favor, selecione uma opção antes de continuar" · "Digite uma busca antes de pesquisar" · "Nenhum resultado encontrado para esta busca" · "Erro ao buscar na internet. Tente novamente." · "Nenhum resultado para traduzir" · "{n} resultado(s) traduzido(s) com sucesso!" · "Erro ao abrir biblioteca. Recarregue a página."
- Chat: "Conexão perdida. Tente novamente." · "Erro ao processar." · "Revisão bloqueada" · "Não foi possível preparar o roteiro." · "Não foi possível carregar os pacotes de crédito." · "Não foi possível processar a recarga." · "Erro inesperado ao recarregar." · Doc upload: "Formato não suportado. Use PDF, DOCX, TXT, MD ou CSV." · "Arquivo maior que 20MB." · "Falha no upload." · "Erro de rede no upload." · "Processando…"

### 4.5 Embedded prompt templates (client-side)
- `Crie um roteiro para a headline: "{headline}" (estrutura_id: {id})`
- `Quero usar o reel {n}: "{caption}"`
- `Execute ação {action}: {json}`
- PubMed query suffix: ` site:pubmed.ncbi.nlm.nih.gov`
- Search suggestions: `benefícios {w1} {w2}` · `estudos científicos {w1}`

All real LLM prompts are server-side. The client only reveals their **inputs** (§1.7).

### 4.6 RAG agent tool names / labels (verbatim; this reveals the backend agent toolset)
`toolLabels`:
- search_documents "🔍 Buscando nos documentos internos"
- search_headline "📋 Buscando estruturas de headline"
- search_headline.avaliar "🤖 IA avaliando estruturas para o contexto"
- search_web "🌐 Buscando na web"
- fetch_instagram_profile "📸 Buscando perfil do Instagram"
- fetch_instagram_reels "🎬 Buscando reels do Instagram"
- search_web.niche "🏥 Nicho saude detectado → PubMed"
- search_web.disambiguating "🔎 Identificando assunto (termo vago)"
- search_web.disambiguated "✅ Assunto identificado"
- search_web.results "📋 Resultados encontrados"
- search_web.scraping "📄 Extraindo conteudo da fonte"
- search_web.scrape_failed "⚠️ Fonte inacessivel"
- nucleo_influencia "👤 Consultando nucleo de influencia"
- consultar_gatilhos "⚡ Estudando gatilhos da atencao"
- buscar_estruturas "📚 Buscando estruturas de headlines"
- buscar_estruturas.avaliar "🤖 IA selecionando melhores estruturas"
- consultar_variaveis_perfil "📊 Consultando variáveis do perfil"
- consultar_estruturas_perfil "🧬 Consultando estruturas do perfil"
- criar_headline "✍️ Criando headline"
- criar_headline.gerar "🎯 Gerando 5 variações"
- criar_headline.qa "🔬 QA selecionando a melhor"
- consultar_pesquisa_viral "🔥 Consultando pesquisa viral"
- gerar_headlines "✍️ Gerando headlines"
- gerar_headlines.generate "🎯 Gerando headlines candidatas"
- gerar_headlines.qualify "🔬 QA — selecionando as melhores"
- qualificar_headline "🔬 Qualificando headline (QA)"
- pesquisar_materia_prima "🧠 Pesquisando materia-prima"
- estruturar_roteiro "📝 Estruturando roteiro"
- refinar_copy "✨ Refinando copy"
- avaliar_qualidade "📊 Avaliando qualidade"

`toolClassMap` (backend PHP classes):
- SearchHeadlineDocsTool, SearchWebTool, ConsultarNucleoInfluenciaTool, ConsultarVariaveisPerfilTool, ConsultarEstruturasPerfilTool, CriarHeadlineTool, ConsultarPesquisaViralTool, GerarHeadlinesTool, SearchMarketingProcessTool
- Sub-steps FindTemplates / ValidateTemplates / FindVariables / ValidateVariables / FindTriggers / ValidateTriggers

`toolNameLabel` adds: list_documents_tool "Listando documentos", salvar_memoria_tool "Salvando na memória", esquecer_memoria_tool "Apagando da memória", avaliar_qualidade_conteudo_tool "Avaliando qualidade do conteudo", consultar_nucleo_influencia_tool "Consultando perfil do cliente".

**What the tools reveal about the headline pipeline:**
1. Find **templates** (structures)
2. Validate templates against the context
3. Find **variables** (subjects/profile variables)
4. Validate the variables
5. Find **triggers** (gatilhos da atenção)
6. Validate the triggers
7. Generate candidates (5 variations)
8. Run a **QA/qualify** step that picks the best

**Roteiro pipeline:** pesquisar matéria-prima → estruturar roteiro → refinar copy → avaliar qualidade, with reviewer agents and retries. The agents also have **long-term memory** (save/forget) and **Instagram profile/reels fetch**.

---

## 5. UI states, gating, credits
- **Loading:**
  - modal overlay `.modal-loading-overlay` (spinner + h5 + "Isso pode levar alguns segundos")
  - buttons disabled with spinner text
  - TomSelect wrapper dimmed (opacity .72, no pointer events) while loading subjects
  - library `#libraryLoadingState`
  - Serper `#serperLoadingState`
  - per-search-box "Buscando na internet..."
- **Empty:** library and Serper (`#serperEmptyState`), "Nenhum perfil compatível encontrado", hidden question containers.
- **Plan/availability gating:** server-rendered `disabled` `<option>`s in subject lists (greyed, not selectable, `cursor:not-allowed`). Any plan or credit refusal on generation would come back as an envelope `type:'error'` toast (no client-side checks are present). **Credits** appear explicitly only in the chat clone-video flow (`insufficient_credits` → recharge packages / Faturamento).
- **Few-results warning** in the headline view (§3.1 step 9).
- **Feedback states** on the roteiro (§3.3).

---

## 6. Inferred data model

**User / Workspace:** `user_id`, `workspace_id` (meta, default 3), `app_env`; credits balance; payment method; credit_packages.

**Customer (agency client; legacy multi-client):** `id`, name; owns structures, variables and boxes.

**Structure (headline template)** — `structures`: `id`, `name`, template text with variable slots, categories (filters), possibly linked triggers and format. It is used as `structure_id` on generated headlines and favorites.

**VariableType / Variable (subjects, "assuntos")**: `variable_type_id`, `variables` (per user or customer and per `who` context); `values` (`get-variables-values`). There are also profile variables (`consultar_variaveis_perfil`).

**HeadlineGeneration** (`user_headlines`, one per run): `id`, `user_id`, `who`, `add_input`, `input_user`, selected variables/subjects, viral topics, reference profiles (search ids or `new:handle`), video formats, category filters, quantity (slider), `payload` (JSON of request + params), `status` (async), `structure_count`, `headline_count`, rendered `headline_preview` (list of generated headlines, each `{structure_id, text}`).

**FavoriteHeadline** (`headline_favorites`): `id`, `user_id`, `headline_id` (source generation), `structure_id`, `headline` text, `roadmap` text (optional attached roteiro), plus questions via `favorites/get-questions`.

**SuggestedHeadline** (`eng_reversa_headlines`): `id`, `user_id`, `headline`, `roadmap` (advanced roteiro text), `day`/date, plus advanced fields (`roadmap_advanced`, `status`, `search_id`, `search_text`, `use_article*`). These are generated daily per user.

**Roadmap / Roteiro** (`user_roadmaps`):
- Core: `id`, `user_id`, `name` (headline, ≤255), `headline_id`, `structure_id`, `agent_id`, `roadmap_gpt`/`roadmap_content`/`roadmap_advanced` (text/HTML), `status`, `payload` (JSON)
- `params` (JSON): `observations`, `brain_id`/`core_id`, `viral_id`/`viral_video_id`, `roadmap_source_type`, `source_links[]`, `selected_links[]`, `duration_minutes`, `ai_provider`, `mode`, `search_provider`, `search_type`, `enable_review`, `use_pubmed`, `serper_query`, `serper_search_in_portuguese`, `is_reprocess`
- Q&A: `questions[]`/`answers[]`
- Research: `search_id` → **Search/Research** record with `search_text` (sources dossier)
- Feedback: `roadmap_liked` (0/1/2), `reason_unliked`
- Source: `source` (`suggested`|`favorite`) + `source_id` (deep link back)

**Agent (roteiro agents):** `id`, name, `questionRoadmap[{question}]` (pre-generation questions), the role in `actionAgentMap` (`roteiro`, …), and reviewers (`reviewer_id`, `name`, `description`) with `max_attempts`.

**Core / "Segundo Cérebro" (cores, brains, beliefs):** `id`, name, content (knowledge base about the creator: beliefs ("core-beliefs"), positioning). It is used as `core_id`/`brain[]` and in the chat `cerebro` mention tab.

**Pesquisa (audience research) / Search:** `search_id`, `profile` (Instagram handle), group (`Meu Público`, …), variables, results. It is linked to subjects via `get-profile` and used as the chat `research` mention and `cite_profile` source. The "núcleo de influência" (client profile) tool implies a **Profile/Nucleus** entity with variables and structures per profile.

**ViralVideo (Biblioteca):** `id`, `title`, `description`, `thumbnail_url`, `plays`, `likes`, `comments`, `format_name`/`format_video`, `profile`, `niche`, `transcription_text`. It is used as `viral_video_id` (reference model) and in the chat `cite_viral`.

**BoxHeadline (per-customer weekly collection):** `customer_id`, `headline_week_id` (week bucket), headline items.

**RAG Document:** `id`, `title`, `meta`, `status` (`pending`/`processing`/ready), `ready`.

**Chat:**
- Conversation: `id`, title, agent, attached references, `context_chars`
- Message: `id`, role, content, `message_html`, trace `{rounds[{tool_calls[]}], usage, rag_steps[]}`
- `memory` (save/forget tools)
- Clone profiles for avatar video (`id`, …); video generation consumes credits

**AI task (legacy):** `task_id`, `status`, `status_message`, `progress`, `response`, `error`.

---

## 7. Things not visible here (they come from Blade/server; capture them next if needed)
- The exact option lists for: "Falar sobre" labels, video formats, category filters, the slider min/max, duration minutes, library format/niche options, the agent list, cores, and the provider list for `ai_provider`.
- `window.showProgressAnimation` (headline generation progress) and the step navigation UI of the advanced modal (step 1→2→3 buttons).
- `headline_preview` HTML (per-headline buttons/markup) and `box_headlines` HTML.
- All server-side prompts. The tool and step names in §4.6 give the pipeline skeleton.
- Pages for Pesquisa (extract from profile), Segundo Cérebro CRUD, Treinamentos, and Minha Biblioteca have no scripts in this folder.
