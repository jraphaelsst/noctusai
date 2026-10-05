# CoreStudio — BUILD SPEC: Minha Pesquisa · Extrair Pesquisa · Segundo Cérebro

> Static reverse-engineering of saved pages (no live requests made). Sources:
> `pages/searches.html` (+ `ex/s_*`), `pages/searches~extract-profile.html` (+ `ex/p_*`),
> `pages/cores.html` (+ `ex/c_*`), external `js/searches.js` (loaded by searches page as
> `back/js/user/searches.js`), `js/brains.js` (loaded by cores page as `back/js/user/brains.js`),
> cross-checked against `pages/roadmaps.html`, `pages/dashboard.html`, `pages/headlines~favorites.html`, `js-analysis.md`.
>
> Legend: **[OBS]** = observed in code/markup. **[INF]** = inferred (not visible client-side). **[LIVE]** = must be verified in the browser (collected in §7).
> pt-BR strings are verbatim, including original typos and trailing spaces (shown inside backticks when the trailing space matters).
> End-user personal data is omitted; "the account owner" = the logged-in user whose pages were saved.

---

## 0 · Cross-cutting conventions (all three screens)

### 0.1 Stack [OBS]
- Laravel (Blade, server-rendered) + Tabler/Bootstrap 5 modals + jQuery + vanilla `fetch` + `toastr` notifications + TomSelect (multi-selects). Forced dark theme (`localStorage.tablerTheme='dark'`, `data-bs-theme="dark"`).
- `<base href="/">` on every page → relative URLs such as `dashboard/user/searches/...` resolve to `/dashboard/user/searches/...`.
- `meta[name=csrf-token]` → sent as `X-CSRF-TOKEN` header on POSTs (JSON or FormData); some FormData posts append `_token` instead. Other metas: `app-env`, `workspace-id`, `user-id`, `first-access`.
- **No Livewire on these three screens.** `window.livewireScriptConfig` (`uri: /livewire/update`) is emitted by the shared layout, but no `wire:` attribute or `$wire` call exists in the page scripts. (Livewire is used by the chat page, which *consumes* Pesquisa/Cérebro data — see §6.4.)
- Shared layout boilerplate (identical md5 across all three pages; skipped): dark-theme forcer, sidebar dropdowns, first-access tutorial modal (`Bem-vindo ao Core Studio!` / `Assistir aos treinamentos agora` / `Pular por agora`), legacy floating audio chat widget (Pusher), Crisp chat loader, Tabler demo "New report" modal (dead template code).

### 0.2 Response envelopes [OBS]
Three coexisting styles — a rebuild should normalise to one, but must accept these for parity:
1. `{ success: bool, message: string, ...payload }` — newer endpoints.
2. `{ type: 'success'|'error'|'info'|'warning', message }` — toastr-driven; client calls `toastr[data.type](data.message)`. Optional flags: `button` (re-enable button), `redirect` (URL, navigate after 1 s), `refresh` (reload after 1 s), `reset` (reset form + close modal).
3. Laravel validation `422 { errors: {field: [msg]} }` → each message toasted. `419` / message containing "csrf" is silently ignored on cores forms.
Generic fallback toast: `Erro ao processar a solicitação.`

### 0.3 Sidebar (context, same on all pages) [OBS]
`Dashboard` · `Criar Headlines e Roteiros` · **`Pesquisa`** → `Minha Pesquisa` (`/dashboard/user/searches`), `Extrair Pesquisa` (`/dashboard/user/searches/extract-profile`) · **`Segundo Cérebro`** (`/dashboard/user/cores`) · `Biblioteca` · `Configurações` → `Minha conta`, `Minha Biblioteca`, `Treinamentos` · `Headlines` → `Gerar Headlines`, `Headlines Favoritas`, `Headlines sugeridas` · `Roteiros`. Workspace switcher (`Espaços de trabalho`, `Adicionar Workspace` modal with `Nome`, `Cancelar`, `Criar`), "Headlines na Box" offcanvas, `Notificações` (`Marcar todas como lidas`), `Ver tutorial novamente`, `Fazer logout`.

---

## 1 · Screen 1 — Minha Pesquisa (`GET /dashboard/user/searches`)

`<title>Minha Pesquisa</title>`. Purpose: one flat, filterable list of "research items" — short text values attached to a **variable** (e.g. "Medos do meu público"), each either **Aprovado** or **Pendente**, optionally linked to a viral video (with view count). These items later feed headline/roteiro generation and the chat's `@research` mentions.

### 1.1 Page layout [OBS]
```
┌ headerContainerMainV2 ───────────────────────────────────────────────┐
│ H2 "Minha Pesquisa"                                                  │
│ P  "Gerencie suas variáveis de pesquisa para criar headlines         │
│     inteligentes."                         [+ Adicionar itens a pesquisa] │
└──────────────────────────────────────────────────────────────────────┘
┌ card (form#save-variables, multipart, method=post) ──────────────────┐
│ [alert#pending-variables-alert — hidden by default]                  │
│ [#global-variables-loading — spinner]                                │
│ .tab-content#variables-content                                       │
│   ├ .tab-pane#my-research  (active; data-type="unified")  ← THE LIST │
│   └ .tab-pane#subject-viral (hidden; "Assuntos Virais" — see §1.8)   │
│ [card-footer#form-footer: button#button_save_variables "Atualizar"]  │
│   → hidden by JS whenever #my-research or #subject-viral is active   │
└──────────────────────────────────────────────────────────────────────┘
```
- **No visible tab navigation** to switch between `#my-research` and `#subject-viral` in the saved markup (no `[data-tab]` links, no nav-tabs for the outer panes). `#subject-viral` is reachable only through `?tab=subject-viral` (handled by `searches.js` `activateTab`). [LIVE]
- Header button `Adicionar itens a pesquisa` → `openAddItemModal()` with no arguments (§1.5.1).

#### Legacy/hidden elements still in DOM [OBS]
- `#pending-variables-alert` (alert-warning): title `Itens pendentes de salvar`; body `Você possui <strong id=pending-count>0</strong> item(ns) novo(s) aguardando para serem salvos. Clique no botão <strong>"Salvar Alterações"</strong> no topo da página para salvar as alterações.` — belongs to the old per-variable editor; nothing in the current unified flow shows it.
- `#global-variables-loading`: spinner + `Carregando variáveis...` (h3) + `Por favor, aguarde enquanto buscamos seus dados.`; used by legacy `loadTabVariables(type)`; in unified mode it is never hidden/shown by the unified code path (the unified list renders its own spinner). [LIVE: confirm it is hidden on load]
- `#form-footer` `Atualizar` submit → `searches.js` posts `FormData(form#save-variables)` to `POST /dashboard/user/searches/save`; success toast `Perfil atualizado. Redirecionando...` + reload after 1 s; 422 → toasts; else `Ocorreu um erro ao salvar o perfil.`; button text while saving `Aguarde salvando...`, restored to `Salvar`. (A second, unused implementation `saveVariablesAjax()` toasts `Variáveis atualizadas com sucesso!` / `Nenhum item para salvar.` and restores `Salvar Alterações`.) Form fields that would be sent: `approved_items[<varId>]` (CSV ids), `rejected_items[<varId>]` (CSV ids), `subject_viral` (newline-joined topics, hidden `#subject_viral_hidden`). **Do not rebuild** — superseded by per-item endpoints.
- Large legacy per-variable renderer code (`loadTabVariables`, `renderApprovedManualItem`, `renderApprovedPendingItem`, `renderPendingItemCard`, `approveSelectedItems`, `deleteSelectedItems`, `emptyVariable`, `openAddVariableModal`, `openRemoveModal<varId>` lookups, `?tab=me|public`). Their DOM targets (`#approved-items-<id>`, `#pending-items-<id>`, `#tab-approved-<id>`) do not exist in this page. Endpoints they call are still listed in §1.10 because the server still exposes them.

### 1.2 Unified list toolbar (`#my-research`) [OBS]
Left → right, one row (wraps on mobile):

| Control | id | Type | Options / labels (verbatim) | Default | Effect |
|---|---|---|---|---|---|
| Sort segmented toggle | `unified-sort-recent`, `unified-sort-plays` | 2-button pill group | `Mais Recentes` · `Mais Views` | `Mais Recentes` (`sort:'recent'`) | recent = `id` desc; plays = `plays` desc (null→0). Active pill gradient `#7c3aed→#9945FF`, inactive transparent/60% white. |
| Status segmented toggle | `unified-filter-approved`, `unified-filter-pending` | 2-button pill group | `Aprovados` · `Pendentes` | `Aprovados` (`statusFilter:'approved'`) | approved = everything not `pending` (i.e. `approved` + `approved_manual`); pending = `pending` only. Active pending pill orange gradient `#c2410c→#f97316`. **There is no "Todos" state** (code supports `''` but no UI sets it). |
| Variable select | `unified-variable-filter` | native `<select>` single | `Todas as variáveis` (value `""`) + 33 variables (§5.1) | `""` | filter by `variableId`. Also used as default target variable by the add-item modal. |
| Group toggle | `unified-groupby-btn` | toggle button | `Agrupar` | off | on → render grouped by variable, **no pagination** (all items), infinite scroll disabled. |
| Count | `unified-total-count` | text | `${n} item(s)` (empty when 0) | — | — |

Bulk bar `#unified-bulk-bar` (display:none until ≥1 checkbox checked): `<n> selecionado(s)` (`#unified-bulk-count`) · button `#unified-select-all-btn` label `Selecionar todos` ⇄ `Desmarcar todos` (toggles only the rows currently rendered) · button `Ações` → opens `#modal-bulk-actions` (§1.5.2).

### 1.3 List row anatomy (`renderUnifiedItem`) [OBS]
Zebra rows (odd rows `rgba(255,255,255,0.025)`), bottom border `#ffffff0f`:
1. 3 px × 36 px accent bar — purple `#9945FF` if approved/approved_manual, orange `#f97316` if pending.
2. Checkbox `.item-checkbox-unified` (data: `item-id`, `variable-id`, `status`, `source`).
3. Text block: **content** (0.88rem, `#e8e0ff`, word-break) + meta line (0.68rem, 25% white) = `«variableLabel» · «Meu Público|Sobre Mim» [· manual] [· «1.234.567» views]` (views formatted with `.` thousands separator, only when `plays` truthy). For variables whose type is `null` (Verbos Poderosos etc.) the code still prints `Meu Público` (bug — anything not `especialista` → `Meu Público`).
4. Icon actions (35 % opacity, 90 % on hover):
   - **Pending**: 👁 `Ver na biblioteca` → `openUserVariableModal(eng_reversa_result_id, content)`; ✓✓ `Aprovar` → sets id on `#modal-approved-variable` confirm; ✕ `Rejeitar` → `#modal-rejected-variable`.
   - **Approved (from extraction)**: 👁 `Ver na biblioteca` + 🗑 `Excluir` → `openUnifiedRemoveModal(id, variableId, 'pending')`.
   - **Approved manual**: 🗑 `Excluir` only → `openUnifiedRemoveModal(id, variableId, 'content')`.
- `openUserVariableModal` opens a new tab: `/dashboard/user/library?viral_result_id=<id>` when the item has a source video, else `/dashboard/user/library?transcription_search=<urlencoded content>` (full-text search of transcriptions).
- `source` semantics: `content` = row in the manual/approved content table; `pending` = row in the pending table (extracted items keep `source='pending'` even after approval — server model detail, see §4).

Grouped mode header per variable: label (`#E1C8FF`, 600) + type badge (`Sobre Mim` bg `#7c3aed` / `Meu Público` bg `#0d6efd`) + `«n» item(s)` badge; groups in insertion order (especialista variables first, then avatar — order of the API objects).

### 1.4 Loading / empty / error / pagination [OBS]
- On page load: `DOMContentLoaded` → if `#my-research` active and nothing loaded → `loadUnifiedData()`. Re-entrancy guard `window._unifiedLoading`.
- Loading: container replaced with spinner + `Carregando itens...`.
- Data: **two parallel GETs** `/dashboard/user/searches/variables/items?type=especialista` and `?type=avatar`; all items merged client-side (no server paging, no server filtering).
- Empty (after filters): `#unified-empty-state` → `Nenhum item encontrado.`
- Error: alert-danger `Erro ao carregar` + `error.message` + button `Tentar novamente` (re-calls load).
- Client-side infinite scroll: `PAGE_SIZE = 20`; sentinel `#unified-scroll-sentinel` observed with `IntersectionObserver({threshold:0.1})` → append next 20. Disabled while `Agrupar` is on. Any filter/sort change resets to first 20.
- After any mutation (add/approve/bulk ops/empty) the list is fully re-fetched (`loadUnifiedData()`), except single delete which removes the row locally.

### 1.5 Modals on Minha Pesquisa

#### 1.5.1 `#modal-add-item` — "Inserir itens na pesquisa" [OBS]
Opened by header button `Adicionar itens a pesquisa` (`openAddItemModal()`; 520 px, centered, glow styling).
- **Target variable**: `variableId` arg, else the current value of `#unified-variable-filter`; label shown under tabs (`#add-item-variable-label`) unless it is `Todas as variáveis`. Hidden `#add-item-variable-id`.
- Header: icon + `Inserir itens na pesquisa`, close `✕`.
- Tabs row: only `Itens` (active). JS also supports a `Prompt` tab (`#add-tab-prompt`, `#add-prompt-system`, `#add-prompt-include-variables`, `#add-prompt-test-input`, `#add-prompt-result`, buttons `#add-prompt-test-btn`, `#add-prompt-save-btn` "Salvar prompt") but **that markup is absent** for this account → prompt editing is presumably admin/role-gated. [LIVE]
- Body (state `items`):
  - Hint: `Cada linha vira um item separado. Pressione [Enter] para nova linha e [Ctrl+Enter] para salvar.`
  - `<textarea id=add-item-value rows=6>` placeholder `Ex:\nMedo de envelhecer\nAnsiedade com dinheiro\nInsegurança no trabalho`. **Ctrl+Enter submits**.
  - Live counter `#add-item-line-count`: `0 itens` / `1 item` / `N itens` (non-empty trimmed lines).
  - `#add-item-process-status` (shown only when prompt active): `Prompt ativo — itens serão processados pela IA`.
- Footer: `Cancelar` (dismiss) · `Salvar itens` (`#add-item-submit-btn`).
- On open: `GET /dashboard/user/searches/add-item-prompt` → `{is_active, prompt_system, include_variables}`; `promptActive = is_active && !!prompt_system`. Errors swallowed. Textarea focused after 300 ms.
- **Validation**: ≥1 non-empty line, else toast warning `Digite ao menos um item.` No max length/line count client-side.
- **Submit — Mode A, prompt ACTIVE (AI classification)**:
  1. Switch to state `processing`: AI orb + `Classificando itens com IA...` / `Aguarde, isso pode levar alguns instantes` (static markup default sub-label: `Isso pode levar alguns instantes`) + indeterminate progress bar.
  2. `POST /dashboard/user/searches/add-items-sync` JSON `{text: lines.join('\n')}` with **90 s AbortController timeout** → render result.
  3. On timeout/network error: label `Processando em segundo plano...` / `A resposta demorou mais que o esperado, avisaremos quando terminar`, then `POST /dashboard/user/searches/add-items-job` `{text}` → `{success, job_id, message}`; if `!success` → error result (`Erro ao iniciar processamento.`). Poll `GET /dashboard/user/searches/add-items-job/{job_id}` every **2 s**, max **300 attempts (~10 min)**; continue while `status ∈ {processing, pending}`; network errors keep polling; exhaustion → error `Tempo limite atingido. Tente novamente.`; dispatch failure → `Erro de conexão. Tente novamente.`
  4. **Result state**: error banner `Erro ao processar` + `message` (fallback `Ocorreu um erro inesperado.`), or success banner `«saved»` + `item adicionado`/`itens adicionados` + ` com sucesso`; collapsible `Ver detalhes` listing `classified` (`{variableLabel: [content…]}`) groups and `Não classificados (N)` (each `content` + monospace `token`). Footer `Inserir mais` (reset to items state) · `Fechar`. If `saved>0` the list reloads.
  - Note: in Mode A the **selected variable is ignored** — the server classifies each line into a variable. [INF]
- **Submit — Mode B, prompt INACTIVE (direct)**: sequential `POST /dashboard/user/searches/variables/contents/add` `{id: variableId, value: line}` per line; button shows `Salvando i/N...`; counts `data.type==='success'`. Then toast `N item adicionado com sucesso!`/`N itens adicionados com sucesso!`, close modal, reload list; or `Nenhum item foi salvo.`; exception `Erro ao salvar itens.` Items added this way are **approved manual** items (status `approved_manual`, meta "manual").
  - If no variable is selected (filter = `Todas as variáveis`) Mode B posts `id: ""` → server-side validation error expected; the UI has no client guard. [LIVE]
- Prompt config endpoints (code present, UI hidden): `POST add-item-prompt {prompt_system (' ' if empty), is_active: !!prompt, include_variables: bool}` → `{success,message}` toast `Prompt salvo!`; `POST add-item-prompt/test {prompt_system, text, include_variables}` → `{success, result}` shows raw result; guards `Digite o prompt system primeiro.` / `Digite um texto para testar.`; errors `Erro ao salvar prompt.` / `Erro no teste.` / `Erro ao testar prompt.`

#### 1.5.2 `#modal-bulk-actions` — "Ações — N selecionado(s)" [OBS]
Small centered modal, opened by `Ações` in the bulk bar.
- `Aprovar selecionados` (`#bulk-action-approve-btn`, visible **only when status filter = Pendentes**) → for each checked row with `status==='pending'`: sequential `POST /dashboard/user/searches/approve-pending-item/{id}`; toast `N item(s) aprovado(s) com sucesso!`; reload. None pending selected → info `Nenhum item pendente selecionado para aprovação.`
- `Excluir selecionados` → confirm modal `#modal-confirm-bulk-delete` with text `Você realmente deseja excluir N item(s) selecionado(s)?` → sequential `POST dashboard/user/searches/variables/contents/remove {id, source}` per row; toast `N item(s) excluído(s) com sucesso!`; reload.
- divider
- `Zerar toda a pesquisa` / sub-label `Remove todos os itens, incluindo os não carregados` → confirm modal `#modal-confirm-empty-variable` with text `Você realmente deseja esvaziar TODOS os itens de TODAS as variáveis? Esta ação não pode ser desfeita.` → `POST /dashboard/user/searches/variables/contents/empty-all` → toast `Toda a pesquisa foi zerada!` / `Erro ao zerar pesquisa.`; reload.
- Each action closes the bulk modal first.

#### 1.5.3 Confirmation modals [OBS]
All: small, centered, `btn-close`, centered `<h3>` message, footer two pill buttons.
| id | Default message | Buttons | Confirm action |
|---|---|---|---|
| `modal-confirm-bulk-delete` | `Você realmente deseja excluir os itens selecionados?` (overwritten: single → `Você realmente deseja excluir este item?`; bulk → `…excluir N item(s) selecionado(s)?`) | `Cancelar` / `Excluir` (danger) | bulk delete or single `variables/contents/remove` |
| `modal-confirm-empty-variable` | `Você realmente deseja esvaziar todos os itens? Esta ação não pode ser desfeita.` | `Cancelar` / `Esvaziar` | `empty-all` |
| `modal-approved-variable` | `Você realmente deseja aprovar esse topico?` | `Cancelar` / `Aprovar` | `handleActionUV('approve', id)` → `POST /dashboard/user/searches/approve-pending-item/{id}` |
| `modal-rejected-variable` | `Você realmente deseja reprovar este topico?` | `Cancelar` / `Reprovar` | `POST /dashboard/user/searches/reject-pending-item/{id}` |
Single remove success: toast `data.message || 'Item excluído com sucesso!'`, row removed locally, count updated. Approve/reject success: toast `data.message || 'Ação realizada com sucesso!'`, modals closed, list reloaded; failure `Erro ao processar ação.` / `Erro ao excluir item.`

#### 1.5.4 Legacy/orphan modals present on this page [OBS]
- `#addVariableModal` "Adicionar conteúdo para a variável «label»": input `#variableValue` (placeholder `Digite o conteúdo...`, Enter submits), button `Adicionar`, hint `Adicione um ou mais conteúdos e depois clique em "Atualizar Agora" para salvar.`, footer `Fechar` → `POST variables/contents/add {id, value}`. **No trigger in the current DOM.**
- `#extractViralProfileModal` "Extrair Pesquisa de Perfil Viral" — the modal version of Screen 2 (12 profiles/page, cards include a hidden `Extrair` button). **No trigger in the current DOM**; Screen 2 replaced it.
- `#profileViralSearchModal` "Pesquisa do perfil @handle" — same as §2.4; reachable here only from the orphan modal above.

### 1.6 Pane `#subject-viral` — "Assuntos Virais" (viral topics) [OBS]
Hidden by default; activated by `?tab=subject-viral` [LIVE: confirm there is no visible entry point]. Server-rendered (Blade), not AJAX-loaded.
- Info alert (clickable card): title `Extrair assuntos virais`, text `Use esta opção para extrair assuntos virais de um perfil e adicionar aos seus assuntos virais.`, button `Extrair Assuntos Virais` → `#extractViralTopicsModal` (§1.7).
- Card title `Assuntos Virais`, nav-tabs: `Aprovado` (active) · `Pendente` + yellow count badge (server value; account owner had `10`). Badge count is recomputed client-side after approve/delete (`updateViralPendingCounter`, removed at 0).
- **Tab Aprovado** (`#tab-approved-viral-topics`):
  - Row: checkbox `Selecionar todos` (`#select-all-approved-viral`) · `Excluir selecionados (N)` (hidden until ≥1 checked) · `Esvaziar` (title `Esvaziar todos os assuntos virais aprovados`).
  - Add input `#new-viral-topic` (`maxlength=255`, placeholder `Digite um novo assunto viral...`, Enter submits) + button `Adicionar` (`#add-viral-btn`, text `Salvando...` while busy). Empty → toast `Digite um tópico válido!`.
  - Badge cloud `#viral-topics-badges` (flex-wrap pills). Pill anatomy: [checkbox (only on pills created by approval in-session)] topic text · `«2.5M» Views` (K/M one decimal, `.0` stripped) or `Manual` for manually-added topics (`eng_reversa_result_id` empty/0) · white `×` (opens `#modal-remove-topic`). Click pill → `#viralModal`. Classes: `viral-topic-badge` (extracted) vs `viral-topic-badge-manual`.
  - Reveal-in-batches: pills start `d-none`; `Ver mais` (`#loadMoreBtn`) reveals **27 more per click**; hidden when exhausted.
  - Empty state: nothing (empty cloud). The account owner had 0 approved topics.
- **Tab Pendente** (`#tab-pending-viral-topics`):
  - Row: `Selecionar todos` · `Aprovar selecionados (N)` (outline-blue, hidden until checked) · `Excluir selecionados (N)` · `Esvaziar` (title `Esvaziar todos os assuntos virais pendentes`).
  - Card per topic (orange border `#ff9900`, bg `#ffa60017`): checkbox · clickable area (title `Clique para ver os virais` → `openViralModal(id, topic)`) containing orange badge **topic**, badge `«2.5M» Views`, muted clock + `Pendente` · actions: ✓✓ (title `Aprovar item`) → `handleViralAction('approve', id)`; 🗑 (title `Excluir item`) → `handleViralAction('reject', id)` — **no confirmation** (the `#modal-approved-topic` / `#modal-rejected-topic` confirm modals exist but are unused).
  - Empty: clock icon + `Nenhum item pendente`.
- Actions & feedback:
  - approve/reject single: `GET dashboard/user/searches/viral/topics/{approve|reject}/{id}` → `{success, message, viral_topic}`; toast message; card removed; on approve a new pill is appended to Aprovado (with a checkbox). 
  - bulk approve (pending only): sequential GET approve per id; toasts `N assunto(s) viral(is) aprovado(s) com sucesso!` / `N assunto(s) viral(is) não puderam ser aprovados.`; non-pending → `Aprovação em massa só está disponível para itens pendentes.`; none → `Nenhum item selecionado.`
  - bulk delete: confirm `#modal-confirm-bulk-delete-viral` (`Você realmente deseja excluir N assunto(s) viral(is) selecionado(s)?`, `Cancelar`/`Excluir`) → `POST /dashboard/user/searches/viral/topics/bulk-delete` JSON `{ids:[int], type:'approved'|'pending'}` → remove locally.
  - empty: confirm `#modal-confirm-empty-viral` (`Você realmente deseja esvaziar TODOS os assuntos virais aprovados|pendentes? Esta ação não pode ser desfeita.`, `Cancelar`/`Esvaziar`) → `POST /dashboard/user/searches/viral/topics/empty` `{type}` → reload after 500 ms.
  - remove approved pill: `#modal-remove-topic` (`Você realmente deseja remover este tópico viral? Esta ação não pode ser desfeita.`, `Cancelar`/`Remover`) → `GET dashboard/user/searches/viral/topics/remove/{id}` (CSRF header on a GET) → removes **all pills with the same topic text** (fade 300 ms).
  - add: `POST dashboard/user/searches/viral/topics/add` (form-urlencoded `topic`) → `{success, message, viral_topic}` → pill prepended (scale-in animation).
- `#viralModal` "Assuntos Virais - «topic»" (lg): loading `Buscando dados dos virais...`; `GET /dashboard/user/searches/viral-data/{id}` → grid (3 per row) of video cards: thumbnail (120 px, fallback `/back/static/placeholder.jpg`), `Views` / `Likes` / `Comments` (K/M), date `dd/mm/yyyy` (pt-BR) or `-`; click opens `item.url` in new tab. Empty: `Nenhum dado viral encontrado para este tópico.`; API failure `Erro ao carregar dados: «message|Erro desconhecido»`; network `Erro ao conectar com o servidor. Tente novamente.`; footer `Fechar`. (Twin endpoint `user-variables-viral-data/{id}` defined but unused.)

### 1.7 `#extractViralTopicsModal` — "Extrair Assuntos Virais" [OBS]
xl modal; same structure as the profile picker in §2 with prefix `vt-`:
- Loading `Carregando perfis com assuntos virais...`; source `GET /dashboard/user/searches/approved-profiles-viral-topics`.
- Search input `#vt-profile-search-input` (oninput filter by handle substring, case-insensitive) + clear button; `Nichos` / `Profissões` TomSelect multi (placeholders `Selecione os nichos...` / `Selecione as profissões...`), options = §5.3/§5.4; `Limpar Filtros`. Pre-selected from the owner's profile via `GET /dashboard/user/profile/get-niches-professions` (applied 100 ms + 500 ms after open).
- Grid 12/page; numbered pagination (all page numbers, prev/next). Empty after filter: `Nenhum perfil encontrado com os filtros aplicados.`; empty source: `Nenhum perfil com assuntos virais encontrado.`
- Card: social icon + `@handle`, up to 3 thumbnails (grey placeholders to fill 3), button `Extrair Assuntos Virais` (title `Extrair assuntos virais deste perfil`).
- Extract: overlay spinner `Extraindo assuntos virais...` + `@handle` → `POST /dashboard/user/searches/extract-profile` `{type:'topic_virais', eng_reversa_search_id}` (synchronous, **no job polling** in this path) → success: hide button, inline alert `Extração concluída!` / `«total_extracted» extraído(s) | «saved_count» novo(s) adicionado(s)` / `Atualize a página para ver os assuntos adicionados — clicando aqui` (reload link); toast `message || 'Assuntos virais extraídos com sucesso!'`; failure warning `Extração concluída com avisos.`; exception `Erro ao extrair assuntos virais. Tente novamente.` New topics land in **Pendente**. [INF]

### 1.8 Network calls — Minha Pesquisa (complete list)
| # | Method | URL | Request | Response (observed keys) | Used by |
|---|---|---|---|---|---|
| 1 | GET | `/dashboard/user/searches/variables/items?type={especialista\|avatar}` | — | `{success, message?, data:{ "<variableId>": {approved_manual:[{id, content, source?}], approved:[{id, content, plays, eng_reversa_result_id, source?}], pending:[{id, content, plays, eng_reversa_result_id}]}}}` | unified list (2 calls in parallel) |
| 2 | POST | `/dashboard/user/searches/variables/contents/add` | JSON `{id: variableId, value}` | `{type:'success', message, data:{id, content}}` | add-item Mode B, legacy add |
| 3 | POST | `/dashboard/user/searches/variables/contents/remove` | JSON `{id, source:'content'\|'pending'}` | `{success\|type, message}` | single + bulk delete (one call per item) |
| 4 | POST | `/dashboard/user/searches/variables/contents/empty-all` | — | `{success, message}` | Zerar toda a pesquisa |
| 5 | POST | `/dashboard/user/searches/approve-pending-item/{id}` | — (CSRF) | `{success\|type, message}` | approve single/bulk |
| 6 | POST | `/dashboard/user/searches/reject-pending-item/{id}` | — | idem | reject |
| 7 | GET | `/dashboard/user/searches/add-item-prompt` | — | `{is_active, prompt_system, include_variables}` | add-item open |
| 8 | POST | `/dashboard/user/searches/add-item-prompt` | `{prompt_system, is_active, include_variables}` | `{success, message}` | (hidden UI) |
| 9 | POST | `/dashboard/user/searches/add-item-prompt/test` | `{prompt_system, text, include_variables}` | `{success, result, message}` | (hidden UI) |
| 10 | POST | `/dashboard/user/searches/add-items-sync` | `{text}` (newline-joined) | `{status?:'error', message, saved, classified:{label:[content]}, unclassified:[{content, token}]}` | Mode A (90 s timeout) |
| 11 | POST | `/dashboard/user/searches/add-items-job` | `{text}` | `{success, job_id, message}` | Mode A fallback |
| 12 | GET | `/dashboard/user/searches/add-items-job/{job_id}` | — | `{status:'pending'\|'processing'\|<done>\|'error', saved, classified, unclassified, message}` | poll 2 s × 300 |
| 13 | GET | `/dashboard/user/searches/viral-data/{viralTopicId}` | — | `{success, message, data:[{plays, likes, comments, post_date, url, thumbnail}]}` | viralModal |
| 14 | GET | `/dashboard/user/searches/user-variables-viral-data/{id}` | — | same as 13 | unused |
| 15 | GET | `/dashboard/user/searches/viral/topics/{approve\|reject}/{id}` | — | `{success, message, viral_topic:{id, topic, total_plays, eng_reversa_result_id}}` | pending topic actions |
| 16 | POST | `/dashboard/user/searches/viral/topics/add` | form `topic` | `{success, message, viral_topic}` | add topic |
| 17 | GET | `/dashboard/user/searches/viral/topics/remove/{id}` | — | `{success, message}` | remove approved topic |
| 18 | POST | `/dashboard/user/searches/viral/topics/bulk-delete` | `{ids, type}` | `{success, message}` | bulk delete topics |
| 19 | POST | `/dashboard/user/searches/viral/topics/empty` | `{type}` | `{success, message}` | empty topics |
| 20 | GET | `/dashboard/user/searches/approved-profiles` | — | see §2.5 | orphan modal / Screen 2 |
| 21 | GET | `/dashboard/user/searches/approved-profiles-viral-topics` | — | same shape | viral-topics modal |
| 22 | GET | `/dashboard/user/profile/get-niches-professions` | — | `{success, data:{niches:[id], professions:[id]}}` | pre-select filters |
| 23 | POST | `/dashboard/user/searches/extract-profile` | `{type:'myPublic'\|'topic_virais', eng_reversa_search_id}` | `{success, message, job_id?, status?, total_extracted, saved_count, skipped_count, skipped_items:[{variable, content}]}` | extraction |
| 24 | GET | `/dashboard/user/searches/extract-profile-status/{job_id}` | — | `{status:'completed'\|'error'\|…, step, progress (0-100), success, message, + counts as 23}` | poll 5 s × 60 |
| 25 | GET | `/dashboard/user/searches/profile-viral-search/{engReversaSearchId}` | `Accept: application/json` | see §2.4 | Pesquisa modal |
| 26 | POST | `/dashboard/user/searches/profile-viral-search/save` | `{items:[{variable_id, content, eng_reversa_result_id, plays}]}` | `{success, message}` | add to my research |
| 27 | POST | `/dashboard/user/searches/variables/contents/bulk-delete` | `{items:[{id,source}], items_by_source:{content:[], pending:[]}, type, variable_id}` | `{success, message}` | legacy per-variable |
| 28 | POST | `/dashboard/user/searches/variables/contents/empty` | `{variable_id, type:'approved'\|'pending'}` | `{success, message}` | legacy per-variable |
| 29 | POST | `/dashboard/user/searches/save` | multipart `form#save-variables` | `{…}` / 422 | legacy "Atualizar" |
| 30 | POST/GET | `/dashboard/user/searches/store`, `…/view/{id}`, `…/remove/{id}`, `…/variables/apply` | legacy "Criar Pesquisa" (options `transcribe_only`, `transcribe_extract`, `instagram_comments`, `youtube_comments`) | `{type, message, redirect, refresh, reset}`, `{data_gpt, data_gpt_edit, content}` | `searches.js` only; no DOM on this page |
Polling: add-items-job 2 s (max 300); extract-profile-status 5 s (max 60 ≈ 5 min; timeout message `Timeout: o processamento demorou mais que o esperado.`). No websockets/Livewire on this screen.

### 1.9 State machines — Minha Pesquisa
**Research item** [OBS statuses / INF transitions]:
```
                (extraction job / AI classification / profile-viral-search save?) 
 server job ──► PENDING ──approve (user)──► APPROVED (source=pending, keeps plays + eng_reversa_result_id)
                   │
                   └──reject (user)──► deleted (or REJECTED, hidden)        [LIVE: soft vs hard]
 user manual add (contents/add) ──► APPROVED_MANUAL (source=content, no plays/video)
 APPROVED / APPROVED_MANUAL ──delete (user)──► deleted
 empty-all (user) ──► all items of all variables deleted (pending included)
```
- Which status does `profile-viral-search/save` create? The UI shows "✓ Já adicionado" and the toast; whether items land as pending or approved is not visible. [LIVE]
- AI "add-items" path: lines classified into variables → saved (likely approved_manual, `saved` count) ; unclassified returned with a `token`. [INF/LIVE]

**Viral topic**: `PENDING` (from `topic_virais` extraction) → approve → `APPROVED` (shows views) · reject → deleted; manual add → `APPROVED` with `eng_reversa_result_id` null ("Manual"); remove/bulk-delete/empty → deleted.

**Add-items job**: `pending → processing → (completed|done) | error` (client only distinguishes `pending`/`processing` vs anything else).

---

## 2 · Screen 2 — Extrair Pesquisa (`GET /dashboard/user/searches/extract-profile`)

`<title>Extrair Pesquisa de Perfil Viral</title>`.

Purpose: browse a **curated catalogue of "approved" viral profiles** (scraped Instagram/other profiles that the platform has already analysed — the "eng_reversa" pipeline), filter by niche/profession, open the research extracted from a profile's viral videos (values per variable, each tied to a video + headline excerpt + views), and copy selected values into **Minha Pesquisa**.

### 2.1 Layout [OBS]
```
┌ header ─────────────────────────────────────────────────────────────┐
│ H2 "Extrair Pesquisa de Perfil Viral"                [Minha Pesquisa] (btn-outline → /dashboard/user/searches)
│ P  "Selecione perfis aprovados para extrair e adicionar às suas      │
│     variáveis de pesquisa."                                          │
└─────────────────────────────────────────────────────────────────────┘
┌ card ───────────────────────────────────────────────────────────────┐
│ [🔍 input "Buscar perfis por nome..."][✕ clear]                      │
│ ┌ Nichos (TomSelect multi) ┐ ┌ Profissões (TomSelect multi) ┐        │
│                                             [Limpar Filtros]         │
│ #extract-profiles-loading  "Carregando perfis aprovados..."          │
│ #extract-profiles-empty    "Nenhum perfil aprovado encontrado."      │
│ #extract-profiles-content → .row-cards#profiles-container (3 cols)   │
│                            #profiles-pagination                      │
└─────────────────────────────────────────────────────────────────────┘
```
- The page also embeds `#profileViralSearchModal` (§2.4). No "Extrair" action exists on this page (the profiles are already extracted server-side).

### 2.2 Filters [OBS]
| Control | id | Behaviour |
|---|---|---|
| Name search | `profile-search-input` | `onkeyup` → lowercased/trimmed substring match on `profile` (handle). Resets to page 1. |
| Clear (icon) | button.btn-outline-danger `title="Limpar busca"` | clears search + both selects; gets class `has-filters` when any filter active (visual highlight). |
| Nichos | `profile-filter-niche` (`name=niche`, multiple) → TomSelect, placeholder `Selecione os nichos...`, `create:false`, dropdown attached to body | match if profile.niche_ids ∩ selected ≠ ∅ (OR within the select). |
| Profissões | `profile-filter-profession` (`name=profession`, multiple) → TomSelect, placeholder `Selecione as profissões...` | idem on `profession_ids`. Niche AND profession combine with AND. |
| `Limpar Filtros` | second clear button | same as clear icon. |
- **Default filters = the account owner's own niches/professions** from `GET /dashboard/user/profile/get-niches-professions` (`data.niches`, `data.professions` = id arrays), applied 500 ms after init (silent `setValue`). So first render is pre-filtered. 
- All filtering & pagination is **client-side** over the full list returned once.
- Option lists: §5.3 (28 niches) and §5.4 (102 professions) — values are numeric ids.

### 2.3 Profile card + pagination [OBS]
- Grid `col-md-6 col-lg-4` (3 per row desktop), **24 per page** on this screen (12 in the orphan modal).
- Card (hover lift −4 px + shadow):
  - Row: social icon (Instagram glyph if `social==='instagram'`, else a generic glyph) + `@«profile»` (h5).
  - 3 thumbnails strip, 120 px tall, `object-fit:cover`, fallback `/back/static/placeholder.jpg`; grey image-placeholder tiles fill up to 3.
  - Buttons (pill, 36 px): `Vídeos` (purple gradient `#6d28d9→#7c3aed`, title `Ver vídeos deste perfil`) → new tab `/dashboard/user/library?profile=«handle»`; `Pesquisa` (teal gradient `#0d9488→#14b8a6`, title `Ver pesquisa extraída deste perfil`) → `openProfileViralSearch(handle, eng_reversa_search_id)`.
- Pagination (only when >1 page): `‹` prev (disabled on p1) · windowed numbers (current ±2, with `1 …` and `… N` ellipses) · `›` next; below: `Mostrando «a»-«b» de «total» perfil(is)`. Changing page scrolls the grid into view (smooth).
- Filtered-empty text: `Nenhum perfil encontrado` + ` com o termo "«q»"` / ` com os nichos selecionados` / ` com as profissões selecionadas` joined with ` e ` + `.`
- Load failure: empty state + toast `Erro ao carregar perfis. Tente novamente.`

### 2.4 Modal `#profileViralSearchModal` — "Pesquisa do perfil @handle" [OBS]
xl, min-width 1000 px, body max-height 70vh scroll.
- Open: reset state; spinner `Carregando pesquisa...`; `GET /dashboard/user/searches/profile-viral-search/{eng_reversa_search_id}`.
- Response `data` = array of **groups**: `{variable_id, variable_name, label, items:[{result_id, plays, post_link, headline, value, thumbnail, already_added}]}`.
- Empty / `!success` / no groups → `Nenhuma extração encontrada para este perfil.`; exception also toasts `Erro ao carregar a pesquisa.`
- Toolbar: `#pvs-count` = `«G» variável(is) · «N» item(s)` · button `Selecionar todos` ⇄ `Desmarcar todos` (toggles every enabled checkbox in all groups, including collapsed ones) · button `Adicionar à minha pesquisa` + count pill (hidden while 0 selected).
- **Group (accordion)**: chevron + group `label` (`#c4b5fd`) + count badge; first group expanded, others collapsed; per-group sort chips `↓ Views` (default active) and `Mais recente` (sort by `result_id` desc — i.e. newest video id, not date).
- **Item row**: checkbox (disabled+checked if `already_added`) · 64×64 thumbnail (or play-icon tile) · **value** (bold, `#e9d5ff`; struck-through grey if already added) · headline excerpt: the sentence(s) of the source video's headline/transcript that contain the value — `truncateHeadline`: cut left at the last `.?!` before the match, cut right at the first `.?!` after max(matchEnd, leftCut+30); matched value **bold** `#e9d5ff`, rest dimmed; if the value is not found literally → dimmed full headline + bold `[value]` · meta: views badge (`1.2M`/`3.4K`/pt-BR integer) · link `Ver vídeo ↗` → `/dashboard/user/library?viral_result_id=«result_id»` (new tab) · `✓ Já adicionado` when applicable.
- Selection key = `«result_id»_«variable_id»-«index»`.
- Save: `POST /dashboard/user/searches/profile-viral-search/save` JSON `{items:[{variable_id:int, content:value, eng_reversa_result_id:int, plays:string|null}]}`; button shows spinner `Salvando...`. Success → toast `message`; selected rows become disabled + struck-through + `✓ Já adicionado`; button hidden; counters reset. `!success` → warning `message || 'Erro ao salvar.'`; exception → `Erro ao salvar variáveis. Tente novamente.` (searches-page copy uses `Erro ao processar a solicitação.`).
- Footer: `Fechar`.

### 2.5 Network calls — Extrair Pesquisa
| Method | URL | Request | Response |
|---|---|---|---|
| GET | `/dashboard/user/profile/get-niches-professions` | — | `{success, data:{niches:[int], professions:[int]}}` |
| GET | `/dashboard/user/searches/approved-profiles` | — | `{success, data:[{profile:string(handle, no @), social:'instagram'\|…, eng_reversa_search_id:int, thumbnails:[url≤3], niche_ids:[int], profession_ids:[int]}]}` (whole catalogue, unpaged) |
| GET | `/dashboard/user/searches/profile-viral-search/{eng_reversa_search_id}` | — | groups as §2.4 |
| POST | `/dashboard/user/searches/profile-viral-search/save` | `{items:[…]}` | `{success, message}` |
No polling on this screen. CSRF via header. Library deep links: `/dashboard/user/library?profile=`, `?viral_result_id=`.

### 2.6 Hidden variant — per-profile extraction job (searches-page orphan modal) [OBS]
`extractProfileData(profile, social, eng_reversa_search_id)` (button `Extrair`, title `Extrair pesquisa deste perfil`, blue gradient, rendered with `display:none`): determines `type` from the active tab (`myPublic` for the old `avatar` tab, `topic_virais` for `#subject-viral`; else toast `Não foi possível determinar o tipo de extração. Por favor, selecione uma tab.`) → overlay `Extraindo dados...` → `POST extract-profile` → if `job_id`, poll `extract-profile-status/{job_id}` every 5 s up to 60× showing `«step || 'Processando IA...'»` + `«progress»%` → result alert: `Extração concluída!` or `Extração concluída (sem novos itens)!`, `«total» item(ns) extraído(s) | «saved» novo(s) adicionado(s) | «skipped» já existentes`, `Atualize a página para ver os itens adicionados clicando aqui`, and `Itens já existiam:` list `(«variable») «content»`; toasts `Extração concluída com sucesso!` / `Extração concluída com avisos.` / `Erro ao extrair dados do perfil. Tente novamente.` → evidence of a server **job with `step` + `progress`** used to extract research into the user's variables. Current product hides it in favour of the pre-computed `profile-viral-search` browse-and-pick flow.

---

## 3 · Screen 3 — Segundo Cérebro (`GET /dashboard/user/cores`)

`<title>Cérebros Personalizados</title>`. Purpose: a set of **"brains" (cores)** — structured knowledge bases about the creator, each filled by answering a questionnaire (typed or spoken) or uploading a document; consumed as context when generating roteiros/headlines and in chat (`@cerebro`).

### 3.1 List page layout [OBS]
```
┌ header ─────────────────────────────────────────────────────────────┐
│ H2 "Cérebros Personalizados"                         [+ Criar Cérebro] (hidden < sm)
│ P  "Segundo cérebro"                                                 │
└─────────────────────────────────────────────────────────────────────┘
┌ alert-info (clickable → #modal-yt-video) ───────────────────────────┐
│ [▶ thumb] Aprenda a usar o Cérebro Personalizado para turbinar suas │
│           postagens!  Assistir agora.                                │
└─────────────────────────────────────────────────────────────────────┘
┌ card → row of col-md-4 cards (3 per row) ───────────────────────────┐
│ ┌──────────────┐ badge [Vazio|Pronto]                                │
│ │ H2 «name»    │                                                     │
│ │ [Acessar Cérebro] (btn-secondary, full width → /dashboard/user/cores/edit/{id})
│ └──────────────┘                                                     │
└─────────────────────────────────────────────────────────────────────┘
```
- Badge colours: `Vazio` → bg `rgba(128,128,128,0.3)`, white text; `Pronto` → bg `rgba(59,92,255,1)`, white text. Other statuses (e.g. processing) are not present in the snapshot. [LIVE]
- Cards seen for the account owner (order as rendered): `História de Criação` (id 8, Vazio) · `Histórias de Vida do Especialista` (9, Vazio) · `Método do Especialista` (14, Vazio) · `Núcleo de Influência` (3081, Pronto) · `Call de diagnóstico` (3741, Pronto) · `Formulário` (4191, Pronto) · `Narrativa` (4192, Pronto).
  - Low ids (8, 9, 14) look like **platform default brain templates** shared by all users; high ids are user-created. But `headlines~favorites.html` lists the same 7 names with ids 8522, 8772–8775, 9385, 9386 → either per-workspace clones or a separate "brain instance" table. [LIVE]
- **No edit/delete controls on the list cards**, although `brains.js` binds `.j_core_edit` (→ `#modal-edit-core`, pre-filled `core_id`, `name` from `data-core-id` / `data-core-name`) and `.j_core_delete` (→ `#modal-core-delete`, confirm link `href=/dashboard/user/cores/custom/delete/{id}` — a GET navigation). Those triggers probably live on the edit page or only render for custom brains. [LIVE]
- Empty list state: not in snapshot. [LIVE]
- Video modal `#modal-yt-video` "Como usar o Cérebro Personalizado": lg, iframe (Bunny `iframe.mediadelivery.net/play/…`, 600 px); iframe `src` cleared on close.

### 3.2 Modal `#modal-make-core` — "Criar Cérebro Personalizado" [OBS]
`form#make_core` (`autocomplete=off`, password-manager opt-outs).
| Field | name / id | Type | Options (value = label) | Required | Notes |
|---|---|---|---|---|---|
| `Tipo de Cérebro:` | `core_type` / `core_type_input` | select | `custom` = `Personalizado` (selected) · `beliefs` = `Crença` | yes (default) | |
| `Nome do Cérebro:` | `name` / `name_input` | text, `readonly` until focus | placeholder `Ex: Reels Instagram` | server-validated (422 `errors.name[0]`) | |
Footer: `Cancelar` · `Criar Cérebro` (`#button_add_core`, text `Aguarde criando...` while posting).
- Submit → `POST /dashboard/user/cores/custom/add` (multipart FormData: `_token` hidden field [OBS in full page], `core_type`, `name`; jQuery also sends `X-CSRF-TOKEN` via a page-level `$.ajaxSetup`).
- Response `{type, message, button?, redirect?, refresh?, reset?}` → `toastr[type](message)`; `redirect` → navigate after 1 s (expected: the new brain's edit page) [INF]; `refresh` → reload.
- 422 → first `errors.name` message, else `Ocorreu um erro ao criar o núcleo.`; button text restored to `criar` (lowercase, sic).

### 3.3 Modal `#modal-edit-core` — "Editar Cérebro Personalizado" [OBS]
`form#edit_core`: hidden `core_id`; `Nome do Cérebro:` (`name`, readonly-until-focus, placeholder `Ex: Reels Instagram`). Footer `Cancelar` · `Atualizar Cérebro` (`#button_update_core`, `Aguarde atualizando...`). → `POST /dashboard/user/cores/custom/update` (FormData `core_id`, `name`) → envelope as above; `reset` → reset form + hide modal. Error fallback `Ocorreu um erro ao atualizar o núcleo.`; button restored to `Atualizar`. Type is **not editable** after creation.

### 3.4 Delete [OBS]
`#modal-core-delete` (markup not on list page) confirm anchor → **GET** `/dashboard/user/cores/custom/delete/{id}` (full navigation; server redirects back) [INF].

### 3.5 Brain editor page `GET /dashboard/user/cores/edit/{id}` — reconstructed from `brains.js` (page HTML NOT saved) [OBS logic / LIVE markup]
The editor is a **questionnaire**: one block per question (`question_id`), each answerable by **text** or **voice**.
- Per-question container `#info-area[«qid»]`:
  - Toggle `.option-speek[data-id=qid]` with label `#text-speek[qid]`: `Prefiro falar` ⇄ `Prefiro escrever` (switches between `#txt-area[qid]` and `#audio-area[qid]`; mic/pencil icons swap).
  - Text: `textarea.form-area#form-area[qid]` (`name="response[qid]"` [INF]); original value cached; any change vs original → hidden `permission[qid]=1` and status line **`Alterações não aplicadas`** (class `waiting`) + per-question button `.aplicarAlteracoes#…[qid]`; reverting to original → `permission=0`, status hidden.
  - Voice: `#record-button[qid]` start/stop; mime `audio/webm` → `audio/mp4` → `audio/mp3` (else `Ops! Parece que seu navegador não tem suporte para esse recurso, tente outro!`); 128 kbps; timer `mm:ss` `#record-timer[qid]`; live waveform on `<canvas>` (164 bars, `#0054A6`); recording clears the textarea; mic error `Erro ao acessar o microfone. Verifique as permissões!`. On stop: player `#audio-player[qid]` with the blob, delete button `#delete-button[qid]` (resets), status `Alterações não aplicadas`, `permission=1`.
  - Status line states (CSS classes on `.statusLine`): `waiting` (`Alterações não aplicadas`) → `proccess` (`Aguarde, processando resposta!`) → `success` (text not in JS; server-rendered [LIVE]).
- **Apply one question** (`.aplicarAlteracoes`): label `Aguarde o upload do audio...`; if a recording exists, upload it in **1 MiB chunks**: `POST /dashboard/user/cores/upload-audio-chunk` multipart `{audio_chunk (chunk_i.webm), chunk_number, total_chunks, question_id}` (CSRF header) → last response `{success, file}` gives the stored file name; then `POST /dashboard/user/cores/update` FormData `{core_id, question_id, response[qid], audio[qid]?}` → UI switches to `Aguarde, processando resposta!`, hides inputs, removes the apply button, disables global save. Errors: `alert('Erro ao enviar o áudio. Tente novamente.')`, `alert('Erro ao enviar. Tente novamente.')`, `alert('Nenhuma informação encontrada para enviar.')`.
- **Apply all** (`form#brains` submit, button `#brain_button_save` "Aplicar Alterações"): label `Aguarde, processando respostas!`; uploads every pending recording (chunked), then `POST /dashboard/user/cores/update` with the whole form + `typeSubmit=aplica_todos` + `audio[qid]` file names → envelope (`type/message/redirect/refresh`); error fallback `Ocorreu um erro ao atualizar o cérebro.`
- **Upload a document** (`#modal-upload-core`): dropzone `#upload-dropzone` (drag&drop or click; label `Clique para escolher ou arraste o arquivo aqui` → file name in bold), input `#file`, hidden `#core_upload_id`; button `#button_upload_core` `Enviar arquivo` (`Processando…` spinner). Validation: required (`Selecione um arquivo antes de enviar.`), extension ∈ `pdf, docx, txt, md, csv` (`Formato não suportado. Use PDF, DOCX, TXT, MD ou CSV.`), ≤ **20 MB** (`Arquivo muito grande. Limite: 20 MB.`). → `POST /dashboard/user/cores/upload-file` FormData `{core_id, file, _token}` → success redirects to `/dashboard/user/cores`; error toast `message || 'Erro ao enviar arquivo. Tente novamente.'`
- **Leave guard**: counter `audioPendente` (recordings not yet uploaded). While >0: `beforeunload` prompt `Você tem uploads em andamento. Tem certeza de que deseja sair?`; F5 / Ctrl+R / Cmd+R / browser-back / mouse leaving the top of the window open `#modal-reload` [LIVE: its text].

### 3.6 Network calls — Segundo Cérebro
| Method | URL | Request | Response |
|---|---|---|---|
| GET | `/dashboard/user/cores` | — | Blade list |
| POST | `/dashboard/user/cores/custom/add` | FormData `core_type ∈ {custom, beliefs}`, `name` | `{type, message, redirect?, refresh?, button?, reset?}` / 422 `{errors:{name:[…]}}` |
| POST | `/dashboard/user/cores/custom/update` | FormData `core_id`, `name` | envelope |
| GET | `/dashboard/user/cores/custom/delete/{id}` | — (navigation) | redirect [INF] |
| GET | `/dashboard/user/cores/edit/{id}` | — | Blade questionnaire |
| POST | `/dashboard/user/cores/upload-audio-chunk` | multipart `audio_chunk, chunk_number, total_chunks, question_id` | `{success, file}` (on final chunk) |
| POST | `/dashboard/user/cores/update` | FormData `core_id, question_id, response[qid], audio[qid]` **or** whole form + `typeSubmit=aplica_todos` | envelope |
| POST | `/dashboard/user/cores/upload-file` | FormData `core_id, file, _token` | 2xx → redirect client-side; error `{message}` |
No polling on the list page: "Pronto" appears only after a reload. [INF: answer processing is an async server job; LIVE: whether the edit page polls/Pusher-updates the `proccess → success` status]

### 3.7 State machines — Brain
```
Brain:   (create) ──► VAZIO ──first answer applied/doc uploaded──► [PROCESSANDO?] ──server job done──► PRONTO
                                                                       ▲                                  │
                                                                       └──── answer edited & applied ◄────┘
Question: unchanged ──edit/record──► WAITING("Alterações não aplicadas") ──apply──► PROCESS("Aguarde, processando resposta!") ──job──► SUCCESS
```
Triggers: user (create, answer, apply, upload); server job (transcribe audio → text, summarise/structure answers into the brain content, mark Pronto). [INF]

---

## 4 · Data model (per entity)

Types are what the client relies on; server-only columns marked [INF].

**ResearchVariable** (static taxonomy, §5.1) — `id:int`, `label:string`, `type: 'avatar' (UI "Meu Público") | 'especialista' (UI "Sobre Mim") | null (global helper lists)`, display order [INF `sort_order`]. No slug in source.

**ResearchItem** — two physical stores, unified in the UI [OBS comment: "Itens pendentes sempre vêm de UserVariablePending"]:
| field | type | notes |
|---|---|---|
| `id` | int | unique **per store** (remove/approve endpoints need `source`) |
| `source` | `'content' \| 'pending'` | `content` = UserVariableContent (manual approved); `pending` = UserVariablePending (extracted; stays `pending` source after approval) |
| `status` (client-derived) | `'approved_manual' \| 'approved' \| 'pending'` | bucket key in API response |
| `variable_id` | int | FK ResearchVariable |
| `content` | string | the value (e.g. `Medo de envelhecer`) |
| `plays` | int \| numeric string \| null | views of the source video; sort key "Mais Views" |
| `eng_reversa_result_id` | int \| null | source viral video (library `viral_result_id`) |
| owner | [INF] `user_id` + `workspace_id` | workspace meta present on page |
| `created_at` | [INF] | "Mais Recentes" sorts by `id` desc, not by date |

**ViralTopic** — `id:int`, `topic:string(≤255)`, `total_plays:int`, `eng_reversa_result_id:int|null` (null/0 ⇒ "Manual"), status `pending|approved` [OBS via tabs], owner [INF]. Detail videos via `viral-data/{id}`: `{plays, likes, comments, post_date (ISO), url, thumbnail}`.

**ApprovedProfile** (catalogue = scraped "eng_reversa_search") — `eng_reversa_search_id:int`, `profile:string` (handle), `social:'instagram'|…`, `thumbnails:string[≤3]` (S3 URLs), `niche_ids:int[]`, `profession_ids:int[]`. "Approved" = curated/processed by the platform [INF]; separate lists for research (`approved-profiles`) and viral topics (`approved-profiles-viral-topics`).

**ProfileResearchGroup** — `{variable_id:int, variable_name:string, label:string, items: ProfileResearchHit[]}`; **ProfileResearchHit** — `{result_id:int (viral video), plays:int|string, post_link:url, headline:string (caption/hook text), value:string, thumbnail:url, already_added:bool}`.

**AddItemPromptConfig** (per user or global [LIVE]) — `{prompt_system:text, is_active:bool, include_variables:bool}`.

**AddItemsJob** — `{job_id, status: pending|processing|<done>|error, saved:int, classified:{[variableLabel]: string[]}, unclassified:[{content, token}], message}`.

**ExtractProfileJob** — `{job_id, status: …|completed|error, step:string, progress:0-100, success, message, total_extracted, saved_count, skipped_count, skipped_items:[{variable, content}]}`; input `{type:'myPublic'|'topic_virais', eng_reversa_search_id}`.

**Niche** `{id, name}` (28) · **Profession** `{id, name}` (102) · **UserProfileTargeting** `{niches:int[], professions:int[]}` (from Minha conta).

**Brain (Core)** — `id:int`, `name:string`, `core_type:'custom'|'beliefs'` (+ built-in templates, type unknown [LIVE]), `status: Vazio|Pronto|…`, owner/workspace [INF], content/summary [INF], questions[]. Used downstream as `core_id` (roteiro), `core[]` (favorites roteiro: "Adicionar Cérebro como fonte de informação:" + "Adicionar Crenças:" — the beliefs select lists `core_type='beliefs'` brains; empty for the account owner), `specific_core_id` ("Núcleo Especifico:" in headline generation), and chat `@cerebro` mentions.

**BrainQuestion** — `question_id:int`, question text [LIVE], `response:text`, `audio:file name` (from chunk upload), `permission:0|1` (dirty flag), status `waiting|proccess|success`.

---

## 5 · Verbatim taxonomies

### 5.1 Research variables (`window.unifiedVariableLabels` / `unifiedVariableTypes`, select order) [OBS]
`⎵` marks a trailing space present in the source label.
| id | label (verbatim) | type | UI group |
|---:|---|---|---|
| 18 | Desejos do meu público | avatar | Meu Público |
| 17 | Dores do meu público⎵ | avatar | Meu Público |
| 16 | Características demográficas do meu público | avatar | Meu Público |
| 25 | Qualidades do meu público | avatar | Meu Público |
| 26 | Defeitos do meu público | avatar | Meu Público |
| 15 | Itens conhecidos pelo meu público | avatar | Meu Público |
| 14 | Instituições conhecidas pelo meu público | avatar | Meu Público |
| 13 | Pessoas e personagens conhecidos pelo meu público | avatar | Meu Público |
| 32 | Inimigos do meu público⎵ | avatar | Meu Público |
| 11 | Filmes, séries ou músicas conhecidas pelo meu público | avatar | Meu Público |
| 19 | Eventos conhecidos pelo meu público⎵ | avatar | Meu Público |
| 20 | Locais conhecidos pelo meu público | avatar | Meu Público |
| 21 | Momentos de vida do meu público | avatar | Meu Público |
| 10 | Objeções do meu público⎵ | avatar | Meu Público |
| 9 | Medos do meu público | avatar | Meu Público |
| 8 | Crenças do meu público⎵ | avatar | Meu Público |
| 5 | Desejos e conquistas que eu realizei⎵ | especialista | Sobre Mim |
| 34 | Produtos conhecidos pelo meu público | avatar | Meu Público |
| 4 | Situações dolorosas que eu enfrentei⎵ | especialista | Sobre Mim |
| 30 | Meus hábitos e hobbies⎵ | especialista | Sobre Mim |
| 31 | Minha formação profissional⎵ | especialista | Sobre Mim |
| 28 | Quem eu sou (idade, estado civil, nacionalidade, etc) | especialista | Sobre Mim |
| 7 | Minhas qualidades | especialista | Sobre Mim |
| 27 | Meus defeitos | especialista | Sobre Mim |
| 6 | Técnicas, serviços e procedimentos que eu efetuo⎵ | especialista | Sobre Mim |
| 12 | Técnicas, serviços e procedimentos que eu não recomendo | especialista | Sobre Mim |
| 3 | Hábitos que eu recomendo para o meu público | especialista | Sobre Mim |
| 2 | Hábitos que eu não recomendo para o meu público⎵ | especialista | Sobre Mim |
| 1 | Crenças e ideias que eu defendo | especialista | Sobre Mim |
| 22 | Verbos Poderosos | null | (global) |
| 23 | Adjetivos Poderosos | null | (global) |
| 24 | Momento do dia | null | (global) |
| 29 | GPT | null | (global) |
- Group labels in UI: `Meu Público` (avatar, badge `#0d6efd`) / `Sobre Mim` (especialista, badge `#7c3aed`). Legacy tab ids: `public` (avatar) and `me` (especialista); extraction type for avatar = `myPublic`.
- Type-`null` variables are **not returned** by the two `variables/items` calls (only `especialista` and `avatar` are fetched), so selecting them in the filter always yields `Nenhum item encontrado.` [INF from code; LIVE]
- Slugs: **none in source**. If a rebuild needs slugs, derive them (proposal, not observed): `publico_desejos(18)`, `publico_dores(17)`, `publico_demografia(16)`, `publico_qualidades(25)`, `publico_defeitos(26)`, `publico_itens(15)`, `publico_instituicoes(14)`, `publico_pessoas(13)`, `publico_inimigos(32)`, `publico_midia(11)`, `publico_eventos(19)`, `publico_locais(20)`, `publico_momentos_vida(21)`, `publico_objecoes(10)`, `publico_medos(9)`, `publico_crencas(8)`, `publico_produtos(34)`, `eu_conquistas(5)`, `eu_situacoes_dolorosas(4)`, `eu_habitos_hobbies(30)`, `eu_formacao(31)`, `eu_quem_sou(28)`, `eu_qualidades(7)`, `eu_defeitos(27)`, `eu_tecnicas_efetuo(6)`, `eu_tecnicas_nao_recomendo(12)`, `eu_habitos_recomendo(3)`, `eu_habitos_nao_recomendo(2)`, `eu_crencas(1)`, `verbos_poderosos(22)`, `adjetivos_poderosos(23)`, `momento_do_dia(24)`, `gpt(29)`.

### 5.2 Status / filter enums [OBS]
- Unified list: sort `recent|plays`; status filter `approved|pending`; item status `approved_manual|approved|pending`; source `content|pending`.
- Viral topics: tab/bulk `type` = `approved|pending`; action path segment `approve|reject`.
- Extraction `type`: `myPublic | topic_virais` (legacy UI also implies an `especialista` counterpart — not seen [LIVE]).
- Brain `core_type`: `custom` (`Personalizado`) | `beliefs` (`Crença`). Brain badge: `Vazio | Pronto`.
- Legacy "Criar Pesquisa" extract options: `transcribe_only`, `transcribe_extract`, `instagram_comments`, `youtube_comments` (labels not in DOM).

### 5.3 Nichos (`profile-filter-niche`, value=id) [OBS]
7=Beleza & Estética · 25=Casa & Decoração · 21=Comunicação & Liderança · 33=Construção Civil · 22=Criação de Filhos · 18=Cripto · 27=Culinária · 9=Desenvolvimento Pessoal · 20=Direito · 4=Educação · 28=Emagrecimento · 13=Emagrecimento e Dieta · 5=Empreendedorismo/Business · 6=Espiritualidade · 3=Finanças · 29=Imigração · 26=Imobiliário · 19=Marketing Digital · 8=Moda & Estilo · 31=Pets & Animais · 2=Relacionamentos · 1=Saúde e Bem-Estar · 14=Saúde Mental · 17=Tech & IA · 24=Trends do Momento · 32=Tributação Fiscal · 30=Turismo & Viagem · 23=Vendas  (28 options; ids 10–12, 15, 16 absent ⇒ deleted/inactive niches [INF])

### 5.4 Profissões (`profile-filter-profession`, value=id) [OBS]
25=Acupunturista · 70=Advogado Administrativo · 72=Advogado Ambiental · 64=Advogado Civil · 74=Advogado Constitucional · 75=Advogado de Consumidor · 67=Advogado de Família · 76=Advogado Digital · 68=Advogado Empresarial · 71=Advogado Imobiliário · 73=Advogado Internacional · 65=Advogado Penal · 77=Advogado Previdenciário · 66=Advogado Trabalhista · 69=Advogado Tributário · 85=Agente de Turismo · 20=Arquiteto(a) · 102=Auditor Fiscal · 3=Autor(a) · 95=Breathwork · 18=Cabeleireiro(a) · 56=Chef de Cozinha · 105=Cirurgião Plástico · 27=Coach · 57=Confeiteiro · 54=Consultor de Imagem · 49=Contador(a) · 62=Copywriter · 82=Corretor de Imóveis · 90=Corretor de seguro de vida · 21=Dentista · 79=Designer de Interiores · 100=Designer de joias · 52=Designer de Sobrancelhas · 60=Designer Gráfico · 28=Economista · 23=Empreendedor(a) · 92=Enfermagem · 80=Engenheiro · 15=Esteticista · 32=Estrategista de Marca · 2=Farmacêutico(a) · 14=Fisioterapeuta · 47=Fisioterapeuta Pélvico · 106=Fonoaudiólogo · 55=Fotógrafo · 61=Gestor de Tráfego/Media Buyer · 22=Gestor(a) · 83=Higienista Ocupacional · 30=Influenciador(a) · 31=Investidor(a) · 99=Joalheira · 84=Jornalista · 78=Juiz · 51=Líder Religioso · 53=Maquiador(a) · 26=Marketeiro(a) · 98=Medicina Regenerativa · 37=Médico Cardiologista · 12=Médico Cirurgião · 33=Médico Dermatologista · 38=Médico Endocrinologista · 101=Médico geral · 89=Médico Geriatra · 36=Médico Ginecologista · 43=Médico Integrativo · 39=Médico Neurologista · 87=Médico Nutrólogo · 104=Médico Obstetra · 40=Médico Oftalmologista · 34=Médico Ortopedista · 91=Medico Otorrinolaringologia · 35=Médico Pediatra · 8=Médico Psiquiatra · 93=Medico Radiologia · 103=Médico ultrassonografista · 41=Médico Urologista · 42=Médico Veterinário · 50=Mentor(a) · 24=Moda · 97=Musculação · 4=Neurocientista · 16=Nutricionista · 81=Paisagista · 5=Pastor(a) · 48=Personal Trainer · 94=Professor de Yoga · 29=Professor(a) · 63=Programador(a) · 46=Psicanalista · 44=Psicólogo Infantil · 7=Psicólogo(a) · 45=Psicoterapeuta · 86=Quiropraxista · 59=Social Media · 58=Sommelier · 6=Teólogo(a) · 9=Terapeuta · 10=Terapeuta Holístico · 96=Terapeuta Somatico · 13=Vendedor(a) · 19=Visagista  (102 options; same list in all four profile pickers)

### 5.5 Brains seen (names verbatim) [OBS]
Templates/defaults (likely): `História de Criação`, `Histórias de Vida do Especialista`, `Método do Especialista`. User-created: `Núcleo de Influência`, `Call de diagnóstico`, `Formulário`, `Narrativa`. Brain types: `Personalizado` (`custom`), `Crença` (`beliefs`). **Questionnaire questions per brain type are not in any saved file** (they render server-side on `/dashboard/user/cores/edit/{id}`). [LIVE]

### 5.6 Sample pending viral topics (account owner, server-rendered) [OBS]
`empreendedorismo` 2.5M · `trabalhar menos (desejo)` 1.6M · `Elon Musk` 1.4M · `finanças das famílias` 1.1M · `profissões que não precisam de faculdade` 1M · `vendas de produtos na internet` 928.2K · `produtos digitais` 852.7K · `capital de risco` 577.6K · `objeção de venda` 334.5K · `juros compostos` 321.2K — sorted by views desc; topics are short noun phrases, sometimes with a parenthesised variable hint (`(desejo)`).

---

## 6 · Server-side pipeline behind each action

### 6.1 Viral-profile research ("engenharia reversa") — **[INF]** unless noted
1. **Catalogue ingestion (platform, offline):** curated Instagram (and other) profiles are scraped into `eng_reversa_search` (one per profile) with `eng_reversa_result` rows per post (thumbnail on S3 under `eng_reversa/`, `plays`, `likes`, `comments`, `post_date`, caption/hook `headline`, transcription [OBS in library page]). Profiles are tagged with niches/professions and marked "approved" by staff.
2. **Per-profile research extraction (platform job, precomputed):** an LLM reads each viral post's headline/transcript and extracts **values per research variable** (e.g. a fear, a known person, an objection), keeping `result_id` + `plays` + the source sentence. This is what `profile-viral-search/{id}` returns, already grouped by variable [OBS shape]. Evidence of a job with `step`/`progress` and "já existentes" de-duplication: the hidden `extract-profile` + `extract-profile-status` flow [OBS].
3. **User picks → Minha Pesquisa:** `profile-viral-search/save` inserts the chosen `{variable_id, content, eng_reversa_result_id, plays}` for the user (de-duplicated: `already_added` on re-open [OBS]). Status on insert: [LIVE].
4. **Viral topics:** `extract-profile {type:'topic_virais'}` extracts short *subjects* from a profile's viral posts into the user's **pending** viral topics with summed `total_plays`; user approves/rejects [OBS UI]. `viral-data/{topicId}` returns the posts behind a topic [OBS].

### 6.2 Manual / AI add ("Inserir itens na pesquisa")
- Prompt inactive: plain insert into the content store as approved-manual [OBS endpoint; INF table].
- Prompt active: server runs an LLM with the configured `prompt_system` (optionally including the variable catalogue — `include_variables`) to **classify each line into a variable**; saves classified lines; returns `classified` by label and `unclassified` with a `token` (probably an LLM-generated tag/reason) [OBS response; INF semantics]. Sync endpoint with 90 s client timeout, async queue job fallback with polling [OBS].

### 6.3 Brain (Segundo Cérebro)
- Create: inserts a brain row (`core_type`, `name`) for user/workspace; presumably attaches the question set for that type and redirects to the editor [INF].
- Answer: text answer saved; audio answer assembled from chunks → stored file → **transcribed** (speech-to-text) → used as the answer text [INF]; then an LLM job **summarises/structures** all answers into the brain's knowledge content; status flips `Vazio → Pronto` [INF]. `typeSubmit=aplica_todos` processes every dirty question in one go [OBS param].
- Upload: a PDF/DOCX/TXT/MD/CSV (≤20 MB) is parsed and ingested into the brain (likely chunked + embedded for RAG, as the chat's document upload uses the same extension list) [INF].

### 6.4 Downstream consumers (why the data matters) [OBS in other pages]
- Headline generation: subject select via `GET /dashboard/user/variables/type/{who}` (the variables above), reference profiles via `POST /dashboard/user/headlines/get-profile` (`variable_selected[]` → profiles from the user's Pesquisa), `specific_core_id` "Núcleo Especifico:".
- Roteiro: `core_id` (`#selectCoreForRoadmap`, "— Nenhum —" + brains), favorites roteiro `core[]` ("Adicionar Cérebro como fonte de informação:" / "Adicionar Crenças:").
- Chat (Livewire `ragChat`): `searchMyResearch(q, group, page, sort, variable)` (group default "Meu Público"), `getResearchVariables(group)`, `searchMyCerebro(q, page)`; mention sources `research` and `cerebro` (cerebro only for the roteiro agent).

---

## 7 · Must be checked live in the browser (cannot be determined statically)

**Minha Pesquisa**
1. Is there any visible control to reach `#subject-viral` ("Assuntos Virais")? Open `/dashboard/user/searches?tab=subject-viral` and confirm the pane renders; check whether the outer page has hidden nav links (the `data-tab` links in `searches.js`).
2. Click `Adicionar itens a pesquisa` with filter = `Todas as variáveis`: is the prompt active (`#add-item-process-status` "Prompt ativo — itens serão processados pela IA" visible)? Capture `GET /dashboard/user/searches/add-item-prompt` JSON.
3. With prompt ACTIVE: add 3 lines (one ambiguous) → capture `add-items-sync` request/response; note `classified` labels, `unclassified[].token` meaning, and in which status the items appear (Aprovados vs Pendentes, "manual" tag or not).
4. With prompt INACTIVE (or a specific variable selected): add a line with filter = `Todas as variáveis` → does `contents/add` return a 422/validation message? What toast?
5. Is the `Prompt` tab visible for an admin role? (markup `#add-tab-prompt` missing for the account owner).
6. `Pendentes` filter → click ✕ `Rejeitar` → confirm `Reprovar`: does the item disappear permanently, or is it kept as rejected (and can it be re-extracted)? Inspect `reject-pending-item` response.
7. Select a type-`null` variable (`Verbos Poderosos`, `Adjetivos Poderosos`, `Momento do dia`, `GPT`) in the filter: confirm list is always empty and whether these lists are platform-global.
8. Confirm `#global-variables-loading` ("Carregando variáveis...") and `#pending-variables-alert` stay hidden on load, and that the `Atualizar` footer never shows.
9. Capture one real `variables/items?type=avatar` response to confirm item fields (`created_at`? `variable_id`? `status`?) and whether `plays` is int or string.
10. Infinite scroll: scroll past 20 rows → confirm the next 20 append (no network call); with `Agrupar` on, confirm all rows render.
11. Bulk `Zerar toda a pesquisa` — confirm whether it also deletes viral topics (endpoint name says only variable contents).
12. Click a pending viral topic badge → `#viralModal`: confirm card click opens Instagram post vs library; capture `viral-data/{id}` sample.

**Extrair Pesquisa**
13. Capture `approved-profiles` response size (how many profiles) and the non-Instagram `social` values (icon is generic).
14. Click `Pesquisa` on a profile → capture `profile-viral-search/{id}`: confirm `variable_id` values map to §5.1, whether `especialista` variables ever appear, and what `headline` contains (caption vs transcript excerpt).
15. Select items → `Adicionar à minha pesquisa` → then open Minha Pesquisa: do the items arrive as **Pendentes** or **Aprovados**? Do they show the views + "Ver na biblioteca" icon?
16. Re-open the same profile's `Pesquisa`: confirm `✓ Já adicionado` persists (server `already_added`), including after deleting the item from Minha Pesquisa.
17. Check that the default Nichos/Profissões pre-selection matches Minha conta, and whether clearing filters persists across reloads (it should not).

**Segundo Cérebro**
18. Open `Acessar Cérebro` for each brain (`/dashboard/user/cores/edit/{id}`) and **save the HTML**: question list (verbatim) for templates `História de Criação`, `Histórias de Vida do Especialista`, `Método do Especialista`, and for a `custom` and a `beliefs` (`Crença`) brain; locate the edit/delete/upload triggers (`.j_core_edit`, `.j_core_delete`, `#modal-upload-core`) and the `#modal-reload`, `#modal-core-delete` texts.
19. `Criar Cérebro` → choose `Crença` vs `Personalizado`: capture the `cores/custom/add` response (`redirect` target?) and the questions each type gets; check 422 messages (empty name, duplicate name, length limit).
20. Answer one question by text → `Aplicar alteração`: watch the status line (`Aguarde, processando resposta!` → ?), whether the page polls/uses Pusher, how long until the card badge becomes `Pronto`, and whether there is an intermediate badge (e.g. "Processando").
21. Record a voice answer → apply: capture the `upload-audio-chunk` responses and confirm the transcription appears back in the textarea.
22. Upload a PDF via the upload modal: does it fill questions, create a separate knowledge doc, or mark the brain `Pronto` directly?
23. Why do brain ids differ between `/dashboard/user/cores` (8, 9, 14, 3081, 3741, 4191, 4192) and the favorites roteiro select (8522, 8772–8775, 9385, 9386)? Compare with the chat `@cerebro` list ids.
24. Can built-in brains (ids 8, 9, 14) be renamed/deleted? Is there a per-plan limit on the number of custom brains (toast on create)?
25. Brain list ordering rule (creation order? templates first?) and whether a `beliefs` brain shows on this list or only in the "Adicionar Crenças:" selects.

---

## 8 · Rebuild notes (quirks worth not copying)
- Single source of truth: the unified list fetches everything and filters client-side; for large research sets prefer server pagination with `sort`, `status`, `variable_id` params.
- Two stores (`content` vs `pending`) leak into the API (`source` param on delete). Prefer one `research_items` table with `status ∈ {pending, approved, rejected}` and `origin ∈ {manual, ai_classified, profile_extraction}`.
- Bulk ops are N sequential requests (approve/delete) — provide real bulk endpoints.
- Mode B add ignores the "no variable selected" case — require a variable (or route to AI classification).
- Type-`null` variables are offered in the filter but never loaded.
- Pending viral-topic approve/reject uses GET without confirmation; `remove` deletes all same-text pills.
- Legacy code paths (per-variable tabs, `searches/save`, "Criar Pesquisa", orphan modals) should not be rebuilt.

---

## 9 · Verified live (2026-10-05, read-only session) — supersedes §1–§7 where they differ

**Minha Pesquisa**
- §7.2 ✅ Prompt is ACTIVE for the account owner. `GET add-item-prompt` → `{success, prompt_system, is_active:true, include_variables:true}`. The full **real system prompt** is captured verbatim in the main tab (AI layer › "Pesquisa classifier prompt"). It classifies lines into **13 `{{SLUG}}` variables** (CARACTERISTICAS-DEMOGRAFICAS-DO-AVATAR, DORES-TANGIVEIS-DO-AVATAR, DESEJOS-TANGIVEIS-DO-AVATAR, MEDOS-DO-AVATAR, FRUSTRACOES-DO-AVATAR, OBJECOES-DO-AVATAR, CRENCAS-LIMITANTES-DO-AVATAR, INIMIGO-COMUM, MECANISMO-UNICO, PROMESSA-PRINCIPAL, PROVA-SOCIAL, NICHO-OU-MERCADO, PESSOAS-E-PERSONAGENS-CONHECIDOS-PELO-MEU-PUBLICO) with a tie-break order DORES > MEDOS > FRUSTRACOES > OBJECOES > CRENCAS-LIMITANTES > DESEJOS, literal-copy, pairs-only output. **Mismatch:** these 13 slugs ≠ the 33 UI variables (no Inimigos/Eventos/Locais…; has Mecanismo/Promessa/Prova social with no UI variable). The server-side slug→variable_id map is unseen.
- §7.9 ✅ Real item (`variables/items?type=avatar`): `{id, user_id, workspace_id, variable_id, eng_reversa_result_id, content, status (0=pending,1=approved), plays ("630319" — **string**), created_at, updated_at, deleted_at (soft delete), source:"pending"}`. Response per variable: `{approved_manual:[], approved:[], pending:[]}`. Account owner: 17 avatar variables keyed, 12 especialista keyed (all empty). Approved/pending counts e.g. Desejos 33/70, Dores 24/36, Itens 12/26, Instituições 11/18.
- §5.1 correction: **server slugs DO exist** (seen in `profile-viral-search` as `variable_name`): 1=CRENCAS-DO-ESPECIALISTA, 3=HABITOS-RECOMENDADOS-PELO-ESPECIALISTA, 10=OBJECOES-DO-AVATAR, 15=ITENS-CONHECIDOS-PELO-AVATAR, 17=DORES-TANGIVEIS-DO-AVATAR, 18=DESEJOS-TANGIVEIS-DO-AVATAR, 19=EVENTOS-CONHECIDOS-PELO-AVATAR, 34=PRODUTOS-CONHECIDOS-PELO-AVATAR (others same pattern, not all seen). The proposed lowercase slugs in §5.1 are unnecessary.
- Row icons confirmed: Aprovados row = 👁 + 🗑; Pendentes row = 👁 + ✓✓ + ✕, orange accent bar. 👁 opens `/dashboard/user/library?viral_result_id=…` in a new tab (screenshot in main tab).
- `Agrupar` confirmed: group header = label + `Meu Público` badge + `N item(s)`; owner's approved groups: Crenças 12 · Medos 2 · Objeções 1 · Pessoas 8 · Instituições 11 · Itens 12 · Demográficas 5 · Dores 24 · Desejos 33.
- Bulk `Ações` modal confirmed: `Aprovar selecionados` (green) · `Excluir selecionados` (red) · divider · `Zerar toda a pesquisa` / `Remove todos os itens, incluindo os não carregados`.
- Not exercised (would change the account): §7.3, 4, 6, 10, 11, 12 — need the owner's OK.

**Extrair Pesquisa**
- §7.13 ✅ `approved-profiles` returns **485 profiles**, unpaged; first item `social:"instagram"`.
- §7.14 ✅ `profile-viral-search/{id}` → `{success, profile, data:[{variable_id, variable_name (SLUG), label, items:[{result_id, plays (int), thumbnail, post_link, headline, value, already_added}]}]}`. **Especialista variables DO appear** (1, 3). `headline` = the video's hook/opening sentences (e.g. "Tonifique seu abdômen usando uma parede. Dois exercícios super fáceis." → value "Tonifique seu abdômen"). Sample profile: 9 variáveis · 76 itens.
- §7.17 ✅ Default filters = owner's profile (Nichos Finanças, Vendas, Imobiliário; Profissões Vendedor(a), Empreendedor(a), Investidor(a)). Quirk: the selected options are appended twice to the native select's option list.
- `Vídeos` button = `<a target=_blank href=/dashboard/user/library?profile=…>`.

**Segundo Cérebro** (major corrections to §3.5)
- §7.18 ✅ **Two editors**, chosen server-side:
  1. **Questionnaire** `/dashboard/user/cores/questions/{id}` (`/cores/edit/{id}` redirects here for an unanswered *Sistema* brain). Header `Cérebro` / `Personalize seu cérebro` / `Voltar`; card `«name» - [Sistema]` / `Responda as perguntas abaixo para personalizar seu cérebro`; `Progresso das respostas` bar + `0 de N`. Questions are numbered cards, textarea `questions[<question_id>]` placeholder `Escreva sua resposta aqui`, live `N caracteres`, status chip `Aguardando resposta`. **Progressive reveal in groups of 3** (`data-group` 0,1,2…): next group appears (fade-in + toast) when every answer in the current group is non-empty; if >3 answers already filled on load, all groups show. Footer: `Zerar Tudo` (modal → `POST /cores/questions/reset`) · `Salvar Rascunho` (`POST /cores/questions/save-draft`, toast `Salvando rascunho...` → `Rascunho salvo com sucesso!`) · `Finalizar Respostas` (`POST /cores/questions/store`).
     - Guard: `HAS_ASSISTANT` false → `Sistema de validação não configurado completamente. Entre em contato com o suporte.`
     - **AI validation of each answer**: store → `{status:'validating'}` → toast `Respostas enviadas para validação. Aguarde...`; all chips → `Validando...`; result arrives via **Echo private channel `questions-validation.{APP_ENV}.user.{USER_ID}` event `.validation-completed`** AND polling `GET /cores/brain-status/{id}` every **3 s** → `{brain_status: synced|syncing|error, validation_status: pending|completed|failed, responses:[{question_id, status: completed|failed, rejection_reason}]}`. Per question chip `Aprovada` (green) / `Rejeitada` (red) + `Motivo da rejeição: «reason»`; failed → toast `Algumas respostas foram rejeitadas. Corrija-as e tente novamente.` All approved → `Todas as respostas foram aprovadas! Gerando cérebro...` → `Respostas aprovadas! Sincronizando seu cérebro...` (brain_status `syncing`) → `Cérebro sincronizado! Redirecionando...` → `/cores?brain_synced=1`; error → `Ocorreu um erro ao gerar o cérebro. Tente novamente.`
  2. **Content editor** `/dashboard/user/cores/edit/{id}` (ready brains + custom brains): back arrow · title · `Alimente este cérebro com o seu conhecimento — quanto mais rico, melhores os resultados da IA.` · source buttons · card `Conteúdo do cérebro` + `N caracteres` + one big **markdown textarea** (the synthesized brain) + save button (`Aplicar Alterações`).
     - Sistema brain (e.g. Núcleo de Influência, badge `Sistema`): buttons `Responder perguntas` · `Enviar arquivo` · `Transcrever do YouTube`. No rename/delete.
     - Custom brain (e.g. Narrativa): ✎ rename next to title, 🗑 delete (top-right), buttons `Enviar arquivo` · `Transcrever do YouTube` (no questionnaire).
     - `Enviar arquivo` modal `Importar arquivo para o cérebro`: dropzone `Clique para escolher ou arraste o arquivo aqui`, `PDF DOCX TXT MD CSV · máx. 20 MB`, `O conteúdo será adicionado abaixo do texto já existente no cérebro.` → `POST /cores/upload-file`.
     - `Transcrever do YouTube` modal `Transcrever vídeos do YouTube`: `Cole um ou mais links do YouTube. A IA baixa o áudio, transcreve e anexa o texto abaixo do conteúdo atual deste cérebro.` multiple link inputs + `+ adicionar outro link` + `Transcrever e anexar` → `POST /cores/youtube/extract` → job; poll `GET /cores/youtube/status/{jobId}` until `status:'done'`.
     - Rename modal `Renomear Cérebro` (`Nome do Cérebro:`, `Atualizar Cérebro`); delete modal `Tem certeza? Você realmente deseja deletar este Cérebro?` (`Cancelar`/`Deletar`).
     - `brains.js` voice-per-question code (§3.5) is still loaded but **no mic UI is visible** on either editor → treat as legacy unless the owner says otherwise.
- **Sistema questionnaires verbatim:**
  - História de Criação (9): 1 Como era sua vida antes de trabalhar com o que você trabalha hoje? · 2 O que te motivou a iniciar nessa área? · 3 Qual ou quais foram os maiores desafios que você enfrentou nesse caminho? · 4 Teve um momento em que você pensou em desistir? O que te fez continuar? · 5 Qual foi o ponto de virada que fez tudo mudar? · 6 Quem você se tornou hoje? · 7 O que você aprendeu com tudo isso e quer passar para outras pessoas? Qual é sua missão nessa área? · 8 O que te motiva a continuar todos os dias? · 9 Qual legado você quer deixar por meio do seu trabalho?
  - Histórias de Vida do Especialista (4): Agora precisamos das histórias que te forjaram na sua jornada. · Agora, conte histórias de grandes descobertas ou ensinamentos que você teve ao longo da sua jornada. · Conte histórias de pessoas que você ajudou. · Agora para finalizar, conte histórias de grandes conquistas que você teve na vida.
  - Método do Especialista (7): Qual é o passo a passo que você ensina para a pessoa sair do ponto A até o resultado? · Quais são os 3 a 5 pilares que toda pessoa precisa entender ou aplicar pra ter resultado com o que você ensina? · Se alguém seguisse só o essencial do que você faz, o que não poderia faltar? · Existe uma ordem certa ou fases que a pessoa precisa seguir? Quais são elas? · Você tem nomes para cada etapa ou princípio do seu método? Quer criar? · Se você pudesse resumir seu método em uma frase ou nome forte, como ele se chamaria? · Tem alguma parte do processo que as pessoas costumam pular e depois se arrependem? Qual é?
  - Núcleo de Influência: Sistema brain, already answered (validated questions 1583…); questions not re-read.
- §7.19 partial: `Criar Cérebro` modal shows **only `Nome do Cérebro:`** (placeholder `Ex: Reels Instagram`); the `core_type` select (`custom`=Personalizado / `beliefs`=Crença) is hidden, so new brains are always Personalizado.
- **Hidden page `/dashboard/user/cores/extract`** (tab title `Minhas Pesquisas`, H2 `Minhas extrações` / `Extrações realizadas`, not in menu): DataTable ID · DATA · NOME · STATUS via `POST /cores/extract/list`, search box `Pesquisar...`; owner sees `Mostrando 0 a 0 de 0 registros (filtrado de 192 registros no total)`. `Nova Extração` modal: `Nome:` (`ex: Pesquisa 1`) · `Extrair para:` TomSelect multi `nucleos[]` of all brains + link `Clique aqui para criar um novo núcleo` (inline `Nome do Núcleo` + `Criar núcleo agora`) · `Url:` `document_url[]` (`ex: https://www.url.com/hsyTh5dh`) + `Suporte a links para transcrição:` · hidden `Transcrição:` textarea `document_text` (`Cole aqui sua transcrição...`) · `Criar Transcrição`. Other modals: `Pesquisa Gerada` / `Transcrição`, `Editar Pesquisa` / `Aplicar Pesquisa`, `Selecione o Tipo de Variável`. Looks like the older way to feed brains from a URL; legacy.
