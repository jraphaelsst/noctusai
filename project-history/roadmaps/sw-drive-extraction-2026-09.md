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

## Owner rules — empresas (2026-09-24, verbatim intent)

- **E1 Which empresas.** A vendedor's empresas (from their Serasa Crednet Participação Societária) need
  certidões when ACTIVE or BAIXADA for less than 5 years, counted back from TODAY. Baixada ≥5 years ⇒ no
  certidões. Case 883: an empresa baixada 05/02/2021 was correctly left out of the contract.
- **E2 The closing date comes from the Cartão CNPJ** ("DATA DA SITUAÇÃO CADASTRAL"), a document type of
  its own, uploaded per empresa and extracted like every other doc. 🔴 The Crednet's
  "SITUACAO DO CNPJ EM <data>" is NOT the closing date (case 883: Crednet 10/05/2025, Cartão 05/02/2021).
- **E3 Spouse.** A married vendedor's cônjuge is a vendedor: full certidões plus their own Crednet empresas.
- **E4 Dedupe.** An empresa owned by both spouses is emitted ONCE and appears ONCE in the contract.
- **E5 PJ set** is fixed at 11: the 12 PF items minus Serasa (CENPROT covers it).
- **E6 Permuta.** The comprador giving an imóvel gets exactly the vendedor treatment (Crednet, empresas,
  full set).
- **E7 Archive.** Every Drive file is stored in SW (the full archive), but it gets there through the live
  process: browser uploads, watching fields fill. Slotted docs and the archive share ONE stored copy.
- **E8 UI.** The Serasa Crednet upload lives in the person's document checklist (it precedes certidões in
  the human order) and also appears as certidão 9 automatically. A new **Empresas tab on the card**
  centralizes the deal's empresas: Cartão CNPJ upload, situação + closing date, "needs certidões?" (E1),
  and the empresa's own certidões.

## P0c data model (spec — build to this)

Existing (verified 2026-09-24, keep and reuse): a permuta is a parcela `tipo='permuta'` linked through
`atendimento_parcela_permuta_ativos` (114) to `permuta_ativos`, whose `imovel_codigo` is the in-house
imóvel link (101). `derivacao.py:717` already adds signing compradores to the certidão set when
`tem_permuta`. A CNPJ `certidao_consultas` row is today linked to its OWNER PERSON
(`cliente_id`/`atendimento_parte_id`); there is no empresa entity and no participação link.

1. **`social_wiring.empresas`**: `id, org_id, cnpj (14 digits, UNIQUE per org), razao_social,
   nome_fantasia, natureza_juridica, data_abertura, situacao_cadastral, data_situacao_cadastral,
   motivo_situacao, uf`, plus group provenance `dados_origem/_documento_id/_em/_confirmado_por/_em`
   (D1/D2 contract). Cross-deal and org-scoped. RLS like sibling tables.
2. **`social_wiring.cliente_empresa_participacoes`**: `id, org_id, cliente_id, empresa_id,
   participacao_pct numeric(5,2), desde (text, as printed e.g. 'mai/2006'), uf, fonte_documento_id →
   cliente_documentos (the Crednet), origem, confirmado_por/_em`. UNIQUE (cliente_id, empresa_id).
3. **Document types.** A `cliente_documento_tipos` row `serasa_crednet`, and a new empresa-document store
   (`empresa_documentos`, same shape as `cliente_documentos`: storage key, extracao_*) with tipo
   `cartao_cnpj`. Crednet extraction fills the cliente under D1 (nome_oficial, cpf, nome_mae,
   data_nascimento; fill-empty with provenance, conflict when the value differs), upserts empresas plus
   participações, and registers the SAME stored file as certidão 9 (`serasa`): numero = protocolo,
   emitida_em = consulta date, resultado derived from the occurrence blocks. Cartão CNPJ extraction fills
   the empresa's cadastral fields.
4. **Empresa certidões.** `certidao_consultas.empresa_id` (nullable FK). A CNPJ consulta belongs to the
   empresa and is reusable across deals. Backfill: every existing CNPJ consulta gets an empresa row (by
   CNPJ) and `empresa_id`; nothing is deleted or re-pointed away from its person.
5. **Derived requirement (derivacao).** empresas_exigidas(deal) = DISTINCT empresa over participações of
   {vendedores ∪ their cônjuges ∪ (compradores ∪ cônjuges if tem_permuta)}, filtered by E1 using the
   empresa's Cartão-sourced `situacao_cadastral`/`data_situacao_cadastral`. An empresa with no Cartão yet
   is `faltando: cartao_cnpj` (never silently assumed active). Reverses df54184ab
   (`derivacao.py:1245` vendedor relief; `contexto.py:288` silent-skip becomes a hard `faltando`;
   `TestSellerCertidoesNaoExigidas` is rewritten to the new rule).
6. **`social_wiring.acervos` / `acervo_itens`.** acervos: `id, org_id, drive_folder_id UNIQUE,
   numero_pasta, data_pasta, titulo, imovel_codigo, atendimento_id, status`. acervo_itens: `id, org_id,
   acervo_id, parent_id, drive_id UNIQUE, kind (folder|file), nome, rel_path, mime_type, size_bytes,
   sha256, drive_modified_at, tipo_documento, alvo_tipo (cliente|empresa|imovel|atendimento), alvo_id,
   documento_tabela, documento_id, classificado_por (regra|ia|humano), notas`. Registered from the
   drive_pull manifest. `documento_*` is set when the live upload creates the slot row, and the archive
   points at that stored copy. Files that fit no slot are stored under the acervo, flagged `sem_slot`.

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
