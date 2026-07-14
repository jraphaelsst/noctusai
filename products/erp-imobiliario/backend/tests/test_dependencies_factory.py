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


class _FakeEmptyErpDbClient:
    """Chainable fake serving EVERY DB shape ``get_erp_user_role`` touches
    (``noctus_users`` select via ``resolve_platform_role``, ``has_role``
    RPC, ``erp.user_roles`` select) with an empty/falsy ``.data`` — drives
    resolution all the way through to the ``user_metadata`` fallback tier
    deterministically, without a real Supabase round-trip.

    Used by ``TestErpRoleResolver`` (``role-cascade-trusted``, 2026-07-14)
    to isolate the historical metadata-fallback tests from the DB-first
    tiers `get_erp_user_role` now checks ahead of them.
    """

    def table(self, *a, **k):
        return self

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def rpc(self, *a, **k):
        return self

    def execute(self):
        from types import SimpleNamespace
        return SimpleNamespace(data=[])


class TestErpRoleResolver:
    """Phase 3 (erp-wiring 2026-05-11) — ERP-specific role resolution preserves
    the historical ``erp_role > noctus_role`` priority while letting cross-
    product SSO admins short-circuit to ``platform_admin``.

    ``role-cascade-trusted`` (2026-07-14): ``get_erp_user_role`` now checks,
    in order, (1) the trusted platform-admin cascade (``public.noctus_users``),
    (2) a trusted ERP-scoped elevation (``public.has_role`` / ``erp.user_roles``),
    (3) an ``erp.user_roles`` base row, BEFORE falling through to the
    historical ``user_metadata`` tier these tests originally covered. Every
    test below patches both DB legs to a deterministic empty/not-elevated
    fake (see :class:`_FakeEmptyErpDbClient`) so the metadata-fallback
    behavior stays covered exactly as before, and adds dedicated coverage
    for the new trusted tiers.
    """

    def _user(self, metadata, *, user_id="u1"):
        """Build a minimal user stub with the given user_metadata dict."""
        from types import SimpleNamespace
        return SimpleNamespace(id=user_id, user_metadata=metadata)

    def _patch_db(self, *, core_client=None, admin_client=None):
        """Patch both DB legs `get_erp_user_role` touches: the trusted
        core client (`resolve_platform_role`'s `noctus_users` select +
        the `has_role` RPC) and the erp-scoped admin client (`erp.user_roles`
        base-row select). Defaults to an empty/not-elevated fake for both.
        """
        from unittest.mock import patch
        core = core_client if core_client is not None else _FakeEmptyErpDbClient()
        admin = admin_client if admin_client is not None else _FakeEmptyErpDbClient()
        return (
            patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=core),
            patch("app.dependencies.get_admin_client", return_value=admin),
        )

    def test_resolves_erp_role_preferred(self):
        from app.dependencies import get_erp_user_role
        user = self._user({"erp_role": "admin", "noctus_role": "user"})
        p1, p2 = self._patch_db()
        with p1, p2:
            assert get_erp_user_role(user) == "admin"

    def test_falls_through_to_noctus_role(self):
        from app.dependencies import get_erp_user_role
        user = self._user({"noctus_role": "owner"})
        p1, p2 = self._patch_db()
        with p1, p2:
            assert get_erp_user_role(user) == "owner"

    def test_defaults_to_user_sentinel(self):
        from app.dependencies import get_erp_user_role
        user = self._user({})
        p1, p2 = self._patch_db()
        with p1, p2:
            assert get_erp_user_role(user) == "user"

    def test_none_metadata_does_not_crash(self):
        from app.dependencies import get_erp_user_role
        user = self._user(None)
        p1, p2 = self._patch_db()
        with p1, p2:
            assert get_erp_user_role(user) == "user"

    def test_trusted_platform_admin_cascades_short_circuits_metadata(self):
        """A trusted ``public.noctus_users`` platform-admin row wins over
        EVERYTHING else — including a spoofed ``user_metadata.erp_role``
        that would otherwise resolve to a different value. Closes the
        role-spoof hole: a Noctus platform admin is admin in ERP too."""
        from types import SimpleNamespace
        from app.dependencies import get_erp_user_role
        user = self._user({"erp_role": "user"})  # spoofed-looking, irrelevant
        core = _FakeEmptyErpDbClient()
        core.execute = lambda: SimpleNamespace(data=[{"role": "admin", "org_role": "member"}])
        p1, p2 = self._patch_db(core_client=core)
        with p1, p2:
            assert get_erp_user_role(user) == "platform_admin"

    def test_erp_scoped_elevation_via_has_role_returns_admin(self):
        """An ERP admin having granted this user 'admin' WITHIN ERP
        (``erp.user_roles``, checked via ``public.has_role`` RPC) resolves
        to ``"admin"`` — the product-scoped override, even though the
        trusted platform lookup found no row (not a platform admin) and
        metadata carries nothing useful."""
        from types import SimpleNamespace
        from app.dependencies import get_erp_user_role
        user = self._user({})

        class _ElevatedCore(_FakeEmptyErpDbClient):
            def execute(self):
                # First call (resolve_platform_role's noctus_users select)
                # sees no row; the has_role RPC call (also routed through
                # this same core client) reports elevated=True. Both share
                # `.data` truthiness semantics generically, so a single
                # elevated response satisfies the RPC leg — the earlier
                # noctus_users .execute() call already returned via the
                # SAME method, so we key off call count.
                self._n = getattr(self, "_n", 0) + 1
                if self._n == 1:
                    return SimpleNamespace(data=[])  # noctus_users: no row
                return SimpleNamespace(data=True)  # has_role RPC: elevated

        p1, p2 = self._patch_db(core_client=_ElevatedCore())
        with p1, p2:
            assert get_erp_user_role(user) == "admin"

    def test_erp_scoped_base_row_returned_when_not_elevated(self):
        """No platform-admin cascade, no ``has_role`` elevation, but a base
        ``erp.user_roles`` row exists (e.g. 'corretor') — returns that
        native ERP role, trusted-DB, ahead of the metadata fallback."""
        from types import SimpleNamespace
        from app.dependencies import get_erp_user_role
        user = self._user({"erp_role": "user"})  # would lose to the DB row anyway
        admin = _FakeEmptyErpDbClient()
        admin.execute = lambda: SimpleNamespace(data=[{"role": "corretor"}])
        p1, p2 = self._patch_db(admin_client=admin)
        with p1, p2:
            assert get_erp_user_role(user) == "corretor"

    def test_db_error_on_has_role_fails_closed(self, caplog):
        """A genuine error on the ``has_role`` RPC (not just an empty
        result) propagates — fail-closed, never silently treated as
        not-elevated-so-fall-through-to-metadata-admin."""
        import logging
        from app.dependencies import get_erp_user_role

        class _RaisingCore(_FakeEmptyErpDbClient):
            def execute(self):
                self._n = getattr(self, "_n", 0) + 1
                if self._n == 1:
                    from types import SimpleNamespace
                    return SimpleNamespace(data=[])  # noctus_users: no row
                raise RuntimeError("connection refused")  # has_role RPC: down

        # `erp_role` only affects step 4 (the metadata fallback) — NOT
        # `resolve_sso_role`'s org_role/noctus_role check, so step 1
        # legitimately misses (no noctus_users row) and falls through to
        # the has_role RPC, which is where this test wants the error to
        # surface.
        user = self._user({"erp_role": "admin"})  # would leak if fallback ran
        p1, p2 = self._patch_db(core_client=_RaisingCore())
        with p1, p2:
            with caplog.at_level(logging.ERROR, logger="app.dependencies"):
                with pytest.raises(RuntimeError):
                    get_erp_user_role(user)


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
