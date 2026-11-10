"""Quem recebe os avisos do dono — CRUD over core `public.notification_owner_recipients` (migration 118).

The numbers are what the seed `notify_owner` sends to over the NoctusAI line. Every write is attributed to the admin
(`alterado_por` on insert/update, the `remover_destinatario_dono` RPC for removal); a SECURITY DEFINER trigger appends
the matching `notification_owner_recipient_events` row in the same transaction (adicionado / ativado / desativado /
renomeado / removido). The number is immutable. Phone numbers are shown to the admin and stored, but
never logged.
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Optional
from urllib.parse import urlparse

from noctusai_lib.primitives.phone import normalize_phone
from noctusai_lib.primitives.timeutil import now_utc

TABLE = "notification_owner_recipients"
_COLUMNS = "id, numero, nome, ativo, created_at"
_UNIQUE_HINTS = ("duplicate key", "unique", "23505", "notification_owner_recipients_numero_key")

OWNER_LINE_URL_ENV = "NOC_OWNER_LINE_WAHA_URL"


class InvalidNumber(ValueError):
    """The number is not a phone number we can normalize to E.164."""


class DuplicateNumber(ValueError):
    """The number is already a recipient."""


class ActorRequired(ValueError):
    """Every write is attributed to an admin (the DB refuses an event with no actor)."""


class RecipientNotFound(LookupError):
    """No recipient with that id."""


def _public(row: dict) -> dict:
    return {k: row.get(k) for k in ("id", "numero", "nome", "ativo", "created_at")}


def list_recipients(db: Any) -> list[dict]:
    rows = db.table(TABLE).select(_COLUMNS).order("created_at").execute().data or []
    return [_public(r) for r in rows]


def _need_actor(user_id: Optional[str]) -> str:
    if not user_id:
        raise ActorRequired("ator_desconhecido")
    return user_id


def add_recipient(db: Any, *, numero: str, nome: Optional[str], user_id: Optional[str]) -> dict:
    user_id = _need_actor(user_id)
    canonical = normalize_phone(numero)
    if not canonical:
        raise InvalidNumber("numero_invalido")
    existing = db.table(TABLE).select("id").eq("numero", canonical).execute().data or []
    if existing:
        raise DuplicateNumber("numero_duplicado")
    try:
        rows = db.table(TABLE).insert(
            {"id": str(uuid.uuid4()), "numero": canonical, "ativo": True, "alterado_em": now_utc().isoformat(), "nome": (nome or "").strip() or None, "alterado_por": user_id}
        ).execute().data or []
    except Exception as exc:  # a concurrent insert of the same number hits the UNIQUE constraint
        if any(h in str(exc).lower() for h in _UNIQUE_HINTS):
            raise DuplicateNumber("numero_duplicado") from exc
        raise
    return _public(rows[0])


def update_recipient(db: Any, *, recipient_id: str, patch: dict, user_id: Optional[str]) -> dict:
    """`patch` carries only the fields the caller sent (`ativo`, `nome`); the number is immutable."""
    user_id = _need_actor(user_id)
    values: dict = {}
    if "ativo" in patch and patch["ativo"] is not None:
        values["ativo"] = bool(patch["ativo"])
    if "nome" in patch:
        values["nome"] = (patch["nome"] or "").strip() or None
    if not values:
        rows = db.table(TABLE).select(_COLUMNS).eq("id", recipient_id).execute().data or []
    else:
        values["alterado_por"] = user_id
        values["alterado_em"] = now_utc().isoformat()
        rows = db.table(TABLE).update(values).eq("id", recipient_id).execute().data or []
    if not rows:
        raise RecipientNotFound(recipient_id)
    return _public(rows[0])


def delete_recipient(db: Any, *, recipient_id: str, user_id: Optional[str]) -> None:
    """One RPC = one transaction: DELETE ... RETURNING with the actor passed to the event trigger."""
    user_id = _need_actor(user_id)
    deleted = db.rpc("remover_destinatario_dono", {"p_id": recipient_id, "p_ator": user_id}).execute().data
    if not deleted:
        raise RecipientNotFound(recipient_id)


def owner_line_status() -> dict:
    """Is the NoctusAI line configured here? Derived from env only — never a call to the instance."""
    url = (os.environ.get(OWNER_LINE_URL_ENV) or "").strip()
    if not url:
        return {"configurada": False, "instancia": None}
    host = urlparse(url if "://" in url else f"//{url}").netloc
    return {"configurada": True, "instancia": host or None}


__all__ = [
    "ActorRequired", "DuplicateNumber", "InvalidNumber", "RecipientNotFound", "add_recipient", "delete_recipient",
    "list_recipients", "owner_line_status", "update_recipient",
]
