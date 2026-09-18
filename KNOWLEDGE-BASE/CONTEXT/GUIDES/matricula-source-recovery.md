# GUIDE — recovering a matrícula's source PDF from its own validation code

> **When you need this.** A `social_wiring.matricula_extracoes` row exists, its
> `texto_extraido` is wrong or unusable (literal `**bold**` markers, a bad OCR
> pass, a truncated read), and the source PDF is gone — because the standalone
> `POST /extrair` path historically **discarded the upload**. The row cannot be
> repaired in place (write-once trigger, see §5) and cannot be re-transcribed
> without a source. This guide recovers the source.
>
> **Discovered 2026-09-17** while trying to make the Euroville matrícula usable
> for the first real generated contract. Written up because it worked, it is
> repeatable, and the alternative — asking the office to find a file they
> uploaded weeks ago — usually fails.

---

## 0 · The insight

A Brazilian registry certidão issued electronically **carries its own retrieval
address inside its text**. The transcription we already have preserves it, even
when the transcription is otherwise defective. So a lost source is often
recoverable *from the very row that lost it*.

Two identifiers matter, and they are not equivalent:

| Identifier | Looks like | Use |
|---|---|---|
| **ONR validation URL** | `https://assinador-web.onr.org.br/docs/XXXXX-XXXXX-XXXXX-XXXXX` | 🟢 **Direct download.** This is the one you want. |
| **CNM** (Código Nacional de Matrícula) | `148429.2.0003917-55` | 🟡 Identifies the matrícula, but does not by itself yield the file. |

A row may have one, both, or neither.

---

## 1 · Extract the identifiers

```sql
select e.id, e.nome_arquivo,
       (regexp_match(e.texto_extraido, 'CNM:?\s*([0-9.\-]+)'))[1]          as cnm,
       (regexp_match(e.texto_extraido, 'PROT\.?\s*([0-9.\-]+)'))[1]        as protocolo,
       (regexp_match(e.texto_extraido, '(?i)(https?://[^\s]+)'))[1]        as url_no_texto
from social_wiring.matricula_extracoes e
where e.texto_extraido is not null
order by e.created_at;
```

⚠️ The URL regex returns only the FIRST match. A row reporting `url_no_texto =
NULL` genuinely has no `http` in its text; a row with one may have more.

**Observed hit rate, 2026-09-17: 2 of 5.** Do not assume this always works —
plan for the miss (§6).

## 2 · Open the validation URL in a real browser

🔴 **A plain `curl` is not enough.** `assinador-web.onr.org.br` is an Angular
SPA: the URL returns HTTP 200 with ~74 KB of shell HTML containing no API paths
(only `main-*.js`), and the document is fetched by client-side JS. You need a
rendering browser.

🔴 **Do not enumerate the site's API endpoints** to shortcut this. Probing an
external host's paths is indistinguishable from scouting and is correctly
refused by the sandbox. Render the page instead.

Expected on success — the page shows **"Documento encontrado"** plus:
- cartório name + CNS
- the validation code you used
- the filename (e.g. `certidao-3917.pdf`)
- `CERTIDÃO VÁLIDA ATÉ` — the certidão's legal validity
- `DOWNLOAD DA CERTIDÃO DISPONÍVEL ATÉ` — ⚠️ **a different, later date**; this
  is the one that decides whether recovery is still possible
- signer + `RESULTADO DA VALIDAÇÃO: Todas as verificações passaram`

Click **Baixar**. The file lands in the browser's download directory.

## 3 · Verify before you trust it

Never upload a file you have not checked is the right document.

```python
import fitz
d = fitz.open(path)
print(d.page_count)            # must match the row's num_paginas
print(len(d[0].get_text()))    # see below
```

- **Page count must match** `matricula_extracoes.num_paginas`.
- **Little or no extractable text is EXPECTED and correct.** The Euroville
  recovery returned 3 pages / 138 chars on page 1 and none of the expected
  keywords, because the certidão is a **scanned image**. That is precisely why
  the original transcription went through the vision rung and emitted `**bold**`
  markers. A text-layer PDF here would be the surprising result.
- Cross-check provenance instead: the validation page's cartório + CNS + filename
  against the row's `texto_extraido` (cartório name, matrícula number, address).

## 4 · Re-upload

Upload at `/matriculas`. A fresh upload produces a NEW `matricula_extracoes` row
whose text is clean, because the current pipeline runs `parse_markup`
(`seed/lib/backend/noctusai_lib/integrations/documents/transcription.py`), which
strips `**`/`<u>` markers into `formatacao` ranges. The defective rows predate
that and store the markers raw — `transcription.py:603-609` documents exactly
this.

After it completes, confirm:

```sql
select id, jsonb_array_length(formatacao) as ranges,
       (texto_extraido like '%**%') as ainda_tem_markup,
       (select count(*) from social_wiring.matricula_atos a where a.extracao_id = e.id) as atos
from social_wiring.matricula_extracoes e order by created_at desc limit 1;
```

Pass = `ainda_tem_markup = false`, `ranges > 0`, and `atos > 0` for a matrícula
with registered acts. **`atos = 0` on a real matrícula means act segmentation
found nothing — investigate, do not proceed to a contract.** (Euroville's
original row had 0 acts, which is part of why it was unusable.)

## 5 · Why you cannot just fix the old row

`matricula_extracoes_protege_concluida` (migration 111) refuses ANY change to
`texto_extraido` once `status='concluida'`; the only sanctioned change is
purge-to-NULL for retention. That guard is correct — this text is quoted
**verbatim into a deed** — and must not be disabled to run a backfill. Recovery
is always: new row supersedes, old row retained.

## 6 · When there is no validation URL

Recovery by this route is impossible. Options, in order of preference:
1. The office's own copy (they uploaded it once).
2. A **fresh certidão** from the cartório — costs money, but produces a current
   document, which is often what the contract wants anyway (certidão freshness
   rules apply: see the contract policy for the < 30 / < 90 day windows).
3. The CNM identifies the matrícula for a manual request even without a URL.

## 7 · Preventing the need for this guide

The real fix is that no transcription should ever lose its source. Retain the
upload through `documento_store.DocumentoStore` (LGPD retention + access log
already wired), ideally by folding `/extrair` into the existing
`imovel_documentos` surface (`tipo_documento='matricula'`), which already stores
the file AND runs extraction. Re-running then means **supersede from the retained
source**, never "ask the office if they still have it."

## Composes with

- `KB § PATTERNS/security/lgpd.md §10` — registry documents are personal data;
  retention and access-log rules apply to the retained source too.
- `KB § PATTERNS/frontend/lying-loading-state.md` — the upload UI's states.
- `project-history/roadmaps/social-wiring-contract-automation-2026-09.md` — why a
  clean matrícula matters: the contract quotes act text verbatim by offset.
