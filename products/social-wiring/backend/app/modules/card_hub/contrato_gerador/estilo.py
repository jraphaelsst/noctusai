"""Contract typography — what goes bold / underlined / upper-case, measured
from the office's own signed contracts, expressed in the matrícula
extractor's formatting model.

ONE FORMATTING MODEL
--------------------
The matrícula transcriber already marks emphasis inline — `**bold**` and
`<u>underline</u>` — and `documents.transcription.parse_markup` turns that
into plain text + `FormatRange`s. The generator writes its OWN emphasis with
the very same two markers: the template (`modelo_texto`) and the phrases
(`frases`) put `**…**` / `<u>…</u>` around data and key terms, the seed
`docx_render` adapter renders the template as usual, and
`docx_render.apply_inline_markup` runs that same `parse_markup` over every run
of the rendered `.docx`, splitting it into real bold/underlined runs
(`documento.renderizar`). The matrícula quote itself arrives as rich runs
carrying the formatting captured at transcription (`contexto.
_descricao_matricula_rica`) and passes through untouched. No marker ever
reaches the document: an unbalanced one is left literal by `parse_markup`
and `lint` refuses it (`MARCACAO_NAO_CONVERTIDA`), and a data value that
already carries a marker is refused where it would be wrapped (`negrito`).

Italic is NOT part of the model, and the corpus says it does not need to
be: italic is 0% in every category measured below (the only italic stretches
are 2 of 10 Latin phrases, in 2 of 20 contracts). Small caps and the Word
"all caps" run property are 0% everywhere too — capitals are real capitals
in the text, so upper-casing is done on the STRING (`nome_parte`), never with
a run property.

MEASURED SPEC (2026-09-30)
--------------------------
20 final office contracts (.docx, de-duplicated by SHA-256), parsed locally
with python-docx; only aggregate formatting statistics were extracted — no
text. A match counts as bold/underlined when >= 80% of its non-space
characters carry the property (run → character style → paragraph style
resolved). "docs" = contracts where the majority of matches are bold.

Bold — the convention (followed here):
- clause heading: 284/284 paragraphs fully bold + upper-case, justified; the
  "CLÁUSULA <ORDINAL>" label ALSO underlined (99%), the topic after the dash
  not underlined (0%) — 20/20 docs.
- title: 20/20 centred, fully bold, upper-case.
- "Parágrafo <Ordinal>:" label, colon included: 227/227 bold, not upper.
- "Parcela NN:" label, colon included: 60/60 bold; "Sinal e princípio de
  pagamento": 21/21 bold.
- money "R$ x,xx (por extenso)" taken together: 81% bold (n=214), 20/20 docs;
  the extenso alone 80% (n=208).
- defined terms VENDEDOR(A/ES) 90% (n=374) / COMPRADOR(A/ES) 94% (n=337)
  bold, always upper-case, 20/20 docs; upper-case PARTE(S) 21/24 bold (the
  title-case "Partes" 0/44). The article before a term: 9/476 bold → never.
- the quoted term after "denominado neste ato simplesmente": 41/41 bold,
  quotes included.
- party names in a qualification: 68% bold + upper-case (n=92, 20/20 docs);
  company (PJ) names 16/16 bold + upper; an intermediário corretor's name
  6/7; the name after "em favor de" 69% bold / 84% upper (n=61).
- "IMÓVEL:" label: 19/19 bold + upper; the quoted matrícula text keeps its
  own captured emphasis (9% of its characters bold, 1% underlined) — no
  italic, no quotes, no indent (19/19 justified, left indent 0).
- municipal inscription number: 87% bold (n=23); the matrícula number digits
  95% bold (n=21) — the "nº"/"Matrícula Nº" words around them 0%.
- certidões group header ("N - Em nome de NOME"): 66/66 whole line bold
  (name upper 86%); the imóvel group header 20/20 bold; the items 0/816.
- pendência letter "a-)": 82% bold (n=142); its text 0%.
- inciso numeral "I –": 4/6 bold (only 2 contracts have incisos — thin, but
  the majority, followed).
- signature block: party labels 60/60, names 99/99, document lines 36/36 and
  "TESTEMUNHAS:" 20/20 bold + upper; the signature rule line 0/7; the
  "cidade, data" line not bold and right-aligned (18/20).

Not bold — the convention (nothing added):
- CPF numbers 0% (n=113), the CPF label 2%; CNPJ 4% (n=72); RG number 21%
  (n=90) — the bold ones are all inside signature-block document lines,
  which are bold as a whole; the rest of a qualification 3% of characters.
- dates (extenso 0/47, numeric 0/799), prazos "N (extenso) dias" 0/42,
  percentages 9% (n=80), multa "2% (dois por cento)" 4/46, legal references
  (art./Lei/Código) 0/130, clause/parcela cross-references 0/63 · 0/80,
  cartório 0/20, comarca 0/29, cidade 0/20, signing platform 0/20, bank /
  agency / PIX 3/117, CRECI 0/14, a PJ's representative's name 0/27,
  "PENDENTES" 0/18, "irrevogável e irretratável" 2/40.

Where the corpus is inconsistent (the choice is the majority):
- party names 68% bold/upper — the rest are plain title-case; bold+upper
  chosen (every contract has it as its majority).
- money 81% bold — followed.
- e-mail addresses 7/14 bold, 6/14 underlined (Word hyperlink styling) —
  no convention, left plain.
- Latin ("pro rata die", "ad corpus") 2/10 bold, 2/10 italic — left plain.
- the quoted defined term uses curly quotes (“ ”) in 41/41; the template
  keeps its straight quotes (a wording/character change is out of this
  typography pass's scope) — only the emphasis is applied.

Page face (docx only; the PDF's layout is the ABNT KIND's, never these):
Arial 11 pt, black, justified body — 100% of runs Arial, 98–100% 11 pt, in
title, headings, body and the IMÓVEL quote alike.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.transcription import has_raw_markup, parse_markup

#: Page face of the generated `.docx` (see "Page face" above).
FONTE = "Arial"
TAMANHO_PT = 11

NEGRITO = "**"
SUBLINHADO_ABRE, SUBLINHADO_FECHA = "<u>", "</u>"


def _sem_marcacao_previa(texto: str) -> None:
    """A value about to be wrapped must not already carry a marker: nested
    `**` toggles the wrong way, and a marker inside DATA (a name, a typed
    free-text field) is exactly the leak `parse_markup` exists to stop —
    refused loudly here rather than rendered as a surprise."""
    if has_raw_markup(texto):
        raise ValueError(
            f"estilo: o valor já contém marcação de formatação (**, <u>) — {texto[:40]!r}"
        )


def negrito(texto: str) -> str:
    """`texto` in bold (`**texto**`). Empty stays empty — never `****`."""
    if not texto:
        return texto
    _sem_marcacao_previa(texto)
    return f"{NEGRITO}{texto}{NEGRITO}"


def sublinhado(texto: str) -> str:
    """`texto` underlined (`<u>texto</u>`). Empty stays empty."""
    if not texto:
        return texto
    _sem_marcacao_previa(texto)
    return f"{SUBLINHADO_ABRE}{texto}{SUBLINHADO_FECHA}"


def nome_parte(nome: str) -> str:
    """A party's (or company's, or favorecido's) name: upper-case + bold."""
    return negrito((nome or "").strip().upper())


def texto_plano(texto: str) -> str:
    """The text a reader sees — markers stripped by the SAME `parse_markup`
    the render uses."""
    return parse_markup(texto)[0]


__all__ = [
    "FONTE",
    "TAMANHO_PT",
    "negrito",
    "nome_parte",
    "sublinhado",
    "texto_plano",
]
