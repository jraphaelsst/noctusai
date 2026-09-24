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
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, Mapping, Optional, Protocol, Sequence, runtime_checkable

from noctusai_lib.integrations.documents.cnpj import format_cnpj, is_valid as _cnpj_is_valid
from noctusai_lib.integrations.documents.ladder import DocumentTextLadder
from noctusai_lib.integrations.documents.text import normalize_lines
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
    """Is this match of `rotulo` actually the TAIL of a longer, different
    label ("SITUACAO CADASTRAL" inside "DATA DA SITUACAO CADASTRAL" /
    "MOTIVO DE SITUACAO CADASTRAL")? Checked against every OTHER known
    label so a shorter label never steals a longer sibling's own value."""
    for outro in todos_rotulos:
        if outro != rotulo and outro.endswith(rotulo) and len(outro) > len(rotulo):
            prefixo_extra = outro[: -len(rotulo)]
            inicio = pos - len(prefixo_extra)
            if inicio >= 0 and linha[inicio:pos] == prefixo_extra:
                return True
    return False


def _campo(
    linhas: list[str], rotulo: str, *, todos_rotulos: Sequence[str] = ()
) -> tuple[Optional[str], Optional[str]]:
    """`(valor, rótulo)` for the box labelled `rotulo`.

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
            return (None, rotulo)
        if resto:
            return (resto, rotulo)

        # The label's own line carried nothing usable — Receita boxes that
        # print the value on the NEXT line. Stop at the next line that
        # looks like it starts a DIFFERENT box.
        for prox in linhas[i + 1 :]:
            if any(o != rotulo and prox.startswith(o) for o in todos_rotulos):
                break
            if prox == _MASCARADO:
                return (None, rotulo)
            if prox:
                return (prox, rotulo)
        return (None, rotulo)
    return (None, None)


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
    uf: Optional[str] = None
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
    "uf": "UF",
    "situacao_cadastral": "SITUACAO CADASTRAL",
    "data_situacao_cadastral": "DATA DA SITUACAO CADASTRAL",
    "motivo_situacao": "MOTIVO DE SITUACAO CADASTRAL",
}


def parse_cartao_cnpj(text: str, source: TextSource) -> CartaoCnpjFields:
    """Text (already ladder-read) → `CartaoCnpjFields`. Pure, never raises."""
    linhas = normalize_lines(text or "")

    confiancas: dict[str, ExtractionConfidence] = {
        campo: ExtractionConfidence.NENHUMA for campo in (*_ROTULOS, "emitido_em")
    }
    rotulos: dict[str, Optional[str]] = {campo: None for campo in confiancas}

    todos_rotulos = tuple(_ROTULOS.values())
    valores: dict[str, Optional[str]] = {}
    for campo, rotulo in _ROTULOS.items():
        valor, achado_rotulo = _campo(linhas, rotulo, todos_rotulos=todos_rotulos)
        valores[campo] = valor
        rotulos[campo] = achado_rotulo
        if valor is not None:
            confiancas[campo] = ExtractionConfidence.ALTA

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

    uf = valores["uf"].strip().upper() if valores["uf"] else None
    if uf is not None and (len(uf) != 2 or not uf.isalpha()):
        uf = None
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

    aviso = "cnpj_digito_invalido" if (cnpj_valor is not None and not cnpj_valido) else None

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
        uf=uf,
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
            "data_situacao_cadastral", "motivo_situacao", "uf", "emitido_em",
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
            motivo_situacao=None,
            uf="SP",
            emitido_em=datetime(2026, 1, 1, 12, 0, 0),
            confiancas={campo: ExtractionConfidence.ALTA for campo in campos},
            rotulos={campo: _ROTULOS.get(campo) for campo in campos},
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
