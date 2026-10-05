# Spec — Pesquisa & Segundo Cérebro

The full build spec for Minha Pesquisa, Extrair Pesquisa and Segundo Cérebro. §0–§8 were rebuilt from the saved page code; §9 is what the live session on 2026-10-05 confirmed or corrected, and **§9 wins wherever they differ**. Tags: **\[OBS\]** seen in code or markup · **\[INF\]** inferred · **\[LIVE\]** to be checked in the browser. pt-BR strings are verbatim. The raw markdown is attached here: spec-pesquisa-cerebro.md.

## 0 · Cross-cutting conventions

**Stack \[OBS\].** Laravel Blade (server-rendered) + Tabler/Bootstrap 5 modals + jQuery + vanilla `fetch` + `toastr` + TomSelect multi-selects. Forced dark theme. `<base href="/">`, so relative URLs resolve from root. CSRF meta sent as an `X-CSRF-TOKEN` header; some FormData posts append `_token`. **No Livewire on these three screens** (the chat page uses Livewire to *read* this data).

**Response envelopes \[OBS\]** — three styles coexist; a rebuild should normalise to one:

1. `{ success, message, ...payload }` (newer endpoints)
2. `{ type: success|error|info|warning, message }` read by `toastr[data.type](data.message)`, with optional `button`, `redirect` (navigate after 1s), `refresh`, `reset`
3. Laravel `422 { errors: {field: [msg]} }`, each message toasted. Generic fallback: `Erro ao processar a solicitação.`

## 1 · Minha Pesquisa (`GET /dashboard/user/searches`)

One flat, filterable list of research items: short text values attached to a **variable** (e.g. *Medos do meu público*), each **Aprovado** or **Pendente**, optionally linked to a viral video with its view count. They feed headline/roteiro generation and the chat's research mentions.

### 1.1 Layout \[OBS\]

- Header: H2 `Minha Pesquisa`, P `Gerencie suas variáveis de pesquisa para criar headlines inteligentes.`, button `+ Adicionar itens a pesquisa` → `openAddItemModal()`.
- Card `form#save-variables` with panes `#my-research` (active, the list) and `#subject-viral` (hidden, *Assuntos Virais*, only via `?tab=subject-viral`). No visible tab nav between them.
- Legacy, never shown: `#pending-variables-alert` (*Itens pendentes de salvar*), `#global-variables-loading` (*Carregando variáveis...*), footer `Atualizar` → `POST /searches/save`. **Do not rebuild.**

### 1.2 Toolbar \[OBS\]

| Control | Options (verbatim) | Default | Effect |
| --- | --- | --- | --- |
| Sort pills | `Mais Recentes` · `Mais Views` | Mais Recentes | recent = `id` desc; views = `plays` desc (null→0). Active pill gradient `#7c3aed→#9945FF` |
| Status pills | `Aprovados` · `Pendentes` | Aprovados | approved = `approved` + `approved_manual`; pending only. Active Pendentes pill orange `#c2410c→#f97316`. No "Todos" |
| Variable select | `Todas as variáveis` + 33 variables (§5.1) | all | filter by variable; default target of the add modal |
| `Agrupar` | toggle | off | group by variable, **no pagination**, infinite scroll off |
| Count | `N item(s)` | — | — |

Bulk bar (hidden until ≥1 checked): `N selecionado(s)` · `Selecionar todos` ⇄ `Desmarcar todos` (rendered rows only) · `Ações` → bulk modal.

### 1.3 Row anatomy \[OBS\]

Zebra rows. (1) 3×36px accent bar: purple `#9945FF` approved, orange `#f97316` pending. (2) checkbox. (3) content (0.88rem `#e8e0ff`) + meta `«variable» · «Meu Público|Sobre Mim» [· manual] [· 1.234.567 views]`. (4) icons at 35% opacity (90% hover):

- **Pending:** 👁 `Ver na biblioteca` · ✓✓ `Aprovar` · ✕ `Rejeitar`
- **Approved (extracted):** 👁 + 🗑 `Excluir`
- **Approved manual:** 🗑 only

👁 opens a new tab: `/dashboard/user/library?viral_result_id=<id>`, or `?transcription_search=<content>` when there is no source video. Grouped header: label (`#E1C8FF`) + badge `Sobre Mim` (`#7c3aed`) / `Meu Público` (`#0d6efd`) + `N item(s)`.

### 1.4 Loading, empty, error, paging \[OBS\]

Two parallel GETs (`variables/items?type=especialista` and `?type=avatar`), merged client-side. Loading `Carregando itens...`; empty `Nenhum item encontrado.`; error `Erro ao carregar` + `Tentar novamente`. Client infinite scroll, 20 rows per page (IntersectionObserver), off while grouped; any filter change resets to the first 20. Every mutation re-fetches the list, except single delete (removed locally).

### 1.5 Modals \[OBS\]

**Inserir itens na pesquisa** (`#modal-add-item`, 520px):

- Target variable = argument, else the current filter; label shown unless `Todas as variáveis`.
- Tabs: only `Itens`. A `Prompt` tab (edit system prompt, include variables, test, `Salvar prompt`) exists in JS but its markup is absent → role-gated.
- Hint `Cada linha vira um item separado. Pressione [Enter] para nova linha e [Ctrl+Enter] para salvar.`; textarea placeholder `Ex:\nMedo de envelhecer\nAnsiedade com dinheiro\nInsegurança no trabalho`; counter `0 itens` / `1 item` / `N itens`; `Prompt ativo — itens serão processados pela IA` when the prompt is on.
- Footer `Cancelar` · `Salvar itens`. On open: `GET add-item-prompt`. Empty → `Digite ao menos um item.`
- **Mode A, prompt active:** state `Classificando itens com IA...` + progress → `POST add-items-sync {text}` (90s abort) → on timeout `Processando em segundo plano...` / `A resposta demorou mais que o esperado, avisaremos quando terminar` + `POST add-items-job` → poll `GET add-items-job/{id}` every 2s × 300. Result: `«N» itens adicionados com sucesso`, `Ver detalhes` (classified by label), `Não classificados (N)` (content + token); footer `Inserir mais` · `Fechar`. The selected variable is ignored \[INF\].
- **Mode B, prompt off:** one `POST variables/contents/add {id, value}` per line (`Salvando i/N...`) → `N itens adicionados com sucesso!`; items become `approved_manual`. No guard when no variable is selected.

**Ações — N selecionado(s)** (`#modal-bulk-actions`): `Aprovar selecionados` (only under Pendentes; one `approve-pending-item/{id}` per row) · `Excluir selecionados` (confirm, then one `contents/remove {id, source}` per row) · `Zerar toda a pesquisa` / `Remove todos os itens, incluindo os não carregados` (confirm `Você realmente deseja esvaziar TODOS os itens de TODAS as variáveis? Esta ação não pode ser desfeita.` → `contents/empty-all` → `Toda a pesquisa foi zerada!`).

| Confirm modal | Message | Buttons |
| --- | --- | --- |
| `modal-confirm-bulk-delete` | `Você realmente deseja excluir este item?` / `…excluir N item(s) selecionado(s)?` | `Cancelar` / `Excluir` |
| `modal-confirm-empty-variable` | `Você realmente deseja esvaziar todos os itens? …` | `Cancelar` / `Esvaziar` |
| `modal-approved-variable` | `Você realmente deseja aprovar esse topico?` | `Cancelar` / `Aprovar` |
| `modal-rejected-variable` | `Você realmente deseja reprovar este topico?` | `Cancelar` / `Reprovar` |

Orphan modals on the page (no trigger): `#addVariableModal`, `#extractViralProfileModal` (old modal form of Extrair Pesquisa).

### 1.6 Assuntos Virais (hidden pane) \[OBS\]

- Info card `Extrair assuntos virais` → `Extrair Assuntos Virais` modal (profile picker like §2, `vt-` prefix, 12/page, `POST extract-profile {type:'topic_virais'}`, new topics land Pendente \[INF\]).
- Tabs `Aprovado` · `Pendente` + count badge. Aprovado: add input (`Digite um novo assunto viral...`, max 255) + `Adicionar`; pill cloud showing `topic · 2.5M Views` or `Manual` + `×`; `Ver mais` reveals 27 at a time; `Selecionar todos` / `Excluir selecionados (N)` / `Esvaziar`.
- Pendente: orange cards (topic, views, `Pendente`) with ✓✓ approve and 🗑 reject — **GET, no confirmation**; `Aprovar selecionados (N)`; empty `Nenhum item pendente`.
- Click a topic → `Assuntos Virais - «topic»` modal: grid of videos (thumb, Views/Likes/Comments, date) from `GET viral-data/{id}`.

### 1.7 Network — Minha Pesquisa

| Method | URL | Request | Response / use |
| --- | --- | --- | --- |
| GET | `/searches/variables/items?type=especialista\|avatar` | — | `{success, data:{"<varId>":{approved_manual[], approved[], pending[]}}}` |
| POST | `/searches/variables/contents/add` | `{id, value}` | `{type, message, data:{id, content}}` — Mode B |
| POST | `/searches/variables/contents/remove` | `{id, source}` | delete (one per item) |
| POST | `/searches/variables/contents/empty-all` | — | Zerar toda a pesquisa |
| POST | `/searches/approve-pending-item/{id}` | — | approve |
| POST | `/searches/reject-pending-item/{id}` | — | reject |
| GET/POST | `/searches/add-item-prompt` (+ `/test`) | `{prompt_system, is_active, include_variables}` | prompt config (edit UI hidden) |
| POST | `/searches/add-items-sync` | `{text}` | `{saved, classified, unclassified[{content, token}], message}` |
| POST / GET | `/searches/add-items-job` · `/add-items-job/{id}` | `{text}` | job, polled 2s × 300 |
| GET | `/searches/viral-data/{topicId}` | — | `{data:[{plays, likes, comments, post_date, url, thumbnail}]}` |
| GET/POST | `/searches/viral/topics/{approve\|reject\|remove}/{id}`, `/add`, `/bulk-delete`, `/empty` | — | viral-topic CRUD |
| GET | `/searches/approved-profiles` (+ `-viral-topics`) | — | profile catalogue |
| POST / GET | `/searches/extract-profile` · `/extract-profile-status/{job}` | `{type, eng_reversa_search_id}` | extraction job, polled 5s × 60 |

### 1.8 State machine \[OBS statuses / INF transitions\]

```
server extraction ──▶ PENDING ──approve──▶ APPROVED (keeps plays + source video)
                          └──reject──▶ removed (soft delete)
manual add ──▶ APPROVED_MANUAL (no video)
APPROVED / APPROVED_MANUAL ──delete──▶ removed
Zerar toda a pesquisa ──▶ every item of every variable removed
```

Add-items job: `pending → processing → done | error`.

## 2 · Extrair Pesquisa (`GET /dashboard/user/searches/extract-profile`)

Browse a **curated catalogue of viral profiles** the platform has already analysed (the "eng\_reversa" pipeline), filter by niche and profession, open a profile's extracted research (values per variable, each tied to a video, its hook sentence and views), and copy chosen values into Minha Pesquisa. There is no "extract" action on this page: the extraction is precomputed.

### 2.1 Layout \[OBS\]

- Header: H2 `Extrair Pesquisa de Perfil Viral`, P `Selecione perfis aprovados para extrair e adicionar às suas variáveis de pesquisa.`, outline button `← Minha Pesquisa`.
- Card: search `Buscar perfis por nome...` + ✕ clear (`Limpar busca`); `Nichos` and `Profissões` TomSelect multi (`Selecione os nichos...` / `Selecione as profissões...`); `Limpar Filtros`.
- States: `Carregando perfis aprovados...` · `Nenhum perfil aprovado encontrado.` · grid + pagination.

### 2.2 Filters \[OBS\]

- Name: case-insensitive substring on the handle; resets to page 1.
- Nichos / Profissões: match when the profile shares any selected id (OR within a select); the two selects combine with AND.
- **Defaults = the user's own niches and professions** (`GET /profile/get-niches-professions`), applied silently 500ms after init.
- All filtering and paging is client-side over the full list, loaded once.

### 2.3 Profile card + pagination \[OBS\]

- 3 per row, **24 per page**; hover lifts 4px.
- Card: Instagram glyph (generic glyph for other networks) + `@handle`; 3 thumbnails (120px, `object-fit: cover`, grey placeholders to fill 3).
- `Vídeos` (purple `#6d28d9→#7c3aed`, title `Ver vídeos deste perfil`) → new tab `/dashboard/user/library?profile=«handle»`.
- `Pesquisa` (teal `#0d9488→#14b8a6`, title `Ver pesquisa extraída deste perfil`) → the modal below.
- Pagination only when >1 page: ‹ · current ±2 with `1 …` / `… N` · ›, plus `Mostrando a-b de N perfil(is)`; smooth-scroll to the grid on change.
- Filtered-empty: `Nenhum perfil encontrado` + `  com o termo "q" ` / `  com os nichos selecionados ` / `  com as profissões selecionadas ` joined by `e`. Load failure toast `Erro ao carregar perfis. Tente novamente.`

### 2.4 Modal *Pesquisa do perfil @handle* \[OBS\]

- xl, min-width 1000px, body max 70vh scroll. Spinner `Carregando pesquisa...` → `GET /searches/profile-viral-search/{eng_reversa_search_id}`.
- Empty: `Nenhuma extração encontrada para este perfil.`
- Toolbar: `«G» variável(is) · «N» item(s)` · `Selecionar todos` ⇄ `Desmarcar todos` (all groups, even collapsed) · `Adicionar à minha pesquisa` + count (hidden at 0).
- **Groups** (accordion, first open): chevron + label (`#c4b5fd`) + count; sort chips `↓ Views` (default) / `Mais recente` (by video id).
- **Item row**: checkbox (disabled + checked if already added) · 64×64 thumb · value bold `#e9d5ff` (struck through if added) · the sentence(s) of the hook containing the value, value bold, rest dimmed (cut at the nearest `.?!`) · views badge (`1.2M`/`3.4K`) · `Ver vídeo ↗` → `/library?viral_result_id=…` · `✓ Já adicionado`.
- Save: `POST /searches/profile-viral-search/save {items:[{variable_id, content, eng_reversa_result_id, plays}]}` (`Salvando...`) → toast; saved rows become disabled + struck + `✓ Já adicionado`. Errors `Erro ao salvar.` / `Erro ao salvar variáveis. Tente novamente.`
- Footer `Fechar`.

### 2.5 Network — Extrair Pesquisa

| Method | URL | Request | Response |
| --- | --- | --- | --- |
| GET | `/profile/get-niches-professions` | — | `{success, data:{niches:[int], professions:[int]}}` |
| GET | `/searches/approved-profiles` | — | `{success, data:[{profile, social, eng_reversa_search_id, thumbnails[≤3], niche_ids[], profession_ids[]}]}` (whole catalogue) |
| GET | `/searches/profile-viral-search/{id}` | — | `{success, profile, data:[{variable_id, variable_name, label, items:[{result_id, plays, post_link, headline, value, thumbnail, already_added}]}]}` |
| POST | `/searches/profile-viral-search/save` | `{items:[…]}` | `{success, message}` |

### 2.6 Hidden variant — per-profile extraction job \[OBS\]

An older orphan modal still carries an `Extrair` button (hidden) that runs `POST extract-profile {type:'myPublic'|'topic_virais', eng_reversa_search_id}` and polls `extract-profile-status/{job}` every 5s × 60, showing `step` + `progress%`, then `«total» item(ns) extraído(s) | «saved» novo(s) adicionado(s) | «skipped» já existentes`. It is evidence of a server job with steps, progress and de-duplication; the current product replaced it with the precomputed browse-and-pick flow.

## 3 · Segundo Cérebro (`GET /dashboard/user/cores`)

A set of **brains** ("cores"): knowledge documents about the creator, filled by a questionnaire, a document upload or a YouTube transcription. Used as context in roteiros, headlines and the chat's @Cérebro. **§9 has the live-verified editor and questionnaire; this section is the static reading, kept for endpoints and messages.**

### 3.1 List page \[OBS\]

- Header: H2 `Cérebros Personalizados`, P `Segundo cérebro`, `+ Criar Cérebro` (hidden below sm).
- Clickable info banner: thumbnail + `Aprenda a usar o Cérebro Personalizado para turbinar suas postagens!` `Assistir agora.` → video modal `Como usar o Cérebro Personalizado` (Bunny iframe, src cleared on close).
- Cards, 3 per row: badge `Vazio` (`rgba(128,128,128,.3)`) or `Pronto` (`rgba(59,92,255,1)`), H2 name, full-width `Acessar Cérebro` → `/dashboard/user/cores/edit/{id}`. No edit/delete on the cards.
- Owner's cards: Hístoria de Criação (8), Histórias de Vida do Especialista (9), Método do Especialista (14), Núcleo de Influência (3081), Call de diagnóstico (3741), Formulário (4191), Narrativa (4192). The favorites roteiro select lists the same names with other ids (8522, 8772–8775, 9385, 9386) — per-workspace copies or a separate table \[LIVE\].

### 3.2 Create / rename / delete \[OBS\]

| Action | UI | Request | Notes |
| --- | --- | --- | --- |
| Create | `Criar Cérebro Personalizado`: `Tipo de Cérebro:` (`custom`=Personalizado / `beliefs`=Crença) + `Nome do Cérebro:` (`Ex: Reels Instagram`) · `Cancelar` · `Criar Cérebro` (`Aguarde criando...`) | `POST /cores/custom/add` FormData `core_type, name` | 422 → `errors.name[0]`, else `Ocorreu um erro ao criar o núcleo.`; `redirect` → navigate after 1s |
| Rename | `Renomear Cérebro` / `Nome do Cérebro:` · `Atualizar Cérebro` (`Aguarde atualizando...`) | `POST /cores/custom/update` `core_id, name` | type can't change |
| Delete | `Tem certeza? Você realmente deseja deletar este Cérebro?` · `Cancelar` · `Deletar` | **GET** `/cores/custom/delete/{id}` (navigation) | server redirects back \[INF\] |

### 3.3 Editor as read from `brains.js` \[OBS logic\]

The script describes a per-question editor; **the live pages (§9) use a different questionnaire and a markdown content editor**, so treat this as the server contract plus legacy UI:

- Per question: `Prefiro falar` ⇄ `Prefiro escrever`; textarea `response[qid]`; editing shows `Alterações não aplicadas` + a per-question apply button; processing shows `Aguarde, processando resposta!`.
- Voice: record (webm → mp4 → mp3, 128 kbps, `mm:ss` timer, 164-bar waveform), player + delete; upload in **1 MiB chunks** `POST /cores/upload-audio-chunk {audio_chunk, chunk_number, total_chunks, question_id}` → `{success, file}`. Mic error `Erro ao acessar o microfone. Verifique as permissões!`.
- Apply one: `POST /cores/update {core_id, question_id, response[qid], audio[qid]?}`. Apply all (`Aplicar Alterações`): whole form + `typeSubmit=aplica_todos`; error `Ocorreu um erro ao atualizar o cérebro.`
- Upload: `pdf, docx, txt, md, csv`, ≤20 MB (`Selecione um arquivo antes de enviar.` / `Formato não suportado. Use PDF, DOCX, TXT, MD ou CSV.` / `Arquivo muito grande. Limite: 20 MB.`) → `POST /cores/upload-file {core_id, file}` → back to `/cores`.
- Leave guard while recordings are unsent: `Você tem uploads em andamento. Tem certeza de que deseja sair?`

### 3.4 Network — Segundo Cérebro (static + live)

| Method | URL | Request | Response |
| --- | --- | --- | --- |
| POST | `/cores/custom/add` · `/custom/update` | `core_type, name` · `core_id, name` | `{type, message, redirect?, refresh?, reset?}` |
| GET | `/cores/custom/delete/{id}` | — | redirect |
| POST | `/cores/questions/save-draft` · `/questions/store` · `/questions/reset` | form `questions[<qid>]` | store → `{status:'validating'}` (live) |
| GET | `/cores/brain-status/{id}` | — | `{brain_status, validation_status, responses[]}` (live, 3s poll) |
| POST | `/cores/update` · `/upload-audio-chunk` · `/upload-file` | see 3.3 | envelope |
| POST / GET | `/cores/youtube/extract` · `/youtube/status/{job}` | links | job until `status:'done'` (live) |
| POST | `/cores/extract/list` | DataTables params | hidden *Minhas extrações* table (live) |

### 3.5 State machine

```
Brain:     create ──▶ VAZIO ──answers approved / file / transcript──▶ syncing ──▶ PRONTO
Answer:    Aguardando resposta ──Finalizar──▶ Validando... ──▶ Aprovada | Rejeitada (+ motivo)
Validation: pending ──▶ completed | failed      brain_status: syncing ──▶ synced | error
```

## 4 · Data model

| Entity | Fields (type) | Notes |
| --- | --- | --- |
| ResearchVariable | `id` int · `label` · `type` avatar (Meu Público) \| especialista (Sobre Mim) \| null (global) · slug e.g. `DESEJOS-TANGIVEIS-DO-AVATAR` | 33 rows, §5.1 |
| ResearchItem | `id` · `user_id` · `workspace_id` · `variable_id` · `eng_reversa_result_id` (source video, nullable) · `content` · `status` 0 pending / 1 approved · `plays` (string) · `created_at` · `updated_at` · `deleted_at` · `source` content\|pending | two stores leak into the API via `source`; buckets `approved_manual` / `approved` / `pending` |
| ViralTopic | `id` · `topic` (≤255) · `total_plays` · `eng_reversa_result_id` (null = Manual) · status pending\|approved | videos via `viral-data/{id}` |
| ApprovedProfile | `eng_reversa_search_id` · `profile` (handle) · `social` · `thumbnails[≤3]` · `niche_ids[]` · `profession_ids[]` | 485 rows, platform-curated |
| ProfileResearchGroup / Hit | group `{variable_id, variable_name, label, items}`; hit `{result_id, plays, post_link, headline, value, thumbnail, already_added}` | `headline` = the video's hook sentences |
| AddItemPromptConfig | `prompt_system` · `is_active` · `include_variables` | per user or global \[LIVE\] |
| AddItemsJob | `job_id` · `status` · `saved` · `classified{label:[content]}` · `unclassified[{content, token}]` |  |
| ExtractProfileJob | `job_id` · `status` · `step` · `progress` 0–100 · `total_extracted` · `saved_count` · `skipped_count` · `skipped_items[]` | input `{type, eng_reversa_search_id}` |
| Niche / Profession | `{id, name}` | 28 / 102 |
| Brain (Core) | `id` · `name` · `core_type` custom\|beliefs (+ Sistema templates) · status Vazio\|Pronto · content (markdown) · `brain_status` synced\|syncing\|error · `validation_status` pending\|completed\|failed | used as `core_id`, `core[]`, `specific_core_id`, chat @Cérebro |
| BrainQuestion / Answer | `question_id` · text · group (0,1,2…) · answer · status completed\|failed · `rejection_reason` |  |

## 5 · Verbatim taxonomies

### 5.1 Research variables (filter order; ⎵ = trailing space in the source label)

| id | Label | Group |
| --- | --- | --- |
| 18 | Desejos do meu público | Meu Público |
| 17 | Dores do meu público⎵ | Meu Público |
| 16 | Características demográficas do meu público | Meu Público |
| 25 | Qualidades do meu público | Meu Público |
| 26 | Defeitos do meu público | Meu Público |
| 15 | Itens conhecidos pelo meu público | Meu Público |
| 14 | Instituições conhecidas pelo meu público | Meu Público |
| 13 | Pessoas e personagens conhecidos pelo meu público | Meu Público |
| 32 | Inimigos do meu público⎵ | Meu Público |
| 11 | Filmes, séries ou músicas conhecidas pelo meu público | Meu Público |
| 19 | Eventos conhecidos pelo meu público⎵ | Meu Público |
| 20 | Locais conhecidos pelo meu público | Meu Público |
| 21 | Momentos de vida do meu público | Meu Público |
| 10 | Objeções do meu público⎵ | Meu Público |
| 9 | Medos do meu público | Meu Público |
| 8 | Crenças do meu público⎵ | Meu Público |
| 34 | Produtos conhecidos pelo meu público | Meu Público |
| 5 | Desejos e conquistas que eu realizei⎵ | Sobre Mim |
| 4 | Situações dolorosas que eu enfrentei⎵ | Sobre Mim |
| 30 | Meus hábitos e hobbies⎵ | Sobre Mim |
| 31 | Minha formação profissional⎵ | Sobre Mim |
| 28 | Quem eu sou (idade, estado civil, nacionalidade, etc) | Sobre Mim |
| 7 | Minhas qualidades | Sobre Mim |
| 27 | Meus defeitos | Sobre Mim |
| 6 | Técnicas, serviços e procedimentos que eu efetuo⎵ | Sobre Mim |
| 12 | Técnicas, serviços e procedimentos que eu não recomendo | Sobre Mim |
| 3 | Hábitos que eu recomendo para o meu público | Sobre Mim |
| 2 | Hábitos que eu não recomendo para o meu público⎵ | Sobre Mim |
| 1 | Crenças e ideias que eu defendo | Sobre Mim |
| 22 | Verbos Poderosos | global (never loaded) |
| 23 | Adjetivos Poderosos | global (never loaded) |
| 24 | Momento do dia | global (never loaded) |
| 29 | GPT | global (never loaded) |

### 5.2 Enums

List sort `recent|plays` · status filter `approved|pending` · item status `approved_manual|approved|pending` · source `content|pending` · viral topic `approved|pending` · extraction `myPublic|topic_virais` · brain `custom` (Personalizado) | `beliefs` (Crença) · badge `Vazio|Pronto`.

### 5.3 Nichos (id = name, 28)

7 Beleza & Estética · 25 Casa & Decoração · 21 Comunicação & Liderança · 33 Construção Civil · 22 Criação de Filhos · 18 Cripto · 27 Culinária · 9 Desenvolvimento Pessoal · 20 Direito · 4 Educação · 28 Emagrecimento · 13 Emagrecimento e Dieta · 5 Empreendedorismo/Business · 6 Espiritualidade · 3 Finanças · 29 Imigração · 26 Imobiliário · 19 Marketing Digital · 8 Moda & Estilo · 31 Pets & Animais · 2 Relacionamentos · 1 Saúde e Bem-Estar · 14 Saúde Mental · 17 Tech & IA · 24 Trends do Momento · 32 Tributação Fiscal · 30 Turismo & Viagem · 23 Vendas

### 5.4 Profissões (id = name, 102)

25 Acupunturista · 70 Advogado Administrativo · 72 Advogado Ambiental · 64 Advogado Civil · 74 Advogado Constitucional · 75 Advogado de Consumidor · 67 Advogado de Família · 76 Advogado Digital · 68 Advogado Empresarial · 71 Advogado Imobiliário · 73 Advogado Internacional · 65 Advogado Penal · 77 Advogado Previdenciário · 66 Advogado Trabalhista · 69 Advogado Tributário · 85 Agente de Turismo · 20 Arquiteto(a) · 102 Auditor Fiscal · 3 Autor(a) · 95 Breathwork · 18 Cabeleireiro(a) · 56 Chef de Cozinha · 105 Cirurgião Plástico · 27 Coach · 57 Confeiteiro · 54 Consultor de Imagem · 49 Contador(a) · 62 Copywriter · 82 Corretor de Imóveis · 90 Corretor de seguro de vida · 21 Dentista · 79 Designer de Interiores · 100 Designer de joias · 52 Designer de Sobrancelhas · 60 Designer Gráfico · 28 Economista · 23 Empreendedor(a) · 92 Enfermagem · 80 Engenheiro · 15 Esteticista · 32 Estrategista de Marca · 2 Farmacêutico(a) · 14 Fisioterapeuta · 47 Fisioterapeuta Pélvico · 106 Fonoaudiólogo · 55 Fotógrafo · 61 Gestor de Tráfego/Media Buyer · 22 Gestor(a) · 83 Higienista Ocupacional · 30 Influenciador(a) · 31 Investidor(a) · 99 Joalheira · 84 Jornalista · 78 Juiz · 51 Líder Religioso · 53 Maquiador(a) · 26 Marketeiro(a) · 98 Medicina Regenerativa · 37 Médico Cardiologista · 12 Médico Cirurgião · 33 Médico Dermatologista · 38 Médico Endocrinologista · 101 Médico geral · 89 Médico Geriatra · 36 Médico Ginecologista · 43 Médico Integrativo · 39 Médico Neurologista · 87 Médico Nutrólogo · 104 Médico Obstetra · 40 Médico Oftalmologista · 34 Médico Ortopedista · 91 Medico Otorrinolaringologia · 35 Médico Pediatra · 8 Médico Psiquiatra · 93 Medico Radiologia · 103 Médico ultrassonografista · 41 Médico Urologista · 42 Médico Veterinário · 50 Mentor(a) · 24 Moda · 97 Musculação · 4 Neurocientista · 16 Nutricionista · 81 Paisagista · 5 Pastor(a) · 48 Personal Trainer · 94 Professor de Yoga · 29 Professor(a) · 63 Programador(a) · 46 Psicanalista · 44 Psicólogo Infantil · 7 Psicólogo(a) · 45 Psicoterapeuta · 86 Quiropraxista · 59 Social Media · 58 Sommelier · 6 Teólogo(a) · 9 Terapeuta · 10 Terapeuta Holístico · 96 Terapeuta Somatico · 13 Vendedor(a) · 19 Visagista

### 5.5 Sample pending viral topics (owner)

`empreendedorismo` 2.5M · `trabalhar menos (desejo)` 1.6M · `Elon Musk` 1.4M · `finanças das famílias` 1.1M · `profissões que não precisam de faculdade` 1M · `vendas de produtos na internet` 928.2K · `produtos digitais` 852.7K · `capital de risco` 577.6K · `objeção de venda` 334.5K · `juros compostos` 321.2K

## 6 · Server pipeline behind each action \[INF unless noted\]

**Viral-profile research ("engenharia reversa"):**

1. *Catalogue ingestion (platform, offline).* Curated profiles are scraped into `eng_reversa_search` (one per profile), with `eng_reversa_result` rows per post: thumbnail on S3, plays, likes, comments, post date, hook `headline`, transcription. Staff tag profiles with niches and professions and mark them approved.
2. *Per-video extraction (platform job, precomputed).* An LLM reads each viral post's hook/transcript and extracts **values per research variable**, keeping `result_id`, `plays` and the source sentence. `profile-viral-search/{id}` returns this already grouped \[OBS shape\]. The older `extract-profile` job with `step`/`progress` and "já existentes" de-duplication is the evidence \[OBS\].
3. *User picks → Minha Pesquisa.* `profile-viral-search/save` inserts the chosen values, de-duplicated (`already_added`) \[OBS\]. Status on insert: \[LIVE\].
4. *Viral topics.* `extract-profile {type:'topic_virais'}` extracts short subjects from a profile's posts into the user's pending topics with summed views; the user approves or rejects them \[OBS UI\].

**Manual / AI add:** prompt off → plain insert as approved-manual. Prompt on → the LLM runs the captured classifier prompt (main tab, AI layer), optionally with the variable catalogue, files each line under a variable, saves it, and returns `classified` + `unclassified` (with a `token`). Sync with a 90s client timeout, queue-job fallback.

**Brain:** questionnaire answers → **LLM validation per answer** (approve / reject + reason) → when all pass, an LLM synthesizes the answers into the brain's markdown document → "sync to Postgres" (`syncing → synced`) → `Pronto` \[OBS states, INF internals\]. File upload and YouTube transcription are parsed or transcribed and **appended** to the document \[OBS text\].

**Downstream consumers \[OBS in other pages\]:**

- Headline generation: subject select from `/variables/type/{who}`, reference profiles from `/headlines/get-profile` (`variable_selected[]`), `Núcleo Especifico:` = `specific_core_id`.
- Roteiro: `core_id` (`— Nenhum —` + brains); favorites roteiro `core[]` (`Adicionar Cérebro como fonte de informação:` / `Adicionar Crenças:`).
- Chat (Livewire): `searchMyResearch(q, group, page, sort, variable)`, `getResearchVariables(group)`, `searchMyCerebro(q, page)`; @Cérebro only for the roteiro agent.

## 7 · Still open — each needs an action that changes the account

These can only be answered by doing something in CoreStudio (adding, rejecting, deleting, recording, uploading). They were not done; each needs the owner's OK.

- [ ] AI add with 3 lines (one ambiguous): capture `add-items-sync`; which status the new items get; what `unclassified[].token` is
- [ ] Direct add with no variable selected: which error appears
- [ ] Reject a pending item: hard delete or kept as rejected (and can it be re-extracted)
- [ ] `Adicionar à minha pesquisa` from a profile: do items land as Pendentes or Aprovados; does `✓ Já adicionado` survive deleting the item
- [ ] `Zerar toda a pesquisa`: does it also clear Assuntos Virais
- [ ] Assuntos Virais pane (`?tab=subject-viral`): render it and capture a `viral-data/{id}` sample
- [ ] Create a brain: redirect target, 422 messages, per-plan limit
- [ ] Answer a questionnaire and Finalizar: capture a real `Rejeitada` reason, the time to `Pronto`, and the synthesized document
- [ ] Upload a PDF / transcribe a YouTube link: what gets appended
- [ ] Live **Trace da IA** on one generation (1 credit): the HEADLINE / ROTEIRO system prompts

## 8 · Quirks worth not copying

- The list loads everything and filters in the browser; use server paging with `sort`, `status`, `variable_id`.
- Two item stores leak into the API (`source`); use one `research_items` table with `status ∈ {pending, approved, rejected}` and `origin ∈ {manual, ai_classified, profile_extraction}`.
- Bulk actions send one request per item; provide real bulk endpoints.
- Direct add has no guard when no variable is selected.
- Four "global" variables are offered in the filter but never loaded.
- Viral-topic approve/reject is a GET with no confirmation; removing a topic deletes every pill with the same text.
- The AI classifier knows 13 slugs while the UI has 33 variables; keep one list.
- Legacy paths (per-variable tabs, `searches/save`, "Criar Pesquisa", orphan modals, voice-per-question, *Minhas extrações*) stay out unless you decide otherwise.

## 9 · Verified live on 2026-10-05 (read-only) — wins over §0–§8

**Minha Pesquisa**

- The AI prompt is **active** for the owner: `add-item-prompt` → `{success, prompt_system, is_active: true, include_variables: true}`. The full prompt is in the main tab (AI layer). It knows 13 slugs, not the 33 UI variables.
- A real item: `{id, user_id, workspace_id, variable_id, eng_reversa_result_id, content, status: 0|1, plays: "630319" (string), created_at, updated_at, deleted_at, source: "pending"}`. Soft delete. The response holds 17 avatar and 12 especialista variable keys.
- Owner's counts, approved / pending: Desejos 33/70 · Dores 24/36 · Itens 12/26 · Instituições 11/18 · Pessoas 8/3 · Demográficas 5/2 · Crenças 12/– · Medos 2/– · Objeções 1/–.
- Server slugs exist (`variable_name`): 1 `CRENCAS-DO-ESPECIALISTA` · 3 `HABITOS-RECOMENDADOS-PELO-ESPECIALISTA` · 10 `OBJECOES-DO-AVATAR` · 15 `ITENS-CONHECIDOS-PELO-AVATAR` · 17 `DORES-TANGIVEIS-DO-AVATAR` · 18 `DESEJOS-TANGIVEIS-DO-AVATAR` · 19 `EVENTOS-CONHECIDOS-PELO-AVATAR` · 34 `PRODUTOS-CONHECIDOS-PELO-AVATAR`.
- Row icons, `Agrupar` headers, the `Ações` modal and 👁 → Biblioteca are confirmed (screenshots in the main tab).

**Extrair Pesquisa**

- `approved-profiles` returns **485 profiles** in one unpaged response.
- `profile-viral-search` includes **Sobre mim** variables (1, 3) as well as Meu Público. `plays` is an int here. `headline` = the hook, e.g. "Tonifique seu abdômen usando uma parede. Dois exercícios super fáceis." → value "Tonifique seu abdômen". Sample: 9 variáveis · 76 itens.
- Default filters match the owner's profile (Finanças, Vendas, Imobiliário / Vendedor(a), Empreendedor(a), Investidor(a)).
- `Vídeos` = `<a target=_blank href=/library?profile=…>`.

**Segundo Cérebro** — replaces §3.3's editor

- `/cores/edit/{id}` redirects an unanswered Sistema brain to `/cores/questions/{id}`: progressive groups of 3, `Zerar Tudo` / `Salvar Rascunho` / `Finalizar Respostas`, a `HAS_ASSISTANT` guard (`Sistema de validação não configurado completamente. Entre em contato com o suporte.`).
- Validation result: websocket (private channel `questions-validation.{env}.user.{id}`, event `.validation-completed`) + `brain-status/{id}` polled every 3s. Messages: `Respostas enviadas para validação. Aguarde...` → `Aprovada` / `Rejeitada` + `Motivo da rejeição:` → `Todas as respostas foram aprovadas! Gerando cérebro...` → `Respostas aprovadas! Sincronizando seu cérebro...` → `Cérebro sincronizado! Redirecionando...` → `/cores?brain_synced=1`; error `Ocorreu um erro ao gerar o cérebro. Tente novamente.`
- Ready and custom brains open a **markdown content editor** with `Enviar arquivo` and `Transcrever do YouTube` (Sistema brains add `Responder perguntas`; custom brains add rename + delete). Both sources append below the existing text.
- `Criar Cérebro` shows only the name; the type select is hidden, so every new brain is Personalizado.
- No mic UI on any editor; voice-per-question is legacy.
- Questionnaire texts for the three Sistema brains are verbatim in the main tab.
- Hidden `/cores/extract` *Minhas extrações* page and its `Nova Extração` modal are documented in the main tab.
