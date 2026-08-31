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
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.storage import StorageBackend

from app.modules.imovel_hub import dados_service
from app.modules.imovel_hub.deps import BUCKET
from app.services import table_reads
from app.services.documento_store import DocumentoStore, documento_base

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

#: 🔴 `acessos_table=None` is an EXPLICIT claim, not a default this fell into:
#: a matrícula is a public registry document about a PROPERTY, so there is no
#: personal-data access to log. `atendimento_documentos` sets it, because an
#: imposto de renda is a very different thing. See the module docstring.
STORE = DocumentoStore(
    table=TABLE,
    owner_col="codigo",
    prefixo="imoveis",
    bucket=BUCKET,
    tipos=TIPOS_DOCUMENTO,
    max_bytes=MAX_UPLOAD_BYTES,
    mimes=ALLOWED_MIME_TYPES,
    acessos_table=None,
)


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _documento_out(row: dict, resolved: dict) -> dict:
    return {
        **documento_base(row, resolved),
        "codigo": row["codigo"],
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
    rows = STORE.listar_linhas(client, org_id, codigo)
    resolved = table_reads.resolve_actors(
        {r["enviado_por"] for r in rows if r.get("enviado_por")}
    )
    items = [_documento_out(r, resolved) for r in rows]
    return {"items": items, "total": len(items)}


def validar_upload(
    *,
    tipo_documento: str,
    content_type: str,
    tamanho_bytes: int,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> None:
    """Refuse an upload we will not store, naming the limit it hit.

    Thin alias over the store's own validator, kept so this module's tests and
    callers read in its own vocabulary. `max_bytes` is a parameter so no test
    has to monkeypatch the constant — see `DocumentoStore.validar`.
    """
    STORE.validar(
        tipo_documento=tipo_documento,
        content_type=content_type,
        tamanho_bytes=tamanho_bytes,
        max_bytes=max_bytes,
    )


def deve_extrair(tipo_documento: str) -> bool:
    return tipo_documento in TIPOS_EXTRAIVEIS


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
    row = await STORE.guardar(
        client,
        storage,
        org_id,
        codigo,
        filename=filename,
        content_type=content_type,
        data=data,
        tipo_documento=tipo_documento,
        enviado_por=enviado_por,
        extra={
            # Queued the moment it lands. `pendente` is set HERE rather than
            # by the background job so a job that never starts — worker died,
            # process recycled mid-request — is visibly waiting instead of
            # invisibly lost, and the sweeper can find it.
            "extracao_status": "pendente" if deve_extrair(tipo_documento) else None,
            "extracao_tentativas": 0,
        },
    )
    resolved = table_reads.resolve_actors(
        {row["enviado_por"]} if row["enviado_por"] else set()
    )
    return _documento_out(row, resolved)


async def url_do_documento(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    codigo: str,
    documento_id: UUID,
) -> dict:
    """A short-TTL signed URL. Minted per request, never stored.

    No access-log append — the store is constructed with `acessos_table=None`
    because a property's registry document is not personal data. See the
    module docstring.
    """
    return await STORE.url(client, storage, org_id, codigo, documento_id)


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
    about the property that happens to have been sourced here; the document is
    evidence. Removing the evidence does not un-know the fact, and silently
    blanking a field the user did not ask to blank is the kind of cascade that
    loses data nobody agreed to lose.

    `numero_matricula_documento_id` keeps pointing at the soft-deleted row, so
    the provenance stays readable.
    """
    STORE.remover(client, org_id, codigo, documento_id, motivo=motivo)


__all__ = [
    "ALLOWED_MIME_TYPES",
    "MAX_UPLOAD_BYTES",
    "TABLE",
    "TIPOS_DOCUMENTO",
    "TIPOS_EXTRAIVEIS",
    "deve_extrair",
    "validar_upload",
    "listar",
    "remover",
    "upload",
    "url_do_documento",
]
