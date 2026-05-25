"""
Mock user objects and authenticated test clients.

MockUser is parameterized to support all product role patterns:
- Core: role only (admin/user)
- ERP: org_id
- Therapy: role + optional clinic_id
- PF: org_id
- AdConnect: role + org_id + extra_metadata (distributor_id)

Helpers:
- ``bind_user_metadata(mock_sb_or_client, *, user=None, **mock_user_kwargs)``
  re-binds ``mock_sb.auth.get_user`` to a freshly-built ``MockUser``.
  Generic primitive lifted from the AdConnect-specific ``bind_adconnect_user``
  during ``adconnect-test-conftest-distributor-binding`` Phase 2 — N≥3
  recurrence across 7+ product conftests of the inline shape::

      mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(...)))

  Products that need product-specific defaults (role-name vocabulary,
  claim-name mapping) wrap this in their own conftest, e.g.::

      def bind_adconnect_user(client, *, role="customer", distributor_id=None, ...):
          extra = {"distributor_id": distributor_id} if distributor_id else None
          return bind_user_metadata(client, role=role, org_id=ORG_ID_BRAND, extra_metadata=extra)
"""
from __future__ import annotations

from typing import Any, Optional
from unittest.mock import MagicMock


#: Canonical test identity — the seed-default ``MockUser`` id and the org id the
#: framework suites assert against. **Products' mock fixtures MUST reference these
#: constants, never a hand-typed literal**: a mock row whose ``user_id`` / ``org_id``
#: drifts from the ``MockUser`` default silently fails every ``.eq(user_id|org_id, …)``
#: predicate once ``MockRequestBuilder`` filtering is accurate (the ``"test-user-id"``
#: vs ``"test-user-123"`` footgun, N=2 daily-life + erp). Import via
#: ``from noctusai_lib.testing import TEST_USER_ID, TEST_ORG_ID``.
TEST_USER_ID = "test-user-123"
TEST_ORG_ID = "test-org-123"


class MockUser:
    """Simulates a Supabase auth user object.

    All metadata fields are optional — products pass what they need::

        MockUser()                              # bare user
        MockUser(org_id="org-1")                # ERP / PF user
        MockUser(role="therapist")              # Therapy user
        MockUser(role="clinic_admin", clinic_id="c-1")  # Clinic admin
    """

    def __init__(
        self,
        id: str = TEST_USER_ID,
        email: str = "test@example.com",
        *,
        role: Optional[str] = None,
        org_id: Optional[str] = None,
        clinic_id: Optional[str] = None,
        noctus_role: Optional[str] = None,
        org_role: Optional[str] = None,
        extra_metadata: Optional[dict] = None,
    ):
        self.id = id
        self.email = email
        self.user_metadata = {}
        if role:
            self.user_metadata["role"] = role
        if org_id:
            self.user_metadata["org_id"] = org_id
        if clinic_id:
            self.user_metadata["clinic_id"] = clinic_id
        if noctus_role:
            self.user_metadata["noctus_role"] = noctus_role
        if org_role:
            self.user_metadata["org_role"] = org_role
        if extra_metadata:
            self.user_metadata.update(extra_metadata)


class MockUserResponse:
    """Wraps MockUser to simulate supabase.auth.get_user() response."""

    def __init__(self, user=None):
        self.user = user or MockUser()


class AuthClient:
    """Wraps FastAPI TestClient with automatic Authorization header.

    Products use this in fixtures to simulate authenticated requests::

        mock_sb = MockSupabaseClient()
        tc = TestClient(app)
        yield AuthClient(tc, mock_sb)

    Access the mock via ``client.mock_supabase`` for assertions.
    """

    def __init__(self, test_client, mock_supabase, token: str = "test-token-valid"):
        self._tc = test_client
        self._mock_supabase = mock_supabase
        self._headers = {"Authorization": f"Bearer {token}"}

    @property
    def mock_supabase(self):
        return self._mock_supabase

    def get(self, url, **kwargs):
        kwargs.setdefault("headers", {}).update(self._headers)
        return self._tc.get(url, **kwargs)

    def post(self, url, **kwargs):
        kwargs.setdefault("headers", {}).update(self._headers)
        return self._tc.post(url, **kwargs)

    def patch(self, url, **kwargs):
        kwargs.setdefault("headers", {}).update(self._headers)
        return self._tc.patch(url, **kwargs)

    def put(self, url, **kwargs):
        kwargs.setdefault("headers", {}).update(self._headers)
        return self._tc.put(url, **kwargs)

    def delete(self, url, **kwargs):
        kwargs.setdefault("headers", {}).update(self._headers)
        return self._tc.delete(url, **kwargs)

    def raw(self):
        """Return the underlying TestClient without auth headers."""
        return self._tc


def bind_user_metadata(
    mock_sb_or_client: Any,
    *,
    user: Optional[MockUser] = None,
    role: Optional[str] = None,
    org_id: Optional[str] = None,
    clinic_id: Optional[str] = None,
    noctus_role: Optional[str] = None,
    org_role: Optional[str] = None,
    user_id: Optional[str] = None,
    email: str = "test@example.com",
    extra_metadata: Optional[dict[str, Any]] = None,
) -> MockUserResponse:
    """Re-bind ``mock_sb.auth.get_user`` to return a fresh ``MockUser``.

    Generic primitive lifted from the AdConnect-specific ``bind_adconnect_user``
    helper (`adconnect-test-conftest-distributor-binding` Phase 2) so other
    products can collapse the inline pattern::

        mock_sb.auth.get_user = MagicMock(
            return_value=MockUserResponse(MockUser(role=..., org_id=..., ...))
        )

    Args:
      mock_sb_or_client: a ``MockSupabaseClient`` directly OR an
        ``AuthClient``/object exposing ``.mock_supabase``. Both shapes
        resolved transparently — saves callers an unwrap step.
      user: pre-built ``MockUser``. If passed, all other ``MockUser``-shaping
        kwargs are ignored. Use this when you need fine-grained control
        (e.g. building user from a fixture factory).
      role / org_id / clinic_id / noctus_role / org_role / user_id /
        email / extra_metadata: passthrough to ``MockUser`` constructor.

    Returns the underlying ``MockUserResponse`` (in case the caller wants
    to access ``.user``).
    """
    mock_sb = (
        mock_sb_or_client.mock_supabase
        if hasattr(mock_sb_or_client, "mock_supabase")
        else mock_sb_or_client
    )
    if user is None:
        kwargs: dict[str, Any] = {"email": email}
        if user_id is not None:
            kwargs["id"] = user_id
        if role is not None:
            kwargs["role"] = role
        if org_id is not None:
            kwargs["org_id"] = org_id
        if clinic_id is not None:
            kwargs["clinic_id"] = clinic_id
        if noctus_role is not None:
            kwargs["noctus_role"] = noctus_role
        if org_role is not None:
            kwargs["org_role"] = org_role
        if extra_metadata is not None:
            kwargs["extra_metadata"] = extra_metadata
        user = MockUser(**kwargs)

    response = MockUserResponse(user)
    mock_sb.auth.get_user = MagicMock(return_value=response)
    return response
