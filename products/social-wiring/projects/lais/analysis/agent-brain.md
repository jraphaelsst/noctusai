# Lais — how the agent's "brain" is configured (S2, 2026-10-13)

Sources: read-only BFF GETs on the owner's agency (`captures/xhr-2026-10-13/`) and the Bubble app
definition (`bubble-app-definition.md`). Values are product content or this agency's own config.
No lead data is included.

## 1. Architecture of the brain
1. **Structured knowledge base.** `business-settings/*` sections (identification, phones, visit
   policy, sale info/docs/financing, rental info/docs/guarantees/contract terms, bot/work hours,
   bot profile, recess), filled through forms.
2. **Prompt compilation.** Each save calls `POST {core-ai}/prompt/rea/{agency}/refresh`, so the system
   prompt is rebuilt from (1). Customers never edit prompt text, and some fields are support-only.
3. **Slot filling.** "Perguntas essenciais" are picked from a fixed catalogue; selected questions are
   asked or inferred during the chat, and "qualifying" ones gate the CRM push.
4. **Behaviour switches** (`behavior-settings`, `web/agency/settings`): full address, IPTU, invalid
   WhatsApp, potential captações, surveys, sender-name prefix, visits.
5. **Guards.** `agents/malicious-instructions/verify` (prompt-injection check), `users/block/rea/{agency}`
   (block a contact), `chats/{id}/feedback` (thumbs on AI replies).
6. **Channel.** WhatsApp through **360dialog** (`dialog360/account-info`, profile fields) and Meta
   Embedded Signup (`waba/onboardings/*`); messages outside 24 h use Meta-approved templates.

## 2. Perguntas essenciais — the catalogue (63 questions, 6 categories)
Limits: **max 8 active, max 5 qualifying**. `requiredQuestions` = "Objetivo: comprar ou alugar"
(always on; locked by support).

| Category | Questions |
| --- | --- |
| Operação (goal) | Objetivo: comprar ou alugar |
| Informações do lead | Nome · E-mail · Região de residência atual · Casado e tem filhos · Data de nascimento · Animal de estimação (Aluguel) · Estado Civil · Filhos menores de idade · CPF |
| Características do imóvel | Faixa de preço desejada · Tipo do imóvel (+ "– Compra", + "apartamento ou casa") · Tamanho · Características específicas · Planta preferida (Compra) · Interesse principal no imóvel · Garagem · Idade máxima · Nº banheiros · Nº quartos · Área m² · Necessidade especial |
| Localização | Cidade · Proximidade a serviços · Bairro desejado |
| Informações financeiras | Renda familiar · Comprovação de renda 3× aluguel · Recurso para entrada (Compra) · Método/Forma de pagamento (Compra) · Parcela ideal de financiamento · Garantia a utilizar (Aluguel) · Permuta com imóvel · Documentação análise de crédito · Compra individual ou conjunta · Valor de entrada disponível · Tipo de renda formal/informal · Valor considerado adequado · Tempo de carteira assinada (≥ 3 anos) |
| Interesses gerais | Locação anual ou temporada · Tempo de busca · Conhecimento de documentação · Estágio de busca · Motivo da localização · Morar ou investir · Investimento depreciação/aluguel · Experiência com aluguel · Tempo de locação · Empreendimento específico · Mais info do imóvel ou outras opções · Decisão por algum imóvel · Prazo para compra · Prazo para mudança (+ Aluguel) · Experiência comprando/alugando · Parceria ou interesse no imóvel (filters broker partnerships) · Possui imóvel próprio · Pronto ou na planta · Conhecimento do processo de locação |

Some questions carry an instruction for the LLM in `description` (for example "Exatamente o mesmo
comportamento… mas perguntada somente nas conversas de usuários querendo comprar"). **The catalogue
item = label + LLM hint + category + optional operation scope.**

This agency's selection: Nome (opt), **Objetivo (qualifying)**, **Faixa de preço (qualifying)**,
Características específicas (opt), Bairro desejado (opt).

`GET web/audiences/required-informations` is the CRM-criteria view of the same slots:
`{information, category lead|real_estate, required, isNumeric, isCurrency, profileField{fieldName,
fieldType string|numeric}}`. For example, Faixa de preço → `price_max` (numeric, currency).

## 3. CRM forwarding
- Connector: `web/forwardings` = `[{type:"vista-v2", enableAutoForwarding:true}]`. **This agency
  pushes to Vista** (closes the S1 unknown).
- Qualified leads: rules per operation, "Visita solicitada via formulário" **OR** "Qualificado via
  Inteligência da Lais" with an optional value range. Rules builder = audiences/user-profiles (S1).
- Cold leads: `auto-forwarding/config {enabled:true, sendType:"interval", intervalMinutes:30}`.
  Options are 30 min to 10 h after the last reengage attempt, or the next morning 05:00–06:00.
- Lead status labels: enhanced = "Enviado ao CRM", message-replied = "Não pronto",
  enhanced-error = "Erro no envio". Each lead carries `forwardingDeliveries[{status, triggeredBy, enhancedAt}]`.
- Agency flags (report payload): `enableSendWithoutNumber:true`, `sendStreet:true`, `reachoutEnable:true`, `reengageHours:4`.

## 4. Reengagement
- `reengage/configs`: reminder 15 min (options 5–60 min, any hour) + final 240 min (1–11 h, 08–20 h only). Both enabled here.
- Réguas (`reengage/rules`): named rules per buy/rent with `attempts[]` (here "Régua 1", disabled, 0 attempts). Rule templates by slug:
  - `lead_reengage_short` — "Olá {{1}}. Sua solicitação segue sem conclusão, gostaria de dar prosseguimento a ele agora?"
  - `lead_reengage_long` — closing message, "…será encerrada. Caso deseje retomar…"
  - `lead_reengage_brief_message` — "Sua solicitação ainda está em aberto…"
  - `lead_reengage` — anchored on the property, "…referente ao imóvel {{2}}… preciso do seu \"ok\""
- Replying restarts the flow; leads who close the conversation are never contacted again.

## 5. WhatsApp templates (Meta-approved, `web/templates/available`)
| Category | Templates (Meta category) |
| --- | --- |
| visit | Visita confirmada / cancelada / remarcada (UTILITY; lead_name, visit_property, visit_scheduled_at) |
| first_contact | Abordagem comercial · Abordagem neutra (MARKETING; lead_name, current_user_name, agency_name) |
| reactivation | 4 reengage templates above (UTILITY) · Reativação de atendimento (MARKETING) · Checagem de interesse (UTILITY) |

Template categories: administrative, campaign, billing, documentation, first_contact, reactivation, visit, other.
**Parameter registry** (`web/templates/params`) — each param has a `source`: `core` (lead.name,
real_estate_agency.name, lead.client_listing_id, lead.property_link, visit.created_at), `core_ai`
(bot.name), `session` (current_user.name), `manual` (message, visit_property, visit_scheduled_at).
Chat-level `templateSendPolicy {allowed, sentCount, maxAttempts}` caps template sends per chat.

## 6. Visits
`agency/settings/visits`: mode `unified` (or split buy/rent), `general{enabled, documentRequired, daysToOffer 3, minDaysToOffer, minHoursToOffer, schedule{weekday:[{start,end}]}}`; 30-min slots.
Visits list needs `view=week&date=YYYY-MM-DD` (`view=month` is rejected). Here: disabled.

## 7. Plans, credits, seats
- Plan "Master Anual" = 700 credits/month (8,400/yr), overage R$ 4.50 (monthly plan: R$ 5).
  `finance/consumption`: month credits, used, remaining. Charts: `plan-consumption` has a projection.
- `lead-summary`: totalLeads, uniqueClients, **qualifiedConsumption / unqualifiedConsumption / unattendedConsumption** (credit accounting splits by outcome).
- Broadcasts: `plan {totalUserPlan 700, maxPerDispatch 105 (15 %), usedThisMonth}`; remarketing segments `leads-2plus-bedrooms`, `eligible-leads-3-15-days`, `eligible-leads-7-30-days`; broadcast template `lead_reachout_recommended_v1_2`.
- Seats: paid/free/test, `seat-policy-50off` add-on; premium module `atendimentos_premium` (gates teams/transfers/notifications).

## 8. Notes for our own module (not a build plan)
- Store the knowledge base as typed sections and compile the prompt server-side, so users never edit prompt text.
- Keep a versioned slot catalogue with LLM hints, a max-active/max-qualifying limit and one required slot.
- A lead is "ready for CRM" when its qualifying slots are filled ∧ a rule matches. Cold leads are pushed on a timer after the last reengage attempt.
- Reengage in two tiers (any-hour short, business-hours long), reset on reply, never after an explicit close.
- Templates reference typed params from a registry (core / ai / session / manual).
