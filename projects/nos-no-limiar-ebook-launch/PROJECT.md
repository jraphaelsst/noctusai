# Nós No Limiar: e-book launch ("Funcionar Não É Estar Bem"): Project Document

> **Status:** ⏳ Phase 0 done (research + verification). **Blocked on the owner's client (Mônica):** see §8.
> **Resume here:** read §0 first, then `intake.md`, then `research/estudo-checado-e-plano.md`.
> **Owner:** João (repo owner), acting for the client Mônica Tangerino / Nós No Limiar.
> **Language with the owner:** pt-BR. **Checkpoint written:** 2026-11-14.

---

## 0. Checkpoint: where we stopped (2026-11-14)

**Done in the first session:**
1. Built a **Hotmart canon reference**: every rule was read on help.hotmart.com with the collapsed sections expanded, and every claim has a URL (`research/hotmart-canon-reference.md`).
2. Read the client's **company documents**: CNPJ card (original and the 23/07/2026 update), Simples Nacional option term and contrato/alteração. Findings are in `intake.md` §2.
3. Read the **e-book PDF**. Structure and readiness findings are in `intake.md` §3.
4. **Fact-checked Mônica's sales-channel study** claim by claim against official pages for Hotmart, Kiwify, Eduzz, Monetizze and Amazon KDP. Rewrote the tax model: the company is an **ME on the Simples Nacional, not a MEI and not a pessoa física**. Result: `research/estudo-checado-e-plano.md`.
5. **Implementation plan**, Hotmart first: `research/estudo-checado-e-plano.md` §6, mirrored in §6 below.

**What the next session does first:**
- Ask the owner which of the §8 blockers Mônica has resolved.
- Re-collect the source files. They are **NOT in git** (privacy and copyright, see `intake.md` §5), so ask the owner to re-upload what is needed.
- Then continue at Phase 1.

---

## 1. Context & Purpose

Mônica Tangerino (psicanalista; studying psychology; no CRP yet) owns the company **Nós No Limiar, Vida Adulta Contemporânea** (Empresário Individual, ME, Simples Nacional, Cotia/SP). She wants to sell her own book **"Funcionar Não É Estar Bem: o custo emocional de dar conta de tudo"** as a PDF e-book.
- Starting price: **R$ 37**.
- **Hotmart** is the canon reference and the first channel; other portals come later.
- Most sales are expected to come from her Instagram.

**Goal:** the e-book is on sale with a working purchase link, legally and fiscally correct (invoice, tax, consumer-law information), and the sales are measurable per channel.

## 2. Confirmed constraints
- **The seller is the ME (CNPJ), not a pessoa física and not a MEI.**
  - Revenue is taxed through the Simples DAS on the **gross** sale value.
  - The book CNAEs are present since 23/07/2026: **58.11-5-00, 47.61-0-01, 46.47-8-02**.
- **No "psicóloga" title** anywhere until her CRP exists. Use "psicanalista".
- **No health or result promises** on the sales page or in posts. Hotmart rejects them, and so do CDC/CONAR.
- **No KDP Select** while the book is sold anywhere else: it requires digital exclusivity.
- **Garantia ≥ 7 days** (CDC art. 49; the Hotmart minimum).
- **Client PII and the client's files never enter git or any external request** (`intake.md` §5).

## 3. Design principles
- Hotmart rules are taken from `research/hotmart-canon-reference.md`, which was verified on official pages. Other platforms come from the table in `research/estudo-checado-e-plano.md` §3.1, which has URLs.
- **Every sourced claim carries its full URL and the date read.** This is a house rule since 2026-11-14 (skill `noc-research`).
- Tax and legal items go to a human professional where the law requires one (contador CRC / advogado OAB). We prepare; they sign.

## 3a. Seed-first analysis
Not applicable today: this is **client advisory and operations**, not a noc product. No code ships.
- **Re-evaluate** if the owner wants this flow productized. The commerce seed already plans digital products: `project-history/roadmaps/commerce-seed-2026-10-digital-products.md`. A future "sell an e-book" product should consume that, not fork it.

## 4. Scope
- **In:**
  - Hotmart setup end to end.
  - A digital edition of the PDF.
  - Sales-page copy, with the mandatory data and no promises.
  - Nota fiscal flow (with the contador).
  - Measurement per channel.
  - Then Kiwify, then Amazon KDP (non-Select).
- **Out:**
  - Paid ads.
  - Price experiments beyond R$ 29,90 → R$ 37.
  - Building our own checkout (that is the commerce seed's job).

## 4a. Dispatch routing
| Slice | Lens / agent |
|---|---|
| Tax (Simples Anexo, immunity, NF-e, pró-labore/Fator R) | `accountant` (then a human contador CRC signs) |
| Consumer law, LGPD notice, CFP advertising rules, copyright/ISBN | `legal-advisor` (then an OAB lawyer validates the final text) |
| Platform fees and terms re-checks | inline, or `general-purpose` with the Playwright render trick (`intake.md` §6) |
| PDF digital edition | inline (pypdf / qpdf) or a designer |
| Sales-page copy | inline + `product-designer` if a page is built |

## 5. Architecture / Data Model
None (no code). The data to track from sale 1 is in §9.

## 6. Implementation phases

### Phase 0 — Research & verification ✅
- [x] Hotmart canon reference (official pages, URLs) → `research/hotmart-canon-reference.md`
- [x] Read the company documents → `intake.md` §2
- [x] Read the e-book → `intake.md` §3
- [x] Fact-check the client study (fees, KDP, tax) → `research/estudo-checado-e-plano.md` §3
- [x] Corrected net-per-sale table (fee + DAS) → same file, §4
- [x] Plan → same file, §6

**Improvements:**
- applied: research rule "every sourced claim carries its full URL" (`.claude/skills/noc-research/SKILL.md`, `KB § PATTERNS/common/research-method.md`).
- learned: help.hotmart.com is JS-rendered and needs the host `api-help-center.bkf.hotmart.com`. It must be read with Playwright plus expanding `[aria-expanded=false]` toggles (`intake.md` §6).

### Phase 1 — Pre-requisites (client side) ❌ blocked on Mônica
- [ ] P1b: resolve the **sede address divergence**. The alteração puts the sede at her residence; the CNPJ card still shows Rod. Raposo Tavares km 22. Also decide which address the sales page shows (Decreto 7.962 requires a physical address).
- [ ] P2: confirm **digital rights**. The print edition is by Editora/Gráfica Paulo's (ISBN 978-85-88246-95-9, CIP lists "Gráfica Paulos"). Does her contract keep the e-book rights? Is there, or will there be, an e-book ISBN?
- [ ] P3: contador sets up the **nota fiscal**: inscrição estadual + NF-e modelo 55 with immunity (accountant view, ⚠️ to confirm). From 2027 there is one invoice per sale; automate it (eNotas or the contador's system).
- [ ] P4: contador confirms the **PGDAS-D Anexo (I or II) + book immunity**, plus the psychology pró-labore / Fator R (Anexo III vs V).
- [ ] P8 (optional): EDA/Biblioteca Nacional registration; e-book ISBN.

### Phase 2 — Product assets (our side, can start now)
- [ ] P7: **digital edition of the PDF.** Remove the 12 print-blank pages (1, 2, 6, 8, 10, 18, 32, 38, 44, 56, 62, 90, to be re-checked on the final file). Add outline bookmarks and a clickable sumário. Add a digital-edition credits page with company data and the e-book ISBN if one exists. Keep the cover with the author name.
- [ ] P6: **sales-page copy.** Start from the client's existing page (14 chapters, FAQ, guarantee). Add: nome empresarial + CNPJ + address + e-mail, product characteristics, price and conditions, 7-day guarantee and how to cancel, a link to a privacy notice, and "psicanalista" (not "psicóloga"). Run a no-promises check.
- [ ] Privacy notice (LGPD: purposes, legal basis, contact, art. 18 rights, the buyer-data watermark) + purchase terms (personal licence, no redistribution).
- [ ] Instagram assets: the client already has a 10-slide carousel and a caption. Insert the link once Phase 3 is done.

### Phase 3 — Hotmart go-live
- [ ] Mônica creates the Hotmart account **in the CNPJ** (the biometrics must be done by her), sends the requerimento de empresário + ID, and creates the 6-digit PIN.
- [ ] Bank account in the **same CNPJ** (after the documents are approved).
- [ ] Product: format eBook; name; description ≥ 200 characters; cover; R$ 37 (or launch at R$ 29,90); garantia 7 days; Pix + cartão (installments only with interest paid by the buyer); **DRM Social on**.
- [ ] Sales page (external URL or Hotmart Pages) → **Finalizar cadastro** → review (~15 min, up to 1 business day).
- [ ] Test purchase by Pix → check delivery and watermark → refund (refund.hotmart.com; no fee on refunds).
- [ ] Link from "Links de divulgação" goes into the Instagram bio and posts, with distinct links per origin.
- [ ] NF automation live **before** the first real sale.

### Phase 4 — Second channel: Kiwify (30–60 days after Phase 3)
- [ ] Same file, price and guarantee. Kiwify approves instantly, releases card money in 15 days and has free automatic withdrawal.

### Phase 5 — Amazon KDP (later, with testimonials)
- [ ] **Non-Select only.** At R$ 37 the royalty is 35% (≈ R$ 12,95). EPUB is recommended. The tax treatment of the royalties goes to the contador.

## 7. Open questions
1. Which sede address is official, and which address goes on the sales page? (Mônica + contador)
2. Paulo's contract and digital rights; e-book ISBN. (Mônica)
3. Anexo I vs II, inscrição estadual + NF-e, pró-labore / Fator R. (contador CRC)
4. Launch price: R$ 37 directly, or R$ 29,90 first? (Mônica)
5. Will the owner want this flow productized later? (João; see §3a)

## 8. Dependencies & blockers
- **Blocked on Mônica:** P1b (address), P2 (rights/ISBN).
- **Blocked on the contador:** P3 (NF), P4 (Anexo / immunity / Fator R).
- **External hosts not reachable in the 2026-11-14 cloud session:** planalto.gov.br, site.cfp.org.br, help.monetizze.com.br, legislacao.fazenda.sp.gov.br, normasinternet2.receita.fazenda.gov.br, the STF portal. The claims that depend on them are marked ⚠️ in the research files.

## 9. Success criteria
- A working Hotmart purchase link, a test purchase done and refunded, an invoice issued for the first real sale.
- Tracked from sale 1: sales per channel and origin, refund and chargeback rate (Hotmart guidance ≤ 0,9%), Pix vs card mix, monthly net received vs DAS paid.

## 10. How to use this plan
- Tick the boxes live. Every new fact gets its source URL and date.
- If a §2 constraint changes (for example, the CRP is issued): update §2, the sales page and §11.

## 11. Change log
- 2026-11-14: project created. Phase 0 complete (Hotmart canon, document intake, e-book intake, study fact-check, plan). Owner answers recorded: the CNAEs were added; Mônica is a psicanalista without a CRP yet (CRP expected soon).
