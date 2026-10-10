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

## Geração — Dashboard, Chat, Biblioteca, Headlines, Roteiros, Treinamentos, Meu Perfil (contract `specs/geracao-contract.md`; migration 229)

> Build everything, then validate everything at once (owner, 2026-10-10). Before walking this list:
> - migration 229 is applied;
> - the image is deployed;
> - `biblioteca_ingestao_habilitada` is ON, but only after the security review passes. If it is OFF, the Biblioteca shows the "ingestão desligada" banner and headlines use Método Audience templates. Note that and continue.
>
> Use one marca with a filled bio throughout (e.g. Gilson Tangerino), plus one marca with nothing filled.

### Access and navigation (all pages `desenvolvimento`)
- [ ] Sidebar shows, under **Criação de mídia**: Dashboard · Criar Headlines e Roteiros · Biblioteca, and group **Configurações** › Meu Perfil · Minha Biblioteca · Treinamentos · **Headlines** › Gerar Headlines · Headlines Favoritas · Headlines sugeridas · Roteiros. Pesquisa and Segundo Cérebro are unchanged.
- [ ] A non-dev user sees none of the new links; opening their URLs directly does not show the pages.
- [ ] Every page has the marca switcher. Switching marca changes the data, and nothing from marca A appears under marca B.

### Meu Perfil (`/media-creation/perfil`)
- [ ] Nichos and Profissões accept at most 3 each ("Selecione até 3 …"). A 4th is refused.
- [ ] The Bio popover shows the "Eu sou (Nome)…" template. Saving the bio here shows the same text on the Segundo Cérebro bio card, and the reverse.
- [ ] Apresentação magnética and CTAs save and persist after reload.
- [ ] Filling the bio but no nichos (or the reverse) and pressing Atualizar shows the "Atenção" modal. Continuar saves.
- [ ] The Instagram card tells you whether this marca has a Meta (Facebook Login) connection, needed to monitor profiles, and links to Conexões › Marcas.

### Treinamentos (`/media-creation/treinamentos`)
- [ ] 5 lessons in order (Como preencher a Bio … Como gerar roteiros com Headlines Próprias), each with its description.
- [ ] Each lesson shows "Vídeo em produção — em breve." (no broken player).
- [ ] As platform admin: edit a lesson, paste a YouTube/Vimeo/Bunny embed URL, save, and the video plays. A URL from another site is refused.
- [ ] As platform admin: deactivate a lesson. You still see it (marked inactive) and can reactivate it; a member no longer sees it.

### Minha Biblioteca (`/media-creation/minha-biblioteca`)
- [ ] **Solicitar Perfil**: typing `instagram.com/<user>` becomes `@<user>`; a reel link is refused ("Isso é um link de vídeo…"); spaces and invalid characters show the right message; the live check shows "✓ Username válido".
- [ ] With no Meta (Facebook Login) account in the org, the form says so and does not pretend to work.
- [ ] Enviar a real public business/creator account: it appears under **Perfis monitorados** as Aguardando, then Ativo with name, photo and number of virais (after the sync job). A non-existent handle ends as "Não encontrado".
- [ ] "Atualizar agora" works once; a second click within the hour is refused.
- [ ] **Perfil completo**: add a monitored profile to this marca with Atualização automática on. It appears in **Minhas referências** as Perfil + Auto. Removing it asks to confirm and is gone after reload.
- [ ] Removing a monitored profile that another marca still uses is refused with a clear message.
- [ ] While ingestion is OFF, both Biblioteca pages say "Monitoramento ainda não ativado" (not an empty library).
- [ ] More than 20 manual "Atualizar agora" in one day across the org are refused (daily cap).

### Creator opt-out (legitimate-interest safeguard, migration 233)
- [ ] Minha Biblioteca › Solicitar Perfil shows the transparency note (public business/creator accounts only, structure study only, opt-out via the privacy policy contact).
- [ ] As platform admin, "Pedidos de exclusão (opt-out)" is visible; as a normal member it is not.
- [ ] Add an opt-out for a monitored handle: the confirm dialog warns that ALL data is deleted now, and the toast reports how many profiles and virais were purged. The profile and its virais disappear from Minha Biblioteca and Biblioteca in every org.
- [ ] Trying to register that handle again shows "Este perfil pediu para não ser monitorado." Adding the same opt-out twice changes nothing.
- [ ] Removing the opt-out lets the handle be registered again.

### Biblioteca (`/media-creation/biblioteca`)
- [ ] The grid shows virais of the monitored profiles, 24 per page. Each card shows @handle, thumbnail, metrics ("—" when unknown, never 0), duration, date and **Ver post**.
- [ ] **Judge "viral"**: do the cards really stand out against each profile's normal posts? Toggle "Mostrar só virais" off to compare. (D4: 3× the profile's median.)
- [ ] The auto-filter banner shows when the marca has nichos/profissões. "Ver todos os virais" removes it. "Meus nichos e profissões" re-applies it.
- [ ] Sort Mais vistos ↔ Mais recentes. Keywords (comma-separated) in gancho vs transcrição. Período, mínimos, Perfil, Formato, ID filters.
- [ ] Select cards → "Adicionar à Minha Biblioteca" → they appear in Minha Biblioteca as Vídeo.
- [ ] Open a viral: the Instagram embed plays (or the "Não consegue ver o vídeo?" fallback); Métricas; Transcrição with **Copiar Transcrição**; badges Nicho / Profissão / Formato / Gatilho.
- [ ] **Judge the transcription and the classification** (DRAFT prompt): right niche, format and trigger? Hook correct?
- [ ] A long or large reel shows the honest status (e.g. "longa demais") and is still classified from its caption.
- [ ] **Gerar headline** wizard: pick approved assuntos virais and/or type one → Revisar → Criar Headline → "Headline enviada para criação!" → **Ver Headlines Sugeridas** shows 2 new Manual headlines within about 2 minutes.
- [ ] "Citar no Chat" / "Citar perfil no Chat" open the chat with the reference attached.
- [ ] In Roteiro Avançado, the library video picker searches only your Minha Biblioteca by default; "Buscar em toda a biblioteca" widens it.
- [ ] While you record a Cérebro voice answer, a library transcription never delays it by more than one reel (voice answers come first).

### Gerar Headlines (`/media-creation/headlines/gerar` → `?who=…`)
- [ ] The landing has 3 cards: Sobre mim · Sobre meu público · Assuntos do Virais.
- [ ] **Sobre meu público**: select 2 variables; each shows its approved items to pick from. Opções Avançadas: Modelagem de um Perfil (max 2; profiles without compatible structures are disabled, with the alert) / Formato / Gatilho. Criatividade slider. Gerar.
- [ ] Progress shows the **real step** ("estrutura 2 de 5"), no fake bar. It ends Completo and the result modal opens.
- [ ] **Judge the headlines** (DRAFT system prompt, D1): do they keep the viral's structure, sound like the marca (bio), avoid invented numbers? Two different angles per structure?
- [ ] "Itens da pesquisa usados" chips appear on headlines that used your approved items. Each chip's text really is in the headline.
- [ ] Tick "Criar as headlines usando apenas os itens da minha pesquisa" with a variable that has no approved items: you get the clear failure listing which variables lack items (no empty "Completo").
- [ ] **Assuntos Virais** (`who=viral`): pick a topic or type one → Tom de Comunicação → Gerar.
- [ ] A marca without bio: Gerar is refused with "Preencha a bio em Meu Perfil…".
- [ ] A second Gerar while one is running is refused.
- [ ] History: search, view (👁), Reprocessar (creates a new batch), excluir one / Excluir Selecionados.
- [ ] Structure link "#N" opens that viral. With an empty library, the warning "usando templates do Método Audience" shows.
- [ ] **Criatividade** (Essencial / Equilibrado / Explorador): generate the same request at the two extremes. Do they feel different? Our AI provider rejects the temperature setting, so the level only works through an instruction in the prompt.

### Headlines Favoritas / sugeridas
- [ ] ♥ a headline in the result modal: it appears in **Headlines Favoritas**. Desfavoritar removes it.
- [ ] Editar a headline: the new text persists. Excluir and Excluir Selecionados work.
- [ ] On a headline that already has a roteiro, Editar opens **Editar Headline e Roteiro**. Changing both saves both. Leaving the roteiro blank keeps it unchanged.
- [ ] **Headlines sugeridas**: Modo Automático/Manual, source metric, Abrir link opens the original post.
- [ ] **Gerar sugestões agora** creates today's automatic suggestions (about 10) within a few minutes. A second click the same day is refused.
- [ ] Next day: new automatic suggestions arrived on their own (daily job), with no repeats of yesterday's virais.

### Roteiro Avançado + Roteiros (`/media-creation/roteiros`)
- [ ] From a favorite → **Criar roteiro**: the modal opens with the headline filled.
- [ ] Fonte: "Deixe a IA pensar" is selectable; "Link específico" and "Pesquisar na web" show "Em breve".
- [ ] Duração ~1 min, a brain, and a library video picked through the picker (filters work), then Criar: strategic questions appear. Answer them → Gerar Roteiro → Criado with tabs Roteiro / Fontes.
- [ ] **Judge the roteiro** (DRAFT): Headline → CTA de salvar → … → your CTAs and Apresentação magnética from Meu Perfil at the end; models the reference video's rhetorical device; **no invented statistics**; length close to ~1 min.
- [ ] "Pular perguntas" goes straight to generation.
- [ ] Closing the modal mid-generation: the roteiro still finishes and shows in **Meus roteiros**.
- [ ] Meus roteiros: search, H. Origem links back to the headline, view/edit (Atualizar persists), Gostei / Não gostei + motivo, Reprocessar with extra info (creates a new one), excluir and Excluir Selecionados. The headline in Favoritas now shows "Roteiro criado".
- [ ] "Criar roteiro" in the list header opens the modal with an empty headline.

### Criar Headlines e Roteiros — chat (`/media-creation/chat`)
- [ ] Tabs HEADLINE / ROTEIRO; "+" creates a conversation; rename and Apagar work; "Ver mais conversas" pages.
- [ ] Ask HEADLINE for "10 headlines sobre <tema>": the answer **streams** word by word, cites "(estrutura #N)" links that open the viral, and each headline has ♥ (lands in Favoritas) and "Criar roteiro a partir desta headline".
- [ ] `@` → Minha Pesquisa / Segundo Cérebro / Biblioteca / Headlines tabs attach chips. "me dá mais 5 baseadas no @perfil" uses mostly that profile's structures.
- [ ] **Memória**: save "não uso emojis" → new answers respect it; delete it. Memories of marca A don't apply in marca B.
- [ ] ROTEIRO agent writes a full roteiro using your brains.
- [ ] Mic dictation fills the composer (it does not send by itself).
- [ ] Stop mid-answer: the partial answer stays, marked as partial. Reload keeps the conversation.
- [ ] A very long answer continues instead of being cut, or says it was cut.
- [ ] The context meter warns when you attach a lot.

### Dashboard (`/media-creation/dashboard`)
- [ ] "Olá, <nome>!" and the KPIs Headlines geradas · Roteiros gerados · Itens pendentes (the last opens Minha Pesquisa pendentes). The numbers match what you created above.
- [ ] Histórico lists your recent actions; Data crescente / decrescente / Tipo reorder it.
- [ ] Headlines Sugeridas widget: Criar roteiro (modal), Editar, Abrir link; "ver todas as headlines" goes to Sugeridas.

### Errors, limits and states (all new pages)
- [ ] First load shows a skeleton, never an empty-state flash. Switching marca keeps the old data until the new arrives.
- [ ] Each page shows "Tentar novamente" on a failed load.
- [ ] With the AI key missing (or the budget exceeded), generation shows a clear "IA indisponível" message, never a spinner forever.
- [ ] When the monthly AI budget is exceeded, Gerar (headlines, roteiros) is refused at once with "orçamento de IA excedido", not after a background failure.

### Owner decisions to take while testing (contract §12)
- [ ] D1 headline prompt · D2 slot filling · D7 classifier · D9 roteiro prompt: OK or list corrections.
- [ ] D3/D4: is "monitored profiles + 3× median" the right viral source and definition?
- [ ] D5/D6/D19: transcription budget for the library (60 / 30 min/day), retention (90 days), LGPD basis.
- [ ] **LGPD legal basis for the Biblioteca (blocks turning ingestion on):** (a) legitimate interest with a documented balancing test and an opt-out/deletion path for creators, or (b) contract, with each client org as controller and NoctusAI as processor. Also confirm 90-day retention for idle profiles. Security review proposal: `LGPD-WARNINGS.md` (Biblioteca de virais).
- [ ] D8: memory per marca (not global) OK?
- [ ] D10/D12: daily suggestion count (10) and the per-user caps.
- [ ] D13: who records the Treinamentos videos?
- [ ] Switch each page from `desenvolvimento` to everyone?
