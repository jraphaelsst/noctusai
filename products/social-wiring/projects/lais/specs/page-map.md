# Lais — UI layer notes (live, 2026-10-13, owner account "Lais da One Consultoria Imobiliária")

Evidence: C = seen live. PII (lead names/phones/emails) deliberately NOT copied here.

## Shell
- Sidebar (accordion, one group open at a time; collapses to icon rail on /chats): Início `/` · Conversas `/chats` · Disparos em massa `/broadcasts` · **Gestão de leads** ▸ Leads `/leads`, Visitas `/visits` · **Gestão de imóveis** ▸ Captação, Atualização de imóveis, Empreendimentos · **Relatórios** ▸ Bairros e imóveis, Avaliações no Google `/avaliacoes` · Minha Lais `/configs` · Usuários e equipes · Pacotes adicionais [NOVO] · Plano e cobranças `/financeiro` · Guia da Lais `/trainings_page` · Ajuda (Intercom). C
- Agency card on top: "Lais da One Consultoria Imobiliária" / agency name. Header: breadcrumb, Novidades `/whats-new`, bell `/notifications`, user menu (JR João Raphael). C
- Global popup: "OPORTUNIDADE — Dispare o Remarketing para 105 leads … Reative-os com o Remarketing" [Depois] [Ir para Disparos]. C (upsell surfaced on any page)
- Stack: Next.js App Router on Vercel (dpl_ ids), NextAuth `/api/auth/session`, Keycloak SSO `sso.lastro.services`, BFF `bff.lastro.services/api/v1`, LaunchDarkly (context kind `agency`, key = agency uuid, attr `isLastro`), Sentry, Intercom, Google Fonts, maplibre-gl, websocket `wss://eventhub.lastro.services`. CSP connect-src restricted to these. C
- Shell GETs on every page: agency/settings, subscription/premium, permissions, permissions/teams, smart-campaigns/onboarding-state, auth/users/me, auth/users/me/profile, agency/details, test-users, flows/{chat-control,add-team,connect-origins,reachout-leads}/onboarding-progress, finance/invoices, agency/charts/plan-consumption. C

## Início `/` (01-home.jpg)
- Title = agency name; refresh button ("Recarregar dados"); month picker ("Outubro, 2026").
- **Atividades**: Consumo do plano anual (5,4% · 118/2184 → /financeiro) · Cobranças de atendimento (count → /notifications?type=lead-user-demanding-followup-notification) · Pré-agendamento de visitas (count → /visits).
- **Destaques**: banner carousel (3 slides, /web/banners/home) — e.g. "Novo dashboard de atendimentos" (module upsell, "Não tem o módulo? Fale com Suporte" / "Abrir relatório" → /relatorio-v2), podcast link.
- **Personalizações de comportamento [NOVO]** (Conferir todas → /configs): cards Pré-agendamento de visita · Perguntas essenciais · Reengajamento.
- **Dados gerais de atendimento** (funnel KPIs): Topo de funil (chegaram pelos canais, 100%) → Atendimentos (atendidos pela Lais, %) → Encaminhados (enviados ao CRM pela Lais, %).
- Charts: Leads por canal (channels: Grupo Zap, WhatsApp, Site próprio, Imovelweb) · Status por canal (Enviado ao CRM / Não pronto / Erro no envio) · Leads por horário no mês (% fora do horário comercial) · Leads semanais (melhor dia da semana) · Leads nos últimos 6 meses (Enviado vs Não enviado ao CRM).
- Data: /web/finance/consumption, /web/agency/charts/{alerts,lead-summary,leads-by-channel,lead-status-by-channel,leads-per-hour,leads-per-weekday,leads-last-six-months}, /web/banners/home. C

## Architecture discovery — two apps
- **Next.js app** `casa.lais.ai` (new) + **Bubble.io legacy app** `legado.lais.ai` (env `NEXT_PUBLIC_BUBBLE_BASE`). Several Next routes are shells whose body is an iframe `legado.lais.ai/<same path>?mode=iframe&agency=<agency uuid>&parentOrigin=https://casa.lais.ai`. Confirmed iframes: /owners, /developments, /configs_my_business. The iframe did not render inside casa in our Chrome (likely 3rd-party cookie); opening the legado URL directly works with the owner's session. C
- Bubble page registers a beforeunload "Leave site?" guard. C
- ⚠ The Bubble page selects data by the URL `agency` param: without it the page rendered empty values. Whether the server enforces ownership is UNKNOWN — **never probe other agency ids** (CoreStudio cross-tenant lesson). U

## Leads `/leads` (02-leads.jpg)
- "Tenha a visão completa e organizada dos leads que entraram em contato com a Lais." "Exibindo N leads". Filtros button (drawer).
- Columns: Lead (name + attendance status "Atendido pela Lais" | "Sem atendimento") · Contato (phone, email) · Operação (Compra | Aluguel + property code `#ONE…` clickable) · Canal (WhatsApp | ImovelWeb | Grupo Zap | Site próprio + datetime) · CRM (badge "Enviado ao CRM" | "Não pronto" | "Erro no envio" + "Enviado pela Lais"/"Enviado automaticamente" + datetime).
- Row actions: Copiar link do histórico · Abrir conversa · Ver resumo · **Enviar ao CRM** (WRITE). Bulk: Baixar selecionados (export) · Enviar selecionados (WRITE) · Programar Remarketing (→ broadcast). Link "Como funciona o Remarketing?" → suporte.lais.ai collection. Pagination 10/page.
- Data: /web/leads/ (list), /web/leads/origins, /web/leads/campaigns. Also /leads-v3 exists (same title "Leads"). C
- Insight: "Enviado automaticamente" (portal lead with no conversation → pushed straight to CRM) vs "Enviado pela Lais" (after qualification). I

## Visitas `/visits` (03-visits-empty.jpg)
- Empty state: "Ative as solicitações de visita — Com elas, a Lais agenda visitas no pré-atendimento e cada pedido chega aqui." [Configurar visitas]. Filtros (disabled). Data: /web/visits/config. C

## Disparos em massa `/broadcasts` (04-broadcasts.jpg)
- "Envie mensagens no Whatsapp para diversos contatos de uma vez." Tipo filter; [+ Novo disparo]. Tabs: Todos · Rascunhos · Agendados · Enviados · Cancelados · Erros (counts). Sections RASCUNHOS / AGENDADOS / HISTÓRICO. Columns Nome · Status · Tipo · Contatos. Example: "Remarketing 23 de jun 2026 às 10:00", Enviado, tipo Remarketing, 12 contatos. Data: /web/broadcasts. C

## Captação (sidebar) = `/notifications?type=lead-property-acquisition&view=acquisition` (05-captacao.jpg)
- "Acompanhe as notificações de imóveis potencialmente captados." Feed grouped by day: card "CAPTAÇÃO — A Lais identificou uma potencial captação de imóvel" + datetime, expandable. 15 in ~5 days. Filtros. Page size 5/10/15/20. C
- Insight: Lais classifies conversations into event types; notification `type` values seen: `lead-property-acquisition`, `lead-user-demanding-followup-notification` ("Cobranças de atendimento"). C

## Atualização de imóveis = `/owners` → Bubble iframe "Conversas com proprietários para atualizar os imóveis anunciados." C (content not yet seen)

## Empreendimentos = `/developments` → Bubble iframe (07-developments.jpg)
- "Aumente as vendas adicionando empreendimentos — A Lais usa as informações cadastradas para aquecer seus leads." [Adicionar empreendimento] [Saiba mais]. List "Empreendimentos cadastrados" + search; item "Vintage" (Inativo). C

## Relatórios ▸ Bairros e imóveis = `/relatorio-v2` (08-relatorio-imoveis.jpg)
- "Confira dados sobre as preferências dos seus leads e otimize suas campanhas e captações." Filters: operação (Aluguel/Compra), month. Tabs Imóveis · Bairros.
- Top tipo de imóveis: Ranking · Tipo · % Leads vs % **Prateleira** (agency inventory). Top 10 imóveis: Ranking · Imóvel (code) · Tipo · Preço · Leads (rows duplicated — vendor bug). Data: /web/report. Also /relatorio-v3. C

## Relatórios ▸ Avaliações no Google `/avaliacoes` (09-avaliacoes.jpg)
- "A Lais está construindo sua reputação — Em outubro, a Lais enviou 33 pedidos de avaliação para leads com boas conversas…" KPIs pedidos enviados / novas avaliações. Distribution 1–5★, average, total. Últimas avaliações (author, date, text) + external link. Data: /web/agency/google-reviews/dashboard. C
- Mechanism: Lais auto-asks leads with good conversations for a Google review. C (copy) / trigger rule U

## Minha Lais `/configs`
- Cards: Meu negócio (Funcionamento da imobiliária, documentações exigidas e garantias) · Perfil do WhatsApp (Nome da Lais, foto de perfil e descrição) · Modelos de mensagem (WhatsApp templates) · Integrações Meta (Receba leads de campanhas Meta). "Comportamento da Lais": Pré-agendamento de visita · Qualificação e Envio ao CRM · Reengajamento automático · Endereço e IPTU dos imóveis. C

### Meu negócio `/configs_my_business` → Bubble (10/11/12-meu-negocio-*.jpg) — "Treine a Lais com informações chave sobre o seu negócio." Tabs Geral · Vendas · Locação; each card has [Editar] (WRITE, not clicked).
- **Geral**: Políticas (Assinatura de contrato = "Digital e físico"; Política de chaves = "Sempre acompanhadas por alguém da equipe") · Telefones da empresa (Administração = phone; [+ Adicionar]) · Exibir nome do atendente ("A pessoa atendida conseguirá visualizar o nome do atendente que mandar mensagem.") · Recesso [Inativo] ("A Lais NÃO confirmará pausa durante o período de festas.").
- **Vendas**: Informações da operação [Ativo] (Atendimento de compra = Ativo; Nomenclatura do corretor = "Corretor") · Financiamento (Acompanhamento do processo = Ativo; Serviços oferecidos = simulação, parceria com bancos…; Custos de financiamento = ITBI, emissão de matrícula, avaliação do imóvel, taxa de registro…) · Documentos necessários (pessoais RG/CPF; renda IR/Holerite; endereço contas de consumo).
- **Locação**: Informações da operação [Ativo] (Atendimento de locação; Nomenclatura do corretor) · Documentos e processos: Documentos necessários (CPF, RG, CNH, Certidão de estado civil; extrato 3 meses, IR, holerite; contas) · Processo de locação (Prazo padrão residencial 12/30 meses; comercial 12/36/24/30; Multa rescisória "3 aluguéis proporcionais ao tempo faltante"; Isenção de multa "Mediante acordo com proprietário") · **Garantias**: Caução (Não aceito; Valor mínimo Nx aluguel) · Fiador (Não aceito; Nome limpo; Imóvel quitado) · Outras garantias (Não aceito; Possibilidade de aluguel sem garantia) · Seguro Fiança (Aceito; Seguradoras Porto Seguro, Tokio Marine, Too) · Título de capitalização (Não aceito; Cobertura; Encargos).
- Insight: this is a STRUCTURED knowledge base (typed fields, enums), not free text — the agent's answers about process/docs/guarantees are grounded in these fields. I

### Config pages — native (Next) vs Bubble
Native: configs, configs_visits, configs_qualification, configs_reengage, configs_templates, configs_meta_integration, configs_display_attendant_name. Bubble iframe: configs_my_business, configs_whatsapp_profile, configs_property_info, configs_behavior, user-management (→ legado `/user_management`), owners, developments. C

### Pré-agendamento de visita `/configs_visits` (13) — "Quando a Lais deve oferecer o Pré-agendamento de visitas?" Card [Inativo] "A Lais não envia a solicitação de visita para seus leads." [Editar]. Data /web/visits/config. C

### Envio de leads qualificados `/configs_qualification` (14) — full-screen wizard "Defina os critérios para que a Lais envie o lead ao CRM." Passo 1 de 2. Checkbox "Configurações diferentes para compra e aluguel". **Critérios de envio**: "A Lais qualifica e envia ao CRM os leads que atenderem algum dos critérios:" — rule groups OR'd; each group = AND of criteria; base criterion locked: `Comportamento = Qualificado via inteligência da Lais`; [+ Combinar com outro critério] (AND) · OU · [+ Adicionar critério de envio] (OR). [Saiba mais] [Próximo]. Data: /web/visits/config, /web/audiences/user-profiles, /web/audiences/required-informations. Step 2 not opened yet (pending code check that Próximo doesn't persist). C

### Reengajamento automático `/configs_reengage` (15, 17) — "Recupere leads e aumente suas chances de conversão." Tabs:
- **Reengajamento padrão**: banner "Caso haja uma Régua de reengajamento ativa, ela será iniciada após a última tentativa de reengajamento padrão." · Reengajamento em minutos [Ativo] "A Lais envia uma mensagem 15 minutos depois que o lead para de responder." · Reengajamento em horas [Ativo] "Se o lead não responder, a Lais irá tentar de novo após 4 horas — só funciona no horário comercial." [Editar each].
- **Réguas de reengajamento [NOVO]** (`?tab=reengage-rules`): [+ Nova régua] · "Régua 1 [Inativo] — Configure até 3 tentativas de contato para leads de compra ou locação." Data /web/reengage/configs, /configs_reengage/rules/:id. C
- Mechanism: 3-tier follow-up — minutes nudge → hours retry (business hours) → optional cadence (≤3 attempts, template-based since outside 24h window). I (24h-window reasoning)

### Modelos de mensagem `/configs_templates` (16) — "Gerencie os modelos de mensagem do WhatsApp disponíveis para seu time." [↻] [+ Criar modelo de mensagem], search, category chips with counts: Administrativo · Campanha · Cobrança · Documentação · Primeiro contato · Reativação · Visita · Outros. Card = category, name, status (Aprovado), body with friendly variables. Variables seen: {{Nome da pessoa}}, {{Nome do atendente}}, {{Nome da imobiliária}}, {{Imóvel da visita}}, {{Data da visita}}, {{Link do imóvel}}. 11 templates: Visita confirmada/cancelada/remarcada; Abordagem comercial/neutra; Reativação ×6 (retomando atendimento, breve, encerramento, ancorada no imóvel, reativação, checagem de interesse). Data /web/templates/available, /web/templates/categories. ⇒ official WhatsApp Business (Cloud) API with Meta-approved HSM templates. C/I

### Integrações Meta `/configs_meta_integration` — "Conecte suas campanhas do Facebook e Instagram à Lais… vincular formulários de campanhas." Steps: autorizar compartilhamento → escolher formulários. [Conectar à Meta] (OAuth, not clicked). Data /web/facebook/pages, /web/facebook/forms/local. Not connected. C

### Exibir nome do atendente `/configs_display_attendant_name` — [Inativo] toggle "Exibir nome do atendente na mensagem?" with WhatsApp bubble preview; [Cancelar][Salvar]. C

### Perfil de WhatsApp (Bubble) (18) — Informações [Editar]: logo, number, Descrição (bio: buy/rent help, send audio or text, send link or code, available anytime), Sobre ("Online"), Endereço, E-mail, Site; phone mockup mapping each field. ⇒ edits the WhatsApp Business profile via API. C/I

### Endereço e IPTU dos imóveis (Bubble) (19) — Acesso ao IPTU: "A Lais NÃO irá acessar o IPTU presente na prateleira de imóveis (XML)…" · Envio de endereço completo [Ativo]. ⇒ inventory ("prateleira") = agency XML feed. C

### Qualificação e Envio ao CRM (Bubble `configs_behavior`) — "Personalize o que a Lais deve fazer com cada tipo de lead." Tabs Perguntas essenciais · Envio ao CRM. (content pending)

### Usuários e equipes (Bubble `user_management`) (20) — "Gerencie quem pode acessar e administrar sua Casa da Lais". **Acesso por código**: "Comunique esse código com seus colaboradores para que eles possam acessar o Histórico do Cliente." 4-digit "Código da Lais". Second card empty (users list didn't render). Native /acessos ("Usuários e equipes") uses /web/agency/access-code, /auth/users, /web/seats/availability. ⚠ a 4-digit shared code gating client history = weak auth (observation only, never tested). C/I

### Qualificação e Envio ao CRM (Bubble `configs_behavior`) (21, 22)
- **Perguntas essenciais**: "Perguntas ativas (0)" [Editar] — empty for this agency. FAQ (verbatim gist): questions collect info about the lead and desired property (localização, características, condições financeiras); a question can be flagged **qualificatória** → Lais only sends to CRM once it has that answer. Lais does NOT always ask: it detects what the lead already said spontaneously and asks only what's missing; a qualificatória question is pursued until answered (less natural). ⇒ **slot-filling with required/optional slots**, extraction from free conversation. C
- **Envio ao CRM** (3 routing policies, each [Editar]):
  1. Envio ao CRM de potenciais captações — current: notify in Casa da Lais only, NOT sent to CRM.
  2. Envio de leads frios ao CRM — current: Lais does NOT send cold leads.
  3. Envio ao CRM de leads com WhatsApp inválido [Ativo] — leads Lais can't reach are auto-sent to CRM.
  ⇒ conversation outcome classes: qualified · cold · potential acquisition (owner wants to list) · invalid WhatsApp. Explains CRM column values. C/I

## Atualização de imóveis (Bubble `/owners`) (23) — header only, list empty: "Conversas com proprietários para atualizar os imóveis anunciados." ⇒ Lais also messages property OWNERS to refresh listings (status/price). Mechanism U.

## Plano e cobranças `/financeiro` (24)
- Plano e conta tabs [Plano atual | Conta de faturamento]: "Master Anual — 700 créditos de atendimentos / mês", Tipo Anual, Início 01/06/2026; donut "Consumo deste mês 120 / 2.184, 2.064 restantes" (pool > monthly ⇒ annual credits accrued/rolled? U).
- Cobranças tabs [Boletos a pagar (1) | Histórico (6)]: month, status Disponível, vencimento, value, [download][copy linha digitável].
- Pacotes adicionais: "Política de Assentos - Desconto 50% — Ativo — 5 unidades".
- Data: finance/{consumption,subscriptions,billing-account,financial-contacts,add-on-billing-accounts,invoices}. C
- Pricing unit = **crédito de atendimento** (one conversation/lead served); admin add-on "Consome meio crédito por atendimento". C

## Pacotes adicionais `/add-ons` (catalog) + detail pages
- **Atendimento administrativo** `/add-ons/administrative`: "Automatize as demandas que travam sua operação. Da segunda via de boleto ao registro de manutenção." Features: Envio de 2ª via de boleto · Registro de ocorrência (classifies + registers maintenance tickets in integrated ERP) · Diagnóstico de manutenção (collects info + evidence from tenants) · Orientação sobre processos administrativos (multas, transferência de titularidade, vistorias, rescisões). "Sistemas ERPs integrados". ½ credit per atendimento; "Ative gratuitamente". [Solicitar demonstração]. C
- **Gestão de atendimentos Pro** `/add-ons/pro` [Pacote contratado]: onboarding steps — 1) add attendant users (each = 1 Pro seat; nome, e-mail, nível de acesso, tipo de assento); 2) per team, choose who distributes leads after Lais pre-service: **the Lais or the CRM**; 3) create teams (by operação, setor, empreendimento, região…); 4) attendants download the **mobile app** (credentials by e-mail). C
- **Campanhas inteligentes** `/add-ons/smart-campaigns`: "Conecte o atendimento da Lais à Meta e melhore a qualidade dos leads gerados por suas campanhas de mídia paga." Claims +25–50% qualification rate. Features: Integração com a Meta (Business Manager, no dev); **Sinal de qualificação** — lead qualificado, visita agendada, resposta do cliente become events sent to Meta's algorithm (⇒ Conversions API offline events); formats incl. Click to WhatsApp. C/I

## Usuários e equipes `/acessos` (native) (25, 26)
- Código de acesso (4-digit "Código da Lais") "Compartilhe com colaboradores para que acessem links da Lais."
- Tabs Usuários · Equipes [NOVO]. Usuários: [+ Adicionar usuário], seat meter "4 de 5 assentos utilizados / 1 disponível"; columns Usuário (name, email) · Nível de acesso (Administrador | Atendente) · Assento (Padrão | Pro) · Status (Ativo) · ⋮ menu. 7 users (3 admins Padrão, 4 attendants Pro).
- Equipes: [+ Criar equipe]; team "Atendimento Piloto — 3 membros [Editar]" expands to table Usuário · Último acesso · **TPR** (tempo de primeira resposta) · Conversas · Distribuição ("Nenhuma atribuída").
- Data: /web/agency/access-code, /auth/users, /web/seats/availability, /web/teams. C

## Conversas `/chats?chatId=<uuid>[&view=kanban]` (27–30) — the operator workspace (3 panes; sidebar collapses to icon rail)
**Left — list**: title "Conversas", view toggle [Ver como lista | Ver como kanban], [+ Nova conversa]; tabs Todas · Minhas · Arquivadas; Pesquisar; Filter drawer "Filtro de conversas" [Limpar] [Filtrar]: OPERAÇÕES (radio: Aluguel · Compra · Administração · Atualização) · STATUS CRM (Enviado ao CRM · Não pronto) · STATUS DE ATENDIMENTO (Lais atendendo · Atendimento manual) · RESPONSÁVEL (multi: Sem responsável + each user) · EQUIPE (multi: teams). Card: name, phone, time, unread dot ●, channel icon (WhatsApp / portal logo e.g. Grupo Zap), operation chip; per-card ⋮ "Abrir menu de ações da conversa". Pinned chats in localStorage `@lastro/chat:pinned-chats`.
**Kanban** (`&view=kanban`, 30): column "Todas (2222)" with eye toggle, collapsed "Arquivadas" lane, [+ Adicionar coluna] ⇒ user-defined columns (likely saved filters). C/I
**Center — conversation**: header lead name + [Atribuir responsável ▾] (WRITE); actions Like service · Dislike service · Leave feedback (= feedback on the AI's service quality — training signal) · Archive chat · Block number (all WRITE). Floating switch **"Lais atendendo" ⇄ "Atendimento manual"** (bot/human handoff — SEND-class, never toggled). Timeline with day separators and **system events**: "Cliente chegou via WhatsApp", "Lead não respondeu mais. Lais reativou a conversa" (+⚙ link to reengage config). Composer: anexo, emoji, text, Gravar áudio, Send (SEND-class).
**Right — "Cliente"**: header actions Call on WhatsApp · History link (copy client-history link) · Send to CRM (WRITE). Accordions: **Perfil** (name, phone, chip "Primeiro contato hoje às 12:19") · **Visitas solicitadas (n)** · **Etiquetas** [+] · **Notas internas (n)** [+ Nova anotação] · **Interações (n)**: per interaction — type (e.g. "Comercial"), "Iniciada em <datetime>", chips channel · operation · CRM status, extracted slots ("Localização: Região (não especificada)", "Orçamento: Não informado"), an AI narrative summary, and intent flags in italics ("*Foi identificado que o lead quis encerrar o atendimento.*"). C
Data: /web/chats/agency (list), /web/chats/:id, /:id/messages, /:id/internals (notes), /:id/visits, /:id/interactions, /web/tags, /auth/users, /web/teams. C

### Observed AI script (one complete conversation, PII omitted)
1. greet + identify ("Sou a Lais, da <imobiliária>") → 2. first qualifying question "Você busca um imóvel para comprar ou alugar?" → (silence) system reengage "Lais reativou a conversa" → "Qual perfil de imóvel você está procurando no momento?" (2nd chat).
3. Off-topic (partnership pitch) → routes to the admin WhatsApp link from Meu negócio › Telefones (Administração), then pivots: "Você possui algum imóvel que gostaria de anunciar ou atualizar…?" (acquisition probe) → repeats routing on follow-up → "Posso ajudar com mais alguma informação?" → polite close. Messages are split into short bubbles (2–3 per turn). Interaction ended as Locação / "Enviado ao CRM" despite being a partnership pitch (CRM policy sent it). C

## Notificações `/notifications` (31, 32)
- "Mantenha-se atualizado com as notificações personalizadas da Lais." Toggle **"Notificar lead pronto para atendimento"** (ON; WRITE). Feed by day; card = category label (e.g. COMERCIAL), text "<lead> é um novo lead na Casa da Lais", datetime, expand chevron. 138 in Oct.
- Filtro de notificações: DATA (range), OPERAÇÕES (Todas · Aluguel · Compra), TIPO DE NOTIFICAÇÃO (Solicitação de pré-agendamento de visita · Cobrança de atendimento · Relatórios da Lais · Remarketing). URL `type=` values seen: `lead-property-acquisition` (+`view=acquisition` → Captação page), `lead-user-demanding-followup-notification`. Data /web/notification-events. C
- ⇒ Notifications are the event bus surfaced to humans: new qualified lead (Comercial), visit request, lead demanding follow-up ("cobrança de atendimento" = lead complaining no one answered), reports, remarketing, property acquisition. I

## Meu perfil `/perfil` — "Atualize seu WhatsApp. Nome, e-mail, cargo e área de atuação são apenas leitura." Dados pessoais (Nome, E-mail, Nível de permissão), Contato (WhatsApp — editable), Cargo e atuação: Cargo/Atribuição enum keys shown raw (`comms_marketing`, `owner_partner`, `team_manager`) and Área de atuação (`marketing`, `people`, `other` + "Outra área" text) — i18n missing, raw enum leak. [Salvar]. C

## Leads v3 `/leads-v3` (33) — same table as /leads (breadcrumb "Leads v3"), newer build: shows leads without operation ("-") and "Não pronto". Data /web/leads/ + origins + campaigns. Feature-flagged successor. I

## Guia da Lais `/trainings_page` — "Aprenda a usar a Lais para vender mais e operar com menos esforço." Trilha de conhecimento: Boas-vindas (1. O que torna a Lais diferente e mais avançada 4min; 2. Onde a Lais atua e como funciona a integração 2min) · Introdução à Casa da Lais · Faça mais com a Casa da Lais. Video lessons. C

## Novidades `/whats-new` — dated changelog (product history)
- 03 SET 2026 **Relatório de Atendimento administrativo**: conversas administrativas, boletos enviados, ocorrências geradas; daily chart; resolved-by-Lais vs forwarded-to-team; Top 5 categorias de ocorrência; month picker (Relatórios › Atendimento administrativo; needs admin add-on).
- 26 AGO 2026 **Página de Disparos em massa**: Remarketing + **Atualização de anúncios** unified; Novo disparo flow for both types; drafts.
- 29 JUL 2026 **Reengajamento**: also re-contacts leads who NEVER replied (on by default); Réguas per operation (venda/aluguel); recovered leads return to Lais for qualification at no extra cost.
- 15 JUL 2026 **Campanhas inteligentes**: Lais sends Meta which leads qualified in conversation (⇒ CAPI events); Meta optimizes audiences.
- 08 JUL 2026 **Gestão de atendimentos Pro**: single WhatsApp number for the whole team; teams with access levels (gestores vs atendentes); attendants see only own leads; qualified leads auto-distributed by **"roleta da Lais"** (round-robin) or CRM rules; admin demands distributed by category; mobile app with real-time notifications.
- 02 JUL 2026 **Análise de crédito** via **CredAluga** integration at the visit-scheduling step; result (aprovada/reprovada) in conversation history; lead must consent (LGPD).
- 01 JUL 2026 **Integrações Meta**: connect multiple Meta lead forms; leads go straight to Lais and are auto-served. C

## Histórico do Cliente `/history` (34) — chrome-less read-only view of one conversation + Cliente panel (Perfil, Interações; WhatsApp + link buttons). This is what "Copiar link do histórico" shares; brokers outside the platform open it with the 4-digit **Código da Lais**. Data: same /web/chats/:id/* endpoints. C/I

## Relatório ▸ Bairros (35) — "Top 10 bairros — os bairros mais interessantes para os seus leads de <operação>" (horizontal bars, lead counts). "Desempenho por bairro" (select bairro): "A mediana de preço de aluguel pesquisada em <bairro> pelos seus leads foi R$ X", "% dos leads … buscaram por <tipo>", "imóveis com N quartos são os que fizeram mais sucesso", table IMÓVEIS MAIS BUSCADOS NESTE BAIRRO. ⇒ the extracted slots (bairro, tipo, faixa de preço, quartos, imóvel de interesse) are stored per lead and aggregated monthly. C/I
