"""Biblioteca de virais -- the creator opt-out registry (LGPD Art. 7 IX legitimate interest; Meta
Platform Terms deletion-on-request). Contract: ``geracao-contract.md`` 2.3, 9.3.

A monitored creator who asks not to be monitored is recorded here ONCE, platform-wide (the handle is
UNIQUE and NOT org-scoped: an opt-out binds every org). The registry is a leaf module (no import of
the service) so the request path, the ingestion handler and the admin endpoints share one check. The
purge itself lives next to ``purgar_perfil`` in :mod:`.biblioteca_service`.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

OPTOUTS = "cs_biblioteca_optouts"
ORIGENS = ("email", "dpo", "admin")
CODIGO_OPTOUT = "perfil_optout"
MSG_OPTOUT = "Este perfil pediu para não ser monitorado."

logger = logging.getLogger(__name__)


def get_optout(db: Any, handle: str) -> Optional[dict[str, Any]]:
    """The registry row of an already-NORMALIZED handle, or ``None``."""
    rows = db.table(OPTOUTS).select("*").eq("handle", handle).execute().data
    return rows[0] if rows else None


def esta_bloqueado(db: Any, handle: str) -> bool:
    return get_optout(db, handle) is not None


def listar(db: Any) -> list[dict[str, Any]]:
    return db.table(OPTOUTS).select("*").order("solicitado_em", desc=True).execute().data or []


def registrar(
    db: Any, handle: str, motivo: Optional[str], origem: str, user_id: Optional[str]
) -> tuple[dict[str, Any], bool]:
    """Insert the opt-out unless the handle is already registered. Returns ``(row, criado)``; a repeat
    returns the existing row and ``criado=False`` (idempotent -- the first reason/origin is kept)."""
    existente = get_optout(db, handle)
    if existente is not None:
        return existente, False
    row = {"id": str(uuid.uuid4()), "handle": handle, "motivo": motivo, "origem": origem, "registrado_por": user_id}
    try:
        return db.table(OPTOUTS).insert(row).execute().data[0], True
    except Exception:  # noqa: BLE001 - a concurrent registration won the UNIQUE; re-read, else re-raise
        existente = get_optout(db, handle)
        if existente is None:
            raise
        logger.info("biblioteca: opt-out registrado em paralelo (idempotente)")
        return existente, False


def remover(db: Any, optout_id: str) -> bool:
    """Delete one registry row (unblock). ``False`` when it does not exist."""
    rows = db.table(OPTOUTS).select("id").eq("id", str(optout_id)).execute().data
    if not rows:
        return False
    db.table(OPTOUTS).delete().eq("id", str(optout_id)).execute()
    return True
