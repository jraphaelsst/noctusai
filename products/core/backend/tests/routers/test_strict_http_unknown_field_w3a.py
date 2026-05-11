"""Regression tests — StrictHttpModel rejects unknown request keys with 422 (W3-A).

W3-A of the core-schemas-extraction (2026-05-11): the 4 routers in this wave
moved their inline `BaseModel` request schemas to `app/schemas/<router>.py`
and switched the base class to `noctusai_lib.api.StrictHttpModel`. That
flips Pydantic's default `extra="ignore"` to `extra="forbid"`, so any
unknown key on the JSON body must return **422 Unprocessable Entity** with
a body that names the offending location — closing the silent-drop bug
class (memory `feedback_pydantic_silent_drop_kills_writes`; KB §
PATTERNS/pydantic-strict-http.md).

Mirrors the per-product convention established in
`products/personal-finance/backend/tests/routers/test_strict_http_unknown_field.py`
and the sibling W2 file `tests/routers/test_strict_http_unknown_field.py`.

One test per extracted schema (10 total):

- `auth.SignupRequest`              POST  /api/auth/signup
- `auth.LoginRequest`               POST  /api/auth/login
- `auth.ProfileUpdate`              PATCH /api/auth/profile
- `auth.PasswordChange`             POST  /api/auth/change-password
- `auth.RefreshRequest`             POST  /api/auth/refresh
- `billing.CheckoutRequest`         POST  /api/billing/checkout
- `billing.PortalRequest`           POST  /api/billing/portal
- `billing.CancelRequest`           POST  /api/billing/cancel
- `credentials.CredentialsBody`     PUT   /api/platform/credentials
- `licenses.LicenseGrant`           POST  /api/licenses
"""
from __future__ import annotations


def _assert_422_names_field(response, sentinel: str) -> None:
    """Common assertion: status 422 + offending field name appears in detail."""
    assert response.status_code == 422, response.text
    body = response.json()
    detail_str = str(body.get("detail", body))
    assert sentinel in detail_str, detail_str


class TestStrictHttpUnknownFieldRejectedW3A:
    # ---- auth ----
    def test_auth_signup_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/auth/signup",
            json={
                "nome": "Test User",
                "email": "test@example.com",
                "password": "password123",
                "empresa": "Test Co",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_auth_login_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "password123",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_auth_profile_update_rejects_unknown_field_with_422(self, client):
        resp = client.patch(
            "/api/auth/profile",
            json={"nome": "New Name", "definitely_not_a_field": "trojan"},
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_auth_change_password_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/auth/change-password",
            json={"new_password": "newpassword123", "definitely_not_a_field": "trojan"},
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_auth_refresh_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/auth/refresh",
            json={"refresh_token": "some-token", "definitely_not_a_field": "trojan"},
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    # ---- billing ----
    def test_billing_checkout_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/billing/checkout",
            json={
                "plan_id": "plan-uuid",
                "billing_cycle": "monthly",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_billing_portal_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/billing/portal",
            json={"return_url": "https://example.com", "definitely_not_a_field": "trojan"},
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_billing_cancel_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/billing/cancel",
            json={"at_period_end": True, "definitely_not_a_field": "trojan"},
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    # ---- credentials ----
    def test_credentials_put_rejects_unknown_field_with_422(self, client):
        resp = client.put(
            "/api/platform/credentials",
            json={"openai": "sk-xxx", "definitely_not_a_field": "trojan"},
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    # ---- licenses ----
    def test_licenses_grant_rejects_unknown_field_with_422(self, admin_client):
        resp = admin_client.post(
            "/api/licenses",
            json={
                "org_id": "org-1",
                "product_id": "product-1",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")
