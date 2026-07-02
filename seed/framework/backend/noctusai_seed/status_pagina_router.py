"""Status-Páginas standard router — product-global page-visibility management.

Each product schema ships a ``status_pagina`` table that gates nav visibility:

- ``producao``        — visible to every user
- ``desenvolvimento`` — visible ONLY to dev / owner roles
- ``desativado``      — hidden from everyone

This router lets platform-admin / owner / admin / dev roles LIST every
page-status row and CHANGE a row's status. Scope is deliberately
change-status-only — no create / no delete (the rows are seeded per product
migration).

Product-global: ``status_pagina`` carries no ``org_id`` — the table is the same
for every org in the product. Reads + writes use the **admin (service-role)
client** because the RLS only exposes ``producao`` rows to normal reads and
ships no UPDATE policy; an admin managing visibility must see + mutate every
row (incl. ``desenvolvimento`` / ``desativado``).

The admin client is already schema-scoped
(``DatabaseModule.get_admin_client`` → ``ClientOptions(schema=...)``), so the
table name is unqualified — matching ``page_status.get_visible_pages`` and
every product admin router (e.g. erp ``site_imoveis``).

Opt in via ``standard_routers=["status_paginas", ...]`` on
``create_product_app``. Registered in ``_STANDARD_ROUTERS`` under the key
``"status_paginas"``.

Defensive-optional columns: ``tipo_pagina`` + ``updated_at`` exist on some
product schemas (erp) but not others (social-wiring / seed). The response model
reads them via ``row.get(...)`` so the shape is uniform regardless.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.primitives.roles import ADMIN_ROLES, DEV_ROLES

logger = logging.getLogger(__name__)

# Roles allowed to manage page visibility: the SSO super-role plus the org
# roles that administer (ADMIN_ROLES) or see in-dev pages (DEV_ROLES). Derived
# from the canonical primitives so the gate can't drift from the role sets.
# Resolves to ("platform_admin", "owner", "admin", "dev").
_MANAGE_ROLES: tuple[str, ...] = ("platform_admin", *dict.fromkeys(ADMIN_ROLES + DEV_ROLES))

# The three canonical page-status values (see noctusai_lib.domain.page_status).
_VALID_STATUSES: tuple[str, ...] = ("producao", "desenvolvimento", "desativado")


class StatusPaginaOut(StrictHttpModel):
    """Response shape for a ``status_pagina`` row.

    ``tipo_pagina`` / ``updated_at`` are defensive-optional (present on erp,
    absent on social-wiring / seed) — read via ``row.get(...)`` in ``_to_out``.
    """

    id: str
    nome_pagina: str
    status: str
    descricao: Optional[str] = None
    tipo_pagina: Optional[str] = None
    updated_at: Optional[datetime] = None


class StatusPaginaUpdate(StrictHttpModel):
    """PATCH body — change the status only.

    ``StrictHttpModel`` (``extra='forbid'``) 422s any unknown key; the value is
    validated against ``_VALID_STATUSES`` in the handler (400 on a bad value).
    """

    status: str


def _to_out(row: dict) -> StatusPaginaOut:
    return StatusPaginaOut(
        id=str(row["id"]),
        nome_pagina=row["nome_pagina"],
        status=row["status"],
        descricao=row.get("descricao"),
        tipo_pagina=row.get("tipo_pagina"),
        updated_at=row.get("updated_at"),
    )


def _create_status_pagina_router(deps, settings, product_name: str) -> APIRouter:
    router = APIRouter(prefix="/api/status-paginas", tags=["Status Páginas"])

    async def _require_manage_role(authorization: Optional[str]):
        user, _ = await deps.get_current_user(authorization)
        role = deps.get_user_role(user)
        if role not in _MANAGE_ROLES:
            raise HTTPException(
                status_code=403,
                detail="Sem permissão para gerenciar status de páginas",
            )
        return user

    @router.get("", response_model=list[StatusPaginaOut])
    async def listar(authorization: Optional[str] = Header(None)):
        await _require_manage_role(authorization)
        admin = deps.get_admin_client()
        result = admin.table("status_pagina").select("*").order("nome_pagina").execute()
        return [_to_out(r) for r in (result.data or [])]

    @router.patch("/{status_pagina_id}", response_model=StatusPaginaOut)
    async def atualizar_status(
        status_pagina_id: str,
        body: StatusPaginaUpdate,
        authorization: Optional[str] = Header(None),
    ):
        await _require_manage_role(authorization)
        if body.status not in _VALID_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"status inválido: {body.status!r}. Válidos: {list(_VALID_STATUSES)}",
            )
        admin = deps.get_admin_client()
        table = admin.table("status_pagina")
        existing = table.select("*").eq("id", status_pagina_id).execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Página não encontrada")
        current = existing.data[0]
        payload: dict = {"status": body.status}
        # `updated_at` is defensive-optional: bump it ONLY when the column
        # exists (erp has it; social-wiring / seed don't → including it would
        # PGRST204 "column not found"). We know the column set from the row we
        # just read — no blind try/except fallback.
        if "updated_at" in current:
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated = table.update(payload).eq("id", status_pagina_id).execute()
        row = (updated.data or [None])[0] or {**current, **payload}
        return _to_out(row)

    return router
