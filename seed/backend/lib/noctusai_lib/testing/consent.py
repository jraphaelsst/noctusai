"""Test helpers for the consent module.

Shipped 2026-04-27 by `consent-guard-rollout` Phase 4 (formalize threshold
tripped after mailing + ERP both inlined the same rewire pattern in their
conftests; daily-life would have been the third occurrence).

The seed's `create_product_app(...)` calls `configure_consent_module(...)`
once at app boot. But test fixtures using `TestClient` cache the app —
subsequent fixture invocations create a NEW `mock_sb` while the consent
module still holds the FIRST fixture's reference. Without a per-fixture
re-bind, consent-guard tests after the first one read stale data.

`bind_consent_module_to_mock(mock_sb)` is the per-fixture rewire helper:
it points the consent module's `get_current_user` and `admin_client_factory`
at the current test's mock_sb. Idempotent — safe to call repeatedly.
"""
from __future__ import annotations

from typing import Any


def bind_consent_module_to_mock(mock_sb: Any) -> None:
    """Wire the consent module's FastAPI deps to a mock Supabase client.

    Call this inside a product's `client` fixture, after the
    `noctusai_seed.database.DatabaseModule.*` patches and after
    `from app.main import app` (so app boot has run).

    Args:
        mock_sb: a `MockSupabaseClient` instance with `mock_sb.auth.get_user`
            already configured to return a `MockUserResponse`.

    Usage::

        @pytest.fixture
        def client():
            mock_sb = MockSupabaseClient(...)
            mock_sb.auth.get_user = MagicMock(
                return_value=MockUserResponse(MockUser(org_id="..."))
            )
            with patch(
                "noctusai_seed.database.DatabaseModule.get_admin_client",
                return_value=mock_sb,
            ):
                from app.main import app
                bind_consent_module_to_mock(mock_sb)
                tc = TestClient(app)
                yield AuthClient(tc, mock_sb)

    The helper queries `mock_sb.auth.get_user("token")` at every consent
    check to resolve the test user. Any consent-guarded endpoint will
    use whatever `MockUser` the test seeded into `mock_sb.auth`.
    """
    # Imported here (not at module level) so importing `noctusai_lib.testing`
    # doesn't pull FastAPI into pure-data test modules. The actual import is
    # cheap given FastAPI is already a hard dep of noctusai_lib.
    from noctusai_lib.ai import configure_consent_module

    async def _mock_get_current_user(authorization: str = None) -> tuple:  # type: ignore[assignment]
        user_resp = mock_sb.auth.get_user("token")
        return user_resp.user, "token"

    configure_consent_module(
        get_current_user=_mock_get_current_user,
        admin_client_factory=lambda: mock_sb,
    )
