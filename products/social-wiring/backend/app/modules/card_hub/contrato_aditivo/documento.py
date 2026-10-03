"""Aditivo -> template context -> .docx (seed `docx_render`) -> lint -> PDF.

Everything here composes the contract generator's pipeline by IMPORT:
qualification (`frases.qualificacao`), agreement (`concordancia.lado`), the
matrícula quote (`contexto._descricao_matricula_rica`), the title address
(`derivacao.resolver_endereco_posse`), the office's page face
(`documento._aplicar_face`), the inline-markup → runs pass
(`docx_render.apply_inline_markup`), the post-render lint (`lint.lint`) and
the ABNT PDF (`documento.gerar_pdf`, called by the service). The private
names (`_aplicar_face`, `_descricao_matricula_rica`) are reported as
public-seam candidates in this slice's delivery note.

🔴 THE LINT AND THE OTHER INSTRUMENT. `lint.lint` assumes every "Cláusula
X" / "Parcela NN" in the text names a clause/parcela OF THIS DOCUMENT. An
aditivo, by construction, also cites the ORIGINAL's ("Cláusula Segunda do
contrato original"). `lint_aditivo` masks exactly the citation shapes
`frases.ref_clausula_original` / `ref_parcela_original` produce — nothing
looser — so the house style's own CLÁUSULA sequence, the restated parcelas
and every money/extenso pair stay under the generator's lint unchanged; and
it adds one rule of its own: every masked citation must name a real ordinal.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

from noctusai_lib.domain.texto_ptbr import data_por_extenso, numero_com_extenso, ordinal_por_extenso
from noctusai_lib.integrations.docx_render import DocxRenderAdapter, apply_inline_markup

from app.modules.card_hub.contrato_aditivo import frases as frases_aditivo
from app.modules.card_hub.contrato_aditivo.avaliacao import parcelas_ordenadas, preco_aditivo
from app.modules.card_hub.contrato_aditivo.dados import DadosAditivo, alteracoes_para_json
from app.modules.card_hub.contrato_aditivo.modelo_texto import LINHA_TITULO, linhas_do_template
from app.modules.card_hub.contrato_gerador import frases
from app.modules.card_hub.contrato_gerador.contexto import _descricao_matricula_rica, snapshot_sha256
from app.modules.card_hub.contrato_gerador.dados import DadosContrato, signatarios
from app.modules.card_hub.contrato_gerador.derivacao import resolver_endereco_posse
from app.modules.card_hub.contrato_gerador.documento import _aplicar_face, paragrafos_do_docx
from app.modules.card_hub.contrato_gerador.estilo import texto_plano
from app.modules.card_hub.contrato_gerador.lint import lint
from app.modules.card_hub.contrato_gerador.politica import Politica

#: Heading lines of either template, matched on the RAW template line.
_TITULO_SECAO = ("<u>CLÁUSULA", "**{{ s.num }}.", "**{{ n_final }}.", "TESTEMUNHAS:")
_ALINHADO_DIREITA = "{{ assinatura.local }}"


def _estilo_da_linha(linha: str) -> str:
    """The SAME Word style names `contrato_gerador.documento.gerar_pdf` maps
    to ABNT kinds (Title / Heading 1 / Normal) — so the PDF's layout comes
    from the kind, exactly as for the contract."""
    if linha == LINHA_TITULO:
        return "Title"
    if linha.startswith(_TITULO_SECAO) or texto_plano(linha).startswith("TESTEMUNHAS:"):
        return "Heading 1"
    return "Normal"


@lru_cache(maxsize=2)
def template_bytes(estilo: str) -> bytes:
    doc = Document()
    _aplicar_face(doc)
    for linha in linhas_do_template(estilo):
        paragrafo = doc.add_paragraph(linha, style=_estilo_da_linha(linha))
        if linha.startswith(_ALINHADO_DIREITA):
            paragrafo.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _titulo_curto(d: DadosContrato) -> str:
    """The original's own title address rule (`contexto.montar_contexto`):
    empreendimento + the matrícula-derived address, never the CRM street."""
    im = d.imovel
    assert im is not None  # gated
    endereco = resolver_endereco_posse(
        im.endereco_registro_texto,
        d.matricula.descricao_imovel_texto or d.matricula.texto,
        d.matricula.texto,
    )
    assert endereco is not None  # gated
    if im.empreendimento:
        nome = f"{im.empreendimento} – {im.endereco.complemento}" if im.endereco.complemento else im.empreendimento
        return f"{nome} – {endereco}"
    return endereco


def _numerar(secao: frases_aditivo.Secao, num: int, estilo: str) -> list[str]:
    if estilo != "formal":
        return list(secao.paragrafos)
    saida, k = [], 0
    for i, texto in enumerate(secao.paragrafos):
        if i in secao.subitens:
            k += 1
            saida.append(f"{num}.{k}. {texto}")
        else:
            saida.append(texto)
    return saida


def montar_contexto(
    d: DadosContrato,
    ad: DadosAditivo,
    politica: Politica,
    assinatura: date,
    adapter: DocxRenderAdapter,
) -> dict[str, Any]:
    """Only reached after `avaliacao.avaliar` returned `pronto`."""
    assert d.imovel is not None and ad.original_assinatura_data is not None  # gated
    V, C = frases_aditivo.lados(d)
    vend, comp = signatarios(d.vendedores), signatarios(d.compradores)
    im = d.imovel
    titulo_curto = _titulo_curto(d)
    cidade, uf = im.endereco.cidade or "", (im.endereco.uf or "").upper()
    ordinal = frases_aditivo.ordinal_aditivo(ad.ordinal)
    corpo = f"PROMESSA DE VENDA E COMPRA DE BEM IMÓVEL – {titulo_curto.upper()} – {cidade.upper()}/{uf}"
    if ad.estilo == "formal":
        titulo = f"{ordinal} TERMO ADITIVO AO INSTRUMENTO PARTICULAR DE {corpo}"
    else:
        prefixo = "" if ad.ordinal == 1 else f"{ordinal} "
        titulo = f"{prefixo}ADITIVO AO INSTRUMENTO PARTICULAR DE {corpo}."

    secoes = frases_aditivo.secoes(
        ad.alteracoes, d, parcelas_ordenadas(ad), preco_aditivo(d, ad), estilo=ad.estilo
    )
    # House: CLÁUSULA PRIMEIRA is the object, amendments from SEGUNDA.
    # Formal: sections numbered 1..N, ratification N+1.
    primeiro = 2 if ad.estilo == "house" else 1
    secoes_ctx = [
        {
            "num": n,
            "ord": ordinal_por_extenso(n, feminino=True).upper(),
            "titulo": s.titulo_house if ad.estilo == "house" else s.titulo_formal,
            "paragrafos": _numerar(s, n, ad.estilo),
        }
        for n, s in enumerate(secoes, start=primeiro)
    ]
    final = primeiro + len(secoes)
    return {
        "titulo": titulo,
        "ordinal": ordinal,
        "V": V,
        "C": C,
        "V_qualificacao": frases.qualificacao(vend, lei_6515_desde=politica.lei_6515_vigencia_desde),
        "C_qualificacao": frases.qualificacao(comp, lei_6515_desde=politica.lei_6515_vigencia_desde),
        "imovel": {
            "cidade": cidade,
            "descricao_matricula": _descricao_matricula_rica(d, adapter),
            "inscricao_municipal": im.inscricao_municipal,
            "matricula_numero": frases.matricula_numero(im.numero_matricula),
            "cartorio": im.numero_registro_imoveis,
        },
        "original": {
            "data": frases_aditivo.data_original_texto(ad.original_assinatura_data),
            "titulo": (
                "Instrumento Particular de Promessa de Venda e Compra de Bem Imóvel – "
                f"{titulo_curto} – {cidade}/{uf}"
            ),
        },
        "secoes": secoes_ctx,
        "ord_final": ordinal_por_extenso(final, feminino=True).upper(),
        "n_final": final,
        "digital": ad.modalidade_assinatura != "fisica",
        "vias": numero_com_extenso(max(2, len(vend) + len(comp)), feminino=True, largura=2),
        "assinatura": {
            "local": d.imobiliaria.endereco.cidade,
            "data_extenso": data_por_extenso(assinatura),
        },
        "V_signatarios": [frases.signatario_linha(p) for p in vend],
        "C_signatarios": [frases.signatario_linha(p) for p in comp],
        "testemunhas": [
            {"linha": frases.nome_email_linha(t.nome, t.email), "cpf": frases.documento_linha(t.cpf)}
            for t in d.testemunhas
        ],
        "linha_assinatura": frases.LINHA_ASSINATURA,
        "V_assinantes_fisicos": [frases.assinante_fisico(p) for p in vend],
        "C_assinantes_fisicos": [frases.assinante_fisico(p) for p in comp],
        "testemunhas_fisicas": [
            {"nome": (t.nome or "").upper(), "documento": frases.testemunha_documento_linha(t.cpf)}
            for t in d.testemunhas
        ],
        # Which sections are operator text — the service names them in the
        # version's legal review.
        "_livres": [s.titulo_house for s in secoes if s.livre],
    }


# ─── lint ────────────────────────────────────────────────────────────────

_ORIGINAL = "|".join(re.escape(v) for v in frases_aditivo.ORIGINAL_POR_ESTILO.values())
_RE_REF_ORIGINAL = re.compile(
    rf"[Cc]láusula ([A-Za-zÀ-ÿ]+(?: [A-Za-zÀ-ÿ]+)?) (?:{_ORIGINAL})"
)
_RE_PARCELA_ORIGINAL = re.compile(rf"[Pp]arcela \d{{2}} (?:{_ORIGINAL})")
_ORDINAIS_FEM = {ordinal_por_extenso(n, feminino=True).title() for n in range(1, 60)}


def lint_aditivo(paragrafos: list[str]) -> list[dict]:
    achados: list[dict] = []
    mascarados: list[str] = []
    for i, texto in enumerate(paragrafos, start=1):
        for m in _RE_REF_ORIGINAL.finditer(texto):
            if m.group(1) not in _ORDINAIS_FEM:
                achados.append(
                    {
                        "codigo": "REFERENCIA_ORIGINAL_INVALIDA",
                        "mensagem": f"Parágrafo {i} cita a cláusula '{m.group(1)}' do contrato original.",
                    }
                )
        texto = _RE_REF_ORIGINAL.sub("item do instrumento original", texto)
        mascarados.append(_RE_PARCELA_ORIGINAL.sub("item do instrumento original", texto))
    return achados + lint(mascarados, referencias={}, clausulas={})


# ─── render ──────────────────────────────────────────────────────────────


@dataclass
class AditivoRenderizado:
    docx: bytes
    paragrafos: list[str]
    #: Titles of the `outro` (operator-text) sections.
    livres: list[str]


def renderizar(
    adapter: DocxRenderAdapter,
    d: DadosContrato,
    ad: DadosAditivo,
    politica: Politica,
    assinatura: date,
) -> AditivoRenderizado:
    contexto = montar_contexto(d, ad, politica, assinatura, adapter)
    livres = contexto.pop("_livres")
    docx = apply_inline_markup(adapter.render(template_bytes(ad.estilo), contexto))
    return AditivoRenderizado(docx=docx, paragrafos=paragrafos_do_docx(docx), livres=livres)


def snapshot_aditivo_sha256(d: DadosContrato, ad: DadosAditivo, politica: Politica, assinatura: date) -> str:
    """The contract's own snapshot hash, chained with the aditivo's data —
    same card state + same aditivo + same date -> same hash."""
    payload = {
        "contrato": snapshot_sha256(d, politica, assinatura),
        "aditivo": {
            "id": ad.aditivo_id,
            "ordinal": ad.ordinal,
            "estilo": ad.estilo,
            "modalidade": ad.modalidade_assinatura,
            "alteracoes": alteracoes_para_json(ad.alteracoes),
            "parcelas": [
                {
                    "tipo": p.tipo, "valor": str(p.valor), "vencimento": str(p.vencimento),
                    "evento": p.evento, "forma": p.forma_pagamento, "favorecido": p.favorecido_id,
                    "confissao": p.confissao_divida, "ordem": p.ordem,
                }
                for p in parcelas_ordenadas(ad)
            ],
            "original_data": str(ad.original_assinatura_data),
        },
    }
    canonico = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


__all__ = [
    "AditivoRenderizado",
    "lint_aditivo",
    "montar_contexto",
    "renderizar",
    "snapshot_aditivo_sha256",
    "template_bytes",
]
