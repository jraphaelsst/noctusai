"""Regression tests — StrictHttpModel rejects unknown request keys with 422.

W3-C of the core-schemas-extraction (2026-05-11): the 3 routers in this
sub-wave (`subscriptions`, `users`, `webhooks`) moved their inline
`BaseModel` request schemas to `app/schemas/<router>.py` and switched the
base class to `noctusai_lib.api.StrictHttpModel`. That flips Pydantic's
default `extra="ignore"` to `extra="forbid"`, so any unknown key on the
JSON body must return **422 Unprocessable Entity** with a body that names
the offending location — closing the silent-drop bug class (memory
`feedback_pydantic_silent_drop_kills_writes`; KB §
PATTERNS/pydantic-strict-http.md).

Mirrors the W2 reference file
`tests/routers/test_strict_http_unknown_field.py` and the per-product
convention established in
`products/personal-finance/backend/tests/routers/test_strict_http_unknown_field.py`.

This file is sibling-isolated from the W3-A / W3-B test files to avoid
merge conflicts — each W3 sub-wave owns its own test module.

One test per extracted schema (5 total):

- `subscriptions.SubscriptionCreate`  POST  /api/subscriptions
- `subscriptions.SubscriptionUpdate`  PATCH /api/subscriptions/{id}
- `users.UserUpdate`                  PATCH /api/admin/users/{user_id}
- `webhooks.WebhookCreate`            POST  /api/webhooks
- `webhooks.WebhookUpdate`            PATCH /api/webhooks/{id}
"""
from __future__ import annotations


def _assert_422_names_field(response, sentinel: str) -> None:
    """Common assertion: status 422 + offending field name appears in detail."""
    assert response.status_code == 422, response.text
    body = response.json()
    detail_str = str(body.get("detail", body))
    assert sentinel in detail_str, detail_str


class TestStrictHttpUnknownFieldRejected:
    def test_subscriptions_create_rejects_unknown_field_with_422(self, admin_client):
        resp = admin_client.post(
            "/api/subscriptions",
            json={
                "org_id": "org-1",
                "plan_id": "plan-1",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_subscriptions_update_rejects_unknown_field_with_422(self, admin_client):
        resp = admin_client.patch(
            "/api/subscriptions/sub-1",
            json={"status": "canceled", "definitely_not_a_field": "trojan"},
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_users_update_rejects_unknown_field_with_422(self, admin_client):
        resp = admin_client.patch(
            "/api/admin/users/user-1",
            json={"nome": "New Name", "definitely_not_a_field": "trojan"},
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_webhooks_create_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["subscription.created"],
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_webhooks_update_rejects_unknown_field_with_422(self, client):
        resp = client.patch(
            "/api/webhooks/wh-1",
            json={"is_active": False, "definitely_not_a_field": "trojan"},
        )
        _assert_422_names_field(resp, "definitely_not_a_field")
