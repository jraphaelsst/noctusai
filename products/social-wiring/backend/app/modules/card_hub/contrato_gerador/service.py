"""`obter_geracao` (the readiness report) and `gerar` (render + save).

Both run the SAME loader, switches and gate, so the GET answer is exactly the
POST's precondition. `gerar` refuses before rendering when the gate is not
`pronto`, refuses before saving when the post-render lint finds anything, and
only then writes a version (origem='gerado' + the context snapshot hash).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from noctusai_lib.integrations.docx_render import DocxRenderAdapter
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.exceptions import AppException

from app.modules.card_hub import contratos_service as contratos_svc
from app.modules.card_hub.contrato_gerador.carregador import carregar
from app.modules.card_hub.contrato_gerador.contexto import snapshot_sha256
from app.modules.card_hub.contrato_gerador.dados import Complementos
from app.modules.card_hub.contrato_gerador.derivacao import (
    avaliar,
    derivar_switches,
    modelo_derivado,
)
from app.modules.card_hub.contrato_gerador.documento import MIME_DOCX, renderizar
from app.modules.card_hub.contrato_gerador.lint import lint
from app.modules.card_hub.contrato_gerador.politica import Politica

FUSO = ZoneInfo("America/Sao_Paulo")


def hoje() -> date:
    """The office's calendar date — a contract signed at 22h in São Paulo is
    not dated tomorrow because the server runs on UTC."""
    return datetime.now(FUSO).date()


class ContratoIncompleto(AppException):
    def __init__(self, faltando: list[dict], bloqueios: list[dict]) -> None:
        super().__init__(
            code="CONTRATO_INCOMPLETO",
            message="O contrato não pode ser gerado: há dados faltando ou inconsistentes.",
            status_code=400,
            details={"faltando": faltando, "bloqueios": bloqueios},
        )


class ContratoReprovadoNaRevisao(AppException):
    """The rendered text failed the post-render lint — nothing was saved."""

    def __init__(self, achados: list[dict]) -> None:
        super().__init__(
            code="CONTRATO_LINT",
            message="O documento gerado não passou na verificação final; nenhuma versão foi salva.",
            status_code=422,
            details={"lint": achados},
        )


def obter_geracao(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    *,
    usuario_id: Optional[Any],
    complementos: Complementos,
    politica: Politica,
) -> dict:
    dados, _ = carregar(
        client, org_id, cliente_id, contrato_id, usuario_id=usuario_id, complementos=complementos
    )
    switches = derivar_switches(dados, politica)
    avaliacao = avaliar(dados, switches, politica, hoje())
    derivado = modelo_derivado(switches)
    return {
        "contrato_id": str(contrato_id),
        "pronto": avaliacao.pronto,
        "modelo_derivado": derivado,
        "modelo_confere": dados.modelo == derivado,
        "switches": switches,
        "faltando": avaliacao.faltando,
        "bloqueios": avaliacao.bloqueios,
        "avisos": avaliacao.avisos,
    }


async def gerar(
    client: Any,
    storage: StorageBackend,
    adapter: DocxRenderAdapter,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    *,
    assinatura: Optional[date],
    usuario_id: Optional[Any],
    complementos: Complementos,
    politica: Politica,
) -> dict:
    data_assinatura = assinatura or hoje()
    dados, atendimento_id = carregar(
        client, org_id, cliente_id, contrato_id, usuario_id=usuario_id, complementos=complementos
    )
    switches = derivar_switches(dados, politica)
    avaliacao = avaliar(dados, switches, politica, data_assinatura)
    if not avaliacao.pronto:
        raise ContratoIncompleto(avaliacao.faltando, avaliacao.bloqueios)

    renderizado = renderizar(adapter, dados, switches, politica, data_assinatura)
    achados = lint(
        renderizado.paragrafos,
        referencias=renderizado.referencias,
        clausulas=renderizado.clausulas,
    )
    if achados:
        raise ContratoReprovadoNaRevisao(achados)

    versao = await contratos_svc.nova_versao_gerada(
        client,
        storage,
        org_id,
        atendimento_id,
        contrato_id,
        data=renderizado.docx,
        content_type=MIME_DOCX,
        contexto_sha256=snapshot_sha256(dados, politica, data_assinatura),
        usuario_id=usuario_id,
    )
    return {"versao": versao, "avisos": avaliacao.avisos}


__all__ = [
    "ContratoIncompleto",
    "ContratoReprovadoNaRevisao",
    "gerar",
    "hoje",
    "obter_geracao",
]
