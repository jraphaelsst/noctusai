# CoreStudio.ai — Platform Study

Oct 5, 2026 · @Raphael

> Reference study for recreating CoreStudio inside NoctusAI's social-wiring product as the **Criação de Mídia** module. Study only — not a build plan yet.

## Overview

CoreStudio ("Inteligência Core") is a workspace-scoped SaaS that turns a creator's niche research into **headlines** and **roteiros** (Reels scripts), driven by a library of viral references and an AI chat. It is the software counterpart of the course whose methodology we already absorbed into social-wiring as *Método Audience*.

- **Core loop:** research the audience (Pesquisa) → store brand knowledge (Segundo Cérebro) → generate headlines grounded in viral references (Biblioteca) → turn a headline into a roteiro (simple or Opções Avançadas) → save, favorite, and track it on the dashboard.
- **Tenancy:** user belongs to one or more *workspaces* (workspace switcher in the sidebar footer; meta `workspace-id`).
- **Studied account:** a licensed user account ("Gilson", My Workspace), real-estate niche — the suggested headlines are all about imóveis.
- **Method:** logged-in browser walkthrough of every page, modal and card + network capture + static analysis of the page scripts (`headlines.js`, `roadmaps.js`, `dashboard.js`, `advanced-roadmap-modal.js`, `advanced-roadmap-library.js`).
- **Limits:** server-side code, the exact LLM system prompts, and database schema are not visible. Where this doc describes them, it is **inferred** from requests, responses and UI behavior, and marked as such.

## Navigation map

The sidebar has **6 top-level items, 3 levels deep**: 4 plain links, 2 expandable groups, and one group nested inside a group (Configurações › Headlines). Users of the rebuild already know this tree and asked that it not change, so it is the spec, verbatim.

| Level 1 | Level 2 | Level 3 | Route | Icon |
| --- | --- | --- | --- | --- |
| Dashboard |  |  | `/dashboard/user` | lucide `house` |
| Criar Headlines e Roteiros |  |  | `/dashboard/user/chat` | lucide `messages-square` |
| Pesquisa ▾ | Minha Pesquisa |  | `/dashboard/user/searches` | tabler folder-search (outline) |
|  | Extrair Pesquisa |  | `/dashboard/user/searches/extract-profile` |  |
| Segundo Cérebro |  |  | `/dashboard/user/cores` | lucide `brain` |
| Biblioteca |  |  | `/dashboard/user/library` | tabler outline (compass-like glyph) |
| Configurações ▾ | Minha conta |  | `/dashboard/user/profile` | lucide `bolt` |
|  | Minha Biblioteca |  | `/dashboard/user/my-library` |  |
|  | Treinamentos |  | `/dashboard/user/trainings` |  |
|  | Headlines ▾ | Gerar Headlines | `/dashboard/user/headlines/generate` |  |
|  |  | Headlines Favoritas | `/dashboard/user/headlines/favorites` |  |
|  |  | Headlines sugeridas | `/dashboard/user/headlines/suggested` |  |
|  | Roteiros |  | `/dashboard/user/roadmaps` |  |

One more page exists but is **not in the menu**: `/dashboard/user/cores/extract` ("Minhas extrações", see Segundo Cérebro). Footer: avatar + name + workspace, a ⋮ menu with *Espaços de trabalho*, *Ver tutorial novamente*, *Fazer logout*.

**Behaviour (from their `layoutV2.css` + inline jQuery):**

1. **Level-1 groups are an accordion.** Clicking a group header hides every group's panel, then shows the clicked one. Exactly one level-1 panel is open; clicking the open header does not close it.
2. **Level-2 sub-groups toggle independently.** Clicking *Headlines* toggles only that sub-panel (`stopPropagation`), and its chevron rotates 180° over 0.2s.
3. **Initial state comes from the route.** On a page inside a group, that group renders highlighted and open, and so does the sub-group holding the page. On `/headlines/favorites`, Configurações and Headlines both load open.
4. **The highlight sits on the level-1 item only.** The active item gets a purple gradient (`#9945FF → #6224AE`, 90°), white text and icon, and a 5px glowing bar on the left edge. When a group is active, the whole expanded block shares the gradient. **The current leaf link has no style of its own**; all sub-links are `#FFFFFFB2`, white on hover.
5. **Below 990px the menu collapses** behind a toggle button (`slideToggle` 300ms) and is forced visible again above that width.

**Measurements:** items 34px narrower than the rail, 12px gap, 13px padding, 16px text, 22px icons, 8px icon–label gap. Level 2: 24px indent with a 1px `#D8BFF7CC` left rule, 12px gap. Level 3: 12px further indent with a 1px `#D8BFF766` rule, 10px gap, 0.9em text. Rail scrollbar 4px, thumb `rgba(153,69,255,.3)`.

&#91;image: Pesquisa group open (accordion, level 1)\]

&#91;image: Configurações open, Headlines sub-group closed\]

&#91;image: Configurações › Headlines open (level 3)\]

&#91;image: On a level-3 page: the group and sub-group load open; the leaf link has no own highlight\]

**Our constraint:** the seed `Sidebar` supports only group → flat items (`seed/lib/frontend/src/design-system/components/Sidebar.tsx:82-101`). You want their nested look, so the seed component gains one more level: a group inside a group. That is a seed change every product inherits, not a social-wiring-only fork. Its exact rules are in the open questions at the end.

## Page-by-page inventory

Thirteen pages, all server-rendered Blade (Laravel) with jQuery/Alpine behavior; only the chat is a Livewire component. The chat is the product's center of gravity — headline/roteiro pages are legacy surfaces demoted under Configurações.

| Page | Route | What it does | Key parts (cards, modals, states) |
| --- | --- | --- | --- |
| Dashboard | `/dashboard/user` | Usage overview | 3 KPI cards (Headlines geradas · Roteiros gerados · Diagnóstico "a preencher"); Histórico timeline (filter: data crescente/decrescente/tipo); Headlines Sugeridas widget (top 20 by views, Ações → Criar roteiro / Editar / Abrir link to source IG post); first-access tutorial modal |
| Criar Headlines e Roteiros | `/dashboard/user/chat?c={uuid}` | AI chat with 2 agents (HEADLINE, ROTEIRO) | Conversation list per agent (rename/delete, "Ver mais", 15 per page); agent select in composer; @-reference picker (4 tabs); Memória modal; docs panel "Referências anexadas"; voice dictation (pt-BR); per-message "Completo" copy + "Roteiro" clean-copy; inline action buttons (criar roteiro / roteiro com headline editável); Trace da IA drawer; Roteiro limpo modal; Twin avatar-video modal with credit recharge |
| Minha Pesquisa | `/dashboard/user/searches` | The persona research base | Unified list (Mais Recentes / Mais Views · Aprovados / Pendentes · variable filter · Agrupar), each item = phrase + variable + group + views + eye (opens source viral) + delete; "Adicionar itens à pesquisa" modal (one per line, AI-classified into variables); bulk approve/delete; hidden Assuntos Virais tab |
| Extrair Pesquisa | `/dashboard/user/searches/extract-profile` | Harvest research from viral profiles | Directory of approved profiles, filtered by user's nichos + profissões; per profile: "Vídeos" and "Pesquisa" → modal "Pesquisa do perfil @x" (e.g. 15 variáveis · 113 itens), grouped by variable with sort Views/Mais recente, each item = phrase highlighted in its source sentence + thumb + views + Ver vídeo; tick + save into own Pesquisa |
| Segundo Cérebro | `/dashboard/user/cores` | Expert knowledge ("cérebros") | Card grid with status badge (Vazio / Pronto) + "Acessar Cérebro"; "Criar Cérebro" modal (Tipo: Personalizado / Crença · Nome); "Como usar" video |
| Cérebro editor | `/dashboard/user/cores/edit/{id}` | Fill one brain | *Sistema* brains = questionnaire (text or voice answers; Salvar Rascunho / Finalizar Respostas / Zerar Tudo); free brains = one synced markdown body (Enviar arquivo · Transcrever do YouTube · Aplicar Alterações) |
| Biblioteca | `/dashboard/user/library` | Viral reels corpus | Auto-filter banner ("seus nichos e profissões"), Nichos + Profissões multi-selects, Mais vistos / Filtros; 24 cards/page, classic pagination (281 pages filtered); card = thumb + @profile + views/likes/comments + duration + date + Ver post + select checkbox; "Informações do Viral" modal (IG embed, Métricas, Transcrição + Copiar, Nicho/Profissão/Formato badges, Gerar headline wizard) |
| Minha Biblioteca | `/dashboard/user/my-library` | Which profiles/videos the chat AI may use | Added profiles (optionally auto-include new posts) + specific videos; request a new IG profile scrape (pending / aprovado / rejeitado) |
| Treinamentos | `/dashboard/user/trainings` | Onboarding videos | 1 module, 5 lessons (Bunny Stream) |
| Minha conta | `/dashboard/user/profile` | Persona settings | Personal data, IG/TikTok handles, up to 3 nichos + 3 profissões, Bio, **Apresentação magnética**, **CTAs** (both injected into roteiros), layout version |
| Gerar Headlines | `/dashboard/user/headlines/generate` | Legacy form flow | 3 cards: Sobre mim · Sobre meu público · Assuntos Virais → Gerar Headlines modal (see Mechanisms) |
| Headlines Favoritas | `/dashboard/user/headlines/favorites` | Saved headlines | Server-side table (ID, Data, Headline + "Roteiro criado" badge), actions: Editar · Ver Viral na Biblioteca · Roteiro Avançado · Excluir; bulk delete |
| Headlines sugeridas | `/dashboard/user/headlines/suggested` | Auto-generated daily suggestions | Same table + Mode (Automático / Manual) + views/likes/comments of the source viral |
| Roteiros | `/dashboard/user/roadmaps` | All roteiros | Server-side table (ID, Data, Nome, H. Origem, Status: Criando → Processando → Completo / Falha), view/edit, delete, bulk delete; opens the Roteiro Avançado modal |

**Global shell:** notifications bell (polled every 30 s, read / read-all), workspace switcher + create, Crisp chat, session-expiry reload on HTTP 419, forced dark theme.

## Component catalog

About 20 reusable components carry the whole UI; most map onto organs we already ship in seed (chat window, resource table, modals). The chat uses its own GitHub-dark palette (`dc-` prefix), distinct from the purple brand shell.

| Component | Where | Behavior to replicate | Our likely organ |
| --- | --- | --- | --- |
| Sidebar w/ nested groups | shell | 3-level nesting, active pill gradient `#9945FF→#6224AE`, workspace footer | seed `Sidebar` (needs nested items) |
| KPI stat card | dashboard | icon tile w/ inset glow + label + number | seed stat tile |
| Activity timeline | dashboard | icon + action + actor + `dd/mm/YYYY - HH:mm`, server sort | new (ActivityLog) |
| Suggested-headline row | dashboard | truncated headline + views pill + Ações dropdown | ResourceManager row |
| Chat window | chat | conversation list per agent, streaming bubbles, "Ir para o final" FAB, context-length warning (> 600k chars) | seed `ChatWindow` |
| Agent select | chat composer | HEADLINE / ROTEIRO; switches conversation list + tools | ChatWindow seam |
| Rich composer | chat | contenteditable with inline reference chips, Enter=send, Shift+Enter=newline, plain-text paste, mic dictation with 12-bar waveform | extend ChatWindow |
| Reference picker (@) | chat | 4 tabs, debounced search (200 ms), infinite scroll, skeletons, multi-select across tabs, "N selecionado · Limpar · Confirmar", keyboard ↑↓↵Esc | new organ |
| Attached-references panel | chat right drawer | list + remove (removes inline chip too) | new |
| Action buttons in AI output | chat | `{{action:roteiro\|id\|headline}}` → "Criar roteiro" / "roteiro com headline editável"; `select_reel` | Markdown renderer extension |
| Streaming step panel | chat | "Processando · N etapas", per-step badges "N aprovados / N resultados", expandable items | new |
| Trace drawer | chat | system/user prompt, rounds, tool calls, reviews, tokens | admin tool |
| Memory modal | chat | list + add (500 chars) + delete | small CRUD modal |
| Viral card | library | 9:16 thumb, @handle tag, select checkbox, metrics row, duration pill, date, Ver post | new card |
| Viral detail modal | library | IG embed player, Métricas grid, transcription + copy, taxonomy badges, Gerar headline | new |
| Filter bar w/ chips | library, extract | TomSelect multi-chips (nichos, profissões) + presets "Meus nichos e profissões" / "Ver todos" | seed filter |
| Research item row | pesquisa | phrase + variable · group · views, status accent bar, eye + trash, bulk select | ResourceManager |
| Extraction modal | extract | accordion per variable w/ count + per-group sort, phrase highlighted in source sentence | new |
| Brain card + editor | cérebro | status badge Vazio/Pronto; questionnaire w/ voice answers or synced markdown body | new |
| Roteiro Avançado modal | roteiros, favorites | 3-step wizard (see Mechanisms), library picker sub-view, result tabs Roteiro / Fontes | new |
| Server-side data table | favorites, suggested, roteiros | DataTables: search, bulk select, pt-BR, row actions as 40 px round icons | ResourceManager |

**Design tokens (brand shell):** primary `#9945FF` (rgb 153,69,255) · deep `#4C1F83` · indigo `#5229CF` · lilac `#E1C8FF` · hairline `#E1C8FF26` · body bg `#04050C` with a 270° near-black gradient · cards `linear-gradient(180deg,#1A182B,#0E0…)` · radii 8 / 18 / 32 (`--borderRadiusSM/MD/LG`), pills 50 · padding 24 · font Inter.

**Chat palette (`dc-`):** bg `#0d1117`, panels `#161b22`, borders `#21262d`/`#30363d`, text `#e6edf3`→`#484f58`, accent `#58a6ff`/`#1f6feb`; user bubble blue glass radius 16 16 4 16, assistant bubble translucent radius 4 16 16 16; mention modal 820 px with an animated conic-gradient border.

## Mechanisms & user flows

There are four ways to produce content, all converging on the same two artifacts (headline, roteiro). Long generations are **server-side jobs polled by the browser** (every 5–20 s, fake progress bars); only the chat streams (SSE).

**A. Chat — the primary flow** (`/dashboard/user/chat`)

1. Pick agent **HEADLINE** or **ROTEIRO** (each has its own conversation list; conversations are UUIDv7).
2. Type a request; optionally `@` to attach references: profiles ("todos os vídeos"), single viral videos, uploaded documents (PDF/DOCX/TXT/MD/CSV ≤ 20 MB), research items (Meu Público / Sobre mim, filterable by variable, sorted by recent or views), and — ROTEIRO only — brains (Meu Cérebro). Chips sit inline in the text and are attached to the conversation (`attachReference`).
3. Send → `POST /chat/stream` (SSE). The UI shows a step panel while the pipeline runs (events `progress`, `rag_step`, `tool_start/end`, `review_start/end/retry`, `token`, `completed`).
4. HEADLINE output: a numbered list of headlines, each citing its source structure `(estrutura #ID)` = a library viral, with buttons **Criar roteiro** and **Criar roteiro com headline editável** (`{{action:roteiro|id|headline}}`).
5. ROTEIRO output: an optional **structure analysis** of a pasted/referenced viral (table Bloco · Elemento · Lógica) then the roteiro with labeled beats, e.g. *(Headline) → (História Magnética / Credencial) → (CTA de Salvar) → (Valor Prático – Item 1..3) → (CTA de Compartilhar) → (Apresentação Magnética) → (CTA de Comentar)*, ending with **Total de palavras**. Pacing rule observed: \~125 words/min, a 2-min Reel = 220–250 words.
6. Iterate in natural language ("linguagem mais popular", "no máximo 2 min", "três opções diferentes"). Copy **Completo** (raw) or **Roteiro** (AI-cleaned spoken text only, "Roteiro limpo" modal with "Saiu errado? Limpar com IA").
7. Optional: **Gerar vídeo com o Twin** — review the spoken script, pick an avatar clone, spend credits (charged per video minute; recharge packages if balance is short).
8. Memory: "guarda na memória que …" makes the agent call `salvar_memoria_tool`; memories (≤ 500 chars each) apply to every HEADLINE and ROTEIRO chat.

**B. Gerar Headlines form (legacy)** — modal with:

1. *Falar sobre*: Meu público · Sobre mim · Assuntos Virais (or a custom subject).
2. *Assuntos*: the 17 audience variables (or 12 "sobre mim" variables), or "Todos".
3. Advanced: **Perfil de Referência** (≤ 2) **XOR** **Formato do Vídeo** (15 formats); Núcleo específico (a brain); Estrutura de Roteiro; **Gatilho da Atenção** (Recompensa, Mistério, Popularidade/Autoridade, Reconhecimento, Crença, Disrupção); **Tom** (Chocante e Disruptiva, Futuro e Possibilidades, Curiosidade e Mistério, Cultura e Sociedade, Crítica e Denúncia, Reflexão e Profundidade); **Criatividade objetiva** slider snapping to Essencial (0) / Equilibrado (50) / Explorador (100).
4. Submit → job (`status: in_gpt2 → completed | error`), polled every 20 s with rotating messages ("Separando referências…", "Analisando tendências…", "Gerando estruturas…"). Generation is **two-pass** (create, then revise) — both payloads are kept.
5. Results → favorite / edit / create roteiro. Box editing format: `{{ ID: <structure_id> }} <headline>`.

**C. Roteiro Avançado (3-step wizard)** — from favorites, suggested, dashboard or Roteiros:

1. **Headline** (prefilled) + **Instruções** (tone, audience, do/don't).
2. **Fonte das informações**: *Deixe a IA pensar* (none) · *Link específico* (≤ 4 URLs) · *Pesquisar na web* (Serper, ≤ 4 results; query auto-translated to English unless "Quero buscar em português"; optional "\[PubMed\] Incluir artigos científicos"; per-result translate).
3. **Duração** (Auto, \~1, \~2, \~3 min) + **Segundo Cérebro** (optional) + **Vídeo da biblioteca** (optional structure reference, filterable picker).
4. Submit (`ai_provider: claude`) → "Este processo passa por 2 etapas de análise e pode levar até 2 minutos" → polled every 5 s (≤ 10 min). Result tabs: **Roteiro** and **Fontes da Pesquisa** (the research dossier, `search_text`). Like/dislike feedback stored.

**D. Headline from a viral** (library → Gerar headline): 4-step wizard (workspace → pick approved topics from Pesquisa → review → background job) producing headlines into *Headlines sugeridas*. Suggested headlines are also generated automatically each day from top virals in the user's niches.

**Research loop (feeds everything):** Extrair Pesquisa (pick phrases from viral profiles) or Adicionar itens (AI classifies free text into variables) → items land as *Pendentes* → user approves → approved items become selectable subjects in headline generation and @-references in chat.

## AI layer

Two tool-using agents (HEADLINE, ROTEIRO; a hidden `headline_express` exists) run a **retrieve → validate → generate → review** pipeline, with reviewer agents that reject and retry. The differentiated IP is the **structure library**: every headline is a viral's syntactic skeleton re-filled with the user's topic and persona. Evidence: 29 real conversations, the page code, the trace-drawer schema; system prompts themselves are server-side and were not visible — the drafts below are **reconstructed** from behavior.

**Pipelines (from tool labels + trace schema)**

- *HEADLINE:* find templates (structures) → validate → find variables (research) → validate → find triggers → validate → generate 5 variations → QA picks the best. Trace summary fields: `templates_validados`, `variaveis_validadas`, `gatilhos_validados`.
- *ROTEIRO:* research raw material → structure the script → refine copy → evaluate quality; reviewers emit `approved`/`feedback` with retry ("↻ aprovado após retry").
- *Tools seen:* Instagram profile/reels fetch, library structure search, documents search/list, web search (Serper, auto-PubMed for health), `salvar_memoria_tool`, `esquecer_memoria_tool`. The legacy headline form also runs **two passes** (create → revise).

**HEADLINE output contract (observed)**

- One-line preamble → one headline per line, each ending **`(estrutura #ID)`** (ID = library viral used as template) → a *Criar roteiro* button per item.
- Count obeys the request (1 / 5 / 10); "manda mais" = 10 new. 190 headlines measured: median **18 words** (11–34); "duas linhas" → 12–16.
- With `@perfil` the structure pool switches to that profile's videos; without, a default house pool (\~52 IDs reused).

| Structure ID (uses) | Skeleton | Example produced |
| --- | --- | --- |
| 124688 (22) | X não destrói Y, só revela o que já estava… | A reforma não destrói o erro, ela só revela aquilo que já estava mal escolhido |
| 124680 (17) | Pouca gente sabe, mas existe um X que… | Pouca gente sabe, mas existe uma coisa num imóvel que nenhum investimento do mundo resolve |
| 124672 (15) | A X não é A. Ela é B. | A saudade de quem você era não é nostalgia. Ela apaga quem você ainda pode se tornar |
| 127980 (8) | Essas X parecem Y, mas atacam Z | Essas atitudes parecem carinho, mas atacam a identidade de quem já está crescido |
| 147303 (4) | O X não é A, não é B e muito menos C | A cláusula mais importante do contrato não é o valor, não é o prazo e muito menos… |
| 132209 | Disseram que X. Ninguém avisou sobre Y | Disseram que essa fase ia passar rápido. Ninguém avisou sobre o silêncio que viria depois |

**ROTEIRO output contract (observed)**

1. Opener ("Perfeito. Tenho tudo que preciso.") after tools run.
2. Analysis: chosen structure + why, or **ANÁLISE DA ESTRUTURA** table *Bloco · Elemento · Lógica* + "Padrões-chave", or "ENGENHARIA REVERSA — bloco a bloco", or "POR QUE VIRALIZOU / motores invisíveis". Sequence is then "travada".
3. **✍️ ROTEIRO — {persona}**, each paragraph prefixed by a **(Rótulo do bloco)**.
4. **Total de palavras: N** (≈ duration).

**Canonical beat vocabulary (frequency across 29 chats):** Opinião Polêmica 145 · Apresentação Magnética 129 · Headline 122 · Provas e Argumentações 99 · Pontos de Identificação 95 · Intensificador do Mistério 88 · Fatos Curiosos 75 · CTA de Comentar 71 · CTA de Compartilhar 66 · CTA de Salvar 45 · Valor Prático 37 · Histórias Magnéticas 36 · CTA de Seguir 21. Compounds mirror a modeled text ("Item 1 + Opinião Polêmica + Consequência"); 126 distinct labels in total.

**Placement rules it states:** CTA de Salvar early (before the value); mid-roll CTA between items 2 and 3 "criando suspense máximo"; Apresentação Magnética mid-video "no pico do engajamento" or closing with CTA de Comentar. Modeling rule: "modelar bloco a bloco sem copiar bordões, jeito de falar ou argumentos do original".

**Quality findings that should become our gates:**

- **Length:** stated rule 220–260 words for 2 min (\~115–130 wpm), but uncapped output lands at 285–330 words, and users asked for a cap \~17 times (the #1 correction). Its own "Total de palavras" undercounts by 2–8%. → count in code, enforce a hard cap.
- **Invented facts:** a Roteiro Avançado output fabricated statistics ("67% … se arrependem", "3.000 famílias"). → a reviewer that rejects unsourced numbers.
- **Fidelity conflict:** users wanted near-paraphrase ("só mude as palavras") while the agent defaults to structural modeling. → explicit mode: *Modelagem estrutural* vs *Paráfrase fiel*.
- **Research dossier unused:** the web-search `search_text` (9k chars, partly off-topic) was not visibly used. → cite sources or drop.
- **Persona lock-in:** see Segundo Cérebro.

**What users actually ask (29 chats):** headlines for an existing script (\~13) · steer a batch ("mais forte", "mais curta", "nessa vibe X") (\~8) · reverse-engineer a viral and model it for the persona (\~10) · N roteiros from one headline, each on a different structure (\~6) · batches of 10–20 · rewrite with a word cap (\~17 msgs) · scope persona/context (\~7) · current events (elections, Selic, tax rules) · extras: legenda + hashtags, B-roll per block, critique.

**Reconstructed draft system prompts** (ours, written from observed behavior — a starting point, not CoreStudio's text):

```markdown
# Agente HEADLINE
Você é o Agente de Headlines de Reels para {persona.nome} ({persona.nicho}; público: {persona.publico}). pt-BR coloquial. Nunca invente fatos, números ou casos.
ENTRADAS: pedido; texto-base (opcional); persona (Núcleo, Sobre mim, Apresentação Magnética, CTAs); memória; referências (@perfil = biblioteca do perfil; #ID = vídeo); variáveis de público aprovadas; restrições (qtde, linhas, tom, termos vetados).
PIPELINE: 1 buscar_estruturas → 2 validar (≥5) → 3 buscar_variaveis → 4 validar → 5 escolher gatilhos (Recompensa, Mistério, Popularidade/Autoridade, Reconhecimento, Crença, Disrupção; variar no lote) → 6 gerar preservando o ESQUELETO sintático da estrutura e trocando todo o conteúdo → 7 revisor QA (até 2 retries): fiel ao esqueleto, específico, lacuna de curiosidade nos 3s iniciais, ≤25 palavras (≤16 se "duas linhas"), sem dado inventado, sem termos vetados, sem repetir headlines do chat.
SAÍDA: "Aqui estão N headlines para <tema>:" → uma por linha + "(estrutura #ID)" → {{action:roteiro|ID|headline}} por item. Padrão N=5.

# Agente ROTEIRO
Você é o Agente de Roteiros de Reels para {persona.nome}. pt-BR falado, frases curtas.
ENTRADAS: headline/tema; roteiro-referência (opcional); estrutura #ID ou @perfil; persona + cérebros; Apresentação Magnética e CTAs; memória; pesquisa (web/PubMed/documentos); limite de palavras (padrão 250 ≈ 2 min); modo = MODELAGEM_ESTRUTURAL | PARAFRASE_FIEL.
PRIORIDADE: instruções do chat > persona ativa > memória. Persona desconhecida → pergunte área, público, bio e @.
PIPELINE: 1 Pesquisa (se falhar: ⚠️ + só conhecimento estável ou [PREENCHER]) → 2 Estrutura (tabela Bloco|Elemento|Lógica + padrões; travar) → 3 Redação bloco a bloco com rótulos canônicos → 4 Refinar (cortar ao limite) → 5 Revisor (estrutura, headline fixa, contagem do sistema ≤ limite, zero fato inventado, persona certa, cada CTA uma vez, variantes com estruturas diferentes).
SAÍDA: análise curta → "✍️ ROTEIRO — {persona}" → blocos rotulados → "Total de palavras: N (≈ Xs)".
```

**Still unknown:** the reviewer prompts and retry limits, how structures/variables/triggers are retrieved (embedding vs SQL), chat model and temperature (Roteiro Avançado uses `ai_provider: claude`), and the exact `duration: auto` rule. The Trace da IA drawer would reveal system prompts on a real message — worth one live generation if you approve spending a credit.

**Captured verbatim — the Pesquisa classifier prompt.** This is a real CoreStudio system prompt, not a reconstruction. The page fetches it from `GET /dashboard/user/searches/add-item-prompt` (`is_active: true`, `include_variables: true`) and runs it on every line pasted into *Inserir itens na pesquisa*. The original sends the variable table as run-together text; it is reformatted below as `slug | meaning` for reading.

```markdown
Você é um classificador automático de variáveis de pesquisa de avatar para copywriting.
🔍 Sua função:
Receber um ou mais itens e retornar APENAS a classificação no formato padronizado. Nada mais.
📚 Variáveis disponíveis:
Variável | O que é
{{CARACTERISTICAS-DEMOGRAFICAS-DO-AVATAR}} | Gênero, idade, profissão, estado civil, localização, renda, escolaridade
{{DORES-TANGIVEIS-DO-AVATAR}} | Problemas concretos que o avatar vive agora
{{DESEJOS-TANGIVEIS-DO-AVATAR}} | Resultados concretos que o avatar quer alcançar
{{MEDOS-DO-AVATAR}} | Cenários futuros negativos que o avatar teme
{{FRUSTRACOES-DO-AVATAR}} | Tentativas passadas que falharam
{{OBJECOES-DO-AVATAR}} | Barreiras e dúvidas que impedem ação/compra
{{CRENCAS-LIMITANTES-DO-AVATAR}} | Crenças internas negativas sobre si mesmo
{{INIMIGO-COMUM}} | Vilão externo que o avatar culpa
{{MECANISMO-UNICO}} | Método ou sistema que diferencia a solução
{{PROMESSA-PRINCIPAL}} | Transformação central prometida
{{PROVA-SOCIAL}} | Resultados de terceiros, números, autoridade
{{NICHO-OU-MERCADO}} | Área ou segmento do produto
{{PESSOAS-E-PERSONAGENS-CONHECIDOS-PELO-MEU-PUBLICO}} | Figuras, celebridades, personagens que o público reconhece
Hierarquia de desempate (se um item puder pertencer a mais de uma):
DORES (vive agora) > MEDOS (teme no futuro) > FRUSTRACOES (falhou no passado) > OBJECOES (impede ação) > CRENCAS-LIMITANTES (identidade) > DESEJOS (quer alcançar)
📌 Regras ABSOLUTAS:

A resposta contém SOMENTE os pares variável/conteúdo
ZERO explicação, raciocínio, introdução, conclusão, resumo ou comentário
ZERO texto antes, entre ou depois dos pares
ZERO resumo quantitativo
Cada item = uma variável na linha de cima + conteúdo na linha de baixo
Uma linha em branco separa cada par
Texto original literal, sem reescrita
Nunca invente variáveis fora da tabela

📦 Formato de saída — ÚNICO formato permitido:
{{VARIAVEL}}
[conteúdo literal]

{{VARIAVEL}}
[conteúdo literal]
🎯 Exemplo:
▶️ Input:
1. Mulheres acima de 40 anos
2. insônia
3. A princesa Sofia
4. já tentei várias dietas
5. perder 8kg em 3 meses
▶️ Output:
{{CARACTERISTICAS-DEMOGRAFICAS-DO-AVATAR}}
[Mulheres acima de 40 anos]

{{DORES-TANGIVEIS-DO-AVATAR}}
[insônia]

{{PESSOAS-E-PERSONAGENS-CONHECIDOS-PELO-MEU-PUBLICO}}
[A princesa Sofia]

{{FRUSTRACOES-DO-AVATAR}}
[já tentei várias dietas]

{{DESEJOS-TANGIVEIS-DO-AVATAR}}
[perder 8kg em 3 meses]
🛑 Se você incluir QUALQUER texto além dos pares {{VARIAVEL}} + [conteúdo], a resposta está ERRADA.
```

## Biblioteca de Virais

The library is a **scraped, transcribed and LLM-classified corpus of competitor Reels** — 514 profiles, \~6,700 virals in this user's 3 niches alone. Its value is the classification + transcripts, not playback (the player is just the Instagram embed). Deeper discussion deferred, per your note.

- **Item (`eng_reversa_result`):** profile handle, social (instagram / tiktok / youtube), thumbnail (S3), plays, likes, comments, post date, post link, `transcription_text`, extracted headline, `is_core` (staff "gold standard" flag), M:N links to **niches** (28), **professions** (102) and **formats** (15).
- **Filters:** keywords (comma-separated; searches the extracted headline by default, transcription optional), date range, min views / likes / comments, network, profile, niche, profession, format, viral ID; sort by views (default) or recent; 24 per page; auto-filtered to the user's niches + professions with a dismissible banner.
- **Detail modal "Informações do Viral":** IG embed, Métricas, Transcrição (copy), badges Nicho / Profissão / Formato, deep-link copy (`library?viral_id=`), **Gerar headline** (4-step wizard), and "Citar no Chat" for a viral or a whole profile.
- **Uses downstream:** (a) headline *estruturas* — every chat headline cites the viral it was modeled on; (b) structure reference for Roteiro Avançado; (c) source of research phrases (Extrair Pesquisa); (d) @-references in chat; (e) daily suggested headlines.

**The 15-format classification rubric** — the classifier prompt behind each viral's format tags (multi-label; the *Alias* column is the tie-break rule):

| # | Format | Definition | Signals | Alias / tie-break |
| --- | --- | --- | --- | --- |
| 1 | Lista de Valor Prático | Dicas/passos/recomendações aplicáveis imediatamente. | Enumeradores, “dicas”, “passos”, “faça hoje”, imperativos em sequência. | Tutorial se houver HOW-TO detalhado. |
| 2 | Lista de Pontos de Identificação | Situações em que o público se reconhece. | “se você…”, “quem já…”, checklists de dores. | Lista de Crenças se virar opinião. |
| 3 | Lista de Crenças | Valores ou princípios afirmados com clareza. | “eu acredito”, tom opinativo forte. | Defesa de Crença Forte se polarizador. |
| 4 | Mistério | Informação-chave retida até o final. | Perguntas intrigantes, “no final eu revelo…”. | Fatos Curiosos se o dado sai cedo. |
| 5 | Comparação | Contrasta duas opções/ideias. | “X vs Y”, “diferença entre”. | Análise do Mundo se macro sem contraste. |
| 6 | Tutorial | Passo a passo de COMO fazer. | “como fazer…”, “passo 1/2/3”. | Lista de Valor se faltar HOW-TO. |
| 7 | Análise do Mundo e Novas Tendências | Mudanças sociais/leis/mercado e impactos. | “tendência”, “cenário”, previsões. | + Assunto do Momento se gancho noticioso. |
| 8 | Histórias Pessoais | Relato em 1ª pessoa com vulnerabilidade. | “quando eu…”, reflexões próprias. | Motivação se só conselhos curtos. |
| 9 | Histórias de Terceiros | Caso de cliente/paciente/figura pública. | “uma cliente…”, nomes de terceiros. | Análise se sem narrativa concreta. |
| 10 | Fatos Curiosos | Dados/estatísticas surpreendentes. | “você sabia que…”, números, estudos. | + Mistério se o dado vem no fim. |
| 11 | Metáforas e Analogias | Explica por comparação familiar. | “é como…”, “imagine que…”. | Não marcar se só slogans. |
| 12 | Assunto do Momento | Trending (notícia, meme, evento). | Datas atuais, “hoje/agora”. | Coexiste com Análise do Mundo. |
| 13 | Defesa de Crença Forte | Opinião polarizadora, linguagem absoluta. | “nunca”, “sempre”, “está errado”. | + Lista de Crenças. |
| 14 | Palavras de Motivação | Encorajamento curto. | Frases-impacto, pouca explicação. | Histórias se houver narrativa. |
| 15 | Websérie | Conteúdo seriado. | “Parte 1/2”, “Episódio”. | “Embalagem” — coexiste com qualquer formato. |

**Taxonomies:** 28 niches (e.g. 3 Finanças · 23 Vendas · 26 Imobiliário · 2 Relacionamentos · 14 Saúde Mental …) and 102 professions (e.g. 82 Corretor de Imóveis · 71 Advogado Imobiliário · 46 Psicanalista …); full id lists live in the scratch analysis and should be seeded verbatim when we build.

## Pesquisa (Minha Pesquisa + Extrair Pesquisa)

Pesquisa is the user's **persona knowledge**: short phrases ("insônia", "Paulo Guedes", "economizar dinheiro") each filed under one of **29 research variables**. Most phrases come from real viral videos, so each keeps the video's view count and a link back to it. Headline and roteiro generation and the chat's @-mentions read from it. The full screen-by-screen spec (every label, endpoint, state and quirk) is in the **Spec — Pesquisa & Cérebro** tab; this section is the summary.

**Where items come from (4 paths):**

1. **Extrair Pesquisa (main path).** The platform has already scraped and analysed **485 curated viral profiles** (Instagram), each tagged with niches and professions. For every viral video an AI pulled out phrases per variable from the video's opening line (hook). The user browses the profiles, opens one, ticks phrases and saves them.
2. **Inserir itens (AI-classified).** The user pastes free lines; an LLM files each line under a variable. The real system prompt is captured in the AI layer section.
3. **Inserir itens (direct).** With the AI prompt off, each line is saved under the selected variable as a "manual" item.
4. **Assuntos Virais (hidden).** A separate list of viral *topics* ("empreendedorismo" 2.5M views) with its own approve/reject flow. It is reachable only via `?tab=subject-viral`; nothing in the menu links to it.

**Statuses:** `pending` (orange bar) → user approves (✓✓) → `approved` (purple bar), or rejects (✕). Manual items are born `approved_manual`. Records are soft-deleted (`deleted_at`). The owner's account holds about 110 approved and 160 pending items.

### Minha Pesquisa (`/dashboard/user/searches`)

| Control | Options (verbatim) | Behaviour |
| --- | --- | --- |
| Sort pills | `Mais Recentes` · `Mais Views` | newest id first, or views desc |
| Status pills | `Aprovados` · `Pendentes` | no "all" state; Pendentes pill turns orange |
| Variable select | `Todas as variáveis` + 33 variables | filters the list; also the default target when adding |
| `Agrupar` | toggle | groups by variable: label + `Meu Público`/`Sobre Mim` badge + `N item(s)` |
| Row | checkbox · phrase · `variable · group · 1.212.039 views` | Aprovado: 👁 + 🗑 · Pendente: 👁 + ✓✓ + ✕ · 👁 opens the source video in Biblioteca (new tab) |
| Bulk bar (≥1 ticked) | `N selecionado(s)` · `Selecionar todos` · `Ações` | modal: `Aprovar selecionados` · `Excluir selecionados` · `Zerar toda a pesquisa` |
| `+ Adicionar itens a pesquisa` | modal *Inserir itens na pesquisa* | one item per line, `Ctrl+Enter` saves, live `N itens` count, `Prompt ativo — itens serão processados pela IA` |

All items load in two calls (`variables/items?type=avatar` and `?type=especialista`); sorting, filtering and 20-row infinite scroll then run in the browser. AI add calls `add-items-sync` (90s timeout), then falls back to a background job polled every 2s. The result shows saved counts, phrases by variable, and `Não classificados`.

&#91;image: Minha Pesquisa — Aprovados, Mais Recentes\]

&#91;image: Pendentes: orange accent, approve ✓✓ and reject ✕ per row\]

&#91;image: Agrupar on: grouped by variable with counts\]

&#91;image: Bulk Ações modal\]

&#91;image: Inserir itens na pesquisa (AI prompt active)\]

&#91;image: 👁 opens the source viral in Biblioteca\]

### Extrair Pesquisa (`/dashboard/user/searches/extract-profile`)

A grid of profile cards, 24 per page: `@handle`, 3 thumbnails, `Vídeos` (opens Biblioteca filtered to that profile) and `Pesquisa`. Above it sit a name search and multi-select `Nichos` / `Profissões` filters, **pre-set to the user's own niches and professions** from Minha conta, plus `Limpar Filtros`.

`Pesquisa` opens *Pesquisa do perfil @handle*. The summary line reads `9 variável(is) · 76 item(s)`, phrases are grouped by variable in collapsible sections, and each section sorts by `↓ Views` or `Mais recente`. Each phrase row shows the video thumbnail, the phrase in bold inside its source sentence ("Fique e aprenda a fazer esta massagem em casa, é **super fácil**."), views and `Ver vídeo ↗`. Ticked phrases go to Minha Pesquisa via `Adicionar à minha pesquisa`; phrases already added show struck through as `✓ Já adicionado`. Both *Meu Público* and *Sobre mim* variables appear.

&#91;image: Extrair Pesquisa — profile catalogue, filters pre-set from the profile\]

&#91;image: Pesquisa do perfil: phrases by variable, with source sentence and views\]

**Variables have server slugs**, for example `DESEJOS-TANGIVEIS-DO-AVATAR` (18), `CRENCAS-DO-ESPECIALISTA` (1), `PRODUTOS-CONHECIDOS-PELO-AVATAR` (34). The full id/label list is in the spec tab.

**Inconsistency to decide on:** the AI classifier prompt only knows **13 slugs**, and they don't match the 33 UI variables. It has no *Inimigos*, *Eventos* or *Locais*, and it has *Mecanismo único*, *Promessa principal* and *Prova social*, which have no UI variable. Our rebuild should use one variable list everywhere.

## Segundo Cérebro (`/dashboard/user/cores`)

A **brain** is one markdown document about the creator (story, method, positioning, beliefs). The roteiro agent and the chat's @Cérebro read it as context. Brains are filled in three ways: an **AI-validated questionnaire**, **file upload**, or **YouTube transcription**. Uploads and transcripts are appended below the existing text.

**List page.** Title `Cérebros Personalizados` / `Segundo cérebro`, a `+ Criar Cérebro` button, and a tutorial banner (Bunny video). Below are cards, 3 per row: a `Vazio` (grey) or `Pronto` (blue) badge, the name, and `Acessar Cérebro`. The owner has 7: Hístoria de Criação, Histórias de Vida do Especialista and Método do Especialista (Vazio), plus Núcleo de Influência, Call de diagnóstico, Formulário and Narrativa (Pronto). Create asks only `Nome do Cérebro:` (placeholder `Ex: Reels Instagram`). A hidden type select (`Personalizado` / `Crença`) exists, so every new brain is Personalizado.

| Brain kind | Opens | Fill methods | Rename / delete |
| --- | --- | --- | --- |
| *Sistema*, not answered yet | questionnaire `/cores/questions/{id}` | answer questions | no |
| *Sistema*, answered (e.g. Núcleo de Influência) | content editor `/cores/edit/{id}` | `Responder perguntas` · `Enviar arquivo` · `Transcrever do YouTube` · edit text | no |
| *Personalizado* (user-made) | content editor | `Enviar arquivo` · `Transcrever do YouTube` · edit text | ✎ rename · 🗑 delete |

### The questionnaire, and how the AI validates answers

1. Numbered question cards, each with a textarea (`Escreva sua resposta aqui`), a live `N caracteres` count, a status chip `Aguardando resposta`, and a top bar `Progresso das respostas · 0 de 9`.
2. **Questions unlock in groups of 3.** The next group fades in when every answer in the current group is filled. If more than 3 answers already exist on load, all show at once.
3. Footer: `Zerar Tudo` (confirm, then clear) · `Salvar Rascunho` (saves without validating) · `Finalizar Respostas`.
4. **Finalizar** sends the answers for **AI validation**; every chip turns `Validando...`. The verdict arrives by websocket (a private channel per user) with a 3s status poll as backup.
5. Each answer comes back **`Aprovada`** or **`Rejeitada` + `Motivo da rejeição: …`**. Any rejection: `Algumas respostas foram rejeitadas. Corrija-as e tente novamente.`
6. All approved: `Gerando cérebro...` → `Sincronizando seu cérebro...` → `Cérebro sincronizado!` → back to the list, now `Pronto`. The AI turns the answers into the brain document; Núcleo de Influência became a "Perfil Profissional" (nome, profissão, experiência, missão, especialidades…).

**System questionnaires, verbatim:**

- **História de Criação (9):** Como era sua vida antes de trabalhar com o que você trabalha hoje? · O que te motivou a iniciar nessa área? · Qual ou quais foram os maiores desafios que você enfrentou nesse caminho? · Teve um momento em que você pensou em desistir? O que te fez continuar? · Qual foi o ponto de virada que fez tudo mudar? · Quem você se tornou hoje? · O que você aprendeu com tudo isso e quer passar para outras pessoas? Qual é sua missão nessa área? · O que te motiva a continuar todos os dias? · Qual legado você quer deixar por meio do seu trabalho?
- **Histórias de Vida do Especialista (4):** Agora precisamos das histórias que te forjaram na sua jornada. · Agora, conte histórias de grandes descobertas ou ensinamentos que você teve ao longo da sua jornada. · Conte histórias de pessoas que você ajudou. · Agora para finalizar, conte histórias de grandes conquistas que você teve na vida.
- **Método do Especialista (7):** Qual é o passo a passo que você ensina para a pessoa sair do ponto A até o resultado? · Quais são os 3 a 5 pilares que toda pessoa precisa entender ou aplicar pra ter resultado com o que você ensina? · Se alguém seguisse só o essencial do que você faz, o que não poderia faltar? · Existe uma ordem certa ou fases que a pessoa precisa seguir? Quais são elas? · Você tem nomes para cada etapa ou princípio do seu método? Quer criar? · Se você pudesse resumir seu método em uma frase ou nome forte, como ele se chamaria? · Tem alguma parte do processo que as pessoas costumam pular e depois se arrependem? Qual é?
- **Núcleo de Influência:** a system brain the owner already answered; its questions weren't re-read.

### Content editor

It shows a back arrow, the title (with its Sistema badge if any) and `Alimente este cérebro com o seu conhecimento — quanto mais rico, melhores os resultados da IA.` Below are the source buttons, then `Conteúdo do cérebro` with a character count: one large markdown textarea holding the synthesized brain, and `Aplicar Alterações`.

- `Enviar arquivo` opens *Importar arquivo para o cérebro*: drag-and-drop of PDF, DOCX, TXT, MD or CSV up to 20 MB, `O conteúdo será adicionado abaixo do texto já existente no cérebro.`
- `Transcrever do YouTube` opens *Transcrever vídeos do YouTube*: one or more links (`+ adicionar outro link`), then `Transcrever e anexar`. A background job downloads the audio, transcribes it and appends the text; the page polls the job until `done`.
- **Narrativa** shows what a synthesized brain looks like: `### MOVIMENTO IDENTIFICADO`, `### BIO`, `### APRESENTAÇÃO MAGNÉTICA`…, the same beat names the roteiros use.
- Their script also contains **voice answers per question** (mic recording uploaded in 1 MB chunks), but no mic button shows on either editor today, so it looks retired.

&#91;image: Segundo Cérebro list: Vazio / Pronto cards\]

&#91;image: Criar Cérebro: name only\]

&#91;image: Questionnaire: groups of 3, character count, status chip\]

&#91;image: Content editor, Sistema brain: Responder perguntas · Enviar arquivo · Transcrever do YouTube\]

&#91;image: Content editor, custom brain: rename + delete, no questionnaire\]

### Hidden page: Minhas extrações (`/dashboard/user/cores/extract`)

Not in the menu. It is a table (ID · Data · Nome · Status) of "extractions" plus a `Nova Extração` modal: `Nome`, `Extrair para:` (multi-select of brains, with `Clique aqui para criar um novo núcleo`), `Url:` or a pasted `Transcrição`, then `Criar Transcrição`. It appears to be the older way of feeding brains from a link. The owner has 0 rows ("filtrado de 192 registros no total").

&#91;image: Hidden Minhas extrações page\]

&#91;image: Nova Extração modal\]

**Gap users hit:** one persona per account, and no way to keep separate brains per client or product line.

## Architecture & API contract

CoreStudio is a **Laravel monolith on the MagicAI SaaS base** (LiquidThemes) with a large custom layer; Tabler/Bootstrap UI, jQuery + Alpine, Livewire 3 only for the chat. Generation runs in server jobs and agent loops; the browser streams the chat over SSE and polls everything else.

&#91;embedded content: CoreStudio architecture · inferred from network + page code\]

Only the chat page talks continuously (SSE); every other generation is a job the page polls every 5–20 s behind a simulated progress bar.

| Area | Endpoints (all under `/dashboard/user`) | Notes |
| --- | --- | --- |
| Chat | `POST chat/stream` (SSE) · `POST chat/documents` (upload) · Livewire `document-chat`: `startNewConversation`, `selectConversation`, `renameConversation`, `deleteConversation`, `loadMoreConversations`, `searchMentions`, `searchMyResearch`, `searchUserDocuments`, `attachReference`, `detachReference`, `loadMemories`, `addMemory`, `deleteMemory`, `copyScriptFast`, `forceCleanScript`, `loadToolDetail` | SSE events: `token`, `progress`, `rag_step`, `tool_start/end`, `refining_*`, `review_start/end/retry/warn`, `completed`, `error` |
| Headlines | `GET headlines/profiles` · `GET headlines/status/{id}` (`in_gpt2→completed\|error`) · `POST headlines/{favorites\|suggested}/list` (DataTables) · `…/update` · `…/delete(-multiple)` · `GET headlines/suggested/view/{id}` (two-pass payloads) · `POST headlines/suggested/store` (from viral) | `variables` encoded `id\|SLUG` |
| Roteiros | `POST roadmaps/list` · `GET roadmaps/view/{id}` (`roadmap_gpt`, `params`, `search_text`, `roadmap_liked`) · `…/advanced-roadmap/{store,show/{id},list-search,direct-search,translate-search-query,translate-search-results}` · `roadmaps/check-status/{id}` · `roadmaps/reversa/{store,show}` | Poll 5 s, ≤ 120 polls |
| Library | `GET library?…filters` (server-rendered) · `GET library/result/{id}` (JSON) · `GET library/workspaces` · `POST library/viral-topics` · `POST library-references/self-assign` | 24 per page |
| Pesquisa | `GET searches/profile-viral-search/{profileId}` · add/approve/reject/delete item endpoints (see scratch analysis) | AI classification sync 90 s → job |
| Cérebro | `GET cores/edit/{id}` · `POST cores/youtube/extract` + `GET cores/youtube/status` | Voice answers chunked 1 MB |
| Shell | `GET notifications` (30 s) · `POST notifications/{id}/read`, `read-all` · `POST workspace/switch` · `POST first-access-seen` · `GET twin/api/credits` | HTTP 419 → reload |

**Third parties seen:** Pusher (key in page, legacy chat widget), Crisp support, Bunny Stream (training videos), S3 (`corestudio-ai` bucket, thumbnails), Instagram embeds, Serper web search, PubMed; LLMs: Claude (`ai_provider: claude` default for roteiros), GPT-4o-mini (query translation, per code comment).

## Inferred data model

About 20 entities, reconstructed from JSON responses and form payloads; names are CoreStudio's where seen, column types are not visible. Scope is **Customer → Workspace → User**, and most creative data hangs off the workspace.

| Entity | Key fields (observed) | Relations |
| --- | --- | --- |
| Customer / Workspace | `id, name` | Customer 1→N Workspace; user switches workspace |
| UserProfile | bio, apresentação magnética, CTAs, IG/TikTok handles, niches (≤ 3), professions (≤ 3) | 1→1 user |
| ViralResult (`eng_reversa_result`) | `profile, social, thumbnail, plays, likes, comments, post_date, post_link_public, transcription_text, headline, is_core` | N:M Niche, Profession, FormatVideo; belongs to ReferenceProfile (`eng_reversa_search_id`) |
| ReferenceProfile | `id, profile (handle), is_structure`, status pending/approved/rejected | 1→N ViralResult |
| FormatVideo | `id, name, definition, signals, alias, status` (15) | N:M ViralResult (via a classification run `eng_reversa_flow_result_id`) |
| Niche (28) · Profession (102) | `id, name, slug` | N:M ViralResult, UserProfile |
| Variable | `id, slug, label, type: public\|me` (17 + 12 + power words) | 1→N ResearchItem |
| ResearchItem | `id, value, variable_id, group, status (user / pending / approved), plays, source result_id, source headline` | user/workspace; source ViralResult |
| ViralTopic | `id, topic, status` | workspace; source ViralResult |
| StructureCategoryItem | `id, group: 3 Estrutura \| 4 Gatilho \| 7 Tom, name` | headline generation filters |
| Core (brain) | template `id` (8–4192) + per-user instance (85xx–93xx), `type: sistema \| personalizado \| crença`, status vazio/pronto, `content` (markdown) | 1→N CoreQuestion / answers |
| UserMemory | `id, content ≤ 500, created_at` | user |
| ChatConversation | `id (UUIDv7), title ≤ 100, agent_id, updated_at, attached_references[{id, source, title, meta}]` | 1→N ChatMessage |
| ChatMessage | `id, role, content (markdown + {{action}} tokens + estrutura citations), is_roteiro, trace JSON` | trace = prompts, rounds, tool calls, reviews, usage |
| ChatAgent | `id, key: headline \| roteiro \| headline_express` | — |
| RagDocument | `id, title, meta, status` (uploads) | user |
| HeadlineGeneration | inputs (who, variables, subject, profiles XOR formats, core, structure items, thermometer), `status in_gpt2→completed\|error`, two-pass payload/callback | 1→N Headline |
| SuggestedHeadline (`eng_reversa_headlines`) | `headline, mode automatic\|manual, result(views), likes, comments, eng_reversa_result_id, structure, roadmap, search_text` | source ViralResult |
| FavoriteHeadline | `headline, headline_id, structure, roadmap, eng_reversa_result_id` | — |
| Roadmap (roteiro) | `id, name, headline, observations, brain_id, viral_id, params{source_type, links, serper_query, pubmed, duration, ai_provider, mode}, roadmap_gpt, search_text, status (Criando/Processando/Completo/Falha), roadmap_liked` | from Favorite/Suggested/Headline |
| ActivityLog · Notification | `actor, action, type, created_at` · `title, body, link, icon, type, status` | user |
| Twin (avatar video) | CloneProfile `{id, name, thumbnail_url}`, CreditWallet `{balance}`, CreditPackage `{credits, price_cents}` | user |

## Mapping to NoctusAI

We already own the methodology (*Método Audience* in `prompts/methodology.py`), a post pipeline, brand kits and transcription; what CoreStudio adds is the **viral structure library, the research base, brains/memory and the agentic chat**. Today social-wiring has one flat "Criação de mídia" link (`App.tsx:150`) with in-page tabs Biblioteca · Novo post · Kits de marca.

**Decided sidebar (interview, 2026-10-05):** a new **Criação de Mídia** group below Edição de Fotos holds CoreStudio's tree exactly, which makes the seed sidebar **4 levels** deep. Each link is still its own `status_pagina` row.

```
Criação de Mídia ▾                       (level 1, our group)
  Dashboard                               (level 2)
  Criar Headlines e Roteiros
  Pesquisa ▾
    Minha Pesquisa                        (level 3)
    Extrair Pesquisa
  Segundo Cérebro
  Biblioteca
  Configurações ▾
    Minha conta
    Minha Biblioteca
    Treinamentos
    Headlines ▾
      Gerar Headlines                     (level 4)
      Headlines Favoritas
      Headlines sugeridas
    Roteiros
```

| Decision | Answer |
| --- | --- |
| Placement | Nested under Criação de Mídia; seed sidebar supports 4 levels |
| Open / close | Accordion (one group open per level), and the open group **can be closed** by clicking it |
| Active state | CoreStudio's highlight on the top item **plus** a mark on the current leaf link |
| Where it lives | A seed `Sidebar` change (approved) |
| Rollout | Every **active** product gets it: academia-de-reciclagem, agents, community, core, igig, orbity, p-studio, social-wiring, store. The 7 asleep products are untouched. What "gets it" means is still open (below) |

**What we reuse vs build**

| CoreStudio piece | We have | Gap |
| --- | --- | --- |
| Method taxonomies (gatilhos, estruturas, CTAs) | `METODO_AUDIENCE` (7 triggers, 32 templates, skeleton) | merge with CoreStudio's 13-beat vocabulary + 15 formats + 6 tones |
| Chat UI + streaming | seed `ChatWindow`, `chat_completion_stream`, help-chat SSE pattern | @-reference picker, inline chips, step panel, trace drawer |
| Conversations store | agents product `stores/conversations.py` | per-agent lists, attached references |
| Brains / knowledge | agents `personas.py` + `knowledge_editorial`, knowledge-extractor `kb_chunk` + `match_kb` | questionnaires, voice answers, YouTube transcription → brain |
| Transcription | `integrations/llm/audio.py` (Whisper), knowledge-extractor pipeline | reel download + batch transcribe |
| Brand persona | `mc_brand_kits` (persona, design system) | Apresentação magnética + CTAs slots; per-conversation persona |
| Tables / CRUD | seed `ResourceManager` | — |
| Viral library + classifier | — | scraper, transcripts, 15-format multi-label classifier, niches/professions |
| Research base | — | 33 variables, extraction from transcripts, approve flow |
| Web research | Claude runtime WebSearch only | seed-level search integration (Serper/PubMed equivalent) |
| Memory | — | small per-user store + save/forget tools |

**Improvements over CoreStudio (from the evidence):** a hard word cap counted in code; a reviewer that blocks unsourced numbers; explicit *Modelagem estrutural* vs *Paráfrase fiel* mode; persona selectable per conversation; cite or drop the research dossier.

**Open questions** (the interview continues; nothing is assumed):

- [x] Nesting: decided — nested, 4 levels, seed change (see the decisions table above)
- [ ] Rollout to the other active products: only the new behaviour (closable accordion + leaf mark) with menus unchanged, or also regroup their menus into nested groups?
- [ ] Do the existing social-wiring tabs (Biblioteca de posts · Novo post · Kits de marca) stay, and where in the new tree?
- [ ] Visual style of the tree: CoreStudio's look (purple gradient, rule lines) or our design-system tokens?
- [ ] Pesquisa: one variable list for both the UI and the AI classifier — CoreStudio's 33, the classifier's 13, or a merged list?
- [ ] Pesquisa: rebuild the hidden Assuntos Virais pane, or leave it out?
- [ ] Segundo Cérebro: keep AI validation of questionnaire answers? Bring back voice answers? Keep the hidden *Minhas extrações* page?
- [ ] Viral library source: scrape our own corpus, or start from the user's references only? (Biblioteca discussion deferred.)
- [ ] Approve actions in CoreStudio that change the account (spec tab §7), including one live generation (1 credit) to read the real HEADLINE / ROTEIRO prompts?
