# Commerce P4 — questions for an accountant (contador)

> **Why this file exists.** The noc owner is not an accountant (*"eu sou leigo"*, 2026-10-14) and set several finance choices "from his head so we can move on and refine later". Every such choice is **provisional** until an accountant confirms it. This list is what to hand a contador, together with the DRE and the CSV/OFX exports. The same list is surfaced inside the product (D47 "accountant checklist").
> Research behind it: primary sources only, accessed 2026-10-14 (summary in §3). Nothing below is a recommendation from us — where the sources are silent, it says so.

## 0 · Accountant-agent review (2026-10-14) — current defaults

The project's `accountant` agent re-researched every item with practice sources (`KB § PATTERNS/finance/dre-structure.md`); the owner accepted its re-answers (D53–D56). The table in §1 is the history; **these are the defaults now, all still provisional until the store's contador confirms**:

| # | Current default (decision) | Strongest source |
|---|---|---|
| Q1 | Gateway/MDR fees → Despesas com vendas; **antecipação → Despesas financeiras**; chargeback fee → Despesas com vendas (D55) | [publicação profissional] — practice is split |
| Q2 | Buyer-paid installment interest → **Receita bruta** (own detail row), settable to Receitas financeiras (D54) | NBC TG 1002 §11.3 + §23.2; tax: SC COSIT 94/2025 |
| Q3 | Chargebacks → Deduções (D55) | open — no Brazilian source found |
| Q4 | **Simples: whole DAS → Deduções** (split IRPJ/CSLL optional); **MEI: DAS-MEI → Despesas administrativas**; Presumido: revenue taxes → Deduções, IRPJ/CSLL → tributos sobre o lucro (D53) | ITG 1000 Anexo 3 footnote; NBC TG 1002 §29.3; NBC TG 1001 §23/§29; Sebrae |
| Q5 | Custo = categories mapped to cost_of_sales; without stock control CMV = purchases of the month (warning) | NBC TG 1002 §5.1(d); approximation open |
| Q6 | By function + contribution-margin managerial view | NBC TG 1001 §5.4; Sebrae |
| Q7 | Split defaults + new categories (D56; table in the KB doc §2a) | mixed |

**Ask your contador (current list):** 1) DAS whole vs split · 2) installment interest in revenue vs financeira · 3) chargeback: deduction vs loss, and does it reduce the Simples base? · 4) gateway fee: vendas vs financeira · 5) CMV by purchases acceptable? · 6) livro-caixa vs full bookkeeping (profit distribution) · 7) IBS/CBS inside or outside the DAS from 2027 (CGSN 190/2026 art. 5 XVI) · 8) what an MEI must keep from 2027 · 9) Presumido: ECD exemption.

## 1 · Provisional choices to confirm (owner's first answers — superseded by §0)

| # | Item | Owner's provisional choice | What the sources say |
|---|---|---|---|
| Q1 (D44) | Card / Pix / boleto **gateway fees** (Asaas) | **Despesas com vendas** (DRE line f) | No norm; practice split (see §0). Tax side only: Solução de Consulta Cosit 143/2021 — the commission fee cannot be excluded from the Simples Nacional base. |
| Q2 (D45) | **Installment interest** paid by the buyer (4x–12x, 1.99 %/month default) | Separated from the sale: **Receitas financeiras** (line j) | CPC 47 §60/§65 require separating a significant financing component; but NBC TG 1002 §11.3 (the standard for these stores) does not require present-value discounting for terms ≤ 1 year. Card installments specifically: not found. |
| Q3 (D46) | **Chargebacks** (buyer disputes a card payment and wins) | **Deduções da receita bruta** (line b), like a cancelled sale | No source found. |
| Q4 (D51) | **DAS** (Simples Nacional tax) | **Undecided** — shown as "awaiting classification" | NBC TG 1002 §29.3 (and 1001 §29.3(b)) allow BOTH: tax on profit (line m, main rule) or deduction from gross revenue (line b, alternative for Simples). The revoked ITG 1000 required the deduction. |
| Q5 (D50) | Which expense categories are **custo** (line d, CMV/CSV) vs operating expense | Store marks categories as "custo" | Lines from NBC TG 1002 §5.1(d); what counts as cost per business is an accounting judgment. |
| Q6 (D49) | Expense grouping for stores ≤ R$4.8M | **By function** (vendas / administrativas / outras) with nature (Pessoal, Aluguel…) as detail | NBC TG 1002 leaves it open; NBC TG 1001 §5.4 requires function above R$4.8M. |
| Q7 | Default category → DRE line mapping (CONTRACT §10.3) | Pending owner review | Accounting judgment per category. |

## 2 · Questions only an accountant can answer for a specific store

- Should this store keep **full accounting (escrituração contábil)** or only the **Livro Caixa**? (LC 123 art. 26 §2 / art. 27; CGSN 140 art. 63.) It matters for distributing profit tax-free above the presumed percentage (LC 123 art. 14 §2; CGSN 140 art. 145 §2).
- **MEI** stores: bookkeeping is waived (CGSN 140 art. 106 §1); the monthly gross-revenue report requirement changes from 2027-01-01 (CGSN 190/2026). What does the store still need to keep?
- **Lucro Presumido** stores: is the ECD (digital bookkeeping) exemption still met? (IN RFB 2.003/2021 art. 3 §1 V and §3.)
- **IBS/CBS inside the Simples DAS:** how should they be presented? No source found (CFC Orientação Técnica 1/2026 covers only the regular regime, and is non-binding).

## 3 · Sources (accessed 2026-10-14)

- Lei 6.404/1976 art. 187 — https://www.planalto.gov.br/ccivil_03/leis/l6404consol.htm
- Lei 11.638/2007 art. 3 — https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2007/lei/l11638.htm
- Código Civil arts. 1.053, 1.179, 1.189 — https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm
- LC 123/2006 arts. 3, 14, 26, 27, 68 — https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm
- NBC TG 1002 (microentidades, in force since 2023-01-01, revenue ≤ R$4.8M) — https://www1.cfc.org.br/sisweb/SRE/docs/NBCTG1002.pdf
- NBC TG 1001 (pequenas empresas) — https://www1.cfc.org.br/sisweb/SRE/docs/NBCTG1001.pdf
- NBC TG 1000 (R1) — https://www1.cfc.org.br/sisweb/SRE/docs/NBCTG1000(R1).pdf
- ITG 1000 (revoked) — https://www2.cfc.org.br/sisweb/sre/detalhes_sre.aspx?Codigo=2012/001418
- CPC 26 (R1) — https://conteudo.cvm.gov.br/cvm_institucional/export/sites/cvm/menu/regulados/normascontabeis/cpc/CPC_26_R1_rev_14.pdf
- CPC 47 — https://conteudo.cvm.gov.br/cvm_institucional/export/sites/cvm/menu/regulados/normascontabeis/cpc/CPC_47_Rev_14.pdf
- CGSN 140/2018 — https://normasinternet2.receita.fazenda.gov.br/api/consulta-externa/ato/92278/visao/vigente
- CGSN 190/2026 — https://normasinternet2.receita.fazenda.gov.br/api/consulta-externa/ato/152832/visao/vigente
- IN RFB 2.003/2021 — https://normasinternet2.receita.fazenda.gov.br/api/consulta-externa/ato/114965/visao/vigente
- SC Cosit 143/2021 — https://normasinternet2.receita.fazenda.gov.br/api/consulta-externa/ato/120688/visao/vigente
- CFC Orientação Técnica 1/2026 (IBS/CBS, regular regime, non-binding) — https://cfc.org.br/wp-content/uploads/2026/07/CFC_Orientacao_Tecnica.pdf

Not verified: NBC TG 51 revoking NBC TG 26 (news only); what replaces the MEI monthly report from 2027; the exact date of CFC OT 1/2026; whether NBC TG 1000 revision 23 changed section 5.
