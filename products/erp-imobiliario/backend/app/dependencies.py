"""
Shared dependencies for FastAPI routers — seed framework + ERP extensions.

Standard deps (get_current_user, get_user_role, get_user_client, get_admin_client)
come from the seed framework. ERP-specific deps (get_org_id with required param,
log_action) are defined here.

Canonical auth pattern (PF retro §e row 1 — formalized 2026-05-11):
The :func:`noctusai_lib.api.auth.make_get_current_user_org` factory binds the
``(user, token, org_id)`` triple resolution at module load. Routers consume the
resulting closure-bound dep via ``Depends(get_current_user_org)`` instead of
the imperative ``Header(authorization) + await get_current_user(authorization)``
shape — see ``KB § PATTERNS/backend.md § Auth — canonical pattern`` and the
youtube-crawler reference at ``products/youtube-crawler/backend/app/dependencies.py``.
"""
import logging
from typing import Optional

from fastapi import HTTPException
from noctusai_seed import create_database_module, create_dependencies
from noctusai_lib.domain.action_log import log_action as _shared_log_action
from noctusai_lib.api.auth import (
    first_or_none,  # noqa: F401 — re-exported for product imports
    make_get_current_user,
    make_get_current_user_org,
    make_require_role,
    resolve_sso_role,
)
from app.config import settings

_db = create_database_module(settings, schema="erp")
deps = create_dependencies(_db)

get_user_role = deps.get_user_role
get_user_client = deps.get_user_client
get_admin_client = deps.get_admin_client

logger = logging.getLogger(__name__)


def get_org_id(user, *, required: bool = False) -> Optional[str]:
    """Extract org_id from user metadata.

    org_id is set in auth.users.raw_user_meta_data during signup (core)
    and user creation (ERP profiles router). Available on every request
    without extra DB queries.

    By default returns None if missing (backwards-compatible).
    Pass required=True in endpoints where org_id is strictly needed.
    """
    org_id = (user.user_metadata or {}).get("org_id")
    if not org_id and required:
        raise HTTPException(status_code=400, detail="Organizacao nao encontrada no perfil do usuario")
    return org_id or None


# Canonical auth deps — wire via the factory so FastAPI sees only
# ``authorization: Header(None)`` in the dep signature.
#
# Late-binding lambda: the conftest patches ``_db.get_client`` AFTER this
# module imports. Capturing the bound method at module load
# (``make_get_current_user(_db.get_client)``) would freeze the pre-patch
# reference. The lambda re-resolves on every request so both production
# and test paths see the right client.
get_current_user = make_get_current_user(lambda: _db.get_client())
get_current_user_org = make_get_current_user_org(
    get_current_user,
    lambda u: get_org_id(u),
    required=True,
    missing_status=400,
    missing_detail="Organizacao nao encontrada no perfil do usuario",
)


def log_action(user_id: str, tipo_acao: str, tipo_entidade: str,
               entidade_id: Optional[str] = None, descricao: str = "", detalhes: Optional[dict] = None):
    """Server-side action logging. Always runs with service role."""
    _shared_log_action(
        get_admin_client(), "user_actions_log", "usuario_id",
        user_id, tipo_acao, tipo_entidade, entidade_id, descricao, detalhes,
    )


# ---------------------------------------------------------------------------
# Role resolution + `require_role` factory wiring
# ---------------------------------------------------------------------------
# Phase 3 (erp-wiring 2026-05-11) — Pattern F continuation. Replaces the
# bespoke `vista_showcase.require_admin` SSO-aware gate and the inline
# `metas_digest` role check with seed `make_require_role` composition.
#
# ERP's role resolution differs from the seed default because it preserves
# *both* historical metadata keys (`erp_role` first, `noctus_role` second)
# while still letting `resolve_sso_role` short-circuit to "platform_admin"
# for cross-product SSO admins. The seed primitive only consumes the
# resolver — composition stays in product code.


def get_erp_user_role(user) -> str:
    """Resolve ERP-tier role for a user.

    Resolution order matches the historical `vista_showcase.require_admin`
    body:
      1. Cross-product SSO role (`resolve_sso_role`) — short-circuits to
         "platform_admin" for SSO-authenticated platform admins.
      2. `user_metadata.erp_role` — ERP-native role (preferred).
      3. `user_metadata.noctus_role` — legacy fallback key.
      4. ``"user"`` — sentinel default for unauthenticated / anonymous
         metadata; downstream `require_role(*allowed)` will 403.
    """
    sso = resolve_sso_role(user)
    if sso == "platform_admin":
        return sso
    metadata = user.user_metadata or {}
    return metadata.get("erp_role") or metadata.get("noctus_role") or "user"


# Canonical `require_role(*allowed)` factory — bound once at module load to
# this product's `get_current_user` (Supabase-client-aware) and ERP role
# resolver. Routers consume via `Depends(require_role("admin", "owner"))`.
require_role = make_require_role(get_current_user, get_erp_user_role)
