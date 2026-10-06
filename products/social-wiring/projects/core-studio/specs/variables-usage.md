# CoreStudio — Research-variable USAGE MAP ("Pesquisa" variables)

Read-only analysis of the locally saved pages, JS, API captures and the 29 chat transcripts, plus the coordinator's live notes (`live/variables-live.md`, `live/add-item-prompt.md`).

**Evidence tags:** **[OBS]** = seen in a saved file (path given). **[LIVE]** = seen in the live read-only session (`live/variables-live.md`), treated as observed. **[INF]** = inference from code shape, not seen working.

Personal data is left out on purpose. Creator handles are written as `@<perfil>`, and the names of the clients in the transcripts are not repeated.

---

## 0 · TL;DR

1. **There are two slug vocabularies, and they do not match.**
   - The **DB slugs** come in the `ID|SLUG` option values. There are 29 of them: 17 avatar and 12 especialista. They show up in `variables/type/{who}` [LIVE] and in the static `<option value="18|DESEJOS-TANGIVEIS-DO-AVATAR">` lists in `pages/dashboard.html`, `pages/headlines~suggested.html` and `pages/headlines~favorites.html` [OBS].
   - The **classifier prompt slugs** are 13 `{{SLUG}}`s, all about the avatar (`live/add-item-prompt.md`). Five of them match a DB slug exactly. One is the same concept spelled differently. Seven have no DB variable.
2. **Gerar Headlines reads research directly.** You pick variables from `variables/type/public|me`. The server then returns your *approved* items for each picked variable (`get-variables-values` → `variable_values[]`) and suggests reference profiles (`get-profile`) [OBS code + LIVE].
   - Generation is **structure (template) driven.** Each variable carries a `data-has-structures` flag [LIVE]. The result reports `structure_count`, and the UI warns when there are "poucas estruturas compatíveis" (`js/headlines.js`) [OBS].
3. **The chat can inject research items.** The `@` mention modal has a **"Minha Pesquisa"** tab with the chips `Meu Público` / `Sobre mim` and a variable filter. It uses Livewire `searchMyResearch` and `getResearchVariables` (`js/app-DLOM2UdR.js`, `pages/chat.html`) [OBS].
   - **None of the 29 saved conversations uses it.** All 28 `@` mentions in user messages are profile references (`@<perfil> - Todos os vídeos`).
   - So the transcripts give **no evidence** of a research item (desire, pain, known person and so on) being injected into a generated headline.
4. **Superseded 2026-10-06.** Headline templates with `{{SLUG}}` placeholders do exist: they are the per-viral **blueprints** in suggested-headline payloads. Their slots are DB slugs plus `{{GPT}}` (see `prompts/headline-engenharia-reversa-DRAFT.md` §3 and `mechanisms.md` §5.7). The points below describe the 2026-10-05 files only.
   **No headline template text with `{{SLUG}}` placeholders exists in any saved file (2026-10-05).**
   - The only `{{SLUG}}`s anywhere are in the classifier prompt.
   - The HEADLINE agent cites structures by numeric ID: `(estrutura #NNNNNN)` appears 190 times, covering 52 distinct IDs.
   - The agent paraphrases these structures with generic `X/Y` or `[característica do avatar]` slots (§3).
5. **The four global variables** (22 Verbos Poderosos, 23 Adjetivos Poderosos, 24 Momento do dia, 29 GPT) appear **only** as labels and options of the Minha Pesquisa filter. Nothing reads them. They look dead from the client side, but server-side use is unknown.
6. **Seven classifier-only slugs** have no UI variable, no `ID|SLUG` option and no reading surface: FRUSTRACOES, CRENCAS-LIMITANTES, INIMIGO-COMUM, MECANISMO-UNICO, PROMESSA-PRINCIPAL, PROVA-SOCIAL and NICHO-OU-MERCADO. Where their classified lines end up is unknown.

---

## 1 · Reading surfaces (what reads research variables)

| # | Surface | Call / mechanism | Which variables | Evidence |
|---|---|---|---|---|
| S1 | **Minha Pesquisa** list (`/dashboard/user/searches`) | `GET /dashboard/user/searches/variables/items?type=especialista` + `?type=avatar`; filter `#unified-variable-filter` | All 33 ids are in the filter and labels. Only avatar and especialista items are fetched. | `pages/searches.html`: `fetch('/dashboard/user/searches/variables/items?type=especialista'), fetch('/dashboard/user/searches/variables/items?type=avatar')`; `window.unifiedVariableLabels = {…"22":"Verbos Poderosos","23":"Adjetivos Poderosos","24":"Momento do dia","29":"GPT"}` |
| S2 | **Inserir itens na pesquisa** (AI classifier) | `GET searches/add-item-prompt` → `POST add-items-sync` / `add-items-job` | 13 classifier slugs (avatar only) | `live/add-item-prompt.md` (verbatim prompt) |
| S3 | **Extrair Pesquisa** (`/searches/extract-profile`) → `profile-viral-search/{id}` | returns `data:[{variable_id, variable_name (SLUG), label, items[...]}]`; `profile-viral-search/save` | The DB slugs. Seen live: 1, 3, 10, 15, 17, 18, 19, 34 | `spec-pesquisa-cerebro.md` §9 |
| S4 | **Gerar Headlines** "Selecionar Assuntos:" (`#make-headlines-select-variables-user`, `name="variables_id[]"`) | `GET /dashboard/user/variables/type/{who}` → `content_option` `<option value='ID|SLUG' data-has-structures>` | `who=public` → 17 avatar, `who=me` → 12 especialista. `especialista`/`avatar`/`global` → null | `js/headlines.js`: `url: '/dashboard/user/variables/type/' + who`; `live/variables-live.md` |
| S5 | Gerar Headlines → **values of each chosen variable** | `POST dashboard/user/headlines/get-variables-values {customer_id, variables}` → per-variable multi-select "Valor das variável: «SLUG»:" `variable_values[]` (value `varId|content`) | Whichever variables were selected. Shows the user's **approved** items (Dores → 24 options = approved count) | `js/dashboard.js`: `url: … 'get-variables-values', data: { customer_id: customer_id, variables: variables }`; `live/variables-live.md` |
| S6 | Gerar Headlines → **reference profiles** | `POST /dashboard/user/headlines/get-profile {variable_selected[]}` → `profiles[{search_id, profile}]` → "Perfil de Referência (máximo 2):" / "Modelagem de um Perfil" | Whichever variables were selected | `js/headlines.js`: `url: "/dashboard/user/headlines/get-profile", … data: { variable_selected: variables` ; empty → `'Nenhum perfil compatível encontrado'` |
| S7 | Gerar Headlines modal **copies** on Headlines sugeridas / favoritas | Same `#make-headlines-select-variables-user`, but labelled "**Selecionar Gatilhos:**" with placeholder "Selecione o gatilho que deseja gerar". 17 avatar options are server-rendered | 17 avatar ids. Sobre-mim options only after the `who` change → S4 | `pages/headlines~suggested.html` / `headlines~favorites.html`: `<option value="8|CRENCAS-DO-AVATAR">Crenças do meu público </option>` |
| S8 | **Chat `@` → "Minha Pesquisa" tab** | Livewire `searchMyResearch(q, group, page, sort, variable)` + `getResearchVariables(group)`; group chips `Meu Público` / `Sobre mim`; `<select class="dc-research-var-select">` "Todas as categorias"; chosen item → `attachReference(id, source)` | Avatar and especialista. Group strings are `'Meu Público'` / `'Sobre mim'` | `js/app-DLOM2UdR.js`: `this.mentionActiveTab==="research"?await this.$wire.searchMyResearch(l,this.researchGroupFilter,d,this.researchSortFilter,this.researchVariableFilter)`; `pages/chat.html`: `@click="switchResearchGroup('Sobre mim')"` |
| S9 | **Chat agent tools** (server-side RAG, shown as trace labels) | `consultar_variaveis_perfil` "📊 Consultando variáveis do perfil"; `gerar_headlines.find_variables` / `validate_variables` (FindVariables / ValidateVariables); `find_templates` / `validate_templates`; `find_triggers` / `validate_triggers`; `consultar_pesquisa_viral` "🔥 Consultando pesquisa viral"; `nucleo_influencia` | Unknown which variables. The tool names imply the agent reads profile variables and picks templates and variables [INF] | `js/app-DLOM2UdR.js` `toolLabels` / `toolClassMap` |
| S10 | Biblioteca "Gerar headline" wizard → `headlines/suggested/store` | `variable_contents[{variable_name:'ASSUNTOS_VIRAIS', content, viral_topic_id, user_variable_id:null, additional_content:null}]` | Only the pseudo-variable `ASSUNTOS_VIRAIS`. The `user_variable_id` field exists but this UI always sends `null` | `pages/library.html`: `variable_name: 'ASSUNTOS_VIRAIS', … user_variable_id: null` |
| S11 | Legacy agency "make-headlines" (`dashboard/make-headlines/get-variables-type`, `get-variables`, `get-variables-values`, `get-structures/{clientId}`) | per customer `variable_type_id` → variables → values | Per customer. Not the user Pesquisa [INF] | `js/dashboard.js`; `js-analysis.md` §(make-headlines) |
| — | Roteiro forms (`roadmaps.js`, `advanced-roadmap-modal.js`), Profile, Meu Cérebro | — | **No research variable is read.** Roteiro inputs are headline, structure_id, brain (`core_id`), observations and web/PubMed sources | `js/roadmaps.js` (0 hits); `data.json .roteiros[].params` keys = `headline_text, ai_provider, mode, save_to, observations, roadmap_source_type, roadmap_use_pubmed, …` — no variable fields |
| — | Dashboard home / suggested-headlines table | Suggested rows = `Result, Likes, Comments, Mode, Data`; favorites = `ID, User, Headline, Structure, Roadmap, EngReversaResultId` | No variable column | `work/sug-dt.js`, `work/fav-dt.js` |

---

## 2 · "Gerar Headlines" — form fields, options, and Meu Público vs Sobre mim

### 2.1 Entry (landing `/dashboard/user/headlines/generate`) [OBS `pages/headlines~generate.html` + LIVE]
There are three cards, which lead to `/headlines?who=…`:
- **Sobre mim**: "Headlines com base nas suas convicções, hábitos e histórias de vida."
- **Sobre meu público**: "…dores, desejos, crenças e demais características do seu público alvo."
- **Assuntos do Virais**: "Headlines com assuntos em alta que conectam com o seu público-alvo."

### 2.2 Current form (live; `form#make-headlines-me` in `pages/dashboard.html`) [OBS + LIVE]

| Field | name / id | Options (verbatim) | Data source |
|---|---|---|---|
| Falar sobre (hidden older header; the live page picks it from the landing card) | `who` radio | `public` "Meu público" · `me` "Sobre mim" · `viral` "Assuntos Virais" ("Digite um assunto personalizado"). JS also knows `ai`, `choose`, `search`, `subject-moment` | static |
| **Selecionar Assuntos:** | `variables_id[]` `#make-headlines-select-variables-user` (multi, TomSelect) | "Selecione o assunto que deseja gerar" · `all` "Todos"/"Todas" · `ID\|SLUG` per variable (§4). Loading "Carregando assuntos…"; error option "Erro ao carregar a lista de assuntos." | `GET variables/type/{who}` |
| Valor das variável: «SLUG»: (one per selected variable) | `variable_values[]` (value `varId\|content`) | the user's **approved** research items for that variable | `POST headlines/get-variables-values` [LIVE; code in `js/dashboard.js`] |
| Selecione o Assunto: | `assuntos[]` `#make-headlines-select-assuntos-user` | "Selecione o assunto personalizado" · `all` "Quero escolher outro assunto" | viral topics (Blade) |
| **Quero criar headlines com base em:** (Opções Avançadas) | radio | **Modelagem de um Perfil** · **Formato de Roteiro** · **Gatilho da Atenção** (tooltip "Crie headlines com base nos gatilhos da atenção que mais se encaixam na sua comunicação") | [LIVE] |
| ↳ Perfil de Referência (máximo 2): | `profile_ids[]` / `#make-headlines-profiles-me-public` | profiles returned by `get-profile` for the selected variables; "Nenhum perfil compatível encontrado"; free entry `new:<handle>` | `POST headlines/get-profile {variable_selected[]}` |
| ↳ Formato do Vídeo: | `format_video_ids[]` | 1 Lista de Valor Prático · 2 Lista de Pontos de Identificação · 3 Lista de Crenças · 4 Mistério · 5 Comparação · 6 Tutorial · 7 Análise do Mundo e Novas Tendências · 8 Histórias Pessoais · 9 Histórias de Terceiros · 10 Fatos Curiosos · 11 Metáforas e Analogias · 12 Assunto do Momento · 13 Defesa de Crença Forte · 14 Palavras de Motivação · 15 Websérie (definitions in `data.json .formats`) | Blade |
| ↳ Gatilho da Atenção: | `structures_category_items[]` `#make-headlines-select-4` | 2 Recompensa · 3 Mistério · 4 Popularidade / Autoridade · 5 Reconhecimento · 6 Crença · 7 Disrupção | Blade |
| Estrutura de Roteiro: (older advanced block) | `structures_category_items[]` `#make-headlines-select-3` | 9 Lista com Argumentação Poderosa | Blade |
| Tom de Comunicação: (subject-moment step) | `structures_category_items[]` | 10 Chocante e Disruptiva · 11 Futuro e Possibilidades · 12 Curiosidade e Mistério · 13 Cultura e Sociedade · 14 Crítica e Denúncia · 15 Reflexão e Profundidade | Blade |
| Núcleo Especifico: | `specific_core_id` | "Selecione os itens" + brains (8 História de Criação · 9 Histórias de Vida do Especialista · 14 Método do Especialista · + user brains) | Blade |
| toggle | ? | "**Criar as headlines usando apenas os itens da minha pesquisa.**" | [LIVE]. The field name was not captured |
| Criatividade objetiva: | `thermometer` range 0–100, default 50 | Essencial "(Só formatos pré-selecionados e validados)" · Equilibrado "(50% formatos validados e 50% ideias criativas variadas)" · Explorador "(100% ideias criativas e diferentes dos formatos pré-selecionados)" | static |
| Submit | → `POST /dashboard/user/headlines/store` (form `#make-headlines-me`, + `who`, `add_input=1`, `input_user`) or `store-custom-subject` (viral form) | "Gerar Headlines" | `js/headlines.js` |

The older modal variant (on Headlines sugeridas and favoritas) has these differences: "**Selecionar Gatilhos:**" instead of "Selecionar Assuntos:"; `add_input` radio "Usar assuntos da pesquisa / Usar minha própria pesquisa" (1) vs "Escolher um assunto agora / Digite sobre o que você deseja falar" (2, textarea `input_user`); and "Criatividade:" noUiSlider 0–10 ("quanto mais alto, mais criativo… Quanto mais baixo, mais respeitará seu gosto de Headlines"). [OBS `pages/headlines~suggested.html`]

### 2.3 How Meu Público vs Sobre mim affect generation (facts only)
- `who` selects **which variable set is offered**: `public` gives the 17 `*-DO-AVATAR` variables and `me` gives the 12 `*-DO-ESPECIALISTA` variables (`variables/type/{who}`) [LIVE]. `who` is also posted with the form (`formData.append('who', whoValue)`, `js/headlines.js`) [OBS].
- **Structure availability depends on the variable.** All 17 avatar variables are `data-has-structures=1`. On the especialista side, at least `27 CARACTERISTICAS-NEGATIVAS-DO-ESPECIALISTA` is `has-structures=0` and is labelled "(Sem estruturas disponíveis)" [LIVE]. Per the live note, this is the only `0`; exact flags for every `me` id should be re-checked (§7).
- The values offered under each variable come from the user's own approved items. The account owner has **0 especialista items** (spec §9: "12 especialista keyed (all empty)"), so on this account "Sobre mim" generation has no item values to offer.
- In chat, the same split is the `researchGroupFilter` (`'Meu Público'` by default, or `'Sobre mim'`), passed to `searchMyResearch` and `getResearchVariables` [OBS].
- **What the server does differently per `who` (prompt wording, which template pool) is not visible in any file.**

---

## 3 · Headline template / structure library — what exists in the files

- **No template text with `{{SLUG}}` or `ID|SLUG` placeholders is present in any saved file.** A full-tree search for `{{…}}` finds only the classifier prompt. A search for bracket placeholders finds only one: `[característica do avatar]`.
- Structures are referenced **by numeric id**:
  - Favorites carry `Structure` / `structure_id` (`work/fav-dt.js`; `like` posts `structure_id`).
  - Roteiro prompts use `Crie um roteiro para a headline: "{headline}" (estrutura_id: {id})` (`js-analysis.md`).
  - The HEADLINE chat agent suffixes every headline with `(estrutura #NNNNNN)`: **190 occurrences, 52 distinct IDs** in `convs.txt`, all in the ~124xxx–152xxx range.
  - That range overlaps viral-video ids such as `viral_id 115244` in `data.json`. [INF] Structures may be keyed to library videos; not determined.
- Structure paraphrases **stated by the agent** in `convs.txt` (agent wording, not the server's template text):

| Structure ID | Trigger stated by agent | Pattern, verbatim as the agent wrote it | convs.txt line |
|---|---|---|---|
| 124688 | Disrupção | "X não destrói — ele só revela o que já estava quebrado" (original: "A fama não destrói ninguém. Ela só revela o que já estava quebrado.") | 830, 4864 |
| 124672 | Disrupção + Mistério | "X não mostra quem você é — ele apaga quem deveria te proteger" ("O álcool não mostra quem você é") | 928, 4865 |
| 127972 | Disrupção + Mistério | "X não escolhe Y, mas outro tipo que você já imagina" | 4866 |
| 124680 | Mistério + Recompensa | "Pouca gente sabe, mas existe X que acaba de vez com Y" | 932, 4867 |
| 127970 | Disrupção + Autoridade | "A pessoa que mais te ama..." | 936 |
| 147243 | Reconhecimento + Mistério | "Se você tem **[característica do avatar]**, esta é a forma cirúrgica de destruir **[algo valioso]**" | 4964 |
| 147089 | Reconhecimento | "Se você tem filhos com menos de 13 anos, esta é a forma cirúrgica..." | 4977 |
| 149271 | Reconhecimento | "Todo pai que não quer que seus filhos tenham uma vida mediana deveria..." | 4977 |
| 149157 | — | "E o gesto dela é exatamente o que falta" | 4962 |

- `[característica do avatar]` (147243) is the **only** place where a template slot is named after a research concept. It maps by meaning to 16 CARACTERISTICAS-DEMOGRAFICAS / 25 / 26. The actual slot token used server-side is unknown.
- **Roteiro structures** are sequences of blocks, not variable slots. Example: "Headline · Intensificador do Mistério · CTA de Salvar · Fatos Curiosos / Notícias · Opinião Polêmica · Pontos de Identificação · Provas e Argumentações · CTA de Compartilhar · Apresentação Magnética · CTA de Comentar/Seguir" (convs.txt ~3720, "ESTRUTURA-PADRÃO … extraída da engenharia reversa").
- **Video formats** (15, `data.json .formats`) have `definition / signals / alias` fields and no variable fields.

---

## 4 · Per-variable usage table

Surface codes are from §1:
- S1 Minha Pesquisa
- S2 AI classifier
- S3 Extrair Pesquisa
- S4 Gerar Headlines subject select
- S5 approved values (`variable_values[]`)
- S6 reference profiles
- S7 copy of the modal on sugeridas/favoritas
- S8 chat @Minha Pesquisa
- S9 chat agent tools (variables unspecified)

"Owner items" = approved/pending counts for the account owner (spec §9), shown where known.

### 4.1 Meu Público (type `avatar`, `who=public`, all `has-structures=1`)

| id | label (verbatim) | DB slug | classifier slug | where read | how used by AI | evidence | status |
|---:|---|---|---|---|---|---|---|
| 18 | Desejos do meu público | DESEJOS-TANGIVEIS-DO-AVATAR | `{{DESEJOS-TANGIVEIS-DO-AVATAR}}` (exact) | S1 S2 S3 S4 S5 S6 S7 S8 S9 | Classifier target ("Resultados concretos que o avatar quer alcançar"). Headline values via S5. Has structures | `pages/dashboard.html` `18\|DESEJOS-TANGIVEIS-DO-AVATAR`; extraction seen live (18); owner 33 approved / 70 pending | used |
| 17 | Dores do meu público⎵ | DORES-TANGIVEIS-DO-AVATAR | `{{DORES-TANGIVEIS-DO-AVATAR}}` (exact; top of the tie-break order) | S1–S9 | Classifier ("Problemas concretos que o avatar vive agora"). S5 rendered 24 options = approved count [LIVE] | owner 24/36 | used |
| 16 | Características demográficas do meu público | CARACTERISTICAS-DEMOGRAFICAS-DO-AVATAR | `{{CARACTERISTICAS-DEMOGRAFICAS-DO-AVATAR}}` (exact) | S1 S2 S4 S5 S6 S7 S8 S9 | Classifier ("Gênero, idade, profissão…"). The agent paraphrased structure 147243 with slot "[característica do avatar]" | owner 5 approved | used |
| 25 | Qualidades do meu público | CARACTERISTICAS-POSITIVAS-DO-AVATAR | — | S1 S4 S5 S6 S7 S8 | Has structures. Not in the classifier, so it is filled only by extraction or manual add | options list | used (no owner items seen) |
| 26 | Defeitos do meu público | CARACTERISTICAS-NEGATIVAS-DO-AVATAR | — | S1 S4 S5 S6 S7 S8 | same as 25 | options list | used (no owner items seen) |
| 15 | Itens conhecidos pelo meu público | ITENS-CONHECIDOS-PELO-AVATAR | — | S1 S3 S4–S8 | Has structures. Extraction seen live (15) | owner 12/26 | used |
| 14 | Instituições conhecidas pelo meu público | INSTITUICOES-CONHECIDAS-PELO-AVATAR | — | S1 S4–S8 | Has structures | owner 11/18 | used |
| 13 | Pessoas e personagens conhecidos pelo meu público | **PESSOAS-PERSONAGENS-CONHECIDOS-PELO-AVATAR** | `{{PESSOAS-E-PERSONAGENS-CONHECIDOS-PELO-MEU-PUBLICO}}` (**spelling differs**) | S1 S2 S4–S8 | Classifier example: "A princesa Sofia" → this slug. The convs contain no case of a research person being injected. "Charlie Munger" appears in an agent headline, but it was copied from the user's own pasted script (convs.txt 1673 → 1780) | owner 8 approved | used |
| 32 | Inimigos do meu público⎵ | INIMIGOS-DO-AVATAR | ≈ `{{INIMIGO-COMUM}}` (different slug and name) | S1 S4–S8 | Has structures | options list | used (no owner items seen) |
| 11 | Filmes, séries ou músicas conhecidas pelo meu público | FILMES-SERIES-E-MUSICAS-CONHECIDAS-PELO-AVATAR | — | S1 S4–S8 | Has structures | options list | used (no owner items seen) |
| 19 | Eventos conhecidos pelo meu público⎵ | EVENTOS-CONHECIDOS-PELO-AVATAR | — | S1 S3 S4–S8 | Extraction seen live (19) | options list | used |
| 20 | Locais conhecidos pelo meu público | LOCAIS-CONHECIDO-PELO-AVATAR (sic, singular) | — | S1 S4–S8 | Has structures | options list | used (no owner items seen) |
| 21 | Momentos de vida do meu público | MOMENTO-DE-VIDA-DO-AVATAR | — | S1 S4–S8 | Has structures | options list | used (no owner items seen) |
| 10 | Objeções do meu público⎵ | OBJECOES-DO-AVATAR | `{{OBJECOES-DO-AVATAR}}` (exact) | S1 S2 S3 S4–S8 | Classifier ("Barreiras e dúvidas…") | owner 1 approved | used |
| 9 | Medos do meu público | MEDOS-DO-AVATAR | `{{MEDOS-DO-AVATAR}}` (exact) | S1 S2 S4–S8 | Classifier ("Cenários futuros negativos…") | owner 2 approved | used |
| 8 | Crenças do meu público⎵ | CRENCAS-DO-AVATAR | ≈ `{{CRENCAS-LIMITANTES-DO-AVATAR}}` (different slug and narrower meaning) | S1 S4–S8 | Has structures | owner 12 approved | used |
| 34 | Produtos conhecidos pelo meu público | PRODUTOS-CONHECIDOS-PELO-AVATAR | — | S1 S3 S4–S8 | Extraction seen live (34) | options list | used |

### 4.2 Sobre mim (type `especialista`, `who=me`)
The owner has 0 items in every especialista variable (spec §9). None of these has a classifier slug, so the AI add path can never produce them. They are filled only by extraction (S3) or by manual add with the prompt inactive (Mode B).

| id | label (verbatim) | DB slug | where read | how used by AI | evidence | status |
|---:|---|---|---|---|---|---|
| 5 | Desejos e conquistas que eu realizei⎵ | DESEJOS-ALCANCADOS-PELO-ESPECIALISTA | S1 S4(me) S5 S6 S8(Sobre mim) | headline variable (`who=me`) | live list | used (owner empty) |
| 4 | Situações dolorosas que eu enfrentei⎵ | SITUACOES-DOLOROSAS-DA-VIDA-DO-ESPECIALISTA | same | same | live list | used (owner empty) |
| 30 | Meus hábitos e hobbies⎵ | HABITOS-DO-ESPECIALISTA | same | same | live list | used (owner empty) |
| 31 | Minha formação profissional⎵ | FORMACAO-PROFISSAO-DO-ESPECIALISTA | same | same | live list | used (owner empty) |
| 28 | Quem eu sou (idade, estado civil, nacionalidade, etc) | CARACTERISTICAS-DEMOGRAFICAS-DO-ESPECIALISTA | same | same | live list | used (owner empty) |
| 7 | Minhas qualidades | CARACTERISTICAS-POSITIVAS-DO-ESPECIALISTA | same | same | live list | used (owner empty) |
| 27 | Meus defeitos | CARACTERISTICAS-NEGATIVAS-DO-ESPECIALISTA | S1 S4(me) S8 | **has-structures=0**, labelled "(Sem estruturas disponíveis)", so headlines cannot be generated from it | live list | listed but not generatable |
| 6 | Técnicas, serviços e procedimentos que eu efetuo⎵ | TECNICAS-E-PROCEDIMENTOS-EFETUADOS-PELO-ESPECIALISTA | S1 S4(me) S5 S6 S8 | headline variable | live list | used (owner empty) |
| 12 | Técnicas, serviços e procedimentos que eu não recomendo | TECNICAS-PROCEDIMENTOS-NAO-RECOMENDADOS-PELO-ESPECIALISTA | same | same | live list | used (owner empty) |
| 3 | Hábitos que eu recomendo para o meu público | HABITOS-RECOMENDADOS-PELO-ESPECIALISTA | S1 **S3** S4(me) S5 S6 S8 | headline variable. Also produced by profile extraction (seen live) | spec §9 (`variable_name` seen in profile-viral-search) | used |
| 2 | Hábitos que eu não recomendo para o meu público⎵ | HABITOS-NAO-RECOMENDADOS-PELO-ESPECIALISTA | S1 S4(me) S5 S6 S8 | headline variable | live list | used (owner empty) |
| 1 | Crenças e ideias que eu defendo | CRENCAS-DO-ESPECIALISTA | S1 **S3** S4(me) S5 S6 S8 | headline variable. Also produced by extraction | spec §9 | used |

### 4.3 Global (type `null`)

| id | label | slug | where read | how used by AI | evidence | status |
|---:|---|---|---|---|---|---|
| 22 | Verbos Poderosos | none seen | S1 filter option + label map only | none visible | `pages/searches.html` `<option value="22">Verbos Poderosos</option>` and `unifiedVariableLabels`. Not in `variables/type/public\|me` [LIVE]. `variables/items` fetches only avatar/especialista, so the filter always shows "Nenhum item encontrado." | **unused client-side** (server use unknown) |
| 23 | Adjetivos Poderosos | none seen | same | none visible | same | **unused client-side** |
| 24 | Momento do dia | none seen | same | none visible | same | **unused client-side** |
| 29 | GPT | none seen | same | none visible | same | **unused client-side** |

`variables/type/global` returned `null` [LIVE]. The names (powerful verbs and adjectives, time of day) would fit as template fillers, but **no file shows them used**. [INF]

### 4.4 Classifier-only slugs (in `prompt_system`, no UI variable)

| slug | classifier meaning (verbatim) | closest UI variable (by name/meaning) | where read | status |
|---|---|---|---|---|
| FRUSTRACOES-DO-AVATAR | "Tentativas passadas que falharam" | none (example "já tentei várias dietas") | S2 output only | **unknown**: no `ID\|SLUG`, no filter option. Storage target unseen |
| CRENCAS-LIMITANTES-DO-AVATAR | "Crenças internas negativas sobre si mesmo" | 8 CRENCAS-DO-AVATAR "Crenças do meu público" | S2 only | unknown |
| INIMIGO-COMUM | "Vilão externo que o avatar culpa" | 32 INIMIGOS-DO-AVATAR "Inimigos do meu público" | S2 only | unknown |
| MECANISMO-UNICO | "Método ou sistema que diferencia a solução" | none in Pesquisa. By meaning, near 6 TECNICAS-E-PROCEDIMENTOS-EFETUADOS-PELO-ESPECIALISTA and the brain "Método do Especialista" (core 14) | S2 only | unknown |
| PROMESSA-PRINCIPAL | "Transformação central prometida" | none | S2 only | unknown |
| PROVA-SOCIAL | "Resultados de terceiros, números, autoridade" | none in Pesquisa (near 5 DESEJOS-ALCANCADOS-PELO-ESPECIALISTA "conquistas") | S2 only | unknown |
| NICHO-OU-MERCADO | "Área ou segmento do produto" | none in Pesquisa. The profile has Nichos (`profile-filter-niche`, spec §5.3) | S2 only | unknown |

The classifier slugs that **do** map are 16, 17, 18, 9 and 10 (exact) plus 13 (spelling variant). These are listed in §4.1. The classifier has **no especialista slug at all**.

---

## 5 · How the AI uses research — evidence summary

| Mechanism | What is visible | Evidence | Determined? |
|---|---|---|---|
| Classifier (Inserir itens) | Line → `{{SLUG}}` + `[literal text]`. Tie-break: DORES > MEDOS > FRUSTRACOES > OBJECOES > CRENCAS-LIMITANTES > DESEJOS. Output is variable/content pairs only | `live/add-item-prompt.md` | yes (prompt verbatim). The slug → variable_id map is server-side and unseen |
| Gerar Headlines | Selected `variables_id[]` (`ID\|SLUG`) + `variable_values[]` (`varId\|content`) + optional profiles / format / trigger / brain / thermometer are POSTed. Output count is capped by the number of compatible **structures** | `js/headlines.js` (`structure_count`, warning texts); LIVE `data-has-structures` | Inputs yes. The prompt and template-filling logic are **not** visible |
| Toggle "usar apenas os itens da minha pesquisa" | Implies that, when off, the generator may go beyond the user's items | LIVE label only | semantics unknown |
| Chat @Minha Pesquisa | User-selected items are attached as references (`attachReference(id, source)`) and appear inline as `dc-mention-tag` | `js/app-DLOM2UdR.js` | Mechanism yes. Prompt injection format unknown. **0 uses in the 29 convs** |
| Chat agent tools | `consultar_variaveis_perfil`, `gerar_headlines.find_variables` / `validate_variables`, `find_templates`, `find_triggers`, `consultar_pesquisa_viral` | `js/app-DLOM2UdR.js` `toolLabels` | Names only. Inputs and outputs not captured (no trace JSON saved) |
| Transcripts | The HEADLINE agent picks structures by ID and trigger (Disrupção / Mistério / Reconhecimento…), uses the Núcleo de Influência (brain) for identity, and cites `(estrutura #id)`. **No transcript names a research variable or quotes an approved research item.** Pain, desire and fear wording in outputs traces to the user's pasted scripts | `convs.txt` (e.g. lines 11–13, 830–936, 4858–4878, 4962–4977) | yes, for these 29 convs |
| Roteiro generation | Params: `headline_text, ai_provider, mode, observations, roadmap_source_type (none\|serper), roadmap_use_pubmed, serper_query, viral_video_id, brain_id` — **no research variable** | `data.json .roteiros[].params` | yes (2 samples) |
| Suggested headlines (from Biblioteca) | `variable_contents[{variable_name, content, viral_topic_id, user_variable_id, additional_content}]`. The UI only sends `ASSUNTOS_VIRAIS` with `user_variable_id:null` | `pages/library.html` | The schema allows research items (`user_variable_id`), but no UI sends them |

---

## 6 · Merged list proposal input (facts only)

Union of the 29 DB variables (`ID|SLUG`), the 4 globals, and the 13 classifier slugs = **40 distinct concepts** (29 + 4 + 7 classifier-only).

**Correction (2026-10-05, owner review):** an earlier version flagged "partial overlaps" by name similarity. That was wrong. Two variables are the same concept only when their definitions AND their real items agree. By that test the only identities are the 5 exact slug matches and one spelling variant (row 6). Every other row is a distinct concept.

| # | Concept | UI id / DB slug | Classifier slug | Relation |
|---|---|---|---|---|
| 1 | Desejos (público) | 18 DESEJOS-TANGIVEIS-DO-AVATAR | DESEJOS-TANGIVEIS-DO-AVATAR | **exact match** |
| 2 | Dores (público) | 17 DORES-TANGIVEIS-DO-AVATAR | DORES-TANGIVEIS-DO-AVATAR | **exact match** |
| 3 | Demografia (público) | 16 CARACTERISTICAS-DEMOGRAFICAS-DO-AVATAR | CARACTERISTICAS-DEMOGRAFICAS-DO-AVATAR | **exact match** |
| 4 | Medos (público) | 9 MEDOS-DO-AVATAR | MEDOS-DO-AVATAR | **exact match** |
| 5 | Objeções (público) | 10 OBJECOES-DO-AVATAR | OBJECOES-DO-AVATAR | **exact match** |
| 6 | Pessoas/personagens conhecidos | 13 PESSOAS-PERSONAGENS-CONHECIDOS-PELO-AVATAR | PESSOAS-E-PERSONAGENS-CONHECIDOS-PELO-MEU-PUBLICO | **same concept, slug spelling differs** |
| 7 | Crenças do público / crenças limitantes | 8 CRENCAS-DO-AVATAR "Crenças do meu público" | CRENCAS-LIMITANTES-DO-AVATAR "Crenças internas negativas sobre si mesmo" | **distinct**. Crenças do meu público = beliefs the audience holds about the world, money and society (owner's real items: "vida que a sociedade queria que eu vivesse", "Cada um dá o que tem", "é rico", "não é barato", "inveja"). Crenças limitantes = negative beliefs about oneself ("não sou capaz"). |
| 8 | Inimigos do público / inimigo comum | 32 INIMIGOS-DO-AVATAR | INIMIGO-COMUM "Vilão externo que o avatar culpa" | **distinct by definition**. INIMIGO-COMUM is "vilão externo que o avatar culpa" (a copywriting device); Inimigos do meu público is its own UI variable. The owner has no Inimigos items to compare. |
| 9 | Frustrações | — | FRUSTRACOES-DO-AVATAR | classifier-only, **distinct**: past attempts that failed, vs Dores = problems lived now (the prompt itself separates them). |
| 10 | Mecanismo único | — | MECANISMO-UNICO | classifier-only, **distinct**: the method that differentiates the solution (product/expert side). |
| 11 | Promessa principal | — | PROMESSA-PRINCIPAL | classifier-only (product side) |
| 12 | Prova social | — | PROVA-SOCIAL | classifier-only, **distinct**: third-party results, numbers, authority (product side). |
| 13 | Nicho / mercado | — | NICHO-OU-MERCADO | classifier-only, **distinct**: a research item naming the product's area; not the account's Nichos taxonomy. |
| 14–24 | Qualidades 25, Defeitos 26, Itens 15, Instituições 14, Filmes/séries/músicas 11, Eventos 19, Locais 20, Momentos de vida 21, Produtos 34 (público) | DB only | — | **no classifier slug**, so AI add can never route a line here (only extraction or manual) |
| 25–36 | Especialista 5, 4, 30, 31, 28, 7, 27, 6, 12, 3, 2, 1 | DB only (`*-DO-ESPECIALISTA`) | — | **no classifier slug** for any. The avatar/especialista mirrors (16↔28, 25↔7, 26↔27, 8↔1) are **distinct** concepts about different people (the audience vs the expert). |
| 37–40 | Verbos Poderosos 22, Adjetivos Poderosos 23, Momento do dia 24, GPT 29 | id only, no slug seen | — | **global type `null`**. Not served by `variables/type`, not fetched by `variables/items` |

Other naming facts:
- DB slug quirk: `LOCAIS-CONHECIDO-PELO-AVATAR` uses singular "CONHECIDO".
- Several UI labels carry a trailing space (⎵): ids 17, 32, 19, 10, 8, 5, 4, 30, 31, 6, 2.
- The UI label "Assuntos" (dashboard) vs "Gatilhos" (sugeridas/favoritas) names the **same** select (`variables_id[]`).
- `ASSUNTOS_VIRAIS` is used as a `variable_name` in `variable_contents`. It is a pseudo-variable for viral topics, with no id in the 33 list.

---

## 7 · Cannot be determined from these files — needs a live check

1. **Classifier slug → variable_id map.**
   - Run `POST searches/add-items-sync` (or the hidden `add-item-prompt/test`, which saves nothing) with one line per classifier-only slug:
     - "já tentei várias dietas" (FRUSTRACOES)
     - "acho que não sou capaz" (CRENCAS-LIMITANTES)
     - "a indústria farmacêutica" (INIMIGO-COMUM)
     - "Método X em 3 passos" (MECANISMO-UNICO)
     - "perder 8kg em 90 dias garantido" (PROMESSA-PRINCIPAL)
     - "500 alunas com resultado" (PROVA-SOCIAL)
     - "emagrecimento" (NICHO-OU-MERCADO)
   - Read the response `classified` labels vs `unclassified[{content, token}]`. This shows whether these 7 slugs are saved (and under which variable_id), dropped, or returned as unclassified.
   - `test` avoids writing to the account. `add-items-sync` writes items and needs the owner's OK.
2. **Does PESSOAS-E-PERSONAGENS-…-MEU-PUBLICO land in id 13?** Same test with "A princesa Sofia"; then check that `variables/items?type=avatar` shows it under 13.
3. **The exact `data-has-structures` value for each of the 12 `me` options.** Re-read the raw `content_option` of `variables/type/me`. Is 27 the only `0`?
4. **The template/structure text.**
   - Open a generated batch in `#modal-view-headline` (`GET headlines/view/{id}`). Capture `payload` (the request JSON with `variables_id`, `variable_values`, `structures_category_items`, `thermometer`, the "apenas itens da pesquisa" flag name) and `headline_preview`.
   - Check whether the structure text contains slot tokens (`{{…}}`, `[…]`, `ID|SLUG`) and whether `structure_id`s match the 124xxx–152xxx ids cited in chat.
5. **Whether generated headlines actually contain research items.**
   - Generate once with `who=public`, Dores only, 2–3 specific `variable_values`, and the toggle "apenas os itens da minha pesquisa" ON.
   - Diff the output against the chosen item texts. Repeat with the toggle OFF.
6. **Field name and server effect of the toggle** "Criar as headlines usando apenas os itens da minha pesquisa." Inspect the DOM input `name` and the POST body.
7. **Chat research injection format.**
   - In the HEADLINE agent, `@` → Minha Pesquisa → pick one Dores item → send.
   - Then open the trace (`traceData.rag_steps`) to see how the item is passed, and whether `consultar_variaveis_perfil` / `find_variables` return variable lists or items, and which `variable_id`s.
8. **What `consultar_variaveis_perfil` reads.** It could be the user's Pesquisa or the reference profile's extracted variables (`profile-viral-search`). Check its output in a chat trace.
9. **Global variables 22/23/24/29.** Check whether any server feature uses them: admin-only UI, template fillers, or the "GPT" variable as an AI-generated-items bucket. Try `GET searches/variables/items?type=null|global` (read-only) and look for them in a headline `payload`.
10. **`get-profile` matching logic.** Which profiles come back for a given `variable_selected[]`, and is it based on the user's Pesquisa items (`eng_reversa_result_id`) or on library profiles tagged by variable? Compare responses for two different variable sets.
11. **"Sobre mim" generation with zero items.** With `who=me` and the owner's empty especialista variables: does `get-variables-values` return nothing, does generation fall back to the brain (Núcleo Especifico), or does it error?
12. **The `user_variable_id` path in `headlines/suggested/store`.** Is there any UI (admin or older) that sends research items through `variable_contents[].user_variable_id`?
13. **Which variables Extrair Pesquisa can produce overall.** Only 1, 3, 10, 15, 17, 18, 19 and 34 have been seen. Sample more profiles to see whether 25/26/11/20/21/32 or the other especialista ids ever appear.

---
*Sources: `pages/dashboard.html`, `pages/headlines~suggested.html`, `pages/headlines~favorites.html`, `pages/headlines~generate.html`, `pages/searches.html`, `pages/chat.html`, `pages/library.html`, `js/headlines.js`, `js/dashboard.js`, `js/app-DLOM2UdR.js`, `work/sug-dt.js`, `work/fav-dt.js`, `data.json` (`.formats`, `.roteiros`, `.conversations`), `convs.txt`, `js-analysis.md`, `spec-pesquisa-cerebro.md` §5.1/§9, `live/add-item-prompt.md`, `live/variables-live.md`.*
