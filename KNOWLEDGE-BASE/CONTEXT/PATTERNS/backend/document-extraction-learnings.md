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
