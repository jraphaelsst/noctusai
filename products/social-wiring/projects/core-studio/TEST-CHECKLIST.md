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

## Pesquisa wave 2 — Extrair Pesquisa + Assuntos Virais (on dev; ships with the next release — migrations 221 + 223)

### Extrair Pesquisa (`Criação de mídia › Pesquisa › Extrair Pesquisa`)
- [ ] Sidebar shows **Extrair Pesquisa** under Pesquisa (owner only while `desenvolvimento`).
- [ ] Source tabs list the brand's connected Instagram account(s), YouTube account(s) and "Posts criados", each with a post count; a brand with nothing connected shows "Nenhuma conta conectada para esta marca".
- [ ] Post grid is newest first, shows thumbnail, date, text excerpt, Views/Likes/Comentários ("—" when unknown, never 0), Reels/Short badge, "Ver post ↗".
- [ ] A post with almost no text is disabled ("Sem texto para analisar").
- [ ] Select a few posts (max 30), tick **Itens de pesquisa** and/or **Assuntos virais**, press **Extrair (N)** → progress panel with step + % and live counters; "Cancelar" works.
- [ ] Reloading the page mid-extraction resumes the progress panel.
- [ ] Result: "Extração concluída!" with saved / already-existing / topics counts; links to the pending items and to Assuntos virais work.
- [ ] **Judge the extraction** — the new pending items are exact phrases from the posts and sit under sensible variables (DRAFT extractor prompt: note every miss).
- [ ] Re-selecting the same posts shows "Já extraído" and skips them unless "Reextrair posts já extraídos" is ticked.
- [ ] A second extraction while one is running is refused ("Já existe uma extração em andamento"); the 11th run in a day is refused (daily limit).

### Assuntos Virais (tab on Minha Pesquisa)
- [ ] Minha Pesquisa shows tabs **Itens de pesquisa | Assuntos virais** (URL `?tab=assuntos-virais` opens the second).
- [ ] Extracted items in Itens de pesquisa show "· extração" and a "Ver post ↗" link.
- [ ] Pendente: approve / reject one; bulk approve; "Esvaziar" (confirm) empties only Pendente.
- [ ] Aprovado: add a topic manually (shows "Manual"); remove one (confirm); "Ver mais" loads more.
- [ ] Clicking a topic opens "Assuntos Virais — «topic»" with the source posts and their metrics; clicking a card opens the post.
- [ ] **Judge the topics** — short, useful subjects? (DRAFT prompt.)

## Segundo Cérebro (on dev; ships with the next release — migration 224)

### List + bio
- [ ] Sidebar shows **Segundo Cérebro › Cérebros / Minhas extrações** (owner only while `desenvolvimento`).
- [ ] Per brand: the 4 system brains appear (História de Criação, Histórias de Vida do Especialista, Método do Especialista, Núcleo de Influência) with `Sistema` badge, status (Vazio/Pronto/Processando) and "N de M respondidas".
- [ ] **Bio do perfil**: type + Salvar persists after reload; "Usar a bio do Instagram" (only when the brand has Instagram connected) fills the field without saving.
- [ ] **+ Criar Cérebro** creates a custom brain and opens its editor; duplicate name is refused.

### Questionnaire (system brains)
- [ ] Questions appear in groups of 3; the next group appears when the current one is answered.
- [ ] Answers autosave (reload keeps them); "Salvar Rascunho" confirms.
- [ ] **Revisar com IA** → each answer gets Aprovada / Rejeitada + motivo; with a suggestion, "Usar sugestão" replaces the text, "Manter minha resposta" keeps it. **Judge the review** (DRAFT prompt).
- [ ] **Finalizar Respostas** works even with rejected answers; on a brain that already has content it asks Substituir / Anexar; ends in the editor with "Cérebro gerado!".
- [ ] **Judge the synthesis** — first person, your coined names kept literally, nothing invented, "Elementos para conteúdo" section present (DRAFT prompt).
- [ ] "Zerar Tudo" (confirm) clears answers but not the brain content.
- [ ] Voice option is NOT shown yet (arrives with the transcription service).

### Editor
- [ ] Edit content + **Aplicar Alterações**; "N caracteres" updates; "Alterações não aplicadas" shows while dirty.
- [ ] **Enviar arquivo** with a PDF, DOCX, TXT/MD/CSV: text is appended under the existing content with an "### Arquivo:" header; wrong type / >20 MB are refused with the right message.
- [ ] Editing while an import lands shows the conflict modal (Copiar meu texto / Recarregar) instead of overwriting.
- [ ] Custom brain: rename and delete work; system brains can't be renamed/deleted.
- [ ] "Transcrever do YouTube" is NOT shown yet (phase 2).

### Minhas extrações
- [ ] **Nova Extração**: name, pick brains (or create one inline), paste a transcription → status Pronta.
- [ ] **Ver** → edit the text, Salvar, **Aplicar aos cérebros** → each target shows Aplicado and the brain content gets an "### Extração:" block; applying again doesn't duplicate.
- [ ] Search, "Carregar mais", Excluir (confirm) work.

### Owner decisions to take while testing
- [ ] Extractor / topics / review / synthesis prompts: OK or list corrections.
- [ ] Questionnaire hints for the 3 non-Núcleo brains (currently empty) — write them or fetch from CoreStudio?
- [ ] Which brand gets your existing CoreStudio brains (Núcleo answers + Call de diagnóstico / Formulário / Narrativa)?
- [ ] Switch Extrair / Segundo Cérebro pages from `desenvolvimento` to everyone?
