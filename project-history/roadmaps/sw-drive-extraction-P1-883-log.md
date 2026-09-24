# P1 · folder 883 (EUROVILLE) — live extraction validation log

> Durable log for roadmap `sw-drive-extraction-2026-09.md` P1. Prod code under test: 840e7809a (P0c).
> This file is redacted and holds NO personal values. Real values and the answer key live in
> `~/.noctusai/private/answer-keys/883.json` + `883-empresas-verificado.json` (0600).

## Protocol (owner rules, 2026-09-24)

1. **Only uploads, never typing.** The agent uploads each real file through the prod UI (browser MCP),
   one at a time, in the human order. It never types a value into any field. What the automated
   extractor writes is the result. A missing or wrong value is an **extractor gap**, recorded here,
   never hand-filled.
2. **Where each file goes.** Person documents go in the person's checklist on the atendimento card.
   **Imóvel documents go on the imóvel details page** (matrícula, IPTU espelho, CND IPTU), are extracted
   per document, and are stored on the imóvel (`imovel_dados`) for later contract generation.
3. **Records.** The imóvel is Vista listing **ONE7515** (883's documentary match, empty before P1:
   0 documentos, 0 imovel_dados). People are linked to existing records by CPF; nothing is deleted.
   The RODRIGO card and its manual imóvel `EUROVILLE-535` belong to noctusai-1b and are not touched.
4. **Order.** (a) imóvel docs on ONE7515 → (b) basic person docs → (c) Serasa Crednet →
   (d, held until noctusai-e4's slices D/E land) Empresas tab + Cartão CNPJ → certidões → contract
   generation → diff vs the signed contract.
5. **Scoring.** Every DB field the upload should fill is compared to the answer key:
   `ok` (matches) · `errado` (wrong) · `vazio` (not filled) · `pendente` (filled, machine-pending,
   awaiting D2 confirmation) · `conflito` (opened a conflict). Each non-ok entry names the likely cause.
6. **Cost.** Record per step: extraction source (texto/ocr), model calls, cost where the usage sink
   reports it.

## Results

_(appended per step)_
