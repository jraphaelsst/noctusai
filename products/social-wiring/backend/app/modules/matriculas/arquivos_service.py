"""The retained PDF for an UNLINKED matrícula upload (migration 135).

A matrícula uploaded WITH a `codigo` keeps its bytes as the imóvel's
`imovel_documentos` row — `imovel_hub.documentos_service` already owns that.
Before this module, an upload WITHOUT a `codigo` (the 092 "arbitrary PDF,
attached to nothing" shape) discarded the bytes the moment transcription
finished reading them: `service.MENSAGEM_ORFA` says so outright, and a
transcription that predates this module can genuinely never be re-run or
audited against its source — the problem migration 135 exists to close.

WHY A NEW TABLE, NOT A REUSE OF `imovel_documentos`
-----------------------------------------------------
`imovel_documentos.STORE` is owned by an imóvel (`owner_col="codigo"`,
`dados_service.ensure_imovel` gates every write) — there is no imóvel to
attach to here BY DEFINITION. Migration 092's own header already drew this
line: "NOT the same table as `imovel_documentos` [...] Same domain word,
different workflow." This module is the retention half that workflow was
always missing, kept as its own table for the same reason.

STILL THE SAME MECHANISM
-------------------------
`DocumentoStore` (`app/services/documento_store.py`) owns validate / put /
insert / sign / soft-delete / retention for every kept-document surface on
this product — this is the fourth configuration of it, not a hand-rolled
fifth storage path. `owner_col="org_id"` is a deliberate choice, not a
placeholder: there is no owner narrower than the org for a file that has not
(yet, or ever) been linked to an imóvel.

LGPD access logging does NOT go through `DocumentoStore`'s own
`acessos_table` mechanism — that always logs against `self.table`'s OWN row
id via a `documento_id` column, and `imovel_documento_acessos.documento_id`
is FK'd to `imovel_documentos(id)` specifically, so a row id from THIS table
would violate that foreign key. Migration 111 already extended that same
access-log table with an `extracao_id` column for exactly this "no
`imovel_documentos` row to log against" shape — `router.py` logs a
view/download of the retained PDF against the EXTRACTION id via
`documento_store.log_acesso_extracao`, the same helper `estrutura_service.
log_leitura_texto` uses for a text read. No second access-log table.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.storage import StorageBackend

from app.modules.imovel_hub.deps import BUCKET
from app.services import documento_retencao
from app.services.documento_store import DocumentoStore, today

TABLE = "matricula_extracao_arquivos"

#: One value today — mirrors `atendimento_contrato_versoes`' `TIPO_VERSAO`
#: shape (a 1-tuple rather than a bare constant, so `STORE.validar` stays the
#: single place this surface's type allow-list lives). The migration's own
#: CHECK enforces the same thing independently of this ever drifting.
TIPO_DOCUMENTO = "matricula"

#: Only a PDF is ever transcribed (`service.MIME_TRANSCREVIVEL` /
#: `estrutura_service.MIME_TRANSCREVIVEL`) — a retained source that is not a
#: PDF could never feed a re-transcription, so there is nothing to retain.
ALLOWED_MIME_TYPES = frozenset({"application/pdf"})

#: Matches the router's `MAX_FILE_SIZE` ceiling for `/extrair` — the same
#: bytes, the same limit, checked twice for the same reason
#: `imovel_hub.documentos_service.validar_upload` is: no test has to
#: monkeypatch a module constant to exercise the limit.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

#: 🔴 `acessos_table=None` — NOT a claim that this content is not personal
#: data (it is: a matrícula names owners, CPFs, estado civil). It means this
#: `DocumentoStore` does not own the logging for it; see the module docstring
#: for where the log actually goes (`documento_store.log_acesso_extracao`,
#: keyed to the extraction rather than to this table's own row id).
STORE = DocumentoStore(
    table=TABLE,
    owner_col="org_id",
    prefixo="matriculas",
    bucket=BUCKET,
    tipos=(TIPO_DOCUMENTO,),
    max_bytes=MAX_UPLOAD_BYTES,
    mimes=ALLOWED_MIME_TYPES,
    acessos_table=None,
)


async def guardar(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    enviado_por: Optional[UUID],
) -> dict:
    """Retain one standalone matrícula upload's bytes. Returns the row.

    Stamps `retencao_ate` from the SAME `superficie="imovel"`,
    `tipo_documento="matricula"` policy `imovel_documentos.upload` reads
    (migration 111 seeded one platform row for it) — both tables hold "the
    matrícula PDF"; they differ only in which one currently has it.
    """
    dias = documento_retencao.dias_para(client, org_id, "imovel", TIPO_DOCUMENTO)
    retencao_ate = (today() + timedelta(days=dias)).isoformat() if dias else None
    return await STORE.guardar(
        client,
        storage,
        org_id,
        org_id,
        filename=filename,
        content_type=content_type,
        data=data,
        tipo_documento=TIPO_DOCUMENTO,
        enviado_por=enviado_por,
        extra={"retencao_ate": retencao_ate},
    )


def exigir(client: Any, org_id: UUID, arquivo_id: UUID) -> dict:
    """The retained-file row, 404 if missing/soft-deleted/wrong org."""
    return STORE.exigir(client, org_id, org_id, arquivo_id)


async def url(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    arquivo_id: UUID,
) -> dict:
    """A short-TTL signed URL for the retained PDF. Minted per request, never
    stored. Caller logs the LGPD access — see the module docstring for why
    this function does not (it has no `acessos_table` to log through)."""
    return await STORE.url(client, storage, org_id, org_id, arquivo_id)


__all__ = [
    "ALLOWED_MIME_TYPES",
    "MAX_UPLOAD_BYTES",
    "STORE",
    "TABLE",
    "TIPO_DOCUMENTO",
    "exigir",
    "guardar",
    "url",
]
