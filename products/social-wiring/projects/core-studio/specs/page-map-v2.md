# CoreStudio — Page Map v2 (authoritative)

Built 2026-10-06 from the fresh crawl `captures/crawl-2026-10-06/` (54 saved server-rendered pages, `inventory.json` with 150 crawled URLs, two new scripts `cores.js` and `profileInstagramV2.js`), cross-checked against the 2026-10-05 study (`docs/platform-study.md`, `specs/*.md`, `captures/js/*`). Where this file and the earlier study disagree, **this file wins**; each correction is listed in §0.2.

Companion files: `specs/mechanisms.md` (how each mechanism works behind the page) and `specs/xhr-to-fetch.md` (read-only GETs still needed).

## 0 · How to read this

### 0.1 Evidence tags

| Tag | Meaning |
| --- | --- |
| **C** (CONFIRMED) | Seen in a saved page, script or captured JSON (file named where useful). |
| **I** (INFERRED) | Reasoned from code shape, naming or data correlation; not seen working. |
| **U** (UNKNOWN) | Cannot be determined from what we hold; listed in open questions. |

All routes are under `https://corestudio.ai/dashboard/user` unless a path starts with another prefix. "XHR" means the browser fetches it after page load; "SSR" means the value is in the server-rendered HTML.

### 0.2 Corrections to the earlier map (2026-10-05)

| # | Earlier claim | Correction (evidence) |
| --- | --- | --- |
| 1 | "Thirteen pages." | **21 route templates** (23 entries below, two of them parameter modes). The earlier map missed `headlines?who=…` (the real generation page), `cores/questions/{id}`, the `library?viral_id` and `library?profile` modes, `profile/instagram`, `profile/integrations` and the `searches?tab=subject-viral` mode. **C** |
| 2 | Gerar Headlines = "Legacy form flow: 3 cards → Gerar Headlines modal". | `/headlines/generate` is only a landing with 3 cards linking to **`/headlines?who=me|public|viral`**, a full page with an in-page form plus a history table (`POST headlines/list`). The *modal* version (`#modal-make-headlines-alternative`) is a second, older copy embedded in Dashboard, Favoritas and Sugeridas. **C** |
| 3 | Gatilho da Atenção = 6 options (Recompensa, Mistério, Popularidade/Autoridade, Reconhecimento, Crença, Disrupção). | That is the **legacy modal** (`structures_category_items[]` ids 2–7). The **current page form** uses a different field, `attention_trigger_ids[]`, with **7** options: Recompensa · Reconhecimento · Popularidade · Autoridade · Mistério · Crença · Disrupção (ids 1–7). Two vocabularies, not one. **C** |
| 4 | Advanced options = Perfil de Referência **XOR** Formato do Vídeo. | On the Meu público / Sobre mim form it is a **3-way** choice `reference-type-me-public ∈ {profile, format, attention}`. The 2-way XOR survives only on the Assuntos Virais form and the legacy modal. **C** |
| 5 | `who=public` could read as "public headlines". | `who=public` means **"Sobre meu público"** (audience variables), `who=me` = "Sobre mim", `who=viral` = Assuntos Virais, `who=search` = hidden "busca inteligente". No public/shared headline concept exists. **C** |
| 6 | "Minha conta" is one page. | Minha conta has 3 in-page tabs that are separate routes: **Meu Perfil** `/profile`, **Instagram** `/profile/instagram`, **Integrações** `/profile/integrations`. **C** |
| 7 | Brain ids: "template id 8–4192 + per-user instance 85xx–93xx" (guess). | Now **C**: two ID spaces. *Core* ids (8, 9, 14, 3081, 3741, 4191, 4192) are used by `/cores/edit/{id}`, the Roteiro Avançado select and "Núcleo Especifico"; *Brain* ids (8772, 8773, 8774, 8775, 8522, 9385, 9386) are used by the Favoritas "Criar Roteiro" select and by the YouTube job (`data-core="3081" data-brain="8775"`). Mapping in mechanisms §3. |
| 8 | Núcleo de Influência questions "not re-read". | **15 questions** captured (`cores/questions/3081`, question ids 1583–1597, 5 groups of 3), all `Aprovada`. **C** |
| 9 | "With @perfil the structure pool switches to that profile's videos; without, a default house pool (~52 IDs)." | The ~52 IDs are **not a house pool**: 47 of the 52 distinct structure IDs (182 of 190 citations) are videos of 3 of the account's 6 **Minha Biblioteca** profiles. And `@perfil` biases rather than filters (a "10 baseadas no @elias.maman" answer cited 2 structures from another allow-listed profile). See mechanisms §7. **C** (correlation) / **I** (mechanism) |
| 10 | `library?viral_id=` opens a page for that viral. | The server still renders the normal auto-filtered list (often **empty**: "Nenhum viral encontrado"), and client JS opens the modal from `GET library/result/{id}`. **C** |
| 11 | Biblioteca is a plain menu item. | Its sidebar `<li>` carries `title="Exclusivo para o Plano Premium"`: plan-gated. Blade comments also show two hidden sidebar sections, **Avatar** and **Estudio de Edicao**, rendered empty. **C** |
| 12 | "Assuntos Virais pane is hidden and unused." | It is reachable by `?tab=subject-viral` (client-side tab; identical HTML) **and it feeds** the `who=viral` headline form ("Nenhum assunto viral disponível no momento" is shown because the owner has 0 *approved* topics; `hasViralTopics=false` in SSR). **C** |

### 0.3 Categories used

`Shell` · `Pesquisa` (Research) · `Cérebro` (Brain) · `Geração` (Generation: chat + headlines) · `Roteiros` (Roadmaps) · `Biblioteca` (Viral library) · `Conta` (Account) · `Integração` (Integration) · `Treinamento` (Training).

### 0.4 Sidebar (verbatim, unchanged since 2026-10-05) **C**

```
Dashboard                                   /dashboard/user
Criar Headlines e Roteiros                  /chat
Pesquisa ▾      Minha Pesquisa              /searches
                Extrair Pesquisa            /searches/extract-profile
Segundo Cérebro                             /cores          (Blade comment: "Nucleo de Influencia")
Biblioteca                                  /library        (title="Exclusivo para o Plano Premium")
(Avatar — empty)  (Estudio de Edicao — empty)   Blade comments only
Configurações ▾ Minha conta                 /profile   (+ in-page tabs /profile/instagram, /profile/integrations)
                Minha Biblioteca            /my-library
                Treinamentos                /trainings
                Headlines ▾  Gerar Headlines      /headlines/generate  (→ /headlines?who=…)
                             Headlines Favoritas  /headlines/favorites
                             Headlines sugeridas  /headlines/suggested
                Roteiros                    /roadmaps
```

Not in the menu but routable: `/cores/edit/{id}`, `/cores/questions/{id}`, `/cores/extract`, `/headlines?who=…`, `/profile/instagram`, `/profile/integrations`. Same 13 nav links on every crawled page. **C**

---

## 1 · Shell (present on every page) — category `Shell`

| Element | What it is | Data source | Endpoints |
| --- | --- | --- | --- |
| Sidebar + footer | Avatar initials, first name, workspace name; ⋮ menu: *Espaços de trabalho* (list → `POST workspace/switch` form, `workspace_id`), *Ver tutorial novamente* (opens `#modal-first-access-tutorial`), *Fazer logout* (`POST /logout`) | SSR | `POST /dashboard/user/workspace/switch` **C** |
| `#modal-create-workspace` "Adicionar Workspace" | `Nome` (placeholder `Ex.. My Workspace 2`), Cancelar / Criar; hidden `customer_id` | SSR | `POST /dashboard/admin/customers/workspace/create` (the user page posts to an **admin** path — quirk) **C** |
| Notifications bell (Alpine) | "Notificações", "Marcar todas como lidas", toggle read, empty "Nenhuma notificação por aqui" | XHR | `GET notifications`, `POST notifications/{id}/read`, `POST notifications/read-all` **C** |
| Offcanvas `#offcanvasEnd` **"Headlines na Box"** | A cart of headlines collected with "Adicionar na Box"; "Remover selecionados", "Salvar Headlines" (→ `#modal-box-headlines-save`, picks a customer + week) | XHR | `POST /dashboard/box-headlines/add|remove`, `GET …/customer/{id}/list`, `POST …/customer/{id}/save` (agency feature) **C** code / **U** whether reachable for this plan |
| `#modal-first-access-tutorial` | "Bem-vindo ao Core Studio! Antes de começar, assista aos treinamentos." → *Assistir aos treinamentos agora* (`/trainings`) / *Pular por agora* | SSR | `POST first-access-seen` **C** |
| `#modal-report` "New report" | Tabler demo leftover (Simple/Advanced, Visibility…) — dead UI | SSR | none **C** |
| Twin credits | Balance check | XHR | `GET twin/api/credits` (on every page) **C** |
| Session | CSRF refresh every 30 min; HTTP 419 → toast "Sua sessão expirou…" + reload | — | `GET /csrf-token` **C** |
| Realtime libs | Pusher 8.2 + Laravel Echo 1.15 loaded on every page | — | `/broadcasting/auth` **C** |

---

## 2 · Dashboard — `/dashboard/user` — category `Shell`

- **Params:** `filter ∈ {dateAsc, dateDesc, type}` (from the Histórico select; full reload) **C**. Not crawled with a value.
- **Sidebar:** level 1 "Dashboard".
- **Purpose:** usage overview + quick actions on suggested headlines.

| Section | Visible labels / fields | Data shown (owner snapshot) | Source |
| --- | --- | --- | --- |
| Greeting | "Olá, Gilson!" | first name | SSR **C** |
| KPI cards | `Headlines geradas` · `Roteiros gerados` · `Diagnóstico` (`a preencher`) | 0 · 2 · 0 | SSR **C**; meaning of "Diagnóstico" **U** |
| Histórico | "Linha do tempo do seu uso.", select `Filtrar / Data crescente / Data decrescente / Tipo` | 2 events "atualizou o perfil." with actor + `dd/mm/YYYY - HH:mm` | SSR **C** |
| Headlines Sugeridas widget | "ver todos as headlines" → `/headlines/suggested`; 20 rows: truncated headline (full text in `title`), views pill (e.g. `3.1M views`), **Ações** ▾ `Criar roteiro` (now a plain link to `/headlines/suggested`; the in-place action is commented out) · `Editar` (→ `#editHeadlineModal`) · `Abrir link` (source Instagram post) | ids 201486–201503, 201774, 201775 (corrected 2026-10-06; "201755–201775" was an interpolated range and its middle ids belong to other customers, see `mechanisms.md` §15); views 372.9K–4.6M (source viral's views) | SSR **C** |

Modals on this page: `#modal-make-headlines` (legacy generator, see §17), `#advancedRoadmapModal` (Roteiro Avançado, §20), `#editHeadlineModal` "Editar headline" (`Headline` textarea → `POST headlines/reversa/update {id, headline}`), `#createRoadmapModal` "Criar Roteiro" (`Headline Base` + "Qual ideia você você quer defender nesse roteiro?" → `POST roadmaps/reversa/store {headline_id, observations}`; synchronous response `roadmap_engreversa.text`), `#viewRoadmapModal` "Visualizar Roteiro", `#viewHeadlineFlowModal` (debug: `Payload Primeira Criação` / `Callback Primeira Criação` / `Payload Revisão` / `Callback Revisão` ← `GET headlines/suggested/view/{id}`). **C**

Dead code: an "O que vamos criar hoje?" AI search box (`#ai-search-input` → `POST mamanai/proccess {query}`) whose markup is not rendered. **C**

Scripts: `headlines.js`, `dashboard.js`, `roadmaps.js`, `advanced-roadmap-modal.js`, `advanced-roadmap-library.js`, Quill 2.0.3, Prism, noUiSlider.

---

## 3 · Criar Headlines e Roteiros — `/chat` — category `Geração`

- **Params:** `c={conversationUUIDv7}` (selected conversation; Livewire `update-url`), `cite_viral={viralId}` (pre-inserts a viral mention), `cite_profile={engReversaSearchId}` (pre-inserts "@perfil - Todos os vídeos"). **C** (code); crawled without params.
- **Sidebar:** level 1.
- **Purpose:** the main AI surface: two tool-using agents (HEADLINE, ROTEIRO) with references, memory and documents.
- **Component:** Livewire 3 `document-chat` (path `dashboard/user/chat`, locale `pt_BR`). SSR state: `messages[{id, role, content, isRoteiro}]` (14 here), `messagesLimit 100`, `conversations[{id, title, updated_at}]` (15, `hasMoreConversations`), `conversationsLimit 15`, `selectedAgentId`, `activeRunId`, `attachedReferences[]`, `contextCharCount` (28,506), `streamUrl` (`/dashboard/user/chat/stream`), `traceMessageId`, `isMobile`. Init JSON `actionAgentMap = {headline: 1, roteiro: 2, headline_express: 3}`. **C**

| Section | Labels |
| --- | --- |
| Conversation rail | "Conversas", `+` (new), per item rename (input `maxlength=100`, "Salvando...") / "Apagar conversa", "Ver mais conversas", empty "Nenhuma conversa para este agente." |
| Links | "Segundo cérebro" (→ `/cores`), **Memória** modal: "O que a IA sabe sobre você em todos os chats de Roteiro e Headline…" ("guarda na memória que eu não uso emojis"), textarea `maxlength=500` placeholder "Ex.: Meu público são donos de clínica de estética.", list + Apagar, "Nada salvo ainda." |
| "Chat com Documentos" | docs drawer **Referências anexadas** |
| Messages | Assistant headline answers render each item with `(estrutura #ID)` linking to `/library?viral_id=ID`, plus buttons "Criar roteiro a partir desta headline" / "Criar roteiro com headline editável", and a copy button. |
| Composer | agent select, @-mention picker (4 tabs), mic dictation, send |

Data: conversation list + current conversation SSR in the Livewire snapshot; streaming over SSE (`POST chat/stream`); uploads `POST chat/documents`; credit/recharge `twin/api/recharges`, `twin/faturamento`. All Livewire actions (`searchMentions`, `searchMyResearch`, `searchMyCerebro`, `attachReference`, memory CRUD, trace) go through Livewire POSTs. **C** (earlier `frontend-js-analysis.md` §1.9, §2.2 still valid).

Snapshot content: a conversation for **Mônica's** psychoanalysis profile run from this same account (headlines for a roteiro, then "me da mais 10 baseadas no @elias.maman", "faz baseado no @psifernandosegredo"…). 30 distinct structure IDs cited on this page. **C**

---

## 4 · Minha Pesquisa — `/searches` — category `Pesquisa`

- **Params:** `tab ∈ {my-research (default), subject-viral}` — **client-side only**: `/searches` and `/searches?tab=subject-viral` return byte-identical HTML; `searches.js` reads/writes `?tab`. **C**
- **Sidebar:** Pesquisa › Minha Pesquisa.
- **Purpose:** the account's persona research base (phrases filed under variables) + the viral-topics list.

Main pane (`#my-research`): toolbar `Mais Recentes` · `Mais Views` · `Aprovados` · `Pendentes` · variable select (33 ids) · `Agrupar` · `Ações`; "Adicionar itens a pesquisa"; infinite list (20/scroll), empty "Nenhum item encontrado." Row anatomy, bulk modal and add-items modal are unchanged from `specs/pesquisa-cerebro-spec.md` §1 and §9. **C**

Data source: **XHR**, 2 calls `GET searches/variables/items?type=avatar|especialista` (all items; sorting/filtering client-side). Labels/types SSR in `window.unifiedVariableLabels`/`unifiedVariableTypes`. **C**

Modals present (19): `extractViralProfileModal` "Extrair Pesquisa de Perfil Viral" (orphan copy), `profileViralSearchModal`, `modal-add-item` (Inserir itens na pesquisa: "Itens", "Salvar itens", "Inserir mais", "Itens pendentes de salvar"), `modal-bulk-actions` "Ações — N selecionado(s)", confirm modals (bulk delete, empty variable, empty all, bulk delete viral, empty viral, approve/reject variable, approve/reject/remove topic), `viralModal` "Tópicos Virais", `addVariableModal` "Adicionar conteúdo para a variável", `extractViralTopicsModal` "Extrair Assuntos Virais". Legacy `form#save-variables` with "Atualizar" (`POST searches/save`). **C**

Endpoints: see matrix §24 rows *Pesquisa*.

### 4b · Assuntos Virais mode — `/searches?tab=subject-viral` — category `Pesquisa`

| Part | Labels | Data (owner) | Source |
| --- | --- | --- | --- |
| Header card | "Extrair assuntos virais" — "Use esta opção para extrair assuntos virais de um perfil e adicionar aos seus assuntos virais." → button **Extrair Assuntos Virais** (`extractViralTopicsModal`, list from `GET searches/approved-profiles-viral-topics`, job `POST searches/extract-profile {type:'topic_virais'}`) | — | **C** |
| Tabs | `Aprovado` · `Pendente 10` | 0 approved, 10 pending | SSR **C** |
| Aprovado tab | Selecionar todos · Excluir selecionados (N) · Esvaziar · input "Digite um novo assunto viral..." (`maxlength 255`) + Adicionar · badges · Ver mais | empty | SSR **C** |
| Pendente tab | Selecionar todos · Aprovar selecionados (N) · Excluir selecionados (N) · Esvaziar; rows: checkbox · topic · `N Views` · `Pendente` · ✓ (approve) · ✕ (reject); click → `viralModal` (`GET searches/viral-data/{topicId}`) | 10 topics, ids 442789–442798, 321.2K–2.5M views (e.g. "empreendedorismo" 2.5M, "juros compostos" 321.2K) | SSR **C** |

Actions: `GET searches/viral/topics/{approve|reject}/{id}` (**mutating GETs**), `POST …/viral/topics/add|bulk-delete|empty`, `GET …/viral/topics/remove/{id}`. **C**

---

## 5 · Extrair Pesquisa — `/searches/extract-profile` — category `Pesquisa`

- **Params:** none server-side (filters are client-side over the XHR list). **C**
- **Sidebar:** Pesquisa › Extrair Pesquisa.
- **Purpose:** browse the platform's approved viral profiles and pull their pre-extracted research phrases into Minha Pesquisa.

| Part | Labels | Source |
| --- | --- | --- |
| Header | "Extrair Pesquisa de Perfil Viral" — "Selecione perfis aprovados para extrair e adicionar às suas variáveis de pesquisa." + link "Minha Pesquisa" | SSR |
| Filters | "Buscar perfis por nome..." · `Nichos` (28) · `Profissões` (102) multi-selects pre-set from `GET profile/get-niches-professions` · Limpar Filtros | SSR options, XHR preset |
| States | "Carregando perfis aprovados..." / "Nenhum perfil aprovado encontrado." / grid + pagination (24/page, client-side) | XHR `GET searches/approved-profiles` (485 profiles, unpaged — 2026-10-05) |
| `profileViralSearchModal` | "Pesquisa do perfil @x", "Carregando pesquisa...", "Nenhuma extração encontrada para este perfil.", count, "Selecionar todos", "Adicionar à minha pesquisa (N)", Fechar | XHR `GET searches/profile-viral-search/{engReversaSearchId}`; save `POST …/profile-viral-search/save` |

All **C**. Card fields and modal row anatomy: `pesquisa-cerebro-spec.md` §2 + §9.

---

## 6 · Segundo Cérebro (list) — `/cores` — category `Cérebro`

- **Params:** `brain_synced=1` (set by the questionnaire redirect; effect **U**). **C**
- **Sidebar:** level 1 "Segundo Cérebro".
- **Purpose:** list the account's brains.

| Part | Labels | Data (owner) | Source |
| --- | --- | --- | --- |
| Header | "Cérebros Personalizados" / "Segundo cérebro", **Criar Cérebro** | — | SSR |
| Tutorial banner | "Aprenda a usar o Cérebro Personalizado para turbinar suas postagens!" → "Assistir agora." (`#modal-yt-video` "Como usar o Cérebro Personalizado", Bunny `play/399061/…`) | — | SSR |
| Cards (7) | badge `Vazio`/`Pronto`, name, **Acessar Cérebro** → `/cores/edit/{coreId}` | Vazio: História de Criação (8), Histórias de Vida do Especialista (9), Método do Especialista (14). Pronto: Núcleo de Influência (3081), Call de diagnóstico (3741), Formulário (4191), Narrativa (4192) | SSR **C** |
| `#modal-make-core` | "Criar Cérebro Personalizado": **Tipo de Cérebro:** `custom=Personalizado` / `beliefs=Crença` (select present in markup, hidden by CSS per 2026-10-05 live check), **Nome do Cérebro:** (`Ex: Reels Instagram`) → `POST cores/custom/add` | — | **C** |
| `#modal-edit-core` | "Editar Cérebro Personalizado": Nome → `POST cores/custom/update` | — | **C** |

Script: `brains.js`.

---

## 7 · Cérebro editor — `/cores/edit/{coreId}` — category `Cérebro`

- **Params:** path `coreId` (core id space, §0.2 #7). **Redirect rule (C):** an unanswered *Sistema* brain redirects to `/cores/questions/{coreId}` (8, 9, 14 did); answered Sistema (3081) and custom brains (3741, 4191, 4192) render the editor.
- **Sidebar:** none highlighted beyond Segundo Cérebro (not a menu item).
- **Purpose:** edit the synthesized brain document and append sources.

| Part | Labels | Data | Source |
| --- | --- | --- | --- |
| Title | `«name»` + `Sistema` badge (Sistema brains); ✎ rename / 🗑 delete (custom only) | Núcleo de Influência — Sistema | SSR **C** |
| Source buttons | `Responder perguntas` (Sistema only → `/cores/questions/{id}`) · `Enviar arquivo` · `Transcrever do YouTube` | — | SSR **C** |
| Content | "Conteúdo do cérebro", `N caracteres`, textarea `cores[{id}]` + hidden `original[{id}]`, **Aplicar Alterações** | 3081: 3,844 chars markdown with sections *Perfil Profissional de …*, *Especialidades*, *Público-Alvo e Desafios*, *Quem Ajuda*, *Solução e Transformação*, *Transformação Gerada*, *Argumentos de Defesa*, *Histórias de Sucesso* | SSR **C** |
| `#modal-upload-core` | "Importar arquivo para o cérebro" (PDF DOCX TXT MD CSV ≤ 20 MB, appended) → `POST cores/upload-file` | — | **C** |
| `#modal-youtube-core` | "Transcrever vídeos do YouTube": link rows, "+ adicionar outro link", **Transcrever e anexar** → `POST cores/youtube/extract {core_id, brain_id, links[]}` → full-screen overlay "Sincronizando o cérebro…" polling `GET cores/youtube/status/{jobId}` every 6 s | `data-core=3081 data-brain=8775` | **C** |
| `#modal-edit-core` "Renomear Cérebro", `#modal-core-delete` "Tem certeza?" | — | — | **C** |

Pages saved: 3081 only (3741/4191/4192 crawled to `inventory.json` but their HTML was not saved — see §25).

---

## 8 · Questionário do cérebro — `/cores/questions/{coreId}` — category `Cérebro`

- **Params:** path `coreId`. Reached by redirect (unanswered Sistema) or "Responder perguntas". **C**
- **Purpose:** answer the brain's questionnaire; answers are AI-validated, then synthesized into the brain document.

| Part | Labels | Data | Source |
| --- | --- | --- | --- |
| Header | "Cérebro" / "Personalize seu cérebro" / Voltar; card "«name» - Sistema" / "Responda as perguntas abaixo para personalizar seu cérebro" | — | SSR **C** |
| Progress | "Progresso das respostas" `N de M` | 3081: 15 questions; 8: 9 questions (ids 1609–1617) | SSR **C** |
| Question cards | number, question (markdown bold + italic hint), textarea `questions[{questionId}]` ("Digite sua resposta aqui..."), `N caracteres`, status chip (`Aguardando resposta` / `Respondida` / `Validando...` / `Aprovada` / `Rejeitada` + "Motivo: …") | 3081: all 15 `Aprovada`; groups of 3 ("Grupo 2 de 5 - Continue respondendo as próximas perguntas") | SSR **C** |
| Footer | `Zerar Tudo` (→ `resetModal` "Confirmar Exclusão" / "Sim, Zerar Tudo") · `Salvar Rascunho` · `Finalizar Respostas` (enabled only when all answered **and** `HAS_ASSISTANT`) | — | **C** |

Endpoints: `POST cores/questions/save-draft|store|reset`, `GET cores/brain-status/{coreId}` (3 s poll), Echo private channel `questions-validation.{APP_ENV}.user.{USER_ID}` event `.validation-completed`. **C**

Núcleo de Influência (3081) questions, verbatim titles (hints omitted): 1 Qual é o seu nome, e o que você faz? · 2 Você se autointitula por algum nome/termo? · 3 Quem você ajuda? · 4 Você costuma chamar sua audiência por um nome específico? · 5 Qual é a principal dor que você resolve? · 6 Qual é o inimigo e principal motivo causador dessa dor? · 7 Você costuma dar um nome para esse inimigo? · 8 O que sua audiência está tentando fazer para resolver isso, mas que não está funcionando? · 9 Qual crença errada ou visão limitada você gostaria que as pessoas mudassem? · 10 Qual problema filosófico existe por trás desse cenário? · 11 Qual é o segredo, atalho ou nova abordagem que resolve essa dor — e que você ensina? · 12 Qual é a grande transformação que você acredita que seu trabalho gera? · 13 Você já criou algum método? Se sim, tem algum nome específico? · 14 Quais argumentos fortes você pode usar para defender essa transformação? · 15 Você conhece histórias reais de pessoas que saíram do ponto A para o ponto B com sua ajuda? **C** (the other three questionnaires are in `platform-study.md`).

---

## 9 · Minhas extrações (hidden) — `/cores/extract` — category `Cérebro` (legacy)

- **Params:** none. Tab title "Minhas Pesquisas". Not in the menu. **C**
- **Purpose:** the older "extraction" flow: a link or pasted transcript → transcription → a generated *pesquisa* applied to brains or to variables.

| Part | Labels | Source |
| --- | --- | --- |
| Header | "Minhas extrações" / "Extrações realizadas", **Nova Extração** | SSR |
| Table `#mySearch` | ID · Data · Nome · Status (`Criando`/`Processando`/`Completo`/`Falha` from `pending_gpt`/…/`completed`/`error`), search "Pesquisar..." | XHR `POST cores/extract/list` (DataTables). Owner: 0 rows "filtrado de 192 registros no total" (2026-10-05) |
| `#modal-new-search` "Nova Extração" (`form#cores`) | `Nome:` (`ex: Pesquisa 1`) · `Extrair para:` multi `nucleos[]` = core ids (8, 9, 14, 3081, 3741, 4191, 4192) + "Clique aqui para criar um novo núcleo" (`Nome do Núcleo`, **Criar núcleo agora** → `POST cores/custom/add`) · `Url:` `document_url[]` ("Suporte a links para transcrição:" icons **YOUTUBE**, **DROPBOX**) · `Transcrição:` `document_text` · **Criar Transcrição** → `POST cores/transcrible` (sic) | **C** (`cores.js`) |
| `#modal-view-search` "Pesquisa Gerada" / "Transcrição" | ← `GET cores/view/{id}` → `{success, content}` | **C** |
| `#modal-edit-search-confirm` "Editar Pesquisa" (`search_edit`, **Aplicar Pesquisa**) · `#modal-edit-customer-search-confirm` "Selecione o Tipo de Variável" (`type`, Confirmar) · `j_core_remove` (→ `GET cores/remove/{id}`) | **C** markup; apply endpoints **U** |

Note: the button label resets to "Criar Pesquisa" and the error toast says "Ocorreu um erro ao criar a pesquisa." — this page is a fork of the old Pesquisa module. **C**

---

## 10 · Biblioteca de virais — `/library` — category `Biblioteca`

- **Sidebar:** level 1 "Biblioteca" (Plano Premium).
- **Purpose:** browse the scraped, transcribed and classified corpus of viral Reels; open a viral; generate a headline from it; allow-list videos for the chat.

### 10.1 Parameters (all server-side, full reload) **C**

| Param | Meaning |
| --- | --- |
| `niche[]` / `niche` | niche ids (28). Absent + no `view_all` ⇒ server **auto-applies the user's profile niches + professions** and shows the banner "Filtros aplicados automaticamente". |
| `profession[]` / `profession` | profession ids (102) |
| `view_all=1` | disable the automatic niche/profession filter ("Ver todos os virais") |
| `sort_by ∈ {plays (default), recent}` | the toggle button shows the **current** mode ("Mais vistos" ↔ "Mais recentes") and links to the other |
| `page` | 24 cards per page, classic pagination (owner, auto-filtered: **281 pages**) |
| `transcription_search` + `search_in ∈ {transcription, headline}` | comma-separated keywords; checkbox "Buscar apenas nas headlines" (default on) |
| `date_from`, `date_to` | post date range |
| `views_min`, `likes_min`, `comments_min` | thresholds |
| `social ∈ {instagram, tiktok, youtube}` | network |
| `profile` | handle (514 handles in the select) |
| `format_video` | format id (15) |
| `viral_result_id` | exact viral id (filter form "ID do Viral") |
| `core` | staff "Core" (gold standard) filter — preserved by JS; effect for non-staff **U** |
| `viral_id` | **deep link**: JS opens the detail modal (`GET library/result/{id}`) and strips the param; the list is the normal (auto-filtered) list |

### 10.2 Page parts

| Part | Labels | Data | Source |
| --- | --- | --- | --- |
| Header | "Biblioteca de virais" / "Biblioteca de virais disponíveis", sort toggle, **Filtros** | — | SSR **C** |
| Auto-filter banner | "Filtros aplicados automaticamente — Estamos mostrando virais dos seus nichos e profissões. Para ver todos os virais da biblioteca, clique em "Ver todos os virais"." | — | SSR **C** (absent when `profile=` is set) |
| Quick filters | `Nichos`, `Profissões` multi (TomSelect), **Meus nichos e profissões**, **Ver todos os virais** | owner presets 3/23/26 and 13/23/31 | SSR **C** |
| "Virais Encontrados" grid | card: checkbox, `@profile` badge, 9:16 thumbnail (S3 `eng_reversa/…`), overlay views · likes · comments, duration (`m:ss`m), post date, **Ver post** (Instagram `/p/…`), optional `CORE` ribbon; `onclick=openViralModal(viralId, engReversaSearchId)` | top card 46.1M views; ids ~98k–160k | SSR **C** |
| Empty | "Nenhum viral encontrado" / "Nenhum viral aprovado está disponível na biblioteca." | — | SSR **C** |
| `#modal-viral-info` "Informações do Viral" | profile header, play (Instagram embed), "Não consegue ver o vídeo?", Métricas (Visualizações, Curtidas, Comentários, Data do Post), Transcrição (Ver post, copy internal link, textarea, **Copiar Transcrição**, "Texto encontrado:" snippet), badges Nicho/Profissão/Formato do Vídeo, **Gerar headline** wizard (Próximo: Escolher Variáveis → Próximo: Revisar e Enviar → Criar Headline → "Headline enviada para criação!" / Ver Headlines Sugeridas / Continuar na Biblioteca), staff-only Core row | XHR `GET library/result/{id}`; wizard `GET library/workspaces`, `POST library/viral-topics`, `POST headlines/suggested/store` | **C** |
| Selection bar | "N vídeo(s) selecionado(s)", Limpar seleção, **Adicionar à Minha Biblioteca** (`POST library-references/self-assign {mode:'video', video_ids[]}`) | — | **C** |
| Filter sidebar "Filtros de Virais" | "Filtros Ativos:", Buscar por palavras-chave, Buscar apenas nas headlines, Período, Visualizações/Curtidas/Comentários Mínimos, Rede Social, Perfil, Nicho, Profissão, Formato de Vídeo, ID do Viral, Aplicar / Limpar Filtros | — | SSR **C** |

### 10.3 Mode: per-viral deep link — `/library?viral_id={id}` **C**

Crawled for the 30 structure IDs cited in the chat (3 HTML files saved, 27 inventory-only). All 3 saved pages render "Nenhum viral encontrado" under the auto-filter (**C**); the likely reason is that these virals belong to `psifernandosegredo`, outside the owner's niches/professions, and that `viral_id` also narrows the server query (**I**). The useful data is only in `GET library/result/{id}` (not captured — see `xhr-to-fetch.md`).

### 10.4 Mode: per-profile — `/library?profile={handle}[&sort_by][&page]` **C**

No auto-filter banner when `profile` is set. Crawled for the 6 Minha Biblioteca profiles:

| Profile | `eng_reversa_search_id` | Virals listed | Pages |
| --- | --- | --- | --- |
| psifernandosegredo | 1702 | 156 | 7 |
| elias.maman | 1735 | 105 | 5 |
| lelinhagentil | 1545 | 51 | 3 |
| dra.lilianalimongi | 1761 | 50 | 3 |
| veridiana_cavalheri | 1640 | 46 | 2 |
| advogandoparaimoveis | 1457 | 23 | 1 |

(431 virals in total; no `CORE` ribbon on any captured card.)

---

## 11 · Minha conta › Meu Perfil — `/profile` — category `Conta`

- **Sidebar:** Configurações › Minha conta. In-page tabs: **Meu Perfil** · **Instagram** · **Integrações**. **C**
- **Purpose:** persona settings that feed generation.

| Field | Label / options | Notes |
| --- | --- | --- |
| Header | "Minha conta" / "Informações e configurações da sua conta"; name + role chip `Cliente` | SSR **C** |
| Dados Pessoais | `Nome`, `Sobrenome`, `Email` (all disabled), `Senha`, `Telefone` (`(99) 99999-9999`), `Instagram`, `Tiktok` | SSR **C** |
| `Nichos` | `niches[]` multi, 28 options, "Selecione até 3 nichos"; tooltip "Preencha com os nichos que você deseja gerar Headlines" | owner: Finanças, Vendas, Imobiliário |
| `Profissões` | `professions[]` multi, 102 options, "Selecione até 3 profissões"; tooltip "Preencha com as profissões que você deseja gerar Headlines" | owner: Vendedor(a), Empreendedor(a), Investidor(a) |
| `Versão do Layout` | `layoutVersion` v1 / v2 (owner v2) | |
| `Bio` ? | popover template: "Eu sou (Nome), Sou (Profissão). Falo sobre (dores e desejos do publico). Eu ajudo pessoas a (resolver as dores) Por meio do (método utilizado no nicho).Para a pessoa consiga (solução e vida com os benefícios)." | filled |
| `Apresentação magnética` ? | "Esse campo será incluso nas gerações de Roteiros. Dentro da Tag Apresentação Magnética" | filled |
| `CTAs` ? | "Esse campo será incluso nas gerações de Roteiros. Dentro da Tag CTAs" | empty |
| **Atualizar** | `POST profile/save` | |
| `#profileIncompleteModal` "Atenção" | "O sistema precisa da bio preenchida juntamente com os nichos e profissões para poder sugerir itens da pesquisa para você. Tem certeza que deseja continuar assim?" Cancelar / Continuar — shown when bio XOR (niches ∧ professions) | **C** (`profile.js`) |

---

## 12 · Minha conta › Instagram — `/profile/instagram` — category `Integração`

- **Params:** `page` (posts pagination; bare URL redirects to `?page=1`), `period` (JS-only, select `#select-period` not rendered; values **U**). **C**
- **Purpose:** analytics of the user's own connected Instagram account.

| Part | Labels | Data (snapshot) | Source |
| --- | --- | --- | --- |
| Header | "Minha conta" / "Perfil do Instagram" + tabs | — | SSR |
| Profile nav | avatar, `one_consultoria`; tiles **Seguidores** · **Novos Seguidores** · **Visualizações** · **Engajamento** · **Comentários** | 13,979 · 0 · 35,533 · 596 · 40 | SSR inline `profileInsights` **C** |
| Charts | **Engajamento** (`Engajamento (%)`) and **Alcance** (`Alcance (K)`), ApexCharts area, x = `30 dias` · `7 dias` · `Hoje` | engaged 596/596/596; reach 14,783 ×3 (all periods equal) | inline **C** |
| Posts grid | 9 cards/page, card = thumbnail, `Reels`/`Post`, date, Curtidas, Comentários, Compartilhamentos, Visualizações, Alcance, Salvamentos; whole card links to the permalink | 168 posts stored (19 pages); account `media_count` 1,592 | inline `instagramPosts` **C** |
| Footer | "Última atualização: 05/10/2026 \| As métricas começam a ser monitoradas a partir da integração" | — | SSR **C** |

Bug: `formatData()` ignores its argument and always prints `06/04/2025` on every card. **C**
Dormant feature in `profileInstagramV2.js`: "select posts" modal (max **60**, counter `N/60`) → `GET profile/instagram/posts/all` + `POST profile/instagram/posts/set {content:[…]}`; buttons not rendered. **C** code / **U** purpose.

---

## 13 · Minha conta › Integrações — `/profile/integrations` — category `Integração`

| Part | Labels | Data | Source |
| --- | --- | --- | --- |
| Header | "Minha conta" / "Integrações com redes sociais" + tabs | — | SSR **C** |
| Card | **Instagram** — avatar, account name ("One Consultoria Imobiliária"), **Remover conta** | connected | SSR **C** |
| Connect | `#start-integration` handler exists; `url = null` server-rendered (account already connected, so no connect button) | — | **C** / connect URL **U** |

Remove: `confirm('Tem certeza que deseja remover esta conta?')` → `GET profile/integrations/delete` (**mutating GET**) → "Conta removida" / "não foi possivel concluiir a ação". The inline `meta_account` JSON (token redacted) is described in `mechanisms.md` §8. **C**

---

## 14 · Minha Biblioteca — `/my-library` — category `Biblioteca`

- **Sidebar:** Configurações › Minha Biblioteca.
- **Purpose:** the allow-list of profiles/videos the chat agents use (and, per evidence, the headline structure pool — mechanisms §7).

Labels: "Minha Biblioteca" — "Gerencie seus perfis e vídeos de referência para usar no Chat."; "Adicionar referência" tabs **Perfil completo** (Perfis da biblioteca, "Atualização automática — Novos vídeos desses perfis entram automaticamente", Salvar) · **Vídeos específicos** (info + "Ir para a Biblioteca de Virais") · **Solicitar Perfil** ("Perfil do Instagram (deve começar com @)", Enviar solicitação, "Minhas solicitações"); table "Minhas referências" (Buscar por ID ou headline...; Tipo · Perfil / Detalhe · Posts até · Atualizado · delete); `#del-confirm-modal` "Remover referência". **C**

Data (SSR): 6 rows, all `Perfil` + `Auto`, Posts até `Todos`, updated `09/06/2026 16:31`: psifernandosegredo, elias.maman, dra.lilianalimongi, advogandoparaimoveis, veridiana_cavalheri, lelinhagentil (reference ids 3602–3607); each links to `/library?profile=…`. Requests list via XHR `GET my-library/requests`. Full behavior: `biblioteca-roteiros-analysis.md` §2. **C**

---

## 15 · Treinamentos — `/trainings` — category `Treinamento`

Module "Treinamentos — Primeiros passos: da Bio aos primeiros roteiros"; 5 lessons (Bunny Stream library 478875, lazy `data-src`):
1 Como preencher a Bio ("…para a IA entender seu contexto.") · 2 Como aprovar itens da Pesquisa (automático e manual) · 3 Como gerar roteiros Headlines Favoritas · 4 Como gerar roteiros Headlines Biblioteca de Virais · 5 Como gerar roteiros com Headlines Próprias. Side list "Aulas". All SSR, no XHR. **C**

The lesson titles state the intended user journey: Bio → approve research (automatic **and** manual) → roteiro from Favoritas / from Biblioteca / from own headlines. **C**

---

## 16 · Gerar Headlines (landing) — `/headlines/generate` — category `Geração`

"Gerar headlines" — "Selecione o assunto que deseja gerar suas headlines"; 3 cards, each **Gerar Headlines**:
- **Sobre mim** — "Headlines com base nas suas convicções, hábitos e histórias de vida." → `/headlines?who=me`
- **Sobre meu público** — "Headlines com base em dores, desejos, crenças e demais características do seu público alvo." → `/headlines?who=public`
- **Assuntos do Virais** — "Headlines com assuntos em alta que conectam com o seu público-alvo." → `/headlines?who=viral`
SSR only. **C**

---

## 17 · Gerar headlines (form + history) — `/headlines?who={me|public|viral}` — category `Geração`

- **Params:** `who ∈ {public, me, viral}`; unknown/absent ⇒ JS selects `viral` (the no-param page `/headlines` renders the generic header). `headline={id}` auto-opens that batch's result modal after completion. **C** (`who=viral` not crawled.)
- **Sidebar:** Configurações › Headlines › Gerar Headlines (via landing).
- **Purpose:** configure and launch an async headline batch; list past batches.

| Part | Labels / fields | Notes |
| --- | --- | --- |
| Header | "Gerar headlines sobre **Meu publico / Mim / Assuntos virais**" + description, Voltar | SSR + JS |
| `form#make-headlines-me` (who = public/me) | **Selecionar Assuntos:** `variables_id[]` multi: `Todos` + 17 avatar options (value `ID|SLUG`, e.g. `18|DESEJOS-TANGIVEIS-DO-AVATAR` "Desejos do meu público") — Sobre mim options load from `GET variables/type/me`; per-variable "Valor das variável" selects (`variable_values[]`) from `POST headlines/get-variables-values`; **Selecione o Assunto:** `assuntos[]` (Selecione o assunto personalizado / Quero escolher outro assunto) | **C** |
| Opções Avançadas (me/public) | "Quero criar headlines com base em:" radio `reference-type-me-public`: **Modelagem de um Perfil** ("Crie suas headlines usando as estruturas de um perfil específico a sua escolha") · **Formato de Roteiro** ("…coerentes com os melhores formatos de roteiro para o seu perfil") · **Gatilho da Atenção** ("…gatilhos da atenção que mais se encaixam na sua comunicação"). Sub-fields: "Perfil de Referência (máximo 2):" `profile_ids_me_public[]` (from `GET headlines/profiles`; alert "Atenção! Exibindo somente perfis que possuem estruturas com as variáveis selecionadas."; profiles with `is_structure=0` disabled "(Sem estruturas disponíveis)") · "Formato do Vídeo:" `format_video_ids_me_public[]` (15) · "Gatilho da Atenção:" `attention_trigger_ids_me_public[]` (7). Checkbox `complete_with_research` "Criar as headlines usando apenas os itens da minha pesquisa." Slider "Criatividade objetiva:" `thermometer` snapping 0 Essencial / 50 Equilibrado / 100 Explorador. Hidden `disable_creativity=0`. | **C** |
| `form#make-headlines-viral` (who = viral) | "Assuntos Virais:" (approved viral topics; owner: "Nenhum assunto viral disponível no momento. Digite abaixo um assunto personalizado…"), "Sobre o que você deseja falar:" `custom_subject`, `assuntos[]` (mislabelled "Use perfis como referência:"), `who-choose=choose` "Escolher assunto"; advanced: `reference-type ∈ {profile, format}` → `profile_ids[]` / `format_video_ids[]`, `attention_trigger_ids[]` | **C** |
| `form#make-headlines-intelligent-search` (hidden, `who=search`, `intelligent_search=1`) | "Como funciona a busca inteligente? — O sistema irá buscar headlines virais para seu nicho e profissão e exibirá os resultados na tela." Limpar Campos · **Buscar Headlines** | no visible entry point **C** |
| `form#make-headlines-subject-moment` | "Tom de Comunicação:" radio `structures_category_items[]` 10 Chocante e Disruptiva · 11 Futuro e Possibilidades · 12 Curiosidade e Mistério · 13 Cultura e Sociedade · 14 Crítica e Denúncia · 15 Reflexão e Profundidade; Voltar · **Selecionar Assunto** · Gerar Headlines | second step of the viral flow **C** |
| Progress | "Processando suas Headlines", bar, rotating messages every 15 s (Separando referências… → Aplicando inteligência… → Analisando tendências… → Gerando estruturas… → Personalizando conteúdo… → Finalizando headlines… → Quase pronto…), "Este processo poderá levar de 1 a 2 minutos."; polls `GET headlines/status/{id}` every 20 s | fake progress capped at 90% **C** |
| History table `#myHeadlines` | search, "Excluir Selecionados (N)", columns ☐ · ID · Data · Tipo (`Variavel` + `Type`) · Status (`Criando` created/created_subjected · `Processando` in_subjected/in_gpt/in_gpt2 · `Completo` · `Falha`) · 👁 (enabled when completed/error) · 🗑 | XHR `POST headlines/list` **C** |
| `#modal-view-headline` "Headlines Geradas" | tabs Headlines (+ hidden old-1 / payload / params panes), `#warning-minimum-quantity-structures`, Cancelar · **Reprocessar** | ← `GET headlines/view/{id}` **C** |
| `#modal-edit-headline` "Editar Headlines" | "Edite as Headlines seguindo o exemplo abaixo, ID da estrutura e Headline:" `{{ ID: 123 }} …`; `headlines_edit`; **Adicionar na Box** (`POST /dashboard/box-headlines/add`) | **C** |
| `#modal-make-headlines` | the legacy modal copy (Falar sobre: Meu público / Sobre mim / Assuntos Virais; "Núcleo Especifico:" `specific_core_id` with core ids; "Estrutura de Roteiro:" `structures_category_items[]` = 9 Lista com Argumentação Poderosa; "Gatilho da Atenção:" 2 Recompensa · 3 Mistério · 4 Popularidade / Autoridade · 5 Reconhecimento · 6 Crença · 7 Disrupção; Criatividade objetiva) | **C** |
| Delete modals | "Você realmente deseja deletar estas Headlines?" / "…as headlines selecionadas?" → `POST headlines/delete-multiple`, `GET headlines/delete/{id}` | **C** |

---

## 18 · Headlines Favoritas — `/headlines/favorites` — category `Geração`

- **Params:** `hid={headlineId}` (deep link from a roteiro back to its headline). **C** (code)
- **Purpose:** headlines the user hearted; launch roteiros from them.

Table (XHR `POST headlines/favorites/list`): ☐ · ID · Data · Headline (+ "Roteiro criado" badge) · actions; "Excluir Selecionados". Modals: `#advancedRoadmapModal` (§20; route keys bound to `headlines/favorites/advanced-roadmap/{generate-questions,store,show/{id}}`), `#modal-view-headline`, `#modal-edit-headline`, `#modal-make-headlines`, `#modal-edit-headline-favorite` "Editar Headline e Roteiro" (Headline, Roteiro textarea "Deixe em branco se não quiser alterar o roteiro", tab Fontes da Pesquisa → `POST headlines/favorites/update`), `#modal-favorites-make-roadmap` "Criar Roteiro" (hidden `referer=favorites`, `structure_id`, `headline`, `headline_id`; **"Adicionar Cérebro como fonte de informação:"** `core[]` with **brain ids** 8522 Call de diagnóstico · 8772 História de Criação · 8773 Histórias de Vida do Especialista · 8774 Método do Especialista · 8775 Núcleo de Influência · 9385 Formulário · 9386 Narrativa; **"Adicionar Crenças:"** `core[]` (empty: no `beliefs` brains); dynamic questions; **Gerar Roteiro**), `#modal-show-roadmaps` "Roteiro" (progress **1. Pesquisando** "Estamos pesquisando seus informações para criar o roteiro." · **2. Extraindo Núcleo** "Agora estamos extraindo o seu núcleo de influência..." · **3. Método** "Estamos aplicando o roteiro de acordo com o método..."), `#createRoadmapModalNew` "Criar Roteiro" ("Qual ideia você você quer defender nesse roteiro?" → `POST roadmaps/favorites/store {headline_id, observations}`, then `POST roadmaps/favorites/show-favorites {id}` polled up to 60×), `#viewRoadmapModalNew` "Visualizar Roteiro" (tabs Roteiro / Fontes da Pesquisa), delete modals. Also `POST chat/start` ("Modo chat"). **C**

---

## 19 · Headlines sugeridas — `/headlines/suggested` — category `Geração`

- **Params:** `hid={headlineId}`. **C** (code)
- **Purpose:** headlines generated for the user automatically (daily) or manually (Biblioteca wizard).

Title "Headline sugeridas". Table (XHR `POST headlines/suggested/list`): ☐ · ID · Data · Headline · Mode (Automático/Manual) · actions; row data also carries `Result` (source viral views), `Likes`, `Comments`, `Structure`, `Roadmap`, `EngReversaResultId`, `HeadlineId`. Modals: `#advancedRoadmapModal` (`headlines/suggested/advanced-roadmap/*`), `#modal-edit-headline-suggested` "Editar Headline e Roteiro" (→ `headlines/suggested/update`), `#modal-suggesteds-make-roadmap` "Criar Roteiro" (same brain/belief selects), `#modal-show-roadmaps`, `#createRoadmapModal`, `#viewRoadmapModal`, `#deleteConfirmationModal`, delete modals (`headlines/suggested/delete`, `…/delete-multiple`). Extra endpoints: `GET headlines/suggested/get/{id}`, `POST headlines/create-advanced-roadmap`, `GET roadmaps/reversa/show/{id}`, `POST chat/start`. **C**

---

## 20 · Roteiro Avançado (modal shared by §2, §18, §19, §21) — category `Roteiros`

"Roteiro Avançado — Crie um roteiro avançado em 3 passos". Fields: **Headline** ("Base do roteiro. Se veio de sugerida ou favorita, já está preenchida."), **Instruções** (`observations`; "Tom, público-alvo, o que pode ou não falar. Quanto mais detalhes, melhor."), **Fonte das informações** (Deixe a IA pensar · Link específico · Pesquisar na web — Serper panel with "[PubMed] Incluir artigos científicos", "Quero buscar em português", Traduzir resultados), **Duração do vídeo** (`duration_minutes`: Auto (recomendado) · ~1 · ~2 · ~3 min), **Segundo Cérebro (opcional)** (`core_id`, **core ids**), **Vídeo da biblioteca (opcional)** (`viral_video_id`; library picker with filters Buscar por texto · Formato · Perfil (514) · Views mínimas 100k+/500k+/1M+/5M+ · Likes mínimas 10k+/50k+/100k+/500k+ · Nicho). Hidden: `ai_provider=claude`, `save_to=user_roadmaps|eng_reversa_headlines`, `roadmap_source_type`, `roadmap_use_pubmed`, `is_reprocess`, `chat_resource_id`. States: Criando ("…passa por 2 etapas de análise e pode levar até 2 minutos"), 🔍 Buscando informações na internet, 📋 Selecione os links relevantes ("Selecione até **2** links por categoria"), Gerando perguntas estratégicas..., questions, library, Criado (tabs **Roteiro** / **Fontes da Pesquisa** "Notícias e Fontes Utilizadas"; Copiar Roteiro, Atualizar Roteiro, Copiar Fontes). Endpoints: §24. Details: `frontend-js-analysis.md` §1.7 / §3.4. **C**

---

## 21 · Roteiros — `/roadmaps` — category `Roteiros`

- **Params:** `open_id={roadmapId}` (auto-opens a roteiro after 2.5 s). **C** (code)
- **Sidebar:** Configurações › Roteiros.

Title "Meus roteiros". Table (XHR `POST roadmaps/list`): ☐ · ID · Data (`Date`) · Nome (`Name`) · H. Origem (`Origen`/`Source`) · Status (`Criando` created · `Processando` in_gpt · `Completo` · `Falha`) · actions; "Excluir Selecionados", "Criar roteiro" (opens Roteiro Avançado with an empty headline). Modals: `#advancedRoadmapModal`, `#modal-customer-roadmap-edit-roadmap` "Editar Roteiro" (Quill editor `roadmap_gpt`, `information_additional`; "O que achou deste roteiro?" **Gostei / Não Gostei**; "Não gostou do roteiro?" reason + Enviar), `#modal-roadmap-reprocess` "Reprocessar Roteiro", `#modal-show-roadmaps`, delete modals (`roadmaps/delete-multiple`). Owner: 2 roteiros (41428, 41429). **C**

---

## 22 · Pages referenced in code but outside the user dashboard

`/logout` (POST), `/csrf-token` (GET), `/broadcasting/auth`, `/api/return/integration/ai/chat` (legacy widget), `/dashboard/admin/customers/workspace/create`, `/dashboard/admin/team/workspace/create`, `/dashboard/box-headlines/*`, `/dashboard/make-headlines/*` (agency/admin "customers" layer), `/dashboard/customers`. **C** code, not crawled.

---

## 23 · Page index by category

| Category | Pages |
| --- | --- |
| Shell | Dashboard `/` · shell widgets |
| Geração | Chat `/chat` · Gerar Headlines landing `/headlines/generate` · form `/headlines?who=` · Favoritas · Sugeridas |
| Roteiros | `/roadmaps` · Roteiro Avançado modal |
| Pesquisa | `/searches` (+ `?tab=subject-viral`) · `/searches/extract-profile` |
| Cérebro | `/cores` · `/cores/edit/{id}` · `/cores/questions/{id}` · `/cores/extract` (hidden, legacy) |
| Biblioteca | `/library` (+ `?viral_id`, `?profile`, filters) · `/my-library` |
| Conta | `/profile` |
| Integração | `/profile/instagram` · `/profile/integrations` |
| Treinamento | `/trainings` |

---

## 24 · Route × endpoint matrix

Methods: G = GET, P = POST, S = SSE. **RO** = read-only; **M** = mutates; **AI** = triggers generation/credits. Routes abbreviated: D Dashboard · CH chat · SE searches · EX extract-profile · CO cores · CE cores/edit · CQ cores/questions · CX cores/extract · LI library (all modes) · MY my-library · PR profile · IG profile/instagram · IN profile/integrations · TR trainings · HG headlines/generate · HW headlines?who · HF favorites · HS suggested · RM roadmaps · * = every page.

| Endpoint | M | Kind | Used by |
| --- | --- | --- | --- |
| `notifications` | G | RO | * |
| `notifications/{id}/read`, `notifications/read-all` | P | M | * |
| `workspace/switch` | P | M | * |
| `twin/api/credits` | G | RO | * |
| `first-access-seen` | P | M | * |
| `/csrf-token` | G | RO (token) | * |
| `twin/api/recharges` · `twin/faturamento` | P · G | M (billing) | CH |
| `chat/stream` | S | AI | CH |
| `chat/documents` | P | M | CH |
| `chat/start` | P | M | HF, HS, RM |
| `chat/{id}` (`__ID__` route) | G | RO | D, HF, HS, RM |
| Livewire `document-chat` actions | P | mixed | CH |
| `searches/variables/items?type=` | G | RO | SE |
| `variables/type/{who}` | G | RO | HW, modal copies |
| `searches/variables/contents/add|remove|bulk-delete|empty|empty-all` | P | M | SE |
| `searches/approve-pending-item/{id}` · `reject-pending-item/{id}` | P | M | SE |
| `searches/add-item-prompt` | G | RO | SE |
| `searches/add-item-prompt` · `/test` | P | M · AI | SE (hidden UI) |
| `searches/add-items-sync` · `add-items-job` | P | AI | SE |
| `searches/add-items-job/{jobId}` | G | RO | SE |
| `searches/viral/topics/add|bulk-delete|empty` | P | M | SE |
| `searches/viral/topics/{approve|reject}/{id}` · `remove/{id}` | G | **M (GET)** | SE |
| `searches/viral-data/{topicId}` · `user-variables-viral-data/{id}` | G | RO | SE |
| `searches/approved-profiles` | G | RO | SE, EX |
| `searches/approved-profiles-viral-topics` | G | RO | SE |
| `searches/extract-profile` | P | AI | SE (modals) |
| `searches/extract-profile-status/{jobId}` | G | RO | SE |
| `searches/profile-viral-search/{searchId}` | G | RO | SE, EX |
| `searches/profile-viral-search/save` | P | M | SE, EX |
| `searches/save` · `store` · `view/{id}` · `remove/{id}` · `variables/apply` | P/G | legacy | SE (`searches.js`) |
| `profile/get-niches-professions` | G | RO | SE, EX, LI |
| `cores/custom/add|update` | P | M | CO, CE, CX |
| `cores/custom/delete/{id}` | G | **M (GET)** | CE |
| `cores/questions/save-draft|store|reset` | P | M · AI (store) | CQ |
| `cores/brain-status/{coreId}` | G | RO | CQ |
| `cores/update` · `upload-audio-chunk` | P | M | CE (`brains.js`, voice — dormant) |
| `cores/upload-file` | P | M | CE |
| `cores/youtube/extract` | P | AI | CE |
| `cores/youtube/status/{jobId}` | G | RO | CE |
| `cores/extract/list` | P | RO (DataTables) | CX |
| `cores/transcrible` | P | AI | CX |
| `cores/view/{id}` | G | RO | CX |
| `cores/remove/{id}` | G | **M (GET)** | CX |
| `library/result/{id}` | G | RO | LI |
| `library/result/{id}/core` | P | M (staff) | LI |
| `library/workspaces` | G | RO | LI |
| `library/viral-topics` | P | RO (lookup) | LI |
| `library/videos?…` | G | RO | roadmap picker (D, HF, HS, RM) |
| `library/profiles?profile=` | G | RO | MY |
| `library-references/self-assign` | P | M | LI, MY |
| `library-references/{id}` (`_method=DELETE`) | P | M | MY |
| `my-library/check-profile?profile=&social=` | G | RO | MY |
| `my-library/requests` | G | RO | MY |
| `my-library/request-virals` | P | M | MY |
| `profile/save` | P | M | PR |
| `profile/instagram/posts/all` | G | RO | IG (dormant UI) |
| `profile/instagram/posts/set` | P | M | IG (dormant UI) |
| `profile/integrations/delete` | G | **M (GET)** | IN |
| `headlines/profiles` | G | RO | D, HW |
| `headlines/get-profile` | P | RO (lookup) | `headlines.js` |
| `headlines/get-variables-values` | P | RO (lookup) | HW, modal copies |
| `headlines/store` · `store-custom-subject` | P | AI | HW, modal copies |
| `headlines/status/{id}` | G | RO | D, HW |
| `headlines/list` | P | RO (DataTables) | HW |
| `headlines/view/{id}` | G | RO | HW |
| `headlines/reprocess/{id}` | G | **AI (GET)** | HW |
| `headlines/delete/{id}` | G | **M (GET)** | HW |
| `headlines/delete-multiple` | P | M | HW |
| `headlines/like` · `unlike` | P | M | HW |
| `headlines/generate-sugeridas-day` | P | **AI, fires on every page that loads `headlines.js`** | D, HW, HF |
| `headlines/favorites/list` | P | RO (DataTables) | HF |
| `headlines/favorites/get/{id}` · `get-questions` | G · P | RO | HF |
| `headlines/favorites/update` · `delete/{id}` (G) · `delete-multiple` | P/G | M | HF |
| `headlines/{favorites|suggested}/advanced-roadmap/generate-questions` | P | AI | HF, HS, D, RM |
| `headlines/{favorites|suggested}/advanced-roadmap/store` | P | AI | HF, HS, D, RM |
| `headlines/{favorites|suggested}/advanced-roadmap/show/{id}` | G | RO | HF, HS |
| `headlines/suggested/advanced-roadmap/list-search` | P | AI (LLM + Serper) | D, HF, HS, RM |
| `…/direct-search` · `translate-search-query` · `translate-search-results` | P | AI/paid API | D, HF, HS, RM |
| `headlines/suggested/list` | P | RO (DataTables) | HS |
| `headlines/suggested/get/{id}` · `view/{id}` | G | RO | HS, D |
| `headlines/suggested/update` · `delete` · `delete-multiple` | P | M | HS, D |
| `headlines/suggested/store` | P | AI | LI |
| `headlines/create-advanced-roadmap` | P | AI | HS |
| `headlines/reversa/update` | P | M | D |
| `roadmaps/list` | P | RO (DataTables) | RM |
| `roadmaps/view/{id}` · `check-status/{id}` | G | RO | RM, D |
| `roadmaps/check-progress` | P | RO (poll) | `roadmaps.js` |
| `roadmaps/store` | P | AI | HF, HS (legacy) |
| `roadmaps/update` · `setFeedback` · `set/reason` · `delete-multiple` | P | M | RM, D, HF, HS |
| `roadmaps/delete/{id}` | G | **M (GET)** | RM |
| `roadmaps/reprocess` · `get-question-roadmap` | P | AI · RO | RM |
| `roadmaps/favorites/store` | P | AI | HF |
| `roadmaps/favorites/show-favorites` | P | RO (poll) | HF |
| `roadmaps/reversa/store` | P | AI | D |
| `roadmaps/reversa/show/{id}` | G | RO | HS |
| `mamanai/proccess` | P | AI (dead UI) | D |
| Echo `questions-validation.{env}.user.{id}` `.validation-completed` | WS | — | CQ |
| Echo `chat.{env}.user.{id}` `.nova-mensagem` | WS | — | legacy widget (`app` bundle) |

---

## 25 · Referenced but not crawled (or crawled without saved HTML)

| Item | Why it matters |
| --- | --- |
| `/headlines?who=viral` (and `who=search`) | the Assuntos Virais / busca inteligente variants; same template, server state differs |
| `/chat?c={uuid}` for the other 14 conversations; `/chat?cite_viral=`, `?cite_profile=` | composer pre-fill behavior |
| `/cores/edit/3741`, `/4191`, `/4192` (headings in `inventory.json`, HTML not saved) | custom-brain editor markup and content structure |
| `/cores/questions/9`, `/14` (saved as `cores_edit_9/14`, redirect targets) — **saved**; `/cores/questions/3741…` | n/a (custom brains have no questionnaire) |
| `/library?viral_id=` for 27 of 30 IDs (inventory only), library pages 11–13 and 272–279 (inventory only) | same template; JSON detail needed instead |
| `/library?view_all=1`, `?core=1`, `?viral_result_id=` | unfiltered corpus size; gold-standard set; direct card render |
| `/roadmaps?open_id=`, `/headlines/{suggested|favorites}?hid=`, `/cores?brain_synced=1`, `/dashboard/user?filter=` | deep-link behaviors |
| `/profile/instagram?period=…` | period values unknown |
| `/twin/faturamento` | billing (out of scope) |
| Sidebar sections **Avatar**, **Estudio de Edicao** | present only as Blade comments; plan-gated or retired |
| Instagram connect URL (`#start-integration`) | only rendered when no account is connected |
| `#modal-box-headlines-save` (Box → customer/week) | agency flow |
