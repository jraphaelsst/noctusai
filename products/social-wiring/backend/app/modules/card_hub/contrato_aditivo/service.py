"""`obter_geracao` (readiness) and `gerar` (render + save) for one aditivo.

Same contract as `contrato_gerador.service`: both run the SAME loaders and
gate, so the GET answer is exactly the POST's precondition; `gerar` refuses
before rendering when not `pronto`, refuses before saving when the
post-render lint finds anything (the generator's own `CONTRATO_LINT`), and
only then writes a version — `origem='gerado'`, PDF + .docx, and ALWAYS
awaiting the final legal review (owner decision 2026-09-30 applied to
aditivos: an aditivo amends a signed instrument, so no generated one is
ever final without a lawyer's approval). Operator free text (`outro`) is
named individually in that review.
"""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.documents.abnt import UnsupportedGlyphError
from noctusai_lib.integrations.docx_render import DocxRenderAdapter
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.exceptions import AppException

from app.modules.card_hub.contrato_aditivo import store
from app.modules.card_hub.contrato_aditivo.avaliacao import avaliar
from app.modules.card_hub.contrato_aditivo.dados import DadosAditivo
from app.modules.card_hub.contrato_aditivo.documento import (
    lint_aditivo,
    renderizar,
    snapshot_aditivo_sha256,
)
from app.modules.card_hub.contrato_gerador.carregador import carregar
from app.modules.card_hub.contrato_gerador.dados import DadosContrato
from app.modules.card_hub.contrato_gerador.documento import gerar_pdf
from app.modules.card_hub.contrato_gerador.politica import Politica
from app.modules.card_hub.contrato_gerador.service import (
    ContratoPdfNaoGerado,
    ContratoReprovadoNaRevisao,
    hoje,
)


class AditivoIncompleto(AppException):
    """Same `details` shape as the contract's `CONTRATO_INCOMPLETO`."""

    def __init__(self, faltando: list[dict], bloqueios: list[dict]) -> None:
        super().__init__(
            code="ADITIVO_INCOMPLETO",
            message="O aditivo não pode ser gerado: há dados faltando ou inconsistentes.",
            status_code=400,
            details={"faltando": faltando, "bloqueios": bloqueios},
        )


def _carregar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    aditivo_id: UUID,
    *,
    usuario_id: Optional[Any],
) -> tuple[DadosContrato, DadosAditivo]:
    _atendimento_id, contrato = store.contexto_contrato(client, org_id, cliente_id, contrato_id)
    row = store.exigir_aditivo(client, org_id, contrato_id, aditivo_id)
    ad = store.dados_aditivo(row, store.parcelas_rows(client, org_id, aditivo_id), contrato)
    # The ORIGINAL's parties, imóvel, testemunhas, favorecidos and schedule —
    # through the generator's own loader, unchanged.
    dados, _ = carregar(client, org_id, cliente_id, contrato_id, usuario_id=usuario_id)
    return dados, ad


def data_assinatura(ad: DadosAditivo, pedida: Optional[date]) -> date:
    """Request date → the aditivo's stored date → today in São Paulo."""
    return pedida or ad.assinatura_data or hoje()


def obter_geracao(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    aditivo_id: UUID,
    *,
    usuario_id: Optional[Any],
    politica: Politica,
) -> dict:
    dados, ad = _carregar(client, org_id, cliente_id, contrato_id, aditivo_id, usuario_id=usuario_id)
    assinatura = data_assinatura(ad, None)
    av = avaliar(dados, ad, politica, assinatura, hoje())
    return {
        "aditivo_id": str(aditivo_id),
        "contrato_id": str(contrato_id),
        "ordinal": ad.ordinal,
        "estilo": ad.estilo,
        "assinatura_data": assinatura.isoformat(),
        "pronto": av.pronto,
        "faltando": av.faltando,
        "bloqueios": av.bloqueios,
        "avisos": av.avisos,
        # Every generated aditivo version awaits the final legal review.
        "revisao_juridica_exigida": True,
    }


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def campos_revisao(ad: DadosAditivo, livres: list[str], contexto_sha: str) -> list[dict]:
    """What the legal review vouches for: the aditivo's whole wording, and
    each operator-written clause by name. Never a personal value — the
    fingerprint only (`contratos_service.CAMPOS_REVISAO_CHAVES`)."""
    base = {
        "entidade": "aditivo",
        "entidade_id": ad.aditivo_id,
        "grupo": "Aditivo",
        "fonte_documento_id": None,
        "fonte_nome": None,
        "confianca": None,
    }
    campos = [
        {
            **base,
            "chave": f"aditivo:{ad.aditivo_id}:redacao",
            "campo": "redacao",
            "rotulo": "Redação do aditivo (revisão jurídica obrigatória)",
            "origem": "gerado",
            "valor_sha256": contexto_sha,
        }
    ]
    outros = ad.alteracoes_do_tipo("outro")
    for i, (alt, titulo) in enumerate(zip(outros, livres), start=1):
        campos.append(
            {
                **base,
                "chave": f"aditivo:{ad.aditivo_id}:outro:{i}",
                "campo": "outro",
                "rotulo": f"Cláusula livre: {titulo}",
                "origem": "manual",
                "valor_sha256": _sha(alt.texto),
            }
        )
    return campos


async def gerar(
    client: Any,
    storage: StorageBackend,
    adapter: DocxRenderAdapter,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    aditivo_id: UUID,
    *,
    assinatura: Optional[date],
    usuario_id: Optional[Any],
    politica: Politica,
) -> dict:
    dados, ad = _carregar(client, org_id, cliente_id, contrato_id, aditivo_id, usuario_id=usuario_id)
    data = data_assinatura(ad, assinatura)
    av = avaliar(dados, ad, politica, data, hoje())
    if not av.pronto:
        raise AditivoIncompleto(av.faltando, av.bloqueios)

    renderizado = renderizar(adapter, dados, ad, politica, data)
    achados = lint_aditivo(renderizado.paragrafos)
    if achados:
        raise ContratoReprovadoNaRevisao(achados)
    try:
        pdf = gerar_pdf(renderizado.docx)
    except UnsupportedGlyphError as exc:
        raise ContratoPdfNaoGerado(str(exc)) from exc

    contexto_sha = snapshot_aditivo_sha256(dados, ad, politica, data)
    versao = await store.nova_versao_gerada(
        client,
        storage,
        org_id,
        aditivo_id,
        pdf=pdf,
        docx=renderizado.docx,
        contexto_sha256=contexto_sha,
        modalidade_assinatura=ad.modalidade_assinatura,
        revisao_campos=campos_revisao(ad, renderizado.livres, contexto_sha),
        usuario_id=usuario_id,
    )
    return {"versao": versao, "avisos": av.avisos}


__all__ = ["AditivoIncompleto", "campos_revisao", "data_assinatura", "gerar", "obter_geracao"]
