# CoreStudio: Biblioteca, Minha Biblioteca, Roteiros, Treinamentos, Minha conta (static analysis)

Sources: `pages/library.html`, `pages/my-library.html`, `pages/roadmaps.html`, `pages/trainings.html`, `pages/profile.html`. These are server-rendered Blade snapshots with inline scripts. I read them statically and sent no requests.

This complements `js-analysis.md`, which covers `roadmaps.js`, `advanced-roadmap-*.js`, `headlines.js` and `dashboard.js`. Anything that report already documents is only referenced here. This report also fills several gaps listed in its §7, mainly the option lists rendered by Blade.

Supporting extracts are in `../ex/`. The most useful one is `ex/profiles.txt`, the full list of 514 profile handles.

---

## 0. Shell shared by every page (context for the rebuild)

- **Title / brand.** Footer: "Copyright © 2026 Inteligência Core. Todos os direitos reservados." / "Feito com ♥ por VC". The theme is forced to dark (V2 layout).
- **Sidebar menu (verbatim, in order).**
  - Dashboard (`/dashboard/user`)
  - Criar Headlines e Roteiros (`/dashboard/user/chat`)
  - **Pesquisa** › Minha Pesquisa (`/searches`) · Extrair Pesquisa (`/searches/extract-profile`)
  - Segundo Cérebro (`/cores`)
  - Biblioteca (`/library`)
  - **Configurações** › Minha conta (`/profile`) · Minha Biblioteca (`/my-library`) · Treinamentos (`/trainings`)
  - (legacy, hidden group) **Headlines** › Gerar Headlines (`/headlines/generate`) · Headlines Favoritas (`/headlines/favorites`) · Headlines sugeridas (`/headlines/suggested`)
  - Roteiros (`/roadmaps`)
  - "Minha Biblioteca" and "Treinamentos" sit under **Configurações**.
- **Profile dropdown.** Avatar initials, first name, and the current workspace ("My Workspace"). It lists "Espaços de trabalho" as a `POST /dashboard/user/workspace/switch` form with `workspace_id` (one submit button per workspace), then "Ver tutorial novamente" (opens `#modal-first-access-tutorial`) and "Fazer logout" (`POST /logout`).
- **Workspaces.** "Adicionar Workspace" opens a modal with `form#customers-workspace-create` (hidden `customer_id`, `name`, default value "My Workspace 2"). It posts to `/dashboard/admin/customers/workspace/create`; on the team page it uses `/dashboard/admin/team/workspace/create`. The response is the standard envelope.
  - This is an **agency / multi-workspace model**: user (customer) → workspaces. Headlines and roteiros are scoped by `workspace_id`.
- **Notifications** (Alpine `notificationsDropdown`).
  - `GET /dashboard/user/notifications[?show_read=1]` → `{notifications[{id,type,icon,title,body,link,status(0 unread/1 read),created_at}], unread_count, read_count}`.
  - `POST /dashboard/user/notifications/{id}/read` and `POST /dashboard/user/notifications/read-all`.
  - Polls every 30 s. UI strings: "Notificações", "Marcar todas como lidas", "Ver já lidas"/"Ocultar lidas", "Nenhuma notificação por aqui".
  - `timeAgo` outputs: "agora", "N min atrás", "Nh atrás", "Nd atrás", or a pt-BR date.
- **Credits.** The Alpine `creditsBadge()` component is defined but **not mounted** on these pages.
  - It calls `GET /dashboard/user/twin/api/credits` → `{balance, cost_per_minute}` and polls every 30 s; the `is-empty` class is set when `balance < cost_per_minute`.
  - Credits are therefore **per minute** and belong to a "twin" (digital-twin video/voice) feature, not to text generation.
  - No plan, subscription or API-key UI appears anywhere in these 5 pages.
- **First-access modal** `#modal-first-access-tutorial` (verbatim): "Bem-vindo ao Core Studio! / Antes de começar, assista aos treinamentos." · "Para ter **bons resultados** com a plataforma, é essencial que você assista aos vídeos de treinamento antes de começar a usar." · "Eles cobrem desde a configuração inicial até como gerar roteiros e conteúdos de forma eficiente. **Usuários que assistem têm resultados significativamente melhores** — não pule essa etapa." Buttons: "Assistir aos treinamentos agora" (→ `/trainings`) and "Pular por agora".
- **"Box de headlines"** offcanvas ("Headlines na Box", "Remover selecionados", "Salvar Headlines") is in the shell on every page. It is documented in js-analysis §1.4.
- **Third-party scripts:** Crisp chat widget, Pusher/Echo, TomSelect, toastr, DataTables (roteiros), Quill (roteiro editor), moment and daterangepicker.
- **Dead boilerplate:** `#modal-report` ("New report", tabler.io) appears on every page and is Tabler demo leftover. Ignore it.

---

## 1. Biblioteca de virais (`GET /dashboard/user/library`)

### 1.1 Page layout (verbatim)
- **H2** "Biblioteca de virais". Subtitle: "Biblioteca de virais disponíveis".
- **Header buttons:**
  - Sort toggle link labelled **"Mais vistos"** with `href=…&sort_by=recent&page=1`. The current list is ordered by plays desc, so the default sort is "most viewed" and the link switches to `sort_by=recent`. Only those two sort modes are visible.
  - **"Filtros"** (`openFilterSidebar()`) opens the right-hand sidebar `#filterSidebar` ("Filtros de Virais", "Filtros Ativos: N").
- **Auto-filter alert (dismissible):** "**Filtros aplicados automaticamente** — Estamos mostrando virais dos **seus nichos e profissões**. Para ver todos os virais da biblioteca, clique em **"Ver todos os virais"**."
  - On first load the server pre-applies the user's profile niches and professions (`?niche=3&niche=23&niche=26&profession=13&profession=23&profession=31`). `view_all=1` disables that.
- **Quick-filter card:** multi-select TomSelects "Nichos" (`#quickFilterNiche`, `quick_niche`) and "Profissões" (`#quickFilterProfession`), plus two buttons:
  - **"Meus nichos e profissões"**: `GET /dashboard/user/profile/get-niches-professions` → `{success, data:{niches[], professions[]}}`, then reloads with those IDs. If both are empty, the toast is "Você ainda não possui nichos ou profissões cadastrados no seu perfil."
  - **"Ver todos os virais"**: `clearQuickFilters()` → `?view_all=1` plus the other filters kept.
  - The quick selects and the sidebar selects are kept in sync both ways (`window.syncingFilters` guard).
- **Grid section:** card title "Virais Encontrados", `.row.row-cards`, **24 cards per page** in a 4-column layout (`col-12 col-md-6 col-lg-3`).
- **Pagination:** classic Laravel server pagination with `page=N`. There is no infinite scroll. The snapshot shows "1 2 … 10 … 280 281", so **281 pages × 24 ≈ 6,700 virais** match just the user's 3 niches and 3 professions. The full library is larger.
- **Selection bar** `#video-selection-bar` appears when any card's checkbox is ticked: "N vídeo(s) selecionado(s)" · "Limpar seleção" · **"Adicionar à Minha Biblioteca"**.

### 1.2 Card structure (one `.viral-card`)
```html
<div class="viral-card" data-video-id="105038" onclick="openViralModal('105038','1544')">
  <div class="viral-thumbnail-container">
     [.core-badge "CORE"  — admins only]
     <div class="video-select-checkbox" onclick="event.stopPropagation(); toggleVideoSelection(105038,this)">
     <div class="profile-badge"><span class="profile-name">lar.cabral</span></div>
     <img class="viral-thumbnail" src="https://corestudio-ai.s3.us-east-1.amazonaws.com/storage/app/public/eng_reversa/tmp_image_…jpg">
     <div class="viral-overlay"><div class="viral-stats">
        stat-item(eye)  "46.1M"   ← plays/views
        stat-item(heart) "1.4M"   ← likes
        stat-item(3rd icon) "4K"  ← comments
     </div></div>
  </div>
  <div class="card-body">
     <span class="badge">1:15m</span>          ← video duration (m:ss + "m")
     <div class="text-muted small">25/10/2024</div>   ← post date
     [.card-transcription-snippet > .snippet-content data-transcription data-search]  ← only when transcription_search is active
     <a class="btn-show-post" href="https://www.instagram.com/p/DBkKs_mOYE8/" target=_blank>Ver post</a>
  </div>
</div>
```
- The second `openViralModal` argument (`'1544'`) is the same for every card from one profile (lar.cabral → 1544, Coralsantoro → 1472, carlosbezerrajr → 1738). In practice it is the **`eng_reversa_search_id` (the scraped-profile id)**, even though the JS parameter is named `engReversaResultsId`. The modal ignores it and reloads data by video id.
- Numbers use the K/M formatter: `formatNumber` with 1 decimal and a trailing ".0" stripped.
- Thumbnails are stored in S3 under `eng_reversa/` ("engenharia reversa" is the scraping/analysis pipeline). Every one of the 24 cards links to Instagram (`/p/{shortcode}/`).
- Cards **do not show** niche, format or headline. Those appear only in the modal.
- **Snapshot sample, top of the sort:** 46.1M / 33.3M / 31.1M / 27.4M / 27M … 15.8M plays. Profiles seen: lar.cabral ×5, Coralsantoro ×2, carlosbezerrajr ×2, sambentley ×2, islam.sousa ×2, escobaradvogados ×2, comecou, marinaguaragna, askvinh, Paulsaladinomd, Papaifinanceiro, eusoufelipeamorim, diegonmenin, gesieudo, joaommenna. Video IDs range from about 9.7k to 159k, so the library holds well over 150k results in total.

### 1.3 Filters (sidebar `form#filterForm`, verbatim)
Submit builds a **clean query string with repeated keys and no `[]`**, then does a full page reload with GET. Buttons: "Aplicar Filtros" and "Limpar Filtros" (→ `?view_all=1`).

| Label | name | Type / options |
|---|---|---|
| Buscar por palavras-chave | `transcription_search` | text, placeholder "Digite palavras-chave..."; **comma-separated terms**, accent-insensitive |
| ☑ Buscar apenas nas headlines | `search_in` | hidden `transcription` + checkbox `headline` (**checked by default**), so the default searches the extracted **headline** of each viral, and unticking searches the transcription |
| Período | `date_from`, `date_to` | date inputs ("Data inicial"/"Data final"), filter on post date |
| Visualizações Mínimas | `views_min` | number, "Ex: 100000" |
| Curtidas Mínimas | `likes_min` | number, "Ex: 10000" |
| Comentários Mínimos | `comments_min` | number, "Ex: 1000" |
| Rede Social | `social` | Todas · `instagram` Instagram · `tiktok` TikTok · `youtube` YouTube |
| Perfil | `profile` | single select (TomSelect "Selecione um perfil..."), "Todos os perfis" + **514 handles** (value = handle). Full list in `ex/profiles.txt` |
| Nicho | `niche` (multi) | 28 niches, see 1.4 |
| Profissão | `profession` (multi) | 102 professions, see 1.4 |
| Formato de Vídeo | `format_video` | 15 formats, see 1.4 |
| ID do Viral | `viral_result_id` | number "Ex: 1234" |
| (admins only) | `core` | the "Core" classification flag; preserved in URLs but no field is rendered for normal users |

Other URL params: `sort_by` (`recent`, otherwise default views), `page`, `view_all=1`, and `viral_id=<id>`. The last is a deep link: it auto-opens the modal after load, then removes itself from the URL.

### 1.4 Taxonomies (id → label, verbatim)
**Nichos (28):** 1 Saúde e Bem-Estar · 2 Relacionamentos · 3 Finanças · 4 Educação · 5 Empreendedorismo/Business · 6 Espiritualidade · 7 Beleza & Estética · 8 Moda & Estilo · 9 Desenvolvimento Pessoal · 13 Emagrecimento e Dieta · 14 Saúde Mental · 17 Tech & IA · 18 Cripto · 19 Marketing Digital · 20 Direito · 21 Comunicação & Liderança · 22 Criação de Filhos · 23 Vendas · 24 Trends do Momento · 25 Casa & Decoração · 26 Imobiliário · 27 Culinária · 28 Emagrecimento · 29 Imigração · 30 Turismo & Viagem · 31 Pets & Animais · 32 Tributação Fiscal · 33 Construção Civil.

**Formatos de vídeo (15)**, the "format_video" taxonomy and core IP of the method: 1 Lista de Valor Prático · 2 Lista de Pontos de Identificação · 3 Lista de Crenças · 4 Mistério · 5 Comparação · 6 Tutorial · 7 Análise do Mundo e Novas Tendências · 8 Histórias Pessoais · 9 Histórias de Terceiros · 10 Fatos Curiosos · 11 Metáforas e Analogias · 12 Assunto do Momento · 13 Defesa de Crença Forte · 14 Palavras de Motivação · 15 Websérie.

**Profissões (102)**, as `id label`. Alphabetical in the filter; the profile page uses id order.
25 Acupunturista · 70 Advogado Administrativo · 72 Advogado Ambiental · 64 Advogado Civil · 74 Advogado Constitucional · 75 Advogado de Consumidor · 67 Advogado de Família · 76 Advogado Digital · 68 Advogado Empresarial · 71 Advogado Imobiliário · 73 Advogado Internacional · 65 Advogado Penal · 77 Advogado Previdenciário · 66 Advogado Trabalhista · 69 Advogado Tributário · 85 Agente de Turismo · 20 Arquiteto(a) · 102 Auditor Fiscal · 3 Autor(a) · 95 Breathwork · 18 Cabeleireiro(a) · 56 Chef de Cozinha · 105 Cirurgião Plástico · 27 Coach · 57 Confeiteiro · 54 Consultor de Imagem · 49 Contador(a) · 62 Copywriter · 82 Corretor de Imóveis · 90 Corretor de seguro de vida · 21 Dentista · 79 Designer de Interiores · 100 Designer de joias · 52 Designer de Sobrancelhas · 60 Designer Gráfico · 28 Economista · 23 Empreendedor(a) · 92 Enfermagem · 80 Engenheiro · 15 Esteticista · 32 Estrategista de Marca · 2 Farmacêutico(a) · 14 Fisioterapeuta · 47 Fisioterapeuta Pélvico · 106 Fonoaudiólogo · 55 Fotógrafo · 61 Gestor de Tráfego/Media Buyer · 22 Gestor(a) · 83 Higienista Ocupacional · 30 Influenciador(a) · 31 Investidor(a) · 99 Joalheira · 84 Jornalista · 78 Juiz · 51 Líder Religioso · 53 Maquiador(a) · 26 Marketeiro(a) · 98 Medicina Regenerativa · 37 Médico Cardiologista · 12 Médico Cirurgião · 33 Médico Dermatologista · 38 Médico Endocrinologista · 101 Médico geral · 89 Médico Geriatra · 36 Médico Ginecologista · 43 Médico Integrativo · 39 Médico Neurologista · 87 Médico Nutrólogo · 104 Médico Obstetra · 40 Médico Oftalmologista · 34 Médico Ortopedista · 91 Medico Otorrinolaringologia · 35 Médico Pediatra · 8 Médico Psiquiatra · 93 Medico Radiologia · 103 Médico ultrassonografista · 41 Médico Urologista · 42 Médico Veterinário · 50 Mentor(a) · 24 Moda · 97 Musculação · 4 Neurocientista · 16 Nutricionista · 81 Paisagista · 5 Pastor(a) · 48 Personal Trainer · 94 Professor de Yoga · 29 Professor(a) · 63 Programador(a) · 46 Psicanalista · 44 Psicólogo Infantil · 7 Psicólogo(a) · 45 Psicoterapeuta · 86 Quiropraxista · 59 Social Media · 58 Sommelier · 6 Teólogo(a) · 9 Terapeuta · 10 Terapeuta Holístico · 96 Terapeuta Somatico · 13 Vendedor(a) · 19 Visagista.

**Counts:** 514 profiles, 28 niches, 102 professions, 15 formats, 3 social networks (+ "Todas"), 24 cards per page, 281 pages for the user's default niche/profession filter.

**Views/likes buckets.** The main library uses free numeric inputs. The **advanced-roadmap picker** (`#advancedRoadmapModal` library step) uses fixed buckets:
- Views mínimas: Qualquer · 100k+ (100000) · 500k+ · 1M+ · 5M+
- Likes mínimas: Qualquer · 10k+ (10000) · 50k+ · 100k+ · 500k+
- Its filters are 🔍 Buscar por texto, 📋 Formato, 👤 Perfil (the same 514), 👁️ Views mínimas, ❤️ Likes mínimas and 🎯 Nicho. It has no profession filter. The endpoint is in js-analysis §1.8.

### 1.5 Viral detail modal `#modal-viral-info` ("Informações do Viral", modal-xl)
Load: `GET /dashboard/user/library/result/{viralId}` → `{type:'success', data:{…}}`. Fields consumed:
```
id, profile (handle, may have '@'), social, eng_reversa_search_id,
thumbnail, post_link_public, plays, likes, comments, post_date,
transcription_text,
relations[{ niche:{name}, profession:{name} }],
engReversaFormatVideoRelation[{ format_video:{name} }],
pode_usar_core (bool, admins), is_core (bool)
```
Layout (`.data_flow`):
- **Header row:** avatar with 2-letter initials, `@handle`, social; button **"Gerar headline"** (`#generate-headline`).
  - The JS also wires **"Citar no Chat"** (`#btn-cite-in-chat` → `/dashboard/user/chat?cite_viral={id}`) and **"Citar perfil no Chat"** (`#btn-cite-profile-in-chat` → `/chat?cite_profile={eng_reversa_search_id}`, meaning all videos of that profile). Their markup is not in this snapshot (feature-flagged), but the JS hooks are live, so the RAG chat accepts a viral or a profile as cited context.
- **Left column, video:** the thumbnail plus a play button `playInstagramVideo()`. It extracts the shortcode from `/(p|reel|tv)/{code}`, then sets an iframe to `https://www.instagram.com/p/{code}/embed/`. The fallback text is "Não consegue ver o vídeo?" → "Seu navegador pode não ter suporte a este vídeo." / "Clique aqui para ver no Instagram". The **video is not hosted**; the Instagram embed is the player.
- **Right column:**
  - Card "Métricas": Visualizações, Curtidas, Comentários, Data do Post (`dd/mm/yyyy hh:mm`).
  - Card **"Transcrição"**: buttons "Ver post" (`.link_public`) and a copy icon "Copiar link do vídeo". The copy icon copies the **internal deep link** `https://corestudio.ai/dashboard/user/library?viral_id={id}`, not the Instagram URL.
  - A read-only textarea holds `transcription_text` (placeholder "Transcrição será carregada automaticamente..." / "Transcrição carregada" / "Transcrição não disponível").
  - Button "Copiar Transcrição" (`.j_copy_transcription`).
  - With an active `transcription_search`, it prepends a snippet box "Texto encontrado:" showing ±100 chars with `<mark class="highlight-match">`.
- **Footer badges:** "Nicho:" (blue), "Profissão:" (green), "Formato do Vídeo:" (purple), or "N/A". A viral can have **many** niches, professions and formats (M:N).
- **Admin "Core" classification (`#core-classification-row`, rendered only for staff):** badge "Core"/"Não classificado" and toggle "marcar como Core"/"remover Core". It calls `POST /dashboard/user/library/result/{id}/core` → `{type, message, is_core}` and adds a "CORE" ribbon to the card. This is a curated "gold standard" flag, filterable with `core=`.
- **Toasts:** "Transcrição copiada para o clipboard!", "Não há transcrição disponível para copiar.", "Link do viral copiado para o clipboard!".

### 1.6 "Gerar headline" from a viral (4-step wizard inside the same modal, `.create_headline`)
1. **Etapa 1: Selecione o workspace.** "Escolha o workspace para gerar o headline". Calls `GET /dashboard/user/library/workspaces` → `{success, data[{id,name}]}`. If there is only one workspace it is auto-selected and the wizard advances after 500 ms. Button: "Próximo: Escolher Variáveis".
2. **Etapa 2: Escolha os assuntos virais.**
   - Calls `POST /dashboard/user/library/viral-topics {workspace_id}` → `{success, data[{id, topic}]}`.
   - Multi-select "Selecione um assunto viral da sua pesquisa:", hint "Esses são assuntos virais aprovados em sua pesquisa", with a counter "N selecionado(s)".
   - Optional textarea "Escreva o assunto viral manualmente (opcional)", hint "Você pode selecionar assuntos virais acima ou escrever manualmente aqui".
   - Buttons: "← Voltar para Workspace" / "Próximo: Revisar e Enviar".
3. **Etapa 3: Revisar e Enviar.** The summary card "Resumo da Criação de Headline" shows Workspace, Assuntos Virais (N assunto(s)) and Conteúdo Manual ("Nenhum assunto viral selecionado" / "Nenhum conteúdo manual adicionado"). Button: **"Criar Headline"**.
4. **Submit:**
   ```
   POST /dashboard/user/headlines/suggested/store
   headlines[0][user_id]=1667
   headlines[0][workspace_id]=…
   headlines[0][variable_contents][i]{variable_name:'ASSUNTOS_VIRAIS', content:<topic text>, viral_topic_id, user_variable_id:null, additional_content:null}
   headlines[0][additional_content]=<manual text|null>
   viral_id=<viral id>
   ```
   → `{success, message}`.
5. **Etapa 4: confirmation.** "Headline enviada para criação!" · "Em 1 ou 2 minutos sua headline será criada. Você pode visualizá-la em **Headlines Sugeridas**." Buttons: "Ver Headlines Sugeridas" (→ `/headlines/suggested`) and "Continuar na Biblioteca".

The concept, in other words: **viral (structure/format reference) × the user's approved "assuntos virais" (topics from their Pesquisa) → an async headline job** that lands in "Headlines sugeridas". Closing the modal resets the wizard and stops the embed.

### 1.7 "Adicionar à Minha Biblioteca" (bulk)
Tick checkboxes on cards, then use the selection bar's "Adicionar à Minha Biblioteca":
```
POST /dashboard/user/library-references/self-assign
_token, mode=video, video_ids[]=…
```
→ `{message}`. Toast: "Solicitação enviada!" (default). Error: "Erro ao salvar.".
- Admins (`IS_ADMIN_USER`) get `openAdminReferenceModal()` instead, which assigns videos to *other* users. That modal is not rendered for this user.
- There is **no per-card "usar como referência"** button in the library. Using a viral as a roteiro reference happens in the advanced roteiro modal ("Vídeo da biblioteca (opcional)", §3.4) or by citing it in chat.

---

## 2. Minha Biblioteca (`GET /dashboard/user/my-library`)

The header is "Minha Biblioteca", with the subtitle "Gerencie seus perfis e vídeos de referência para usar no Chat."

**Purpose:** a per-user (and per-workspace: `WORKSPACE_ID=1619` is embedded in the page) **allow-list of reference profiles and videos that the RAG chat agent may draw on**. It is not a "favorites" list.

### 2.1 "Adicionar referência": 3 tabs (`.atrib-mode-tab-btn`)
1. **Perfil completo** (default).
   - TomSelect "Perfis da biblioteca" (placeholder "Buscar perfis…", remote). It calls `GET /dashboard/user/library/profiles?profile=<q>` → `{profiles[{id, profile, video_count, social}]}`. Each option shows `@handle` and "N vídeos · instagram" with an initials avatar.
   - Profiles already assigned (`ASSIGNED_PROFILE_IDS`, 6 here) are filtered out.
   - Switch **"Atualização automática — Novos vídeos desses perfis entram automaticamente"** (on by default).
   - "Salvar" sends:
     ```
     POST /dashboard/user/library-references/self-assign  (JSON)
     {mode:'profile', eng_reversa_search_ids:[int…], auto_refresh:bool}
     ```
     → `{success, message}`, then a reload.
   - Errors: "Selecione ao menos um perfil." and "Perfil já adicionado.".
2. **Vídeos específicos.** Info only: "Atribuição de vídeos específicos — Para adicionar vídeos específicos, acesse a Biblioteca de Virais, selecione os vídeos desejados e escolha você como destinatário. As atribuições feitas lá aparecem na tabela abaixo." Link: "Ir para a Biblioteca de Virais".
3. **Solicitar Perfil** (ask the team to scrape a new profile).
   - `form#solicitar-virais-form` with hidden `social=instagram` and the field "Perfil do Instagram (deve começar com @)" (`profile`, maxlength 31, placeholder `@username`).
   - Client normalization: strips spaces, extracts the username from an `instagram.com/<user>` URL, rejects reserved segments (reels/p/tv/stories/explore/accounts/direct/ar/location/tagged), and prefixes `@`. Regex: `^@[a-zA-Z0-9._]{1,30}$`.
   - Validation messages: "Informe o username do perfil." · "Isso é um link de vídeo, não de perfil. Informe o @username do criador." · "O username não pode ter espaços." · "O username deve começar com @." · "Use apenas letras, números, _ e . (máx. 30 caracteres após @)."
   - Live check (500 ms debounce) with `GET /dashboard/user/my-library/check-profile?profile=@x&social=instagram` → `{status: available|in_library|already_requested, request_status?, notes?}`. Messages:
     - "✓ Username válido"
     - "⚠️ Este perfil já está disponível na biblioteca de virais."
     - "✗ Sua solicitação foi reprovada. Motivo: …"
     - "⚠️ Este perfil já foi aprovado para você."
     - "✗ Este perfil já está em análise pela nossa equipe. Aguarde o retorno."
     - "Não foi possível verificar este perfil."
   - Submit: `POST /dashboard/user/my-library/request-virals` JSON `{profile, social:'instagram'}` → `{success, message}`. Default message: "Solicitação enviada! Aguarde a aprovação.".
   - "Minhas solicitações" list: `GET /dashboard/user/my-library/requests` → `{requests[{profile, status: pending|approved|rejected, notes, created_at_human}]}`. Table columns: Perfil · Status (Pendente/Aprovado/Reprovado, plus "Motivo: …" when rejected) · Data. Empty state: "Nenhuma solicitação ainda.".
   - The `socialLabel` map includes TikTok, so the model supports it, but the UI is Instagram-only.

### 2.2 "Minhas referências" table
- Client-side search: "Buscar por ID ou headline..." (accent-insensitive, every term must match). Empty row: "Nenhuma referência encontrada para essa busca".
- Columns: **Tipo** (pills "Perfil" and "Auto"; video rows presumably "Vídeo") · **Perfil / Detalhe** (initials, `@handle`, social; links to `/library?profile=<handle>`) · **Posts até** ("Todos", i.e. a cutoff date when auto-refresh is off) · **Atualizado** (`dd/mm/yyyy hh:mm`) · a delete action.
- 6 rows in the snapshot, all with Tipo = Perfil and Auto: psifernandosegredo, elias.maman, dra.lilianalimongi, advogandoparaimoveis, veridiana_cavalheri and lelinhagentil (reference ids 3602 to 3607).
- **Delete:** a custom confirm "Remover referência — Esta ação removerá a referência da sua biblioteca. Não é possível desfazer." with "Cancelar" / "Sim, remover". It sends `POST /dashboard/user/library-references/{id}` with `_method=DELETE` and reloads. Toast: "Referência removida.".

---

## 3. Roteiros (`GET /dashboard/user/roadmaps`)

### 3.1 List page
- **H2** "Meus roteiros". Subtitle: "Edite suas headlines favoritas ou crie roteiros a partir delas."
- **Header:**
  - **"Criar roteiro"** (`openAdvancedRoadmapWithCustomHeadline()` → `AdvancedRoadmapModal.openWithCustomHeadline('')`).
  - Search input "Pesquisar..." (`#customSearchInput`, reloads on keyup).
  - **"Excluir Selecionados"** (hidden until something is checked; its label shows the count).
- **DataTable `#myRoadmaps`:** server-side.
  - Request: `POST /dashboard/user/roadmaps/list` with DataTables params (`draw/start/length/order`) and `search.value`.
  - Rows: `{Checkbox, ID, Data, Name, Source (HTML), Status}`.
  - Columns: ☐ (select all) · **ID** · **Data** · **Nome** · **H. Origem** (title "Headline de Origem") · **Status** · actions.
  - Settings: no length change, `simple_numbers` paging, pt-BR language strings (for example "Mostrando _START_ a _END_ de _TOTAL_ registros", "Nenhum resultado encontrado", "Processando...").
- **Status enum → badge:**

| wire | label | color |
|---|---|---|
| `created` | Criando | green |
| `in_gpt` | Processando | yellow |
| `in_gpt2` | Processando | yellow |
| `completed` | Completo | azure |
| `error` | Falha | red |

  The two-pass pipeline is `in_gpt` → `in_gpt2`, which matches the modal text "Este processo passa por 2 etapas de análise e pode levar até 2 minutos".
- **Row actions:** 👁 view (`.j_roadmaps_view`, enabled only when completed or error; opens the edit modal, see js-analysis §3.3) and 🗑 delete (`.j_roadmaps_delete` → `#modal-roadmaps-delete`: "Você realmente deseja deletar este Roteiro?" Cancelar/Deletar → `GET /dashboard/user/roadmaps/delete/{id}`).
  - There is **no copy or duplicate action** in the list. Copying is inside the modal ("Copiar Roteiro").
- **Bulk delete:** `POST /dashboard/user/roadmaps/delete-multiple {ids[]}` → `{success, message, refresh}`. Confirm text: "Você realmente deseja deletar N roteiro(s) selecionado(s)?". Warnings: "Selecione pelo menos um roteiro para excluir." and "Nenhum roteiro selecionado.".
- There are **no status or date filters**; free-text search only.

### 3.2 Edit modal `#modal-customer-roadmap-edit-roadmap` ("Editar Roteiro"), Blade side
- **Tabs:** **Roteiro** · **Fontes da Pesquisa** (shown when `search_text` exists) · ⋯ dropdown "Reprocessar" (`.j_reprocess_roadmap`).
  - Hidden debug tabs: `#roadmap_payload` (JSON `<code>`), `#headlines-tabs-params` (JSON params) and `#headlines-tabs-headline-old-1`.
- **Roteiro tab:** "Nome:" (`name`) and "Roteiro:" with the button "Copiar Roteiro", a Quill editor (`#quill-editor`) and hidden `roadmap_gpt`.
- **Fontes tab:** card "Notícias e Fontes Utilizadas" with markdown `#search-sources-content`.
- **Feedback block:**
  - "O que achou deste roteiro?" with "Não Gostei" (`data-feedback=2`) and "Gostei" (`data-feedback=1`).
  - On dislike: "Não gostou do roteiro?" textarea "(Opcional) Diga-no o motivo..." and "Enviar".
  - Endpoints are in js-analysis §1.6.
- **Footer:** "Cancelar" and **"Atualizar"** (submit → `/roadmaps/update`).
- **Legacy reprocess modal** `#modal-roadmap-reprocess` ("Reprocessar Roteiro"): textarea "Informação Adicional:" (`information_additional`) and button "Gerar Roteiro".
- **Legacy progress modal** `#modal-show-roadmaps` ("Roteiro"), `form#favorites_make_roadmap` (hidden `referer=favorites`, `structure_id`, `headline`, `headline_id`). Three progress cards, verbatim:
  - **"1. Pesquisando"**: "Estamos pesquisando seus informações para criar o roteiro."
  - **"2. Extraindo Núcleo"**: "Agora estamos extraindo o seu núcleo de influência..."
  - **"3. Método"**: "Estamos aplicando o roteiro de acordo com o método..."

  These expose the generation pipeline concept: research → extract the user's "núcleo de influência" (from Segundo Cérebro) → apply the method.

### 3.3 Rendered roteiro structure
The table loads by AJAX and the editor content comes from `/roadmaps/view/{id}`, so **no roteiro body is present** in this snapshot. There are no "gancho / desenvolvimento / CTA" headings in any of the 5 pages.

What the snapshot does show about the output structure is the **profile fields injected as tags**:
- "Apresentação magnética": "Esse campo será incluso nas gerações de Roteiros. Dentro da Tag Apresentação Magnética".
- "CTAs": "…Dentro da Tag CTAs".

So the prompt template has at least `<Apresentação Magnética>` and `<CTAs>` slots, plus the headline (the hook) and the format/structure from the viral. To get the actual section structure, capture one `GET /dashboard/user/roadmaps/view/{id}` response.

### 3.4 "Roteiro Avançado" modal (`#advancedRoadmapModal`): the Blade option lists missing from js-analysis §7
- Header: "Roteiro Avançado" / "Crie um roteiro avançado em 3 passos".
- Progress text: "Criando roteiro avançado com IA..." / "Este processo passa por 2 etapas de análise e pode levar até 2 minutos" / `#advancedProgressStatus` "Iniciando processamento...".
- **Hidden inputs:**
  - `headline_id`
  - **`ai_provider=claude`** (the default LLM provider is Claude)
  - `chat_resource_id`, `advancedRoadmapIdForUpdate`
  - `advancedRoadmapChatResourceType=user_roadmaps`, `save_to=user_roadmaps`
  - `roadmap_source_type`, `roadmap_use_pubmed=0`, `is_reprocess=0`
- **Step 1, Headline:** textarea "Base do roteiro. Se veio de sugerida ou favorita, já está preenchida." Placeholder: "Ex: 3 alimentos que aumentam testosterona".
- **Step 2, Instruções** (`observations`): "Tom, público-alvo, o que pode ou não falar. Quanto mais detalhes, melhor." Placeholder: "Ex: Não falar de suplementos; tom leve; público 25–40 anos; evitar jargões médicos…".
- **Step 3, Fonte das informações:** "Escolha a origem das informações para o roteiro." It offers 3 cards (`data-source`):
  - `none`: "**Deixe a IA pensar**: Sem fontes externas. Só headline e instruções."
  - `links`: "**Link específico**: URLs de artigos ou páginas como base." Panel "URLs para usar como base — Adicione um ou mais links. Depois clique em Criar Roteiro." Repeatable `input[type=url]` and "+ Adicionar novo link".
  - `serper`: "**Pesquisar na web**: Busca na internet e usa os resultados." Panel text: "Por padrão as buscas são feitas em **inglês** para melhores resultados, mesmo que você digite em português." Contents:
    - input "Pesquisar na web…" with the button "Pesquisar"
    - ☐ "[PubMed] Incluir artigos científicos" (`use_pubmed`)
    - ☐ "Quero buscar em português" (`serper_search_in_portuguese`)
    - "Selecionados N" and "Resultados" lists, with "Traduzir resultados"
    - empty state "Digite algo acima e clique em Pesquisar para buscar na web."
    - Serper.dev is the search provider.
- **Duração do vídeo** (`duration_minutes`): "Defina um tempo-alvo." Options: `auto` "Auto (recomendado)", `1` "~1 min", `2` "~2 min", `3` "~3 min".
- **Segundo Cérebro (opcional)** (`core_id`): "Adicione um cérebro personalizado ao contexto." This user's cores: — Nenhum — · 8 História de Criação · 9 Histórias de Vida do Especialista · 14 Método do Especialista · 3081 Núcleo de Influência · 3741 Call de diagnóstico · 4191 Formulário · 4192 Narrativa.
  - The low ids 8, 9 and 14 look like **system or template cores** shared across users; the high ids are user-created.
- **Vídeo da biblioteca (opcional)** (`viral_video_id`): "Use um vídeo viral como referência de formato e estrutura. Ao escolher, o vídeo selecionado aparecerá aqui com opção de remover."
  - Button: "Abrir biblioteca e escolher vídeo". This opens the picker: "Escolha um Vídeo Viral de Referência — Selecione um vídeo para usar como base estrutural do seu roteiro" with "Voltar", "Mostrar Filtros", "Limpar Filtros" and the filters listed in §1.4.
  - **This is the "usar como referência" flow.**
- **Legacy questions step:** "Gerando perguntas estratégicas..." / "Aguarde enquanto criamos perguntas personalizadas para seu roteiro." / "Headline Base" / "Responda as perguntas abaixo para personalizar seu roteiro".
- **Legacy links step:** "🔍 Buscando informações na internet" / "Entendendo a busca necessária para seu roteiro..." / "📋 Selecione os links relevantes" / "N selecionados" / "Voltar" / "Continuar com links selecionados".
- **Result:** "Roteiro criado com sucesso!", tabs "Roteiro" and "Fontes da Pesquisa", "Roteiro Gerado", "Copiar Roteiro", "Atualizar Roteiro", "Notícias e Fontes Utilizadas", "Copiar Fontes".
- **Footer:** "Fechar" and **"Criar Roteiro"** (`AdvancedRoadmapModal.submitRoadmapSteps()`).
- Routes (`window.AdvancedRoadmapModalConfig`) are in js-analysis §1.7. They include `check-status/__ID__`, `chat/__ID__`, `list-search`, `direct-search`, `translate-search-query` and `translate-search-results`.

---

## 4. Treinamentos (`GET /dashboard/user/trainings`)

- **H2** "Treinamentos". Subtitle: "Primeiros passos: da Bio aos primeiros roteiros".
- **Structure:** one module (no module list) of **5 lessons**. A main player sits on the left and a sidebar on the right ("Aulas") with numbered buttons. `setActiveLesson(n)` swaps the panel and lazy-loads the iframe from `data-src`, blanking the others to stop playback.
- **Video host: Bunny Stream** (`iframe.mediadelivery.net/embed/478875/<guid>?autoplay=false&loop=false&muted=false`, library 478875).
- **No durations, progress tracking or completion state** are rendered.

| # | Title (verbatim) | Description (verbatim) | Bunny GUID |
|---|---|---|---|
| 1 | Como preencher a Bio | Como preencher sua Bio do jeito certo para a IA entender seu contexto. | 05ef32e5-4155-4b77-a596-3c02317a3036 |
| 2 | Como aprovar itens da Pesquisa (automático e manual) | Aprenda a aprovar itens gerados na Pesquisa, tanto no modo automático quanto no manual. | 903037f1-d6a2-4da3-a686-0443e9f76475 |
| 3 | Como gerar roteiros Headlines Favoritas | Gere roteiros a partir das suas Headlines Favoritas com poucos cliques. | 37a7a3fc-4916-4310-adf9-64b6b3b7f012 |
| 4 | Como gerar roteiros Headlines Biblioteca de Virais | Use a Biblioteca de Virais para gerar roteiros prontos para produção. | 2401cac1-832f-4327-bf85-f069a1eb201e |
| 5 | Como gerar roteiros com Headlines Próprias | Crie seus próprios ganchos/headlines e gere roteiros a partir deles. | ec681f61-0372-4cbe-a0c5-99442ca853c0 |

The lesson order spells out the intended user journey: Bio → approve Pesquisa items → roteiros from favoritas, from the Biblioteca, or from your own headlines.

---

## 5. Minha conta / Configurações (`GET /dashboard/user/profile`)

- **H2** "Minha conta". Subtitle: "Informações e configurações da sua conta". Tabs: **Meu Perfil** (`/profile`) · **Integrações** (`/profile/integrations`, not captured; this is where Instagram or other integrations would live).
- **Form `#save_profile`** → `POST /dashboard/user/profile/save` (multipart FormData) → envelope `{type, message, refresh}`. A 422 shows the `errors` bag as toasts. Section title "Dados Pessoais"; the role label shows "Cliente".

| Label | name | Notes |
|---|---|---|
| Nome | `name` | disabled |
| Sobrenome | `lastname` | disabled |
| Email | `email` | disabled |
| Senha | `password` | blank = unchanged |
| Telefone | `phoneNumber` | mask "(99) 99999-9999" |
| Instagram | `instagramAccount` | free text |
| Tiktok | `tiktokAccount` | free text |
| Nichos | `niches[]` | multi, **max 3** (tooltip "Preencha com os nichos que você deseja gerar Headlines"; hint "Selecione até 3 nichos"; error "Máximo de 3 nichos permitidos"). Same 28 list |
| Profissões | `professions[]` | multi, **max 3** (tooltip "Preencha com as profissões que você deseja gerar Headlines"; "Selecione até 3 profissões"; "Máximo de 3 profissões permitidos"). Same 102 list, id order |
| Versão do Layout | `layoutVersion` | `1` v1 · `2` v2 (selected) |
| **Bio** | `bio` | help popover template (verbatim): "Eu sou (Nome), Sou (Profissão). Falo sobre (dores e desejos do publico). Eu ajudo pessoas a (resolver as dores) Por meio do (método utilizado no nicho).Para a pessoa consiga (solução e vida com os benefícios)." |
| **Apresentação magnética** | `presentation_magnetic` | "Esse campo será incluso nas gerações de Roteiros. Dentro da Tag Apresentação Magnética" |
| **CTAs** | `ctas` | "Esse campo será incluso nas gerações de Roteiros. Dentro da Tag CTAs" |

- **Incomplete-profile guard:** if `(niches ∧ professions ∧ ¬bio) ∨ (bio ∧ (¬niches ∨ ¬professions))`, the `#profileIncompleteModal` appears: "Atenção — O sistema precisa da bio preenchida juntamente com os nichos e profissões para poder sugerir itens da pesquisa para você. Tem certeza que deseja continuar assim?" with "Cancelar" / "Continuar". Submit button: "Atualizar" → "Aguarde atualizando...".
- The profile's niches and professions also feed the library's **auto-filter** (`/profile/get-niches-professions`) and the Pesquisa suggestions.
- **Not present:** plan or subscription, credit balance, API keys, team or members, and workspace CRUD beyond the sidebar "Adicionar Workspace" and switch.
- PII note: the snapshot contains the account owner's real name, email and Bio text. They are deliberately not reproduced here.

---

## 6. Inferred data model (rebuild reference)

```
User(id, name, lastname, email, phone, instagram_account, tiktok_account,
     bio, presentation_magnetic, ctas, layout_version, role)
UserNiche(user_id, niche_id)            ≤3
UserProfession(user_id, profession_id)  ≤3
Workspace(id, customer_id→User, name)   -- current workspace in session
Niche(id, name)              28 rows
Profession(id, name)         102 rows
FormatVideo(id, name)        15 rows

EngReversaSearch  (= scraped creator profile)
  (id, profile handle, social[instagram|tiktok|youtube], video_count, …)   ~514
EngReversaResult  (= one viral video)
  (id, eng_reversa_search_id, social, profile, post_link_public, thumbnail(S3),
   plays, likes, comments, duration_seconds, post_date,
   transcription_text, headline (extracted; searchable via search_in=headline),
   is_core bool)
EngReversaResultRelation(result_id, niche_id?, profession_id?)            M:N
EngReversaFormatVideoRelation(result_id, format_video_id)                 M:N

LibraryReference  (Minha Biblioteca = chat-agent allow-list)
  (id, user_id, workspace_id, mode[profile|video], eng_reversa_search_id?,
   eng_reversa_result_id?, auto_refresh bool, posts_until date|null, updated_at)
ViralProfileRequest (id, user_id, profile '@x', social, status[pending|approved|rejected],
   notes, created_at)

ViralTopic  ("assuntos virais aprovados em sua pesquisa")  (id, workspace_id, topic)
SuggestedHeadline (async job) ← {workspace_id, variable_contents[{variable_name:'ASSUNTOS_VIRAIS',
   content, viral_topic_id, user_variable_id, additional_content}], additional_content, viral_id}

Core ("Segundo Cérebro") (id, user_id|null for system, name)  e.g. Núcleo de Influência, Método do Especialista
UserRoadmap (id, user_id, workspace_id, name, headline_id?, headline, source(html "H. Origem"),
   status[created|in_gpt|in_gpt2|completed|error], roadmap_gpt(html), payload json, params json
   {observations, core_id, viral_video_id, roadmap_source_type[none|links|serper],
    source_links[], selected_links[], duration_minutes[auto|1|2|3], use_pubmed, ai_provider},
   search_text (sources dossier), roadmap_liked(0|1|2), reason_unliked, created_at)
Notification (id, user_id, type, icon, title, body, link, status 0/1, created_at)
TwinCredits (balance, cost_per_minute)
Training lesson (static): (n, title, description, bunny_guid)
```

### 6.1 Endpoint index (only the ones new relative to js-analysis.md)
| Method | Path | Purpose |
|---|---|---|
| GET | `/dashboard/user/library` | page; query `transcription_search, search_in, date_from, date_to, views_min, likes_min, comments_min, social, profile, niche*, profession*, format_video, viral_result_id, core, sort_by(recent), page, view_all, viral_id` |
| GET | `/dashboard/user/library/result/{id}` | viral detail (fields in §1.5) |
| POST | `/dashboard/user/library/result/{id}/core` | toggle Core (staff) |
| GET | `/dashboard/user/library/workspaces` | `{success,data[{id,name}]}` |
| POST | `/dashboard/user/library/viral-topics` | `{workspace_id}` → `{success,data[{id,topic}]}` |
| POST | `/dashboard/user/headlines/suggested/store` | headline job from viral (§1.6) |
| GET | `/dashboard/user/library/profiles?profile=` | profile autocomplete `{profiles[{id,profile,video_count,social}]}` |
| POST | `/dashboard/user/library-references/self-assign` | `mode=video, video_ids[]` (form) or JSON `{mode:'profile', eng_reversa_search_ids[], auto_refresh}` |
| DELETE (POST+_method) | `/dashboard/user/library-references/{id}` | remove reference |
| GET | `/dashboard/user/my-library/check-profile?profile=&social=` | `{status, request_status?, notes?}` |
| POST | `/dashboard/user/my-library/request-virals` | JSON `{profile, social}` |
| GET | `/dashboard/user/my-library/requests` | `{requests[…]}` |
| GET | `/dashboard/user/profile/get-niches-professions` | `{success,data{niches[],professions[]}}` |
| POST | `/dashboard/user/profile/save` | profile form |
| POST | `/dashboard/user/roadmaps/list` | DataTables server-side |
| POST | `/dashboard/user/roadmaps/delete-multiple` | `{ids[]}` |
| GET | `/dashboard/user/chat?cite_viral={id}` · `?cite_profile={search_id}` | open chat with a viral or profile as context |
| POST | `/dashboard/user/workspace/switch` | `workspace_id` |
| POST | `/dashboard/admin/customers/workspace/create` | `customer_id, name` |
| GET/POST | `/dashboard/user/notifications[?show_read=1]`, `/{id}/read`, `/read-all` | notifications |
| GET | `/dashboard/user/twin/api/credits` | `{balance,cost_per_minute}` |

### 6.2 Rebuild notes (what matters)
1. **The library is a scraped corpus of competitor reels** (Instagram-first), with transcription, an extracted headline, and an M:N classification into niche, profession and **15 narrative formats**. Its value comes from the classification and transcripts, not the player: playback is just an Instagram embed.
2. **Default personalization.** A user's ≤3 niches and ≤3 professions from the profile pre-filter the library, and the Pesquisa topics come from the Bio plus niches.
3. **Three ways to use a viral:**
   - (a) **headline generation**: viral format × approved viral topics → async job → Headlines sugeridas
   - (b) **roteiro reference**: `viral_video_id` in the advanced modal, as "base estrutural"
   - (c) **chat citation / Minha Biblioteca**: an allow-list of profiles or videos as RAG context, with auto-refresh of new posts
4. **Roteiro inputs:** headline, instructions, source mode (none / links / Serper web + PubMed, EN by default), duration (auto, 1, 2 or 3 min), optional Core, and an optional viral reference. The profile's Bio, Apresentação magnética and CTAs go in as tagged blocks. The status machine is `created → in_gpt → in_gpt2 → completed|error`.
5. **Async UX everywhere** ("Em 1 ou 2 minutos…", "até 2 minutos"): background jobs plus polling or notifications.
