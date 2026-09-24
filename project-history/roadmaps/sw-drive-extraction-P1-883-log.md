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

### Step a1 · Matrícula → imóvel ONE7515 (2026-09-24, prod 840e7809a)

- File: 3 pages, "GdPicture.NET". Its text layer holds ONLY the ONR validation stamp ("Valide este documento…",
  once per page); the whole body is a scanned image. The stamp strip leaves nothing, so the vision rung runs.
- Two jobs run on upload:
  - number read (`imovel_documentos.extracao_*`) → `sem_dados`, source ocr, 1 attempt
  - full transcription (`matricula_extracoes`) → `concluida`, 5,751 chars, starting "Mat. 3917 - Página 1/3 - PROT. …"
- Scorecard (`imovel_dados`, vs answer key 883):

| field | result | note |
|---|---|---|
| numero_matricula | **vazio** | GAP: the transcription carries "Mat. 3917" in its heading, but the number job (vision) found none and nothing promotes it from the finished transcription. Fix: derive it deterministically from the transcription heading (saves a vision call too). |
| numero_registro_imoveis | ok | "Oficial de Registro de Imóveis da Comarca de Carapicuíba/SP" ≈ contract "Cartório de RI de Carapicuíba" |
| prefeitura_cadastro_imobiliario | difere | extracted value carries a trailing "-1" check digit; the contract prints it without. Owner to rule which form is canonical. |
| titulo_aquisitivo_texto | ok | matches Cl. 1ª (escritura 28/02/2023, 1º Tabelião Guarujá, L. 958, fls. 265/270) |
| situacao_onus | ok | livre (Cl. 4ª: no ônus) |

- UI finding: the "Lendo o número da matrícula…" spinner stayed after the DB reached `sem_dados`. The page didn't poll to
  the terminal state; a reload showed "Documento lido, mas nenhum número de matrícula foi encontrado".
- Rule question raised by the page: "Certidões dos antigos proprietários são obrigatórias (transferência < 5 anos, R-4
  permuta 11/07/2023)". The signed 883 contract lists no certidões for antigos proprietários. Owner to rule.

### Step a2 · Guia de IPTU (espelho) → ONE7515
- The structured read (`estrutura_status=ok`) extracts only `inscricao_imobiliaria` (by design, `CAMPOS_ESTRUTURA_POR_TIPO`).
- It read `23231.42.11.0377.00.000`, which DIFFERS from the matrícula-sourced `…000-1`. D1 worked: no overwrite,
  `imovel_campo_conflitos` opened (pendente, notified). The contract prints the IPTU form (without "-1").
- Proposed rule for the owner: the prefeitura's own documents (Guia/CND IPTU) are authoritative for the inscrição municipal;
  the matrícula's trailing DV is registry notation.

### Step a3 · CND de IPTU → ONE7515 (Certidões do imóvel)
| field | result | contract 3.2 |
|---|---|---|
| numero | ok `29834/2026` | nº 29834/2026 |
| emitida_em | ok `2026-09-04` | emitida em 04/09/2026 |
| validade_ate | ok `2026-12-03` | (90 days, printed) |
| resultado | ok `negativa` | Negativa |
All values are machine-pending (`origem=ia`, `confirmado_em` null) until D2 confirmation. Text layer, no vision call.

### Imóvel phase summary
- 3 uploads, 0 values typed. `imovel_dados`: 4/5 contract fields correct; 1 gap (numero_matricula); 1 conflict correctly
  raised (inscrição "-1"). CND: 4/4 correct.
- Gaps to fix: (G1) promote numero_matricula from the finished transcription heading "Mat. NNNN"; (G2) the imóvel
  documents card must poll until the extraction is terminal (the spinner stuck on "Lendo…").
- Owner questions: (Q1) antigos proprietários certidões (transfer <5y: the page says mandatory, the 883 contract has none);
  (Q2) inscrição municipal source priority (IPTU > matrícula?).

### Step b0 · Test card setup
- Lead `[TESTE P1] 883 Euroville` created via Funil → "Novo lead" (owner-authorized typing: name, fake example.com
  e-mail, código ONE7515). The trigger spawned atendimento 7b9d07df (titular cliente 0e60427a).
- GAP (G3, product): "Adicionar vendedor/comprador" only CREATES a person (nome + celular). There is no pick-existing
  option, although the backend `compradores_service.adicionar` accepts `parte_cliente_id`. Owner decision: synthetic parties
  (`[TESTE] Vendedora 883`, …) receive the real documents, so no real record is duplicated or merged.
- UI finding: after adding a parte by name, its checklist shows "Nome Completo —" (the typed name isn't shown there).

### Step b1 · Vendedora · CNH (image-only, TurboScan) → vision, 1 attempt, `ok`
| field | result | note |
|---|---|---|
| nome_oficial | ok | written (origem cnh), confiança baixa |
| cpf | ok | exact; confiança ALTA although read by vision (check-digit valid). The P0c rule caps vision identifiers at baixa for new extractors; the identity extractor predates it (triage) |
| rg | errado | `13032360`: the DV "-3" is dropped (contract: 13.032.360-3) |
| rg_orgao_expedidor | ok | SSP/SP |
| nacionalidade | difere | "brasileiro" for a woman (contract: "brasileira"). OK if the generator inflects by gênero, else wrong |
| data_nascimento | **vazio** | GAP: the CNH prints DATA NASCIMENTO; not read (the Crednet supplies it next) |
| genero | n/a | a CNH has no sex field |
- UI finding: after the CNH read reached `ok` in the DB, the card still showed "Lendo…", "Falta: RG e CPF" and the
  qualificação list as missing (the same stale-UI class as the imóvel page, G2).

### 🔴 BLOCKER found live (G4): the Serasa Crednet slot is hidden for EVERY vendedor
- GET /documento-checklist for the vendedora returns 7 items and no `serasa_crednet`.
- Root cause: `documento_checklist_service._e_certificando` resolves the deal via `resolve_atendimento_id`, which only
  finds atendimentos where the cliente is the TITULAR. A vendedor is always an `atendimento_partes` row, so the lookup
  gets `AmbiguousAtendimento([])` → False, and the parte/cônjuge branches are dead code. Unit tests missed it, since no
  fixture had the real titular-comprador + vendedor-parte shape.
- Dispatched: feat/sw-p1-fixes-1 (G4 + G1 matrícula nº + inscrição precedence + CNH DN/RG DV + G2 polling). Step c
  (Serasa) waits for its deploy.
