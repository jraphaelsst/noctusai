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

### Step b2 · Vendedora · Comprovante de endereço (image-only) → vision, `ok`, via Anexos type
| field | result | note |
|---|---|---|
| endereco_cep | ok | |
| endereco_logradouro | ok | "AL ALEMANHA" (abbreviated) |
| endereco_numero | difere | "00535": leading zeros not normalized (contract "535") |
| endereco_bairro | **errado** | vision misread "RESIDENCIAL EDINUELE" (the real one is "Residencial Euroville"). Needs a CEP→bairro cross-check or the D2 gate with a crop |
| endereco_cidade | difere | "CARAPICUIBA": accents lost (contract "Carapicuíba") |
| endereco_uf | ok | |
Written to clientes.endereco_* (origem comprovante_endereco), machine-pending.

### Step b3 · Vendedora · Certidão de casamento c/ averbação de divórcio (image-only) → vision, `ok`
- estado_civil `divorciado` ok (contract "divorciada"), regime `separacao_total` (the former marriage), data_casamento read,
  nome ok. Written with origem certidao_casamento.
- Note: the comprovante/casamento have no checklist slots; uploaded via the Anexos type picker, which works because
  extraction dispatches by tipo.

### Step c · Vendedora · Serasa Crednet (image-only) → vision, via the Anexos type (the checklist slot is hidden, G4)
Reading (`cliente_documentos.extracao_crednet`): protocolo `112566` **ok** (= contract 1.9 and the verified key);
participações **2/2 read, both CNPJs check-digit valid**; nome_mae written (origem serasa_crednet) ok; data_nascimento
1964-04-20 ok (already filled by the certidão de casamento; value correct).
🔴 **G5 (live P0c bug): no empresas / participações / certidão 9 created.** Prod log: `crednet_service._upsert_empresa:194`
→ FK 23503: it wrote the Crednet's `cliente_documentos.id` into `empresas.dados_documento_id`, whose FK targets
`empresa_documentos`. The contract said NULL for Crednet-created empresas.
🔴 **G6 (silent failure):** the crash hit a BackgroundTask AFTER `extracao_status='ok'`. The UI reports success while
the side effects never ran. The unit mock doesn't enforce FKs, so tests were green.
Both added to feat/sw-p1-fixes-1. After deploy: re-run extraction on this document and re-score.

## Round 2 (2026-09-25, prod 123c74d8e: G1–G6 fixes live)

### Re-checks
- G4 fixed live: the vendedora's checklist now carries `serasa_crednet` (8 items).
- Witnesses: synthetic CPFs set on /testemunhas (owner-authorized typing). UI finding: the list prints the CPF unformatted.

### Step c (re-run) · Serasa Crednet → re-extraction via POST …/documentos/{id}/extrair
- G5/G6 fixed live: 2 empresas + 2 `cliente_empresa_participacoes` created (origem serasa_crednet, `dados_documento_id` NULL, machine-pending).
| field | result | note |
|---|---|---|
| cnpj ×2 | ok | both exact vs `883-empresas-verificado.json` |
| participacao_pct ×2 | ok | 100 / 99 |
| desde ×2 | ok | |
| razao_social (MEI) | ok | exact |
| razao_social (REALIZA) | difere | the Crednet itself truncates to 40 columns; DB = exact first 40 chars of the real name. Not a misread. The Cartão carries the full name |
- Certidão 9 (Serasa) resultado: not yet written. By design it is deferred until the vendedora's certidões consulta exists (crednet_service §C5/§E7).

### Step d1 · Empresas tab · Cartão CNPJ REALIZA (image-only) → ocr, 1 attempt, `ok`
| field | result | note |
|---|---|---|
| cnpj | ok | check-digit valid |
| data_abertura | ok | |
| data_situacao_cadastral | ok | 05/02/2021 (the E1 date) |
| situacao_cadastral | **vazio** | G7: the transcription came back as a pipe table; the parser read the situação box as `"|"`. BAIXADA lost, so E1 can't decide |
| razao_social / motivo / natureza / porte | difere | G8: trailing `| | |` residue on every value (same root) |
| endereço (masked `********`) | difere | G8: read as `* |`, mask not detected, `endereco_mascarado=false` (no fabrication this time; the values are the mask) |
| razao_social vs Crednet | conflito | G9: D1 opened a conflict, but it's a truncation upgrade (Crednet 40-col prefix → full Receita name) |
- UI: the empresa header shows "Dispensada — Falta Cartão CNPJ" (G10). `sem_cartao_cnpj` is undecided, not dispensed.
- Dispatched feat/sw-p1-fixes-2 (G7–G10 + CPF formatting). Re-extract the Cartão after deploy.
- Open question for the owner: the MEI's Cartão CNPJ is not in folder 883. Without it E1 can't classify the MEI (the contract lists its 11 certidões).

### Step e1 · Vendedora certidões (11 of 12; nº 9 held to test the Crednet deferred fill)
- Matrix path: "Registrar certidões manualmente" from the certidões MATRIX opens with the CPF empty (G11, `CertidoesMatrizSection` doesn't pass `documento`). From the Vendedor tab the name and CPF are prefilled, so the consulta was created there with zero typing.
- G13: the manual consulta did NOT apply the already-read Crednet to certidão 9 (`criar_consulta_manual` never calls `aplicar_crednet_pendente`).
- G12: the manual consulta fans out 13 rows, generic `tjsp` + `tjsp_esaj` + `tjsp_eproc`, against the owner rule "always split".
- Each PDF uploaded through the row's upload button; structured read = `sucesso`, 1 attempt, `origem=ia`.

| item | numero | emitida_em | resultado | note |
|---|---|---|---|---|
| 1.1 RF | **vazio** | ok | **differs from the contract, doc supports DB** | the doc says POSITIVA COM EFEITOS DE NEGATIVA; the contract wrote "negativa". G14: "Código de controle" not captured as nº. The contract's code ≠ this file's code (another emission). ⇒ Relatório Fiscal now REQUIRED for this vendedora (owner rule) |
| 1.2 JF 1ª | ok | ok | ok | |
| 1.3 JF 2ª | ok | ok | ok | |
| 1.4 TRT2 digital | ok | ok | ok | |
| 1.5 TRT2 físico | difere | ok | ok | G15: "NNNNNN / AAAA" stored without the "/ AAAA" |
| 1.6 CNDT | ok | ok | ok | |
| 1.7 e-SAJ | ok | differs from the contract | ok (negativa_com_homonimos) | the doc carries only 25/08; the contract says 26/08 |
| 1.8 e-Proc | ok | ok | ok | |
| 1.10 CENPROT | differs from the contract | differs from the contract | ok | image-only browser print of a 2025 CENPROT consultation. The folder file isn't the one the contract cites; the extractor read it faithfully |
| 1.11 Fazenda (não inscritos) | ok | ok | ok | |
| 1.12 Dívida ativa | ok | ok | ok | |
- Extractor accuracy vs the documents themselves: 31/33 fields correct (2 gaps: G14, G15).

### Step e2 · MEI empresa certidões (11, folder "REGINA CNPJ")
- Consulta registered from the empresa's own panel (Empresas tab): name + CNPJ prefilled, zero typing.
- The PJ consulta fans out 13 rows: generic `tjsp` (G12 again) + **`fgts_regularidade`**, which isn't in the owner's fixed 11-item PJ set (the contract has none). Owner question.
- Score vs contract: **31/33**.
  - 2.5 TRT2 físico nº: "/ AAAA" dropped (G15, same as PF).
  - 2.9 CENPROT emitida_em: vazio. Correct: this CENPROT print carries no date anywhere in its text; the contract's date came from the office.
- Note for G14: the PJ RF (a plain NEGATIVA) DID capture the "código de controle" as nº; the PF one (POSITIVA COM EFEITOS DE NEGATIVA layout) did not.

### Step b4 · Compradores (titular = comprador 1; synthetic `[TESTE] Compradora 883` parte = comprador 2)
- 6 uploads (CNH, casamento, comprovante ×2). Everything landed on the right cliente. Typing: only the synthetic parte name (owner-authorized).
| field | comprador 1 | comprador 2 | note |
|---|---|---|---|
| nome_oficial | ok | ok | |
| cpf | ok | ok | |
| rg | **vazio** | ok (RG == CPF, legit on new CNH) | G16: CNH-e (Senatran digital, image-only) RG/órgão not read |
| rg_orgao_expedidor | vazio | vazio | G16 |
| genero | ok | ok | |
| estado_civil | ok | ok | divorciado/a |
| nacionalidade | ok | difere | "brasileiro" for a woman (G19: check the generator's inflection) |
| data_nascimento | **errado** | (set, from CNH) | G17: from the certidão de casamento, year 2008 = minor at marriage; implausible, must be rejected |
| endereço (comprovante) | CEP/nº ok; logradouro abbreviated (G18); cidade/UF **vazio** | **sem_dados** (all vazio) | G20: both bills are mixed PDFs (text pages + 1 scan), routed wholesale to OCR/vision; the text layer carries the full address |
| profissão / e-mail | vazio / n.a. | vazio / n.a. | no document carries them (manual later, owner rule) |
- regime_bens / data_casamento were written (the former marriages); the contract prints none for divorciados. Expected.
- Dispatched feat/sw-p1-fixes-3 (G16–G20).

### Step f0 · First "Gerar contrato" attempt
- 🔴 G24 (prod crash): "Gerar contrato" → whole-app ErrorBoundary, `e.startsWith is not a function`. The BE injects the rich destino object into `faltando[].sugestoes[].destino` (196cd0a25); the FE `resolverDestino` expects a string. Any card with a document-sourceable faltando crashes. Dispatched feat/sw-gerar-crash-destino.
- The click created draft contrato 2eb662d5. Readiness read via GET …/geracao (not ready):
  - faltando: profissão ×3, RG/órgão (comprador 1, G16), órgão (comprador 2), endereço ×2 (G20), negociação (imóvel, valor, parcelas, posse prazo/marco, itens integrantes, ad corpus), Cartão CNPJ ×2 (REALIZA: G7; MEI: not in folder), RF nº (G14), Serasa certidão (G13), testemunhas (select).
  - "Usar este imóvel" (ONE7515) showed "é o imóvel da negociação" but `negociacao.imovel` is still faltando: it needs the form's Salvar (UX: the link reads as done before it's saved).
  - bloqueios (12): the reference date is TODAY because no assinatura date is set. The real contract was signed 2026-09-05 (answer key). Even at that date, two rules contradict the signed contract: RF emitted 61 days before signing (rule <30), and the estado-civil certidão ~1500 days old (rule <90). Owner question.
  - avisos: e-SAJ "Negativa com apontamentos de Homônimos" is flagged as CERTIDOES_POSITIVAS (the contract prints it as a negativa). Owner question.
  - Relatório Fiscal: the vendedora's RF = PCEN ⇒ required by the owner rule, but the rule isn't implemented yet (backlog). This is its first live example.
- Negociação/financiamento: folder 883 holds document sources (ITBI guia with the transaction value, Itaú proposta, financing contract), but nothing extracts them; every field is typed. Owner scope decision.

## Round 3 (2026-09-25, prod 4b9e88e59: round-2 fixes live; migration 171 applied)
Re-extraction of the real docs (POST …/extrair, same pipeline as an upload):
- ✅ G13: re-reading the Crednet filled certidão 9 (Serasa) on the manual consulta: sucesso, negativa, nº = protocolo, fonte = the Crednet document.
- ✅ G16 (CNH-e): comprador 1's RG now matches the contract; órgão SSP/SP read.
- ✅ G20 (mixed PDF): comprador 2's comprovante now reads the full address (CEP, cidade, UF ok; logradouro "Alameda …", 1-char spelling diff vs the contract).
- ❌ G7 (Cartão situação) NOT fixed: vision transcribes the same PDF differently per call. This read matched the document TITLE for the situação label again (non-pipe shape). Round-2 was tuned to one sample. → round 3 (A).
- ❌ G9 (razão prefix upgrade) didn't fire: group provenance `dados_origem` already reads cartao_cnpj. → round 3 (B).
- NEW G25: a same-document re-read conflicts with ITSELF (Cartão motivo/natureza piped vs clean; comprador 1's endereço incomplete vs complete, both from the same comprovante row). D1 refinement: a re-read of the same document replaces its own unconfirmed values. → round 3 (C).
- The DN conflict (casamento 2008 vs CNH) is correctly a human decision (D1/D2).
- G26: comprador 2's phone-scan CNH (new format) still gives no órgão. → round 3 (D).
- Prod smoke false red: core's public site serves /_site/assets/*.js; spa_smoke fixed (f4f9a6274).

---

## CHECKPOINT 2026-09-28 — handoff (session 018BxYjwcVbyKtpF4e9a1PqU)

**Prod state:** social-wiring = `ef4682de1` (healthy, swap-verified); core = `95863d114`. main = prod = `ef4682de1`; prod-backup = `95863d114`. All work below is LIVE.

### Shipped this session (all on prod)
- DPS tripwire judged **per page** (Itaú p7 mention + p8 insurance words no longer refuse the contract).
- Itaú Quadro vocabulary (no "QUADRO RESUMO" title; anchor `CONDICOES DO FINANCIAMENTO`), CREDOR→bank, prazo specific-first, `valor_financiado` = "Recursos do financiamento"/"Valor destinado…" (NOT "saldo devedor").
- Seller account from Itaú item 8 (`VALOR A SER LIBERADO AO VENDEDOR` + following `Rótulo: valor` lines) → favorecido via existing `_aplicar_favorecido_vendedor`. Prompt hint "table borders are not text" fixed Haiku's `|033`→`1033` misread (2/2 fresh reads correct). Unknown code → `banco_impresso` + aviso `conta_credito_vendedor_banco_nao_reconhecido`.
- Proposta: "Valor do crédito" = financiado; prazo parsed in months.
- ITBI label synonyms (f3ccfcc0d); shared seed box-matcher `documents/caixa_rotulada.py` (N=3 `_campo` formalized: longest-first, word-boundary, other-field guard); FGTS synonyms + aviso `quadro_resumo_fgts_ausente`.
- Certidão de casamento: `NUMERO DO CPF` row broke 2-nubente collector; tabular DN; no cross-spouse DN fallback.
- Transcription truncation: stop-reason normalized across providers, 1 retry at 8192, else `transcricao_truncada` (permanent error in SW).
- CORS: `X-Noctus-Client` added to seed default allow_headers (fixed fleet-wide "Servidor indisponivel (/api/me/consents | /api/admin/llm-spend)" toasts; verified 200 live).
- Audit hardening (SW): shared `services/extracao_job.py` runner (never `ok` before apply) for identidade/empresas/matrícula; sweep skips non-retentável; FGTS-missing ≠ 0 (`fgts_nao_lido`); conflict dedupe supersedes on new value; favorecido machine-write resets confirmation / manual edit = confirmed; unverifiable membership → conflicts (`pertencimento_nao_verificado`); situação de ônus → indeterminado when any act unclassified; foro comarca scoped to abertura.
- Tooling: gate_sweep runs test subprocesses without `.env` secrets + redacts summaries (MCP server must be reloaded — `/mcp` — for the toolkit to use it).

### Model decision (owner): **Haiku 4.5 stays.** Measured on real 883 scans (providers.py docstring): Sonnet won only the bank code, failed ITBI (4096 cap), ~4.5× cost.

### NEXT (pick up here)
1. **Re-read 883 negociação docs on prod** (not done — Chrome extension disconnected; in-container exec was refused by the auto-mode classifier). Route: owner's logged-in tab → `POST /api/clientes/0e60427a-cb54-44dc-bdfe-311f7f26115a/financiamento/documentos/<id>/extrair` for contrato `6f1f48f3…`, guia ITBI `4483ceab…`, proposta `9963a0d8…`; then score vs `~/.noctusai/private/answer-keys/883.json` (values never printed).
2. **Manual fields** (profissões, sinal/intermediária, corretagem/intermediários, ad corpus, 2 testemunhas): owner-authorized but blocked twice by the classifier (PII/sensitive-source) — owner enters in UI or adds a permission rule.
3. Owner decisions still open: MEI Cartão CNPJ; comprador 1 DN (confirm CNH value in review).
4. **Rotate the Resend API key** (was echoed by the old gate_sweep).
5. Follow-ups logged in code: `conjuges.py` tabular per-spouse scoping; extend `pertencimento_nao_verificado` to fgts/proposta/agente/situação; `NOC-REMEDIATE[extracao-varredura-colunas-erro]` (add `extracao_erro` to 2 sweep column lists); `NOC-REMEDIATE[imovel-rejeitado-antes-decidido-por]`; `NOC-REMEDIATE[extracao-job-runner-adopt]` (crednet + negociação onto the runner).
6. Hygiene: clean up merged worktrees (`noctus.dev.task_branch action=cleanup`) — sw-itau-conta-vendedor, cors-noctus-client-header, gate-sweep-env-hygiene, doc-transcricao-truncada, sw-transcricao-truncada-msgs, sw-matricula-foro-onus, seed-box-matcher, doc-casamento-883, sw-extracao-job-runner, sw-negociacao-hardening, sw-extracao-job-tests-schema, docs-p1-883-checkpoint.
