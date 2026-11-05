# Security incident response playbook — NIST SP 800-61r3 on our tools, with the LGPD clock

> **What it is.** What we do when a security incident is suspected or confirmed: who decides, which
> tool does each step, how severity is set, when the LGPD Art. 48 / Res. CD/ANPD 15/2024 clock starts,
> what we tell whom (pt-BR templates), how evidence is kept, and how the incident becomes a keeper.
> Born 2026-11-05 (agent-refinement W1-S2); owned by agent `security`.
>
> **Why.** The platform has excellent post-fix lessons and no incident procedure. The 2026-09-17
> erp-certidoes public-bucket exposure (`KB § PATTERNS/security/lgpd.md` §12) was fixed in hours and
> gated forever — and never *assessed*: no "risco ou dano relevante" decision, no register entry, no
> communication decision. Under Res. 15/2024 the register is mandatory even for incidents that are NOT
> communicated. This playbook closes that half.
>
> **How to use it.** On a suspected incident open §2 (severity) and §3 (roles), then walk §4 phase by
> phase; §5 is the LGPD decision, §6 the templates, §7 evidence, §8 the review. **House split:**
> devops-engineer owns runbook *mechanics* (restart, rollback, recreate — `KB § PATTERNS/devops/prod-watchdog.md`,
> `noctus.dev.deploy_image`); `security` owns *classification*, scope-of-exposure analysis and the
> technical half of the LGPD assessment; the **owner (as controller's representative)** owns the
> communication decision. Legal items marked **re-verify** come from secondary sources or need a
> lawyer's reading before use.

**Standard term ↔ house term.**

| Standard (NIST / LGPD) | House |
|---|---|
| Incident commander | the tech-lead session (owner present) |
| Detection sources (DE.CM / DE.AE) | `noctus.dev.prod_watchdog`, `/api/health` `startup_hook_error`, keepers, `predeploy_check`, Supabase advisors, owner/customer report |
| Containment action | `noctus.vps.*`, `noctus.dev.deploy_image` (atomic redeploy with `:previous` rollback), secret revoke at provider, flag/route off |
| Controlador / operador (LGPD Art. 5 VI/VII) | the customer org is usually *controlador* of its leads/clients' data; NoctusAI is *operador* for that data and *controlador* for its own users/accounts (**re-verify per product with the legal advisor**) |
| Encarregado (Art. 41) | not formally appointed in KB today — gap (§10) |
| Incident register (Res. 15 art. 10) | proposed `project-history/security-incidents/register.ndjson`, PII-free (ids, counts, categories) — guarded by `check_ledger_pii` |

---

## 1 · What counts as a security incident

Any confirmed or reasonably suspected event that compromises **confidentiality, integrity or
availability** of systems or data. Personal-data incidents (*incidente de segurança com dados pessoais*)
are the subset that triggers §5. Examples here: a public bucket or a view granted to `anon` with personal
data; a leaked secret (repo, log, chat); cross-tenant read/write (BOLA); forged webhooks accepted; an LLM
agent disclosing another lead's data; a compromised staff account; ransomware/host compromise of the VPS;
a malicious dependency/action in CI.

Not incidents (but log them): a vulnerability found before any exposure path existed (that is a P-level
finding, `KB § PATTERNS/security/appsec-craft-canon.md` §4); availability blips with no security cause
(devops runbook).

## 2 · Severity ladder

| SEV | Definition (first match) | Response |
|---|---|---|
| **SEV1** | Personal data of a Res. 15 art. 5 category (sensitive, children/elderly, financial, authentication, secrecy-protected, large scale) **exposed or likely exposed**; ∨ active attacker; ∨ prod credential with write power leaked; ∨ cross-tenant write | all hands now; owner informed immediately; §5 clock assumed running |
| **SEV2** | Other personal data exposed; ∨ cross-tenant read without evidence of access; ∨ secret leaked without evidence of use | same day; §5 assessment within 1 business day |
| **SEV3** | Exposure path existed but logs show no access, no personal data; ∨ contained misconfiguration | within the release train; register entry |
| **SEV4** | Near miss / policy violation caught by a gate | finding + keeper candidate |

Upgrade on any new fact; never downgrade without evidence (logs, access records). A SEV is not a CVSS
score — CVSS rates the *vulnerability*, SEV rates the *event*.

## 3 · Roles

| Role | Who | Owns |
|---|---|---|
| Incident commander (IC) | tech-lead session, owner present | decisions, timeline, phase transitions |
| Security lead | agent `security` (advisor) | classification, exposure scope, evidence plan, technical LGPD assessment |
| AI-agent lead | agent `agents-security` | when an LLM agent is the vector or the leak |
| Ops | `devops-engineer` | containment mechanics, rollback, recreate, host forensics capture |
| Fix executor | backend/frontend/devops engineer | the root-cause change + keeper |
| Communication decision | owner (controller representative); future `legal-advisor` agent advises (§10) | ANPD / titulares / customer-controller communication |
| Scribe | IC session | the timeline in UTC, every action with tool + result |

## 4 · Phases (NIST SP 800-61r3 on CSF 2.0) mapped to our tools

SP 800-61r3 (April 2025) is a CSF 2.0 Community Profile: incident response is spread across the CSF
functions rather than a standalone lifecycle. The house walk:

### 4.1 Prepare (GOVERN / IDENTIFY / PROTECT)
- This playbook + the §6 templates exist before they are needed; contacts (owner phone/e-mail, Supabase,
  Cloudflare, Hostinger, provider support) kept in the owner's vault, not in KB.
- Asset/data inventory: products ⇒ `noctus.dev.product_scope_report`; data categories ⇒
  `KB § PATTERNS/security/lgpd.md` §2 + `LGPD-WARNINGS.md`.
- Preventive gates are the keepers (`KB § PATTERNS/security/secure-code-review-checklist.md`).

### 4.2 Detect and analyze (DETECT — DE.CM, DE.AE; RESPOND — RS.AN)
- Sources: `noctus.dev.prod_watchdog` (off-host, every 10 min; `KB § PATTERNS/devops/prod-watchdog.md`),
  `/api/health` degraded fields, `noctus.dev.supabase_advisors`, Supabase logs (MCP `query_logs`),
  `noctus.vps.logs`, gitleaks/Trivy alerts, a customer or owner report.
- Triage questions (security lead): *what data, which orgs, since when, by which route, any evidence of
  access?* Write each answer with its evidence source. Unknown ⇒ write "unknown" — never assume "no access".
- **Set `t_conhecimento`** — the moment we know (or reasonably should know) that the incident affected
  personal data. That timestamp starts the §5 clock; record it in UTC.

### 4.3 Contain (RESPOND — RS.MI)
Containment beats root cause. Choose the narrowest action that stops exposure:

| Situation | Action (tool) |
|---|---|
| Public bucket / over-granted view | flip private / `REVOKE` (migration via `noctus.dev.migrate_product`, or SQL through the Supabase MCP with owner consent) |
| Bad deploy introduced it | `noctus.dev.deploy_image` rollback to `:previous` (auto-rollback on failed health) |
| Leaked secret | revoke at the provider FIRST, then rotate in `.env.fleet` / settings, redeploy |
| Abusive sender / flood on an agent | block number (SW `julia_protecao_service` blocklist), agent off-switch (single outbound chokepoint re-reads the DB), platform kill switch |
| Compromised staff account | revoke sessions (GoTrue), reset password/MFA, remove org membership |
| Host compromise | isolate: stop tunnel ingress for the slug; preserve before rebuild (§7); never `prune` evidence |

Every action is logged in the timeline with the exact tool call and result.

### 4.4 Eradicate and recover (RESPOND — RS.MI; RECOVER — RC.RP)
- Root-cause fix at the right level (seed if the default caused it — CLAUDE.md §1 "No quick fixes").
- Recover: `noctus.dev.predeploy_check` ⇒ deploy ⇒ `noctus.dev.smoke_fleet` / `spa_smoke` /
  `sso_smoke` ⇒ watch `prod_watchdog` for two cycles.
- Verify the exposure path is closed **from the attacker's side** (e.g. unauthenticated fetch of the
  public URL now 400/404; `anon` select now denied).

### 4.5 Report and communicate (RESPOND — RS.CO; RECOVER — RC.CO)
§5 decides; §6 provides the words. Internal status updates every few hours for SEV1/2.

### 4.6 Improve (IDENTIFY — ID.IM)
§8 post-incident review; the incident becomes a checklist line and, at N≥2 or SEV1, a keeper.

---

## 5 · LGPD decision — Art. 48 + Res. CD/ANPD 15/2024

**Law.** LGPD Art. 48: the *controlador* must communicate to the ANPD and to the titulares the
occurrence of a security incident that may cause relevant risk or damage to the titulares. Art. 46: security
measures; Art. 37: records of processing.

**Regulation (Res. CD/ANPD 15/2024, text read on legisweb 2026-11-05).**
- **Art. 5 — relevant risk or damage:** when the incident *can significantly affect interests and
  fundamental rights* of titulares **and** involves at least one criterion: sensitive data; data of
  children, adolescents or elderly; financial data; system authentication data; data protected by legal,
  judicial or professional secrecy; large-scale data.
- **Art. 6 — ANPD communication:** within **3 business days** (*três dias úteis*) of the controller
  learning that the incident affected personal data. **§8: deadlines doubled for agentes de pequeno
  porte** (Res. CD/ANPD 2/2022). Complementation of the information within **20 business days**
  (**re-verify** the exact paragraph — secondary sources).
- **Art. 9 — titulares:** within **3 business days**, in simple, easy-to-understand language; doubled for
  small agents (§6). Declaration to the ANPD that titulares were informed, within 3 business days after
  (**re-verify** — secondary source).
- **Art. 10 — register:** keep a record of **every** security incident with personal data, **including
  those not communicated**, for **at least 5 years** from the register date; contents include the date of
  knowledge and the risk/damage assessment (full field list **re-verify** against the DOU text).

**Decision procedure (the owner decides; security prepares).**
1. Was personal data affected? No ⇒ register as non-personal-data incident (internal), stop §5.
2. Who is the *controlador* for this data? If a customer org ⇒ NoctusAI as *operador* informs that
   controller without undue delay with everything it needs to decide (template 6.3) — **re-verify the
   operator's duties and timing with the legal advisor**. If NoctusAI ⇒ continue.
3. Art. 5 test: significant effect **and** ≥1 criterion? Write the reasoning, criterion by criterion.
4. Yes ⇒ communicate ANPD (template 6.1) and titulares (6.2) within the clock from `t_conhecimento`
   (business days; doubled if small agent — confirm the company's status once and record it here).
5. No ⇒ do not communicate, **but register** with the reasoning (art. 10).
6. Any doubt on 3–5 ⇒ treat as yes and get legal review in parallel; the clock does not pause.

**Small-agent status:** NoctusAI's classification under Res. CD/ANPD 2/2022 is **not recorded in KB** —
record it once (owner + legal) so the doubled deadline is a fact, not an assumption.

## 6 · Communication templates (pt-BR)

### 6.1 ANPD (comunicação preliminar)
> **Assunto:** Comunicação de incidente de segurança com dados pessoais — [controlador], [data]
>
> 1. **Controlador:** [razão social, CNPJ, endereço]; **encarregado:** [nome, contato].
> 2. **Ciência do incidente:** [data/hora UTC-3 de `t_conhecimento`] e como foi detectado.
> 3. **Descrição:** [o que aconteceu, por qual meio, período de exposição].
> 4. **Dados e titulares afetados:** [categorias de dados; dados sensíveis/financeiros/de autenticação: sim/não; número estimado de titulares; menores/idosos: sim/não].
> 5. **Riscos e possíveis danos:** [avaliação conforme art. 5 da Res. CD/ANPD 15/2024].
> 6. **Medidas adotadas:** [contenção, correção, prevenção de recorrência, com datas].
> 7. **Comunicação aos titulares:** [realizada em / prevista para; meio].
> 8. **Motivo de eventual atraso:** [se houver].
> Informações complementares serão enviadas no prazo regulamentar.

(Channel: ANPD's electronic petition form — **re-verify** the current form/URL at the time.)

### 6.2 Titulares
> **Assunto:** Aviso sobre incidente de segurança envolvendo seus dados
>
> Olá, [nome]. Em [data] identificamos um incidente de segurança que pode ter exposto os seguintes dados
> seus: [lista em linguagem simples]. **O que aconteceu:** [uma ou duas frases]. **O que já fizemos:**
> [medidas]. **O que recomendamos que você faça:** [ex.: desconfiar de contatos pedindo pagamento/PIX em
> nosso nome; trocar senha]. **Riscos possíveis:** [em linguagem simples]. Dúvidas: [canal do
> encarregado]. Pedimos desculpas pelo ocorrido.

### 6.3 Operador ⇒ controlador (cliente)
> **Assunto:** Incidente de segurança na plataforma NoctusAI — informações para sua avaliação
>
> Prezados, como operadores dos dados tratados em [produto], informamos que em [data/hora] tomamos
> ciência de [descrição]. Dados possivelmente afetados: [categorias, volume, período]. Medidas já
> adotadas: [lista]. Evidências disponíveis: [registros de acesso, janela]. Ficamos à disposição para
> apoiar sua avaliação de risco e eventuais comunicações à ANPD e aos titulares.

### 6.4 Interno (status SEV1/SEV2)
> **[SEVn] [título] — atualização [hh:mm]** · Situação: [contido/em análise/resolvido] · Escopo
> conhecido: [...] · Desconhecido: [...] · Próximas ações (dono, prazo): [...] · Relógio LGPD: ciência
> em [data/hora]; prazo ANPD [data] (dias úteis [x/3 ou x/6]).

## 7 · Evidence preservation

- **Before any destructive action:** capture, then contain. `noctus.vps.logs` (save output), `noctus.vps.inspect`,
  `noctus.vps.ps`; keep the running image (`deploy_image` keeps `:previous`; do not `noctus.vps.prune`
  during an incident); Supabase logs export (API/Storage/Auth) for the window; Cloudflare logs if available.
- **Hash what you keep** (`sha256sum`), record who/when/where in the timeline (chain of custody).
- **Times in UTC** with source; note clock sources.
- **No personal data in git/ledgers** — the register holds ids, counts, categories (`check_ledger_pii`
  refuses CPF/phone/e-mail at write time); raw evidence with personal data stays in restricted storage
  outside the repo with a retention date.
- Keep evidence at least as long as the register (≥ 5 years) when it supports the assessment.

## 8 · Post-incident review (blameless, within 5 business days)

1. Timeline (detection ⇒ containment ⇒ recovery), with time-to-detect / time-to-contain.
2. Root cause at the right level (seed default? missing gate? wrong assumption?) — 5 whys.
3. What the gates missed and why (a keeper with a blind spot is the most valuable finding).
4. Actions with owners: fix, **keeper** (s4) or checklist line (s3), KB update — the house loop
   incident ⇒ checklist line ⇒ keeper (`KB § PATTERNS/security/appsec-craft-canon.md` §13 table gains a row).
5. Register entry closed with the final assessment.

## 9 · Register schema and the retroactive entry

**Schema (one JSON object per incident, PII-free).**
`id` · `t_deteccao` · `t_conhecimento` · `t_contencao` · `produto` · `descricao` · `vetor`
(STRIDE letter + route) · `categorias_dados` · `titulares_estimados` · `criterios_art5` (list) ·
`risco_relevante` (bool + `fundamentacao`) · `papel` (controlador/operador) · `comunicado_anpd` (data or
`nao` + motivo) · `comunicado_titulares` · `medidas` · `evidencias` (locations + hashes) · `revisao`
(link) · `registrado_em` · `reter_ate` (≥ 5 years).

**Retroactive entry owed — erp-certidoes (2026-09-17), fields known today:**
`produto` erp-imobiliario · `vetor` I / Storage `/object/public/` route · `categorias_dados` CPF, nome
completo, débitos/restrições (financial ⇒ art. 5 criterion) · `titulares_estimados` ≤ people named in
102 objects (count from the DB, not from memory) · `t_contencao` 2026-09-17 (buckets flipped private,
migration `048_storage_no_public_buckets.sql`) · **unknown:** exposure start (bucket public since
migration 001/011 — date from git), evidence of access (Supabase Storage logs for the window, if still
retained), `papel` (is the client imobiliária the controller?), `risco_relevante` decision. Owner +
legal decide; `security` assembles the evidence. Tracked as agent-refinement follow-up #7.

## 10 · Hand-off — legal / privacy advisor

Agent `legal-advisor` (hired 2026-11-05) answered these from the DOU primary text in
`KB § PATTERNS/legal/lgpd-privacy-program.md` (incident communication + register sections) — that
doc wins on the legal side; this list stays as the hand-off record:
1. Exact Res. 15/2024 article/paragraph numbers for complementation (20 business days) and the
   titulares-notice declaration; full art. 10 register field list (read the DOU text).
2. NoctusAI's agente de pequeno porte status (Res. CD/ANPD 2/2022) and its exclusions.
3. Controller/operator mapping per product, and the operator's notification duty and timing toward the
   controller (contracts/DPAs).
4. Appointment and publication of the encarregado (Art. 41) and the titulares channel.
5. The erp-certidoes retroactive assessment (§9).
6. International transfer basis for LLM providers (Art. 33 + Res. CD/ANPD 19/2024 SCCs) — touches
   every incident involving an LLM provider.
7. The ANPD communication channel/form in force.

`security` keeps: classification, technical scope, evidence, containment advice. The advisor takes: the
legal reading, the communication decision support, the register as a program.

## Sources

Accessed 2026-11-05.
- NIST SP 800-61 Rev. 3 (April 2025), *Incident Response Recommendations and Considerations for
  Cybersecurity Risk Management: A CSF 2.0 Community Profile* — https://csrc.nist.gov/pubs/sp/800/61/r3/final — CSF 2.0 alignment (fetched).
- LGPD, Lei 13.709/2018 — https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm — Arts. 5, 37, 41, 46, 48 (audit-verified).
- Res. CD/ANPD 15/2024 (text) — https://www.legisweb.com.br/legislacao/?id=458235 — arts. 5, 6 (§8), 9 (§1, §6), 10 (fetched; secondary host — DOU fetch failed, **re-verify** at https://www.in.gov.br/en/web/dou/-/resolucao-cd/anpd-n-15-de-24-de-abril-de-2024-556243024).
- Mattos Filho, analysis of Res. 15/2024 — https://www.mattosfilho.com.br/unico/regulamento-incidente-seguranca/ — 20-business-day complementation, register ≥ 5 years (audit-verified via search; secondary — **re-verify**).
- Res. CD/ANPD 19/2024 analysis (international transfer) — https://www.mattosfilho.com.br/unico/regulamentacao-transferencia-internacional-dados/ — SCCs (secondary — **re-verify**).

## Composes-with

`KB § PATTERNS/security/appsec-craft-canon.md` · `KB § PATTERNS/security/lgpd.md` ·
`KB § PATTERNS/security/ai-agent-security-canon.md` (agent incidents) · `KB § PATTERNS/devops/prod-watchdog.md` ·
agent `security` (owner) · agent `devops-engineer` (mechanics) · agent `agents-security`.
