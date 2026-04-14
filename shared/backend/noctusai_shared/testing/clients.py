"""
Mock user objects and authenticated test clients.

MockUser is parameterized to support all product role patterns:
- Core: role only (admin/user)
- ERP: org_id
- Therapy: role + optional clinic_id
- PF: org_id
"""
from __future__ import annotations

from typing import Optional


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
        id: str = "test-user-123",
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
