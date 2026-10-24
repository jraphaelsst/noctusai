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
| 🔴 **The agent never fills a field that a pack document should supply** — no certidão número/data, no título redação, no transfer date, no RG digit, no estado civil read off a PDF by eye. A miss stays empty, becomes a finding, and is fixed **in code** (reader/extractor) until a re-read (`Reler` / "Voltar à leitura automática") fills it by itself | We are validating the extraction mechanism; a hand-filled miss is a bypassed error that hides the defect and makes the score lie (799: Serasa nº, CENPROT dates, título and última transferência were typed by the agent — owner caught it, all reverted) |
| Only **negotiation-only terms** (parcelas, posse, intermediação, termos, testemunhas, condições especiais) may be typed — from the deal's proposal/data sheet, or from the answer key when nothing else exists — and each is logged with its source as **operator-entered**; the score reports them apart from extraction | No document carries them, so typing them tests the generator, not the intake — they must never count as an extraction pass |
| Every defect found → a finding row (`F#`) with the mechanism → a fix slice (`task_branch` + engineer) → shipped → the doc re-extracted (`Reler`) — **fix all, always**; never "accept" or route around an extractor miss | The run is a fix loop, not a report; the system must work by itself |
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
| 5.x | Certidões: 🔴 **EMIT, do not upload** (owner 2026-10-24: "we are to emit the certidões and validate automated data extraction") — per party row **Solicitar emissão (todas)** (paid InfoSimples; only parties the contract lists: sellers, antigos, their PJs — never buyers unless listed). Emitted results carry today's date/nº (scored as re-emitted). Only rows the system cannot emit (manual-only: TJSP e-SAJ/e-Proc, Serasa from the Crednet; Dívida ativa without the office GOV.BR login; a source the provider paused) fall back to the pack PDF via **Enviar PDF**, and each such fallback is logged. A cell read incompletely is **never** completed via Editar — it is a finding; after the fix ships, "Voltar à leitura automática" | Certidões tab | `certidao_consultas.origem='automatica'` + `certidao_resultados` per cell: `resultado`, `numero`, `emitida_em`, owner name; failures carry `erro_mensagem` (provider vs. ours) |
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
- **Keep exactly one party row expanded** in the certidões grid, and before every Confirmar assert the dialog title names the
  target party (`"<CERTIDÃO> — <NOME>"`). With two rows open, a "first table" helper writes into the wrong person
  (799: a seller's real negativas were overwritten with "não emitida" and had to be restored by hand — a manual value
  is protected from `Reler`, by design).
- Radix select lists align the **currently selected** item over the trigger, so option positions move with the
  preselected value — measure the option's rect each time instead of reusing coordinates.
- If the session drops to the public landing, stop and ask the owner to log in again (never type credentials); check
  the auth logs for a server-side `/logout` (799: a product cookie-session drop revoked the SPA's own GoTrue session).

## 4 · Score and read the result

- `contract_score` renders read-only from the live DB, writes a masked scorecard, returns verdict
  counts only. Material terms fail; wording/structure are observations (see the harness README).
- Before chasing a material divergence, check the **reference** is right: two runs found the signed
  contract wrong (a shortened name the marriage certidão contradicts; an RG typo the office copied
  from its own data sheet). Record those as "reference wrong", never "fix" the extraction toward them.
- Template-era differences (e.g. a Feb-2026 contract with a generic "documents the sellers will
  deliver" list instead of itemised certidões) are observations, not generator defects.

### 4.1 · The gap-marker render (a NOT-`pronto` card) — gated inputs and their stand-ins

A not-`pronto` card is scored from `harness.dados_com_marcadores` (every gap is a visible marker, never
a silently missing word). The generator `assert … # gated`s / `# type: ignore`s inputs that the readiness
gate (`derivacao`) guarantees in production, so the marker copy must supply a stand-in for **each** one.
Inventory (audited 2026-10-24; no assertion lacked a readiness rule — none is a production 500 at
"Gerar versão"):

| gated input (`contexto.py`) | readiness rule that guarantees it | marker-mode stand-in |
|---|---|---|
| `imovel`, `valor_negociado` | `negociacao.imovel`, `negociacao.valor_negociado` | money sentinel (imóvel absent = no render) |
| `endereco_curto` (imóvel + each permuta ativo) | `matricula.atos` / `imovel.endereco_registro_texto` / `matricula.permuta.<id>.atos` | `endereco_registro_texto` = marker, only when the matrícula yields no street |
| `cartorio_partes(...)` under `tem_onus_ja_quitado` | `imovel.numero_registro_imoveis` (empty or no city) | `CARTORIO_LACUNA` |
| `onus_fonte_atos[0]`, `AtoCitado.numero` | `matricula.onus_fonte`, `ONUS_FONTE_INVALIDA` | synthetic ato / `999` |
| `termos.onus_baixa_protocolo_em` | `negociacao.onus_baixa_protocolo_em` | date sentinel |
| `favorecidos[...]` (sinal tranche, divisão, corretagem) | `negociacao.parcela.<id>.favorecido`, `…divisao.<n>.favorecido`, `FAVORECIDO_INEXISTENTE` | one synthetic favorecido |
| `Parcela.valor`, `Intermediario.valor`, `DivisaoFavorecido.valor`, `pct_comissao` | `negociacao.parcela.<id>.valor`, `…intermediario.<id>.valor`, `…divisao.<n>.valor`, `negociacao.pct_comissao` | money / `999` sentinel (`harness.ENTRADAS_ESTRUTURAIS`) |
| `representantes(...)[0]` of each PJ | `partes.pj.representante` | blank synthetic representante |
| sinal parcela, fixed `posse_data` | `negociacao.sinal`, `posse.data` | synthetic sinal / date sentinel |

Declared **no-render** cards (raise → `incompleto_sem_render`): no seller or buyer on a side, no imóvel,
a permuta parcela whose imóvel is not loaded. `tests/e2e_contrato/test_harness_fuzz_marcadores.py` blanks
every field of every dataclass (and drops list elements) one at a time over every fixture variant plus
the PJ / já-quitado / divisão / sinal-em-partes / permuta scenarios, and asserts the marker render never
raises (outside that list) **and** the harness rewrites only declared fields — a production-optional field
(`Endereco.complemento`, intermediário representante, `prazo_pendencias_dias`, a resolvable
`endereco_registro_texto`) is never turned into a marker. A new gated input fails that test until it gets a row.

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
| 799 r2 (2026-10-24, score) | Marker render crashed on a missing favorecido and invented gaps on optional fields (harness fixed: per-type marking); matrícula act quotes carried signature lines + the certidão footer into the contract; vendedor married to a separate anuente lost "casado"; all-female group printed "COMPRADORES/casados"; free-text forma "por meio de pago aos…"; readiness avisos added (post-signing document, PJ intermediário without representante, sede incomplete, doação em adiantamento de legítima without doadores anuentes); CNH-only RG now a contract gap like the checklist. Reference deviations kept as observations: multa 20k vs the owner's multa=sinal rule; shortened buyer name |
| 874 (2026-10-24) | Extension-less office files (WhatsApp/Drive) refused as octet-stream (type now sniffed from bytes); a failed search rendered as "nenhum imóvel" + "cadastrar novo" (duplicate risk); ANEXOS/certidão uploads refused by the server vanished without a message; the WhatsApp-triage tipo was offered in the operator picker; a birth certidão filed as casamento was read as "casado, alta" and applied (reader now trusts the document's own title; delete reverts applied values); a utility bill's CEP/city came from the issuer's sender block (titular block only + CEP cross-check); antigos panel read the imóvel from the empty negociação instead of the atendimento's principal (one canonical resolver; no auto-billed emission on legacy deals); a party without CPF could not receive certidão PDFs (and the PDF's CPF now fills it); grid stale after async emission, negociação panel stale after save, condomínio pick looked saved but wasn't; "localizada na <rua>, nº" not read as the registry address; e-SAJ certidão completes a CNH-only RG check digit. Live emission: 5/9 automatic certidões emitted and read correctly; CENPROT/Fazenda (provider paused), Receita (source down), Dívida ativa (needs office GOV.BR) did not. Process: 5 engineer branches bounced on the doc-staleness gate — briefs must name the gate command |
