# Lais legacy (Bubble) — the app definition, read from `window.app` (S2, 2026-10-13)

**How it was read.** Every Bubble page ships its own definition to the browser as `window.app`
(here 3.5 MB on `/configs_my_business`). It contains the data types, option sets, the
API Connector catalogue, the current page's element tree with its workflows, and every reusable
element. Opening `https://legado.lais.ai/<page>?mode=iframe&agency=<own id>&parentOrigin=https://casa.lais.ai`
in its own tab renders the page shell with **no data** (no token arrives by `postMessage`), but the
definition is complete. So the whole UI and its save logic can be mapped **without opening or saving
any form on live data**. Only this agency's own id was used. API keys stay server-side
(`private_key_header` groups); none are in `client_safe`, and none were looked for.

Evidence: C (read from the definition).

## 1. Bubble's own database is thin

| Type | Fields |
| --- | --- |
| User | name, userId, auth_token, refresh_token, session_state, expires_in, role (option Role), currentReaId, json_role_rea, real estate agency id (list) |
| User Agency Role | User, Agency ID, Role, Status (ativo/pendente) |
| Pending Invitations | Agency ID, Email, Role |
| Banner · BannerToAgency | CTA, Title, CTA Link, ImageURL, Priority, Type (Default/Dynamic/Report) · banner→agency |
| Feature Flag · Maintenance | type/enabled · enabled + modes (per page) |
| Breadcrumb | link, name, page, order, active |
| Rea In Onboarding / Rea with Intercom Odf / Rea In Owners_temp | agency-id lists (rollout cohorts) |
| misc | test, upsell, addReaUser, logoutUser, FirstVideoOnboarding |

All business data lives behind the APIs below. Bubble is only a UI and orchestration layer.

**Option sets worth reusing:** Role = Administrador · Editor · Membro. Channel = 56 lead
portals/channels (Grupo Zap, ImovelWeb, Chaves na Mão, Casa Mineira, 123i, Guia de Imóveis ×13
regional, ZN/ZL/ZS/ZO Imóvel, RD Station, Kenlo, Rocket Imob, Facebook/Instagram/Google Ads,
YouTube, Placa, …). FilterStatus = Todos os Leads · Enviado ao CRM · Erro no envio · Não pronto ·
Sem atendimento. NotificationType = Nova visita solicitada · Novo lead · Cobrança de atendimento.
Onboarding step slugs: whatsapp-profile, whatsapp-config, features, features-visit, business-id,
business-phones, business-policy, business-rent(-schedule|-docs|-guarantees|-deadlines),
business-sell(-schedule|-docs|-financing), crm, xml, developments, schedule-call.

## 2. API Connector catalogue (what Bubble calls)

Hosts are parameters: `[path]`/`[version]` = the BFF or core API, `[version]-ai.lastro.services` = **Core AI**.

| Group | Calls (method path) |
| --- | --- |
| **Onboarding - Core** (knowledge base) | GET/PUT `/api/v1/real-estate-agency/{agency}/business-settings/{identification · visit-policy · rental-info · rental-documentation · rental-guarantees · rental-contract-terms · sale-info · sale-documentation · sale-financing · bot-work-hours · work-hours · bot-profile}` · GET/PUT `…/behavior-settings` (+ `/info`, `/visit-hours`) · flows `…/flows/{slug}/onboarding-progress`, `…/steps/{step}/complete` · lead-origins CRUD · XML `validate-xml`, `v2/etl/{agency}/load`, `v2/onboarding/dashboard/agencies/{agency}/feeds/xml-status`, `…/forwardings/crm-status`, `v2/onboarding/dashboard/forwardings/validate`, `forwarding-settings` |
| **Core AI** | chats `{chatId}/feedback` GET/POST · `chats/{chatID}/history` · onboarding chat `chats/onboarding` (+`/{chatId}`, `/{chatID}/message`) · `users/block/rea/{agency}` check/POST/DELETE · **`dialog360/account-info` GET/PUT** (WhatsApp provider = 360dialog) · **`agents/malicious-instructions/verify`** (prompt-injection check) |
| **Core AI - Configs** | **`prompt/rea/{agencyID}/phones` GET/PUT · `prompt/rea/{reaId}/recess` GET/PUT · `prompt/rea/{agencyID}/refresh` POST** |
| Lastro Refactor (legacy core) | dashboard-config, basic-info, dashboard(+performance, annual-overview), report(+exists), leads filter v2, lead visits, `leads/{id}/enhance`, `force-enhance`, `batch-enhance`, batch-xlsx imports, access-code GET + check, developments CRUD (+image), property-owners (list, available-dates, upload, confirm, schedule PATCH, batch-xlsx), reachout (validate leads/file, schedule confirm, available dates), payments, campaigns-for-filters, behavior-settings |
| Keycloak - BFF | `auth/logout`, Keycloak token (3 grant shapes), `auth/users/me`, users CRUD, `auth/profile`, implementation-analyst calendar, `web/agency/settings` GET/POST, **`web/auto-forwarding/{intervals,config}`**, **`web/forwardings`** (+PUT `{ids}`), **`web/required-information`** (+`/selected` GET/POST), `web/reengage/configs` (+delay-minutes), audiences, visits config, plan-consumption, test-users, smart-suggestions, property-owners from suggestion |
| Waba Onboarding - BFF | `waba/onboardings/start`, `es-complete`, `es-failed` (Meta Embedded Signup), `waba/{onboarding}/status`, `waba/count`, `waba/latest` |
| other | MailerSend email · Bubble backend workflows `user_invitations`, `link-creator`, `multi_file_to_base64` |

## 3. The save pattern: settings → prompt rebuild

From the `configs_my_business` workflows: every "Salvar" in a Meu negócio drawer does
`PUT business-settings/<section>` (or `PUT prompt/rea/{id}/phones|recess`), then
**`POST {ai}/prompt/rea/{agencyID}/refresh`**, then shows "Alterações feitas com sucesso!".
**The agent's system prompt is generated server-side from structured settings and rebuilt on
every save.** It is not free text the customer edits. Some fields are support-only ("Para alterar
este campo entrar em contato com o suporte").

Leaving a drawer with unsaved changes asks "Sair da edição? As modificações feitas não serão
salvas." (Cancelar / Confirmar).

## 4. Edit forms (the `drawer` reusable: 1,174 elements, shared by all config pages)

Each card on a page opens the same drawer with a `type`. The fields per section are below.

### Meu negócio — Geral
- **Políticas**: Assinatura de contrato (Digital e físico · Digital · Físico); Chaves para visitar (Sempre acompanhadas por alguém da equipe · Cliente pode buscar a chave e visitar sozinho · Outro). → `PUT business-settings/visit-policy`.
- **Telefones da empresa** ("Atualize os contatos dos diferentes setores para que a Lais direcione os clientes corretamente"): list of {setor, phone (mask, ex 5511999999999)}, a main contact, an "Adicionar novo contato" popup. → `PUT prompt/rea/{id}/phones` + refresh.
- **Exibir nome do atendente** → `web/agency/settings.prefixHumanMessagesWithSenderName`.
- **Recesso**: Início/Término (dd/mm/yyyy, calendar), switch "Aviso de recesso — A Lais avisará que estão em recesso durante o período informado", message. → `PUT prompt/rea/{id}/recess`.

### Meu negócio — Vendas
- **Informações da operação**: Lais atende compra? (support-only), Nomenclatura do corretor de venda. → `sale-info`.
- **Documentos necessários** (chips): Documentos pessoais (Certidão de estado civil, Passaporte/RNE, Carteira de trabalho, Telefone de contato, Número do PIS, E-mail, Extrato do FGTS, Para PJ: contrato social, …), Comprovante de renda (Extrato bancário 3 meses, Contra-cheque, Pro-labore, Para PJ: Balanço patrimonial, …), Comprovante de endereço (luz, água, telefone, internet, faturas de cartão, boleto de condomínio), Detalhes adicionais. → `sale-documentation`.
- **Financiamento**: Empresa acompanha o processo?; Serviços oferecidos (Parceria com despachantes · Oferece simulação de financiamento · Parceria com bancos); Custos de financiamento (Avaliação do imóvel · Taxa do registro do imóvel/contrato · Taxa de engenharia · Emissão de matrícula · Taxa de análise de crédito · …); Detalhes. → `sale-financing`.

### Meu negócio — Locação
- **Informações da operação**: Lais atende locação? (support-only), Nomenclatura do corretor de locação. → `rental-info`.
- **Documentos necessários**: the same three chip groups plus "Para fiador: documento de próprio imóvel quitado" and "Matrícula do imóvel". → `rental-documentation`.
- **Processo de locação**: Prazo padrão Residencial / Comercial (chips 12 · 24 · 30 · 36 · 48 · 60 meses); Multa rescisória padrão (10% do valor do contrato proporcional aos meses restantes · 3 aluguéis proporcionais ao tempo faltante); Isenção de multa (Sim · Não · Mediante proposta e aceitação do proprietário). → `rental-contract-terms`.
- **Garantias** (one card each, "A Lais poderá oferecer essa opção…"), all → `rental-guarantees`:
  - Caução: aceito? oferecer? valor mínimo (nº de aluguéis), detalhes (support-only).
  - Seguro fiança: aceito? oferecer? seguradoras aceitas (chips incl. Porto Seguro, Tokio Marine, Fiança Rápida, Super Save, …).
  - Fiador: aceito? oferecer? requisitos Nome limpo, Imóvel quitado, Localização específica (Mesma cidade · Mesmo estado).
  - Título de capitalização: aceito? oferecer? quantidade de aluguéis ("12", "até 12", "de 6 a 12"), inclui encargos (IPTU, condomínio).
  - Outras garantias: aceitas? (chips Loft (antiga CredPago), Fianças Bancárias, …), "Possibilidade de alugar sem garantia — É necessária aprovação do proprietário".

### Perfil de WhatsApp (`configs_whatsapp_profile`) → `{ai}/dialog360/account-info` GET/PUT
Foto da Lais (PNG/JPG ≤ 5 MB, ≥ 192×192), Nome da Lais (support-only), Telefone da Lais (support-only),
Descrição (default "Estou aqui para te ajudar a comprar ou alugar o seu próximo imóvel. Mande áudio ou
texto…"), Sobre ("Disponível 24h"), Endereço, Site (support-only), E-mail de contato.

### Endereço e IPTU (`configs_property_info`) → `behavior-settings` + `web/agency/settings.useIptu`
"Envio de endereço completo" (else only bairro + cidade); "Permitir acesso ao IPTU?" (reads IPTU from
the XML shelf; the UI advises keeping it off when the XML is incomplete).

### Qualificação e Envio ao CRM (`configs_behavior`)
- **Perguntas essenciais** → `GET web/required-information` (catalogue) + `GET/POST …/selected`.
  Lista de perguntas filtered by category, switches per question, a **"Qualificatória"** checkbox,
  "Mostrar todas". Limits come from the API (`maxNumberQuestions` 8, `maxNumberQualifyingQuestions` 5),
  with the tooltip "Você atingiu o limite de perguntas adicionadas". Locked questions show "Esta pergunta
  é essencial para a identificação da operação correta… desativa-la solicitando ao suporte". A question
  used by a CRM criterion can't be switched off ("primeiro desative os critérios de envio ao CRM").
  The confirm text reads "a Lais irá mudar seu comportamento no atendimento, fazendo as perguntas adicionadas".
  A banner notes that the qualifying questions have moved into the **Envio ao CRM** criteria.
- **Envio automático de leads qualificados** (cards for compra and aluguel): "A Lais qualifica e envia
  ao CRM os leads interessados em … que atenderem algum critério: Visita solicitada via formulário da
  Lais **OU** Qualificado via Inteligência da Lais (a partir de / até / Independente do valor)". Saves to
  `POST web/auto-forwarding/config` + `PUT web/forwardings/{ids}`.
- **Envio de leads frios ao CRM**: "Encaminhar leads frios" switch; Após intervalo programado
  (`web/auto-forwarding/intervals` = 30 min … 10 h, counted from the last reengage attempt) **or**
  the next morning 05:00–06:00.
- **Potenciais captações**: send to the CRM, or notify in Casa da Lais only.
- **WhatsApp inválido**: send to the CRM automatically or not.
- **Pesquisa com clientes**: an opt-in for weekly random satisfaction surveys.

### Reengajamento (`configs_reengage`) → `web/reengage/configs` PUT ×2 (reminder + final)
Short term: any hour, delay 5–60 min. Long term: business hours only, 08:00–20:00, delay 1–11 h.
"Sempre que o lead responder, o fluxo de reengajamento recomeça. Pessoas que encerram o atendimento
não serão contatadas." The legacy single-delay card (1–6 h) also persists in `behavior-settings`.

### Pré-agendamento de visita (`configs_visits`) → `behavior-settings`
Switch (accept visit requests; switching off "desativa apenas o envio do link de pré-agendamento");
"Diferenciar configuração para leads de compra e aluguel" (Compra/Aluguel tabs); per weekday switch
plus two time ranges; Solicitação de CPF obrigatória; Tempo mínimo (dias + horas) / máximo (dias) to
request; slots every 30 min ("9:00, 9:30, 10:00…").

### Usuários (`user_management`)
Invite by e-mail + full name → `POST auth/users` + flow step complete, plus a Bubble `user_invitations`
workflow; give/remove editor; delete user/invite (`DELETE auth/users/{email}`); member search, paging;
"Acesso por código — Código da Lais" (`GET access-code`).

## 5. Bubble-side gotchas seen
- The client keeps `auth_token`/`refresh_token` fields on the Bubble User type (token persistence in Bubble).
- Visibility of the whole definition (all pages' elements and API paths) is by design in Bubble. That is useful for us; it is not a vulnerability report.
