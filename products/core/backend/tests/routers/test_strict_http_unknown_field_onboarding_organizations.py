"""Regression tests — StrictHttpModel rejects unknown request keys with 422 (W3-B).

W3-B of the core-schemas-extraction (2026-05-11): the 4 routers in this
wave (`onboarding`, `organizations`, `products`, `roles`) moved their
inline `BaseModel` request schemas to `app/schemas/<router>.py` and
switched the base class to `noctusai_lib.api.StrictHttpModel`. That flips
Pydantic's default `extra="ignore"` to `extra="forbid"`, so any unknown
key on the JSON body must return **422 Unprocessable Entity** with a body
that names the offending location — closing the silent-drop bug class
(memory `feedback_pydantic_silent_drop_kills_writes`; KB §
PATTERNS/pydantic-strict-http.md).

Mirrors the W2 test file `tests/routers/test_strict_http_unknown_field.py`
(uses a separate file name to avoid merge conflicts with W3-A / W3-C).

One test per wired route in the wave (5 total — `CompanyDetailsUpdate` in
`onboarding.py` is an orphan schema with no route handler, so no test
asserts on it directly; its 422 contract is covered by the Pydantic
runtime config inherited from `StrictHttpModel`):

- `onboarding.StepComplete`        PATCH /api/onboarding/complete
- `organizations.OrgUpdate`        PATCH /api/organizations/{org_id}
- `products.ProductCreate`         POST  /api/products
- `roles.RoleCreate`               POST  /api/roles
- `roles.RoleUpdate`               PATCH /api/roles/{role_id}
"""
from __future__ import annotations


def _assert_422_names_field(response, sentinel: str) -> None:
    """Common assertion: status 422 + offending field name appears in detail."""
    assert response.status_code == 422, response.text
    body = response.json()
    detail_str = str(body.get("detail", body))
    assert sentinel in detail_str, detail_str


class TestStrictHttpUnknownFieldRejectedW3B:
    def test_onboarding_complete_rejects_unknown_field_with_422(self, client):
        resp = client.patch(
            "/api/onboarding/complete",
            json={
                "step": "company_details",
                "data": {"k": "v"},
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_organizations_update_rejects_unknown_field_with_422(self, client):
        resp = client.patch(
            "/api/organizations/org-1",
            json={"nome": "Updated", "definitely_not_a_field": "trojan"},
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_products_create_rejects_unknown_field_with_422(self, admin_client):
        resp = admin_client.post(
            "/api/products",
            json={
                "nome": "Erp Imobiliario",
                "slug": "erp-imobi",
                "icone": "Building2",
                "url_base": "https://erp.noctus.ai",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_roles_create_rejects_unknown_field_with_422(self, admin_client):
        resp = admin_client.post(
            "/api/roles",
            json={
                "name": "Reviewer",
                "slug": "reviewer",
                "permissions": ["team:read"],
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_roles_update_rejects_unknown_field_with_422(self, admin_client):
        resp = admin_client.patch(
            "/api/roles/some-role-id",
            json={"name": "Renamed", "definitely_not_a_field": "trojan"},
        )
        _assert_422_names_field(resp, "definitely_not_a_field")
