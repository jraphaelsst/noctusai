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

import re
from datetime import date
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.documents import (
    Instrumento,
    find_matricula,
    frase_titulo_aquisitivo,
    ler_encerramento,
)
from noctusai_lib.integrations.documents.matricula_cabecalho import (
    find_cartorio,
    formatar_cartorio,
)

from app.modules.imovel_hub import documentos_service as docs_svc
from app.modules.imovel_hub import vinculo_legal
from app.modules.matriculas import estrutura_service as estrutura_svc
from app.services import table_reads


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _numero_formatado(numero: str) -> str:
    return f"{int(numero):,}".replace(",", ".") if numero.isdigit() else numero


def _documento_encerrado(client: Any, org_id: UUID, extracao: dict) -> bool:
    """The extraction transcribes a matrícula CLOSED by transfer.

    The document's own `matricula_encerrada` flag (set by its structured
    read) is the fast path. It must not be the ONLY path: a matrícula
    document that was never (re-)read — or whose read ran before migration
    301 — has the flag unset while its transcription plainly carries the
    closing averbação ("…ficando encerrada a presente matrícula"), and the
    whole predecessor chain (título, última transferência, antigos
    proprietários) silently vanished with it (deal 799, F60/F61). So the
    transcription's text is read with the SAME seed reader the document
    read uses (`ler_encerramento`) when the flag says nothing."""
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
    if not rows or rows[0].get("tipo_documento") != "matricula":
        return False
    if rows[0].get("matricula_encerrada"):
        return True
    texto = extracao.get("texto_extraido") or estrutura_svc.texto_da_extracao(
        client, org_id, extracao["id"]
    )
    return ler_encerramento(texto or "")[0]


def extracao_e_predecessora(client: Any, org_id: UUID, extracao: dict) -> bool:
    """True when the extraction transcribes a matrícula closed by transfer."""
    return _documento_encerrado(client, org_id, extracao)


def _cartorio_atual(client: Any, org_id: UUID, extracao: dict) -> Optional[str]:
    """The registry of the imóvel's CURRENT matrícula (the successor), read
    literally from that document's own heading — `None` when no current
    matrícula transcription names one (never inferred from the closing
    averbação's wording)."""
    codigo = extracao.get("codigo")
    if not codigo:
        return None
    candidatas: list[dict] = []
    for fonte in vinculo_legal.codigos_leitura(client, org_id, codigo):
        documentos = (
            _t(client, docs_svc.TABLE)
            .select("id")
            .eq("org_id", str(org_id))
            .eq("codigo", fonte)
            .eq("tipo_documento", "matricula")
            .is_("deleted_at", "null")
            .execute()
        ).data or []
        for documento in documentos:
            ultima = (
                _t(client, estrutura_svc.EXTRACOES_TABLE)
                .select("*")
                .eq("org_id", str(org_id))
                .eq("imovel_documento_id", str(documento["id"]))
                .eq("status", estrutura_svc.STATUS_CONCLUIDA)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            ).data or []
            candidatas.extend(
                e for e in ultima
                if str(e["id"]) != str(extracao["id"]) and not _documento_encerrado(client, org_id, e)
            )
    for atual in sorted(candidatas, key=lambda e: str(e.get("created_at") or ""), reverse=True):
        cartorio, _conf, _ = find_cartorio(
            atual.get("texto_extraido") or estrutura_svc.texto_da_extracao(client, org_id, atual["id"]) or ""
        )
        if cartorio:
            return formatar_cartorio(cartorio)
    return None


def matricula_origem(client: Any, org_id: UUID, extracao: dict) -> Optional[str]:
    """`da matrícula nº 21.748 do Cartório de Registro de Imóveis de
    Barueri/SP, atualmente matriculado sob o nº 11.926 do Oficial de Registro
    de Imóveis de Carapicuíba/SP` when the extraction is a predecessor
    matrícula; `None` for the current one. Read literally from the document's
    own heading (number + registry) and its closing averbação (successor
    number) + the successor matrícula's own heading (its registry); a part
    the documents do not state is omitted, never invented."""
    if not _documento_encerrado(client, org_id, extracao):
        return None
    texto = estrutura_svc.texto_da_extracao(client, org_id, extracao["id"]) or ""
    numero, conf, _ = find_matricula(texto)
    cartorio, _conf, _ = find_cartorio(texto)
    cartorio = formatar_cartorio(cartorio) if cartorio else None
    if not numero or conf == "nenhuma":
        return f"da matrícula anterior do {cartorio}" if cartorio else None
    frase = f"da matrícula nº {_numero_formatado(numero)}"
    if cartorio:
        frase += f" do {cartorio}"
    sucessora = ler_encerramento(texto)[1]
    if sucessora:
        frase += f", atualmente matriculado sob o nº {_numero_formatado(sucessora)}"
        atual = _cartorio_atual(client, org_id, extracao)
        if atual:
            frase += f" do {atual}"
    return frase


_UF_DA_ORIGEM = re.compile(r"/([A-Z]{2})\b")


def extracoes_predecessoras(client: Any, org_id: UUID, codigo: str) -> list[dict]:
    """The imóvel's concluded transcriptions of CLOSED matrículas, newest
    first — closed by the document's flag OR by its own transcription
    (`_documento_encerrado`). The manual record linked to a Vista código is
    included (`codigos_leitura`)."""
    saida: list[dict] = []
    for fonte in vinculo_legal.codigos_leitura(client, org_id, codigo):
        documentos = (
            _t(client, docs_svc.TABLE)
            .select("id")
            .eq("org_id", str(org_id))
            .eq("codigo", fonte)
            .eq("tipo_documento", "matricula")
            .is_("deleted_at", "null")
            .execute()
        ).data or []
        for documento in documentos:
            ultima = (
                _t(client, estrutura_svc.EXTRACOES_TABLE)
                .select("*")
                .eq("org_id", str(org_id))
                .eq("imovel_documento_id", str(documento["id"]))
                .eq("status", estrutura_svc.STATUS_CONCLUIDA)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            ).data or []
            saida.extend(e for e in ultima if _documento_encerrado(client, org_id, e))
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
        uf_origem=(_UF_DA_ORIGEM.search(origem).group(1) if origem and _UF_DA_ORIGEM.search(origem) else None),
    )


def _data(bruto: Any) -> Optional[date]:
    return date.fromisoformat(str(bruto)[:10]) if bruto else None
