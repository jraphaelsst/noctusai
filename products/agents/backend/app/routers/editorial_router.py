"""``/api/studio/editorial`` — the seed editorial workflow, mounted in agents
(project ``seed-editorial-workflow``, slice E5).

One generic queue/detail/versions/transitions/diff surface for every editorial
item in the org (today: ``kind="knowledge_document"``, i.e. documents of a
GOVERNED knowledge collection). Everything is the seed's
``noctusai_lib.domain.editorial.editorial_router``; this module only supplies
the product seams:

* auth — ``require_admin`` (owner/admin of the org; the admin MFA gate of
  ``platform-admin-mfa`` already sits inside that factory, policy per org);
* org — the router needs a VERIFIED org membership on top of the user-global
  ``editorial:*`` grants (``public.user_permission_grants`` has no org
  dimension): ``require_admin`` resolves the caller's org membership, and the
  store filters every read/write by that org;
* grants — derived server-side from the permissions organ against core's
  ``public.user_permission_grants`` — never from the request body.

The seams are injectable through :data:`editorial_deps` (tests set a Fake store
and a Fake grant repository; the production default is built lazily).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.config import settings
from app.dependencies import coerce_org_uuid, require_admin
from app.responses import success_response
from noctusai_lib.api.auth.session import AuthContext
from noctusai_lib.domain.editorial import EditorialContext, EditorialStore, editorial_router
from noctusai_lib.domain.permissions import PermissionGrantRepository

__all__ = ["EditorialDeps", "editorial_deps", "router"]

_SCHEMA = "agents"


@dataclass
class EditorialDeps:
    """Request-time seams. ``None`` ⇒ the production implementation, built on
    first use (a Fake without a service-role key, like every agents store)."""

    store: EditorialStore | None = None
    permissions: PermissionGrantRepository | None = None

    def get_store(self) -> EditorialStore:
        if self.store is None:
            from noctusai_lib.domain.editorial import make_editorial_store

            if not getattr(settings, "supabase_service_role_key", None):
                self.store = make_editorial_store(_SCHEMA, use_fake=True)
            else:
                from app.database import get_admin_client

                self.store = make_editorial_store(_SCHEMA, client=get_admin_client())
        return self.store

    def get_permissions(self) -> PermissionGrantRepository:
        if self.permissions is None:
            from noctusai_lib.domain.permissions import make_permission_grant_repository

            if not getattr(settings, "supabase_service_role_key", None):
                self.permissions = make_permission_grant_repository(use_fake=True)
            else:
                from app.dependencies import get_core_client

                self.permissions = make_permission_grant_repository(supabase_client=get_core_client())
        return self.permissions


editorial_deps = EditorialDeps()


def _resolve_context(ctx: AuthContext) -> EditorialContext:
    user_id = UUID(str(ctx.user_id)) if ctx.user_id else None
    return EditorialContext(org_id=coerce_org_uuid(ctx.org_id), user_id=user_id)


router = editorial_router(
    auth_dependency=require_admin,
    resolve_context=_resolve_context,
    get_store=lambda: editorial_deps.get_store(),
    get_permission_repo=lambda: editorial_deps.get_permissions(),
    success_response=success_response,
    prefix="/api/studio/editorial",
    tags=["studio-editorial"],
)
