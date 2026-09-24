"""Cartão CNPJ (Receita's "COMPROVANTE DE INSCRIÇÃO E DE SITUAÇÃO CADASTRAL",
printed to PDF) → typed fields.

Protocol + Fake + Real + factory, sibling of `serasa_crednet.py` and
`matricula_extractor.py` — same ladder (`ladder.py`), same confidence
vocabulary, same "not a text layer ⇒ not alta" tempering.

🔴 A BOXED FORM, NOT A TABLE — A DIFFERENT PROMPT FROM `serasa_crednet`
-------------------------------------------------------------------------
The Receita comprovante prints one value per LABELLED BOX
("NÚMERO DE INSCRIÇÃO", "DATA DE ABERTURA", ...), never a table row. So this
module's transcription prompt asks for `RÓTULO: valor`, one box per line —
the shape `serasa_crednet.DOCUMENT_PROMPT_CREDNET`'s pipe-table convention
would actively lose (a box has no columns to align). `real.py`'s own
identity-document prompt states the same "preserve THIS document's own
labels, verbatim" principle for a third, different layout.

🔴 A MASKED BOX IS `None`, NEVER THE LITERAL ASTERISKS
----------------------------------------------------------
The Receita masks some boxes (commonly "TÍTULO DO ESTABELECIMENTO" and
"SITUAÇÃO ESPECIAL") as a literal `********`. That string is not a value —
it is the document telling the reader nothing was printed there — so every
field parser here folds it to `None`, same treatment as an entirely blank
box, while the box's own label still lands in `rotulos` so a human can see
the field WAS present and masked, not silently missing from the layout.

🔴 `situacao_cadastral` IS A CLOSED VOCABULARY, THE RAW TEXT SURVIVES IN
`rotulos` WHEN IT DOESN'T MATCH
-------------------------------------------------------------------------
Migration `167_empresas_crednet_cartao_cnpj.sql` (§A.1) CHECKs
`empresas.situacao_cadastral` against exactly `'ativa' | 'baixada' |
'inapta' | 'suspensa' | 'nula'`. A read that doesn't normalise to one of
those five is `None` (never guessed, never written), but the box's raw text
is kept at `rotulos["situacao_cadastral"]` — the one field in this module
where `rotulos` carries the VALUE rather than the label, because "what did
the document actually say" is exactly what a human needs to resolve an
unrecognised situação.

🔴 THE ADDRESS BLOCK IS OFTEN MASKED IN FULL, AND EACH BOX IS READ ON ITS
OWN — NEVER SCRAPED OUT OF A NEIGHBOUR'S VALUE
---------------------------------------------------------------------------
`logradouro`/`numero`/`complemento`/`cep`/`bairro`/`municipio`/`uf` are each
their OWN labelled box, exactly like every other field here — `_campo`'s
usual same-line/next-line matching applies unchanged, cut off at the NEXT
known label so `municipio`'s value never bleeds into `uf`'s (or vice
versa). `uf` additionally validates against the 27-state whitelist
(`_UFS_BR`) — never a guess. `endereco_mascarado` is `True` when ANY of
these seven boxes was found printing the literal `********` — measured
against a real Cartão CNPJ (2026-09-24): the WHOLE address block is
routinely masked together, and a consumer needs one flag to know the
address section is unusable rather than reading seven independent `None`s
and guessing why. 🔴 An earlier version of this module tried to recover
`uf` by scanning a whole merged "city + code" value row for a trailing
UF-shaped token — that measurement's premise was wrong (the real file's
`uf=None` was masking, not a merged row) and the heuristic could, on a
document shaped differently, have picked up text belonging to a
neighbouring box. Removed; every field here is read from its own box only.

🔴 A REAL TEXT LAYER EXISTS TOO, AND IT HAS ITS OWN SHAPE — `pdftotext
-layout`'S COLUMN ALIGNMENT
-------------------------------------------------------------------------
Some Cartões are Chrome-printed PDFs (`Producer: Skia/PDF`) that carry a
genuine text layer, so rung 1 (`ladder.DocumentTextLadder`, PDF-text-first)
answers directly — no vision call, and `alta` is reachable (measured
2026-09-24). That extraction preserves visual COLUMN alignment via runs of
whitespace rather than the vision prompt's `RÓTULO: valor` convention: a
row of several short address labels prints as one line
(`"CEP  BAIRRO/DISTRITO  MUNICIPIO  UF"`), and the corresponding values as
the line right below, column-for-column (masked or not). `normalize_lines`
collapses that alignment (it exists to make LABEL matching accent/case
-insensitive, not to preserve column gaps), so this shape is read by a
SEPARATE pre-pass (`_valores_colunas_alinhadas`) over the text layer's own
raw lines, splitting on runs of 2+ spaces (a real multi-word value like
"SAO PAULO" carries only ONE space and so never splits) — tried FIRST,
falling back to the per-box `_campo` matcher above for anything it does
not resolve.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, Mapping, Optional, Protocol, Sequence, runtime_checkable

from noctusai_lib.integrations.documents.cnpj import format_cnpj, is_valid as _cnpj_is_valid
from noctusai_lib.integrations.documents.ladder import DocumentTextLadder
from noctusai_lib.integrations.documents.text import normalize_lines, strip_accents_upper
from noctusai_lib.integrations.documents.types import (
    ExtractionConfidence,
    TextSource,
)

# ─── transcription prompt (rung 2) ────────────────────────────────────────

#: `RÓTULO: valor`, one box per line — see the module header. Masked boxes
#: are transcribed AS PRINTED (the literal asterisk run); the parser, not
#: the prompt, decides that means "no value".
DOCUMENT_PROMPT_CARTAO_CNPJ = (
    "Transcreva o texto EXATO deste Comprovante de Inscrição e de Situação "
    "Cadastral (Cartão CNPJ), sem corrigir, resumir ou traduzir o CONTEÚDO "
    "de nenhum campo. O documento imprime cada campo como uma CAIXA — o "
    "rótulo (como 'NÚMERO DE INSCRIÇÃO', 'DATA DE ABERTURA', 'NOME "
    "EMPRESARIAL', 'SITUAÇÃO CADASTRAL', etc.) e, logo abaixo ou ao lado, o "
    "valor, MESMO QUE O DOCUMENTO NÃO IMPRIMA DOIS PONTOS ENTRE ELES. Você "
    "DEVE, ao transcrever, juntar cada rótulo ao seu valor em UMA ÚNICA "
    "LINHA no formato RÓTULO: valor — o rótulo exatamente como impresso, "
    "seguido de dois pontos (mesmo que o documento não os imprima) e o "
    "valor impresso naquela caixa, sem misturar o valor de uma caixa com o "
    "rótulo da caixa seguinte. Uma linha por campo. Se o valor estiver "
    "mascarado com asteriscos (********), transcreva os asteriscos "
    "literalmente. Transcreva também a linha de rodapé 'Emitido no dia ...'."
)

# ─── shared confidence tempering ──────────────────────────────────────────


def _temper(confidence: ExtractionConfidence, source: TextSource) -> ExtractionConfidence:
    """`alta` is reachable only off a PDF's own text layer — own copy, not
    shared with the sibling extractors, per this family's own convention
    (see `serasa_crednet._temper`)."""
    if confidence is ExtractionConfidence.ALTA and source is not TextSource.TEXT_LAYER:
        return ExtractionConfidence.BAIXA
    return confidence


# ─── small parsing helpers, local to this layout ──────────────────────────

_MASCARADO = "********"

#: Migration 167 §A.1's closed vocabulary. Keys are how the Receita prints
#: it (already accent-stripped/upper via `normalize_lines`); values are the
#: normalised snake_case the CHECK constraint accepts.
_SITUACAO_VOCAB: dict[str, str] = {
    "ATIVA": "ativa",
    "BAIXADA": "baixada",
    "INAPTA": "inapta",
    "SUSPENSA": "suspensa",
    "NULA": "nula",
}

#: The 27 Brazilian UF codes — the closed set `uf` is validated against.
#: Never a guess: a token that isn't in this set is not a UF, however
#: plausible-looking.
_UFS_BR: frozenset[str] = frozenset(
    {
        "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
        "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
        "RR", "SC", "SP", "SE", "TO",
    }
)


def _uf_valida(txt: Optional[str]) -> Optional[str]:
    """`uf`'s OWN box value, validated against `_UFS_BR` — never a guess,
    and never scraped out of a different box's text (see the module
    header). Tolerates stray punctuation/whitespace around the code
    (`"SP."`, `" SP "`, `"sp"`) but does not scan across multiple words —
    a value that isn't cleanly one of the 27 codes once trimmed is simply
    not a UF read, and reads as `None`, not a best-effort pick."""
    if not txt:
        return None
    candidato = re.sub(r"[^A-Z]", "", txt.strip().upper())
    return candidato if candidato in _UFS_BR else None


# ─── the `pdftotext -layout` column-aligned shape (real text layer) ───────


def _linhas_cruas(text: str) -> list[str]:
    """Raw lines, line-ending-normalised only — UNLIKE `normalize_lines`,
    internal whitespace runs survive, because they are the only signal a
    `pdftotext -layout` column boundary leaves behind. See the module
    header."""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _colunas(linha_crua: str) -> list[str]:
    """One raw line's column segments — split on a run of 2+ spaces (the
    `-layout` column-gap convention), so a single-spaced multi-word value
    ("SAO PAULO") stays one segment."""
    return [c for c in re.split(r"\s{2,}", linha_crua.strip()) if c]


def _linha_de_rotulos_alinhados(
    linha_crua: str, todos_rotulos: Sequence[str]
) -> Optional[list[str]]:
    """This raw line's own column segments, IF EVERY ONE of them is a
    known label (accent/case-folded) — a column-HEADER row. `None` for
    anything else (prose, or a value row): a header row is never
    partially recognised, because a partial match means this line is
    something other than what it looks like."""
    segmentos = _colunas(linha_crua)
    if len(segmentos) < 2:
        return None
    normalizados = [strip_accents_upper(s).strip() for s in segmentos]
    if all(s in todos_rotulos for s in normalizados):
        return normalizados
    return None


def _valores_colunas_alinhadas(
    text: str, todos_rotulos: Sequence[str]
) -> dict[str, tuple[Optional[str], bool]]:
    """`{rótulo -> (valor, mascarado)}` for every column-aligned
    header+value row pair in `text`. The header row's OWN very next
    NON-BLANK raw line supplies the values, split the SAME way and zipped
    positionally; a value row whose column COUNT doesn't match its
    header's is a positional zip across a different count, so instead of
    guessing it every column of THAT header is recorded as `(None,
    False)` — "the label was found, its value was not readable" — so the
    per-box `_campo` fallback never independently re-derives a value from
    the very same garbled next line (it would otherwise treat the whole
    unsplit line as ONE field's value)."""
    linhas = _linhas_cruas(text)
    saida: dict[str, tuple[Optional[str], bool]] = {}
    for i, linha in enumerate(linhas):
        cabecalho = _linha_de_rotulos_alinhados(linha, todos_rotulos)
        if cabecalho is None:
            continue
        for prox in linhas[i + 1 :]:
            if not prox.strip():
                continue
            valores = _colunas(prox)
            if len(valores) == len(cabecalho):
                for rotulo, valor in zip(cabecalho, valores):
                    valor = valor.strip()
                    if valor == _MASCARADO:
                        saida[rotulo] = (None, True)
                    elif valor:
                        saida[rotulo] = (valor, False)
            else:
                for rotulo in cabecalho:
                    saida.setdefault(rotulo, (None, False))
            break
    return saida


def _data_br(txt: str) -> Optional[date]:
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", txt)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _embutido_em_rotulo_maior(
    linha: str, pos: int, rotulo: str, todos_rotulos: Sequence[str]
) -> bool:
    """Is this match of `rotulo` actually a SUBSTRING of a longer, different
    label — at ANY position, not just the tail ("SITUACAO CADASTRAL" inside
    "DATA DA SITUACAO CADASTRAL" / "MOTIVO DE SITUACAO CADASTRAL"; "NUMERO"
    (the address box) as the literal PREFIX of "NUMERO DE INSCRICAO")?
    Checked against every OTHER known label so a shorter label never steals
    a longer sibling's own value, regardless of where inside it sits."""
    for outro in todos_rotulos:
        if outro == rotulo or len(outro) <= len(rotulo) or rotulo not in outro:
            continue
        k = outro.find(rotulo)
        inicio = pos - k
        fim = inicio + len(outro)
        if inicio >= 0 and fim <= len(linha) and linha[inicio:fim] == outro:
            return True
    return False


def _campo(
    linhas: list[str], rotulo: str, *, todos_rotulos: Sequence[str] = ()
) -> tuple[Optional[str], Optional[str], bool]:
    """`(valor, rótulo, mascarado)` for the box labelled `rotulo`.
    `mascarado` is `True` only when the box's own value was the literal
    `********` (distinct from "blank"/"never found" — see `endereco_mascarado`).

    🔴 REAL RECEITA CARTÕES DO NOT ALWAYS PRINT THE COLON THIS MODULE'S
    PROMPT ASKS FOR. Measured against a real Cartão CNPJ (2026-09-24): the
    vision transcription sometimes runs `RÓTULO valor` on one line with no
    separator at all, and sometimes prints the label alone with the value on
    the box's OWN next transcribed line — the prompt's instruction competes
    with "transcribe verbatim" and a real model does not always resolve
    that tension the same way twice. So this parser tries, in order:
    same line (colon or not, trimmed at the NEXT known label so two
    concatenated boxes never bleed into each other), then the next
    non-blank line that is not itself another label's own box.
    """
    for i, linha in enumerate(linhas):
        idx = -1
        busca = 0
        while True:
            achado = linha.find(rotulo, busca)
            if achado < 0:
                break
            if not _embutido_em_rotulo_maior(linha, achado, rotulo, todos_rotulos):
                idx = achado
                break
            busca = achado + 1
        if idx < 0:
            continue

        resto = linha[idx + len(rotulo) :].lstrip(" :").rstrip()
        corte = len(resto)
        for outro in todos_rotulos:
            if outro == rotulo:
                continue
            p = resto.find(outro)
            if p >= 0:
                corte = min(corte, p)
        resto = resto[:corte].strip(" :")

        if resto == _MASCARADO:
            return (None, rotulo, True)
        if resto:
            return (resto, rotulo, False)

        # The label's own line carried nothing usable — Receita boxes that
        # print the value on the NEXT line. Stop at the next line that
        # looks like it starts a DIFFERENT box.
        for prox in linhas[i + 1 :]:
            if any(o != rotulo and prox.startswith(o) for o in todos_rotulos):
                break
            if prox == _MASCARADO:
                return (None, rotulo, True)
            if prox:
                return (prox, rotulo, False)
        return (None, rotulo, False)
    return (None, None, False)


_EMITIDO_RE = re.compile(
    r"EMITIDO\s+NO\s+DIA\s+(\d{2})/(\d{2})/(\d{4})\s+AS\s+(\d{2}):(\d{2}):(\d{2})"
)


# ─── public value object ───────────────────────────────────────────────────


@dataclass(frozen=True)
class CartaoCnpjFields:
    """What one Cartão CNPJ yielded.

    `confiancas`/`rotulos` are keyed by this dataclass's own field names —
    same per-field-dict shape `serasa_crednet.CrednetFields` uses, and for
    the same reason: this document's boxes already disambiguate each field,
    so a dict avoids fourteen near-duplicate `<campo>_confianca` attributes.
    """

    cnpj: Optional[str] = None
    cnpj_valido: bool = False
    matriz_filial: Optional[Literal["MATRIZ", "FILIAL"]] = None
    data_abertura: Optional[date] = None
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    porte: Optional[str] = None
    natureza_juridica: Optional[str] = None
    #: Normalised to migration 167 §A.1's closed vocabulary, or `None` when
    #: the printed text does not match one of the five values — see the
    #: module header. The raw text survives at `rotulos["situacao_cadastral"]`.
    situacao_cadastral: Optional[str] = None
    #: "DATA DA SITUAÇÃO CADASTRAL" (E2) — the Cartão CNPJ is the sole
    #: source of truth for this date; see the P0c contract's tech-lead
    #: decision H4 (a Crednet-sourced date is NEVER copied here).
    data_situacao_cadastral: Optional[date] = None
    motivo_situacao: Optional[str] = None
    #: The address block — each its own box (see the module header). `uf`
    #: is validated against the 27 Brazilian states; the other six are
    #: read verbatim, no closed vocabulary.
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    cep: Optional[str] = None
    bairro: Optional[str] = None
    municipio: Optional[str] = None
    uf: Optional[str] = None
    #: `True` when ANY of the seven address boxes above printed the literal
    #: `********` — the real document masks the WHOLE block together far
    #: more often than it masks a single field within it.
    endereco_mascarado: bool = False
    emitido_em: Optional[datetime] = None
    confiancas: Mapping[str, ExtractionConfidence] = field(default_factory=dict)
    rotulos: Mapping[str, Optional[str]] = field(default_factory=dict)
    source: TextSource = TextSource.NENHUMA
    aviso: Optional[str] = None
    error: Optional[str] = None
    error_message: Optional[str] = None


# ─── pure parser ────────────────────────────────────────────────────────

#: `campo name -> the box's printed label` (already accent-stripped/upper —
#: see `normalize_lines`).
_ROTULOS: dict[str, str] = {
    "cnpj": "NUMERO DE INSCRICAO",
    "data_abertura": "DATA DE ABERTURA",
    "razao_social": "NOME EMPRESARIAL",
    "nome_fantasia": "TITULO DO ESTABELECIMENTO (NOME DE FANTASIA)",
    "porte": "PORTE",
    "natureza_juridica": "CODIGO E DESCRICAO DA NATUREZA JURIDICA",
    "logradouro": "LOGRADOURO",
    "numero": "NUMERO",
    "complemento": "COMPLEMENTO",
    "cep": "CEP",
    "bairro": "BAIRRO/DISTRITO",
    "municipio": "MUNICIPIO",
    "uf": "UF",
    "situacao_cadastral": "SITUACAO CADASTRAL",
    "data_situacao_cadastral": "DATA DA SITUACAO CADASTRAL",
    "motivo_situacao": "MOTIVO DE SITUACAO CADASTRAL",
}

#: The seven address-block field names — see `endereco_mascarado`.
_ENDERECO_CAMPOS: tuple[str, ...] = (
    "logradouro", "numero", "complemento", "cep", "bairro", "municipio", "uf",
)


def parse_cartao_cnpj(text: str, source: TextSource) -> CartaoCnpjFields:
    """Text (already ladder-read) → `CartaoCnpjFields`. Pure, never raises."""
    linhas = normalize_lines(text or "")

    confiancas: dict[str, ExtractionConfidence] = {
        campo: ExtractionConfidence.NENHUMA
        for campo in (*_ROTULOS, "emitido_em", "matriz_filial")
    }
    rotulos: dict[str, Optional[str]] = {campo: None for campo in confiancas}

    todos_rotulos = tuple(_ROTULOS.values())
    # The text-layer's column-aligned shape, tried FIRST — see the module
    # header. Falls through to the per-box `_campo` matcher for whichever
    # fields it doesn't resolve (the normal vision-prompt shape, or a
    # text-layer field this document didn't print column-aligned).
    colunas = _valores_colunas_alinhadas(text or "", todos_rotulos)

    valores: dict[str, Optional[str]] = {}
    mascarados: dict[str, bool] = {}
    for campo, rotulo in _ROTULOS.items():
        if rotulo in colunas:
            valor, mascarado = colunas[rotulo]
            achado_rotulo: Optional[str] = rotulo
        else:
            valor, achado_rotulo, mascarado = _campo(linhas, rotulo, todos_rotulos=todos_rotulos)
        valores[campo] = valor
        rotulos[campo] = achado_rotulo
        mascarados[campo] = mascarado
        if valor is not None:
            confiancas[campo] = ExtractionConfidence.ALTA

    endereco_mascarado = any(mascarados.get(campo, False) for campo in _ENDERECO_CAMPOS)

    cnpj_valor: Optional[str] = None
    cnpj_valido = False
    matriz_filial: Optional[Literal["MATRIZ", "FILIAL"]] = None
    if valores["cnpj"]:
        m = re.search(r"[0-9A-Z./\-]{14,20}", valores["cnpj"])
        if m:
            cnpj_bruto = m.group()
            cnpj_valido = _cnpj_is_valid(cnpj_bruto)
            cnpj_valor = format_cnpj(cnpj_bruto) or cnpj_bruto
            confiancas["cnpj"] = (
                ExtractionConfidence.ALTA if cnpj_valido else ExtractionConfidence.BAIXA
            )
        if "MATRIZ" in valores["cnpj"]:
            matriz_filial = "MATRIZ"
        elif "FILIAL" in valores["cnpj"]:
            matriz_filial = "FILIAL"
        if matriz_filial is not None:
            # Read out of the SAME box as `cnpj` ("NÚMERO DE INSCRIÇÃO" —
            # the Receita prints MATRIZ/FILIAL right beside the number, not
            # in a box of its own), so it carries that box's own label and
            # confidence just like every other field does.
            confiancas["matriz_filial"] = ExtractionConfidence.ALTA
            rotulos["matriz_filial"] = rotulos["cnpj"]

    data_abertura = _data_br(valores["data_abertura"]) if valores["data_abertura"] else None
    if valores["data_abertura"] and data_abertura is None:
        confiancas["data_abertura"] = ExtractionConfidence.NENHUMA

    data_situacao_cadastral = (
        _data_br(valores["data_situacao_cadastral"])
        if valores["data_situacao_cadastral"]
        else None
    )
    if valores["data_situacao_cadastral"] and data_situacao_cadastral is None:
        confiancas["data_situacao_cadastral"] = ExtractionConfidence.NENHUMA

    situacao_cadastral: Optional[str] = None
    if valores["situacao_cadastral"]:
        bruto = valores["situacao_cadastral"].strip()
        # The closed vocabulary word may sit anywhere in the box's text
        # ("BAIXADA" alone, or "SITUACAO: BAIXADA" if the model re-echoed
        # the label) — matched as a whole word, never a substring of a
        # longer, unrelated word.
        achado = next(
            (v for k, v in _SITUACAO_VOCAB.items() if re.search(rf"\b{k}\b", bruto)),
            None,
        )
        if achado is not None:
            situacao_cadastral = achado
        else:
            # Doesn't match the closed vocabulary: field stays None, but the
            # RAW text is kept at rotulos so a human can see what was
            # actually printed — see the module header.
            confiancas["situacao_cadastral"] = ExtractionConfidence.NENHUMA
            rotulos["situacao_cadastral"] = bruto

    # 🔴 THE RECEITA MASKS THE ADDRESS BLOCK OF EVERY BAIXADA COMPANY
    # (verified 5/5 real Cartões, 2026-09-24). A transcription that reports
    # address VALUES here anyway is not a parser gap — it is the vision
    # model FABRICATING a plausible-looking address instead of reading the
    # mask (measured live: 6/7 fields "found" on a REALIZA Cartão whose
    # address boxes are ALL `********`). So this is a policy override, not
    # a best-effort read: every address field is forced `None` here
    # regardless of what the transcription said, the block is always
    # treated as masked, and — when the transcription DID carry values —
    # the fabrication stays VISIBLE via `aviso` rather than silently
    # discarded.
    endereco_descartado_por_baixada = False
    if situacao_cadastral == "baixada":
        if any(valores[campo] is not None for campo in _ENDERECO_CAMPOS):
            endereco_descartado_por_baixada = True
        for campo in _ENDERECO_CAMPOS:
            valores[campo] = None
            confiancas[campo] = ExtractionConfidence.NENHUMA
        endereco_mascarado = True

    uf = _uf_valida(valores["uf"])
    if valores["uf"] and uf is None:
        # The label was found but nothing in its value validated as one of
        # the 27 UFs — never guessed, so this reads as unreadable, not
        # `rotulos["uf"]` losing the label that WAS matched.
        confiancas["uf"] = ExtractionConfidence.NENHUMA

    emitido_em: Optional[datetime] = None
    m = _EMITIDO_RE.search("\n".join(linhas))
    if m:
        dia, mes, ano, hh, mm, ss = m.groups()
        try:
            emitido_em = datetime(int(ano), int(mes), int(dia), int(hh), int(mm), int(ss))
            confiancas["emitido_em"] = ExtractionConfidence.ALTA
            rotulos["emitido_em"] = "EMITIDO NO DIA"
        except ValueError:
            emitido_em = None

    avisos: list[str] = []
    if cnpj_valor is not None and not cnpj_valido:
        avisos.append("cnpj_digito_invalido")
    if endereco_descartado_por_baixada:
        avisos.append("endereco_descartado_baixada")
    aviso = ",".join(avisos) if avisos else None

    return CartaoCnpjFields(
        cnpj=cnpj_valor,
        cnpj_valido=cnpj_valido,
        matriz_filial=matriz_filial,
        data_abertura=data_abertura,
        razao_social=valores["razao_social"],
        nome_fantasia=valores["nome_fantasia"],
        porte=valores["porte"],
        natureza_juridica=valores["natureza_juridica"],
        situacao_cadastral=situacao_cadastral,
        data_situacao_cadastral=data_situacao_cadastral,
        motivo_situacao=valores["motivo_situacao"],
        logradouro=valores["logradouro"],
        numero=valores["numero"],
        complemento=valores["complemento"],
        cep=valores["cep"],
        bairro=valores["bairro"],
        municipio=valores["municipio"],
        uf=uf,
        endereco_mascarado=endereco_mascarado,
        emitido_em=emitido_em,
        confiancas={campo: _temper(c, source) for campo, c in confiancas.items()},
        rotulos=rotulos,
        source=source,
        aviso=aviso,
    )


# ─── Protocol + Fake + Real + factory ──────────────────────────────────────


@runtime_checkable
class CartaoCnpjExtractor(Protocol):
    """Bytes + mimetype → a Cartão CNPJ's typed fields.

    Implementations MUST NOT raise for an unreadable/corrupt document — they
    return `CartaoCnpjFields` with `error` set."""

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> CartaoCnpjFields:
        ...


class FakeCartaoCnpjExtractor:
    """Deterministic extractor — the dev/test default.

    Uses the same real, checksum-valid CNPJ `serasa_crednet.FakeCrednetExtractor`
    does (`11.222.333/0001-81`) — see that module's Fake docstring for why an
    arithmetically invalid identifier would be the wrong default."""

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> CartaoCnpjFields:
        if not content:
            return CartaoCnpjFields(error="empty_document", error_message="no bytes to read")
        campos = (
            "cnpj", "matriz_filial", "data_abertura", "razao_social",
            "nome_fantasia", "porte", "natureza_juridica", "situacao_cadastral",
            "data_situacao_cadastral", "motivo_situacao", "logradouro",
            "numero", "complemento", "cep", "bairro", "municipio", "uf",
            "emitido_em",
        )
        return CartaoCnpjFields(
            cnpj="11.222.333/0001-81",
            cnpj_valido=True,
            matriz_filial="MATRIZ",
            data_abertura=date(2010, 3, 15),
            razao_social="EMPRESA FAKE SINTETICA LTDA",
            nome_fantasia="FAKE SINTETICA",
            porte="DEMAIS",
            natureza_juridica="206-2 - SOCIEDADE EMPRESARIA LIMITADA",
            situacao_cadastral="ativa",
            data_situacao_cadastral=date(2010, 3, 15),
            motivo_situacao="MOTIVO FAKE SINTETICO",
            logradouro="RUA FAKE SINTETICA",
            numero="99",
            complemento="SALA FAKE",
            cep="99999-999",
            bairro="BAIRRO FAKE",
            municipio="SAO PAULO FAKE",
            uf="SP",
            endereco_mascarado=False,
            emitido_em=datetime(2026, 1, 1, 12, 0, 0),
            confiancas={campo: ExtractionConfidence.ALTA for campo in campos},
            # `matriz_filial` has no box of its own — it rides the "cnpj"
            # box's label, matching `parse_cartao_cnpj`'s own behaviour.
            rotulos={
                campo: (_ROTULOS.get("cnpj") if campo == "matriz_filial" else _ROTULOS.get(campo))
                for campo in campos
            },
            source=TextSource.TEXT_LAYER,
        )


class LadderCartaoCnpjExtractor:
    """Text-layer-first, vision-second Cartão CNPJ reader.

    Construct via `make_cartao_cnpj_extractor(real=True)`."""

    def __init__(
        self,
        *,
        org_id: Optional[str] = None,
        resolver=None,
        provider: Optional[str] = None,
    ) -> None:
        self._ladder = DocumentTextLadder(
            org_id=org_id,
            document_prompt=DOCUMENT_PROMPT_CARTAO_CNPJ,
            resolver=resolver,
            provider=provider,
        )

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> CartaoCnpjFields:
        if not content:
            return CartaoCnpjFields(error="empty_document", error_message="no bytes to read")

        text, source, err = await self._ladder.to_text(content, mimetype, filename)
        if err is not None:
            return CartaoCnpjFields(source=source, error=err[0], error_message=err[1])
        if not text.strip():
            return CartaoCnpjFields(source=source)

        return parse_cartao_cnpj(text, source)


def make_cartao_cnpj_extractor(
    *,
    real: bool = False,
    org_id: Optional[str] = None,
    provider: Optional[str] = None,
) -> CartaoCnpjExtractor:
    """Return a Cartão CNPJ extractor. Fake-by-default.

    A single page always affords the ladder's own default page count, so —
    unlike `make_crednet_extractor` — there is no `max_pages` override here.
    """
    if not real:
        return FakeCartaoCnpjExtractor()
    return LadderCartaoCnpjExtractor(org_id=org_id, provider=provider)


__all__ = [
    "CartaoCnpjExtractor",
    "CartaoCnpjFields",
    "DOCUMENT_PROMPT_CARTAO_CNPJ",
    "FakeCartaoCnpjExtractor",
    "LadderCartaoCnpjExtractor",
    "make_cartao_cnpj_extractor",
    "parse_cartao_cnpj",
]
