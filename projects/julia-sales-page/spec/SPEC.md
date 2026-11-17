# Julia sales page — product spec (draft, recommendation)

> **Author:** product-manager · **Date:** 2026-11-17 · **Requested by:** owner (2026-11-17), via tech-lead
> **Status:** DRAFT. Every scope, price and priority call below is the owner's; this file recommends.
> **Method:** `KB § PATTERNS/product/sales-page-anatomy.md` (branch `feat/kb-sales-page-anatomy`, not yet on dev) §1 sequence, §3 legal floor, §4 events · `KB § PATTERNS/product/product-management-canon.md` §3-§8.
> **Products touched:** `agents` (Julia's brain) and `social-wiring` (transport + CRM). Both are `ativo` + `live` (`deploy/fleet/build-scope.txt`, refresh 2026-11-12), so prod rules apply. No asleep product is in scope.

---

## 0 · What Julia can honestly claim today (evidence sweep, read before any copy)

Codebase is the source of truth. Each line names where it was verified. "Shipped" means the mechanism exists on dev/prod code. It does NOT mean it is switched on for a given client; that is live state I could not read (see §0.3).

### 0.1 Shipped capabilities (claimable, with the evidence)

| # | Capability | Evidence |
|---|---|---|
| C1 | Answers leads who write on the company's WhatsApp number | `KB 02-LANDSCAPE.md` Social Wiring + Agentes rows; `products/agents/projects/julia-v2/CONTRACT.md` §5.2 (turn decision table) |
| C2 | Starts the conversation with a NEW incoming lead (e.g. Meta lead-form lead), never mass-messages the old base | memory `project-julia-golive-eligibility` (owner rule 2026-11-05); MCP tool `noctus.sw.ad_lead_intake` |
| C3 | Scores the lead with fixed rules: same lead, same score (deterministic engine, versioned standard `imob-lead` v1) | CONTRACT §3.2, §4.3; existing landing bullet "o mesmo lead recebe sempre a mesma nota" (`products/agents/frontend/src/pages/Landing.tsx:147`) |
| C4 | Qualifies on real-estate criteria: buy/rent, decision deadline, payment form (à vista, financiamento, FGTS, permuta, consórcio), approved credit, blockers, property type, price range, regions, features, life profile | CONTRACT §4.3 |
| C5 | Offers up to 3 properties per round from the company's own catalogue, never repeats one, says so when none is left and offers a human | CONTRACT §12.6; catalogue live from Vista CRM or the Social Wiring mirror, per org (§12.7) |
| C6 | Does NOT book visits: collects the lead's available days/times and says a person will continue | CONTRACT §12 (owner rule 2026-11-03) |
| C7 | Hands off to the team with a written report (summary, profile, properties offered + reaction, visit availability, documents received as flags) sent by WhatsApp to a team member and saved on the lead card | CONTRACT §12.4, §12.5 |
| C8 | Warns the team when a lead is unhappy or she made a mistake | CONTRACT §12.3 (`sinalizar_alerta`); landing bullet "Quando um cliente reclama, avisa a equipe" |
| C9 | Controls: ligado / drenando / desligado per company; platform-wide kill switch; evaluation mode (answers only allow-listed people) | CONTRACT §5.1, §12.1, §12.12; landing `#controle` |
| C10 | One conversation history per lead across agents and humans; human takeover pauses her | CONTRACT §5.1, §6; landing "Uma conversa por lead" |
| C11 | Lead name and contact encrypted at rest; consent recorded in the conversation | `02-LANDSCAPE.md` Agentes row; landing `#controle` |
| C12 | Abuse limits (floods, bots, spend per day) and replies that do not reveal internal instructions | CONTRACT §5.2a; `KB § PATTERNS/security/audits/julia-2026-11.md` |
| C13 | Follow-ups to a silent lead capped at 2 in a row | CONTRACT §5.2 (owner 2026-11-10) |
| C14 | Collects CPF (required for a visit) and accepts ID document photos, which feed the client card | CONTRACT §12.8 |

### 0.2 Planned or in progress (NEVER in page copy as current)

| # | Item | Evidence |
|---|---|---|
| P1 | SDR for other markets (a market-agnostic `sdr-base` template) | memory `project-agent-templates-from-julia`: templates in draft, the publish chain deferred; memory `reminder-golive-assistant-julia-agentebase` (2026-11-13): `agente-base`, `sdr-base` and Julia have 0 published Studio versions of the layered design |
| P2 | Julia's layered (BASE → SDR → Julia) version published | same memory; owner order: agente-base loop → sdr-base loop → Julia |
| P3 | Behaviour quality at 90-95% stable across runs | memory `julia-quality-target-90`: score 0.979 (11-05) → 0.778 (11-08); target 90-95%, publish floor 0.80 |
| P4 | Onboarding a SECOND company on its own isolated WhatsApp line | `julia-2026-11.md` row "Shared-session takeover: OPEN (structural; blocker before a 2nd org)"; `deploy/fleet/waha-instances.yml` lists only `nosnolimiar` and `assistant`, no Julia/social-wiring line |
| P5 | Hand-off note to an org fallback number | memory `project-agent-templates-from-julia` round 12: "Sending the actual notification … is NOT built yet" |
| P6 | Self-serve agent creation by the customer (creator chat) | same memory: creator deferred |
| P7 | Funnel instrumentation on landing organs | `seed/lib/frontend/src/marketing/`: no `section_viewed` / `cta_clicked` / UTM capture (grep, 0 hits) |

### 0.3 Live state and numbers I could NOT verify (all page numbers are `[AMOSTRA — needs owner data]`)

- Whether Julia is out of evaluation mode in prod today, and for which org(s). Only one real-estate client org is referenced in memory ("One"); its name on Julia (`nome_organizacao`) is an open owner question (memory 2026-11-13).
- Leads handled, response time, qualification rate, lead→visit, revenue influenced: no published figure exists. The data that would compute some of them exists but is platform-admin only: `agents.turn_metrics` (turn_ms p50/p95, handoffs, cost; CONTRACT §14) and the `social_wiring.julia_*` tables (`julia_contatos`, `julia_relatorios`, `julia_leads`, migrations 297-314). Semantic memory search was unavailable this session (OpenAI quota exhausted), so a decision with a number may exist that I did not find.
- No testimonial, case study or client permission to use a name is on file anywhere I looked.

### 0.4 Pricing state

- **No Julia or agents plan exists in code.** Core ships generic seed plans from 2025 (`products/core/backend/migrations/001_noctusai_core.sql:463-468`: Free R$0, Pro R$99, Enterprise R$299). They are not Julia's and must not be shown as her price.
- **Checkout infrastructure exists in core:** `plans` + `plan_prices` (integer cents, monthly/yearly) + Stripe/Asaas subscriptions + webhook inbox (`050_billing_gateways.sql`), with automations and gateways OFF by default. The live DB rows are unknown.
- **Owner billing decision (memory `project-usage-billing-credits-model`, 2026-10-29):** plan allowance + prepaid credit wallet (PIX/boleto) as the default, plus a bring-your-own-key tier; per-outcome pricing not chosen. So the page's price section depends on a plan shape the owner has not set.

### 0.5 Two conflicts the page must not paper over

1. **Opt-out.** `KB § PATTERNS/legal/consumer-ecommerce.md` §8 says opt-out "must work deterministically, without the model deciding". The owner decided on 2026-11-08 that opt-out is Julia's judgement (CONTRACT §5.2, "it shouldn't be deterministic, Julia judges"). The page must not promise "parou, parou garantido" until `legal-advisor` and `agents-security` rule on this. → owner question D9.
2. **WhatsApp channel.** Julia's lines run on WAHA (WhatsApp Web automation), not the official WhatsApp Business Cloud API (`waha-instances.yml`; ban risk rated PARTIAL in `julia-2026-11.md`). No "API oficial do WhatsApp" or "sem risco de bloqueio" claim.

---

## 1 · Problem and job

**Job statement (buyer's words, draft to validate with the owner):**
> "Quando um lead chega no WhatsApp da imobiliária à noite, no fim de semana ou enquanto meus corretores estão em visita, eu quero que alguém responda na hora, entenda o que a pessoa procura e me entregue só quem está pronto, para que meus corretores parem de perder tempo com curioso e eu pare de perder cliente para quem respondeu primeiro."

- **Situation:** small or mid real-estate agency, leads arriving from portals, Meta ads and the site into one WhatsApp number; the owner or a small team answers between visits.
- **Motivation:** speed of first answer, filtering, not losing leads, not hiring an SDR.
- **Expected outcome:** every lead answered, qualified leads handed to a broker with context, the owner keeps control.
- **No solution disguised as a need:** the need is "every lead answered and filtered"; "an AI agent" is our answer, not their need.

**Our angle (from the anatomy doc §2):** we sell the operating system done for you, not a course that teaches you to build it. The honest form of "done for you" today: onboarding is operator-run (we provision the WhatsApp line, set the catalogue source, write the company's specs, run evaluation mode with the owner first). That matches the code (line provisioning is platform-admin, `noctus.dev.waha_instance`; Vista key per org, CONTRACT §12.7) but the onboarding steps and their duration are not written down anywhere as a customer promise → owner question D11.

**Stories**
- S1. As a real-estate agency owner, I want to understand in under 2 minutes what Julia does and does not do, so I can judge if it fits my agency.
- S2. As a non-technical owner, I want to know who sets it up and how long it takes, so I know whether I have the time.
- S3. As a cautious buyer, I want to see the price, the legal 7 days and how to cancel, so I can buy without fear.
- S4. As a buyer with doubts, I want to talk to a person on WhatsApp from the page, so I can ask before paying.
- S5. As NoctusAI, we want every section and CTA measured, so we know where readers leave and which promise converts.

**ICP**
- **Supported today:** real-estate agencies (imobiliárias) and independent brokers that sell or rent residential property, take leads on WhatsApp, and keep listings in Vista CRM or are willing to keep them in Social Wiring. Evidence: the only published qualification standard is `imob-lead` (C3, C4) and the offer tool reads a property catalogue (C5).
- **Not supported today:** any other vertical. The market-agnostic SDR is a draft template (P1). Copy must say "para imobiliárias"; other markets at most get a waitlist ("Lista de espera"), the catalog convention already approved for the site (memory `noc-site-funnel-decisions-2026-11`). → owner question D6.
- **Buyer objections the page must answer (from the anatomy doc):** "não sou técnico", "não tenho tempo", "funciona pro meu mercado?", plus "e se ela falar besteira com meu cliente?" (answered by evaluation mode, controls, alerts) and "vou perder o controle?" (answered by ligado/drenando/desligado + human takeover).

**Success metric (target side; data side is the architect's, `measurement-by-design.md` §2)**

| Metric | Definition | Baseline | Target | Read date |
|---|---|---|---|---|
| M1 CTA→checkout rate | sessions with ≥1 `checkout_started` ÷ sessions with ≥1 `cta_clicked` | unknown (no page, no events) | owner sets (D1 batch); I recommend fixing it after 2 weeks of baseline, not before | 30 days after launch, then 60 |
| M2 Checkout completion | `checkout_completed` ÷ `checkout_started` | unknown | owner sets | 30 days |
| M3 7-day refund rate (honesty metric) | `refund_requested` within 7 days ÷ `checkout_completed` | unknown | owner sets; a rising rate means the page over-promises | 30 and 60 days |
| M4 WhatsApp handoff → qualified conversation | `whatsapp_handoff` that reach a qualified stage ÷ all `whatsapp_handoff` | unknown | owner sets | 30 days |

If the owner chooses "fale com um especialista" instead of self-serve checkout (D2), M1/M2 are replaced by CTA→`whatsapp_handoff` and handoff→paid, and the checkout events still apply to whatever payment link closes the sale. `product-analyst` reads and judges.

---

## 2 · Section-by-section table (anatomy §1, 19 sections)

Organs: `@noctusai/lib/marketing` exports `Hero`, `FeatureGrid`, `Steps`, `CtaBand`, `Faq`, `LeadCaptureForm`, `LandingFooter`, `ProductCatalogGrid`, `LandingNav` (verified, `seed/lib/frontend/src/marketing/index.ts`). Gaps are composed from primitives inside the product under a declared named seam until a second page needs them (anatomy §1, DRY rule). Events: every section emits `section_viewed{section_id}`; every CTA emits `cta_clicked{cta_id, section_id}` (only the extra events are listed).

Copy below is DIRECTION for `product-designer`, not final copy. Tone follows the existing landing: short, concrete, "sob o seu controle", no hype.

| # | Section | Job | Draft pt-BR headline / copy direction | CTA (first person) | Organ | Extra event | Evidence for each claim |
|---|---|---|---|---|---|---|---|
| 1 | Hero | promise + pre-empt top 3 objections | H: "A Julia responde, qualifica e passa para o seu corretor só quem está pronto." Sub: "Atendimento de leads no WhatsApp da sua imobiliária, configurado por nós. Mesmo que você não seja técnico e não tenha tempo." No numeric promise until owner data exists; `stats` slot empty or `[AMOSTRA]` labelled like the existing hero panel | "Quero a Julia na minha imobiliária" · "Ver como ela trabalha" | `Hero` (media slot: illustrative conversation labelled "Amostra") | — | C1, C3, C7; "configurado por nós" pending D11 |
| 2 | Pain | cost of standing still | "Lead que espera, esfria. Enquanto seu corretor está em visita, o lead já está falando com outra imobiliária." No statistic unless sourced | "Quero parar de perder lead" | `FeatureGrid` text variant | — | generic framing, no number; any statistic needs a cited source (CDC 38) |
| 3 | Symptom mirror | reader feels seen | Two lists: "Se você está cansado de…" (responder lead à meia-noite; corretor perdendo tempo com curioso; não saber quem está pronto) / "Provavelmente você também já…" (perdeu um cliente porque respondeu tarde; contratou alguém para atender e não deu certo) | "Isso é comigo" | **gap**: checklist organ (compose from primitives) | — | buyer framing; owner to confirm with real client pains (D10) |
| 4 | Origin story | "we were where you are" | OPEN. Only if the owner provides a true story (e.g. Julia was built inside a real agency's operation) | — | **gap**: story/bio organ | — | `[OPEN — D10]`; do not invent |
| 5 | Turning point | one named reframe | "A Julia não é um chatbot de menu. É uma pessoa da equipe que segue as regras da sua imobiliária e sabe a hora de chamar um corretor." | "Quero ver a Julia trabalhando" | `CtaBand` | — | C3, C7, C9; existing landing "sabe a hora de chamar uma pessoa" |
| 6 | Authority | verifiable track record | OPEN. Candidate true facts: "em produção no WhatsApp de imobiliária desde nov/2026" (needs owner confirmation of date and client permission); security posture (encrypted lead data, abuse limits). No logo strip without written permission | — | `Hero` `stats` / logo strip **gap** | — | `[AMOSTRA — needs owner data]`; go-live 2026-11-04 per `julia-2026-11.md`; client name needs permission (D5) |
| 7 | Named mechanism | the method as a 3-part system | Proposal: "Atende · Qualifica · Entrega". Atende: responde na hora e puxa conversa com lead novo de anúncio. Qualifica: perguntas da imobiliária, nota por regras fixas. Entrega: relatório para o corretor e imóveis já oferecidos | "Quero esse atendimento" | `Steps` or `FeatureGrid columns={3}` | — | C1-C2 / C3-C4 / C5, C7 |
| 8 | Proof | client results | OPEN. No case, screenshot or testimonial on file. Options in D5. Until then the section is cut, not faked | — | **gap**: proof carousel | — | `[AMOSTRA — needs owner data]` |
| 9 | Objection triplet | answer "mas eu…" inline | "Não sou técnico" → nós configuramos e testamos com você antes de abrir. "Não tenho tempo" → você só aprova o teste; depois só lê os relatórios. "E se ela errar com meu cliente?" → modo de avaliação, alerta quando o cliente reclama, você desliga na hora | "Quero tirar minhas dúvidas no WhatsApp" | `FeatureGrid` | `whatsapp_handoff` on that CTA | C8, C9; onboarding steps pending D11 |
| 10 | How it works | each pillar expanded | Bullets per pillar, only from C1-C14: nota igual para o mesmo lead; até 3 imóveis por vez, sem repetir; nunca marca visita sozinha, pega os horários do cliente e passa ao corretor; pede CPF quando há visita; conversa única por lead; para de insistir após 2 tentativas sem resposta | "Quero a Julia na minha imobiliária" | `FeatureGrid` `bullets` | — | C3-C7, C10, C13, C14 |
| 11 | Inside view | what the buyer gets access to | Screens: the agent controls (ligado/drenando/desligado), the lead card with Julia's report, conversations. Screenshots with sample data labelled "Amostra" | "Quero ver o painel" | `FeatureGrid` / screenshots | — | C7, C9, C10; SW `/julia/*` pages (`02-LANDSCAPE.md`) |
| 12 | Ecosystem | not a lone bot, a whole system | "A Julia trabalha dentro do Social Wiring: leads, funil, imóveis e contratos no mesmo lugar." Only if the offer includes Social Wiring (D8) | "Quero o sistema completo" | `ProductCatalogGrid` / `FeatureGrid` | — | `02-LANDSCAPE.md` Social Wiring row; offer scope pending D8 |
| 13 | Value stack | each included item with its value | OPEN until D1. Items that are true: setup do número, configuração das regras da imobiliária, período de avaliação, relatórios, suporte. Values in R$ only if the owner sets them and we can prove them | — | **gap**: offer-stack organ | — | `[OPEN — D1]` |
| 14 | Price | real price, installments, per-day framing | OPEN until D1. No "de/por" (no price history exists, §3 floor). Per-day framing only from the real price | "Quero assinar" or "Quero falar com um especialista" (D2) | **gap**: pricing/offer organ, links to core checkout (`plans`/`plan_prices`) | `checkout_started` | §0.4; no Julia plan in code |
| 15 | Who's behind it | bio aligned with reader | OPEN (D10): NoctusAI as the company, founder bio, or skip | — | **gap**: bio organ | — | `[OPEN — D10]` |
| 16 | Guarantee | risk reversal | "Você tem 7 dias para desistir, por lei (CDC art. 49), com reembolso integral." Anything longer labelled "garantia contratual adicional" (D3) | "Testar sem risco" | **gap**: guarantee badge | — | anatomy §3; `consumer-ecommerce.md` §3 |
| 17 | FAQ | ~12 objections, buyer's words | See §3 below | "Ainda tenho dúvida: falar no WhatsApp" | `Faq` | `whatsapp_handoff` | §3 |
| 18 | Future pacing | stand still vs adopt | A: "Daqui a 3 meses, os mesmos leads sem resposta à noite." B: "Daqui a 3 meses, cada lead respondido e seu corretor recebendo só quem quer visitar." No numeric outcome | "Quero o cenário B" | `CtaBand variant="inverse"` | — | framing only, no number |
| 19 | Footer recap | price + guarantee + WhatsApp handoff + supplier identity | Price (D1), 7 dias por lei, WhatsApp button with opt-in, supplier name + CNPJ + address + contact (Decreto 7.962 art. 2, D4), legal links to seed `/consent/*` | "Falar no WhatsApp" | `LandingFooter` + `LeadCaptureForm` (opt-in) | `whatsapp_handoff` | existing landing footer; `consumer-ecommerce.md` §2 |

**Things the page reuses from the existing agents landing (and must not contradict):** "sob o seu controle", the three control states, evaluation mode, "uma conversa por lead", encrypted lead data, the illustrative panel labelled "Amostra", the `LeadCaptureForm` with `consentSubject` and a human reply "em horário comercial" (`Landing.tsx:193-208`). The landing presents Julia and Bia together; this page is Julia only.

**Who answers the WhatsApp handoff:** a person, as the current landing says. Julia herself should NOT be the page's SDR yet: her only standard qualifies property buyers, not agencies buying software (C4). A NoctusAI-sales instance would need its own standard (planned, depends on P1). → D12.

---

## 3 · FAQ (buyer's words, answered only from verified facts)

| # | Question | Answer direction | Evidence / gap |
|---|---|---|---|
| F1 | "Eu não sou técnico. Vou conseguir usar?" | Você não configura nada técnico. Nós ligamos o número, escrevemos as regras da sua imobiliária com você e testamos antes de abrir. No dia a dia você liga, pausa ou desliga com um botão. | C9; setup ownership pending D11 |
| F2 | "Não tenho tempo. Quanto do meu tempo isso toma?" | No começo, o tempo de testar a Julia em modo de avaliação e aprovar. Depois, ler os relatórios que ela manda quando um lead está pronto. Duration `[OPEN — D11]` | C7, C9 |
| F3 | "Funciona pro meu mercado?" | Hoje a Julia é feita para imobiliárias e corretores de imóveis residenciais (compra e aluguel). Outros mercados: lista de espera. | C4; P1; D6 |
| F4 | "E se ela falar besteira com meu cliente?" | Antes de abrir, ela só conversa com quem você liberar. Ela segue regras definidas, avisa a equipe quando um cliente reclama, e você pode pausar uma conversa ou desligá-la na hora. | C8, C9, C10. Do NOT claim "nunca erra" (P3) |
| F5 | "Ela marca visita sozinha?" | Não. Ela pergunta os dias e horários que o cliente pode e passa para o corretor, que confirma. | C6 |
| F6 | "Ela mostra imóveis do meu estoque?" | Sim, até 3 por vez, sem repetir, buscando no seu Vista CRM ou no catálogo do Social Wiring. | C5; Vista dependency D8 |
| F7 | "E os leads antigos da minha base, ela vai sair mandando mensagem?" | Não. Ela responde quem escrever depois que for ligada e puxa conversa só com lead novo que chega (por exemplo, de formulário de anúncio). | C2 |
| F8 | "Meu corretor perde o controle da conversa?" | Não. Quando uma pessoa da equipe assume, a Julia para; o histórico continua o mesmo. | C10 |
| F9 | "Os dados dos meus clientes ficam seguros? E a LGPD?" | Nome e contato do lead ficam criptografados no banco; o consentimento fica registrado na conversa; há limites contra abuso. Details in the privacy policy. | C11, C12. Controller/operator wording → `legal-advisor` (`consumer-ecommerce.md` §7: no "operador" section yet) |
| F10 | "Quanto custa? Tem fidelidade?" | `[OPEN — D1]`. Must state price, cycle, installments, and how to cancel. | §0.4 |
| F11 | "E se não funcionar para mim?" | 7 dias para desistir por lei, com reembolso integral, pelo mesmo canal da compra. Anything beyond: D3. | `consumer-ecommerce.md` §3 |
| F12 | "Por que vocês e não um curso ou um chatbot qualquer?" | Porque entregamos funcionando, não ensinamos a montar: número, regras, testes e relatórios configurados por nós, com você no controle. | anatomy §2 angle; C1-C14 |
| F13 | "Usa o WhatsApp que eu já tenho?" | `[OPEN — needs devops/owner]`: today lines are provisioned per number on WAHA by our team; whether the client's existing number is reused, and the ban-risk wording, must be decided before this answer exists. Never "API oficial". | §0.5 item 2; P4 |

---

## 4 · Acceptance criteria (numbered; each needs a test or an owner review)

**Content honesty**
- **AC-1** Given the published page, when any capability is stated, then it maps to a row C1-C14 of §0.1; no P1-P7 item appears as current. *(Layer: owner/legal review against this table; checklist in the PR.)*
- **AC-2** Given any number on the page (leads, response time, conversion, clients, savings), when the page is published, then the number has a source on file (query or table + date) recorded in the page's evidence log, else the number is absent. No `[AMOSTRA]` value ships unlabelled. *(Review + a content test that fails on the literal `AMOSTRA` outside an element labelled "Amostra".)*
- **AC-3** Given the page states the vertical, when read, then it says Julia serves imobiliárias/corretores, and any other market is offered only a waitlist. *(Review.)*
- **AC-4** Given the page mentions WhatsApp, then it does not claim the official WhatsApp Business API, zero ban risk, or a guaranteed automatic stop on opt-out, until D9 and F13 are resolved. *(Review.)*

**CDC floor (anatomy §3; `consumer-ecommerce.md` §2, §3, §5)**
- **AC-5** Given a price is shown with a strike-through "de", when published, then that "de" equals a price actually charged for this plan, provable from `plan_prices` history; with no history, no strike-through is rendered. *(Unit test on the price component: no `from` value without a history reference.)*
- **AC-6** Given the guarantee section, then it states "7 dias para desistir, por lei (CDC art. 49)" with full refund, and any longer period is labelled contractual. *(Content test + legal review.)*
- **AC-7** Given a deadline, bonus or scarcity claim, when its date passes, then the claim disappears or the offer ends; no deadline is computed relative to the visitor's session. *(Test: an expired deadline renders nothing.)*
- **AC-8** Given the page and the checkout, then supplier name, CNPJ/CPF, address, e-mail and a service channel are visible before purchase (Decreto 7.962 art. 2 I-II), and a contract summary is shown before payment (art. 4 I). *(e2e.)*
- **AC-9** Given a buyer who wants to withdraw, then the withdrawal channel is the same tool used to buy, and the request is acknowledged immediately (Decreto 7.962 art. 5 §1, §4). *(e2e on the checkout path chosen in D2.)*
- **AC-10** Given a testimonial, client name, logo or partner name, then written permission is on file before publish. *(Owner review.)*

**WhatsApp opt-in**
- **AC-11** Given a visitor clicks a WhatsApp CTA or submits the lead form, when no explicit opt-in checkbox (unchecked by default) is ticked, then no outbound WhatsApp message is sent to that number, and the consent text version is stored with the lead (`LeadCaptureForm` → core `/api/website/leads` already sends `consent_marketing` + `consent_text_version`). *(Contract test on the lead payload; e2e on the default-unchecked box.)*
- **AC-12** Given a lead who asks to stop, then no further marketing message is sent; the mechanism that guarantees it is the one `legal-advisor` approves in D9. *(Test owned by agents-security once D9 is decided.)*

**Funnel events (anatomy §4; data shape is the architect's)**
- **AC-13** Given a visitor scrolls a section of §2 into view, then exactly one `section_viewed{section_id}` is recorded per section per session, with the 19 ids of §2. *(e2e.)*
- **AC-14** Given a visitor clicks any CTA, then `cta_clicked{cta_id, section_id}` is recorded, with UTM parameters of the landing URL carried. *(e2e.)*
- **AC-15** Given a checkout is opened / paid / refunded, then `checkout_started`, `checkout_completed` and `refund_requested` are recorded with an outcome enum, and `refund_requested` carries days since purchase. *(Contract test on the billing webhook path.)*
- **AC-16** Given a WhatsApp handoff, then `whatsapp_handoff` is recorded and the resulting lead in the leads organ carries the UTM attribution. *(Contract test.)*
- **AC-17** Given 30 days after launch, then `product-analyst` can compute M1-M4 from the recorded events alone, with no manual join. *(Judged by product-analyst at the read date.)*

**Go-live gate (recommendation, owner decides in D8 batch)**
- **AC-18** Given the page would send buyers to onboarding, when it is published, then Julia's version a new client receives is a published Studio version, and a second company can be onboarded on its own WhatsApp line (P4 closed). Otherwise the page runs as "fale com um especialista" / waitlist only. *(Owner review + `agents-security` sign-off.)*

---

## 5 · Data categories touched

Categories only; the five questions (basis, minimization, destination, retention, tenant isolation) are in `KB § PATTERNS/security/lgpd.md` §3. `security` and `legal-advisor` own the handling.

- Visitor behaviour: section views, CTA clicks, UTM parameters, a session identifier (cookie or similar).
- Lead capture form: name, WhatsApp phone, e-mail, company, free-text message, marketing consent flag + consent text version.
- WhatsApp conversation after handoff: phone, message content, whatever the buyer volunteers (may include third-party data about their own clients).
- Checkout and billing: buyer name, CPF or CNPJ, billing address, payment method data (held by the gateway), invoice data.
- Withdrawal / refund requests and their acknowledgements.
- Marketing opt-in / opt-out records (`consumer-ecommerce.md` §8).

Note for legal: once the buyer becomes a client, their LEADS' data flows through Julia with the client as controller and NoctusAI as operator; the privacy texts do not yet have an operator section (`consumer-ecommerce.md` §7).

---

## 6 · Open owner decisions (batches of at most four; tech-lead relays)

**Decided 2026-11-17 (owner, in chat)**
- **D2 → (b) "fale com um especialista".** No self-serve checkout until the multi-org blocker (P4) closes.
- **D1 → (b) setup + monthly.** Values are still open. The owner added that **onboarding is done by our chatbot**: it interviews the client about their business and context, as a person designing their assistant would, and builds the client's contextualised Julia on top of the sdr-base layer. This follows the model of Lais's base SDR plus its business-specific settings ("Minha Lais"). The reference study is in progress (`_private-studies/lais/specs/business-context-2026-11.md` → onboarding interview checklist). New scope: an onboarding-chatbot spec (separate, after the study).
- **D3 → (a) only the legal 7 days**, stated as the law. This may change later.
- **D7 → all three surfaces, ONE canonical page.** `/julia` on agents is canonical: full sequence, the specialist CTA, funnel events, and it links to the client's control panel. The core site shows a `ProductCatalogGrid` card linking to `/julia`. The Social Wiring landing gets a "your hub comes with an AI SDR" section linking to `/julia`, which is the honest bundle while Julia is real-estate-only and runs on Social Wiring data. No duplicated full copy.

Still open: D1 values · D4 · D5 · D6 · D8 · D9 · D10 · D11 (shaped by the onboarding chatbot) · D12.

**Batch A — the offer**
1. **D1 Price and plan.** No Julia plan exists in code; core has the billing machinery (Stripe/Asaas, `plan_prices`). Options: (a) monthly subscription with a credit allowance + prepaid top-up (your 2026-10-29 billing model); (b) one-off setup fee + monthly; (c) paid pilot (30-60 days, target agreed before start) then monthly; (d) no public price, quote after a conversation. Which, and at what values?
2. **D2 Purchase path.** (a) self-serve checkout on the page; (b) "fale com um especialista" on WhatsApp, a person closes and sends a payment link; (c) hybrid: checkout for the pilot, specialist for the full plan. Recommendation: (b) or (c) until P4 is closed, because each new client needs operator setup and an isolated line.
3. **D3 Guarantee beyond the legal 7 days.** (a) none, only the legal 7 days; (b) 30-day contractual guarantee; (c) pilot guarantee tied to an agreed target (e.g. response to every lead). Note that (c) needs a measurable baseline per client.
4. **D4 Who sells.** Decreto 7.962 requires the supplier's name and CNPJ/CPF on the page. (a) NoctusAI's legal entity (which CNPJ?); (b) another entity. `legal-advisor` reviews.

**Batch B — proof and scope**
5. **D5 Results and testimonials.** Nothing is on file. (a) use the current real-estate client (name, numbers, quote) with written permission; (b) publish anonymised aggregates from `julia_*` / `turn_metrics` after you approve the query and the period; (c) no proof section until a pilot produces a before/after. Which, and who asks the client?
6. **D6 Vertical scope.** (a) real estate only; (b) real estate + "Lista de espera" for other markets; (c) generic SDR for any market (not recommended: P1 is unpublished).
7. **D7 Where the page lives.** (a) a new route on agents, e.g. `agents.noctusai.com/julia`, linked from the current landing; (b) replace the current agents landing; (c) on noctusai.com (core site) as a product page; (d) on the Social Wiring landing. `product-architect` advises.
8. **D8 What is sold.** (a) Julia alone (needs a catalogue source: Vista key or Social Wiring); (b) Julia + Social Wiring CRM as one package; (c) both as tiers. Also: do we launch before P2/P4 close (with D2 = specialist), or wait?

**Batch C — trust and story**
9. **D9 Opt-out.** Your 2026-11-08 decision makes opt-out Julia's judgement; the consumer-law canon asks for a deterministic stop. (a) keep as is and say nothing on the page about stop guarantees; (b) restore a deterministic stop floor before selling; (c) ask `legal-advisor` + `agents-security` first and follow their recommendation.
10. **D10 Story and bio (sections 3, 4, 15).** (a) a true founder/company story you provide; (b) NoctusAI company bio only; (c) skip these sections. If (a), which real client pains can we quote?
11. **D11 Onboarding promise.** What do we commit to: who does each setup step (line, catalogue, rules, evaluation), and in how many days? (a) we do everything, N days; (b) shared, with a checklist for the client; (c) no deadline on the page.
12. **D12 Page's WhatsApp handoff.** (a) a person answers (as today's landing); (b) a NoctusAI-sales Julia instance with its own qualification standard (planned work, needs P1); (c) a person now, Julia later.

---

## 7 · Scope in / out, creep log, hand-offs

**In scope:** one checkout-bound sales page for Julia (real estate), its copy direction, section map, FAQ, events and acceptance criteria; the legal floor; the success metrics.

**Out of scope (named):** building the gap organs as seed organs (only on second use); a NoctusAI-sales Julia instance (D12); other-vertical pages; the credit wallet and plan creation in core (billing work, after D1); fixing P1-P5 (the agents/Julia roadmap owns them); Bia.

**Scope-creep log**

| Date | Request | Effect | Trade-off named |
|---|---|---|---|
| 2026-11-17 | (none yet) | — | — |

Watch item: "and make Julia answer the page's leads" would pull a new qualification standard and instance into this project (D12). Recommended: a deferred sub-feature, not this page.

**Hand-offs**
- **`product-designer`:** final pt-BR copy and mockup from §2/§3, reusing the existing landing's voice and brand scope; gap sections composed from primitives under a declared seam.
- **`legal-advisor`:** §0.5 conflicts (opt-out, WhatsApp channel claims), CDC applicability to a business buyer (`consumer-ecommerce.md` §1: B2B SaaS may be civil/commercial, CC 421-A; recommendation is to honour the 7 days regardless), Decreto 7.962 art. 2/4/5 items, price-display rules (Lei 10.962/2004, Decreto 5.903/2006, not yet in the KB), testimonial permission, the operator section of the privacy texts.
- **`product-architect`:** where the page lives (D7), the offer/tier shape (D8), the 7 organ gaps, and the funnel-event gap in the marketing organs (P7) as a seed seam, not a per-page hack.
- **`architect`:** the data side of M1-M4 (event tables, enums, UTM carry into the leads organ), per measurement-by-design.
- **`agents-security`:** AC-12, AC-18, P4 status before any "sign up now" path.
- **tech-lead:** contract and slices once Batch A is answered.

---

## Sources

Read this session: `.claude/worktrees/kb-sales-page-anatomy/KNOWLEDGE-BASE/CONTEXT/PATTERNS/product/sales-page-anatomy.md` · `KNOWLEDGE-BASE/CONTEXT/PATTERNS/product/product-management-canon.md` · `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md` (rows 19, 24) · `KNOWLEDGE-BASE/CONTEXT/PATTERNS/legal/consumer-ecommerce.md` §1-§9 · `KNOWLEDGE-BASE/CONTEXT/PATTERNS/security/audits/julia-2026-11.md` · `products/agents/projects/julia-v2/CONTRACT.md` §4.3, §5, §12, §14 · `products/agents/frontend/src/pages/Landing.tsx` · `products/agents/frontend/src/pages/Financeiro.tsx` (internal finance organ, not pricing) · `products/core/backend/migrations/001_noctusai_core.sql:463-468`, `050_billing_gateways.sql` · `seed/lib/frontend/src/marketing/index.ts`, `coreLead.ts` · `deploy/fleet/active-scope.txt`, `build-scope.txt`, `waha-instances.yml` · memories `project-julia-golive-eligibility`, `julia-quality-target-90`, `reminder-golive-assistant-julia-agentebase`, `project-agent-templates-from-julia`, `project-usage-billing-credits-model`, `noc-site-funnel-decisions-2026-11`, `genai-divide-funnel-redesign`.

**Not verified:** live prod state (Julia's evaluation mode, which orgs, plan rows in `public.plans`), any count from `julia_*` or `agents.turn_metrics` (platform-admin data, not queried), memories older than ~2 weeks may be superseded (semantic memory search was down: OpenAI quota exhausted), CDC applicability to a legal-person buyer (lawyer's call).
