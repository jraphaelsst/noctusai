"""The chain of matrículas behind an imóvel (migration 301): a matrícula CLOSED
by transfer to another registry (`matricula_encerrada`) is a PREDECESSOR. It
never becomes the imóvel's current reading, but the acts that built the
current ownership (the título aquisitivo, the last transfer of ownership)
often live ONLY there — the successor opens with an abertura and a "REGISTRO
ANTERIOR: R-04/M-21.748 …" citation, no transmission act of its own.

Owner 2026-10-22: a título/última-transferência derivation that stopped at the
current matrícula answered "nenhum ato confirmado" (or, worse, named a 1985
compra e venda as the last transfer when a 1988 doação sat on the closed
predecessor). So the derivation consults the predecessors, and any phrase
built from one of their acts says WHERE the act lives ("da matrícula nº
21.748 do Registro de Imóveis de Barueri/SP").
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.documents import Instrumento, find_matricula, frase_titulo_aquisitivo
from noctusai_lib.integrations.documents.matricula_cabecalho import find_cartorio

from app.modules.imovel_hub import documentos_service as docs_svc
from app.modules.imovel_hub import vinculo_legal
from app.modules.matriculas import estrutura_service as estrutura_svc
from app.services import table_reads


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _numero_formatado(numero: str) -> str:
    return f"{int(numero):,}".replace(",", ".") if numero.isdigit() else numero


def _documento_encerrado(client: Any, org_id: UUID, extracao: dict) -> bool:
    documento_id = extracao.get("imovel_documento_id")
    if not documento_id:
        return False
    rows = (
        _t(client, docs_svc.TABLE)
        .select("matricula_encerrada,tipo_documento")
        .eq("org_id", str(org_id))
        .eq("id", str(documento_id))
        .limit(1)
        .execute()
    ).data or []
    return bool(rows and rows[0].get("tipo_documento") == "matricula" and rows[0].get("matricula_encerrada"))


def extracao_e_predecessora(client: Any, org_id: UUID, extracao: dict) -> bool:
    """True when the extraction transcribes a matrícula closed by transfer."""
    return _documento_encerrado(client, org_id, extracao)


def matricula_origem(client: Any, org_id: UUID, extracao: dict) -> Optional[str]:
    """`da matrícula nº 21.748 do <cartório>` when the extraction is a
    predecessor matrícula; `None` for the current one. Read literally from the
    document's own heading (number + registry); a part the heading does not
    state is omitted, never invented."""
    if not _documento_encerrado(client, org_id, extracao):
        return None
    texto = estrutura_svc.texto_da_extracao(client, org_id, extracao["id"]) or ""
    numero, conf, _ = find_matricula(texto)
    cartorio, _conf, _ = find_cartorio(texto)
    if not numero or conf == "nenhuma":
        return f"da matrícula anterior do {cartorio}" if cartorio else None
    frase = f"da matrícula nº {_numero_formatado(numero)}"
    return f"{frase} do {cartorio}" if cartorio else frase


def extracoes_predecessoras(client: Any, org_id: UUID, codigo: str) -> list[dict]:
    """The imóvel's concluded transcriptions of CLOSED matrículas, newest
    first. The manual record linked to a Vista código is included."""
    saida: list[dict] = []
    for fonte in vinculo_legal.codigos_leitura(client, org_id, codigo):
        documentos = (
            _t(client, docs_svc.TABLE)
            .select("id")
            .eq("org_id", str(org_id))
            .eq("codigo", fonte)
            .eq("tipo_documento", "matricula")
            .eq("matricula_encerrada", True)
            .execute()
        ).data or []
        for documento in documentos:
            saida.extend(
                (
                    _t(client, estrutura_svc.EXTRACOES_TABLE)
                    .select("*")
                    .eq("org_id", str(org_id))
                    .eq("imovel_documento_id", str(documento["id"]))
                    .eq("status", estrutura_svc.STATUS_CONCLUIDA)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                ).data
                or []
            )
    return sorted(saida, key=lambda e: str(e.get("created_at") or ""), reverse=True)


def frase_titulo(ato: dict, det: dict, origem: Optional[str] = None) -> Optional[str]:
    """THE título aquisitivo phrase over one act's typed details — one
    derivation for the suggestion (`titulo_service.obter_titulo`), the machine
    fill (`preenchimento_service`) and the autopilot, so they can never
    disagree on what the act says."""
    if ato.get("numero") is None:
        return None
    bruto = det.get("data_registro")
    return frase_titulo_aquisitivo(
        Instrumento.from_json(det.get("instrumento")),
        kind=ato["kind"],
        numero=int(ato["numero"]),
        natureza=det.get("natureza"),
        data_registro=_data(bruto),
        matricula_origem=origem,
    )


def _data(bruto: Any) -> Optional[date]:
    return date.fromisoformat(str(bruto)[:10]) if bruto else None
