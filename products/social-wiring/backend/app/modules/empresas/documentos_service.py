"""`empresa_documentos` — the Cartão CNPJ upload (P0c contract §A.3/§D4).

`DocumentoStore`-backed, mirroring `imovel_hub/documentos_service.py`'s own
shape (contract §H1: "Empresa docs engine: DocumentoStore (imóvel
sibling)"). `NOC-REMEDIATE[dry-documento-store]` stays open — this module is
a THIRD `DocumentoStore` consumer rather than the seed-lib convergence that
remediation names, on the same terms `imovel_hub` already accepted it.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.storage import StorageBackend

from app.modules.empresas import dados_service
from app.modules.empresas.deps import BUCKET, PREFIXO
from app.services import table_reads
from app.services.documento_retencao import dias_para
from app.services.documento_store import DocumentoStore, documento_base, today

TABLE = "empresa_documentos"

TIPOS_DOCUMENTO: tuple[str, ...] = ("cartao_cnpj",)

#: 30 MB — same ceiling `card_hub`'s client-document surfaces use; a Cartão
#: CNPJ is a one/two-page scan, well under it.
MAX_UPLOAD_BYTES = 30 * 1024 * 1024
ALLOWED_MIME_TYPES = frozenset({"application/pdf", "image/jpeg", "image/png", "image/webp"})

STORE = DocumentoStore(
    table=TABLE,
    owner_col="empresa_id",
    prefixo=PREFIXO,
    bucket=BUCKET,
    tipos=TIPOS_DOCUMENTO,
    max_bytes=MAX_UPLOAD_BYTES,
    mimes=ALLOWED_MIME_TYPES,
    acessos_table="empresa_documento_acessos",
)


def deve_extrair(tipo_documento: str) -> bool:
    return tipo_documento in TIPOS_DOCUMENTO


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _documento_out(row: dict, resolved: dict) -> dict:
    return {
        **documento_base(row, resolved),
        "empresa_id": row["empresa_id"],
        "extracao_status": row.get("extracao_status"),
        "extracao_fonte": row.get("extracao_fonte"),
        "extracao_erro": row.get("extracao_erro"),
        "extracao_dados": row.get("extracao_dados"),
        "extracao_descartada_em": row.get("extracao_descartada_em"),
        "extracao_descartada_por": table_reads.actor(
            resolved, row.get("extracao_descartada_por")
        ),
    }


def listar(client: Any, org_id: UUID, empresa_id: UUID) -> dict:
    dados_service.ensure_empresa(client, org_id, empresa_id)
    rows = STORE.listar_linhas(client, org_id, empresa_id)
    resolved = table_reads.resolve_actors(
        {r["enviado_por"] for r in rows if r.get("enviado_por")}
        | {r["extracao_descartada_por"] for r in rows if r.get("extracao_descartada_por")}
    )
    items = [_documento_out(r, resolved) for r in rows]
    return {"items": items, "total": len(items)}


def validar_upload(
    *, tipo_documento: str, content_type: str, tamanho_bytes: int,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> None:
    STORE.validar(
        tipo_documento=tipo_documento,
        content_type=content_type,
        tamanho_bytes=tamanho_bytes,
        max_bytes=max_bytes,
    )


async def upload(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    empresa_id: UUID,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    tipo_documento: str,
    enviado_por: Optional[UUID],
) -> dict:
    dados_service.ensure_empresa(client, org_id, empresa_id)
    dias = dias_para(client, org_id, "empresa", tipo_documento)
    retencao_ate = (today() + timedelta(days=dias)).isoformat() if dias else None
    row = await STORE.guardar(
        client, storage, org_id, empresa_id,
        filename=filename, content_type=content_type, data=data,
        tipo_documento=tipo_documento, enviado_por=enviado_por,
        extra={
            # `pendente` at upload — the sweep's claim path, same reasoning
            # every sibling extraction lifecycle gives: a job that never
            # starts must be visibly waiting, not invisibly lost.
            "extracao_status": "pendente" if deve_extrair(tipo_documento) else None,
            "extracao_tentativas": 0,
            "retencao_ate": retencao_ate,
        },
    )
    resolved = table_reads.resolve_actors(
        {row["enviado_por"]} if row["enviado_por"] else set()
    )
    return _documento_out(row, resolved)


def documento_pendente_ou_processando(client: Any, org_id: UUID, documento_id: UUID) -> Optional[dict]:
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(documento_id))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


async def url_do_documento(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    empresa_id: UUID,
    documento_id: UUID,
    *,
    usuario_id: Optional[UUID] = None,
) -> dict:
    """A short-TTL signed URL, minted per request, never stored. No `intent`
    parameter — view and download reuse the same URL (contract §D4
    clarification, 2026-09-24)."""
    return await STORE.url(
        client, storage, org_id, empresa_id, documento_id, usuario_id=usuario_id
    )


def remover(
    client: Any,
    org_id: UUID,
    empresa_id: UUID,
    documento_id: UUID,
    *,
    motivo: str,
    usuario_id: Optional[UUID] = None,
) -> None:
    """Soft delete. `empresas.dados_documento_id` (075-shaped FK) is left
    pointing at the soft-deleted row if it names this document — same
    reasoning `imovel_hub.documentos_service.remover` gives for `numero_
    matricula_documento_id`: the document is evidence, not the fact itself,
    and removing evidence does not un-know a fact nobody asked to unlearn."""
    STORE.remover(
        client, org_id, empresa_id, documento_id, motivo=motivo, usuario_id=usuario_id
    )


def listar_acessos(client: Any, org_id: UUID, empresa_id: UUID, documento_id: UUID) -> dict:
    dados_service.ensure_empresa(client, org_id, empresa_id)
    STORE.exigir(client, org_id, empresa_id, documento_id)
    rows = STORE.listar_acessos(client, org_id, documento_id)
    return {"items": rows, "total": len(rows)}


def descartar_extracao(
    client: Any, org_id: UUID, empresa_id: UUID, documento_id: UUID, *, usuario_id: Optional[UUID]
) -> dict:
    """Turn the reading down — kept on the document (`extracao_dados`
    survives), just stops being offered as machine-pending. Mirrors
    `identidade_extracao_service.descartar_sugestao`'s posture."""
    documento = STORE.exigir(client, org_id, empresa_id, documento_id)
    from datetime import datetime, timezone

    patch = {
        "extracao_descartada_em": datetime.now(timezone.utc).isoformat(),
        "extracao_descartada_por": str(usuario_id) if usuario_id else None,
    }
    _t(client, TABLE).update(patch).eq("id", str(documento_id)).execute()
    return {**documento, **patch}


__all__ = [
    "ALLOWED_MIME_TYPES",
    "MAX_UPLOAD_BYTES",
    "STORE",
    "TABLE",
    "TIPOS_DOCUMENTO",
    "descartar_extracao",
    "deve_extrair",
    "documento_pendente_ou_processando",
    "listar",
    "listar_acessos",
    "remover",
    "upload",
    "url_do_documento",
    "validar_upload",
]
