"""Ficha cadastral bancária → `FichaCadastralLida`. Protocol + Fake + Real +
factory — sibling of `matricula_extractor.py`, sharing its ladder
(`ladder.py`) but with a DIFFERENT primary rung: these are AcroForm
fillable PDFs, so the widget FIELD NAMES/VALUES are read first (exact,
free, no vision call) — the plain PDF text layer is not even attempted,
because it prints labels and values in two disjoint blocks (see
`ficha_cadastral.py`'s own module docstring for the measured reason).
Vision is the fallback ONLY for a form with no usable widgets at all (a
flattened/scanned copy — measured on the P3 corpus: 2 of the FGTS forms
carry no text layer and no fillable fields either).
"""
from __future__ import annotations

import re
from typing import Optional, Protocol, runtime_checkable

from noctusai_lib.integrations.documents.ficha_cadastral import (
    ESTADO_CIVIL_OPCOES,
    REGIME_BENS_OPCOES,
    CampoWidget,
    FichaCadastralLida,
    PessoaFichaCadastral,
    classificar_campo,
    montar_pessoas,
)
from noctusai_lib.integrations.documents.ladder import DocumentTextLadder, looks_like_pdf
from noctusai_lib.integrations.documents.text import strip_accents_upper
from noctusai_lib.integrations.documents.types import ExtractionConfidence, TextSource


@runtime_checkable
class FichaCadastralExtractor(Protocol):
    """Bytes + mimetype → every person a ficha cadastral bancária names.

    Implementations MUST NOT raise for an unreadable/corrupt document — they
    return `FichaCadastralLida` with `error` set. An extractor that raises
    into a background job turns a bad upload into a lost job — same
    contract as `IdentityExtractor`/`MatriculaExtractor`.
    """

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> FichaCadastralLida:
        ...


#: The SAME real, checksum-valid fake CPF `fake.FakeIdentityExtractor` /
#: `serasa_crednet.FakeCrednetExtractor` use — a Fake returning an
#: arithmetically invalid CPF would let a consumer's tests pass against a
#: code path the Real adapter never exhibits on its happy path.
_CPF_FAKE = "412.954.238-98"


class FakeFichaCadastralExtractor:
    """Deterministic extractor — the dev/test default. One obviously-fake
    proponente, so a fixture that leaks into a real screen is recognisable
    as fake rather than plausible.

    Pass `result=` to script a specific outcome (several people, an
    unmatched CPF, an error) — same convention as `fake.FakeIdentityExtractor`
    / `serasa_crednet.FakeCrednetExtractor`."""

    def __init__(self, result: Optional[FichaCadastralLida] = None) -> None:
        self._result = result

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> FichaCadastralLida:
        if self._result is not None:
            return self._result
        if not content:
            return FichaCadastralLida(error="empty_document", error_message="no bytes to read")
        pessoas = (
            PessoaFichaCadastral(
                papel="proponente",
                nome="FULANO DE TAL FAKE",
                nome_confianca=ExtractionConfidence.ALTA,
                cpf=_CPF_FAKE,
                cpf_confianca=ExtractionConfidence.ALTA,
                profissao="profissao fake",
                profissao_confianca=ExtractionConfidence.ALTA,
                estado_civil="casado",
                estado_civil_confianca=ExtractionConfidence.BAIXA,
            ),
        )
        return FichaCadastralLida(pessoas=pessoas, source=TextSource.TEXT_LAYER)


def _widget_valor_util(field_type: str, valor: Optional[str]) -> str:
    if valor is None:
        return ""
    if field_type == "RadioButton" and valor == "Off":
        return ""
    return valor


#: How far right of a checkbox's own `rect` its printed label may sit — a
#: Brazilian form checkbox is drawn `(  ) Rótulo`, the label immediately
#: beside it, never below or above. Measured generous on the P3 corpus's
#: longest option ("Participação Final nos Aquestos").
_JANELA_ROTULO_PONTOS = 300


def _rotulo_geometrico(page, rect, opcoes: tuple[str, ...]) -> Optional[str]:
    """The printed option phrase sitting immediately beside this checkbox's
    own `rect` — see `ficha_cadastral.py`'s module-level note on why this
    replaces a position-based export-value decode. `None` when nothing in
    `opcoes` is found in that window (a layout this module has not seen)."""
    import fitz

    clip = fitz.Rect(rect.x0 - 5, rect.y0 - 3, rect.x0 + _JANELA_ROTULO_PONTOS, rect.y1 + 3)
    texto = page.get_text("text", clip=clip)
    norm = re.sub(r"[^A-Z ]", " ", strip_accents_upper(texto))
    for opcao in opcoes:
        if opcao in norm:
            return opcao
    return None


class LadderFichaCadastralExtractor:
    """Widget-first, ladder-second ficha cadastral reader.

    Construct via `make_ficha_cadastral_extractor(real=True)`.
    """

    def __init__(
        self,
        *,
        org_id: Optional[str] = None,
        document_prompt: Optional[str] = None,
        resolver=None,
        max_pages: Optional[int] = None,
        provider: Optional[str] = None,
    ) -> None:
        # `max_pages=None` (every page) by default, unlike the identity
        # family's `-1` sentinel: a ficha cadastral's people may sit on any
        # page (the FGTS form's own person block is on page 4 of 7 in the
        # P3 corpus) and there is no averbação-style "truncating loses
        # detail, never merely degrades" ceiling to protect against — a
        # caller narrowing this is an explicit choice, not this module's.
        self._ladder = DocumentTextLadder(
            org_id=org_id,
            document_prompt=document_prompt,
            resolver=resolver,
            max_pages=max_pages,
            provider=provider,
        )

    def _ler_widgets(self, content: bytes) -> Optional[dict[int, list[CampoWidget]]]:
        """Every classified widget, grouped by 0-based page index — or
        `None` when the bytes are not a PDF fitz can open, or carry no
        fillable fields at all (the caller falls through to the ladder)."""
        try:
            import fitz  # PyMuPDF — imported lazily, matching every other
            # real adapter here (a slim image must still import this
            # package's Fake/Protocol side with no PyMuPDF installed).
        except ImportError:  # pragma: no cover - exercised only in a slim image
            return None
        try:
            doc = fitz.open(stream=content, filetype="pdf")
        except Exception:
            return None
        try:
            por_pagina: dict[int, list[CampoWidget]] = {}
            total_valores = 0
            for i, page in enumerate(doc):
                widgets = list(page.widgets() or [])
                if not widgets:
                    continue
                classificados: list[CampoWidget] = []
                for w in widgets:
                    campo = classificar_campo(w.field_name or "")
                    if campo is None:
                        continue
                    valor = _widget_valor_util(w.field_type_string, w.field_value)
                    if not valor:
                        continue
                    if campo in ("estado_civil", "regime_bens"):
                        if w.field_type_string == "RadioButton":
                            # The export VALUE (`"1"`..`"6"`) is never
                            # decoded by position — see `ficha_cadastral.py`'s
                            # module-level note. Read the printed label
                            # beside THIS button's own rect instead.
                            opcoes = ESTADO_CIVIL_OPCOES if campo == "estado_civil" else REGIME_BENS_OPCOES
                            rotulo = _rotulo_geometrico(page, w.rect, opcoes)
                            if rotulo is None:
                                continue
                            campo_final = f"{campo}_geo"
                            valor = rotulo
                        elif campo == "estado_civil":
                            # A ComboBox/Text field prints the option's own
                            # word directly (FGTS) — no geometry needed.
                            campo_final = "estado_civil_texto"
                        else:
                            # `regime_bens` measured on the P3 corpus only
                            # as a RadioButton — an unexpected ComboBox/Text
                            # shape has no consumer to route to; skip rather
                            # than emit a key `_pessoa_de_campos` never reads.
                            continue
                    else:
                        campo_final = campo
                    classificados.append(
                        CampoWidget(campo=campo_final, valor=valor, tipo=w.field_type_string)
                    )
                    total_valores += 1
                if classificados:
                    por_pagina[i] = classificados
            if total_valores == 0:
                return None
            return por_pagina
        finally:
            doc.close()

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> FichaCadastralLida:
        if not content:
            return FichaCadastralLida(error="empty_document", error_message="no bytes to read")

        if looks_like_pdf(mimetype, filename):
            por_pagina = self._ler_widgets(content)
            if por_pagina is not None:
                pessoas = montar_pessoas(por_pagina)
                return FichaCadastralLida(pessoas=pessoas, source=TextSource.TEXT_LAYER)

        # No usable AcroForm data (a flattened copy, a scan, or not a PDF
        # at all) — fall through to the shared ladder: text layer first,
        # rasterize→vision second. A degraded read off narrative text is
        # covered only for a SINGLE person (see `parse_texto`'s own scope
        # note) — the FGTS form this rung exists for is single-person by
        # construction.
        from noctusai_lib.integrations.documents.ficha_cadastral_texto import parse_texto

        text, source, err = await self._ladder.to_text(content, mimetype, filename)
        if err is not None:
            return FichaCadastralLida(source=source, error=err[0], error_message=err[1])
        if not text.strip():
            return FichaCadastralLida(source=source)
        lida = parse_texto(text)
        return FichaCadastralLida(pessoas=lida.pessoas, source=source, aviso=lida.aviso)


def make_ficha_cadastral_extractor(
    *,
    real: bool = False,
    org_id: Optional[str] = None,
    document_prompt: Optional[str] = None,
    provider: Optional[str] = None,
    max_pages: Optional[int] = None,
) -> FichaCadastralExtractor:
    """Return a ficha cadastral extractor.

    Fake-by-default, the posture every seed IO module takes. `provider`:
    which vendor reads a scanned page (the vision fallback only) — any key
    of `documents.providers.OCR_MODELS`; `None` = the seed's canonical
    document provider, matching every sibling factory in this package.
    """
    if not real:
        return FakeFichaCadastralExtractor()
    return LadderFichaCadastralExtractor(
        org_id=org_id, document_prompt=document_prompt, provider=provider, max_pages=max_pages,
    )


__all__ = [
    "FakeFichaCadastralExtractor",
    "FichaCadastralExtractor",
    "LadderFichaCadastralExtractor",
    "make_ficha_cadastral_extractor",
]
