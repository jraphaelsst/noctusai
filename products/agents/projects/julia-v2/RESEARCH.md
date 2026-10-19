# Julia v2: research appendix (2026-10-19)

Online research the owner asked for to enrich Julia v2's build. There were three tracks: (1) lead qualification and scoring, (2) agent context, threads, enforcement, evals and KPIs, (3) real-estate content, regulation and behaviour. This file is **input** to the v1 content seed, which is written as DB rows in the agents app and never as code. The binding decisions live in `CONTRACT.md` §0.3/§0.4. Where research and an owner decision differ, **the owner decision wins**. Each such conflict is listed in §6 with the safeguard we apply.

Point values, thresholds and cadences marked *illustrative* are starting values to calibrate on real outcomes (broker-accepted vs. rejected after about 60 days). They are not market statistics.

---

## 1 · Qualification: frameworks and scoring

- **Frameworks.** BANT/ANUM/FAINT are one family, and MEDDIC and GPCTBA are enterprise frameworks (overkill here). For B2C real estate the useful ideas are **LPMAMA** (Location, Price, Motivation, Agent, Mortgage, Appointment) and CHAMP's "motivation first". Sources: [Sierra](https://help.sierrainteractive.com/helpcenter/how-to-use-lpmama-to-qualify-buyer-leads), [The Close](https://theclose.com/lpmama/), [KW](https://kellerink.com/blogs/news/qualify-clients-with-lpmama-the-mother-of-all-conversation-frameworks), [meddicc.com](https://meddicc.com/meddicc-versus-other-qualification-frameworks-like-bant).
- **Order of questions.** Most ISA practice goes motivation → finances → timeline, and always asks "do you need to sell first?". The order is a matter of style; what to cover is the consensus ([HousingWire](https://www.housingwire.com/articles/buyer-questionnaire/), [agentloft](https://agentloft.com/blog/top-questions-to-qualify-real-estate-leads)).
- **Separate axes.** Score fit and intent (and urgency) separately and require each one. Engagement must never promote a lead whose fit is poor ([Breadcrumbs](https://breadcrumbs.io/?p=16557)).
- **Negative scoring** is standard ([Pedowitz](https://www.pedowitzgroup.com/how-do-you-prevent-over-scoring-low-intent-leads?hsLang=en)).
- **Decay** applies to intent and urgency, never to fit. Time-anchored answers such as `prazo_decisao` expire and are asked again.
- **Explainability.** Each point carries a reason (criterion, value, quote), and each stage carries the rule id that fired. This also serves LGPD art. 20 review.
- **Over-qualification guard.** The handoff never waits on later-stage items. Profile details refine the property match; they do not gate the handoff.

### 1.1 Julia v1 basics (owner scope: a fast first moment; target about 6–8 lead replies)

| key | type / options | note |
|---|---|---|
| `operacao` | compra · aluguel | Often implied by the campaign, so confirm it rather than ask |
| `interesse_campanha` | so_esse · esse_e_similares · aberto | The campaign property anchors price, region and type |
| `motivacao` | primeiro_imovel · upgrade_espaco · mudanca_regiao · investimento · sair_aluguel · outro | One open question: "o que te fez buscar agora?" |
| `prazo_decisao` | imediato · ate_3m · 3_6m · 6_12m · mais_12m · indefinido | Urgency axis; expires (`validade_dias`) |
| `forma_pagamento` | a_vista · financiamento · permuta · nao_sabe (n/a for rent) | Coarse viability only; detail is later stage |
| `precisa_vender_atual` | sim · nao · nao_se_aplica | The most common buyer blocker |
| `faixa_preco` | BRL range | Ask for a range, never income |
| `regioes` + `trabalho_define_local` / `regiao_trabalho` | list; bool + text | One question: "precisa ficar perto de algo?" |
| `tipo` + `quartos_min` (+ `vagas_min`) | casa · casa_condominio · apartamento · terreno; int | Hard filters |
| `itens_essenciais` | animais, jardim/quintal, piscina, churrasqueira, escola_perto, comercio_perto, acesso_rodovia, terreo_sem_escadas | One "o que não pode faltar?". Accessibility is asked as a feature, never as a reason (health data) |
| `ja_tem_corretor` | sim · nao | Código de Ética art. 6, VII: never divert another broker's client. If sim, route to a human |
| identity (owner §0.4) | `nome`, `email`, `cpf`, `rg` (phone comes from the channel) | Asked **after visit intent**, with the purpose stated; see §6 |
| derived | `imoveis_curtidos[]`, `imoveis_rejeitados[]` + `motivo_rejeicao`, `intencao_visita` (sim · talvez · nao), `pediu_humano`, `respostas_count`, `ultima_resposta_em` | System-derived; the model cannot record these directly |

Dropped from v1 (minimisation): `profissao` (`regiao_trabalho` covers what matters), `composicao_familiar` (`quartos_min` covers it), `credito_aprovado` and the full `bloqueios` list (later stage).

**Minimum to offer properties:** `operacao` + `faixa_preco` + (`regioes` ∨ `trabalho_define_local`) + (`tipo` ∨ `quartos_min`). When the lead came from a campaign and `interesse_campanha ≠ so_esse`, the campaign property anchors price, region and type, so Julia can offer after about 3 answers.

**Axes (*illustrative*):**
- **FIT 0–40, never decays:**
  - region in coverage: +10
  - price range overlaps the portfolio: +15 (no overlap: −15)
  - `forma_pagamento` known: +10
  - does not need to sell first: +5
- **INTENT 0–40:**
  - campaign interest recorded: +5
  - liked properties: +5 each, max 10
  - visit intent: sim +20, talvez +8
  - replied within 24h: +5
  - all properties rejected in 2 rounds: −5
- **URGENCY 0–20:** imediato 20 · ate_3m 15 · 3_6m 10 · 6_12m 5 · otherwise 0. "Só pesquisando" sets it to 0.
- **Decay:** intent halves after 14 days without a reply and resets at 45 days. Urgency follows the `validade_dias` re-ask rule.

**Stages (deterministic, data rules):**
1. `novo`
2. `em_conversa`
3. `perfil_basico` (minimum to offer)
4. `qualificado` = perfil_basico ∧ prazo ≤ 6m ∧ `forma_pagamento` ≠ nao_sabe ∧ `precisa_vender_atual` known ∧ FIT ≥ 25
5. `nutrir` = perfil_basico ∧ (prazo ≥ 6m ∨ indefinido ∨ FIT < 25)
6. `pronto_para_corretor` (conclusive), reached by any of:
   - qualificado ∧ (intencao_visita = sim ∨ (≥1 liked ∧ urgency ≥ 15)), with identity complete (owner §0.4)
   - `pediu_humano`, from any stage
   - 2 rounds rejected ∧ qualificado
7. `descartado_sugerido`: opt-out, wrong number or spam, out of coverage, broker fishing. **A human confirms `descartado`** (LGPD art. 20).

### 1.2 Later-stage park list (financeiro / jurídico agents, not Julia)

`credito_aprovado`, `usa_fgts` (eligibility: 3 years of FGTS, own home, no other residential property in the city, no active SFH financing; SFH/FGTS ceiling R$2.25M since Oct/2025 per [Band](https://www.band.com.br/noticias/conselho-do-fgts-libera-uso-do-fundo-para-imoveis-de-ate-r-225-mi-202511261545)), `enquadramento` (SFH/SFI/MCMV; MCMV 2026 faixa limits *unverified against the portaria*), `consorcio_carta`, `entrada_percentual_disponivel` (financing quota of about 80% *reported, varies by bank*), `garantia_locaticia` (Lei 8.245 art. 37: caução up to 3 rents, fiança, seguro-fiança, cessão de quotas; **only one per contract**), `documentacao_pendente`, `custos_transacao_cientes` (ITBI: São Paulo city 3%, **Cotia's rate not verified**), full `bloqueios`, `composicao_familiar`, `permuta_detalhe`.

## 2 · Agent architecture (track 2)

**Already covered by the contract:** prompts in the DB; platform definition plus org specs; skill gating; deterministic qualification with a quote; post-turn detectors; an eval gate; controls and per-thread pause; a shared thread tagged per agent.

**Changes and additions** (routed to slices on 2026-10-19):
- **Prompt layer order for caching** (A-CONT): platform definition → org specs → skills index → **breakpoint** → dynamic dossier and time → recent turns. Never put timestamps or lead data in the static layers ([Anthropic, context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)).
- **Locked platform blocks** that orgs cannot override (A-CONT): AI disclosure, opt-out, escalation to a human, and real-estate-only scope. Meta's WhatsApp Business terms §4.7 (effective 15 Jan 2026) bar general-purpose AI assistants, while business-support AI is allowed ([Meta terms](https://www.facebook.com/legal/Meta-Terms-for-WhatsApp-Business-Platform), [TechCrunch](https://techcrunch.com/2025/10/18/whatssapp-changes-its-terms-to-bar-general-purpose-chatbots-from-its-platform)). CADE's measure in Brazil is still unsettled.
- **Version tuple on every assistant message** (A-CONT + A-THREAD): definition version, compiled hash, org-specs hash, skill versions.
- **Per-agent context = dossier + last N turns + latest handoff note**, not the full history. Tool calls stay private per agent ([LangChain multi-agent](https://blog.langchain.com/langgraph-multi-agent-workflows)). Clear raw tool outputs once their facts are recorded.
- **Handoff record with commitments and open questions**, written before the transfer (A-THREAD). Commitments are what gets lost between agents.
- **Opt-in and opt-out events per lead** (A-THREAD). WhatsApp policy requires opt-in before a business-initiated contact, a clear escalation path, and honouring every stop request ([policy](https://whatsappbusiness.com/pt-br/policy/)).
- **Enforcement** (A-RT): tool preconditions checked in code that return structured errors; a **retry budget** (stop after K=2 gate refusals in one turn → safe fallback plus a flagged event); refusal-rate tracking per tool. **Deterministic escalation triggers**: the lead asks for a human, an out-of-scope legal/financial topic, repeated refusals or errors, qualification complete. Add a "no human available" message.
- **Prompt-injection posture** (OWASP LLM01): tools scoped server-side to this lead and org (the model never passes ids), lead text in labelled delimiters, every quote verified as a substring of a real inbound message, lead text never reaches Maya's reports as instructions ([OWASP](https://genai.owasp.org/llmrisk/llm01-prompt-injection/), [arXiv 2506.08837](https://arxiv.org/abs/2506.08837)).
- **Evals** (A-EVAL):
  - gate on **pass^k** (k=3 for critical scenarios), not pass@1 ([Anthropic, evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents));
  - grade the **end state** (dossier, stage, handoff, messages), except hard-path rules;
  - **sharded scenarios** where information arrives piecemeal, since LLMs lose about 39% when tasks span turns ([Laban et al.](https://arxiv.org/abs/2505.06120));
  - scripted user turns for the gate, simulators only for exploration ([AURA](https://arxiv.org/abs/2505.01592));
  - online human sampling; LLM judges are advisory.
- **Policy:** **never use WhatsApp transcripts to train or fine-tune** (Meta §4.7 data clause). Eval fixtures are synthetic or anonymised.

## 3 · Real-estate content (track 3)

**Market patterns worth copying:**
- Lais (Lastro): seconds-level replies, scoped mission, handoff.
- QuintoAndar Domi: handoff package with preferred visit window and summary; takes on the agency's name.
- Ylopo: asks whether the lead already works with another agent.
- Loft: a WhatsApp qualification agent.

Vendor-reported figures are unverified ([Canaltech](https://canaltech.com.br/mercado/nova-ia-do-quintoandar-recomenda-imoveis-e-marca-visitas-pelo-whatsapp/), [Ylopo](https://www.ylopo.com/ai-agents-lead-nurture), [Portas](https://portas.com.br/noticias/loft-aposta-em-ia-para-transformar-experiencia-imobiliaria-com-avatares-e-busca-inteligente/)). The Air Canada chatbot liability case is the risk to avoid: never promise what the agency won't honour.

**Regulation:**
- **Lei 6.530/78.** Art. 3: intermediation is the corretor's work. Art. 20: publicity needs the CRECI number, written authorization, and the loteamento/incorporação registration ([Câmara](https://www2.camara.leg.br/legin/fed/lei/1970-1979/lei-6530-12-maio-1978-365766-publicacaooriginal-1-pl.html)).
- **Código de Ética (Res. COFECI 326/92).** Art. 4, II: exact data, never omit negatives. Art. 4, VI: deal guidance is the corretor's alone. Art. 6: no "anunciar capciosamente", no diverting another broker's client ([CRECISP](https://www.crecisp.gov.br/Files/notify/71f27005-77ce-47fb-8d10-3c2365681464_codigoeticaci.pdf)).
- **What this means for Julia:** she informs, triages and records. She **never negotiates, counter-offers, gives value opinions, or advises on credit, legal or tax matters**.
- **CDC (Lei 8.078/90).** Arts. 30, 31 and 37: what she says in an offer binds the agency; information must be correct and clear; no misleading omission ([Planalto](https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm)). Quote catalogue data only, and show condomínio fee and IPTU together with the price.
- **AI disclosure.** No Brazilian or Meta rule mandating it was found (PL 2338 status unverified), but it is the safe default and is a locked block (see §2).

**Prompt sections v1:**
- persona
- abertura (agency name and CRECI-J; disclose she is a virtual assistant; reference the lead's source)
- missão (about 5–8 exchanges; speed before depth)
- obrigações (tools only; consulted price shown with condomínio fee and IPTU; record everything; honour "parar")
- condução (answer first, then ask; one question; never repeat a question)
- imóveis
- identificação (owner §0.4)
- limites
- transferência
- reengajamento (24h window or a template; at most 2 touches, each offering something new; opt-out)
- identidade-e-privacidade
- fora-de-escopo

**Skills v1:**
- `qualificar-lead`: about 4 questions, adapted to what is already known
- `ofertar-imoveis`: 3 cards, ask "o que chamou atenção e o que não serviu?", feedback refines the filters, widening rules
- `intencao-de-visita`: which property, preferred day and period, who will attend; record it; the corretor confirms; then identity collection
- `bloqueios-e-objecoes`: Validar → Explorar → Evidenciar → Convidar; accept the first "no"; never discuss permuta, FGTS or credit
- `transferir-para-humano`: triggers plus the package
- `identificar-perfil`: buyer or renter vs. owner wanting to sell (→ captação) vs. other contacts

**Property card:**
- Line 1: `🏡 [Tipo] em [Condomínio/Bairro] — R$ X | aluguel R$ X + cond. R$ Y + IPTU R$ Z`
- Line 2: area · bedrooms (suites) · parking spaces
- Then 2–3 factual highlights, the link, and the reference.
- Omit missing fields and never estimate. One line comparing the 3 options, then ask for feedback.

**Similarity (*illustrative*):**
- Must-haves are hard filters.
- Price −15%/+10% of the range.
- Same region or condomínio first, then adjacent regions (defined in org specs).
- Rank by matched nice-to-haves plus the lead's likes and dislikes.
- **Widen** when there are fewer than 3 results or after 2 rejected batches. Relax one axis at a time — nice-to-haves → adjacent region → price +10% → typology — and say what was relaxed.

**Org-specs template** (each agency fills it in the app):
- agency: legal and trade name, **CRECI-J**, address, contacts, privacy URL
- team: corretores with CRECI-F, routing, hours, handoff ETA
- service areas with agency-verified notes; adjacency map
- visit policy, commission-disclosure policy, partners, tone, FAQ
- Granja Viana starter facts (Raposo Tavares km 21–29, Rodoanel as alternative, schools and landmarks) **to be verified by the agency**. **No safety claims.**

## 4 · KPIs (for the SW reports and, later, Maya)

| KPI | Definition |
|---|---|
| Speed-to-lead (agent) | Agent first response; the human's response after handoff is the KPI that matters ([HBR 2011](https://hbr.org/2011/03/the-short-life-of-online-sales-leads): ~7× more likely to qualify within 1h) |
| Response rate | — |
| Qualification rate | — |
| Time- and turns-to-qualify | — |
| Handoff rate by reason | — |
| Broker acceptance SLA | — |
| Funnel | visit → proposal → contract, attributed to the agent version |
| Re-engagement success | — |
| Containment | Confirmed vs. assumed, Intercom-style |
| Cost per qualified lead | — |
| Tool-error and gate-refusal rate | — |
| Conformance-violation rate | — |
| Out-of-catalog rate | Property claims not returned by a tool |
| Re-ask rate | Asked a fact already in the dossier |
| Escalation-trigger misses | — |

**Maya's daily per-agent score** uses the deterministic ones only: conformance, refusals and errors, out-of-catalog, re-ask, handoff by reason, containment, qualification rate and time, cost per qualified lead, escalation misses. Funnel and SLA go in the owner report, not in the agent score.

**Event schema:** align with the OpenTelemetry GenAI conventions ([OTel](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans)), with the conversation id set to the thread id.

## 5 · WhatsApp economics and cadence

- Free-form messages are allowed only within 24h of the lead's last message; after that, templates only. Per-message billing since July 2025.
- **Click-to-WhatsApp ad leads get a 72h free window** if the business replies within 24h ([SleekFlow](https://help.sleekflow.io/en_US/understanding-click-to-whatsapp-ads-ctwa-and-the-72-hour-free-window)), so finish the basics within it.
- Meta caps marketing templates per user (adaptive).
- Reply buttons max out at **3**, which matches "3 at a time" ([Bird](https://bird.com/docs/guides/whatsapp/message-types/interactive)). Choice overload depends on context and is stronger for complex options ([Chernev 2015](https://www.kellogg.northwestern.edu/academics-research/research/detail/2015/when-product-assortment-leads-to-choice-overload-a-conceptual/)).
- **Transport caveat:** today SW uses **WAHA** (an unofficial client). Its ToS and ban risk were not researched. The Cloud API path stays the target once Meta verification is done.

## 6 · Conflicts with research → owner decision wins

| Topic | Research | Owner decision (binding) | Safeguard applied |
|---|---|---|---|
| CPF/RG in the first moment | Don't collect in the first stage (minimisation; TJSC ruling on generic legítimo interesse) | Collect name, number, email, RG and CPF **before the visit** | Asked only after visit intent, with the purpose stated (registering the visit and condomínio entry); legal basis art. 7 V (pre-contractual, at the lead's request); validated; **encrypted at rest**, never in quotes or LLM context, masked display, audited decrypt; retention aligned; lgpd_flag filed |
| Handoff target | Broker directly | The **owner** (human operator), who redirects to the broker | Handoff record targets the org owner by default, configurable later |
| Rules in code vs. prompt | Code-enforced gates | "All specs in her prompt/specs in the agents app; no code rules" | The code is a generic engine; every rule, threshold, criterion and text is a DB row editable in the app and rendered into the compiled prompt |

## 7 · Open uncertainties

- Cotia's ITBI rate
- MCMV 2026 ceilings, checked against the portaria
- Whether CRECI must appear in 1:1 chats (cautious default: include it)
- PL 2338's final text
- Outcome of the CADE case
- WAHA ToS risk
- All illustrative weights and thresholds
