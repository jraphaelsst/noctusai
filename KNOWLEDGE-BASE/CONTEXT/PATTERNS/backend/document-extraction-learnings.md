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
- **Guia ITBI (Carapicuíba)** — no transaction-value box: price = "Valor do Instrumento (à vista)"
  + "Valor Financiado" (equals the base de cálculo).

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
