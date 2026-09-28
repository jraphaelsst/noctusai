"""`GET /api/eu` — contract §Identity, slice BE-A.

Answers for ANY authenticated org user (staff or membro) — role routing
on the frontend reads this to decide staff-nav vs portal-nav.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.services.acesso_service import nivel_grupoterapia

_MEMBROS_TABLE = "membros"
_PLANOS_TABLE = "planos"


def build_eu(client: Any, *, user: Any, org_id: UUID, papel: str) -> dict:
    """Assemble the `GET /api/eu` response body.

    `client` is the ADMIN (service-role) client — same rationale as the
    member portal's own reads (contract §Member portal / §Grupoterapia
    "read with the service-role client"): a membro's own plan may not
    satisfy the member-self RLS predicates (`planos_select_ativos_membro`
    requires `ativo`), and this endpoint must answer correctly regardless.
    Every read below is explicitly org- and user-scoped in code, so
    bypassing RLS here never leaks another org's or another member's row.

    `nome` mirrors `user_metadata["nome"]` — the SAME field every
    identity write in this product (and the seed's own `team` standard
    router, via `sync_org_metadata`/`provision_invited_identity`)
    maintains — falling back to the email's local part for the rare user
    that somehow has neither.
    """
    metadata = getattr(user, "user_metadata", None) or {}
    email = getattr(user, "email", "") or ""
    nome = metadata.get("nome") or (email.split("@", 1)[0] if email else "")

    membro_out: dict | None = None
    if papel == "membro":
        rows = (
            client.table(_MEMBROS_TABLE)
            .select("*")
            .eq("org_id", str(org_id))
            .eq("user_id", str(getattr(user, "id", "")))
            .limit(1)
            .execute()
        ).data or []
        if rows:
            membro = rows[0]
            plano = None
            if membro.get("plano_id"):
                plano = (
                    client.table(_PLANOS_TABLE)
                    .select("*")
                    .eq("org_id", str(org_id))
                    .eq("id", str(membro["plano_id"]))
                    .maybe_single()
                    .execute()
                ).data
            membro_out = {
                "id": membro["id"],
                "status": membro["status"],
                "plano_id": membro.get("plano_id"),
                "plano_nome": plano.get("nome") if plano else None,
                "nivel_grupoterapia": nivel_grupoterapia(membro, plano),
            }

    return {"papel": papel, "nome": nome, "email": email, "membro": membro_out}
