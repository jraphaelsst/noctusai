# ABNT formatting — contract (social-wiring transcripts + contracts)

> Authored once by the tech-lead (skill `noc-contract-first`); every slice builds TO this file and its tests assert against it. A slice that needs a change stops and surfaces it, never re-guesses.

## 0 · Owner requirements (2026-09-14, verbatim intent)

1. Matrículas: instead of a copy field, return a **PDF** containing the transcript. The **"Copiar"** button copies the text **with its formatting for Word** (no separate "copiar com formatação" button).
2. Contracts: **PDF**, no more `.docx` for the user. Same formatting rules.
3. Bold and underlined passages in the source documents MUST carry into the transcript and into the contract.
4. Everything **ABNT-formatted by construction, by default** — no formatting copied from the reference files.
5. Both **matrículas and certidões**.

## 1 · Shared value objects (SHIPPED in this commit)

`seed/lib/backend/noctusai_lib/integrations/documents/formatting.py`: `FormatRange(start, end, bold, underline)` (offsets `[start, end)` into the owning plain text), `ranges_to_json` / `ranges_from_json`, `Run(text, bold, underline)`, `ParagraphKind {TITLE, HEADING, BODY, QUOTE}`, `Paragraph(runs, kind)`, `FormattedDocument(paragraphs, title)`.

Persisted JSON (a `jsonb` array, sorted by `start`,`end`): `[{"start": 0, "end": 4, "bold": true, "underline": false}, …]`.

🔴 Invariant: the plain text is canonical and **unchanged** by this feature. Formatting is a second layer of offsets into it. Existing offsets (matrícula acts, migration 109) stay valid.

Import from submodules (`…documents.formatting`, `…documents.abnt`, `…documents.transcription`). Only slice **S2** edits `documents/__init__.py`.

## 2 · Slice S1 — seed transcriber captures formatting

File scope: `seed/lib/backend/noctusai_lib/integrations/documents/transcription.py` + its tests.

- `TranscribedPage.formatting: tuple[FormatRange, ...] = ()`: offsets into `page.text`.
- `Transcription.formatting` (property): document-level ranges re-based onto `Transcription.text` (pages joined by `"\n\n"`, blank pages dropped, exactly as `text` joins them).
- **Rung 1 (text layer)**: `page.text` stays byte-identical to today. Bold from PyMuPDF spans (`flags & 16` or bold-family font name), underline from `page.get_drawings()` horizontal strokes under a span. Spans are aligned onto the existing page text; an unalignable span is dropped (never shifts text).
- **Rung 2 (vision)**: the OCR prompt asks the model to mark bold as `**…**` and underline as `<u>…</u>` (combined allowed), still verbatim otherwise. A parser strips the markers → page text + ranges. Unbalanced or unknown markers are kept as literal text and logged; the parse never raises.
- Validation set: real platform documents in `…/scratchpad/formatting-samples.md` (tech-lead supplies the path in the brief), plus synthetic PDFs built in tests.

## 3 · Slice S2 — seed ABNT renderers

File scope: new `seed/lib/backend/noctusai_lib/integrations/documents/abnt.py` + tests, `documents/__init__.py` exports, `seed/lib/backend/pyproject.toml` (declare `reportlab`).

```python
def paragraphs_from_text(text: str, formatting: Sequence[FormatRange] = (), *,
                         kind: ParagraphKind = ParagraphKind.BODY) -> tuple[Paragraph, ...]
    # "\n\n" (one or more blank lines) splits paragraphs; a single "\n" stays a line break inside a Run.
def paragraphs_from_docx(docx: bytes, *,
                         classify: Callable[[str, str], ParagraphKind] | None = None) -> tuple[Paragraph, ...]
    # python-docx runs → Runs (bold/underline preserved); classify(style_name, text) → kind; default BODY; empty paragraphs dropped.
def render_abnt_pdf(doc: FormattedDocument) -> bytes
def render_word_html(doc: FormattedDocument) -> str
```

**ABNT rules (NBR 14724), fixed by construction and not configurable per call:**

| | |
|---|---|
| Page | A4; margins top 3 cm, left 3 cm, bottom 2 cm, right 2 cm |
| Font | Times (PDF core `Times-Roman`/`Times-Bold`, no embedding) 12 pt; Word HTML: `"Times New Roman", Times, serif` |
| BODY | justified, first-line indent 1.25 cm, line spacing 1.5, no extra space between paragraphs beyond one line |
| TITLE | centered, bold, 12 pt, followed by one blank line |
| HEADING | left, bold, no indent, line spacing 1.5 |
| QUOTE | left indent 4 cm, 10 pt, single spacing, justified |
| Page numbers | top right, 10 pt, from page 2 onward |
| Inline | `Run.bold` → bold, `Run.underline` → underline, both combinable; a `\n` inside a Run is a line break |

Output must be deterministic for the same input (fixed metadata / invariant mode). HTML is a self-contained fragment with inline styles only (Word ignores `<style>` blocks on paste), with all text HTML-escaped.

## 4 · Slice S3 — social-wiring backend: transcripts (matrículas + certidões)

File scope: `products/social-wiring/backend/migrations/113_transcricao_formatacao.sql`, `app/modules/matriculas/**` (NOT `estrutura_service.obter_selecao`, which belongs to S4), `app/modules/certidoes/**`, and their tests.

**Migration 113**
- `social_wiring.matricula_extracoes.formatacao jsonb NOT NULL DEFAULT '[]'`
- `social_wiring.certidao_resultados.texto_extraido text`
- `social_wiring.certidao_resultados.formatacao jsonb NOT NULL DEFAULT '[]'`
- `social_wiring.certidao_resultados.tem_transcricao boolean GENERATED ALWAYS AS (texto_extraido IS NOT NULL) STORED`

**Write paths**
- The matrícula pipeline (`service.processar_extracao`) persists `ranges_to_json(transcription.formatting)` with `texto_extraido`.
- The certidões pipeline transcribes every PDF it stores (API emissions after `_persist_pdf`, TJSP, manual upload) through the existing seed transcriber path (`_extract_pdf_text` seam, text layer), and persists `texto_extraido` + `formatacao`. A failed transcription leaves both null/[], is logged, and never fails the certidão.
- 🔴 List/detail endpoints that `select("*")` on `certidao_resultados` switch to an explicit column list that EXCLUDES `texto_extraido` and `formatacao` and INCLUDES `tem_transcricao`, so polling never ships document text.

**Endpoints** (auth `get_current_user_org`, org-scoped, strict `== 401` auth-boundary tests)

| Method + path | Success | Errors |
|---|---|---|
| `GET /api/matriculas/extracoes/{id}` (existing) | envelope unchanged, `data` gains `formatacao: FormatRange-json[]` and `texto_html: string \| null` (`render_word_html`; null when no text) | unchanged |
| `GET /api/matriculas/extracoes/{id}/pdf` (new) | `200 application/pdf`, `Content-Disposition: attachment; filename="<nome_arquivo sem extensão>_transcricao.pdf"`; ABNT PDF: TITLE `Transcrição da matrícula — <nome_arquivo>`, then `paragraphs_from_text(texto, formatacao)` | `404 {"detail": "Extração não encontrada"}` · `409 {"detail": "Transcrição ainda não concluída"}` when `status != 'concluida'` or no text |
| `GET /api/certidoes/resultados/{id}/transcricao` (new) | `success_response({"texto": str, "texto_html": str, "formatacao": [...]})` | `404 "Resultado não encontrado"` · `404 "Transcrição indisponível para esta certidão"` |
| `GET /api/certidoes/resultados/{id}/transcricao/pdf` (new) | `200 application/pdf`, attachment `"<tipo>_transcricao.pdf"`; TITLE `Transcrição — <nome_display>` | same 404s |

Side effects: every text read (JSON or PDF) is LGPD-logged exactly like today's text reads (`estrutura_svc.log_leitura_texto` for matrículas; `_log_resultado_acesso(..., intent="view")` for certidões), BEFORE the response. A failed log fails the request (existing contract).

Deprecation: FE `navigator.clipboard.writeText(texto_extraido)` on the Matrículas page is removed in S5.

Existing rows: `formatacao = []` until re-transcribed. The PDF still renders (unformatted). Named follow-up: `NOC-REMEDIATE[transcricao-formatacao-backfill]`.

## 5 · Slice S4 — social-wiring backend: contract PDF

File scope: `app/modules/card_hub/contrato_gerador/**`, `app/modules/matriculas/estrutura_service.py::obter_selecao` (formatting of the selected text only), `card_hub/contratos_service.py` version-mime handling if needed, and tests.

- `gerar` keeps the docxtpl template + two-pass numbering + lint exactly as today (the `.docx` stays an INTERNAL intermediate). It then builds `FormattedDocument(paragraphs_from_docx(docx, classify=…))` → `render_abnt_pdf` → stores the version with `content_type="application/pdf"` and a `.pdf` file name. The user never receives the `.docx`.
- ABNT by construction: `template_bytes()` drops Arial/11 and the `_NEGRITO` run bolding. Kinds come from the template's paragraph **style names** (e.g. `Title`, `Heading 1`, `Quote`) mapped in `classify`: the "INSTRUMENTO PARTICULAR…" line is TITLE, "CLÁUSULA…" and "TESTEMUNHAS:" are HEADING, matrícula literal quotations are QUOTE, everything else is BODY.
- Matrícula literal text quoted in the contract carries its bold/underline: `obter_selecao` returns the selection's `formatacao` re-based onto the selected text, and the context passes it as docxtpl `RichText` (template tag `{{r … }}`) so the runs survive into the `.docx` and from there into the PDF.
- `POST …/gerar` response unchanged: `201 {"versao": {...}, "avisos": [...]}`; `versao` now names a `.pdf` with mime `application/pdf`. The version URL endpoint is unchanged.

## 6 · Slice S5 — social-wiring frontend

File scope: `products/social-wiring/frontend/src/pages/Matriculas.tsx`, `pages/Certidoes.tsx`, `components/CertidoesPartePanel.tsx`, `components/GeradorContratoContainer.tsx` (+ contract-version labels in `components/card/ContratosPanel.tsx` if they say docx), `hooks/useMatriculas.ts`, `hooks/useCertidoes.ts`, their tests, and ONE shared helper in the seed lib frontend: `copyRichText(html: string, text: string): Promise<void>` (ClipboardItem with `text/html` + `text/plain`; falls back to `writeText(text)` only when `ClipboardItem` is unavailable, and says so via the returned/thrown result, never silently).

- **Matrículas** (concluída extraction): `[Baixar PDF]` (GET `/api/matriculas/extracoes/{id}/pdf` → blob → save with the server filename) and `[Copiar]` → `copyRichText(texto_html, texto_extraido)`. The old "Copiar Texto" is removed.
- **Certidões page + per-parte panel**: for a resultado with `tem_transcricao === true`: `[Transcrição PDF]` (GET `…/transcricao/pdf`) and `[Copiar]` (GET `…/transcricao` then `copyRichText`). Hidden when `tem_transcricao` is false.
- **Gerar contrato**: download/open label and handling for a PDF (no `.docx` wording anywhere).
- All four UI states per house rules; toasts on failure with the backend `detail`.
