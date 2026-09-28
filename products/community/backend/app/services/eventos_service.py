"""Relationship timeline — `community.membro_eventos` (migration 013).

One writer for every slice (CONTRACT.md §Timeline): status changes, plan
changes, payments, subscription lifecycle, notes, contacts, access and
grupoterapia all land here, so the CRM detail shows one ordered history.

Append-only by construction — the table has no UPDATE/DELETE policy.
"""
from __future__ import annotations

import logging
from typing import Any, Literal
from uuid import UUID

logger = logging.getLogger(__name__)

TipoEvento = Literal[
    "status", "plano", "pagamento", "assinatura", "nota", "contato",
    "acesso", "grupoterapia", "sistema",
]

_TABLE = "membro_eventos"


def registrar_evento(
    client: Any,
    *,
    org_id: UUID | str,
    membro_id: UUID | str,
    tipo: TipoEvento,
    descricao: str,
    dados: dict[str, Any] | None = None,
    autor_id: UUID | str | None = None,
    id: UUID | str | None = None,
) -> dict[str, Any]:
    """Append one timeline event and return the written row.

    `client` is whichever client the caller already holds: the user's
    (staff writes — RLS checks `eh_equipe()`) or the service-role client
    (webhooks, the billing sweep, the public signup). `autor_id` is None
    for system-originated events.

    `id` is OPTIONAL — the table's own `DEFAULT gen_random_uuid()`
    (migration 013) fills it server-side when omitted, same as every
    other write here. Pass it explicitly ONLY when the caller must echo
    a UUID-typed id back in an HTTP response written in the SAME call
    (e.g. `POST /api/membros/{id}/eventos` — contract §Identity): the
    in-repo `MockSupabaseClient` fills a MISSING id with a `mock-<table>-
    <n>` placeholder (never a real UUID, since it has no DB default to
    simulate), which a strict `id: UUID` response model rejects. A real
    Postgres write behaves identically either way (`ON CONFLICT` never
    applies here — this is a plain append).

    Raises whatever the client raises: a lost timeline write is a lost
    audit record, so it is never swallowed here. A caller that must not
    fail its primary action on a timeline error decides that explicitly.
    """
    row: dict[str, Any] = {
        "org_id": str(org_id),
        "membro_id": str(membro_id),
        "tipo": tipo,
        "descricao": descricao[:2000],
        "dados": dados or {},
        "autor_id": str(autor_id) if autor_id else None,
    }
    if id is not None:
        row["id"] = str(id)
    written = client.table(_TABLE).insert(row).execute().data or []
    return written[0] if written else row
