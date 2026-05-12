"""
Smoke test for the canonical factory-wired auth deps.

Verifies that the ERP backend's `app.dependencies` module exposes:
- `get_current_user` — wired via `make_get_current_user` so FastAPI sees only
  `authorization: Header(None)` in the dep signature.
- `get_current_user_org` — wired via `make_get_current_user_org` with
  `required=True, missing_status=400` matching ERP's pre-existing
  `get_org_id(user, required=True)` contract.

These factory wirings replaced the imperative
`Header(authorization) + await get_current_user(authorization)` shape across
ERP routers in Phase 1 of `erp-wiring` (2026-05-11). See the seed factory at
`seed/lib/backend/noctusai_lib/api/auth.py:231-310`.
"""
import inspect

import pytest


class TestGetCurrentUserWiring:
    def test_get_current_user_is_callable(self):
        from app.dependencies import get_current_user
        assert callable(get_current_user), "get_current_user must be callable"

    def test_get_current_user_signature_is_authorization_only(self):
        """The FastAPI-facing dep MUST have exactly one parameter — authorization."""
        from app.dependencies import get_current_user
        sig = inspect.signature(get_current_user)
        params = list(sig.parameters.values())
        # The factory wraps in `async def _product_get_current_user(authorization: ...)`.
        assert len(params) == 1, (
            f"Expected 1 param (authorization), got {[p.name for p in params]}"
        )
        assert params[0].name == "authorization"


class TestGetCurrentUserOrgWiring:
    def test_get_current_user_org_is_callable(self):
        from app.dependencies import get_current_user_org
        assert callable(get_current_user_org), "get_current_user_org must be callable"

    def test_get_current_user_org_signature_is_authorization_only(self):
        from app.dependencies import get_current_user_org
        sig = inspect.signature(get_current_user_org)
        params = list(sig.parameters.values())
        assert len(params) == 1, (
            f"Expected 1 param (authorization), got {[p.name for p in params]}"
        )
        assert params[0].name == "authorization"


class TestFactorySourceIsSeed:
    """Verify the factories come from `noctusai_lib.api.auth`, not a local re-impl."""

    def test_make_get_current_user_org_import_path(self):
        from app.dependencies import make_get_current_user_org
        assert make_get_current_user_org.__module__ == "noctusai_lib.api.auth", (
            f"Expected seed source, got {make_get_current_user_org.__module__}"
        )

    def test_make_get_current_user_import_path(self):
        from app.dependencies import make_get_current_user
        assert make_get_current_user.__module__ == "noctusai_lib.api.auth", (
            f"Expected seed source, got {make_get_current_user.__module__}"
        )

    def test_make_require_role_import_path(self):
        """Phase 3 (erp-wiring 2026-05-11) — Pattern F continuation."""
        from app.dependencies import make_require_role
        assert make_require_role.__module__ == "noctusai_lib.api.auth", (
            f"Expected seed source, got {make_require_role.__module__}"
        )


class TestErpRoleResolver:
    """Phase 3 (erp-wiring 2026-05-11) — ERP-specific role resolution preserves
    the historical ``erp_role > noctus_role`` priority while letting cross-
    product SSO admins short-circuit to ``platform_admin``.
    """

    def _user(self, metadata):
        """Build a minimal user stub with the given user_metadata dict."""
        from types import SimpleNamespace
        return SimpleNamespace(user_metadata=metadata)

    def test_resolves_erp_role_preferred(self):
        from app.dependencies import get_erp_user_role
        user = self._user({"erp_role": "admin", "noctus_role": "user"})
        assert get_erp_user_role(user) == "admin"

    def test_falls_through_to_noctus_role(self):
        from app.dependencies import get_erp_user_role
        user = self._user({"noctus_role": "owner"})
        assert get_erp_user_role(user) == "owner"

    def test_defaults_to_user_sentinel(self):
        from app.dependencies import get_erp_user_role
        user = self._user({})
        assert get_erp_user_role(user) == "user"

    def test_none_metadata_does_not_crash(self):
        from app.dependencies import get_erp_user_role
        user = self._user(None)
        assert get_erp_user_role(user) == "user"


class TestRequireRoleFactoryBinding:
    def test_require_role_is_callable(self):
        from app.dependencies import require_role
        assert callable(require_role)

    def test_require_role_returns_dependency(self):
        """``require_role("admin")`` should return a FastAPI dep callable."""
        from app.dependencies import require_role
        dep = require_role("admin", "owner")
        assert callable(dep)
        sig = inspect.signature(dep)
        params = list(sig.parameters.values())
        # The seed-factory wraps in `async def _check_role(authorization: ...)`.
        assert len(params) == 1, (
            f"Expected 1 param (authorization), got {[p.name for p in params]}"
        )
        assert params[0].name == "authorization"
