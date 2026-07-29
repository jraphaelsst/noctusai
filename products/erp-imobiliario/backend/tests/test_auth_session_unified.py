"""
Cookie-session auth infra — `app.dependencies.get_current_user_org_unified`
(erp-httponly-cookie-session-2026-07 roadmap, Slice 2).

SEC-6: the caller-facing token returned by `get_current_user_org_unified`
for a cookie-session user MUST be the freshly-MINTED Supabase access token
(from `TokenExchanger.access_token_for`), NEVER the opaque session id
(`AuthContext.raw_token`) itself — a cookie-derived AuthContext must never
reach `set_session` as-is. These tests exercise the dep directly (Fakes,
no live Redis/Supabase) rather than through the FastAPI `client` fixture,
since `get_current_user_org_unified` is not yet wired onto any router.
"""
import asyncio
from uuid import uuid4

import pytest

from noctusai_lib.api.auth.session import AuthContext, FakeTokenExchanger


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestGetCurrentUserOrgUnifiedSec6:
    def test_user_ctx_returns_exchanged_access_token_not_session_id(self, monkeypatch):
        """The returned token is the exchanger's MINTED access token — the
        opaque session id (`ctx.raw_token`) never leaks out as if it were
        a usable Supabase access token."""
        from app.dependencies import get_current_user_org_unified

        session_id = "opaque-session-id-not-a-jwt"
        minted_access_token = "eyJ-fake-minted-access-token"
        fake_exchanger = FakeTokenExchanger(
            tokens={session_id: minted_access_token}
        )
        monkeypatch.setattr(
            "app.dependencies._get_token_exchanger", lambda: fake_exchanger
        )

        org_id = uuid4()
        user_id = uuid4()
        ctx = AuthContext(
            org_id=org_id,
            caller_kind="user",
            user_id=user_id,
            scopes=[],
            raw_token=session_id,
            api_token_id=None,
        )

        user, token, returned_org_id = _run(get_current_user_org_unified(ctx))

        assert token == minted_access_token, (
            "SEC-6: get_current_user_org_unified must return the EXCHANGED "
            "access token"
        )
        assert token != session_id, (
            "SEC-6 violation: the opaque session id must never reach the "
            "caller as if it were a usable access token"
        )
        assert fake_exchanger.calls == [session_id], (
            "the exchanger must be called with the session id (ctx.raw_token)"
        )
        assert str(user.id) == str(user_id)
        assert user.user_metadata["org_id"] == str(org_id)
        assert returned_org_id == str(org_id)

    def test_product_caller_kind_rejected(self):
        """No pk_* automation consumer is wired to ERP's business routers
        yet (`FakeApiTokenResolver` in `get_auth_context` never resolves a
        `pk_*` bearer) — a `caller_kind="product"` AuthContext reaching
        this dep is unreachable today but must fail loud, not silently
        coerce into a user-shaped tuple."""
        from app.dependencies import get_current_user_org_unified
        from fastapi import HTTPException

        ctx = AuthContext(
            org_id=uuid4(),
            caller_kind="product",
            user_id=None,
            scopes=[],
            raw_token="pk-token-id",
            api_token_id=uuid4(),
        )

        with pytest.raises(HTTPException) as exc_info:
            _run(get_current_user_org_unified(ctx))
        assert exc_info.value.status_code == 403


class TestSessionStoreSharedSingleton:
    def test_get_session_store_delegates_to_seed_shared_accessor(self):
        """`app.dependencies._get_session_store()` MUST return the SAME
        object `noctusai_seed.auth_router.get_session_store(settings)`
        returns — a second independent `make_session_store(...)` call
        would split-brain the in-memory Fake (a session minted by the
        mounted `standard_routers=["auth"]` router's own `/login` would be
        invisible to a lookup running through a separate instance)."""
        from app.config import settings
        from app.dependencies import _get_session_store
        from noctusai_seed.auth_router import get_session_store as seed_get_session_store

        assert _get_session_store() is seed_get_session_store(settings)
