"""Regression tests — StrictHttpModel rejects unknown request keys with 422.

W2 of the core-schemas-extraction (2026-05-11): the 8 routers in this wave
moved their inline `BaseModel` request schemas to `app/schemas/<router>.py`
and switched the base class to `noctusai_lib.api.StrictHttpModel`. That
flips Pydantic's default `extra="ignore"` to `extra="forbid"`, so any
unknown key on the JSON body must return **422 Unprocessable Entity** with
a body that names the offending location — closing the silent-drop bug
class (memory `feedback_pydantic_silent_drop_kills_writes`; KB §
PATTERNS/pydantic-strict-http.md).

Mirrors the per-product convention established in
`products/personal-finance/backend/tests/routers/test_strict_http_unknown_field.py`.

One test per extracted file (8 total):

- `admin_cache.FlushBody`            POST /api/admin/llm-cache/flush
- `admin_llm_spend.BudgetUpdate`     PUT  /api/admin/llm-spend/{org_id}/budget
- `api_keys.ApiKeyCreate`            POST /api/api-keys
- `me_consents.ConsentToggle`        PUT  /api/me/consents/{feature_key}
- `oauth.OAuthCallbackBody`          POST /api/auth/oauth/callback
- `plans.PlanCreate`                 POST /api/plans
- `settings.PlatformSettingBody`     PUT  /api/settings/platform/{key}
- `test_accounts.TestAccountCreate`  POST /api/admin/test-accounts
"""
from __future__ import annotations


def _assert_422_names_field(response, sentinel: str) -> None:
    """Common assertion: status 422 + offending field name appears in detail."""
    assert response.status_code == 422, response.text
    body = response.json()
    detail_str = str(body.get("detail", body))
    assert sentinel in detail_str, detail_str


class TestStrictHttpUnknownFieldRejected:
    def test_admin_cache_flush_rejects_unknown_field_with_422(self, admin_client):
        # admin_cache.FlushBody — the route uses a separate admin-role check
        # (`noctus_role == "admin"`) but the Pydantic body validation runs
        # before the dependency, so 422 still fires for an admin caller.
        # Using admin_client to bypass any pre-validation auth short-circuit.
        resp = admin_client.post(
            "/api/admin/llm-cache/flush",
            json={
                "product": "erp-imobiliario",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_admin_llm_spend_budget_rejects_unknown_field_with_422(self, admin_client):
        resp = admin_client.put(
            "/api/admin/llm-spend/org-1/budget",
            json={"monthly_brl": 100.0, "definitely_not_a_field": "trojan"},
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_api_keys_create_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/api-keys",
            json={
                "name": "my-key",
                "scopes": ["read"],
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_me_consents_toggle_rejects_unknown_field_with_422(self, client):
        resp = client.put(
            "/api/me/consents/some-feature-key",
            json={"granted": True, "definitely_not_a_field": "trojan"},
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_oauth_callback_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/auth/oauth/callback",
            json={"provider": "google", "definitely_not_a_field": "trojan"},
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_plans_create_rejects_unknown_field_with_422(self, admin_client):
        resp = admin_client.post(
            "/api/plans",
            json={
                "nome": "Pro",
                "slug": "pro",
                "price_monthly": 99,
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_settings_platform_upsert_rejects_unknown_field_with_422(self, admin_client):
        resp = admin_client.put(
            "/api/settings/platform/some-key",
            json={"value": "x", "definitely_not_a_field": "trojan"},
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_test_accounts_create_rejects_unknown_field_with_422(self, admin_client):
        resp = admin_client.post(
            "/api/admin/test-accounts",
            json={
                "nome": "Test User",
                "email": "test@example.com",
                "password": "password123",
                "empresa": "Test Co",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")
