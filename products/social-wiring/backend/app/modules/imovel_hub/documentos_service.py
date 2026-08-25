"""Imóvel documents — the matrícula and the guia de IPTU (migration 075).

🔴 WHY THIS IS **NOT** A COPY OF `card_hub/documentos_service.py`
-----------------------------------------------------------------
The two look alike (upload → storage → row → signed URL → soft delete) and
they are deliberately not shared, because the half that dominates that file
does not apply here at all:

- **No access log.** Every read of a client document's CONTENT appends to
  `cliente_documento_acessos`, because an RG is personal data about a
  natural person and who looked at it is auditable. A matrícula is a PUBLIC
  registry document about a property. Logging it would imply an LGPD posture
  this data does not have, and would bury the real log in noise.
- **No retention clock, no LGPD category.** `cliente_documento_tipos` drives
  `retencao_ate` from a per-type `retencao_dias`. A property's registry
  document has no such clock — it is evidence for a transaction, kept as
  long as the transaction record is.
- **No `ativo` allow-list table.** The client-side type list is DATA so that
  enabling a withheld, sensitive type is a data change rather than a deploy.
  There is nothing sensitive to withhold here, so the type list is code
  (`TIPOS_DOCUMENTO`) — which also means adding "certidão negativa" is a
  tuple entry, not a seeded row.

What IS shared is the part that genuinely is one idea — the org-scoped paged
read and the actor-name resolution — via `app.services.table_reads`.

The size/mime limits ARE duplicated as values, and that is intentional: they
are policy for a DIFFERENT surface. A matrícula is a multi-page scanned PDF
and routinely larger than a photo of an ID, so the two ceilings must be free
to diverge without one silently dragging the other.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.imovel_hub import dados_service
from app.modules.imovel_hub.deps import BUCKET
from app.services import table_reads

logger = logging.getLogger(__name__)

TABLE = "imovel_documentos"

#: The document types an imóvel accepts. Code-owned, per migration 075's note
#: — the set will grow (certidão negativa, habite-se, convenção de condomínio)
#: and a CHECK constraint would make each addition a migration.
TIPOS_DOCUMENTO: tuple[str, ...] = ("matricula", "guia_iptu")

#: Which types are worth reading a número de matrícula off. Only the matrícula
#: itself — a guia de IPTU carries an inscrição imobiliária, a DIFFERENT
#: number that would be wrong in this column.
TIPOS_EXTRAIVEIS = frozenset({"matricula"})

#: 40 MB. Higher than the client-document ceiling (25 MB) on purpose: a
#: certidão de matrícula with decades of averbações is routinely 20-40 pages
#: of scan, where an RG is one photo.
MAX_UPLOAD_BYTES = 40 * 1024 * 1024
ALLOWED_MIME_TYPES = frozenset(
    {"application/pdf", "image/jpeg", "image/png", "image/webp"}
)

_SIGNED_URL_TTL_SECONDS = 300


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _format_bytes_human(n: int) -> str:
    """Human-readable byte count for a user-facing limit message.

    Never integer-divides to a misleading "0MB" — see
    `card_hub.documentos_service._format_bytes_human` for the incident that
    rule came from.
    """
    mb = n / (1024 * 1024)
    if mb >= 1:
        return f"{mb:.1f}MB"
    return f"{n / 1024:.0f}KB"


def _documento_out(row: dict, resolved: dict) -> dict:
    return {
        "id": row["id"],
        "codigo": row["codigo"],
        "nome_original": row["nome_original"],
        "mime_type": row["mime_type"],
        "tamanho_bytes": row["tamanho_bytes"],
        "tipo_documento": row["tipo_documento"],
        "enviado_por": table_reads.actor(resolved, row.get("enviado_por")),
        "created_at": row["created_at"],
        # Extraction state, surfaced so the UI can show "lendo…" / "não
        # encontrei um número" rather than an empty field that looks broken.
        "extracao_status": row.get("extracao_status"),
        "extracao_matricula": row.get("extracao_matricula"),
        "extracao_confianca": row.get("extracao_confianca"),
        "extracao_rotulo": row.get("extracao_rotulo"),
        "extracao_erro": row.get("extracao_erro"),
    }


def listar(client: Any, org_id: UUID, codigo: str) -> dict:
    dados_service.ensure_imovel(client, org_id, codigo)
    rows = table_reads.paged_rows(
        client,
        TABLE,
        org_id,
        eq_filters={"codigo": codigo},
        refine=lambda q: q.is_("deleted_at", "null"),
    )
    resolved = table_reads.resolve_actors(
        {r["enviado_por"] for r in rows if r.get("enviado_por")}
    )
    items = [_documento_out(r, resolved) for r in rows]
    items.sort(key=lambda d: d["created_at"], reverse=True)
    return {"items": items, "total": len(items)}


async def upload(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    codigo: str,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    tipo_documento: str,
    enviado_por: Optional[UUID],
) -> dict:
    dados_service.ensure_imovel(client, org_id, codigo)

    if tipo_documento not in TIPOS_DOCUMENTO:
        raise ValidationError_(
            f"tipo_documento desconhecido: {tipo_documento!r}. "
            f"Permitidos: {', '.join(TIPOS_DOCUMENTO)}",
            field="tipo_documento",
        )
    if content_type not in ALLOWED_MIME_TYPES:
        raise ValidationError_(
            f"Tipo de arquivo não permitido: {content_type}. "
            f"Permitidos: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
            field="mime_type",
        )
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValidationError_(
            f"Arquivo excede o limite de {_format_bytes_human(MAX_UPLOAD_BYTES)} "
            f"({_format_bytes_human(len(data))} enviado)",
            field="tamanho_bytes",
        )

    documento_id = uuid4()
    storage_path = f"{org_id}/imoveis/{codigo}/{documento_id}"
    await storage.put(
        bucket=BUCKET,
        key=storage_path,
        data=data,
        content_type=content_type,
        metadata={"nome_original": filename},
    )

    row = {
        "id": str(documento_id),
        "org_id": str(org_id),
        "codigo": codigo,
        "storage_path": storage_path,
        "nome_original": filename,
        "mime_type": content_type,
        "tamanho_bytes": len(data),
        "tipo_documento": tipo_documento,
        "enviado_por": str(enviado_por) if enviado_por else None,
        "deleted_at": None,
        "delete_motivo": None,
        "created_at": _now(),
        # Queued the moment it lands. `pendente` is set HERE rather than by
        # the background job so a job that never starts — worker died,
        # process recycled mid-request — is visibly waiting instead of
        # invisibly lost, and the sweeper can find it.
        "extracao_status": "pendente" if deve_extrair(tipo_documento) else None,
        "extracao_tentativas": 0,
    }
    _t(client, TABLE).insert(row).execute()
    resolved = table_reads.resolve_actors(
        {row["enviado_por"]} if row["enviado_por"] else set()
    )
    return _documento_out(row, resolved)


def deve_extrair(tipo_documento: str) -> bool:
    return tipo_documento in TIPOS_EXTRAIVEIS


def _require_documento(
    client: Any, org_id: UUID, codigo: str, documento_id: UUID
) -> dict:
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("codigo", codigo)
        .eq("id", str(documento_id))
        .execute()
    ).data or []
    if not rows or rows[0].get("deleted_at"):
        raise NotFoundError(TABLE, str(documento_id))
    return rows[0]


async def url_do_documento(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    codigo: str,
    documento_id: UUID,
) -> dict:
    """A short-TTL signed URL. Minted per request, never stored.

    No access-log append — see the module docstring for why a property's
    registry document is not on the same footing as a person's RG.
    """
    documento = _require_documento(client, org_id, codigo, documento_id)
    url = await storage.signed_url(
        bucket=BUCKET,
        key=documento["storage_path"],
        expires_in_seconds=_SIGNED_URL_TTL_SECONDS,
    )
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=_SIGNED_URL_TTL_SECONDS)
    ).isoformat()
    return {"url": url, "expires_at": expires_at}


def remover(
    client: Any,
    org_id: UUID,
    codigo: str,
    documento_id: UUID,
    *,
    motivo: str,
) -> None:
    """Soft delete.

    🔴 The imóvel's `numero_matricula` is deliberately NOT cleared, even when
    the deleted document is the one it was read off. The number is a fact
    about the property that happens to have been sourced here; the document
    is evidence. Removing the evidence does not un-know the fact, and
    silently blanking a field the user did not ask to blank is the kind of
    cascade that loses data nobody agreed to lose.

    `numero_matricula_documento_id` keeps pointing at the soft-deleted row,
    so the provenance stays readable. (Migration 075's FK is ON DELETE SET
    NULL, which only fires on a HARD delete.)
    """
    _require_documento(client, org_id, codigo, documento_id)
    _t(client, TABLE).update(
        {"deleted_at": _now(), "delete_motivo": motivo}
    ).eq("id", str(documento_id)).execute()


__all__ = [
    "ALLOWED_MIME_TYPES",
    "MAX_UPLOAD_BYTES",
    "TABLE",
    "TIPOS_DOCUMENTO",
    "TIPOS_EXTRAIVEIS",
    "deve_extrair",
    "listar",
    "remover",
    "upload",
    "url_do_documento",
]
