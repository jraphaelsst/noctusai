"""Operator-authored checklist lines — the per-client half of the card.

The bodies are the seed's `noctusai_lib.domain.card_hub.checklist_extras`,
lifted out of THIS file as a MOVE (wave A, 2026-09-22). The functions below
keep their historical `(client, ...)` signatures as thin shims over it, bound
to social-wiring's `CardHubConfig` (`app.modules.card_hub.config.CARD_HUB`);
`TipoIncompativel` / `concluido_de` / `TIPOS_VALIDOS` ARE the seed's (one
class, so the router's `except` matches whichever layer raised it). The rules
below are the seed's, stated here in this product's words.

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
---------------------------------------------
`documento_checklist_service` owns the MANDATORY list: eight items identical
for every client, defined in code so adding a ninth is a deploy rather than a
per-client backfill. This module owns the other half — a line an operator typed
for THIS person and nobody else ("condomínio: enviar convenção", "escritura
anterior"). Same surface on screen, two homes, because the two are different
kinds of fact: one is a decision about every client, the other is a note about
one.

🔴 `concluido` IS DERIVED, NEVER STORED
---------------------------------------
Migration 068's argument, applied to this table rather than re-litigated. A
`texto` line is done when it has text; an `arquivo` line is done when it holds a
live document. Both facts already live in the row, so a stored `concluido` could
only agree with them or be silently wrong — and here there is a concrete writer
that would make it wrong with nobody watching: the retention sweep
(`documentos_service.run_retention_sweep`) soft-deletes documents on a schedule
and knows nothing about this table. A stored tick would outlive the file it
asserts. Derivation has no such interval.

🔴 DELETING THE FILE KEEPS THE LINE
-----------------------------------
The product rule, stated here because the code has to be read as meaning it and
not as an oversight: `remover_documento` soft-deletes the `cliente_documentos`
row, NULLs `documento_id`, and leaves the extra standing — empty, underived, and
ready for a fresh upload. The line is the REQUEST; the document is only its
current answer. A cascade that removed the line along with the file would delete
the request because someone sent the wrong scan.

Uploading onto a line that already holds a document REPLACES it, by the same
reading: the request did not change, its answer did. The displaced document is
soft-deleted (never orphaned), so it stays in the Documentos tab's history and
its access log survives.

🔴 A CROSSED WRITE IS A 422, NOT A SILENT IGNORE
------------------------------------------------
A `texto` line refuses a document and an `arquivo` line refuses `valor_texto`.
Both are caller bugs — `tipo` is chosen at creation and returned on every read —
and a 200 that quietly dropped the value would show as a line that will not
tick, with nothing anywhere saying why.

Storage, LGPD category, retention and the access log are NOT re-implemented
here: `documentos_service.upload_documento` / `delete_documento` are the one
path a file enters or leaves this product by, and a second one would be a second
place for the retention policy to be wrong.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from noctusai_lib.domain.card_hub import checklist_extras as seed_extras
from noctusai_lib.domain.card_hub.checklist_extras import (
    TIPOS_VALIDOS,
    TipoIncompativel,
    concluido_de,
)
from noctusai_lib.integrations.storage import StorageBackend

from app.modules.card_hub.deps import card_hub_config

TABLE = "cliente_checklist_extras"

#: The `tipo_documento` an extra's upload is filed under
#: (`CARD_HUB.checklist_extra_tipo_documento` is built from this).
#:
#: An operator-authored line has no document TAXONOMY behind it by definition —
#: whatever they are asking for is the thing the catalogue did not anticipate.
#: `outro` is the catalogue's own answer for that (migration 057 seeds it
#: `ativo = true`, categoria `nao_classificado`, 365-day retention), so the
#: upload goes through the same allow-list and the same retention policy every
#: other document does. Inventing a per-extra type would mean a row in
#: `cliente_documento_tipos` with no retention anybody had decided on, which is
#: precisely the hardcoded-`if` that migration exists to prevent.
TIPO_DOCUMENTO = "outro"


def listar(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    return seed_extras.listar(card_hub_config(), client, org_id, cliente_id)


def criar(client: Any, org_id: UUID, cliente_id: UUID, *, label: str, tipo: str) -> dict:
    return seed_extras.criar(card_hub_config(), client, org_id, cliente_id, label=label, tipo=tipo)


def atualizar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    extra_id: UUID,
    *,
    label: Optional[str] = ...,
    valor_texto: Optional[str] = ...,
    ordem: Optional[int] = ...,
) -> dict:
    """`...` sentinels an unset field — only what the PATCH carried is written."""
    return seed_extras.atualizar(
        card_hub_config(), client, org_id, cliente_id, extra_id,
        label=label, valor_texto=valor_texto, ordem=ordem,
    )


def remover(client: Any, org_id: UUID, cliente_id: UUID, extra_id: UUID) -> None:
    seed_extras.remover(card_hub_config(), client, org_id, cliente_id, extra_id)


async def anexar_documento(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    extra_id: UUID,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    enviado_por: Optional[UUID] = None,
) -> dict:
    return await seed_extras.anexar_documento(
        card_hub_config(), client, storage, org_id, cliente_id, extra_id,
        filename=filename, content_type=content_type, data=data, enviado_por=enviado_por,
    )


async def remover_documento(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    extra_id: UUID,
    *,
    usuario_id: Optional[UUID] = None,
) -> None:
    await seed_extras.remover_documento(
        card_hub_config(), client, storage, org_id, cliente_id, extra_id, usuario_id=usuario_id,
    )


__all__ = [
    "TABLE",
    "TIPOS_VALIDOS",
    "TIPO_DOCUMENTO",
    "TipoIncompativel",
    "anexar_documento",
    "atualizar",
    "concluido_de",
    "criar",
    "listar",
    "remover",
    "remover_documento",
]
