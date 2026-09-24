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

from noctusai_lib.integrations.documents.abnt import UnsupportedGlyphError
from noctusai_lib.integrations.docx_render import DocxRenderAdapter
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.exceptions import AppException

from app.modules.card_hub import contratos_service as contratos_svc
from app.modules.card_hub import services as svc
from app.modules.card_hub.contrato_gerador.carregador import carregar
from app.modules.card_hub.contrato_gerador.contexto import snapshot_sha256
from app.modules.card_hub.contrato_gerador.dados import DadosContrato
from app.modules.card_hub.contrato_gerador.derivacao import (
    avaliar,
    derivar_switches,
    modelo_derivado,
)
from app.modules.card_hub.contrato_gerador.documento import MIME_PDF, gerar_pdf, renderizar
from app.modules.card_hub.contrato_gerador.lint import lint
from app.modules.card_hub.contrato_gerador.politica import Politica
from app.modules.card_hub.contrato_gerador.validacao_extracao import exigir_sem_pendentes

FUSO = ZoneInfo("America/Sao_Paulo")


def hoje() -> date:
    """The office's calendar date — a contract signed at 22h in São Paulo is
    not dated tomorrow because the server runs on UTC."""
    return datetime.now(FUSO).date()


def data_assinatura(dados: DadosContrato, pedida: Optional[date]) -> date:
    """Which date the instrument is dated, and which the gate measures every
    certidão's age against.

    Precedence, most specific first: the date the operator asked for in THIS
    request, then the date STORED on the contract
    (`atendimento_contratos.assinatura_data`, migration 114), then today in
    São Paulo. A stored date beats "today" because the office sets it when the
    signing is scheduled; an explicit request beats the stored one because
    that is an operator dating this generation deliberately.
    """
    return pedida or dados.assinatura_data or hoje()


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


class ContratoPdfNaoGerado(AppException):
    """`gerar_pdf` found a character the core Times font's `WinAnsiEncoding`
    cannot represent (`UnsupportedGlyphError`) — a refusal, nothing saved,
    never a silent 500 (contract §5)."""

    def __init__(self, motivo: str) -> None:
        super().__init__(
            code="CONTRATO_PDF_NAO_GERADO",
            message="O documento gerado não pôde ser convertido em PDF.",
            status_code=422,
            details={"motivo": motivo},
        )


def obter_geracao(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    *,
    usuario_id: Optional[Any],
    politica: Politica,
) -> dict:
    dados, _ = carregar(client, org_id, cliente_id, contrato_id, usuario_id=usuario_id)
    # [E1/H2] ONE `hoje()` snapshot for both switches and the gate — never
    # one call per function, which could disagree across a real midnight
    # boundary between the two.
    referencia = hoje()
    switches = derivar_switches(dados, politica, referencia)
    # No date is "asked for" on a GET, so this is the stored one or today —
    # the same value `gerar` will use for a POST with no explicit date, which
    # is what makes this answer the POST's precondition rather than an
    # approximation of it.
    avaliacao = avaliar(dados, switches, politica, data_assinatura(dados, None), referencia)
    derivado = modelo_derivado(switches)
    return {
        "contrato_id": str(contrato_id),
        "pronto": avaliacao.pronto,
        "modelo_derivado": derivado,
        "modelo_confere": dados.modelo == derivado,
        # True = `gerar` will set the contract's modelo to `modelo_derivado`
        # (a 'gerado' contract); False = a mismatch is only flagged.
        "modelo_automatico": dados.origem == "gerado",
        # Migration 151 — so the UI can show the dispensation is active
        # even before the reader gets down to the avisos that name it.
        "processo_legado": dados.processo_legado,
        # Migration 157 — which instrument `gerar` will render.
        "modalidade_assinatura": dados.modalidade_assinatura,
        "switches": switches,
        "faltando": avaliacao.faltando,
        "bloqueios": avaliacao.bloqueios,
        "avisos": avaliacao.avisos,
    }


#: Title of a contract started from the card's "Gerar contrato" button —
#: the instrument's own name (see this package's docstring).
TITULO_GERADO = "Promessa de Venda e Compra"


def iniciar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    usuario_id: Optional[Any],
    politica: Politica,
) -> dict:
    """Start a generated contract for this deal — or CONTINUE one already
    started, when it never got a version. Sets the contract's modelo to the
    one the deal's data derives, and returns it with the readiness report —
    so the card can show "what is missing" at once. Nothing is rendered
    here; v1 comes from `gerar` once `pronto`.

    🔴 REUSES A LEFTOVER DRAFT (2026-09-22) INSTEAD OF ALWAYS INSERTING.
    `criar_para_gerar` used to run unconditionally on every call — one more
    empty `rascunho` row per click of the "Gerar contrato" button, since a
    generated draft cannot render itself. `contratos_svc.
    rascunho_gerado_sem_versao` finds the atendimento's newest `origem=
    'gerado'`, `status='rascunho'` draft that still has ZERO versions, if
    any, and this reuses it — same as a freshly created row, its modelo is
    still re-derived and corrected below, so "the same derived modelo" is
    true by construction rather than something this function has to compare
    up front. The caller (the router) is told whether a row was created or
    reused, to answer 201 vs 200.
    """
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    reaproveitado = contratos_svc.rascunho_gerado_sem_versao(client, org_id, atendimento_id)
    if reaproveitado is not None:
        row = reaproveitado
    else:
        row = contratos_svc.criar_para_gerar(
            client,
            org_id,
            atendimento_id,
            titulo=TITULO_GERADO,
            modelo="compra_venda",
            criado_por=usuario_id,
        )
    contrato_id = UUID(row["id"])
    dados, _ = carregar(client, org_id, cliente_id, contrato_id, usuario_id=usuario_id)
    derivado = modelo_derivado(derivar_switches(dados, politica, hoje()))
    if derivado != row["modelo"]:
        contratos_svc.definir_modelo(client, org_id, contrato_id, derivado)
        row["modelo"] = derivado
    return {
        "contrato": contratos_svc.saida(client, org_id, row),
        "geracao": obter_geracao(
            client, org_id, cliente_id, contrato_id, usuario_id=usuario_id, politica=politica
        ),
        # Popped by the router before the body is serialised — decides
        # 201 (a brand-new draft) vs 200 (an unrendered one continued).
        "_reaproveitado": reaproveitado is not None,
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
    politica: Politica,
) -> dict:
    dados, atendimento_id = carregar(client, org_id, cliente_id, contrato_id, usuario_id=usuario_id)
    # Owner decision D2 (migration 156): nothing a machine extracted may reach
    # the instrument before a human validated it. Checked FIRST — a rejected
    # value turns into a `faltando` below, so the validation is what the
    # operator must clear before the completeness report is even meaningful.
    # 409 `EXTRACAO_PENDENTE_VALIDACAO`; the modal is UI, this is the gate.
    exigir_sem_pendentes(client, org_id, dados, usuario_id=usuario_id)
    data = data_assinatura(dados, assinatura)
    # [E1/H2] ONE `hoje()` snapshot for switches, the gate, AND the render —
    # a generation run reads a single "today" throughout, never one call
    # per stage that could disagree across a real midnight boundary.
    referencia = hoje()
    switches = derivar_switches(dados, politica, referencia)
    avaliacao = avaliar(dados, switches, politica, data, referencia)
    if not avaliacao.pronto:
        raise ContratoIncompleto(avaliacao.faltando, avaliacao.bloqueios)

    renderizado = renderizar(adapter, dados, switches, politica, data, referencia)
    achados = lint(
        renderizado.paragrafos,
        referencias=renderizado.referencias,
        clausulas=renderizado.clausulas,
    )
    if achados:
        raise ContratoReprovadoNaRevisao(achados)

    # A 'gerado' contract's modelo is the derived one by construction — keep
    # it in sync with the data this version was rendered from (the deal may
    # have gained parcelas since `iniciar` set it).
    derivado = modelo_derivado(switches)
    if dados.origem == "gerado" and dados.modelo != derivado:
        contratos_svc.definir_modelo(client, org_id, contrato_id, derivado)

    # `renderizado.docx` is the editable rendering; `gerar_pdf` derives the
    # ABNT PDF from it. BOTH are stored on the saved version (migration 120,
    # 2026-09-16) — the user can download either.
    try:
        pdf = gerar_pdf(renderizado.docx)
    except UnsupportedGlyphError as exc:
        raise ContratoPdfNaoGerado(str(exc)) from exc

    versao = await contratos_svc.nova_versao_gerada(
        client,
        storage,
        org_id,
        atendimento_id,
        contrato_id,
        data=pdf,
        content_type=MIME_PDF,
        docx=renderizado.docx,
        contexto_sha256=snapshot_sha256(dados, politica, data),
        usuario_id=usuario_id,
        # Migration 157 — so "Baixar para impressão" only ever offers a
        # rendering that actually carries the signature lines.
        modalidade_assinatura=dados.modalidade_assinatura,
    )
    return {"versao": versao, "avisos": avaliacao.avisos}


__all__ = [
    "ContratoIncompleto",
    "ContratoPdfNaoGerado",
    "ContratoReprovadoNaRevisao",
    "data_assinatura",
    "gerar",
    "hoje",
    "iniciar",
    "obter_geracao",
]
