# Consumer law and e-commerce — CDC, Decreto 7.962/2013, withdrawal, abusive clauses, terms and privacy texts, marketing consent

> **Owner:** agent `legal-advisor` (advisor). **Consumers:** the owner, executors on the commerce seed and the store (`products/store/`), anyone writing a public terms/privacy text or a marketing message.
> **Status:** craft canon, 2026-11-05 (agent-refinement W2-S3). Method and tiers: `KB § PATTERNS/legal/legal-advisor-canon.md`. **Not legal advice** — public terms and refund policies are approved by a lawyer (§9).

**What this is.** The consumer-law floor every product that sells to natural persons online must meet — information duties, the 7-day withdrawal right, abusive clauses, adhesion-contract form, advertising — mapped onto the store and the commerce seed, plus the rules for the platform's own terms/privacy texts and for marketing messages.

**Why it exists.** The store sells a digital contract kit to consumers (`projects/store/contrato/README.md`), and its code lets the seller configure the guarantee to **0 days** (`products/store/backend/app/schemas/store.py:34` `Field(ge=0, le=30)`); the landing page has no supplier identification; checkout collects CPF without a privacy link. Each is a CDC / Decreto 7.962 duty, and none was anyone's job.

**How to use it.** Selling feature → §§2–4. A refund/chargeback flow → §6 (and the accountant for the books). Writing terms or a privacy text → §7. A marketing or WhatsApp message to a lead → §8. The house mechanism wins: the seed-mounted `/consent/*` pages (`KB § PATTERNS/frontend/consent-routes-mandate.md`) are *the* terms and privacy surface — products link them, never re-declare them.

## Contents
0. Term map · 1. When the CDC applies · 2. Mandatory information (CDC 31; Decreto 7.962 arts. 2, 4) · 3. Right of withdrawal (CDC 49; Decreto 7.962 art. 5) · 4. Abusive clauses and adhesion form (CDC 51, 54) · 5. Advertising and offer (CDC 30, 35, 37) · 6. Refunds and chargebacks · 7. Terms of use and privacy texts · 8. Marketing and WhatsApp consent · 9. When the lawyer decides · 10. Store gap list · 11. Worked examples · 12. Anti-patterns · 13. Sources · 14. Re-verify list

## 0 · Standard term ↔ house term

| Standard | House |
|---|---|
| Fornecedor (CDC 3) | the seller of the store/commerce product (an org, or NoctusAI itself) |
| Consumidor (CDC 2) | checkout buyer (nome / e-mail / CPF — `products/store/frontend/src/components/CheckoutDialog.tsx:15-22`) |
| Prazo de reflexão / direito de arrependimento (CDC 49) | store `guarantee_days` (`settings_service.py:37` default 7) and the landing copy "peça o reembolso e recebe 100%" (`Landing.tsx:295`) |
| Garantia contratual (CDC 50) | anything **beyond** the 7 legal days |
| Sumário do contrato (Decreto 7.962 art. 4 I) | none yet |
| Estorno / chargeback | `charge_refunded` → order `reembolsado`, downloads stop (`products/store/backend/app/services/webhook_service.py:12,96`) |
| Termos / Política de privacidade | `seed/framework/frontend/src/content/consent.ts` → `/consent/terms-of-use`, `/consent/privacy-policy` |

## 1 · When the CDC applies

Consumer = natural or legal person acquiring or using a product or service **as final recipient** (CDC 2) [norma]; supplier = whoever develops an activity of supplying products or services (CDC 3), product includes **immaterial** goods (§1) [norma] — a downloadable contract template is a product. Third parties exposed to commercial practices are equated to consumers (CDC 29). B2B SaaS contracts with a client org are usually civil/commercial (CC 421-A), unless the org is vulnerable and the final recipient — decide case by case (lawyer).

## 2 · Mandatory information

**The law** [norma]:
- CDC 31: correct, clear, precise, conspicuous information in Portuguese on characteristics, price, guarantee, terms, origin, risks.
- CDC 33: for remote sales, the manufacturer's name and address on advertising and documents.
- **Decreto 7.962/2013 art. 2** — sites offering or concluding consumer contracts must show, **prominently**: I business name and CPF/CNPJ of the supplier; II physical and electronic address; III essential characteristics; IV breakdown of extra charges (delivery, insurance); V full offer conditions (payment, availability, delivery deadline); VI restrictions on the offer.
- **Art. 4** — I **contract summary before contracting**, emphasising rights-limiting clauses; II tools to correct input errors before finishing; III immediate confirmation of acceptance; IV contract available for conservation and reproduction right after contracting; V effective electronic service channel; VI immediate acknowledgement of demands; VII effective security for payment and data processing; sole paragraph: answer demands **within 5 days**.

**Applied HERE (store).**
- Landing footer (`products/store/frontend/src/pages/Landing.tsx:370-376`) carries only the "modelo genérico … não constitui assessoria jurídica" disclaimer — **no supplier name, CPF/CNPJ, address or contact** (art. 2 I–II gap).
- Product characteristics and price ✅ (Landing, `landingContent.ts`); payment conditions shown by the gateway.
- No contract summary / terms acceptance in `CheckoutDialog.tsx` (art. 4 I, IV gap); thank-you page promises the link by e-mail (`Obrigado.tsx:34`) ✅ art. 4 III partially.
- **Commerce seed:** make art. 2 I–VI a seed-level storefront requirement (supplier identity from the org's settings, rendered in every storefront footer) — a seed seam, not per product (CLAUDE.md "Seed first").

## 3 · Right of withdrawal (arrependimento)

**The law** [norma]: CDC 49 — the consumer may withdraw **within 7 days** of signing or receiving the product/service whenever the contract is made **outside the commercial establishment** (online included); amounts paid are returned **immediately, monetarily updated** (sole paragraph). **Decreto 7.962 art. 5** — inform clearly and conspicuously the means to withdraw (caput); withdrawal **by the same tool used to contract** (§1); it cancels accessory contracts at no cost (§2); the supplier must **immediately notify the card issuer** so the charge is not posted or is reversed (§3); confirm receipt immediately (§4).

**Applied HERE.**
- `guarantee_days` accepts **0–6** (`store.py:34`) — values below 7 cannot remove the legal right; showing "garantia de 3 dias" would also be misleading (CDC 37 §1). **Recommendation:** floor the field at 7 (`ge=7`) and describe anything above 7 as contractual guarantee (CDC 50). The landing hides the seal when `days` is falsy (`Landing.tsx:268`), so 0 silently removes the information too.
- Withdrawal channel: the landing promises a refund "sem precisar explicar" (`Landing.tsx:295`) but shows **no button or channel** — add a withdrawal link in the purchase e-mail and the download page (same tool, art. 5 §1), with immediate acknowledgement.
- Refund → `charge_refunded` stops downloads ✅; art. 5 §3 (notify the card issuer) is satisfied by refunding through the gateway — confirm the gateway does it.
- **Digital content already downloaded:** the CDC has no exception for digital goods; courts and doctrine diverge on abuse cases → **open; keep honouring the 7 days** (the landing already promises it) [interpretation].

## 4 · Abusive clauses and adhesion form

**CDC 51** [norma] — **null** clauses include: exonerating or attenuating the supplier's liability (I; for a legal-person consumer it may be limited in justifiable situations); removing the option of reimbursement (II); transferring liability to third parties (III); iniquitous or exaggerated disadvantage, incompatible with good faith (IV); inverting the burden of proof against the consumer (VI); compulsory arbitration (VII); imposing a representative (VIII); leaving only the supplier free to conclude the contract (IX); unilateral price change (X), cancellation without reciprocity (XI), or modification (XIII); charging the consumer collection costs without reciprocity (XII); breach of environmental rules (XIV); disagreement with the protective system (XV); waiver of compensation for necessary improvements (XVI); and, by Lei 14.181/2021, limiting access to the Judiciary (XVII) and grace periods / blocked restoration of rights after the default is cured (XVIII). Exaggerated advantage is presumed in the cases of §1; nullity of one clause keeps the contract (§2). **CDC 54** — adhesion contracts: font **not smaller than 12** (§3); clauses limiting rights **highlighted** for immediate understanding (§4). CDC 47 — interpret in the consumer's favour. CDC 46 — clauses the consumer had no chance to know beforehand do not bind.

**Checklist for any consumer-facing text (terms, kit, generated contract against a consumer):** no liability waiver · refund option intact · no unilateral change of price/terms without the consumer's right to exit · foro not removing access to the consumer's domicile · arbitration optional · limitations highlighted · ≥ 12-point font in printable versions · plain Portuguese.

## 5 · Advertising and offer

The offer **binds** the supplier (CDC 30) and refusal lets the consumer demand performance, an equivalent, or rescission with refund (CDC 35) [norma]; misleading advertising, including **by omission**, is forbidden (CDC 37 §1, §3) [norma]. **Store:** "Contrato Blindado" and claims of protection must not promise outcomes a generic template cannot deliver; the "não constitui assessoria jurídica" disclaimer must be visible **before** purchase, not only in the footer → lawyer reviews the copy.

## 6 · Refunds and chargebacks

- **Withdrawal refund:** immediate and monetarily updated (CDC 49 sole paragraph); also cancel accessory contracts (Decreto art. 5 §2).
- **Chargeback:** the card network's dispute process, not a consumer-law institute; when it follows a withdrawal the supplier failed to process, the CDC duty was already breached. Keep evidence (delivery logs, terms accepted, withdrawal requests and answers) to contest abusive chargebacks.
- **Books and taxes:** where the refund or lost chargeback lands in the DRE and whether it reduces the Simples base → agent `accountant`, `KB § PATTERNS/finance/dre-structure.md` §4 (chargeback placement is still **open** there, line 88).

## 7 · Terms of use and privacy texts

**Rules** [norma]: Marco Civil art. 7 VIII (clear and complete information on collection, use, storage, processing and protection of personal data, in the terms), IX (express consent, highlighted), X (deletion at the end of the relation, except legal retention), XI (publicity and clarity of terms); LGPD art. 9 (facilitated access to processing information: purpose, form and duration, controller identity and contact, sharing, responsibilities, rights) and art. 6 VI (transparency). Consumer terms also follow §4.

**Applied HERE** (`seed/framework/frontend/src/content/consent.ts`, v1.1, 11/10/2026):
- ✅ single source, seed-mounted, versioned, rights and encarregado sections.
- ⚠️ no "when we act as operator" section — client-org data is the org's (`KB § PATTERNS/legal/lgpd-privacy-program.md` §2).
- ⚠️ the international-transfer section is generic — needs the Res. CD/ANPD 19/2024 art. 17 §2 content (`lgpd-privacy-program.md` §9).
- ⚠️ the controller is a natural person with no CNPJ; if the store sells as NoctusAI, Decreto 7.962 art. 2 I requires the supplier's CPF or CNPJ to be shown — **owner decides which entity sells**, lawyer reviews.
- Terms limitation-of-liability already reserves CDC rights; foro = user's domicile ✅ consumer-safe.
- **Checkout** (`CheckoutDialog.tsx`) collects CPF with no privacy-policy link — add a link next to the CPF field and state the purpose (fiscal/payment identification).

## 8 · Marketing and WhatsApp consent

- **Legal basis** for promotional messages to leads: consent (LGPD art. 7 I) or legitimate interest (art. 7 IX) with a written balancing test and an easy opt-out — never for sensitive data (`lgpd-privacy-program.md` §3).
- **Opt-out must work deterministically**, without the model deciding: the agents-security STOP floor (`KB § PATTERNS/security/ai-agent-security-canon.md` §6) is the mechanism; the law gives the right to oppose (LGPD art. 18 §2) and to revoke consent (art. 8 §5).
- Opt-in/opt-out records (`LGPD-WARNINGS.md:39`, agents migration 033) are personal data with their own retention (`lgpd-privacy-program.md` §12).
- WhatsApp Business platform policies (Meta) add their own opt-in rules — contractual, not Brazilian law; read Meta's current policy when building a campaign feature [re-verify].
- Unsolicited review requests after a deal (`LGPD-WARNINGS.md:48`) = marketing-adjacent: legitimate interest + opt-out in every message.

## 9 · When the lawyer decides

Final terms of use, privacy policy and refund policy; the store copy and any "blindado" claim; whether a specific digital-content withdrawal can be refused; which legal entity sells; any Procon complaint, consumer.gov.br case, or lawsuit.

## 10 · Store gap list (proposed, for the tech-lead to route)

| # | Gap | Rule | Proposed fix | Owner |
|---|---|---|---|---|
| 1 | `guarantee_days` accepts 0–6 (`store.py:34`) | CDC 49, 37 §1 | `Field(ge=7, le=30)`; copy distinguishes legal 7 days vs contractual extra | backend executor |
| 2 | No supplier name, CPF/CNPJ, address, contact on the storefront (`Landing.tsx:370-376`) | Decreto 7.962 art. 2 I–II | seed-level storefront footer from org settings | architect (seed seam) + frontend |
| 3 | No contract summary / terms acceptance before payment (`CheckoutDialog.tsx`) | Decreto art. 4 I, IV | summary + links + acceptance checkbox | frontend |
| 4 | No visible withdrawal channel | Decreto art. 5 caput, §1, §4 | "Desistir da compra" link in e-mail and download page + instant acknowledgement | backend + frontend |
| 5 | CPF collected with no privacy notice | LGPD art. 9; Marco Civil art. 7 VIII | purpose line + privacy link | frontend |
| 6 | Kit sale prerequisites (`projects/store/contrato/README.md:31-34`) | contracts-br §7 | keep as hard gate | owner + lawyer |
| 7 | Store missing from `deploy/fleet/active-scope.txt` though described as live in owner memories | product catalog rule | owner confirms its scope | owner |

## 11 · Worked examples

### A · Seller sets a 3-day guarantee
Answer: the legal 7 days apply anyway (CDC 49 is public order); showing "3 dias" misleads (CDC 37 §1). Block below 7.

### B · Buyer downloads all files and asks for a refund on day 6
Answer: the CDC gives no digital exception; the landing promised 100% without justification (binding offer, CDC 30). Refund. Abuse patterns (repeat buyers) → lawyer before any refusal policy.

### C · A storefront for a client org on the commerce seed
Supplier = the org; its CNPJ, address and contact go in the footer (Decreto art. 2); NoctusAI is the org's operator for the buyers' data (`lgpd-privacy-program.md` §2) and must say so.

## 12 · Anti-patterns

- **"Garantia" below 7 days** or a refund promise with no channel.
- **Product-local terms pages** that shadow the seed `/consent/*` routes.
- **Disclaimers only after purchase.**
- **Letting the LLM decide whether "pare" means opt-out.**
- **Treating chargebacks as only an accounting matter** — the consumer duty comes first.

## 13 · Sources

Accessed 2026-11-05.

| Title | URL | Supports | Tier |
|---|---|---|---|
| CDC, Lei 8.078/1990 (compilado) | https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm | arts. 2, 3, 29, 30, 31, 33, 35, 37, 46, 47, 49, 50, 51, 54 | [norma] |
| Decreto 7.962/2013 | https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2013/decreto/d7962.htm | arts. 2, 4, 5 | [norma] |
| Marco Civil da Internet, Lei 12.965/2014 | https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2014/lei/l12965.htm | art. 7 VIII–XI | [norma] |
| LGPD, Lei 13.709/2018 | https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm | arts. 6 VI, 7, 8 §5, 9, 18 §2 | [norma] |
| Lei 14.181/2021 (superendividamento) | https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14181.htm | CDC 51 XVII–XVIII | [norma] |

## 14 · Re-verify list

- Price-display rules for e-commerce (Lei 10.962/2004 and Decreto 5.903/2006) — **not read in this slice**.
- Withdrawal for downloaded digital content — current STJ position (no source read).
- Meta WhatsApp Business messaging policy (opt-in requirements) — vendor policy, changes often.
- Any 2025–2026 amendment to Decreto 7.962 (none seen on the Planalto page, 2026-11-05).
