# Managerial and SaaS metrics — the management views that reconcile to the DRE

> **Owner:** agent `accountant` (advisor). **Consumers:** store owners (contribution margin, cash), the NoctusAI owner (the company's own SaaS P&L and Simples position), `noctusai_lib.domain.finance` reports.
> **Status:** craft canon, 2026-11-05 (agent-refinement W1-S6). Tiers as in `KB § PATTERNS/finance/dre-structure.md` §0. Numbers in worked examples are **illustrative**, not NoctusAI's books.

**What this is.** The managerial side of the accountant's work: cash-flow, contribution margin, per-order unit economics, cash vs accrual, and the SaaS metrics NoctusAI needs for its own finances (MRR/ARR, churn, CAC, LTV, payback, bookings vs revenue).

**Why it exists.** The audit found the agent had one statutory statement (the DRE) and nothing for management decisions or for NoctusAI-the-company, which the owner put in scope on 2026-11-05.

**How to use it.** **Managerial ≠ statutory.** These views regroup or re-time the same facts the DRE uses and must reconcile to it; they never replace it and never decide a tax question. Tax and regime rules live in `KB § PATTERNS/finance/br-tax-advisor-canon.md`; DRE lines in `dre-structure.md`.

## Contents
0. Standard term ↔ house term · 1. Cash vs accrual and the DFC · 2. Contribution margin · 3. Unit economics per order · 4. SaaS: bookings, billings, revenue · 5. MRR / ARR · 6. Churn · 7. CAC, LTV, payback · 8. Which organ data feeds what · 9. Worked example B — NoctusAI's own Fator R + SaaS view · 10. Owner glossary (pt-BR) · 11. Anti-patterns · 12. Sources

## 0 · Standard term ↔ house term

| Standard term | House term / code |
|---|---|
| Cash-flow statement (DFC), direct method | `reports.cashflow` (`seed/lib/backend/noctusai_lib/domain/finance/reports.py:52`): realized ledger + projected open entries, by month |
| Contribution margin view | DRE `view="managerial"` (`reports.py:122`; `dre.py:21` "regroups the SAME facts (variable vs fixed) and reconciles to `net_result`") |
| Variable / fixed cost | `CategoryBehavior.VARIABLE` / `FIXED` (`types.py:124-128`), inherited per category |
| Recurring revenue contract | `recurrences` templates (`recurrences.py`) — generate receivables on a schedule; **not** a subscription ledger |
| Deferred revenue | not modelled (no unearned-revenue account in the organ) |

## 1 · Cash vs accrual and the DFC

- Statutory statements are on accrual (competência); only the cash-flow statement is on cash (dre-structure §6, NBC TG 1001/1002) [norma].
- **The bridge** (what the owner usually asks: "I made a profit, where is the cash?"): `Resultado líquido (accrual) − Δ contas a receber − Δ estoque + Δ contas a pagar + Δ receita diferida − investimentos ± financiamentos = Δ caixa`.
- **Direct-method DFC from the organ:** receipts and payments by `settled_on` (the same facts the Livro Caixa lists), transfers between own accounts excluded; projected = open entries by `due_date`.
- **Simples note:** until 2026-12 a Simples store may be taxed on cash; from 2027 on the invoice moment (`br-tax-advisor-canon.md §3`). The DRE stays on accrual either way; the tax base report is separate (`simples_base.py`).

## 2 · Contribution margin

- **MC = preço de venda − (custos variáveis + despesas variáveis)**, variable despesas including taxes on sales and commissions [Sebrae] (dre-structure §2).
- **Margem de contribuição %** = MC / receita líquida. **Ponto de equilíbrio (R$)** = custos e despesas fixos / MC%.
- House rule: the managerial view regroups the **same** accrual lines (variable: Deduções, CMV, variable selling; fixed: administrative, rest of selling) — totals reconcile to `net_result`.

## 3 · Unit economics per order (store)

| Per order | Source in the organ | Note |
|---|---|---|
| Gross price (+ buyer-paid interest) | receivable `amount_cents` (+ `:interest` row) | interest is receita bruta for the Simples base |
| − taxes on sales (DAS share at the effective rate) | Deduções | Simples: effective rate × price |
| − CMV / delivery cost | `cost_of_sales` categories | no stock control yet ⇒ purchases of the month (approximation) |
| − MDR / gateway fee | settlement fee → `Taxas de cartão/gateway` | line disputed (dre-structure §5 Q1) — the *amount* is not |
| − marketplace commission | selling expenses | never netted from receita bruta (SC COSIT 94/2025) |
| − outbound freight | selling expenses (or CMV, per store) | |
| − chargeback reserve | expected-loss % × price | managerial provision; the actual loss books when it happens |
| **= contribution per order** | | the number that funds fixed costs |

From 2027+ with split payment: the gateway may withhold IBS/CBS at settlement — that withholding is **tax**, not fee (`br-tax-advisor-canon.md §3`).

## 4 · SaaS: bookings, billings, revenue

a16z: "a common mistake is to use bookings and revenue interchangeably". **Bookings** = contract value signed; **billings** = what was invoiced; **revenue** = recognized as the service is delivered. **Deferred revenue** = cash collected for service not yet delivered; billings = revenue + Δ deferred revenue is a forward-looking health signal [publicação profissional].
- Annual plan paid upfront in January: booking and billing in January; revenue 1/12 per month; the rest sits as deferred revenue (a liability) — on accrual books. On a cash-basis tax view the timing differs; say which view the number is.

## 5 · MRR / ARR

- **MRR** = Σ monthly recurring subscription value of active customers. **ARR** = MRR × 12 (only for recurring). ARR "should exclude one-time (non-recurring) fees and professional service fees" (a16z) — setup fees, implementation, consulting, one-off AI credits are out.
- **MRR movement:** `MRR_end = MRR_start + new + expansion − contraction − churned (+ reactivation)`. Report each component; a flat total can hide heavy churn.
- Annual contracts count as contract value / 12 per month; discounts are netted at the contracted price.

## 6 · Churn

- **Logo churn** = customers lost / customers at start of period.
- **Gross revenue churn** = (contraction + churned MRR) / MRR at start — "estimates the actual loss to the business".
- **Net revenue churn** = (contraction + churned − expansion) / MRR at start — "understates the losses" (a16z) because upsells mask weakness; can go negative (net expansion).
- Always show gross next to net.

## 7 · CAC, LTV, payback

- **Paid CAC** = paid acquisition spend / customers acquired through paid channels. **Blended CAC** mixes in organic customers and "doesn't inform how well your paid campaigns are working" (a16z). Show paid CAC first.
- **LTV** = "the present value of the future net profit from the customer" (a16z) — **profit, not revenue**. Practical form: `LTV ≈ ARPA × margem de contribuição % / churn mensal` (undiscounted; say so).
- **CAC payback (months)** = CAC / (ARPA × margem de contribuição %).
- **LTV/CAC** is only as good as its inputs: revenue-based LTV overstates what you can afford to spend.
- **Burn:** net burn (expenses − incoming revenue) is "the true measure" of cash consumption [publicação profissional].

## 8 · Which organ data feeds what

| Metric | Organ source | Gap |
|---|---|---|
| DFC, cash bridge | `reports.cashflow`, ledger, settlements | Δ deferred revenue not modelled |
| Contribution margin | DRE managerial view, `CategoryBehavior` | stock (CMV) approximated |
| Unit economics | entries + settlements + fee categories | chargeback reserve is managerial only |
| MRR / churn (NoctusAI) | `recurrences` approximate contracted recurring receivables | **no subscription ledger** (plan, start/end, MRR events) — metrics are approximations until one exists; proposal for the tech-lead |
| CAC | marketing categories + customer origin | no attribution of customer → channel in the organ |

**Deferred revenue for annual plans is not modelled yet** (NBC TG 1002: recognise 1/12 per month as the service is delivered; cash arrives up front) — open for the tech-lead; until then annual-plan MRR and the cash bridge are approximations (§0, §1).

**NoctusAI company file** (pre-CNPJ, no revenue, no contador, 2026-11-07): `br-tax-advisor-canon.md` §13; the §9 numbers are illustrative.

## 9 · Worked example B — NoctusAI's own Fator R + SaaS view

**Question (owner):** "Nossa alíquota do DAS está certa?"

**Step 1 — classification (contador's sign-off).** NoctusAI's CNAE decides whether its services are Fator-R-sensitive (III or V) or fixed in an Anexo; for IT CNAEs practice treats several as Fator-R-sensitive [publicação profissional — re-verify per CNAE, `br-tax-advisor-canon.md §2`].

**Step 2 — Fator R (LC 123 art. 18 §§5-J/5-K/5-M)** [norma]. Illustrative trailing-12-month figures:
- RBT12 = R$ 600.000; folha 12m (salaries + pró-labore + CPP/FGTS paid) = R$ 150.000.
- Fator R = 150.000 / 600.000 = **25% < 28% ⇒ Anexo V**.

**Step 3 — effective rate** (art. 18 §1-A: `(RBT12 × Aliq − PD) / RBT12`; bracket 3, R$ 360.000,01–720.000; table values [publicação profissional — re-verify against LC 123 Anexos III/V]):
- Anexo III: 13,5% nominal, PD R$ 17.640 ⇒ (81.000 − 17.640) / 600.000 = **10,56%**.
- Anexo V: 19,5% nominal, PD R$ 9.900 ⇒ (117.000 − 9.900) / 600.000 = **17,85%**.
- On R$ 50.000 of monthly revenue: DAS ≈ R$ 5.280 (III) vs R$ 8.925 (V) — **Δ ≈ R$ 3.645/month** (illustrative).

**Step 4 — the lever (contador decision).** Reaching 28% needs folha 12m ≥ R$ 168.000 (+R$ 18.000/year). Raising pró-labore raises payroll-side costs (social security and personal income tax on the partner) — the net effect, the timing (trailing 12 months, so it takes effect gradually) and the documentation are the **contador's** call (CRC boundary, `br-tax-advisor-canon.md §8`). The agent shows the arithmetic; it never recommends the pró-labore figure as a decision.

**Step 5 — the SaaS view next to it** (illustrative month):

| | R$ |
|---|---|
| MRR start | 40.000 |
| + new | 4.000 |
| + expansion | 1.500 |
| − contraction | 500 |
| − churned | 2.000 |
| **MRR end** | **43.000** |
| Setup fees billed this month (excluded from MRR) | 3.000 |

- Gross revenue churn = (500 + 2.000) / 40.000 = **6,25%**; net revenue churn = (2.500 − 1.500) / 40.000 = **2,5%** — report both; net understates the loss.
- ARR = 43.000 × 12 = R$ 516.000 (setup fees excluded).
- Tax side reconciles: receita bruta for the DAS includes the setup fees (they are revenue), even though MRR excludes them.

**Output to the owner (pt-BR):** the Anexo determination as **open until the contador confirms the CNAE**, the Fator R arithmetic with tier per claim, the Δ, the lever framed as a contador decision, and the MRR/churn table labelled managerial.

## 10 · Owner glossary (pt-BR)

| Termo | Em uma frase |
|---|---|
| Margem de contribuição | quanto sobra de cada venda para pagar os custos fixos |
| Ponto de equilíbrio | o faturamento em que o lucro é zero |
| Fluxo de caixa (DFC) | entradas e saídas de dinheiro de fato, mês a mês |
| Regime de competência | a receita e a despesa contam quando acontecem, não quando o dinheiro entra/sai |
| MRR / ARR | receita recorrente mensal / anual das assinaturas, sem taxas avulsas |
| Churn bruto / líquido | perda de receita recorrente sem / com o ganho de upgrades |
| CAC | custo para conquistar um cliente |
| LTV | lucro (não faturamento) que um cliente deixa durante a vida dele com você |
| Payback do CAC | em quantos meses o lucro do cliente paga o custo de conquistá-lo |
| Fator R | folha de 12 meses ÷ receita bruta de 12 meses; ≥ 28% leva certos serviços ao Anexo III |

## 11 · Anti-patterns

- **Managerial numbers presented as the DRE** or used to answer a tax question.
- **MRR including setup/implementation fees.**
- **Net churn without gross churn.**
- **LTV on revenue** (overstates affordable CAC).
- **Blended CAC as the efficiency metric** of paid channels.
- **Recommending a pró-labore figure** instead of showing the arithmetic and naming the contador.
- **Treating `recurrences` as a subscription ledger** without saying it is an approximation.

## 12 · Sources

| Title | URL | Supports | Accessed |
|---|---|---|---|
| a16z — 16 Startup Metrics | https://a16z.com/16-startup-metrics/ | §4–§7 bookings vs revenue, deferred revenue/billings, ARR exclusions, gross vs net churn, paid vs blended CAC, LTV as PV of net profit, net burn | 2026-11-05 |
| Lei Complementar 123/2006, Planalto | https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm | §9 art. 18 §1, §1-A formula, §§5-J/5-K/5-M Fator R | 2026-11-05 |
| Sebrae — margem de contribuição | https://respostas.sebrae.com.br/pergunta/como-fazer-calculo-da-margem-de-contribuicao/ | §2 MC formula [Sebrae] | 2026-10-14 (via dre-structure §2) |
| Fator R / Anexo tables practice (Agilize) | https://agilize.com.br/blog/gestao-fiscal/anexo-iii-fator-r-6-de-imposto/ | §9 bracket nominal rates and deductions [publicação profissional — re-verify against LC 123 Anexos] | 2026-11-05 (search result) |
