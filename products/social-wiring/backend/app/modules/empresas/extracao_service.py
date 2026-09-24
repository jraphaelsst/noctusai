"""Cartão CNPJ extraction (P0c contract §C6) — the background job the
upload route schedules, and the recovery sweep's own entry point.

`extrair_cartao` is `card_hub`'s `extrair_identidade` sibling for this
surface: stamp `processando`, read the blob, log the access, call the
(injected) extractor, record the WHOLE reading on the document
(`extracao_dados`), and apply the group-level D1 policy onto `empresas`
(`dados_service.aplicar_cartao`) — never raising; every failure path ends
in a recorded `extracao_status`, same contract every sibling extraction
gives its own sweep recovery.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.storage import StorageBackend

from app.modules.empresas import dados_service, documentos_service
from app.modules.empresas.deps import BUCKET
from app.services import campo_conflitos, table_reads

logger = logging.getLogger(__name__)

TABLE = documentos_service.TABLE

#: `_fan_out`/the sweep gives up on a Cartão after this many STARTS (D3,
#: mirroring `identidade_extracao_service.MAX_TENTATIVAS`).
MAX_TENTATIVAS = 3
MAX_RETENTATIVAS_ERRO = MAX_TENTATIVAS - 1


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _marcar(client: Any, documento_id: UUID, **campos: Any) -> None:
    _t(client, TABLE).update(campos).eq("id", str(documento_id)).execute()


def _log_acesso(client: Any, org_id: UUID, documento_id: UUID) -> None:
    _t(client, "empresa_documento_acessos").insert(
        {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "documento_id": str(documento_id),
            "usuario_id": None,
            "acao": "extract",
            "created_at": _now(),
        }
    ).execute()


def _serializar_leitura(leitura: Any) -> dict:
    """`CartaoCnpjFields` → JSON-safe dict for `extracao_dados` (contract
    §A.3: "the full reading — every CartaoCnpjFields value incl. per-field
    confiança/rótulo")."""
    if is_dataclass(leitura) and not isinstance(leitura, type):
        dados = asdict(leitura)
    else:
        dados = dict(vars(leitura))
    for chave in ("data_abertura", "data_situacao_cadastral"):
        valor = dados.get(chave)
        if hasattr(valor, "isoformat"):
            dados[chave] = valor.isoformat()
    if hasattr(dados.get("emitido_em"), "isoformat"):
        dados["emitido_em"] = dados["emitido_em"].isoformat()
    fonte = dados.get("source")
    dados["source"] = getattr(fonte, "value", fonte)
    confiancas = dados.get("confiancas") or {}
    dados["confiancas"] = {
        k: getattr(v, "value", v) for k, v in confiancas.items()
    }
    return dados


async def extrair_cartao(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    empresa_id: UUID,
    documento_id: UUID,
    *,
    extractor: Any,
    notification_service: Optional[Any] = None,
) -> dict:
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(documento_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        logger.warning("empresas: documento %s not found for org %s", documento_id, org_id)
        return {"status": "erro", "erro": "documento_nao_encontrado"}
    doc = rows[0]
    if doc.get("deleted_at"):
        return {"status": "erro", "erro": "documento_removido"}
    if not documentos_service.deve_extrair(doc["tipo_documento"]):
        return {"status": "erro", "erro": "tipo_nao_extraivel"}

    tentativas = int(doc.get("extracao_tentativas") or 0) + 1
    _marcar(
        client, documento_id,
        extracao_status="processando", extracao_em=_now(), extracao_tentativas=tentativas,
    )

    try:
        blob = await storage.get(bucket=BUCKET, key=doc["storage_path"])
    except Exception as exc:  # noqa: BLE001 - detached job; record, never raise
        logger.warning("empresas extracao %s: storage read failed: %s", documento_id, exc)
        _marcar(
            client, documento_id,
            extracao_status="erro", extracao_erro=f"storage: {exc}", extracao_em=_now(),
        )
        return {"status": "erro", "erro": "storage"}
    if blob is None:
        _marcar(
            client, documento_id,
            extracao_status="erro", extracao_erro="objeto ausente no storage",
            extracao_em=_now(),
        )
        return {"status": "erro", "erro": "objeto_ausente"}

    # A content read is logged BEFORE the extraction, so a crash mid-read
    # still leaves the access recorded — same rule every sibling in this
    # product follows.
    _log_acesso(client, org_id, documento_id)

    if extractor is None:
        # A caller with no pre-built extractor (mirrors `identidade_
        # extracao_service.extrair_identidade`'s own fallback) — every REAL
        # caller (the upload route, the re-run route, the sweep) passes one
        # pre-built through `deps.get_cartao_extractor_factory()`.
        from app.modules.empresas.deps import get_cartao_extractor_factory

        extractor = get_cartao_extractor_factory()(str(org_id), "cartao_cnpj")

    leitura = await extractor.extract(
        blob.data, mimetype=doc.get("mime_type"), filename=doc.get("nome_original")
    )

    if leitura.error:
        _marcar(
            client, documento_id,
            extracao_status="erro",
            extracao_erro=f"{leitura.error}: {leitura.error_message or ''}".strip(": "),
            extracao_fonte=getattr(leitura.source, "value", leitura.source),
            extracao_em=_now(),
        )
        return {"status": "erro", "erro": leitura.error}

    achou_algo = bool(
        leitura.cnpj or leitura.razao_social or leitura.situacao_cadastral
    )
    _marcar(
        client, documento_id,
        extracao_status="ok" if achou_algo else "sem_dados",
        extracao_fonte=getattr(leitura.source, "value", leitura.source),
        extracao_erro=None,
        extracao_em=_now(),
        extracao_dados=_serializar_leitura(leitura),
    )

    resultado = dados_service.aplicar_cartao(
        client, org_id, empresa_id, leitura, documento_id=documento_id
    )
    conflitos = resultado.get("conflitos") or []
    if conflitos:
        empresa = dados_service.get_empresa(client, org_id, empresa_id)
        nome = (empresa or {}).get("razao_social") or (empresa or {}).get("cnpj") or ""

        async def _notify_one(conflito: dict) -> None:
            await notification_service.notify_empresa_field_conflict(
                org_id=org_id, conflito=conflito, empresa_nome=nome
            )

        await campo_conflitos.notificar_conflitos(
            client, campo_conflitos.EMPRESA, conflitos,
            _notify_one if notification_service is not None else None,
        )

    return {
        "status": "ok" if achou_algo else "sem_dados",
        "aviso": resultado.get("aviso"),
        "conflitos": len(conflitos),
    }


__all__ = ["MAX_RETENTATIVAS_ERRO", "MAX_TENTATIVAS", "extrair_cartao"]
