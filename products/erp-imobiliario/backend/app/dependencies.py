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
    resolve_sso_role,  # noqa: F401 — re-exported for product imports
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
