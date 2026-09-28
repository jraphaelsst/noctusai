"""Cartão CNPJ extraction (P0c contract §C6) — the background job the
upload route schedules, and the recovery sweep's own entry point.

`extrair_cartao` is `card_hub`'s `extrair_identidade` sibling for this
surface: stamp `processando`, read the blob, log the access, call the
(injected) extractor, record the WHOLE reading on the document
(`extracao_dados`), and apply the group-level D1 policy onto `empresas`
(`dados_service.aplicar_cartao`) — never raising; every failure path ends
in a recorded `extracao_status`, same contract every sibling extraction
gives its own sweep recovery.

🔴 lesson G6 (2026-09-28): this used to stamp `extracao_status='ok'`
BEFORE calling `dados_service.aplicar_cartao`, with no `try` around the
apply at all — a transient DB error there left the document `ok` with
nothing actually applied, and the sweep never revisits an `ok` row. Now
built on the shared `app.services.extracao_job` runner (the recurrence-
rule formalization — see that module's own docstring): the reading is
persisted and the apply runs inside ONE failure domain, and the terminal
status is written only after both succeed.
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
from app.services import campo_conflitos, extracao_job, table_reads

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
    if extractor is None:
        # A caller with no pre-built extractor (mirrors `identidade_
        # extracao_service.extrair_identidade`'s own fallback) — every REAL
        # caller (the upload route, the re-run route, the sweep) passes one
        # pre-built through `deps.get_cartao_extractor_factory()`.
        from app.modules.empresas.deps import get_cartao_extractor_factory

        extractor = get_cartao_extractor_factory()(str(org_id), "cartao_cnpj")

    async def _ler(blob_bytes: bytes, doc: dict) -> Any:
        return await extractor.extract(
            blob_bytes, mimetype=doc.get("mime_type"), filename=doc.get("nome_original"),
        )

    async def _processar(leitura: Any, doc: dict) -> dict:
        # Recorded BEFORE the apply step — a failure past this point still
        # leaves the reading on the document rather than a row stuck with
        # nothing to show for the vision call.
        extracao_job.marcar(
            client, TABLE, documento_id,
            extracao_fonte=getattr(leitura.source, "value", leitura.source),
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

        achou_algo = bool(leitura.cnpj or leitura.razao_social or leitura.situacao_cadastral)
        return {
            "status": "ok" if achou_algo else "sem_dados",
            "aviso": resultado.get("aviso"),
            "conflitos": len(conflitos),
        }

    config = extracao_job.ExtractionJobConfig(
        table=TABLE,
        bucket=BUCKET,
        deve_extrair=documentos_service.deve_extrair,
        ler=_ler,
        leitura_erro=lambda leitura: leitura.error,
        leitura_erro_mensagem=lambda leitura: leitura.error_message,
        leitura_fonte=lambda leitura: getattr(leitura.source, "value", leitura.source),
        log_acesso=lambda org, doc_id: _log_acesso(client, org, doc_id),
        processar=_processar,
    )
    return await extracao_job.executar(client, storage, org_id, documento_id, config)


__all__ = ["MAX_RETENTATIVAS_ERRO", "MAX_TENTATIVAS", "extrair_cartao"]
