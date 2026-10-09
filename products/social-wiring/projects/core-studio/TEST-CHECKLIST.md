# Live test checklist — Criação de Mídia (CoreStudio rebuild)

Walk it together, one line at a time, on prod (`social-wiring`). Tick `[x]` when it behaves as
described; on a failure, write what happened under the line and keep going. New modules
append their own section as they ship.

## Minha Pesquisa v1 — shipped 2026-10-09 (migration 217)

### Access and navigation
- [ ] Sidebar shows **Criação de mídia › Pesquisa › Minha Pesquisa** for the owner (page is `desenvolvimento`, so a non-dev user does NOT see it).
- [ ] The old **Criação de mídia** link still opens the existing page, unchanged.
- [ ] Opening `/media-creation/pesquisa` directly lands on the page; the sidebar highlights Minha Pesquisa.

### Brand switcher
- [ ] The switcher lists the org's marcas (One Consultoria, João Raphael, Mônica Tangerino, Gilson Tangerino, Nós no Limiar, NoctusAI).
- [ ] Switching brand changes the list and the counts; nothing from brand A appears under brand B.
- [ ] Reloading the page keeps the last brand chosen.

### Variables
- [ ] The variable select shows 40 variables in 4 groups: Meu Público, Sobre Mim, Produto, Globais.
- [ ] Labels read naturally in pt-BR (no trailing spaces, no slugs shown).

### Manual add (approved straight away)
- [ ] "Adicionar itens" → pick a variable → type 3 lines → Salvar: 3 items appear under **Aprovados**, meta shows "manual".
- [ ] Ctrl+Enter saves; the live counter shows "3 itens".
- [ ] Adding the same text again (any letter case) is reported as skipped, not duplicated.
- [ ] Empty textarea → the modal asks for at least one item.

### AI classification (pending for approval)
- [ ] "Classificar com IA" with a mixed list, e.g. `Mulheres acima de 40 anos` · `insônia` · `já tentei várias dietas` · `perder 8kg em 3 meses` · `A princesa Sofia` · `Método X em 3 passos` · `500 alunas com resultado`.
- [ ] Processing state shows, then the result view: saved count, items grouped by variable, unclassified list.
- [ ] **Judge the sorting** — is each line in the variable you would pick? Note every disagreement (this validates the DRAFT classifier prompt).
- [ ] Saved items land under **Pendentes** with meta "IA".
- [ ] "Inserir mais" resets the modal; "Fechar" closes it and the list is refreshed.

### Approve / reject / delete
- [ ] Pendentes → Aprovar one item: it moves to Aprovados, counts update.
- [ ] Pendentes → Rejeitar one item: it disappears and does not come back after reload.
- [ ] Re-adding a rejected text via the AI keeps it hidden; re-adding it **manually** brings it back as approved.
- [ ] Aprovados → Excluir (confirm): the item is gone after reload.

### Filters, sort, grouping, paging
- [ ] Filter by one variable shows only that variable's items; "Todas as variáveis" shows all.
- [ ] "Mais views" vs "Mais recentes" changes the order (views only matter once Extrair brings plays; for now everything is recent).
- [ ] "Agrupar" groups items by variable with per-group counts; "Carregar mais" hides while grouped.
- [ ] With 50+ items, "Carregar mais" loads the next page.
- [ ] Empty filter result shows "Nenhum item encontrado."

### Bulk actions
- [ ] Select several → bar shows "N selecionado(s)"; "Selecionar todos" toggles the visible rows.
- [ ] Ações → Aprovar selecionados (only offered on Pendentes) approves them all.
- [ ] Ações → Excluir selecionados (confirm) deletes them.
- [ ] Ações → **Zerar toda a pesquisa da marca** requires typing the brand name; afterwards that brand is empty and OTHER brands are untouched.

### Errors and states
- [ ] First load shows a skeleton, never an empty "Nenhum item" flash before data arrives.
- [ ] Changing filters keeps the old list visible while refreshing (no blank flicker).
- [ ] If the AI fails, the modal shows "Falha ao classificar com IA" and nothing is saved.

### Owner decisions to take while testing
- [ ] Classifier prompt: OK as is, or list the corrections (from the AI section above).
- [ ] Variable list: any label to rename, any variable to hide (e.g. the 4 Globais, "GPT").
- [ ] Ready to switch the page from `desenvolvimento` to everyone?
