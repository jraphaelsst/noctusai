# SW contract generation — e2e validation runbook (real deal replay)

> **What this is.** The repeatable procedure for replaying a *real, already-signed* deal through
> social-wiring in prod — lead → uploads → extraction → typed data → readiness → generation → score
> against the signed contract — so the document extractors and the generator are validated on real
> files, run after run, by steps instead of memory. Born from the deal-857 (2026-10-21) and deal-799
> (2026-10-22) runs. **PII-free by construction:** this doc holds the process only; every per-deal
> artifact (pack, findings log, answer key) stays under `~/.noctusai/private/` or the session
> scratchpad and is never committed.
>
> Tools: `noctus.dev.drive_census` (census + answer keys) · `noctus.dev.contract_e2e_pack` (ordered
> upload pack + `run.json`) · `noctus.dev.contract_score` (read-only render + score) · harness depth in
> `products/social-wiring/backend/tests/e2e_contrato/README.md`.

---

## 0 · Ground rules

| Rule | Why |
|---|---|
| Never upload anything from `99-GABARITO-NAO-SUBIR` (signed contract, D4Sign, aditivos, bundled `CERTIDÕES X.pdf`) | It is the answer key; uploading it makes the run circular. There is no bundle splitter — one file per cell |
| The agent never types bank/account numbers, passwords or tokens | Safety boundary. Favorecido bank data stays a gap (`dados_indisponiveis` in the score) or is filled by the owner |
| The agent never logs in. A dropped session = ask the owner to log back in | Credentials are the owner's |
| Typed data comes from a source the operator would really have (the deal's proposal/data-sheet files in `98-OUTROS`), and every typed value is logged with its source | Typing an answer-key value tests the generator, not the intake — record it as such |
| Every defect found → a finding row (`F#`) with the mechanism → a fix slice (`task_branch` + engineer) → shipped → the doc re-extracted (`Reler`) | The run is a fix loop, not a report |
| Real PII stays local: tests use synthetic fixtures mirroring the real layout | `KB § PATTERNS/compliance/testing.md` |

## 1 · Select the deal (blind + rich + scorable)

1. Rank census folders: `~/.noctusai/private/census/*.json` × answer keys `~/.noctusai/private/answer-keys/*.json`.
2. Keep only answer keys with `status == "ok"` and `fonte.tipo == "d4sign"`, `confianca == "alta"`
   (an image-only signed contract — `contrato_so_imagem` — cannot be scored).
3. Exclude the 8 template reference contracts (`products/social-wiring/contracts/01–08*.docx`) and
   deals already run.
4. **Check prod for prior seeding** — query `social_wiring.clientes` by the answer key's CPFs: deals
   seeded by the P2/P4 phases carry `[P2]`/`[P4]` names and are **not blind** (871, 858, 859, 881–897
   were). Pick a deal with 0 CPFs in prod.
5. Prefer variety vs previous runs: identity docs (CNH/RG/CIN) present, marriage/birth certidões,
   a real certidão de matrícula, CND condomínio, financing, PJ sellers (Crednet participations).

## 2 · Stage the pack

```
noctus.dev.contract_e2e_pack numero=<n>                       # plan (counts only, no PII)
noctus.dev.contract_e2e_pack numero=<n> action=stage confirm=true dest=<session scratchpad>/docs-<n>
```

- **Stage into the session scratchpad** (or a folder the owner added with `/add-dir`): the browser
  upload tool only accepts session-readable paths — `~/Downloads` is refused.
- Phases: `01-IMOVEL` · `02-PESSOAS` · `03-SERASA` · `05-CERTIDOES` (one file per cell, `NN.mmm-k_`
  prefixes) · `06-FINANCIAMENTO` (reference) · `98-OUTROS` (look here for the typed-data sources:
  proposal, "Dados Vendedores", "Ficha Proposta", "Info PP") · `99-GABARITO-NAO-SUBIR`.
- **Matrícula choice:** the pack orders a certidão before a visualização, but upload **the document
  the deal used at signing** — check the signed contract's certidões clause (`"Visualização da
  Certidão da Matrícula … emitida em <data> (Arisp)"` ⇒ the visualização; a certidão issued after the
  signing date is post-signing material). Also check each certidão's issue dates against the signing
  date before deciding upload vs "não emitida".
- Open a private findings log next to the pack (`<n>-findings.md`, table `# | step | result | finding`).

## 3 · The run (prod, browser, in this order)

| # | Step | Where | Validate (DB / screen) |
|---|---|---|---|
| 0.1 | Imobiliária + witnesses exist | Configuração → Imobiliária | rows complete |
| 0.2 | Search the property in Vista; else **Cadastrar imóvel** (título, categoria, condomínio — create the suggestion if new, endereço, CEP, valor, processo nº) | `/imoveis` | `SW-xxxx` created |
| 1.1 | Upload the matrícula | imóvel → Documentos do imóvel (tipo Matrícula) | `imovel_documentos`: `extracao_matricula`, `tipo_documento_matricula`, `emitida_em` vs the page's certification date |
| 1.2 | Espelho IPTU (Guia de IPTU) · CND IPTU · CND condomínio | same card, pick the tipo first | `inscricao_imobiliaria`; CND `emitida_em`/`resultado` |
| 0.4 | **Novo lead**: buyer titular, phone (from the proposal), imóvel, corretor | Funil → Novo lead | card in Qualificação (search it — new cards don't surface at the top) |
| 2.1 | Titular identity doc (CNH/RG/CIN slot) | card → Geral → Dados obrigatórios | nome/CPF/RG/órgão/nascimento; a CNH never carries the RG check digit — the checklist flags it |
| 2.2 | Typed data (email, profissão, gênero, RG DV, nacionalidade, mãe, estado civil, endereço) | Dados do cliente → pencil | setting `Casado(a)` reveals the marriage-certidão slot |
| 2.3 | Marriage certidão → cônjuge | Dados do cliente → Certidão de casamento | `extracao_conjuges` has 2 entries; spouse auto-linked; regime + data do casamento applied |
| 2.4 | Cônjuge (if not auto-linked): Cônjuge tab → Adicionar cônjuge by CPF; upload its CNH; typed data | Cônjuge tab | same as 2.1/2.2 |
| 2.5 | Each seller: Vendedor → Adicionar vendedor by CPF (proprietário; spouses that sign also as vendedor) | Vendedor tab | row per party |
| 3.1 | Each seller's **Serasa Crednet** | seller row → checklist Serasa Crednet | identity filled; **Empresas** tab gets the PJ participations + registry situação; certidão cell 9 filled |
| 2.6 | Seller identity doc + typed data; marriage/birth certidão (solteiros: ANEXOS → pick tipo "Certidão de nascimento" **then** upload) | seller row | qualificação "completa para o contrato" |
| 4.1 | Confirm each participação (or "Não é do vendedor") | Empresas | `Participação confirmada`; baixada > 5 y ⇒ certidões dispensadas |
| 8.0 | **Gerar contrato** → draft: Assinatura digital/física, **Data de assinatura = the real signing date**, "Processo anterior à plataforma" (with motivo) for a historical replay, matrícula description source, **Imobiliária que assina** | Contratos | readiness list ("Faltam dados") |
| 5.x | Certidões: per party/company row, per cell — **Enviar PDF** for each folder file; **Preencher manualmente → Não emitida** for cells the folder lacks (they print as pendências) | Certidões tab | `certidao_resultados` per cell: `resultado`, `numero`, `emitida_em`, owner name |
| 7.x | Negociação / parcelas / favorecidos (owner fills bank data) / intermediação / termos / financiamento | card tabs | readiness section clears |
| 8.1 | Readiness to `pronto`; **Gerar versão** | Contratos | version row |
| 8.2 | Score | `noctus.dev.contract_score cards=[{numero, org_id, cliente_id, contrato_id}]` | verdict + categories; add the deal to `~/.noctusai/private/p3/cards.json` |

**Readiness reading:** red = bloqueio, orange = aviso (prints with a warning), grey list = faltando
with "Resolver →" deep links. Work top-down; every item is either a typed fact, a document, or a
finding.

### Automation notes (browser agent)

- File inputs are hidden; `file_upload` needs the real `input[type=file]` ref. The certidões grid
  has **one input per expanded row**: click the row's "Enviar PDF" (sets the target cell), then set
  the file on that row's input; re-`find` the input after expanding another row.
- The card's left rail only reacts when hovered (expanded); target tabs by their accessible ref.
- Radix selects: click the trigger, then the option; typeahead+Enter is unreliable. In the manual
  certidão dialog the "Não emitida" option sits a fixed offset below the trigger.
- The grid lags behind the DB; verify uploads in `certidao_resultados` / `cliente_documentos` /
  `imovel_documentos`, not the screen.
- Dates: click the day segment first, then type `ddmmyyyy`.

## 4 · Score and read the result

- `contract_score` renders read-only from the live DB, writes a masked scorecard, returns verdict
  counts only. Material terms fail; wording/structure are observations (see the harness README).
- Before chasing a material divergence, check the **reference** is right: two runs found the signed
  contract wrong (a shortened name the marriage certidão contradicts; an RG typo the office copied
  from its own data sheet). Record those as "reference wrong", never "fix" the extraction toward them.
- Template-era differences (e.g. a Feb-2026 contract with a generic "documents the sellers will
  deliver" list instead of itemised certidões) are observations, not generator defects.

## 5 · Close the loop

1. Every finding → fix slice (seed reader / SW service / FE), synthetic tests, integrate (merged-tip
   gates), ship (`noc-ship`), then **Reler** the affected documents in prod and re-check.
2. Recurrence: a finding seen on two deals is N=2 → formalize (detector/test), never a third patch.
3. Append the run's PII-free learnings here (§6) and the extractor-specific ones to the matching KB
   doc (`CERTIDOES-LEVANTAMENTO-LEARNINGS.md`, seed module docstrings).

## 6 · Learnings by run

| Run | Extractor / generator findings (fixed unless noted) |
|---|---|
| 857 (2026-10-21) | Crednet "Resumo da consulta" variant unparsed; manual estado civil stored labels not tokens; profissão closed vocabulary blocked typed values; cartório city lost on a wrapped ARISP header; bank as adquirente in R.6; matrícula visualização vs certidão kind + ARISP view-stamp date from the PDF text layer; an act's own "selo digital" is not a certidão marker |
| 799 (2026-10-22) | Matrícula certidão closing line "CITY-UF, - dd de mês de aaaa" missed + an LLM date equal to the last act accepted; marriage certidão "passará a usar o nome de X" split into a phantom 3rd/4th spouse (no cônjuge, confidence nenhuma); 1977 certidão: 8-word extenso year read as 1970, unqualified "comunhão de bens" pre-Lei 6.515 = universal, estado civil casado without averbação; ANEXOS upload without a tipo silently dropped; matrícula picker listed other deals' matrículas; CENPROT `emitida_em` never read (2nd deal); Crednet no longer fills certidão cell 9; certidão age counted vs today instead of the signing date; rotated new-layout CNH RG not read (open); nacionalidade suggestion ignores gênero (open); spouse does not inherit estado civil (open); mid-session logout (under investigation) |
