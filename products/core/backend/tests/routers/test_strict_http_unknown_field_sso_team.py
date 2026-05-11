"""Regression tests — StrictHttpModel rejects unknown request keys with 422 (W4).

W4 of the core-schemas-extraction (2026-05-11): the `sso` + `team` routers
moved their inline `BaseModel` request schemas to `app/schemas/sso.py` +
`app/schemas/team.py` and switched the base class to
`noctusai_lib.api.StrictHttpModel`. That flips Pydantic's default
`extra="ignore"` to `extra="forbid"`, so any unknown key on the JSON body
must return **422 Unprocessable Entity** with a body that names the offending
location — closing the silent-drop bug class
(memory `feedback_pydantic_silent_drop_kills_writes`;
KB § PATTERNS/pydantic-strict-http.md).

Sibling-isolated alongside the existing W3-A file
(`test_strict_http_unknown_field_w3a.py`); matches the per-product
convention established by personal-finance's `test_strict_http_unknown_field.py`.

Coverage (7 request schemas → 7 tests):

- `sso.SSOTokenRequest`      POST  /api/sso/token
- `sso.SSOValidateRequest`   POST  /api/sso/validate
- `sso.SSOSessionRequest`    POST  /api/sso/session
- `team.InviteCreate`        POST  /api/team/invite
- `team.TeamMemberRoleUpdate` PATCH /api/team/{user_id}/role
- `team.AcceptInviteRequest` POST  /api/team/accept-invite

(`SSOSessionResponse` is a response-side schema — its strictness is
exercised indirectly by FastAPI's response_model validation on the green
path in `test_sso_router.py::TestSSOSession`.)
"""
from __future__ import annotations


def _assert_422_names_field(response, sentinel: str) -> None:
    """Common assertion: status 422 + offending field name appears in detail."""
    assert response.status_code == 422, response.text
    body = response.json()
    detail_str = str(body.get("detail", body))
    assert sentinel in detail_str, detail_str


class TestStrictHttpUnknownFieldRejectedW4:
    # ---- sso ----
    def test_sso_token_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/sso/token",
            json={
                "product_slug": "erp-imobiliario",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_sso_validate_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/sso/validate",
            json={
                "token": "some-sso-token",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_sso_session_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/sso/session",
            json={
                "token": "some-sso-token",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    # ---- team ----
    def test_team_invite_rejects_unknown_field_with_422(self, admin_client):
        resp = admin_client.post(
            "/api/team/invite",
            json={
                "email": "new@example.com",
                "role": "member",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_team_role_update_rejects_unknown_field_with_422(self, admin_client):
        resp = admin_client.patch(
            "/api/team/some-user/role",
            json={
                "role": "admin",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")

    def test_team_accept_invite_rejects_unknown_field_with_422(self, client):
        resp = client.post(
            "/api/team/accept-invite",
            json={
                "token": "some-invite-token",
                "definitely_not_a_field": "trojan",
            },
        )
        _assert_422_names_field(resp, "definitely_not_a_field")
