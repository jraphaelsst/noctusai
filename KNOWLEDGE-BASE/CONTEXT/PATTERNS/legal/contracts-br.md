# Brazilian contracts — formation, party qualification, signatures, título executivo, clause libraries and the generator's limits

> **Owner:** agent `legal-advisor` (advisor). **Consumers:** the owner, the social-wiring contract generator's executors (`products/social-wiring/backend/app/modules/card_hub/contrato_gerador/`), the store "Contrato Blindado" kit (`projects/store/contrato/README.md`), the reviewing lawyer.
> **Status:** craft canon, 2026-11-05 (agent-refinement W2-S3). Method and tiers: `KB § PATTERNS/legal/legal-advisor-canon.md`. **Not legal advice** — the final wording of any contract is the lawyer's (§8).

**What this is.** The civil-law knowledge behind the contracts the platform *generates* (promessa de compra e venda in social-wiring) and *sells* (the store kit): what makes a contract valid, how each party must be qualified (PF and PJ), which electronic signature does what, when a private document is an enforceable title, how a clause library is governed, and what the generator may never decide alone.

**Why it exists.** The generator already encodes much of this as gates (`derivacao.py` `faltando`/`bloqueia`/`avisa`), but the *why* lived in owner memories and comments, and two open questions had no legal home: the PJ-party wording ("redação de PJ derivada de um único contrato assinado — confirme na revisão jurídica", `derivacao.py:1616-1618`) and whether a D4Sign-signed promise can be registered. This doc is that home.

**How to use it.** Before changing a clause, a gate or a party rule: read the matching section, then the code it cites. The house mechanism wins — the **one final legal review per generated version** (`revisao_juridica.py:1-34`, owner decision 2026-09-30) is *the* lawyer checkpoint; never add a parallel approval. New clause text goes to the lawyer through that review, not around it.

## Contents
0. Term map · 1. Formation and validity · 2. Qualifying the parties (PF, PJ, representation) · 3. Real-estate specifics (spouses, escritura, registration, arras) · 4. Consumer vs B2B · 5. Electronic signatures · 6. Witnesses and título executivo · 7. Clause-library principles (SW generator, store kit) · 8. What the generator must never decide alone · 9. Review checklist for a generated contract · 10. Worked examples · 11. Anti-patterns · 12. Sources · 13. Re-verify list

## 0 · Standard term ↔ house term

| Standard | House |
|---|---|
| Qualificação das partes | `frases.qualificacao_*`; PF via `texto_pessoa`, PJ via `frases.py:519` `qualificacao_pj` |
| Pessoa jurídica parte | `ParteJuridica` + `_parte_juridica` gate (`derivacao.py:1621`, migration 193) |
| Representante legal | the single PF linked to the PJ (`PJ_MAIS_DE_UM_REPRESENTANTE`, `derivacao.py:1662`) |
| Outorga uxória / marital (CC 1.647) | `_pacto_do_casal` + spouse anuência; none for a PJ (owner 2026-09-25) |
| Testemunhas | `contrato_testemunhas`, 2–5 selected, nome + CPF, e-mail for digital (`derivacao.py:3414-3450`) |
| Assinatura eletrônica | D4Sign platform; clause `modelo_texto.py:308-310` cites MP 2.200-2/2001 |
| Título executivo (confissão de dívida) | clause `modelo_texto.py:170` citing CPC 784 III |
| Cláusula resolutiva expressa (CC 474) | `modelo_texto.py:321` |
| Foro de eleição | `modelo_texto.py:339`; comarca from the matrícula (`derivacao.py:426` `foro_comarca`) |
| Revisão jurídica | `revisao_juridica.aprovar` |
| Fidelity to real signed contracts | `noctus.dev.contract_score` (masked, verdict-only) |

## 1 · Formation and validity

**Principle** [norma]: a legal act is valid with a capable agent, a lawful, possible, determined or determinable object, and the form prescribed or not forbidden by law (CC art. 104); form is free unless the law requires one (art. 107); **escritura pública is essential** for acts that constitute, transfer, modify or waive real rights over real estate worth more than 30× the highest minimum wage (art. 108). Absolute incapacity under 16 (art. 3); relative incapacity 16–18 and others (art. 4). Null acts: art. 166; voidable (relative incapacity, defects of consent): art. 171. Contracts follow social function and good faith (arts. 421, 422); ambiguous adhesion clauses are read in favour of the adherent (art. 423) and advance waivers of rights inherent to the deal in adhesion contracts are void (art. 424). B2B contracts are **presumed paritários** (art. 421-A, Lei 13.874/2019).

**Applied HERE.** The promessa is a **contrato preliminar** (CC 462–463) — form free (instrumento particular), because it is the escritura that transfers; it creates a real right to acquire only once **registered and without an arrependimento clause** (art. 1.417), enabling adjudicação (art. 1.418). The generated irretratabilidade clause (`modelo_texto.py:321`) is exactly what art. 1.417 needs. A private instrument proves obligations between the parties but binds third parties only after registration (art. 221).

**Checklist:** capable parties (age, interdição) · determined object (matrícula, price, conditions) · form (promise private ✅; definitive transfer above the art. 108 threshold → escritura) · no arrependimento if registration-as-real-right is the goal.

## 2 · Qualifying the parties

### 2.1 Pessoa física
Full name, nationality, estado civil (+ regime and pacto antenupcial when married — feeds §3), profession, CPF, identity document, address. Data come from documents under the art. 7 V basis (`KB § PATTERNS/legal/lgpd-privacy-program.md` §3).

### 2.2 Pessoa jurídica — the knowledge behind the PJ-qualification reminder
**The law** [norma]: a legal person is bound by its administrators' acts **within the powers defined in the ato constitutivo** (CC art. 47); a limitada is administered by persons designated in the contrato social or a separate act (art. 1.060); absent contrary provision administrators may do all acts of management, but **selling or encumbering real estate, when not the company's object, depends on what the majority of partners decides** (art. 1.015; its sole paragraph — the old ultra vires defence — was revoked by Lei 14.195/2021). An attorney-in-fact needs a procuração stating place, qualification of both, date, object and **the extent of the powers** (art. 654 §1); the counterparty may demand a notarised signature (§2).

**What a PJ qualification must contain (recommended standard, lawyer confirms the wording):**
1. Razão social (exactly as in the CNPJ card / Junta), legal nature.
2. CNPJ and NIRE (Junta Comercial registration) — or the registry of a sociedade simples.
3. Sede (full address).
4. **The act that grants the powers** — "nos termos de seu contrato social / da última alteração contratual consolidada, registrada na JUCESP sob nº … em …" — and, if signing via attorney, the procuração (cartório, livro, folha or private instrument data).
5. The representative's full PF qualification and **capacity** (sócio-administrador, administrador não sócio, procurador).
6. When the deal is a sale/encumbrance of real estate and that is **not** the company's object: the **partners' majority deliberation** (art. 1.015) — reference or attach it.
7. Joint representation clauses ("assinatura em conjunto de dois administradores") — if the contrato social requires it, both sign.

**Applied HERE.** `frases.py:519-533` renders items 1–3 and 5 (deal 866 verbatim shape: "representada neste ato por sua sócia e administradora …"). It does **not** render item 4 (no reference to the contrato social or procuração), does not ask item 6, and blocks item 7 by design (`PJ_MAIS_DE_UM_REPRESENTANTE`, `derivacao.py:1662`). The gate always raises `PJ_REDACAO_A_CONFIRMAR` (`derivacao.py:1670-1674`) — correct and honest. **Proposed deltas for the lawyer:** (a) add item 4 as a required field + phrase; (b) add a readiness question "a venda de imóvel é objeto social? se não, há deliberação da maioria?" (art. 1.015) → `faltando` until answered; (c) document joint representation as an explicit `bloqueia` reason (it already blocks, the message should cite the rule). The PJ's certidões (11, owner 2026-09-25) cover the company's debts, **not** its representative's powers.

**Drift note:** the OPEN owner reminder "contrato PJ qualificação" (memory, 2026-10-02) still describes a block `partes.pj_sem_qualificacao` that migration 193 replaced; what remains open is exactly items 4 and 6 above.

## 3 · Real-estate specifics

- **Spouses** [norma, CC 1.647 I]: neither spouse may alienate or encumber real estate without the other's authorisation, **except in separação absoluta**; the lacking authorisation makes the act voidable (art. 1.649). House: `_pacto_do_casal` decides the anuência; no spouse anuência for a PJ party (the company sells its own asset — owner 2026-09-25, legally consistent).
- **Arras / sinal** [norma]: arras confirmatórias (art. 417); on breach by the payer the other side keeps them, by the receiver they return plus the equivalent with monetary update, interest and fees (art. 418, wording by Lei 14.905/2024); penitential arras exclude further damages (art. 420). House: "multa = sinal" (owner, `project_contract_automation`) — the penalty clause is reducible by the judge when excessive or partly performed (art. 413), and capped at the main obligation (art. 412).
- **Cláusula resolutiva expressa** operates by law (art. 474) — `modelo_texto.py:321`; the email-notification variant for constituting default is a contract choice; lawyer confirms it for consumers.
- **Registration**: see §5.3 — the signature type decides whether the RI will accept the title.
- **Vendedor não proprietário** (`VENDEDOR_NAO_PROPRIETARIO`, F36): the promise of a third party's asset is valid as an obligation but cannot be registered against the matrícula; keep the gate.

## 4 · Consumer vs B2B

| Relation | Regime | Effect on the text |
|---|---|---|
| Imobiliária/incorporadora selling to a natural-person end buyer | CDC arts. 2–3 [norma] — consumer relation | abusive-clause list (CDC 51) applies; adhesion rules (CDC 54: ≥ 12-point font, limiting clauses highlighted); interpretation pro-consumer (CDC 47) |
| Private seller PF ↔ buyer PF, broker intermediates | civil (CC); the broker's service to each party may be consumer | CC 423–424 for adhesion; good faith |
| Company ↔ company | CC 421-A presumption of parity | freer risk allocation; still CC 413 |
| Store kit buyer (natural person buying a digital template) | **consumer** (`KB § PATTERNS/legal/consumer-ecommerce.md`) | right of withdrawal, information duties |

When a generated contract is used by a **fornecedor** against a consumer, every clause must pass `consumer-ecommerce.md` §4.

## 5 · Electronic signatures

### 5.1 The three levels (Lei 14.063/2020 art. 4) [norma]
- **Simples** — identifies the signer or links data (e.g. a click with login).
- **Avançada** — non-ICP-Brasil certificates or other means **admitted by the parties or accepted by the addressee**, uniquely linked to the signer, under the signer's sole control, tamper-evident (e.g. D4Sign, DocuSign with evidence trail).
- **Qualificada** — ICP-Brasil digital certificate (MP 2.200-2/2001 art. 10 §1: presumed true against signers).

### 5.2 Between private parties
MP 2.200-2 art. 10 §2 [norma]: other means of proving authorship and integrity are valid **when admitted by the parties** or accepted by whom it is opposed to. Lei 14.063 governs interactions **with public entities** (art. 2) — it does not set the floor for a purely private contract. ⇒ An advanced signature on the promise is valid between the parties; the generated clause (`modelo_texto.py:308-310`) records the parties' admission, which is what art. 10 §2 requires ✅.

### 5.3 For registration at the Registro de Imóveis
Lei 14.063 art. 5 §2 IV [norma]: the qualified signature is mandatory "nos atos de transferência e de registro de bens imóveis" (Juntas Comerciais excepted), and §5 makes it prevail in conflicts. Lei 6.015 art. 17 §§1–2 (Lei 14.382/2022) [norma] admits advanced or qualified signatures for registry access **as regulated by the CNJ**, which may allow advanced signatures for real-estate acts. TJSP (dúvida 1117826-50.2025.8.26.0100, 27/11/2025) kept the RI's refusal of a DocuSign-signed electronic lease for lack of ICP-Brasil signatures, citing art. 5 §2 IV and Provimento CNJ 149/2023 [órgão oficial via CNB/SP]; IRIB (abr/2026) reads CNJ Código Nacional de Normas art. 208 the same way [publicação profissional].
**Position:** a D4Sign-signed promise is **valid and executable but likely not registrable**. If the parties want registration (the art. 1.417 real right), they sign with ICP-Brasil certificates (e-Notariado or a qualified provider) or register a notarised/wet-ink original. **Lawyer + registrar decide; re-verify CNN art. 208.** The "autorização de registro" clause (`modelo_texto.py:314`) should not imply registrability the chosen signature cannot deliver — wording for the lawyer.

## 6 · Witnesses and título executivo

- **CPC art. 784 III** [norma]: a private document signed by the debtor **and two witnesses** is an extrajudicial executive title.
- **CPC art. 784 §4** (Lei 14.620/2023) [norma]: for titles **constituted or attested electronically**, any legal electronic signature is admitted and **witnesses are dispensed when integrity is conferred by a signature provider**.
- **Applied HERE.** The confissão de dívida clause (`modelo_texto.py:170`) still conditions executiveness on "assinado pelos devedores e por duas testemunhas". For a D4Sign-signed digital contract, §4 makes the witnesses legally dispensable; the house keeps them (owner 2026-09-23 made witness e-mail mandatory for digital signing) — harmless and conservative. **Proposed wording for the lawyer:** cite "art. 784, III e § 4º" so the clause stays true in both modalities.
- Witnesses must be capable and not interested parties; CPF + name are the minimum identification (house gate ✅).

## 7 · Clause-library principles

**Social-wiring generator (`modelo_texto.TEMPLATE`)**
1. **Every clause traces to a source**: a real signed contract (corpus, measured by `noctus.dev.contract_score`), a statute, or an owner/lawyer decision — never to a model's paraphrase.
2. **Variants are data, not prose forks** (à vista / financiado / parcelado+confissão; digital / física) — the template selects; a new variant is a lawyer-reviewed addition.
3. **Statute citations are checked against Planalto** whenever a clause is touched (CPC 784 §4 above is the example of a citation going stale by omission).
4. **Unknowns block or warn, never default silently** — the `faltando` / `bloqueia` / `avisa` + `revisar` vocabulary is the right one.
5. **One lawyer review per version** covers new and machine-derived text.

**Store "Contrato Blindado" kit (`projects/store/contrato/README.md`)**
1. It is derived from the SW generator with every datum replaced by `[CAMPO]` (README:17-19) — no personal data ✅.
2. **Ownership of the wording:** blank contract forms are not protected by copyright (Lei 9.610 art. 8 III) [norma], but the specific text derived from Marina's office's contracts carries a **relationship and confidentiality** question — README:33 "Autorização do escritório/Gilson" stays a hard prerequisite.
3. It is sold to **consumers** — they are laypeople filling blanks: put plain-language instructions, the warning that it is not legal advice (Landing footer already has it, `products/store/frontend/src/pages/Landing.tsx:370-376`), and **no promise of "blindado" protection** that a judge could read as misleading advertising (CDC 37) → `consumer-ecommerce.md` §5.
4. README:34 "uma revisão jurídica da versão genérica" stays mandatory before sale.

## 8 · What the generator must never decide alone

- The **legal wording** of a new party type or clause (PJ items 4 and 6, procuração, espólio, menor/interdito, estrangeiro).
- **Whether a spouse must consent** when the regime or pacto is unclear (block, ask).
- **The amount or nature of penalties** beyond the office's standard (CC 412–413, CDC 51/53 for consumers).
- **Registrability** or the signature level needed for registration (§5.3).
- **Whether a consumer relation exists** (§4).
- **Interpretation of a matrícula's encumbrances** (penhora, alienação fiduciária, indisponibilidade) — extraction may *report* them; the decision to proceed is human.
- **Approval of the version** — only `revisao_juridica.aprovar` by an authorised human.

## 9 · Review checklist for a generated contract (for the lawyer's review screen)

1. Parties: full qualification; PF estado civil + regime; spouse anuência where CC 1.647 applies; PJ items 1–7 (§2.2); procuração data if any.
2. Object: matrícula number and RI, description matches the matrícula, encumbrances disclosed.
3. Price, sinal (arras type), parcels, index, default interest and penalty within CC 412–413 (and CDC if consumer).
4. Delivery of possession, taxes (ITBI, IPTU) and costs allocation.
5. Irretratabilidade and resolutive clause (CC 474, 1.417).
6. Signature modality vs intended registration (§5).
7. Witnesses (2+, capable, identified) or CPC 784 §4 reliance.
8. Foro (comarca of the property; consumer ⇒ consumer's domicile cannot be excluded in an abusive way).
9. LGPD clause on the parties' data (purpose = contract and registration; retention).
10. Every `PJ_REDACAO_A_CONFIRMAR` / machine-derived value in `revisao_juridica_campos` checked.

## 10 · Worked examples

### A · A company sells the apartment
Readiness passes on razão social, CNPJ, NIRE, sede, one representative ✅; the rendered text omits the powers act. Advisor answer: ask for the latest consolidated contrato social; confirm the representative is administrator with powers to alienate; if the company's object is not real-estate trading, get the partners' majority deliberation (art. 1.015); add the reference to the qualification; lawyer approves in the review.

### B · Buyers want to register the promise
Signed on D4Sign (advanced). Advice: valid and executable (MP 2.200-2 art. 10 §2; CPC 784 §4) but the RI is likely to refuse (Lei 14.063 art. 5 §2 IV; TJSP 2025). Options: re-sign with ICP-Brasil certificates or a notarised path; registrar confirms; lawyer decides.

### C · Store kit buyer asks whether the template "protects" them
Answer per §7: generic model, not advice; the lawyer's review of the generic version is a sale prerequisite; marketing must not promise outcomes (CDC 37).

## 11 · Anti-patterns

- **Model-written clauses** shipped without corpus or statute provenance.
- **"Representada por seu sócio" with no powers act** — the counterparty cannot verify authority (CC 47).
- **Assuming the promise is registrable** because it was signed electronically.
- **Citing CPC 784 III alone** for digital contracts (misses §4).
- **Relying on the generator's gates as legal review** — they check completeness, not legality.
- **Selling a kit** derived from a third party's wording without their authorisation.

## 12 · Sources

Accessed 2026-11-05.

| Title | URL | Supports | Tier |
|---|---|---|---|
| Código Civil, Lei 10.406/2002 (compilado) | https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm | arts. 3, 4, 47, 104, 107, 108, 166, 171, 221, 412, 413, 417, 418, 420, 421, 421-A, 422–424, 462–463, 474, 654, 1.015, 1.060, 1.417, 1.418, 1.647, 1.649 | [norma] |
| CPC, Lei 13.105/2015 | https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm | art. 784 III, §4 | [norma] |
| MP 2.200-2/2001 | https://www.planalto.gov.br/ccivil_03/mpv/antigas_2001/2200-2.htm | art. 10 §§1–2 | [norma] |
| Lei 14.063/2020 | https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2020/lei/l14063.htm | arts. 2, 4, 5 §2 IV, §5 | [norma] |
| Lei 6.015/1973 (Registros Públicos) | https://www.planalto.gov.br/ccivil_03/leis/l6015compilada.htm | art. 17 §§1–2 | [norma] |
| CDC, Lei 8.078/1990 | https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm | arts. 2, 3, 37, 47, 51, 54 | [norma] |
| Lei 9.610/1998 (Direitos Autorais) | https://www.planalto.gov.br/ccivil_03/leis/l9610.htm | art. 8 III | [norma] |
| TJSP, Dúvida 1117826-50.2025.8.26.0100 (via CNB/SP) | https://cnbsp.org.br/2025/12/01/dje-processo-n-1117826-50-2025-8-26-0100-tj-sp-mantem-obice-a-registro-de-contrato-de-locacao-eletronico-sem-assinatura-digital-qualificada-icp-brasil/ | §5.3 | [órgão oficial] via secondary host |
| IRIB — Assinatura eletrônica qualificada nos atos de registro imobiliário (08/04/2026) | https://www.irib.org.br/assinatura-eletronica-qualificada-nos-atos-de-registro-imobiliario/ | §5.3 CNN art. 208 reading | [publicação profissional] |

## 13 · Re-verify list

- CNJ Código Nacional de Normas art. 208 (and any provimento under Lei 6.015 art. 17 §2) — read the consolidated CNJ text.
- JUCESP practice on the "última alteração consolidada" reference (doctrine/practice, not read).
- Whether the office's standard penalty for consumer buyers respects CDC 53 / Lei 13.786/2018 (distrato) — **not researched in this slice; lawyer.**
