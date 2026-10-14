# DRE structure — the NoctusAI store income statement (Brazil, small e-commerce)

> **Owner:** agent `accountant` (advisor). **Consumers:** `noctusai_lib.domain.finance` (DRE report, category→line mapping), commerce P4 (`projects/commerce-seed-p4/CONTRACT.md §10`), the owner's own bookkeeping questions.
> **Status:** research-backed design, 2026-10-14. Not a substitute for the store's contador — see §6.

## 0 · Evidence tiers (every claim below carries one)

| Tier | Meaning |
|---|---|
| **[norma]** | CFC standard (NBC TG / ITG), law (LC 123, Código Civil) — binding text, read in full |
| **[órgão oficial]** | Receita Federal / CGSN / Comitê Gestor acts (Soluções de Consulta, Resoluções) |
| **[Sebrae]** | Sebrae guides — the de-facto small-business teaching standard |
| **[publicação profissional]** | accounting firms, ERP vendors, Fórum Contábeis — practice, not rule |
| **open** | no reliable source found; a choice the store's contador must confirm |

**Rule for this domain: never guess.** A placement without a tier is a bug. When sources disagree, the DRE ships the choice as **data** (per-store mapping, flagged provisional — roadmap D48), not as code.

## 1 · Which standard applies

- **≤ R$ 4,8 mi/ano receita bruta → NBC TG 1002 (microentidades)** [norma]. DRE lines §5.1 (a)–(n). Accrual basis (competência) — cash flow is the only statement on cash basis. Source: https://www.dinamicasistemas.com.br/upload/files/NBCTG1002.pdf
- **R$ 4,8 mi – 78 mi → NBC TG 1001 (pequenas e médias)** [norma]. Same line shape plus more disclosure. Source: https://www.ibet.com.br/wp-content/uploads/2022/01/NBCTG1001.pdf
- **ITG 1000** (Res. CFC 1.418/2012) — revoked from 2023, but its Anexo 3 model DRE + chart of accounts is still the practitioner default and is the origin of the DAS rule below [norma, historic]. https://crcgo.org.br/wp-content/uploads/2022/12/ResolucaoCFC_-1418.pdf
- **MEI** — no statutory DRE duty (Código Civil art. 1.179 §2 exempts the pequeno empresário; MEI keeps the Relatório Mensal de Receitas Brutas) [norma via publicação profissional]. Ship a **managerial** DRE only.

The product shows a warning when a store's trailing-12-month receita bruta crosses R$ 4,8 mi (switch to NBC TG 1001 shape — CONTRACT §10).

## 2 · The canonical line structure

Matches NBC TG 1002 §5.1 and the market template (Conta Azul 2026; Sebrae's compressed form) one-to-one.

| # | Line (`DreLine`) | Content | Tier |
|---|---|---|---|
| 1 | Receita bruta | sales of goods, digital products, services — **including interest embedded in an installment price charged to the buyer** (tax view, see §4 h) | [norma] + [órgão oficial] |
| 2 | (−) Deduções | cancellations, refunds, devoluções; unconditional discounts; **taxes on revenue** (whole DAS for Simples — §3; PIS/COFINS/ISS/ICMS for Presumido) | [norma] |
| 3 | = Receita líquida | | |
| 4 | (−) Custo das vendas (CMV/CSP) | goods sold; per-sale digital delivery cost; categories flagged `custo` (D50) | [norma] + [Sebrae] |
| 5 | = Lucro bruto | | |
| 6 | (−) Despesas com vendas | marketplace commission, ads, outbound freight, gateway/MDR fees (provisional — §5) | [publicação profissional] |
| 7 | (−) Despesas administrativas | fixed SaaS/tools, salaries, rent; **DAS-MEI** for MEI stores | [publicação profissional] + [Sebrae] |
| 8 | (−) Outras despesas / (+) outras receitas operacionais | chargeback/fraud losses (provisional — §5) | open |
| 9 | ± Resultado financeiro | antecipação cost, bank fees, late-payment interest (juros de mora) received | [publicação profissional] + [órgão oficial] |
| 10 | = Resultado antes dos tributos sobre o lucro | | |
| 11 | (−) IRPJ / CSLL | Presumido/Real always; Simples only when the store splits the DAS (§3) | [norma] |
| 12 | = Resultado líquido | | |

**Managerial view (contribution margin)** — Sebrae teaches MC = preço de venda − (custos variáveis + despesas variáveis), where variable despesas include taxes on sales and commissions [Sebrae]. It regroups the SAME accrual lines (variable: 2, 4, variable part of 6; fixed: 7, rest of 6) — totals reconcile, only grouping differs. Ship both views from one data set. https://respostas.sebrae.com.br/pergunta/como-fazer-calculo-da-margem-de-contribuicao/

## 2a · Default categories → lines (owner D56, accountant review 2026-10-14)

| Default category | Line | Behavior |
|---|---|---|
| Vendas · Serviços · Mensalidades | gross_revenue | variable |
| Juros de parcelamento (new) | gross_revenue (detail row; alt. financial_revenue) | variable |
| Outras receitas | other_operating (+) | — |
| Rendimentos / juros recebidos | financial_revenue | — |
| Impostos sobre vendas (DAS Simples, ISS, ICMS, PIS, COFINS) | deductions | variable |
| Mercadorias / insumos para revenda | cost_of_sales | variable |
| Terceiros na produção / entrega | cost_of_sales | variable |
| Pessoal | administrative_expenses (production staff → cost_of_sales, per store) | fixed |
| Aluguel e condomínio · Software e assinaturas · Fornecedores gerais | administrative_expenses | fixed |
| Contabilidade / jurídico / consultoria | administrative_expenses | fixed |
| Taxas e licenças (alvará, IPTU) · DAS-MEI | administrative_expenses | fixed |
| Marketing · Frete de envio · Comissões (marketplace/afiliados) · Taxas de cartão/gateway · Tarifa de chargeback | selling_expenses | variable |
| Tarifas bancárias · Antecipação de recebíveis · Juros e multas pagos | financial_expenses | — |
| IRPJ / CSLL (Presumido; Simples only when split) | income_taxes | — |
| Outras despesas | other_operating (−) | — |
| Entre contas | excluded (transfer) | — |

**No stock control yet:** cost_of_sales = purchases of the month (approximation — warn; the contador confirms) [norma TG 1002 §5.1(d) defines the line; the approximation is open].

## 3 · Where the DAS goes (the question the first research pass missed)

- **Simples Nacional (ME/EPP): the whole DAS → line 2 Deduções.** ITG 1000 Anexo 3 footnote: *"As entidades que estão enquadradas no Simples Nacional devem evidenciar os tributos na linha 'Deduções de Tributos, Abatimentos e Devoluções'. Neste caso, devem desconsiderar essas contas [IRPJ/CSLL]."* [norma]. NBC TG 1002 §29.3 keeps it as the permitted alternative: *"a microentidade poderá, alternativamente, evidenciá-la como dedução da receita bruta, juntamente com os demais tributos apurados no âmbito do Simples Nacional"* [norma]. NBC TG 1001 §29.3(b) same, as an "expediente prático" [norma].
- **Why:** the DAS is a rate applied on receita bruta; NBC TG 1002 §23.2 and §28.5 put revenue-based charges as deductions [norma]. Sebrae's financial-planning guide (2026) computes faturamento líquido = bruto − canceladas/devolvidas − impostos ("Simples Nacional em uma faixa de 9,5%") [Sebrae]. https://sebrae.com.br/content/dam/portal-sebrae/na/midias/documentos/pdfs/guia-de-planejamento-financeiro_2026-04-18_v1.pdf
- **Norm default = split** (IRPJ/CSLL share of the DAS → line 11 using the Anexo "percentual de repartição"). Allowed, more work, minority practice. **Product default: whole DAS in Deduções; split is a per-store setting** (owner D53).
- **MEI: DAS-MEI is a fixed monthly amount, not a % of sales → line 7 (fixed cost).** Sebrae-PR "Como administrar um pequeno negócio – MEI" lists the DAS-MEI under CUSTOS FIXOS [Sebrae]. https://extranet.pr.sebrae.com.br/portal/arquivos-gratuitos/MEI_como_administrar.pdf
- **Lucro Presumido:** PIS/COFINS/ISS/ICMS → line 2 (NBC TG 1001 §23) [norma]; IRPJ/CSLL → line 11, "evidenciada antes do lucro líquido" (§29.2/29.4) [norma]. (A 2021 draft that put Presumido IRPJ/CSLL in deductions was dropped from the final text — do not follow it.)

## 4 · E-commerce items

| Item | Placement | Tier |
|---|---|---|
| a. Gateway / MDR / Pix / boleto fees | Despesas com vendas (fee triggered by the sale) — **disputed**: some practice books them as despesa financeira | [publicação profissional], open |
| b. Antecipação de recebíveis (split out of the gateway fee — its own line) | Resultado financeiro (cost of money, not of selling) | [publicação profissional], consensus |
| c. Marketplace commission | Despesas com vendas. **Never** netted from receita bruta — SC COSIT 94/2025: receita bruta is the total "sem dedução da comissão da plataforma" | [órgão oficial] (tax) + [publicação profissional] (line) |
| d. Outbound freight paid by the seller | Despesas com vendas (some e-commerce practice: direct cost above lucro bruto) | [publicação profissional], split |
| e. Chargeback / fraud loss | **No Brazilian source found** (re-searched 2026-10-14). Product default: reversed amount → Deduções (like a return); the **chargeback fee** → Despesas com vendas; goods already delivered stay in custo. Whether a lost chargeback reduces the Simples base (LC 123 art. 3 §1 "vendas canceladas") is for the contador | open |
| f. Refund / devolução / cancelamento | Deduções | [norma] + [Sebrae] |
| g. Tarifas bancárias | Resultado financeiro (fixed card-agreement fees sometimes administrativas) | [publicação profissional] |
| h. Interest charged to the buyer on installments | **Product default line: receita bruta** (detail row) — NBC TG 1002 §11.3 waives present-value adjustment for terms ≤ 1 year and §23.2 measures revenue at the consideration [norma]; alternative receita financeira (§25.1) kept as a setting. **Tax: receita bruta** — SC COSIT 94/2025: "os juros embutidos nos valores pagos … nas compras parceladas compõem a receita bruta sujeita ao Simples Nacional" (Res. CGSN 140 art. 2 §4 I). **Accounting line: open** — revenue (NBC TG 1002 §23.2, consideration) vs receita financeira over time (§25.1). Juros de **mora** are receita financeira, outside receita bruta | [órgão oficial] (tax), open (line) |
| i. Hosting / platform / software | per-sale variable cost → line 4; fixed subscription → line 7 | [Sebrae] by principle |
| j. Installments "sem juros" absorbed by the seller | the acquirer/gateway discount — same treatment as a (or b if it is an antecipação) | [publicação profissional] |

SC COSIT 94/2025: https://www.normaslegais.com.br/legislacao/solucao-de-consulta-cosit-94-2025.htm

**Consequence for the system (h):** whatever DRE line the store picks, the buyer-paid installment interest MUST count in receita bruta for the Simples base. So the ledger books it separately (`source_ref=<order>:interest`, CONTRACT §10) and the DRE maps it — the tax-base report always includes it.

## 5 · Genuinely open (ship as provisional per-store data, ask the contador)

1. Gateway/MDR fees — despesa com vendas vs financeira.
2. Outbound freight — custo vs despesa com vendas.
3. Chargebacks/fraud — deduction vs outras despesas.
4. Buyer-paid installment interest — receita bruta vs receita financeira (accounting line only; tax answer is settled).
5. DAS whole vs split.
6. Chargeback on a split charge (platform fee, commerce D27) — does Asaas pull the split back from the recipient, or does the store's account bear all of it? Not in the Asaas docs (re-checked 2026-10-14); asked to Asaas. **Refunds are settled:** a partial refund returns the split share proportionally via `splitRefunds` (owner decision 2026-10-14, `charges._asaas_split_refunds`); a full refund reverses the split on Asaas' side.

The question list for the contador lives in `projects/commerce-seed-p4/ACCOUNTANT-QUESTIONS.md`.

## 6 · Cash vs accrual, and the 2027 change

- Statements are on competência (accrual); only the cash-flow statement is on cash (NBC TG 1001 P10; NBC TG 1002) [norma]. A Simples store taxed on cash basis has a temporary difference between DRE revenue and taxable revenue (NBC TG 1001 §29.10); deferred tax is waived for Simples (§29.3(a)) [norma].
- **Res. CGSN 190/2026 revokes the Simples cash-basis option from 2027-01-01** [órgão oficial — official text verified 2026-10-14: https://normasinternet2.receita.fazenda.gov.br/api/consulta-externa/ato/152832/visao/vigente]. Dated 2026-08-04, DOU 2026-08-10; art. 8 XXIII revokes CGSN 140 arts. 77–78; art. 9 effects 2027-01-01; new art. 2 §8: revenue counts "no momento do faturamento" (§9 extends to advance payments); IBS/CBS may be paid outside the DAS (art. 5 XVI).

## 7 · When a human contador (CRC) is required — the agent must say so

- **Bookkeeping is legally a contabilista's responsibility** — Código Civil art. 1.182; only MEI/pequeno empresário exempt (art. 1.179 §2) [norma].
- **ME/EPP must keep at least a livro-caixa** — LC 123 art. 26 §2 [norma].
- **Profit distribution above the presumed limit** (presumed profit − DAS) needs full bookkeeping proving the higher profit — LC 123 art. 14 §§1–2 [norma]. Lei 15.270/2025 adds 10% withholding over R$ 50k/month per person from 2026 [publicação profissional].
- **Filings** (DEFIS for Simples; ECD/ECF for Presumido/Real; ECD for Simples with investidor-anjo) — signatures and responsibility are the contador's [publicação profissional — exact IN text unverified].
- Regime choice/changes, tax planning, anything the store will sign → contador.

The software prepares, classifies and exports (accountant checklist, CSV/OFX); it never signs, files or decides a regime.

## 8 · Could not verify (re-check before hardening)

Official text of Res. CGSN 190/2026 · planalto.gov.br text of LC 123/Código Civil (mirrors used) · IN RFB 2.003/2021 + 2.004/2021 wording · any CRC publication on DAS placement . *(Resolved 2026-10-14: the seller receives the buyer-paid interest — our Price-table total is sent to Asaas as `totalValue` (`integrations/payments/checkout.py`), Asaas adds no interest itself: https://docs.asaas.com/docs/criar-uma-cobranca-parcelada.)*
