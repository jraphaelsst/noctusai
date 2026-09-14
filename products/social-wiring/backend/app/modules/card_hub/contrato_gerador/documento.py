"""Build the template .docx, render it through the seed `docx_render` adapter,
read the result back.

- The template is BUILT from `modelo_texto` with python-docx at runtime and
  cached — the wording stays reviewable text in git, no binary blob.
- Rendering is two passes over the same template: pass 1 only counts each
  clause's `par()` calls, pass 2 labels them ("Único" when a clause rendered
  exactly one). The totals are measured from the template itself, so there
  is no second, hand-kept paragraph declaration to drift from it.
- The product never imports docxtpl: `adapter` is the seed's
  `DocxRenderAdapter` (StrictUndefined — a missing key is an error).
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from docx import Document
from docx.shared import Pt

from noctusai_lib.integrations.docx_render import DocxRenderAdapter

from app.modules.card_hub.contrato_gerador.contexto import montar_contexto
from app.modules.card_hub.contrato_gerador.dados import DadosContrato
from app.modules.card_hub.contrato_gerador.modelo_texto import linhas_do_template
from app.modules.card_hub.contrato_gerador.numeracao import ContadorParagrafos
from app.modules.card_hub.contrato_gerador.politica import Politica

MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_NEGRITO = ("INSTRUMENTO PARTICULAR", "CLÁUSULA", "TESTEMUNHAS:")


@lru_cache(maxsize=1)
def template_bytes() -> bytes:
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(11)
    for linha in linhas_do_template():
        run = doc.add_paragraph().add_run(linha)
        if linha.startswith(_NEGRITO):
            run.bold = True
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@dataclass
class Renderizado:
    docx: bytes
    paragrafos: list[str]
    #: clause key -> how many times the template read `cl.<key>.ref`.
    referencias: dict[str, int]
    #: clause key -> its number, for the included clauses.
    clausulas: dict[str, int]


def paragrafos_do_docx(docx: bytes) -> list[str]:
    return [p.text for p in Document(io.BytesIO(docx)).paragraphs]


def document_xml(docx: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(docx)) as zf:
        return zf.read("word/document.xml").decode("utf-8")


def renderizar(
    adapter: DocxRenderAdapter,
    dados: DadosContrato,
    switches: dict[str, bool],
    politica: Politica,
    assinatura: date,
) -> Renderizado:
    tpl = template_bytes()
    contagem = ContadorParagrafos(None)
    adapter.render(tpl, montar_contexto(dados, switches, politica, assinatura, contagem))

    rotulos = ContadorParagrafos(contagem.chamadas)
    contexto = montar_contexto(dados, switches, politica, assinatura, rotulos)
    docx = adapter.render(tpl, contexto)
    if rotulos.chamadas != contagem.chamadas:
        raise RuntimeError(
            "par() chamado de forma diferente nas duas passagens — template não determinístico"
        )
    registro = contexto["cl"]
    return Renderizado(
        docx=docx,
        paragrafos=paragrafos_do_docx(docx),
        referencias=dict(registro.referencias),
        clausulas={chave: c.n for chave, c in registro.items()},
    )


__all__ = [
    "MIME_DOCX",
    "Renderizado",
    "document_xml",
    "paragrafos_do_docx",
    "renderizar",
    "template_bytes",
]
