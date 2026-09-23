# social-wiring · certidões levantamento — extraction learnings

> Born 2026-09-23 from a real due-diligence sweep (customer identifiers deliberately left out — LGPD): 10 certidão bundles (2 vendedores + 8 empresas,
> 138 pages) read with SW's own mechanisms — the seed transcriber
> (`noctusai_lib.integrations.documents.make_document_transcriber`, text-layer rung, then the
> vision rung on the image-only pages) — and turned into the "5 · Levantamento de certidões" form.
> Both rules below were confirmed by the owner. Read this before touching `modules/certidoes`
> (`service.py` `_extract_pdf_text` / `_analyze_estrutura_with_ai`, `registry.py`), the certidão
> step of the contract validation gate (`project-history/roadmaps/sw-extraction-contract-gate-2026-09.md`
> D2), or anything that shows a certidão's number or status to a human.

## 1 · Numbers read by AI from a scan are UNVERIFIED until checked against the image

**What happened.** The vision rung transcribed 29 image-only pages. The statuses it produced were
all correct, but the **identifiers were not**:

| Field | Vision read | Actual (verified on a 200-dpi crop) |
|---|---|---|
| CENPROT protocolo (6 of 10 wrong; query IDs, not personal data) | `9153736671` · `9153786517` · `0153736325` · `0153786940` · `0153786501` · `0153789126` | `0153786671` · `0153786517` · `0153786325` · `0153786840` · `0153786591` · `0153787126` |
| Serasa Refin contract | 14 digits (last digit dropped) | 15 digits |
| CNPJ root in the same pages (4 misreads) | `AB.0CD…` / `AB.6CD…`, `…98x` read as `…96x`, `…60x` read as `…69x` | one digit different each time |

The errors are single-digit swaps (`0`↔`9`, `6`↔`3`, `8`↔`9`, `9`↔`0`) and dropped digits. They are
invisible to a reviewer who reads the transcription: the output is fluent, well-formed and wrong.
Text-layer numbers (TRF3, TRT2, CNDT, TJSP e-SAJ/e-Proc, SEFAZ, PGE, Receita when it has a text
layer) were all exact.

**The rule.**
- A number whose provenance is the vision rung (protocolo, nº da certidão, processo, contrato,
  CPF/CNPJ, valor) is **machine-pending** in the D2 sense. It is never shown or stored as
  confirmed until it is checked, and it is never used as a join key on its own.
- Cheap mechanical checks come first, before any human effort: CPF/CNPJ check digits; the
  document's own CPF/CNPJ vs. the one the certidão was requested for; CNJ process-number check
  digits (`NNNNNNN-DD.AAAA.J.TR.OOOO`); a sibling-sequence check (protocols issued in one session
  are near-consecutive — `01537865xx`, so an outlier like `9153736671` is suspect by construction).
- Anything that fails a check, or cannot be checked, goes to the human validation gate with the
  image crop beside the value. It is never silently "corrected" by a second LLM pass.
- Provenance must say **how** a value was read (`texto` vs `ia_visao`), not just from which
  document. A status can be trusted from vision more than an identifier can.

## 2 · "Constam" is broader than "the certidão says positiva"

The form has three statuses per cell: **Não constam**, **Constam**, **Pendente**. The owner
confirmed this mapping onto SW's `resultado` vocabulary (`registry.py`):

| Form status | SW `resultado` / situation |
|---|---|
| Não constam | `negativa` (and `negativa_com_homonimos`, flagged for review) |
| Constam | `positiva` · `positiva_com_efeito_de_negativa` · **`nao_emitida` when the issuer refuses because of the contribuinte's own situation** |
| Pendente | no certidão of that type in the file set yet (nothing requested / not uploaded) |

**The non-obvious part — a refusal to issue IS an apontamento.** Confirmed examples:
- Receita Federal: "CNPJ **Inapta** – omissão de declarações, emissão de certidão não permitida".
- Receita Federal: "informações … **insuficientes para emitir a certidão pela Internet**". The owner
  confirmed this reads as Constam (it usually means pendências), not as Pendente.
- SEFAZ-SP débitos não inscritos: "**Não foi possível emitir** a Certidão Negativa … Relatório de
  Pendências Fiscais".
- PGE-SP e-CRDA: "as informações do contribuinte … **não permitem a emissão** da certidão de
  regularidade".

None of these has a certidão number, so the number cell is `—`, never empty. Empty means Pendente.
A `nao_emitida` caused by the *system* (site down, captcha, timeout) is **Pendente**, not Constam.
The difference is in the text, so the refusal reason must be kept verbatim.

`positiva_com_efeito_de_negativa` (e.g. Receita: débitos com exigibilidade suspensa, art. 151 CTN) is
Constam with a note. It is legally usable, but the buyer's lawyer must see it.

## 3 · Smaller facts worth knowing

- **Bundles hide page order.** The text-layer rung drops image-only pages, so its page index ≠ the
  PDF page. Key every page by its original page number before classifying.
- **One certidão ≠ one page.** TRF3, TRT2-físico and Serasa span 2 pages. The continuation page
  holds the rest of the process list (Serasa p.2 had 2 more companies).
- **Serasa Crednet is the owner→company map.** "Participação Societária" lists every company, CNPJ
  and % for a CPF. The spouse's companies come from the spouse's own Crednet.
- **Cross-entity links matter.** The same TRT2 process appeared against vendedor 1 and two companies they
  own, and one protest (same cartório, same value) appeared against vendedor 1 and one company. A levantamento view should surface shared processes/protests.
- **macOS decomposes `Õ`** in filenames (`CERTIDÕES …`). NFC-normalize before slicing or matching.
- The form ships 6 EMP columns. Real cases exceed it (this one had 8), so the grid must grow.
