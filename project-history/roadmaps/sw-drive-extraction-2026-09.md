# sw-drive-extraction-2026-09 — real deal folders → trusted extraction → correct contracts

> Durable record (`KB § PATTERNS/common/roadmap-tracking.md`). Origin: 2026-09-23/24 owner session
> (noctusai-3e). Follows `project-history/roadmaps/sw-extraction-contract-gate-2026-09.md` (D1–D4 stay in force).
> Source: the owner's shared Drive folder "2 - PROCESSOS EM ANDAMENTO" (~40 deal folders 685→897 + two
> "CONTROLE DE PROCESSOS" spreadsheets). Real PII is read and stored locally only (memory
> `feedback_sw_document_read_authorization`).

## Goal (owner, verbatim intent)

Learn how to structure data, files, extraction, relationships and links, so that uploading a deal's files
fills everything the contract needs, and generation produces a 100% correct, 100% complete contract.
One folder at a time, until the owner says to automate. Bugs in the first rounds are expected; each
round improves the methodology.

## Owner rules (2026-09-23/24)

- **R1 Certidões.** VENDEDORES and EVERY empresa associated with them are MANDATORY. Compradores are
  NOT needed, except with a **permuta**: then the comprador gives an imóvel and needs certidões.
  Revokes df54184ab ("sellers don't need certidões"), which is live in prod since d1dc3f834.
- **R2 Serasa Crednet.** The vendedor's Crednet supplies every certidão-emission field except the RG
  number, which comes from another doc. Its "Participação Societária" lists the vendedor's empresas.
  Each empresa is its own DB record with its own certidões.
- **R3 Human order = extraction priority.** Basic docs → Serasa → all docs 100% → certidões de pessoas
  (casamento, CNDs…) → the rest. Imóvel mandatory docs (matrícula, IPTU, CND) are uploaded per doc on the
  imóvel page, extracted per doc, and stored on the imóvel. They are worked inside the certidões step.
- **R4 Permuta.** A negociação toggle plus a link to an in-house imóvel given in exchange. That imóvel's
  data feeds the contract, and prices/values/specs must reconcile.
- **R5 Validation.** Only through the real UI (browser MCP): uploads, manual entry where extraction is
  impossible, generation and visualization. Delete no data. Real people link to existing records (matched
  by CPF), never duplicated.
- **R6 Tokens.** Files never pass through the agent's context. Drive → disk (seed `RealDriveDownloader`)
  → product extractor (Haiku, cost-logged via seed `llm/usage.py` `UsageSink`). The agent reads only
  redacted scorecards. Track cost per run.
- **R7 Drive link is transitional.** No in-product Drive import. Once each folder is registered in the DB
  and linked to its owners, the Drive link is no longer needed for this purpose.

## Folder anatomy (measured on 883)

`<nº> - <dd/mm/aaaa> - <imóvel> - (<corretor>)/`
- `DOCUMENTOS/`: identity (CNH), certidão de casamento (+ averbações), comprovante de residência, bank
  forms (DPS, proposta).
- `CERTIDÕES/<PESSOA>/` and `CERTIDÕES/<PESSOA> CNPJ/`: a numbered set per entity.
  `1 RF · 2 JF 1ª · 3 JF 2ª · 4 Trab digital · 5 Trab físico · 6 Déb trab · 7 TJSP e-SAJ · 8 TJSP e-Proc ·
  9 SERASA (PF only) · 10 CENPROT · 11 Déb não inscritos · 12 Dívida ativa`. This is 1:1 with contract
  Cláusula Terceira items 1.1–1.12 (PF) and 2.1–2.11 (PJ, no Serasa).
- Root: matrícula (PDF, sometimes also .docx), IPTU espelho, CND IPTU, ITBI guia + comprovante,
  financing contract, the REV FINAL contract .docx, and the D4Sign-signed PDF.
- **Ground truth:** the REV FINAL contract carries every certidão nº + date, the parties' qualificação,
  the imóvel description, price and parcelas. Every extracted value is checked against it.

## Phases

- **P0 Foundations.**
  - (a) `noctus.dev` Drive-pull tool: mirror a folder to local scratch plus a manifest (tree, ids, md5,
    size, mime), zero tokens.
  - (b) A per-run cost ledger.
  - (c) Data model: `empresas` (cross-deal), pessoa↔empresa participação (%, source Crednet),
    certidões attachable to pessoa ∨ empresa, `acervo` (the deal archive mirroring the Drive tree + a
    per-file classification and target), permuta toggle + imóvel link.
  - (d) Reverse R1 at `derivacao.py:1245`, `contexto.py:288` and the `TestSellerCertidoesNaoExigidas`
    tests.
- **P1 Extraction trust loop, per doc type, in R3 order.** pull → browser upload on the card → extractor →
  compare to ground truth → score → fix → re-run → record learnings.
- **P2 Score every folder** (data quality × completeness). Pick reference contracts by score.
- **P3 Contract generation.** Diff against REV FINAL, by contract type (sem/com permuta, …). Extend
  `KB § CONTEXT/PRODUCTS/social-wiring/CONTRACT-FIELD-PROVENANCE-MAP.md` with the Vista-sourced fields.
- **Folder → ref mapping** (parallel to P1). Match each deal to its in-house/Vista imóvel by address +
  condomínio + m² + endereço interno; the owner confirms every match. Certidões link to vendedores or
  empresas; matrícula/IPTU/CND link to the imóvel.

## Open questions (owner)

- Canonical reference folder: decided after P2 scoring.

## Status

- 2026-09-24: roadmap drafted; P0 starting.
- 2026-09-24: P0a done. `noctus.dev.drive_pull` (auth_start/auth_finish/pull) mirrored deal folder 883
  (46 files, 50.8 MB) in 120 s, with zero file content through agent context; an idempotent re-run takes 3 s.
  The token is joaoraphaelsst, drive.readonly only (Google merged earlier grants into the refresh token;
  the tool keeps only drive.readonly when minting). Lessons: consent must finish within 10 min, so start
  a localhost:8011 listener BEFORE opening the consent URL; never revoke on this client (it is shared with
  SW's live Gmail/YouTube grants).
