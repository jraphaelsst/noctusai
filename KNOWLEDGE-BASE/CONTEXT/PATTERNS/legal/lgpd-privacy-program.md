# LGPD as a privacy program — roles, legal bases, ROPA, RIPD, rights, transfers, encarregado, incidents, retention, DPAs

> **Owner:** agent `legal-advisor` (advisor). **Consumers:** the owner (as controller's representative), the encarregado, `security` (technical controls — `KB § PATTERNS/security/lgpd.md` stays security-owned), every executor building a feature that touches personal data.
> **Status:** craft canon, 2026-11-05 (agent-refinement W2-S3). Method, tiers and the lawyer boundary: `KB § PATTERNS/legal/legal-advisor-canon.md`. **Not legal advice** — every "decide" below names who decides.

**What this is.** LGPD (Lei 13.709/2018) treated as a *program* — the standing set of records, decisions and routines a controller and an operator must be able to show — mapped onto a multi-tenant SaaS where **NoctusAI is mostly an operador** for client organizations and **a controlador for its own data**.

**Why it exists.** The house already has excellent *controls*: RLS, private buckets with a no-exception keeper, an AI consent catalog, a PII-refusing ledger, `noctus.dev.lgpd_flag` (`KB § PATTERNS/security/lgpd.md` §§5, 9, 12, 13). What it lacks is the *program*: no per-product controller/operator map, no ROPA, no RIPD, no rights runbook, no transfer mechanism per provider, no formal encarregado act, no DPA with client orgs, no incident register — and 51 open concerns in `LGPD-WARNINGS.md` whose recurring blocker is "controller decision". Each of those decisions needs a legal reading before the owner can make it.

**How to use it.** Security answers *"is the data protected?"*; this doc answers *"may we process it, on what basis, for how long, who answers for it, and what must we be able to show?"*. Start a new feature at §3 (basis) and §2 (role); a data-subject request at §6; an incident at §10; a new vendor at §9 and §13. The house mechanism wins: consent for AI features **is** `register_feature` + `public.ai_consent` (`lgpd.md` §9) — the program records it, never duplicates it.

## Contents
0. Standard term ↔ house term · 1. Program inventory and status · 2. Roles per product · 3. Legal bases per processing · 4. ROPA (art. 37) · 5. RIPD (art. 38) · 6. Data-subject rights runbook · 7. Automated decisions (art. 20) · 8. Children and adolescents (art. 14, ECA Digital) · 9. International transfers (art. 33, Res. 19/2024) · 10. Incident communication — the hand-off · 11. Encarregado and small-agent status · 12. Retention and deletion · 13. DPA clauses for client contracts · 14. LGPD-WARNINGS triage plan · 15. Worked examples · 16. Anti-patterns · 17. Sources · 18. Re-verify list

## 0 · Standard term ↔ house term

| LGPD / ANPD | House |
|---|---|
| Titular | lead, client, patient, user, property owner, witness, broker — any natural person in a row |
| Dado sensível (art. 5 II) — health, biometric, etc. | clinical text (therapy), psychoanalysis-practice conversations (monica → `nosnolimiar`), voice (biometric when used to identify — treat conservatively) |
| Tratamento (art. 5 X) | every read/write/LLM call/embedding/log/export (`lgpd.md` §2 "Derived" row: embeddings are personal data) |
| Consentimento específico e destacado | `register_feature(..., default_granted=False)` + `/settings/ai`; therapy patient consent (`lgpd.md` §9); Julia credit consent (`julia_credito_service.py:16-18`) |
| Registro das operações (ROPA, art. 37) | none yet — §4 template |
| RIPD (art. 38) | none yet — §5 template |
| Canal do titular / encarregado | `consent.ts:24-27` (João Raphael, e-mail + phone), `/consent/privacy-policy` §17 |
| Aviso de privacidade per org (operator context) | Julia per-org notice `julia_aviso_service.py:1-5` ("the notice belongs to the org (the LGPD controller)") |
| Registro de incidentes (Res. 15/2024 art. 10) | proposed `project-history/security-incidents/register.ndjson` (`KB § PATTERNS/security/incident-response-playbook.md` §9) |
| Concern register | `LGPD-WARNINGS.md` (51 open on 2026-11-05) |

## 1 · Program inventory and status

| Artifact | Legal anchor | Status 2026-11-05 | Next step / owner |
|---|---|---|---|
| Privacy policy + terms | arts. 6 VI, 9; Marco Civil art. 7 VIII | ✅ live, seed-mounted (`consent.ts`, v1.1, 11/10/2026) | gaps in §2, §9, §11 — legal-advisor drafts, lawyer approves |
| Controller/operator map per product | arts. 5 VI–VII, 37, 39 | ❌ — the policy names one controller for everything | §2 — owner confirms per product |
| Legal basis per processing | arts. 7, 11 | ⚠️ partial (consent catalog; register entries in `lgpd.md` §§10–11) | §3 |
| ROPA | art. 37; Res. 2/2022 art. 9 (simplified) | ❌ | §4 template; one row per processing |
| RIPD | art. 38; ANPD Q&A | ❌ | §5 — monica/nosnolimiar first |
| Rights runbook | arts. 18, 19 | ⚠️ ad hoc (Julia deletion; therapy erasure rule) | §6 |
| Transfer mechanism per provider | art. 33; Res. 19/2024 | ❌ policy §11 says "cláusulas contratuais adequadas" generically | §9 matrix |
| Encarregado formal act | art. 41; Res. 18/2024 art. 3 | ⚠️ named, no written act; conflict-of-interest question | §11 |
| Small-agent classification | Res. 2/2022 arts. 2–4 | ❌ not recorded | §11 — lawyer |
| Incident register + decision | art. 48; Res. 15/2024 | ❌ (erp-certidoes owed retroactively) | §10 |
| DPA with each client org | arts. 39, 42 §1 I; ANPD guide §4.1 | ❌ (nosnolimiar DECISIONS S-DPA "owner action") | §13 template |
| Retention schedule | arts. 15, 16 | ⚠️ per-surface (`documento_retencao_politicas`), many tables without one | §12 |

## 2 · Roles per product

**The test (ANPD agents guide v2.0, §4.1 ¶53):** the operador "só poderá tratar os dados para a finalidade previamente estabelecida pelo controlador" — the difference is *power of decision* over purpose and essential elements; the operator may define non-essential elements such as technical measures (¶57) [órgão oficial]. Employees and partners of a legal person are not separate agents (¶60). A cloud vendor hired by an operator is a **suboperador**; the operator must tell the controller (¶54 iii; example 5) [órgão oficial]. **An operator that uses the data for its own purposes becomes a controller for that use.**

| Product / surface | Titulares | Controlador | NoctusAI | Confidence |
|---|---|---|---|---|
| core — accounts, SSO, platform settings, transcription API keys | platform users | NoctusAI (today João Raphael, PF — `consent.ts:20-22`) | controlador | high |
| social-wiring — leads, clients, deals, contracts, certidões, Julia | leads, buyers, sellers, spouses, witnesses, brokers | the client org (imobiliária; e.g. One Consultoria — `LGPD-WARNINGS.md:63`) | operador | high for CRM data |
| social-wiring — Biblioteca de virais (third-party Reels) | third-party creators' voices | the org that registers the profile; **NoctusAI if it reuses outputs across orgs** | operador / controlador | open — §15 |
| agents — Julia and every studio agent on WhatsApp | leads | the client org | operador | high; per-org LLM key ⇒ the LLM vendor is the **org's** operator, not NoctusAI's suboperador (`LGPD-WARNINGS.md:63` mitigation) |
| monica → nosnolimiar — leads, WhatsApp, patients, clinical tools | prospective and current patients | Mônica / Nós no Limiar (`products/nosnolimiar/projects/clinical-tools-build/DECISIONS.md:39` "Mônica = controller, NoctusAI = operator") | operador | high |
| store — kit buyers (nome, e-mail, CPF at checkout) | consumers | the seller of the kit (fornecedor) — **identify the legal entity** (`consumer-ecommerce.md` §2) | operador if the seller is a client; controlador if NoctusAI sells | open |
| mcp/vista — read tools over a client's Vista CRM | owners, brokers, clients | the client imobiliária | operador | high (`LGPD-WARNINGS.md:18`) |
| Platform telemetry, cost ledgers, security logs | users | NoctusAI | controlador | high |
| Aggregate/product-improvement use of client data | any | **NoctusAI becomes controller** for that purpose — needs its own basis | controlador | rule |

**Gap in the published policy.** `consent.ts` §1 declares João Raphael controller of the platform's data with no statement that, for client-org data, NoctusAI acts as operator and the org is the controller. Titulares of client data (leads, patients) must find the **org's** controller identity and channel — the Julia per-org notice already does this for leads; nosnolimiar's consent screen plans it (S-CO). **Proposed delta:** a §"Quando atuamos como operador" in the policy + per-org notices for every operator surface. Lawyer approves the text.

## 3 · Legal bases per processing (arts. 7 and 11)

**The bases** [norma, LGPD art. 7]: I consent · II legal/regulatory obligation · III public administration · IV research · V **contract execution or preliminary procedures at the titular's request** · VI regular exercise of rights in proceedings · VII protection of life · VIII health protection by health professionals/services/sanitary authority · IX **legitimate interest** of the controller or a third party (unless the titular's fundamental rights prevail) · X **credit protection**. **Sensitive data** only under art. 11: I specific, highlighted consent; II without consent only when *indispensable* for (a) legal obligation, (b) public policy, (c) research, (d) rights in proceedings, (e) life, (f) health protection by health professionals/services/sanitary authority, (g) fraud prevention and security in identification/authentication.

**Rules of thumb (each with a source):**
- **Legitimate interest never covers sensitive data** — it exists only in art. 7, not art. 11 (ANPD LI guide fev/2024, p. 7) [órgão oficial]. Use the guide's 3-phase test — (1) finalidade, (2) necessidade, (3) balanceamento e salvaguardas — and **keep the test on record** (art. 10 §§1–3: only strictly necessary data; transparency; ANPD may demand a RIPD) [norma].
- **Consent** must be for determined purposes (generic authorizations are void), revocable free of charge, and the controller carries the burden of proof (art. 8 §§2, 4, 5) [norma]. House proof = `ai_consent` rows with `rationale_pt` snapshot (`lgpd.md` §9).
- **Art. 7 V is for the titular's own contract.** It fits buyer/seller civil qualification on their own promise contract (`lgpd.md` §11 register entry); it does **not** fit witnesses, spouses-as-anuentes or former owners — those need art. 7 II (registry/notarial obligation, where it exists), art. 7 VI or IX (legal obligation/rights/legitimate interest) [interpretation — lawyer confirms].
- **Psychoanalysis is not a regulated health profession** ⇒ art. 11 II f (health protection "por profissionais de saúde") is doubtful; nosnolimiar's clinical tools chose art. 11 I consent (`DECISIONS.md:38`) — correct conservative default, lawyer confirms [interpretation].

| Processing (house) | Data | Proposed basis | Tier / decision owner |
|---|---|---|---|
| Platform accounts and SSO (core) | identity, e-mail, auth logs | art. 7 V (contract with the user) + II for logs where a law requires them | [norma]; owner |
| Lead CRM + Julia conversation (SW/agents) — org as controller | name, phone, messages, preferences | the **org's** choice: usually art. 7 V (preliminary procedures at the lead's request — the lead wrote first) or IX; disclosure in first message (`LGPD-WARNINGS.md:63`) | org decides; legal-advisor drafts the notice |
| Lead CPF/RG collected by the SDR before a visit (`LGPD-WARNINGS.md:33`) | identifiers | art. 7 V (preliminary procedures to the visit/contract) **only if necessary** for that step; else ask later | org + lawyer |
| Julia credit analysis (`julia_credito_service.py:16-18`) | financial standing via bureau | consent already enforced 3×; art. 7 X (credit protection) is an alternative — **keep consent** if the org wants revocability; record the choice | org + lawyer |
| Review-ask WhatsApp (`LGPD-WARNINGS.md:48`) | phone, name, outcome | art. 7 IX with balancing test + opt-out in every message | org; agents-security STOP floor |
| Meta Conversions API (`LGPD-WARNINGS.md:51`) | hashed phone/e-mail + events | art. 7 IX (org) or I; hashing is pseudonymization, still personal data; disclose Meta | org + lawyer |
| Promise-contract parties (`lgpd.md` §11) | identity docs, estado civil | art. 7 V (parties) | recorded; owner decision 2026-09-16 |
| Matrícula / certidões (`lgpd.md` §§10, 12) | CPF, chain of title, debts | art. 7 II/V + IX (recorded) | recorded |
| Serasa Crednet of a seller (`LGPD-WARNINGS.md:84`) | credit report | art. 7 X or IX (due diligence) — **not** consent by default; minimise fields (`nome_mae` `LGPD-WARNINGS.md:87`) | lawyer |
| Buyer's income-tax return, FGTS, payslips for financing (`LGPD-WARNINGS.md:111`) | financial | art. 7 V (financing at the buyer's request) | org |
| monica/nosnolimiar WhatsApp + leads (`LGPD-WARNINGS.md:21`) | health-adjacent free text | art. 11 I (consent) or art. 7 V for scheduling-only data; **RIPD first** | Mônica + lawyer |
| Clinical tools (`DECISIONS.md:38`) | sensitive | art. 11 I | Mônica + lawyer |
| Transcription API voice (`LGPD-WARNINGS.md:75`) | voice | for the caller's own purpose: the **caller** is controller, NoctusAI operator | contract terms (§13) |
| Biblioteca de virais (`LGPD-WARNINGS.md:78`; policy §19 "legítimo interesse … com avaliação de impacto documentada") | third parties' voice/speech in public posts | art. 7 IX — **the documented balancing test must exist**; none found in the repo | owner + lawyer |
| Finance counterparty CPF/CNPJ, commerce fiscal retention (`LGPD-WARNINGS.md:66,69`) | identifiers on fiscal records | art. 7 II (tax law) for the fiscal retention window | contador for the period |

## 4 · ROPA — registro das operações (art. 37)

Both controller and operator must keep it, "especially when based on legitimate interest" [norma, art. 37]; small agents may keep a simplified one (Res. 2/2022 art. 9) [norma]. One row per *processing activity* (not per table). Keep it as **data** (a versioned YAML/CSV under the program, PII-free), never prose.

```
- id: sw-julia-lead-chat
  produto: social-wiring + agents
  papel_noctus: operador            # controlador | operador | controlador conjunto
  controlador: <org cliente>        # razão social + CNPJ, from the org row
  finalidade: atendimento e qualificação de leads de imóveis
  base_legal: art. 7 V              # + art. 11 X when sensitive
  teste_li: <link>                  # mandatory when base = art. 7 IX
  titulares: leads (pessoas naturais)
  categorias: [nome, telefone, mensagens, preferências]
  sensiveis: false
  criancas_adolescentes: false
  fonte: o próprio titular (WhatsApp)
  compartilhamento: [OpenAI (suboperador/org key), Supabase, WAHA host]
  transferencia_internacional: {destino: EUA, mecanismo: <§9>}
  retencao: 180 dias (cron) + eliminação a pedido   # LGPD-WARNINGS.md:63
  seguranca: RLS org-scoped; chave LLM por org; logs sem corpo
  codigo: products/agents/... ; products/social-wiring/...
  revisado_em: AAAA-MM-DD
```

## 5 · RIPD — relatório de impacto (art. 38)

**When.** The law lets the ANPD *require* it (art. 38; art. 10 §3 for legitimate interest) [norma]. The ANPD Q&A recommends it whenever processing may generate **high risk**, using Res. 2/2022 art. 4 as the reference until a specific rule exists (one general criterion — large scale or significant effect on rights — **plus** one specific — emerging technology, automated decisions, sensitive data, children/elderly), ideally **before** the processing starts; it is sent to the ANPD only when requested [órgão oficial].

**Required in this house now (recommendation):**
1. **nosnolimiar (monica)** — WhatsApp conversations of a psychoanalysis practice + clinical tools (sensitive ∧ significant effect). Blocking for clinical tools go-live.
2. **Julia credit analysis** — automated verdict (`aprovado`/`reprovado`) with significant effect on renting.
3. **Core transcription API** (voice) and **Biblioteca de virais** (third-party voices + LLM classification).
4. **therapy-platform** — only on reactivation (product asleep).

**Minimum content** [norma, art. 38 sole paragraph]: data types, collection and security methodology, the controller's analysis of measures, safeguards and mitigation. **Recommended structure** [órgão oficial, ANPD Q&A]: parties, justification, process, systems, data life cycle (collection → deletion), categories and titulares, retention, legal basis per purpose, principles analysis, risks, risk assessment, mitigation, approvals.

```
RIPD — <processo> — v<n> — <data>
1. Identificação: controlador, operador(es), encarregado, elaboradores
2. Necessidade do RIPD: critérios (geral + específico) — Res. 2/2022 art. 4 por referência
3. Descrição do tratamento: finalidade, ciclo de vida, sistemas (file:line), fluxos e destinos
4. Categorias de dados e titulares; volume; sensíveis/crianças/idosos
5. Base legal por finalidade (art. 7/11) + teste de LI quando art. 7 IX
6. Necessidade e proporcionalidade (art. 6 III): o que não coletamos e por quê
7. Riscos aos titulares (probabilidade × impacto), incl. transferência internacional e decisões automatizadas
8. Medidas e salvaguardas (técnicas — security; organizacionais — este programa)
9. Risco residual e aceite: quem aceita (dono como representante do controlador) + parecer do encarregado
10. Revisão: gatilhos (nova finalidade, novo fornecedor, incidente, norma nova)
```

## 6 · Data-subject rights runbook (arts. 18–19)

**The law** [norma]: rights I–IX of art. 18 (confirmation, access, correction, anonymization/blocking/elimination of unnecessary data, portability, elimination of consent-based data, sharing info, consequences of refusing consent, revocation); exercised by express request to an agente de tratamento (§3); if not immediate, the controller answers saying it is not the agent (indicating who) or giving the reasons (§4); free of charge, "nos prazos e nos termos previstos em regulamento" (§5); the controller informs the agents it shared with so they repeat correction/elimination (§6). **Access:** simplified format **immediately**, or a clear and complete declaration **within 15 days** of the request (art. 19 I–II). Small agents: double deadline for art. 19 II and may give the simplified declaration within 15 days (Res. 2/2022 arts. 14 III, 15) [norma]. No ANPD rights regulation in force was found (consultation closed 2024 — §18).

**House default:** answer **every** request within **15 days** (the only statutory number), acknowledge immediately.

```
1. Receber (canal do encarregado / per-org notice) → registrar: data, canal, direito pedido, sem conteúdo pessoal no ledger.
2. Quem é o controlador desses dados? (§2)
   - Org cliente ⇒ NoctusAI é operador: encaminhar ao controlador em até 2 dias úteis (DPA §13) e
     responder ao titular indicando o controlador (art. 18 §4 I). Não decidir pelo controlador.
   - NoctusAI ⇒ seguir.
3. Verificar identidade proporcional ao risco (nunca pedir mais dados do que o necessário).
4. Localizar: todas as tabelas + embeddings + storage + caches + LLM logs + backups (janela PITR declarada).
5. Executar o direito:
   - acesso: declaração completa (origem, critérios, finalidade) — art. 19 II;
   - eliminação: hard delete onde a base for consentimento; manter o que tem base própria (art. 16 I — obrigação legal, ex.: fiscal) e dizer o que ficou e por quê;
   - revogação de consentimento: forward-only (lgpd.md §9) + oferecer eliminação do passado;
   - oposição (art. 18 §2): parar o tratamento sem consentimento se houver descumprimento.
6. Propagar a quem recebeu (art. 18 §6): suboperadores, Meta CAPI, LLM vendor (se retém).
7. Responder em linguagem simples; registrar data de resposta.
```

**Known house gaps:** deleting a nosnolimiar lead does not delete its chat/messages (`LGPD-WARNINGS.md:21` open item 2); no single "find everything about titular X" tool across products — a candidate `noctus.dev.*` tool (DSAR locator), routed to the tech-lead.

## 7 · Automated decisions (art. 20)

**The law** [norma]: the titular may request **review** of decisions taken **solely** on automated processing that affect their interests, including profiling (personal, professional, consumption, credit, personality); the controller must give clear information on criteria and procedures on request, subject to trade secrets (§1); otherwise the ANPD may audit for discrimination (§2).

| House decision | Solely automated? | Effect | Position |
|---|---|---|---|
| Julia qualification score + stage (`products/agents/backend/app/qualificacao/engine.py:330-372`) | normal stages yes; **terminal stages are only suggested** and need confirmation (`engine.py:366-372`) | prioritisation of a lead | keep the human-confirmed terminal design; publish the criteria summary in the org notice; record that review = a human re-reads |
| Julia credit analysis verdict (`julia_credito_service.py:47` `aprovado`/`reprovado`) | the bureau's verdict, applied automatically | access to renting | **art. 20 applies** — give a human review path and the criteria on request; RIPD (§5) |
| `erp.lead_score` (erp-imobiliario, asleep) | consent-gated (`products/erp-imobiliario/backend/app/routers/ai.py:102`) | prioritisation | park with the product |
| LLM classification in Biblioteca / extraction readiness | no decision on the titular | — | out of art. 20 |

Res. 2/2022 art. 4 II c lists "decisões tomadas unicamente com base em tratamento automatizado … inclusive … de crédito" as a **high-risk** criterion — relevant for §11.

## 8 · Children and adolescents (art. 14; ECA Digital)

**LGPD** [norma]: processing in their **best interest**; children's data (under 12) need specific, highlighted consent of at least one parent/guardian (§1), with public information on data types and rights procedures (§2), reasonable efforts to verify the guardian (§5), simple and accessible information (§6); collection without consent only to contact the parents once, without storage, or for protection, never passed to third parties (§3). LI is possible for children and adolescents only with the best-interest test prevailing (ANPD LI guide, children section) [órgão oficial].

**ECA Digital (Lei 15.211/2025)** — the ANPD guide (out/2026) applies it to IT products "direcionado … ou de acesso provável" by children and adolescents, via three cumulative requirements (likelihood/attractiveness, ease of access, significant risk); **generative AI systems** and e-commerce of products forbidden to minors are among the categories with a **legal presumption** of likely access (guide Annex III, citing Decreto 12.880/2026); platforms of strictly professional nature may get differentiated treatment [órgão oficial; law and decree text not fetched — re-verify].

**House position.**
- B2B tools (social-wiring, agents studio, store admin) — not directed to minors; record the self-assessment (the guide says it does not bind the ANPD).
- **Public WhatsApp agents (Julia) are generative-AI systems talking to the public** ⇒ presumption question → **lawyer**; minimum floor: if a lead declares being under 18, stop qualification and hand off to a human.
- **nosnolimiar patients may be adolescents** (psychoanalysis practice) ⇒ the clinical-tools consent flow must handle a guardian's consent for under-12 and a policy for 12–17 → Mônica + lawyer.
- Policy §16 says the platform is not for under-18s — true for users, **not** for titulares of client data.

## 9 · International transfers (art. 33; Res. CD/ANPD 19/2024)

**The law** [norma]: transfer only (I) to countries with adequacy, (II) with controller-provided guarantees — (a) specific clauses, (b) **standard clauses**, (c) global corporate rules, (d) seals/certificates — or (III–IX) other cases, including (VIII) specific, highlighted consent with prior information on the international nature, and (IX) the cases of art. 7 II, V and VI.

**Res. 19/2024** [norma]:
- A transfer needs **both** a legal basis (art. 7/11) **and** a valid mechanism (Annex I art. 9); limited to the minimum necessary (art. 9 sole paragraph).
- The controller checks whether there is a transfer, whether LGPD applies and the basis + mechanism; **the operator assists** with the information it has (art. 4 §1).
- **Standard clauses** must be adopted **in full and without alteration** from Annex II (art. 16), as a separate contract or an addendum; other clauses may not exclude or contradict them (§2).
- Parties already using contractual clauses had **12 months from publication (23/08/2024)** to incorporate the ANPD standard clauses (Resolution art. 1 sole paragraph) — i.e. by ≈ 23/08/2025.
- **Transparency:** full clauses to the titular on request within 15 days (art. 17 §1), and a **public page in Portuguese** on the transfer: form, duration, purpose, destination country, controller identity/contact, sharing, responsibilities and security, rights and the ANPD petition right (art. 17 §§2–3) — may be a highlighted section of the privacy policy.
- International **collection** directly by a foreign agent is not a transfer (art. 6).

**Provider matrix (fill per provider; the operator's job is to gather it).**

| Provider | Data | Destination | Role toward client data | Mechanism available | Status |
|---|---|---|---|---|---|
| OpenAI | Julia chats, extraction, clinical (therapy) | EUA | org's operator when the org's key is used; else NoctusAI's suboperador | provider DPA (usually EU SCCs) — ANPD Annex II verbatim? | **open** |
| Anthropic | Biblioteca classification, igig assistant | EUA | suboperador | same question | **open** |
| Google, Meta | OAuth, CAPI, WhatsApp | EUA/global | suboperador / independent controller (Meta platform terms) | provider terms | **open** |
| Supabase | everything | region per project — **check** (nosnolimiar `DECISIONS.md:41` S-RG) | suboperador | DPA | **open** |
| Cloudflare, Resend, VPS host | traffic, e-mail, hosting | global / per host | suboperador | DPA | **open** |
| Asaas, D4Sign | payments, signatures | Brasil (verify) | suboperador | — (no transfer if BR) | verify |

**Decision path when a provider does not offer the ANPD clauses verbatim** (lawyer decides): (1) negotiate the ANPD Annex II addendum; (2) rely on art. 33 IX where the transfer is necessary to perform the titular's own contract (art. 7 V) — narrow; (3) art. 33 VIII specific consent — fragile for B2B operator settings because the **client org** collects it; (4) avoid the transfer (BR region, self-hosted model). **Policy delta:** replace the generic §11 sentence with the art. 17 §2 transparency content.

## 10 · Incident communication — the hand-off with security

`KB § PATTERNS/security/incident-response-playbook.md` owns detection, severity, containment, evidence and the technical assessment; §10 of that playbook hands the legal items here. This section closes them.

**Res. CD/ANPD 15/2024, read on the DOU** [norma] — confirming or correcting the playbook's secondary readings:
- **Art. 5** — relevant risk or damage = may significantly affect interests and fundamental rights **and** ≥ 1 of: sensitive data; children/adolescents/elderly; financial data; authentication data; data under legal, judicial or professional secrecy; large scale. §1 gives examples of "significant" (prevent rights or service use, material or moral damage, discrimination, physical integrity, image/reputation, financial fraud, identity theft). ✅ playbook correct.
- **Art. 6** — ANPD communication by the **controller within 3 business days** of knowing the incident affected personal data (§1); 12 mandatory content items (§2 I–XII — incl. number of titulares with children/adolescents/elderly broken out, measures before and after, operator identification, total titulares in the affected activities); **complementation within 20 business days** of the communication (§3) ✅ — the playbook's "re-verify" item 1 is now verified; electronic form (§4); filed **by the encarregado with proof of the link, or by a constituted representative with a power of attorney** (§5), documents with the communication (§6); deadlines of the caput and §3 doubled for small agents (§8).
- **Art. 9** — titulares within **3 business days**, 7 content items, plain language, direct and individual when possible (§§1–2), public channels when not (§3); **declaration to the ANPD that titulares were informed within 3 business days after the end of the art. 9 deadline** (§4) ✅ verified; doubled for small agents (§6).
- **Art. 10** — register of **every** incident, communicated or not, **≥ 5 years**; minimum fields (§1): knowledge date, circumstances, nature and category of data, number of titulares, risk assessment and possible damages, correction/mitigation, form and content of any communication, **reasons for not communicating** ✅ — map these to the playbook §9 schema (all present; add `circunstancias`).
- **Operator → controller:** Res. 15/2024 places the duty on the **controller** and only asks the operator's identification (art. 6 §2 X). The operator's duty to inform the controller is **contractual** (art. 39 instructions; §13 clause) — the regulation sets no operator deadline [norma — absence verified in the text].

**Decision support (owner decides):**
1. Controller for the affected data? Client org ⇒ notify the org per DPA (template playbook 6.3) **fast enough for their 3-business-day clock** — house SLA: within 24 h of confirming personal data was affected. NoctusAI ⇒ continue.
2. Is it an incident? Res. 15 art. 3 XII: "evento adverso **confirmado**" violating confidentiality, integrity, availability or authenticity. An exposure window **without** evidence of access (e.g. browser-readable tables, `LGPD-WARNINGS.md:24,27,30`) is a confirmed *vulnerability*; whether it is a confirmed *incident* depends on the log review → **register the assessment either way**; lawyer on borderline cases.
3. Art. 5 test criterion by criterion, written.
4. Communicate (3 business days, or 6 if the small-agent status is recorded — §11) or register the reasons not to.

**Owed:** erp-certidoes (2026-09-17) retroactive register entry (playbook §9) — CPF + débitos/restrições ⇒ "dados financeiros" criterion present; the controller is presumably the client imobiliária (operator role ⇒ the duty to communicate is theirs; ours was to inform them) → owner + lawyer.

## 11 · Encarregado and small-agent status

**Encarregado** [norma]: the controller must appoint one (LGPD art. 41) and publish identity and contact (§1). **Res. 18/2024:** appointment by **formal written, dated and signed act** stating duties (art. 3 §1), shown to the ANPD on request (§2); a **formally designated substitute** for absences (art. 4); identity (full name) and contact **published prominently on the website** (art. 9 §1 I); communicates in Portuguese (art. 13); no certification required (art. 14); duties: complaints, ANPD communications, staff guidance (art. 15) and advice on incidents, ROPA, RIPD, security, contracts, transfers, governance and privacy by design (art. 16); performing them does **not** make the encarregado responsible for compliance — the agent is (arts. 11, 17); **conflict of interest** may arise when the encarregado accumulates **strategic decision-making about the processing** (art. 19 §1 II), verified case by case and sanctionable (§2); operators may appoint one as good practice (art. 6).

**House reading.** `consent.ts:20-27` names João Raphael as **both controller and encarregado**. For a natural-person controller this is the decision-maker himself — the art. 19 §1 II conflict concern applies at least in spirit → **lawyer**: (a) keep (small agent, if eligible, need not appoint at all — Res. 2/2022 art. 11 — and a channel suffices; appointment counts as good practice §2), or (b) appoint an external encarregado once a CNPJ exists. Either way: write the formal act (Res. 18 art. 3) and name a substitute (art. 4).

**Small-agent status (Res. 2/2022)** [norma]: includes ME, EPP, startups, non-profits **and natural persons** acting as controller or operator (art. 2 I); excluded when (art. 3) the processing is **high risk**, revenue exceeds LC 123 art. 3 II (or LC 182 for startups), or the economic group exceeds it; high risk = general criterion + specific criterion (art. 4); proof within 15 days on ANPD request (art. 5); benefits: simplified ROPA (art. 9), optional encarregado with a mandatory channel (art. 11), simplified security policy (art. 13), **doubled deadlines** (art. 14) except where physical/moral integrity or national security is at risk (art. 14 II). The flexibilities never exempt from the bases, principles and rights (art. 6). **Position:** do **not** record NoctusAI as a small agent until a lawyer assesses art. 3 I against §5's high-risk list; until then plan with the single deadlines.

## 12 · Retention and deletion (arts. 15–16)

Processing ends when the purpose is achieved, the period ends, the titular revokes consent, or the ANPD orders it (art. 15); data are then **eliminated**, keeping them only for legal/regulatory obligation, research (anonymized when possible), transfer to a third party within the law, or exclusive anonymized use (art. 16) [norma]. Retention and access-log decisions ship **together** (`lgpd.md` §10).

| Data | House default | Basis for the period | Who sets it |
|---|---|---|---|
| Lead conversations (agents) | 180 days, cron (`LGPD-WARNINGS.md:63`) | purpose (qualification) | org (operator default) |
| Card documents (SW) | 1825 days (`lgpd.md` §11) | contract + limitation periods | org + lawyer |
| Fiscal records (CPF/CNPJ on paid orders, finance entries) | tax limitation period | art. 16 I — **contador** names the period | accountant + contador |
| Clinical tool answers | treatment end + N years (`DECISIONS.md:42`; CFP rule only if a CRP applies) | professional rule | Mônica + lawyer |
| Security incident register | ≥ 5 years | Res. 15/2024 art. 10 | fixed |
| Access logs of applications (Marco Civil art. 15) | 6 months **if** the provider is a legal person acting professionally | Lei 12.965 art. 15 — today the controller is a natural person ⇒ verify applicability | lawyer |
| Voice recordings / transcripts | define per purpose (`LGPD-WARNINGS.md:42,75`) | purpose | owner |
| ImovelWeb inbox and ledger | none (`LGPD-WARNINGS.md:194`) | define | org |

Deletion must reach backups' disclosed window, embeddings and caches (`lgpd.md` §2 derived data).

## 13 · DPA clauses for client contracts (controller ⇄ NoctusAI as operator)

The LGPD does not require a written contract, but the ANPD calls it good practice and lists its content: object, duration, nature and purpose, data types, rights, obligations and responsibilities (agents guide ¶¶55–56) [órgão oficial]; the operator is jointly liable when it breaches the law or the controller's lawful instructions (art. 42 §1 I) [norma]. Clause library (lawyer finalises wording):

1. **Roles and instructions** — the org is controller; NoctusAI processes only on documented instructions (art. 39); product configuration = instruction; anything else needs written instruction.
2. **Purpose limitation** — no use for NoctusAI's own purposes (aggregate analytics, model training) without a separate basis and the org's agreement — otherwise NoctusAI becomes controller (§2).
3. **Confidentiality** of personnel.
4. **Security measures** (art. 46) — reference `KB § PATTERNS/security/lgpd.md` controls; summary annex.
5. **Suboperadores** — current list (§9 matrix) + prior notice of changes (agents guide ¶54 iii); flow-down of equal obligations.
6. **International transfers** — mechanism per suboperator; ANPD Annex II clauses where used (Res. 19/2024 art. 16).
7. **Incidents** — notify the controller **within 24 h** of confirming personal data was affected, with the Res. 15/2024 art. 6 §2 items available; cooperate with communications.
8. **Data-subject requests** — forward within 2 business days; assist (art. 18 §§3–4, §6).
9. **ROPA and RIPD assistance** (art. 37; Res. 19 art. 4 §1 for transfers).
10. **Audits** — information on request; reasonable on-site audit rights.
11. **Return and deletion** at the end (art. 16), with export format and deadline; backup window disclosed.
12. **Liability allocation** — within the limits of art. 42–45; no clause can remove liability toward titulares.
13. **Sensitive data annex** for health products (nosnolimiar): art. 11 basis owned by the controller; extra measures (S-ENC, S-AUD).

## 14 · LGPD-WARNINGS triage plan (51 open on 2026-11-05)

`LGPD-WARNINGS.md` is append-only by keeper (`check_lgpd_entry_removal`); this plan **proposes** a disposition per entry (by line number of the `- [ ]` line); it does not edit the file. Active products = `deploy/fleet/active-scope.txt` (agents, core, nosnolimiar, seed, social-wiring); others are asleep.

| Bucket | Lines | Count | Who acts | Closure evidence |
|---|---|---|---|---|
| **B · Legal basis / transparency decision** | 18, 21, 33, 36, 45, 48, 51, 63, 75, 78, 84, 87, 105, 108, 111, 150, 191 | 17 | legal-advisor drafts basis + notice text (§3); controller decides (org or owner); lawyer on sensitive/credit | decision recorded as a register entry in `lgpd.md` style + ROPA row |
| **C · Possible incident — assessment owed** | 24, 27, 30 | 3 | security: apply migration + log review; legal-advisor: Res. 15 art. 3 XII / art. 5 reasoning; owner decides | register entry (§10), then tick |
| **D · Retention period to define** | 39, 42, 54, 57, 60, 66, 69, 72, 81, 194, 197 | 11 | legal-advisor proposes period + basis (§12); accountant/contador for fiscal (66, 69); executor implements purge | retention row + purge job |
| **E · Technical access control** | 99, 102 | 2 | security | code/policy change |
| **A · Close with pointer** | 96 | 1 | security after migration 119 is applied — the register entry already exists (`lgpd.md` §11) | pointer + applied proof |
| **F · Asleep products — park** | 93, 200, 207, 210, 225, 231, 234, 237, 240, 243, 246, 249, 252, 255, 258, 261, 264 | 17 | nobody now (inativo ⇒ don't touch); **one owner question:** does prod still hold these products' personal data? If yes ⇒ retention/deletion decision now | parked note per product |

**Order:** C first (clocks and registers), then B for active operator surfaces (Julia 63/33/36/45/48/51; nosnolimiar 21), then D.
**Proposed ownership (Wave 3 decides):** the **file and the `lgpd_flag` tool stay `security`'s** (technical intake); **legal disposition** of buckets B, C (communication decision), D (periods) and F (parking) becomes `legal-advisor`'s; buckets A and E stay `security`'s. A future `lgpd_flag` field `bucket:` (A–F) would make this mechanical — tooling proposal, not done here.

## 15 · Worked examples

### A · nosnolimiar clinical tools go-live
- Controller Mônica/Nós no Limiar, NoctusAI operator (`DECISIONS.md:39`). Data: answers to clinical reflection tools = sensitive (health) [norma art. 5 II].
- Basis art. 11 I consent, versioned and recorded (S-LB, S-CO) — psychoanalysis outside art. 11 II f's "profissionais de saúde" reading [interpretation].
- Must-haves before go-live: RIPD (§5, high risk: sensitive ∧ significant effect), DPA with sensitive annex (§13), Supabase region / transfer disclosure (S-RG, §9), retention (S-RT, lawyer), minors policy (§8), real DELETE + backup window disclosure (S-DEL).
- **Lawyer:** basis confirmation, retention years, minors. **Mônica:** controller decisions and consent text.

### B · Julia lead with OpenAI on the org's key
- Org = controller; NoctusAI = operator; with the org's own OpenAI key the vendor is the **org's** operator and the transfer is the org's (Res. 19 art. 3 I — exporter is the org) [interpretation]; NoctusAI assists (art. 4 §1) and its own policy must not claim otherwise.
- Gaps: the org's notice must name OpenAI, the destination country and the mechanism (art. 17 §2); if the platform key is used instead, OpenAI is NoctusAI's suboperador → DPA flow-down (§13.5–6).

### C · erp-certidoes retroactive assessment
See §10 "Owed" — financial data criterion present; role likely operator; the evidence half is security's (`incident-response-playbook.md` §9).

## 16 · Anti-patterns

- **One controller for everything** in the policy (§2).
- **Legitimate interest for sensitive data**, or LI without a written balancing test.
- **Consent as the default basis** when the relation is contractual — revocation then breaks the service.
- **"We're an operator, so it's the client's problem"** — the operator keeps its own ROPA (art. 37), security duties (art. 46) and joint liability (art. 42 §1 I).
- **Assuming small-agent doubled deadlines** without a recorded classification.
- **"Cláusulas contratuais adequadas"** without the ANPD Annex II text or another named mechanism.
- **Deleting a lead but not its conversations / embeddings / files.**
- **Treating "was readable" as "nothing happened"** without a recorded log review and assessment.

## 17 · Sources

Accessed 2026-11-05.

| Title | URL | Supports | Tier |
|---|---|---|---|
| LGPD (Planalto) | https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm | arts. 5, 7, 8, 9, 10, 11, 14, 15, 16, 18, 19, 20, 33, 37, 38, 39, 41, 42, 46, 48, 52 | [norma] |
| Res. CD/ANPD 2/2022 (DOU print on gov.br/palmares) | https://www.gov.br/palmares/pt-br/midias/arquivos-menu-acesso-a-informacao/legislacao/resolucao-cd-anpd-n2-2022.pdf | §11 arts. 2–6, 9, 11–15; §5 art. 4 | [norma] (2022 text) |
| Res. CD/ANPD 15/2024 (DOU) | https://www.in.gov.br/en/web/dou/-/resolucao-cd/anpd-n-15-de-24-de-abril-de-2024-556243024 | §10 arts. 3, 5, 6, 9, 10; amends Res. 2/2022 art. 14 II | [norma] |
| Res. CD/ANPD 18/2024 (DOU) | https://www.in.gov.br/en/web/dou/-/resolucao-cd/anpd-n-18-de-16-de-julho-de-2024-572632074 | §11 arts. 3, 4, 6, 9, 11–19 | [norma] |
| Res. CD/ANPD 19/2024 (DOU) | https://www.in.gov.br/en/web/dou/-/resolucao-cd/anpd-n-19-de-23-de-agosto-de-2024-580095396 | §9 Res. art. 1 sole para.; Annex I arts. 3, 4, 6, 9, 16, 17 | [norma] |
| ANPD — Guia agentes de tratamento e encarregado v2.0 (abr/2022) | https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia_agentes_de_tratamento_e_encarregado___defeso_eleitoral.pdf | §2 ¶¶53–60; §13 ¶¶55–56 | [órgão oficial] |
| ANPD — Guia legítimo interesse (fev/2024) | https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/copy_of_guia_legitimo_interesse.pdf/@@display-file/file | §3 3-phase test; not for sensitive data; §8 children | [órgão oficial] |
| ANPD — RIPD perguntas e respostas | https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/relatorio-de-impacto-a-protecao-de-dados-pessoais-ripd | §5 when, content, submission | [órgão oficial] |
| ANPD — Guia ECA Digital: fornecedores de TI (out/2026) | https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia-fornecedores-de-produtos-ou-servicos-de-tecnologia-da-informacao.pdf | §8 likely-access test, presumption categories | [órgão oficial] |
| ANPD — materiais educativos (guide list) | https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes | guide inventory | [órgão oficial] |
| Marco Civil da Internet (Planalto) | https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2014/lei/l12965.htm | §12 art. 15; art. 7 VIII–X | [norma] |
| Mayer Brown — end of SCC grace period (ago/2025) | https://www.mayerbrown.com/pt/insights/publications/2025/08/end-of-grace-period-implementation-of-brazils-standard-contractual-clauses-in-international-transfers-of-personal-data | §9 no equivalence recognised as of ago/2025 | [publicação profissional] — search result only, re-verify |

## 18 · Re-verify list

- ANPD regulation on data-subject rights (deadlines) — none found 2026-11-05.
- Any ANPD adequacy decision or equivalence of foreign SCCs after 2025 (a consultancy blog cites a "Res. CD/ANPD 32/2026" on the EU — **unverified, do not rely**).
- Lei 15.211/2025 (ECA Digital) and Decreto 12.880/2026 — read the texts (only the ANPD guide was read).
- Res. 2/2022 consolidated text; the ANPD simplified-ROPA model (art. 9 sole paragraph).
- Supabase project region(s); each provider's current DPA and whether it offers the ANPD Annex II clauses.
