# Document extraction — what real documents taught us

> **Status:** living document, started 2026-09-28 from the P2 reference corpus (the 10 most
> recent closed deals, 641 files, re-entered file-by-file on fresh prod cards and scored
> against their signed contracts). Every entry below was **measured on a real document**, then
> fixed at the root and re-scored. Add to it; never delete a lesson — supersede it.
>
> Related: `CONTEXT/PRODUCTS/social-wiring/CONTRACT-FIELD-PROVENANCE-MAP.md` (which document
> feeds which contract field) · `CONTEXT/PATTERNS/common/extractor-correctness-vs-mirror.md`.

## 0 · The method (why this document exists)

Extraction is its own process, measured separately from contract generation (owner standard,
2026-09-28). The loop:

1. **Ground truth** = the signed contract's values, parsed into an answer key. The document is
   scored first; a contract value that no folder document supports is logged as a
   **contract↔document divergence**, never "fixed" in the extractor.
2. **Transcribe once, parse many.** A page's vision transcription is paid once and cached (by
   file hash + prompt); every parser change is then re-scored for free across the whole corpus.
3. **Upload through the real UI** (owner rule R5) — the product path is what gets measured.
4. **Fix at the root, re-score the corpus, never regress.** A fix tuned to one sample is not a fix.

## 1 · Mechanism invariants (non-negotiable)

- **Every page, one call per page, never batched.** Transcription is page-by-page; the
  *structured read* must be page-by-page too, with a deterministic merge (first page with a value
  for número/datas; resultado = the **most severe** across pages). Joining pages into one prompt
  silently loses page 2+.
- **No silent truncation, no silent page caps.** A `[:4000]` cut on certidão text let a
  "positiva" on page 2 read as "negativa"; a 3-page default cap failed or dropped longer scans; the
  financing contract read only 8 pages. A limit, if any, must fail loudly.
- **A reading that cannot be trusted is routed to a human, never auto-applied.** Low legibility
  (see §2) → aviso + mandatory human confirmation at the review gate (owner decision 2026-09-28).
- **A reading never overwrites an owner correction — it asks** (owner order 2026-10-20, deal 876: a
  re-read of the ficha put back the typo "aposentanda" the owner had corrected). Predicate
  `identidade_extracao_service.correcao_do_dono`: `<campo>_origem='manual'` + a value + NOT a phantom
  `manual` (a form re-saved unchanged over a document, proven by its own audit row — that one stays
  healable by a same-value read, the 2026-10-19 rule). A disagreeing reading opens a `pendente`
  conflict with `protege_correcao=true` (SW migration 291): approve = the document's value with its
  document provenance, reject = the correction stays and the proposal never returns
  (`ja_rejeitado_pelo_usuario`). It never blocks contract generation (the owner's value prints);
  the readiness report shows it as `correcoes_contestadas` with approve/reject. The resolver backfill
  never decides one. Only exception kept: a value PROVEN invalid (check digit / another type's
  identifier). The stamp is compliance-by-construction: `update_cliente` stamps `manual` server-side
  only on a value that actually changed. Raw DB patches that leave a document `origem` are NOT
  corrections — correct data through the app, or set `origem='manual'`, `documento_id=NULL`.
- **Watch the vision request budget.** A page is re-rendered at lower DPI (400 → 150/100) to fit
  the ~5 MB request limit; dense pages lose accuracy at 100 DPI. Prefer a compressed image format
  over dropping resolution.

## 2 · How the vision model actually fails (Haiku 4.5, identity prompt)

| Behaviour | Seen on | Consequence | Root fix |
|---|---|---|---|
| **Mislabels an adjacent field**: writes the holder's name under "1ª HABILITAÇÃO" (the CNH-e prints "1 NOME" beside it) and emits no NOME row | 4/9 CNH-e | name never read | the 1ª-habilitação field is a *date*; a name-shaped, digit-free value there is the displaced NOME (`media`) |
| **Hallucinates on a low-resolution capture** (phone screenshot of the CNH Digital app): invents values that contradict their labels ("DATA DE NASCIMENTO: BRASILEROCA", "CEP: 99 de abril") and takes the **mother's name** (filiação) as the holder | 1 app screenshot | wrong nome + wrong CPF written to a real person (worse than empty) | legibility gate (label/value type mismatches, "(ilegível)" share, holder == filiação) → human gate. Sonnet reads the same image correctly — escalation is an option |
| **The MRZ is also a vision read**: misreads one letter | 1/3 MRZs | a strict MRZ-vs-label check erased a correct name | single-edit token differences agree; a real disagreement demotes to `baixa` (human), never blanks |
| Transcribes the page's decoys faithfully — the RG verso's "LEI Nº 7.116", a CPF-shaped "Matrícula" | RG, casamento | a decoy number becomes a candidate | teach the parser the decoy (statute refs, matrícula labels) |

### 2a · Measurements that change how we build (P2, 2026-09-28)

- **Run-to-run variance is material.** The same RG, same code, same model: 4 local reads found the
  RG, the prod read did not. A single vision read is a *sample*, not a fact → **re-read** (second
  sample or stronger model) when a core field is missing or the read is flagged.
- **Prompt tuning is a weak lever; structure is the strong one.** An identity prompt v2 with explicit
  label rules, measured on all 10 deals: +1 name, +1 CPF filled, but CPF wrong 2→4, RG wrong 7→9,
  gênero 15→11 → **not shipped** (a wrong value on a real person is worse than a missing one). A
  comprovante-specific prompt: 4/9 → 4/9. Parser-side structural rules moved CNH names 5/11 → 9/11.
- **A stronger model is the lever for hard images.** Sonnet 5 read the hallucinated app screenshot
  correctly; comprovante addresses Haiku 4/9, Sonnet 6/9, union 7/9. Escalate selectively (on
  missing core field / low legibility), not by default.
- **The re-read escalation, measured (shipped `releitura.py`).** Trigger = OCR source ∧
  (`leitura_comprometida` ∨ the tipo's core fields unmet); 19/62 corpus docs escalated to Sonnet 5.
  Party fields: nome right 23→27, CPF 22→27, RG 14→16 (wrong 7→5); 28 improvements, 0 regressions.
  Merge rule that made it safe: **agree ⇒ +1 confidence step (cap média); disagree ⇒ withhold +
  human review, never pick** — it turned a hallucinated CNH name into a blank instead of a wrong
  value. A group field travels with its anchor *only when the reads disagree on it too*: an
  issuer both reads agree on survives a divergent RG number.
- **🔴 Superseded 2026-10-13 — the AGREEMENT GATE (owner decision: "ship only with an agreement
  rule").** Winner-picking heuristics between disagreeing reads (compromised-loses, averbação-
  wins, wrong-shape-RG-loses, implausible-name-loses) were whack-a-mole: the same certidão gave
  two divorce averbações, estado_civil came out divorciado/casado/viúvo across runs. Critical
  fields (nome, cpf, rg+órgão, rne, data_nascimento, estado_civil, regime_bens, data_casamento,
  spouses' names, certidão matrícula) are now emitted ONLY when two valid reads agree; the re-read
  ALWAYS runs for OCR documents carrying them. Disagreement ⇒ NO value, both readings in
  `leituras_alternativas`/`divergencias`, aviso `divergencia_leituras`; social-wiring opens a
  pending `cliente_campo_conflitos` review with both. When the cliente column ALREADY holds a value
  (owner 2026-10-21): a reading equal to it opens nothing; a differing one opens a review
  (`valor_anterior` = on-file value; `protege_correcao` if it is an owner correction; a rejected
  reading is never re-raised) — never a silent drop. A CPF/matrícula whose DV verifies may stand
  alone; a transcription containing a CPF/32-digit matrícula with a failing DV is `ancora_falhou`
  (never counts, like a failed/compromised read — a third read is taken). Real-corpus gate = 0
  WRONG over 3 consecutive harness runs; a field left empty WITH a divergence aviso is REVIEW.
- **🔴 Superseded later 2026-10-13 — ROUTE, GATE, THEN CONCILIATE ONLY THE DOUBT (owner: "always
  debating every run is too expensive").** Always-two-reads is now MEASUREMENT mode only
  (`modo_medicao=True`). Production: ONE read with the routed primary
  (`documents/roteamento_modelos.py`, GENERATED by `roteamento_gerador` from de-identified
  benchmark/production counts — Anthropic only, Fable measured but never routed (30-day retention),
  a row moves only on ≥24 reads over ≥8 documents per model AND non-overlapping Wilson 95%
  intervals); a deterministic trust gate per field (`documents/confianca.py`: check digits,
  vocabularies, plausible dates, compromised/anchor, `resolucao_reduzida`, calibrated parser
  confidence, measured residual precision, cross-document corroboration); ONE fallback read only
  for a doubtful critical field, reconciled under the agreement rules (`releitura.conciliar`).
  A missing core field is NOT a trigger (12/12 RG reads would pay for a CPF most RGs never
  print). Offline replay over the 27-doc × 3-run benchmark (Sonnet 5 → Opus 5.5): production
  0 WRONG / 183 PASS / 15 REVIEW at US$0.034/doc (fallback on 15/81 reads) vs always-two-reads
  3 WRONG / 181 / 14 at US$0.102/doc. Every routed read is recorded per field
  (social-wiring `extracao_leitura_resultados`, fingerprints only) and settled by the human
  resolution; `noctus.dev.roteamento_modelos_recalibrar` regenerates the table (dry-run diff).
- **Escalation can't fix attribution.** Comprovante address scores didn't move because the reader
  never extracts the bill HOLDER, so the address can't be attached to the right party — a parser
  gap, not a model gap (see §4).
- **Calibrate every gate on the real corpus before shipping.** The legibility gate's first version
  flagged 17/28 genuine ID cards (compound CNH labels, "DOC IDENTIDADE / ÓRG EMISSOR / UF"); the
  second flagged 8/9 comprovantes (a bill legitimately carries CNPJ/ICMS) and 7/13 certidões
  (extenso dates, cartório footer CEP). Final: signals scoped by document kind → 3/49 flagged
  (both real hallucinations + one genuinely illegible CNH), 0 false alarms.
- **Don't derive what you can't verify.** The SP RG check digit (weights 2..9, 11−mod) matched only
  12/18 contract RGs → never complete a CNH-sourced RG automatically; flag it for a human.
- **Persist what the model read.** Prod keeps no identity transcription, so a prod miss cannot be
  diagnosed after the fact — store per-page transcriptions privately (LGPD retention).

## 3 · Layout catalog (what the parsers must know)

- **CNH (2022+, bilingual)** — "NOME E SOBRENOME / NAME AND SURNAME:": drop the English gloss
  before label matching. **"DOC IDENTIDADE / ÓRG EMISSOR / UF" prints the RG *without* its
  check digit** — a CNH alone cannot give the complete RG; the full RG (with DV) is on the RG
  card or the deal's "Info PP" sheet.
- **RG (SP)** — front: "Número registro", "Número documento"; verso: "REGISTRO GERAL: nn.nnn.nnn-d"
  (the real RG) under the "CARTEIRA DE IDENTIDADE" heading next to "LEI Nº 7.116".
- **Certidão de casamento, SP Registro Civil standard (scan, deal 857, 2026-10-21)** — the `NOMES:`
  label is REPEATED once per spouse (`NOMES: <spouse 1>` / `CPF: …` / `NOMES: <spouse 2>` /
  `CPF: …`); `name._candidatos` read only the lines BELOW a `NOMES` label, so the first spouse's
  same-line name was dropped, the second looked like the ONLY holder, and the titular received the
  other spouse's name (the two model reads then "diverged" on `nome` → `campos_nucleo_ausentes`).
  A same-line value is now a holder too — **as printed, never comma-cut** (`NOMES COMPLETOS DE
  SOLTEIRO, DATAS …` is a column header). Per-spouse qualification paragraph opens with the
  gentílico ("<Nome>, brasileiro, natural de …, nascido no dia <extenso> (dd/mm/aaaa), filho de
  …"): the word after the name IS the nationality (`conjuges._nacionalidade_da_qualificacao`,
  `media`), the numeric echo in parens is the birthdate (`media` inside the own "nascido(a)"
  clause). RGs come from "ANOTAÇÕES DE CADASTRO: Conjuge1: RG nn.nnn.nnn-d/SSP/SP. Conjuge2: …"
  — attributed by ordinal (Conjuge1 = first name), so `media` at most, recorded per spouse on the
  `extracao_conjuges` entry (`rg`, `rg_orgao`, and now `nome_mae`/`nome_pai`/`naturalidade`).
  **OWNER DECISION 2026-10-21 (supersedes the 2026-10-13 "a certidão is not a CPF/RG source"
  rule):** the certidão's CPF (NOMES/CPF line), RG and órgão (annotation) now FILL an EMPTY
  `clientes` field — machine-pending, `origem=certidao_casamento` — for the titular AND the other
  spouse, via the generic D1 path: a different on-file value opens the approve/reject review, a
  `manual`/`protege_correcao` value is untouched, nothing is overwritten. They are read PER
  SPOUSE only (`autoridade.SO_POR_CONJUGE`: a whole-document read would hand the first spouse's
  to both). Authority: `rg`/`rg_orgao` rank LAST in `PRECEDENCIA` (a real RG/CNH or the ficha
  outranks the certidão, the certidão never takes over); `cpf` stays unranked there on purpose
  — the measured-precision table already lets a CNH/CIN beat it with no human, and ranking it
  would turn that win into a review. The stale `rg × certidao_casamento = 0/4` precision cell
  (it measured the unattributed flat columns) was removed: the per-spouse RG is unmeasured.
  **Filiação and naturalidade** are fields now (`IdentityFields.nome_mae/nome_pai/naturalidade`,
  `filiacao.py`; migration 296 for `nome_pai`/`naturalidade`, `nome_mae` is 167's): each spouse's
  clause ("natural de Campinas, Estado de São Paulo, … filho de A e de B") is read by anchoring on
  the spouse's NAME (`conjuges._com_filiacao`, `media`); an RG/CIN/CNH `FILIAÇÃO` block is
  positional (pai, mãe) so `baixa`, explicit `PAI:`/`MÃE:` labels are `alta`; two different
  clauses in one document are two holders → nothing is attributed. The CNH prints no
  naturalidade. Neither is required by the contract (the generator prints neither).
  **The OTHER spouse is created when no cliente matches** (`_criar_conjuge_da_certidao`): match
  by CPF first (org-wide — a person already registered is LINKED, never duplicated), then
  name within the card; only a CPF that passes its check digits + a read name creates, through
  the same `compradores_service.adicionar(papel='conjuge')` as "Adicionar cônjuge", with the CPF
  deliberately NOT passed there (it would be stamped `manual`). It refuses (today's
  conflict/aviso behaviour) when the titular is already linked to someone else, the destination
  atendimento/side is ambiguous, a read is `leitura_comprometida`, or a placeholder party
  ("Comprador 2", no CPF) on the same side might BE the spouse.
  The certidão describes BOTH spouses: when the other spouse is already linked as cônjuge but was
  not attributed an entry, she still receives estado civil / regime / data do casamento
  (`identidade_extracao_service._aplicar_fatos_do_casal`: only when the certidão is what set the
  titular's estado civil; fill-empty-or-conflict, `origem=certidao_casamento`).
- **Certidão de casamento, CNJ standardized model** (most recent deals): "Primeiro Cônjuge: …" /
  "Segundo Cônjuge: …" blocks; each block's "Estado Civil" is the status **before** the wedding
  (the document's own verdict is *casado* unless an averbação says otherwise); "Nome que o
  [primeiro|segundo] cônjuge passou a utilizar" is the post-marriage legal name; a single
  "Número do CPF" near the "Nome atual dos cônjuges" header; the matrícula line is CPF-shaped.
- **Certidão de casamento, older layouts** — (a) "NOME: …/NOME: …" then "ELE: <name>, nascido…" /
  "ELA: …" with the qualification glued to the name by a comma; (b) "inteiro teor" holder list
  (name + clause per row under a "… DOS CÔNJUGES" header); (c) the pre-CNJ narrative: both names
  only once ("assento do matrimônio de X e Y"), then "O/A contratante nascido… profissão… estado
  civil solteiro" — the **only document in the corpus that carries PROFISSÃO**, and the names are
  deliberately NOT split on "e" (it is also a surname particle). OCR writes "contratente" too.
- **gov.br CIN (PDF from the app)** — text layer = app boilerplate + a date; the data is an embedded
  image → a text-layer read that lacks nome/CPF/RG must fall through to vision. The CIN number is
  the CPF (no separate RG).
- **Old-model CNH** — the name is a bare line with no label; "CPF" merged into the identity line.
- **Serasa Crednet** — "Participação Societária" rows can print `100.0 %` (dot decimal) and an
  unpunctuated 14-digit CNPJ; a share never has a thousands separator.
  The portal-print text layer's "Resumo da consulta" has no pipes and wrapped headers
  ("DATA"/"NASCIMENTO"); it is read by CELL order (2+ space split, or one cell per line),
  anchored on the CPF + date shapes. Rows are "Pendência Refin" (→ `pendencias_financeiras`) and
  "Protesto Estadual"; "Último Registro" is `MM/YYYY` (→ day 1).
- **Guia ITBI (Carapicuíba)** — no transaction-value box: price = "Valor do Instrumento (à vista)"
  + "Valor Financiado" (equals the base de cálculo).
- **Guia ITBI (Cotia, text layer)** — the price is "Valor do Instrumento (Valor Venal de
  Mercado)" (not Carapicuíba's cash part), and the text layer dumps the boxed row as a label
  COLUMN then a value COLUMN: the line after a label is another box's value (an area that parses
  as money). Pair money labels ↔ `R$` amounts, equal counts only
  (`caixa_rotulada.valor_em_coluna`); an unpairable dump reads `None`, never the next line.
- **Guia ITBI (Embu das Artes, text layer)** — facts in prose; the text layer wraps through the
  label ("… E VALOR DA" / "TRANSAÇÃO: R$ …") → a joined-pairs second pass
  (`caixa_rotulada.linhas_unidas`). Before both fixes, 0/6 text-layer guides read a value.
  People too: Cotia dumps "Nome:/Endereço:/CGC/CPF:" then the three values (the contribuinte is
  the comprador); Embu wraps "A - CPF: … E" / "B - CPF: …". Without them no guide's CPF reached
  the belongs-check (0/6 → 5/6 verified; the 6th names a CPF absent from the deal → refused).
- **Guia ITBI (vision)** — the comprador block comes in four shapes: "CONTRIBUINTE: A e B" with
  "CPF/CNPJ: x / y" on the NEXT line; "ADQUIRENTE: A - CPF/CNPJ: [EM BRANCO]" (name only); a
  "Contribuinte(Comprador)" heading then "Nome:"/"CGC/CPF:" lines; a headless "Nome: A - CPF: x"
  above the transmitente. Names pair with CPFs only on equal counts
  (`caixa_rotulada.parear_nomes_cpfs`); the contribuinte is sometimes the OWNER (Embu), so it is
  belongs-check evidence, never a party record. A stamped scan defeats the cheap model (both CPFs
  misread): an untrustworthy vision read (CPF failing its check digit, or no valor) is re-read
  once with `ESCALATION_OCR_MODELS` and merged (`guia_itbi.deve_escalar`/`mesclar`: valid CPFs
  win, differing valores are withheld). "Valor da Transação Atualizado/Avaliado" is a different
  box — a label followed by more words before the colon never reads as the price.
  Belonging without a valid CPF = EVERY named comprador strictly (`chave_nome`) on the deal.
- **Proposta de financiamento (Itaú "Carta de Crédito", 10/11 of the corpus)** — names the
  proponente only in a greeting ("Oi, <Nome>. Sua proposta foi aprovada") and prints NO CPF;
  another bank prints "Nome do(s) Comprador(es):" and "CPF(s):" on separate lines. Belonging is
  then a STRICT `chave_nome` match to a deal comprador — vision misreads 1–2 letters of a name in
  ~3/8 letters, and those stay unverified (a human decides), never fuzzily accepted.

## 4 · Where signed contracts diverge from the documents

- **RG**: the contract prints the full RG with DV; the CNH doesn't carry the DV. One party's
  contract RG matched no document in the folder at all.
- **Names after marriage**: the contract used the spouse's **maiden** name (= her RG), not the
  certidão's post-marriage name → which one is the contract name is an **owner rule** (open).
- **Certidões**: the contract can cite a different emission (número/date) than the file in the
  folder (P1/883 RF). Score against the document; flag the divergence.

- **Proof of address — whose bill it is decides.** Corrected measurement (holder name searched in
  the transcription, 9 bills vs contracts): 7/9 are in a party's own name and the contract used that
  address for the party AND the spouse; 1/9 is a non-party's bill and its contract did NOT use it;
  1/9 own bill, contract used another address. An earlier "mostly relatives' bills" claim came from
  a failed attribution in the test harness, not from the documents. Rule: holder is a party →
  apply to holder + spouse; anyone else → human review.
- **Chained deals share people.** One deal's sellers are another's buyers (identical files by
  hash): expect the same person on several cards; attribute by extracted name/CPF, never by
  folder position or "the lead" default.

## 4a · Resolving divergences between documents without a human (2026-09-29)

Resolver: `products/social-wiring/backend/app/services/divergencia_resolucao.py` (pure policy) +
`identidade_extracao_service.backfill_resolver_conflitos_pendentes` (run on every read of the
conflict queue). Order: validators → **live evidence** → corroboration → measured source tier →
human. Every automatic decision lands as `resolvido_automatico` with its rule in `motivo_resolucao`.

- **A conflict row is a snapshot; the documents are the truth.** Most "hard" conflicts in the prod
  queue were stale: the document behind one side had been deleted or re-read to something else. Ask
  what the value's OWN document says now before comparing sources at all (rule `retratado`).
- **Positive evidence only.** "No live document of that type" is NOT retraction — values are also
  typed, derived (nacionalidade from an RG issuer), legacy, or point into another table. Retract only
  when the specific document is soft-deleted, now reads a different value, or is a two-person
  document with nothing attributed to this person. Human-typed/confirmed values are never retracted.
- **Two-person documents assert per-person facts only through attribution.** A certidão de casamento's
  flat RG/DN/gênero/name/CPF columns name nobody in particular; only the `extracao_conjuges` entry
  whose `cliente_id` (or CPF) is this person counts. Couple-level facts (estado civil, regime, data do
  casamento) read the flat columns. Measured: every certidão conflict in the queue came from reads
  that predated attribution.
- **Corroboration must count documents, not conflict history.** A value applied without a conflict
  was never "proposed", so a history-only count misses the agreeing document.
- **Check "same value" before any gate that opens a conflict.** A bill in someone else's name that
  states the address already on file asks nothing.
- **Answer keys don't cover every field.** Signed contracts carry no birth date, so its source
  precision can't be measured from them; fields outside the contract should not block on a human.
- Result on prod: 22 pending → 12 resolved (pass 1) → 9 of the remaining 10 (pass 2, dry-run); the
  two decisions checkable against a signed contract both picked the contract's value.

### 4a-i · R1-R5: every remaining live-queue case has a rule (2026-09-30)

5 historical deals re-run on prod surfaced 5 more shapes, all resolvable without a human — owner
directive: "Human reviews are meant to be the exception, not the rule."

- **R1 — re-resolution on new evidence.** A conflict is a SNAPSHOT of what was known at open time; a
  name/CPF/address that lands on ANY party AFTER can be exactly the missing evidence. `identidade_
  extracao_service.revalidar_negociacao` runs `backfill_resolver_conflitos_pendentes` over the
  extracted cliente AND every other party of the same `atendimento`(s) at the end of every extraction
  — not only on `GET /conflitos` resolve-on-read, which only fires when a human happens to open the
  queue.
- **R2 — an empty on-file address is not "can't judge."** `_decidir_endereco_pendente` used to read
  `valor_anterior=None` (the shape `aplicar_endereco_ao_cliente` writes when the conflict opened
  against an EMPTY address) as "not a JSON object" and parked the row in `ignorado_composto` forever
  — even once the missing holder evidence later landed. Fixed: only `valor_proposto`'s shape gates
  the judgement. The holder-tier check (`_titular_e_parte_ou_conjuge`) now also recognises another
  ATENDIMENTO PARTY as a verified holder, not only self/spouse; a definitely-unrelated holder
  auto-rejects (never pending) when the cliente already holds an address from their own document.
- **R3 — household address propagation.** A spouse with no comprovante of their own inherits the
  other's OWN-document address (`identidade_extracao_service.propagar_endereco_domicilio`), tagged
  `endereco_origem="conjuge_domicilio"` — a tier below any real document (never a propagation SOURCE
  itself), never overwrites, and un-fills the moment the source no longer qualifies.
- **R4 — cross-party identity values are misfiling, not a fact.** A proposed `nome_oficial`/`cpf`/`rg`
  that equals another PARTY's (or their attributed spouse's) own value is auto-rejected
  (`divergencia_resolucao.decisao_outra_pessoa`, rule `outra_pessoa`) — never filled, never left
  pending. The source document gets `extracao_aviso="documento_de_outra_parte"` so the UI can suggest
  moving it. `endereco` is deliberately out of scope — a shared household address is not misfiling.
- **R5 — two-person documents withhold EVERY per-person field, not just one.** The CPF-only
  withholding (950c2c255) generalises to all of `CAMPOS_POR_PESSOA` (rg, rg_orgao_expedidor, genero,
  data_nascimento, nome_oficial, profissao) — a divorce certidão's flat reading had carried an
  ex-spouse's RG onto the wrong card the same way an earlier pass carried a CPF.

## 5 · Sources for data no identity document carries (automation ideas)

- **"Info PP"** (per-deal Google Doc, "pesquisa prévia"): sellers' nome/CPF/**RG with DV**/DN +
  empresas/CNPJ — the missing RG check digit and the empresa list.
- **"Comprovante Sinal"** receipts: sinal value, date, paying/receiving account → parcela 1.
- **Bank forms** (e.g. Itaú "FORMULÁRIO COMPRADOR/VENDEDOR"): profissão, estado civil, address,
  income — but they are *not* identity documents: never run them through the identity reader
  (a bank form read as an ID produced a wrong name at `alta`).

## 6 · Product/UI lessons from the same run

- A card = Funil → "Novo lead" (spawns the atendimento); Contatos → "Novo contato" does not.
- Anexos silently drops a file picked before a tipo is selected; "Adicionar vendedor" ignores a
  click before the button enables — both need feedback.
- A finished read must be re-runnable from the UI (delete + re-upload destroys LGPD access history).
- Imóvel "Remover" uses a native `window.confirm()` — it freezes the renderer for browser
  automation (no CDP input until a human clicks) and can't be pre-accepted from page script. A
  misfiled doc also needs a *reclassify* action, not only delete; the upload tipo select resets
  after a failed upload, which is how an IPTU guia got filed as a matrícula.

## Deal 857 live run (2026-10-21) — three matrícula/profissão findings

- **A typed value is never blocked by a machine-misread guard.** The profissão vocabulary guard (`contrato_gerador/profissoes.py`) exists for machine reads ("aposentanda"); when `clientes.profissao_origem == 'manual'` the generator only warns (`PROFISSAO_DIGITADA_FORA_DO_VOCABULARIO`) and prints it as typed.
- **ARISP "Visualização de matrícula" headings wrap onto two lines** ("REGISTRO DE IMÓVEIS, TÍTULOS E DOCUMENTOS" / "E CIVIL DE PESSOAS JURÍDICAS DE <CIDADE>"): `find_cartorio` accepts a continuation line opening `E CIVIL|E DOCUMENTOS|…`, so the city is kept.
- **In an ônus act (hipoteca / alienação fiduciária) the bank is the credor, never an adquirente** (`matricula_ato_detalhes._credor_nao_adquirente`); names carrying prose words ("pela", "responsabilidade") are not parties.

## Deal 857 live run (2026-10-21) — CENPROT date, registry address, budget storage

- **A clipped clock digit is derived from evidence, never guessed.** The PJ/negativa CENPROT capture sits ~2px closer to the screenshot's right edge, so the clock's last year digit ("202?") is cut; the strict "never complete a `?`" rule dropped `emitida_em`. `cenprot._candidatas_data` now accepts ONLY `dd/mm/aaa?` (a `?` anywhere else stays unreadable), expands it to the ten years, and keeps the one inside the consulta window (225 days wide → at most one survives); both crops must agree on the same date, no reference date → not recorded.
- **The registry address = abertura street + the number from a later construction AV.** `matricula_endereco` already took the number from an officialização AV; a building-numbering AV says "…um prédio … o qual recebeu o número 08 da Rua X" (`_RECEBEU_NUMERO`, number must follow "recebeu" directly; highest AV wins). The result is still the suggestion the operator confirms (`endereco_registro_texto`).
- **The LLM budget lives in `public.org_settings` (core migration 001), never in a product schema.** The guard read `db.table("org_settings")` through the product-pinned admin client, so social-wiring got PGRST205 on `social_wiring.org_settings` on every LLM call, swallowed into "no budget". It now reads `.schema("public")`; a missing table raises `LLMBudgetNotConfigured` (ERROR logged once per process); transient read errors stay fail-open.
