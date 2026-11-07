# Brazilian tax & accounting advisor canon — how the accountant reads the law, the regimes, the Reforma and the finance organ

> **Owner:** agent `accountant` (advisor). **Consumers:** the owner (stores' and NoctusAI's own tax questions), `noctusai_lib.domain.finance` (simples_base, mei, livro_caixa, dominio, accountant checklist), commerce P4.
> **Status:** craft canon, 2026-11-05 (agent-refinement W1-S6). Evidence tiers as in `KB § PATTERNS/finance/dre-structure.md` §0. **Not a substitute for a contador (CRC)** — §8 says when one is required.

**What this is.** The advisor's working canon for Brazilian small-business tax and accounting: how norms rank, what each regime implies, the Simples mechanics (Anexos, Fator R), the Reforma Tributária calendar 2026–2033 with split payment, the fiscal documents (NF-e, NFS-e Nacional), the statutory statements, and what each finance-organ module implements.

**Why it exists.** The audit found the agent excellent on epistemics but scoped to one statement (the DRE) for one client type (stores). It had no Reforma calendar (the biggest date in the domain), no Fator R (which decides NoctusAI's *own* Simples rate), no NFS-e status, and five organ modules with no owned depth. The mission now includes NoctusAI's own finances (owner decision 2026-11-05).

**How to use it.** `dre-structure.md` stays the canonical DRE line doc — read it first for any "which line?" question. Use this doc for "which rule, which year, which regime, which document?" and for what the code does. Every answer: state **which year's rules** it holds for (§3), tier every claim, end with what the contador must confirm (§8).

## Contents
0. Standard term ↔ house term · 1. Norm hierarchy and source protocol · 2. Regimes · 3. Reforma Tributária 2026–2033 · 4. Fiscal documents · 5. Statutory statements · 6. The finance organ, module by module · 7. Checklists and answer template · 8. When a contador (CRC) is required · 9. Worked examples · 10. Anti-patterns · 11. Sources · 12. Re-verify list · 13. NoctusAI company file · 14. Abertura de CNPJ

## 0 · Standard term ↔ house term

| Standard term | House term / code |
|---|---|
| Regime tributário | `TaxRegime` = `mei` · `simples` · `presumido` · `unknown` (`domain/finance/types.py:115-121`; no `real` yet) |
| Receita bruta (Simples base) | `GET /reports/simples-base` (`simples_base.py`), separate from the DRE |
| Regime de caixa / competência (Simples) | `basis_of(month)` → `cash` ≤ 2026-12, `invoice` ≥ 2027-01 (`INVOICE_BASIS_FROM`, `simples_base.py:26,40-42`) |
| DRE (Lei 6.404 art. 187; NBC TG 1002 §5.1) | `DreLine` enum (`types.py:98-112`); report `reports.dre` (`reports.py:122`) |
| Demonstração dos Fluxos de Caixa | `reports.cashflow` (`reports.py:52`) — realized + projected by month |
| Livro-caixa (LC 123 art. 26 §2) | `GET /reports/livro-caixa` (`livro_caixa.py`) |
| Relatório Mensal de Receitas Brutas (MEI) | `GET /reports/mei-monthly` (`mei.py`) |
| Lançamentos contábeis para o escritório | `GET /exports/dominio.txt` (`dominio.py`, `DOMINIO-LAYOUT.md`) |
| Checklist do contador | `GET /accountant-checklist` (`accountant.py`, questions Q1–Q10) |
| Acesso do contador | permission `finance.accountant_read:<org_id>` (`ACCOUNTANT-ACCESS.md`) |
| Anexo (Simples) | not modelled in code yet — **note:** `ANEXO_INVALIDO` in `errors.py:24` is a file *attachment* error (`attachments.py:68`), not a Simples Anexo |

## 1 · Norm hierarchy and source protocol

**Hierarchy (highest first).** Constituição / Emenda Constitucional (incl. ADCT) → Lei Complementar (LC 123, LC 214) → Lei ordinária (Lei 6.404, Código Civil) → Decreto → **Resolução CGSN** (Simples) → **Instrução Normativa RFB** → **Solução de Consulta** (COSIT / regional) → **NBC / ITG (CFC)** for accounting → Sebrae → professional publications.
- Tax law and accounting standards answer different questions: "is it receita bruta for the Simples base?" (tax: LC/Res. CGSN/SC) vs "which DRE line?" (accounting: Lei 6.404 + NBC TG). Never let one answer the other (dre-structure §4 h is the house example).
- **A Solução de Consulta binds the consulente who asked;** for anyone else it is a strong signal of how the RFB reads the rule, tier [órgão oficial], not a rule. Quote its number, year and the exact sentence.

**Owner source tiers (2026-11-07).** Every claim carries ONE tag, plus URL and access date:
`[norma]` > `[órgão oficial]` > `[publicação técnica/científica]` (peer-reviewed or institutional: CFC/CRC, FGV, IBPT papers) > `[opinião de especialista]` (named author with credentials, cross-checked by **≥2 independent sources**) > `[blog/prática]` (a pointer to find the primary, **never the basis**). The norm order above is unchanged; older `[publicação profissional]` tags read as `[publicação técnica/científica]` only when institutional, else `[blog/prática]`.
- **Conflicts between sources are stated explicitly** ("A diz X, B diz Y; prevalece Z por hierarquia, ou fica aberto") — never resolved silently.
- All research is online; unreachable primary ⇒ tag the substitute honestly and mark **open**.

**Source protocol.**
1. Read the primary text: Planalto (CF/EC/LC/Lei), `normasinternet2.receita.fazenda.gov.br` (Res. CGSN, IN, SC), CFC (NBC). A mirror (`normaslegais`, `ibet`, accounting blogs) is at best [publicação profissional] and is replaced when the primary is reachable.
2. Planalto pages carry several versions of amended articles; quote the text marked in force and note the amending act (e.g. LC 214 as amended by LC 227/2026).
3. Date-stamp every claim (accessed date) and re-check anything older than a year (§12).
4. No source ⇒ say **open**, propose the question for the contador.

## 2 · Regimes

| Regime | Who | Tax on revenue | DRE consequence (see dre-structure §3) |
|---|---|---|---|
| **MEI** | individual micro-entrepreneur | fixed monthly DAS-MEI | DAS-MEI → administrative (fixed); managerial DRE only (no statutory DRE duty) |
| **Simples Nacional — ME** | receita bruta ≤ R$ 360.000,00/ano (LC 123 art. 3 I) [norma] | DAS = effective rate × monthly revenue | whole DAS → Deduções (product default); split optional |
| **Simples Nacional — EPP** | > R$ 360 mil and ≤ R$ 4.800.000,00 (art. 3 II, LC 155/2016) [norma] | same | same |
| **Lucro Presumido** | above Simples, or by choice | PIS/Cofins (cumulative), ISS/ICMS; IRPJ/CSLL on presumed profit | PIS/Cofins/ISS/ICMS → Deduções; IRPJ/CSLL → line 11 |
| **Lucro Real** | mandatory above thresholds / by choice | non-cumulative PIS/Cofins; IRPJ/CSLL on book profit | not modelled (`TaxRegime` has no `real`) — answer, but flag the code gap |

**Simples mechanics.**
- **Effective rate.** The nominal rate of the bracket is set by the receita bruta accumulated in the **12 months before** the apuração period (RBT12; LC 123 art. 18 §1) and converted to an effective rate by the art. 18 §1-A formula: `(RBT12 × Aliq − PD) / RBT12` [norma; formula structure confirmed on Planalto, coefficients per Anexo table — re-verify the table before computing a real DAS].
- **Anexos I–V.** I commerce · II industry · III/IV/V services. Anexo IV services pay the employer social contribution (CPP) outside the DAS.
- **Fator R (LC 123 art. 18 §§5-J, 5-K, 5-M)** [norma]: for the services listed in §5-I, the ratio **folha de salários / receita bruta, both over the 12 months before the apuração period** (§5-K), decides the Anexo: **≥ 28% ⇒ Anexo III** (§5-J), **< 28% ⇒ Anexo V** (§5-M). Folha includes salaries, pró-labore and the CPP/FGTS actually paid [publicação profissional; statutory definition in art. 18 — re-verify the paragraph].
- **Software / SaaS (verified chain, advisory 2026-11-07).** LC 123 art. 18 §5-D IV/V (software development/licensing services) + §5-M II; Res. CGSN 140 art. 25 §1 V d/e/f/u ⇒ **Anexo III if Fator R ≥ 0,28, else Anexo V** [norma]. The earlier premise "Anexo VI lists the CNAEs" is **wrong**: Anexo VI lists the CNAEs that **bar entry** to the Simples. Which CNAE a company registers is still a decision to take with the §8 list in view.
- **Fator R — folha rules (LC 123 art. 26 §§3–7)** [norma, verified in the advisory]: what the folha excludes; companies with **less than 13 months** of activity use the 0,28/0,01 rules for the ratio; the **zero-folha** and **zero-revenue** cases have their own treatment. Quote the paragraph from Planalto/Receita before computing a real DAS.
- **From 2027 the Simples base is "faturamento, entrega ou execução, o que primeiro ocorrer"** (Res. CGSN 140 art. 2 §8 as amended by Res. CGSN 190/2026) and **caixa ends** [órgão oficial].
- **First-bracket nominal rates** (up to R$ 180 mil RBT12): Anexo III 6%, Anexo V 15,5% [publicação profissional; LC 123 Anexos III/V tables not re-fetched].
- **DAS repartição.** Each Anexo table splits the DAS into IRPJ/CSLL/Cofins/PIS/CPP/ISS-ICMS percentages; the house DRE uses it only when a store splits the DAS (`dre_help.py`, `INCOME_TAXES` "percentual de repartição do seu anexo"; accountant Q4).

## 3 · Reforma Tributária 2026–2033

Primary texts: EC 132/2023 (incl. ADCT arts. 125–129) and LC 214/2025 (as amended by LC 227/2026). **Every answer names the year it holds for.**

| Year | What changes | Source | Tier |
|---|---|---|---|
| **2026** | Test year: IBS at 0,1% (state) and CBS at 0,9%, offsettable against PIS/Cofins | ADCT art. 125 | [norma] |
| **2027** | CBS charged; contributions on revenue (CF art. 195 I "b" and IV — the PIS/Cofins base) revoked; IPI zeroed except Zona Franca de Manaus incentives; Imposto Seletivo starts | EC 132 art. 22 I; ADCT art. 126 | [norma] |
| **2027–2028** | IBS at 0,05% state + 0,05% municipal; CBS reduced by 0,1 p.p. | ADCT art. 127 | [norma] |
| **2027** (Simples) | IBS/CBS rules for Simples optantes take effect 2027-01-01; Simples base moves to the invoice moment ("no momento do faturamento", Res. CGSN 190/2026 art. 2 §8; effects art. 9) | Res. CGSN 190/2026 (dre-structure §6); CRC-MS note | [órgão oficial]; [publicação profissional] |
| **2029–2032** | ICMS and ISS charged at 9/10, 8/10, 7/10, 6/10 of their own rates; IBS rises correspondingly (LC 214 art. 174 §4 caps — audit-verified) | ADCT art. 128 | [norma] |
| **2033** | ICMS and ISS revoked (CF arts. 155 II, 156 III and related) | EC 132 art. 22 II | [norma] |

**Simples and IBS/CBS.**
- A Simples optante may opt to apurar and recolher IBS/CBS **by the regular regime** instead of inside the DAS (LC 214 art. 41 §3; exercised under LC 123, §4) [norma]; the CGSN rule lets them be paid outside the DAS (Res. CGSN 190/2026 art. 5 XVI) [órgão oficial]. A Simples optante that received a refund of these taxes in the current or prior year cannot leave the regular regime (art. 41 §5).
- **Option window:** the IBS/CBS option for **H1-2027 closed Sep/Oct 2026** [órgão oficial, advisory]. Res. CGSN 194/2026 is **unverified — open**. The H2-2027 window is **open** (§12).
- **Credit consequence for B2B buyers:** if IBS/CBS stay inside the DAS, the optante takes no credits (art. 47 §9 I) and a regular-regime buyer credits only the amount paid through the Simples (art. 47 §9 II) [norma]. That is why B2B service sellers (NoctusAI's own case) may prefer the regular IBS/CBS regime — a contador decision.
- **DRE consequence:** inside the DAS ⇒ nothing changes in the Deduções line. Outside ⇒ IBS/CBS become their own Deduções rows (accountant Q7 is open on presentation).

**Split payment (LC 214 arts. 31–35)** [norma].
- Electronic-payment providers and payment-system operators **segregate and remit** IBS/CBS to the Comitê Gestor and RFB **at the financial settlement** of the transaction (art. 31; timing art. 34 I). Installments: remitted proportionally at each installment's settlement (art. 34 II).
- A **simplified procedure** is optional: a preset percentage of the operation, by sector or taxpayer, unrelated to the actual debits (art. 33 §§1–2); when the buyer is in the regular regime, the simplified remittance generates no credit to the buyer (art. 33 §7 II).
- Arts. 31–35 carry no Simples-specific rule.
- **Gateway impact (Asaas, our gateway).** From go-live, part of each settled charge may be withheld before it reaches the store, so: (a) settlement amount ≠ charge amount even without fees; (b) the ledger must book the withheld IBS/CBS as tax, not as a gateway fee; (c) installment charges withhold per installment. Go-live date and Asaas' mechanics: **open — ask Asaas and the contador; re-verify the implementation calendar.**
- **Code impact (proposal, not done):** `TaxRegime` and `DreLine` will need IBS/CBS deduction rows; `gateway_sync` must distinguish split-payment withholding from MDR.

## 4 · Fiscal documents

- **NF-e** (goods, state) and **NFS-e** (services, municipal). From 2027 the Simples base is the invoice moment, so **the invoice issue date becomes a tax input**: today `simples_base.py` approximates it with the receivable's `competence_month` and says so in `BASIS_NOTE` (`simples_base.py:8-9,36-38`).
- **NFS-e Nacional (Emissor Nacional).** gov.br NFS-e news: on 28/04/2026, ME/EPP Simples optantes were to issue through the Emissor Nacional from 01/09/2026; on 11/08/2026, "Comitê Gestor do Simples Nacional prorroga a obrigatoriedade…" [órgão oficial — new date not shown on the listing]. **Verified (advisory 2026-11-07): NFS-e Nacional is mandatory for ME/EPP from 01/11/2026 (Res. CGSN 191/2026)** — in force on this doc's date.
- **API shape:** one **signed DPS per POST**, ICP-Brasil mTLS (manual dos contribuintes v1.2, Oct 2025) [órgão oficial]; **one NFS-e per tomador per charge**.
- Early adoption: some municipalities let optantes adopt early (gov.br, 28/09/2026). LC 214 sanctions municipalities that do not adopt (audit-verified).
- **Automation rule.** Any automation touching the Simples base from 2027 must carry the NF-e/NFS-e issue date; until it does, every figure says it is an approximation (the house already does this — keep it).

## 5 · Statutory statements

- **Lei 6.404/1976 art. 187** [norma] — the DRE "discriminará": I receita bruta, deduções, abatimentos e impostos; II receita líquida, custo das mercadorias e serviços vendidos e lucro bruto; III despesas com vendas, despesas financeiras (deduzidas das receitas), gerais e administrativas e outras operacionais; IV lucro ou prejuízo operacional, outras receitas e outras despesas; V resultado antes do IR e a provisão para o imposto; VI participações (debêntures, empregados, administradores, partes beneficiárias); VII lucro ou prejuízo líquido e o montante por ação. It is the statutory skeleton the NBC TG lines descend from; the house `DreLine` order follows it.
- **NBC TG 1002 (microentidades)** — dated 18/11/2021, DOU 09/12/2021, for fiscal years from 01/01/2023, receita bruta up to R$ 4,8 mi/ano; above that for two consecutive years ⇒ NBC TG 1001 [norma; CFC-hosted draft + professional mirrors — read the final CFC text before quoting a paragraph]. **NBC TG 1001** (pequenas e médias) and **NBC TG 1000** (PMEs, larger) above that [norma; scope boundaries — re-verify at CFC]. **ITG 1000** (Res. CFC 1.418/2012) is revoked from 2023 but its model DRE is still practitioner default (dre-structure §1).
- **DFC.** Statements are on accrual; only the cash-flow statement is on cash (dre-structure §6). Managerial cash views and the cash↔accrual bridge: `KB § PATTERNS/finance/managerial-and-saas-metrics.md`.
- **Livro-caixa.** ME/EPP (non-MEI) must keep at least a livro-caixa with all financial and bank movement (LC 123 art. 26 §2) [norma, verified on Planalto 2026-11-05].

## 6 · The finance organ, module by module (`seed/lib/backend/noctusai_lib/domain/finance/`)

| Module | What it does | Legal anchor (as the code cites it) | Known gaps / open |
|---|---|---|---|
| `simples_base.py` | Simples receita bruta per month: sales + buyer-paid installment interest, commission NOT netted, refunds out, chargebacks reported apart; cash ≤ 2026-12, invoice ≥ 2027-01; splits a period crossing the boundary and warns `transicao_caixa_faturamento` | SC COSIT 94/2025 & 143/2021; Res. CGSN 190/2026 art. 2 §8, art. 9 | invoice moment approximated by `competence_month` (no NF issue date); 2026 sales received in 2027 are the contador's call; IBS/CBS not modelled |
| `mei.py` | Relatório Mensal de Receitas Brutas: cash basis, by activity group (comércio/indústria/serviços), "com/sem documento fiscal" | Res. CGSN 140 art. 106 (+108, 109), Annex X | **field list UNVERIFIED** against the official Annex X (`FIELDS` is the one place to fix); `has_invoice` manual (`NOC-REMEDIATE[finance-mei-has-invoice-from-commerce]`); MEI duty changes 2027-01-01 (Q8) |
| `livro_caixa.py` | Livro Caixa view over the ledger: all accounts, transfers excluded, saldo anterior, capped exports (422 over cap, never truncated) | LC 123 art. 26 §2; Res. CGSN 140 art. 63 | DB-side aggregate for large orgs (`NOC-REMEDIATE[finance-report-sql-aggregates]`) |
| `dominio.py` + `DOMINIO-LAYOUT.md` | Domínio "leiaute com separador" batch entries (6000/6100), cash basis, contador's accounting codes; refuses 422 when a code is missing | Thomson Reuters layout (solução 672) + official sample file | items marked UNVERIFIED in `DOMINIO-LAYOUT.md` |
| `accountant.py` | Checklist for the contador: provisional choices, open questions Q1–Q10, export links; disclaimer (never signs/files/chooses a regime) | Código Civil art. 1.182; LC 123 art. 26 §2 | questions mirror `projects/commerce-seed-p4/ACCOUNTANT-QUESTIONS.md` |
| `ACCOUNTANT-ACCESS.md` | Read-only, per-org accountant grant (`finance.accountant_read:<org_id>`); CPF/CNPJ stay masked | LGPD (via security) | — |
| `reports.py` | `cashflow` (realized + projected), `dre` (statement / managerial views), `aging` | NBC TG 1002 §5.1; Lei 6.404 art. 187 | — |

**Rule.** Before advising an automation, read the module (codebase = source of truth) and say which row above it changes.

## 7 · Checklists and answer template

**Question intake.**
```
- [ ] Whose books? (a store org · NoctusAI itself · the owner as a person)
- [ ] Regime + Anexo (+ CNAE for services) · RBT12 · year the answer must hold for
- [ ] Tax question or accounting question (or both — answer separately)
- [ ] Already in dre-structure.md / this canon? cite; else research (primary text first)
- [ ] Touches the code? read the module (§6)
```

**Answer template (pt-BR for the owner).**
```
Resposta curta: …
Vale para: <ano/regime>.
Por quê (com fontes): 1. … [norma] <link, acesso AAAA-MM-DD> 2. … [órgão oficial] …
Recomendação padrão: … (provisória/por loja se a prática diverge)
Em aberto / pergunte ao seu contador: …
O que o contador precisa confirmar ou assinar: …
Mudança proposta no doc/dado: …
```

## 8 · When a human contador (CRC) is required

The agent always says so — the list in `dre-structure.md` §7 (bookkeeping responsibility, livro-caixa minimum, profit distribution above the presumed limit, filings DEFIS/ECD/ECF, regime choice, anything signed) plus, from this canon:
- **Anexo and CNAE classification**, and therefore Fator R's effect on a real DAS.
- **Pró-labore level** as a Fator R lever (also a social-security and personal-income decision).
- **IBS/CBS inside vs outside the DAS** from 2027.
- **Split-payment reconciliation** policy once it goes live.
- **The 2026→2027 transition** (2026 sales received in 2027).

**No-contador mode (owner has none, 2026-11-07).** The agent is the **primary advisor**: it gives a recommended decision with tiered sources, never "ask your contador" as the answer. It keeps a running list **"pendências que exigem CRC por lei"** — ONLY what the law makes a registered contador's act or signature. Which acts need a CRC for an ME/EPP in the Simples vs not is researched and cited per item when it arises; starting points to verify (do not assert without the source): Decreto-Lei 9.295/1946 (privativo do contabilista) [norma — verify]; ECD/ECF signature where the obligation applies (Simples optantes are generally dispensed — verify IN RFB 2.003/2021 and 2.004/2021); DEFIS responsibility — **open**. The agent says plainly when the owner must hire a contador or an online accounting service and **what to look for** (CRC active, scope: abertura/escrituração/folha/fiscal, e-CAC procuração, price transparency, data-export rights, LGPD clause) — **neutral, no vendor names or ads**.

## 9 · Worked examples

### A · Installment interest after the reform (a store)

**Question:** "A loja vende parcelado com juros. O que muda em 2027?"
- **Today (settled):** buyer-paid installment interest is receita bruta for the Simples base — SC COSIT 94/2025 [órgão oficial]; `simples_base.py` counts the `:interest` rows even when the store maps the DRE line to financial revenue (test `seed/lib/backend/tests/domain/finance/test_dre_api.py:189`).
- **When (2027):** the base moves to the invoice moment (Res. CGSN 190/2026 art. 2 §8) [órgão oficial]. The code approximates the invoice moment with `competence_month` and says so (`BASIS_NOTE`) until the NF-e/NFS-e issue date is an input (§4).
- **What changes with IBS/CBS:** inside the DAS ⇒ nothing in the Deduções line. Outside (LC 214 art. 41 §3) ⇒ IBS/CBS become separate Deduções rows, and **split payment** withholds per installment at each settlement (LC 214 arts. 31, 34 II) [norma] — the Asaas settlement will then net tax as well as fees.
- **Open:** Asaas' split-payment mechanics and go-live; presentation of IBS/CBS in the DRE (Q7).
- **Contador:** the inside/outside-DAS choice; the 2026→2027 transition.

### B · NoctusAI's own Anexo (SaaS)

See `KB § PATTERNS/finance/managerial-and-saas-metrics.md` §9 — Fator R computed on NoctusAI's trailing-12-month figures, the Anexo III vs V delta, and the SaaS view next to it.

## 10 · Anti-patterns

- **Rate tables hard-coded in code** — rates and brackets are data with a source and a validity date.
- **Mirror-only citations** when the primary text is reachable.
- **Answering for the wrong year** (the 2026→2027 boundary flips the Simples base and the IBS/CBS rules).
- **Treating a Solução de Consulta as a rule** for a different taxpayer.
- **Letting the tax answer decide the DRE line** (or the reverse).
- **Deciding the Anexo, the regime or the pró-labore** instead of naming them as contador decisions.
- **Confusing `ANEXO_*` error codes (file attachments) with Simples Anexos.**

## 11 · Sources

| Title | URL | Supports | Accessed |
|---|---|---|---|
| Lei Complementar 123/2006, Planalto | https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm | §2 art. 3 I–II; art. 18 §1, §1-A, §5-D, §5-J, §5-K, §5-M; §5 art. 26 §2 | 2026-11-05 |
| Emenda Constitucional 132/2023, Planalto | https://www.planalto.gov.br/ccivil_03/constituicao/emendas/emc/emc132.htm | §3 ADCT arts. 125–128; EC art. 22 I–II | 2026-11-05 |
| Lei Complementar 214/2025, Planalto | https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm | §3 arts. 31, 33, 34 (split payment); art. 41 §§1–6; art. 47 §§3, 9; art. 174 §4 (audit-verified) | 2026-11-05 |
| Lei 6.404/1976 consolidated, Planalto | https://www.planalto.gov.br/ccivil_03/leis/l6404consol.htm | §5 art. 187 I–VII | 2026-11-05 |
| Portal NFS-e (gov.br) — notícias | https://www.gov.br/nfse/pt-br/noticias | §4 28/04/2026 obligation from 01/09/2026; 11/08/2026 postponement; 28/09/2026 early adoption | 2026-11-05 |
| CRC-MS — NFS-e Nacional obrigatória para ME/EPP a partir de 01/11/26 | https://crcms.org.br/?p=37798 | §4 new date 01/11/2026 (Res. CGSN 191/2026); IBS/CBS Simples rules from 2027-01-01 [publicação profissional — re-verify against the resolution] | 2026-11-05 (search result) |
| NBC TG 1002 — CFC-hosted draft (docx) | https://portalrestore.cfc.org.br/wp-content/uploads/2021/09/NBC-TG-1002-Microempresas.docx | §5 existence/scope; final text via https://www.normaslegais.com.br/legislacao/nbc-tg-1002-2021.htm (mirror) — date 18/11/2021, DOU 09/12/2021, effective 2023 | 2026-11-05 (search-confirmed) |
| Res. CGSN 190/2026 (official, Receita normas) | https://normasinternet2.receita.fazenda.gov.br/api/consulta-externa/ato/152832/visao/vigente | §3/§4 invoice moment from 2027; art. 5 XVI IBS/CBS outside DAS | 2026-10-14 (via dre-structure §6) |
| SC COSIT 94/2025 | https://www.normaslegais.com.br/legislacao/solucao-de-consulta-cosit-94-2025.htm | §9 A installment interest in receita bruta (mirror) | 2026-10-14 (via dre-structure §4) |
| Fator R / Anexo III vs V practice (Agilize; Contábeis) | https://agilize.com.br/blog/gestao-fiscal/anexo-iii-fator-r-6-de-imposto/ · https://www.contabeis.com.br/noticias/51679/o-que-e-fator-r-como-calcular | §2 software CNAEs Fator-R-sensitive; 6% vs 15,5% first bracket [publicação profissional] | 2026-11-05 (search result) |

## 12 · Re-verify list (date-watch)

- NFS-e Nacional obligation date for Simples ME/EPP (01/11/2026 per Res. CGSN 191/2026 — professional sources only). **Re-verify.**
- Split-payment implementation calendar and Asaas' mechanics.
- Res. CGSN 140 Anexo VI (CNAE → Anexo, Fator R flag) for IT CNAEs; LC 123 Anexos III/V tables; the folha-de-salários definition paragraph in art. 18.
- NBC TG 1000 / 1001 / 1002 scope boundaries — final CFC texts.
- Res. CGSN 190/2026 MEI changes from 2027 (accountant Q8).
- **Open (advisory 2026-11-07):** 2027 wording of the Fator R window; the H2-2027 IBS/CBS option window; Res. CGSN 194/2026 (unverified); SP / Cotia adherence to NFS-e Nacional.

## 13 · NoctusAI company file (as of 2026-11-07)

**State:** pre-CNPJ, **no revenue, no customers, no contador**. Nothing is due today; this list starts the day the CNPJ opens.
- **NFS-e Nacional** — mandatory for ME/EPP since 01/11/2026 (Res. CGSN 191/2026); Emissor Nacional or API (§4), the API path needs a certificado ICP-Brasil.
- **Fator R tracking** — monthly folha ÷ receita bruta, trailing 12 months; <13 months of activity use the art. 26 rules (§2); r ≥ 0,28 ⇒ Anexo III, else V. Illustration: `managerial-and-saas-metrics.md` §9.
- **IBS/CBS semester option** — inside vs outside the DAS; H1-2027 window closed, H2-2027 open (§3, §12); B2B buyers favour the regular regime (art. 47 §9).
- **Folha / pró-labore plan** — pró-labore is the Fator R lever and a social-security/IR decision; fix amount, start month and INSS at opening.
- **Pendências que exigem CRC por lei:** kept per §8; empty until a CNPJ exists.

## 14 · Abertura de CNPJ — decision checklist (playbook stub)

> **Deferred by owner — research when asked.** Checklist only; nothing below is researched or sourced yet.
- [ ] **Natureza jurídica:** SLU vs LTDA vs MEI eligibility for software. MEI does not allow CNAE 6201/6203/6204 (verify at the MEI CNAE annex when asked).
- [ ] **CNAE choice** (primary + secondary) and its Anexo/Fator R effect (§2).
- [ ] **Município and address:** Cotia / Carapicuíba / São Paulo; home-office address rules per municipality.
- [ ] **Simples opting window** (at opening vs January window) and impediments.
- [ ] **Pró-labore** amount and start (§13).
