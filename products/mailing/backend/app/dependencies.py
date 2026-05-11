"""Dependencies for Mailing Product — delegates to framework.

The seed framework's ``ProductDependencies`` exports ``get_org_id`` /
``get_user_role`` / ``get_user_client`` as plain functions; using them as
``Depends()`` does NOT chain through FastAPI because their positional
``user`` / ``token`` args become required query parameters. The canonical
pattern is to bind :func:`noctusai_lib.api.auth.make_get_current_user_org`
once at module load and use the resulting closure-bound dep at every router
site that needs ``(user, token, org_id)``.

See ``KB § PATTERNS/backend.md § Auth — canonical pattern`` for the why.
``mailing-wiring`` Phase 1 adopts the factory (PF-1 recurrence, N=3
formalize). Imperative helpers below are retained for back-compat with
service-layer call-sites that still take ``user`` positionally.
"""
from noctusai_seed import create_dependencies, create_database_module
from noctusai_lib.api.auth import make_get_current_user_org
from app.config import settings

_db = create_database_module(settings, schema="mailing")
deps = create_dependencies(_db)

get_current_user = deps.get_current_user
get_user_role = deps.get_user_role
get_org_id = deps.get_org_id
get_user_client = deps.get_user_client
get_admin_client = deps.get_admin_client

# Canonical auth dep — wire via ``Depends(get_current_user_org)`` so FastAPI
# sees only ``authorization: Header(None)`` in the dep signature.
get_current_user_org = make_get_current_user_org(
    get_current_user,
    get_org_id,
    required=True,
)
