"""§D approval-assertion edge cases — exercised through `POST /api/kb`
(assertion verification is route-agnostic; one vehicle route avoids
duplicating this matrix across all seven routers).
"""
from __future__ import annotations

from uuid import UUID, uuid4

from noctusai_lib.api.auth.session.types import AuthContext

from app.dependencies import get_approval_assertion_keys
from app.main import app
from tests.routers.conftest import canonical_body, sign_assertion

_ORG = UUID("00000000-0000-4000-8000-0000000000aa")
_AGENT = UUID("00000000-0000-4000-8000-0000000000cc")
_APPROVER = UUID("00000000-0000-4000-8000-0000000000ff")
_SECRET = "test-approval-secret-32-bytes-minimum-for-hs256"
_OTHER_SECRET = "another-test-secret-also-32-bytes-long!"


def _product_ctx() -> AuthContext:
    return AuthContext(
        org_id=_ORG, caller_kind="product", user_id=None,
        scopes=["academia:kb:write", "academia:read"], raw_token="tok",
        api_token_id=uuid4(), principal_agent_id=_AGENT,
    )


def _seed_role(client, role: str = "owner") -> None:
    client.mock_supabase.set_table_data(
        "noctus_users", [{"id": str(_APPROVER), "org_id": str(_ORG), "org_role": role}]
    )


def _use_keys(keys: list[str]) -> None:
    app.dependency_overrides[get_approval_assertion_keys] = lambda: keys


_BODY = {"slug": "s", "categoria": "geral", "titulo": "A", "corpo_md": "x", "motivo": "m"}


class TestAssertionEdgeCases:
    def teardown_method(self, method):
        app.dependency_overrides.pop(get_approval_assertion_keys, None)

    def _post(self, client, *, token: str, body: bytes = None):
        return client.raw().post(
            "/api/kb",
            content=body if body is not None else canonical_body(_BODY),
            headers={"content-type": "application/json", "X-Approval-Assertion": token},
        )

    def test_key_rotation_accepts_any_configured_key(self, client, store, set_auth):
        """Contract §D: "academia accepts any element" of the key list —
        rotation is prepend-new-deploy-both-drop-old."""
        _use_keys([_OTHER_SECRET, _SECRET])
        _seed_role(client)
        set_auth(_product_ctx())
        body = canonical_body(_BODY)
        token = sign_assertion(
            secret=_SECRET, org_id=_ORG, agent_id=_AGENT, approved_by=_APPROVER,
            tool="academia.kb.escrever", method="POST", path="/api/kb", body=body,
        )
        resp = self._post(client, token=token, body=body)
        assert resp.status_code == 201, resp.text

    def test_wrong_key_is_403(self, client, store, set_auth):
        _use_keys([_SECRET])
        _seed_role(client)
        set_auth(_product_ctx())
        body = canonical_body(_BODY)
        token = sign_assertion(
            secret=_OTHER_SECRET, org_id=_ORG, agent_id=_AGENT, approved_by=_APPROVER,
            tool="academia.kb.escrever", method="POST", path="/api/kb", body=body,
        )
        resp = self._post(client, token=token, body=body)
        assert resp.status_code == 403
        assert resp.json()["code"] == "assertion_invalid"

    def test_body_tampered_after_signing_is_403(self, client, store, set_auth):
        _use_keys([_SECRET])
        _seed_role(client)
        set_auth(_product_ctx())
        signed_body = canonical_body(_BODY)
        token = sign_assertion(
            secret=_SECRET, org_id=_ORG, agent_id=_AGENT, approved_by=_APPROVER,
            tool="academia.kb.escrever", method="POST", path="/api/kb", body=signed_body,
        )
        tampered_body = canonical_body({**_BODY, "titulo": "Tampered"})
        resp = self._post(client, token=token, body=tampered_body)
        assert resp.status_code == 403
        assert resp.json()["code"] == "assertion_invalid"

    def test_path_mismatch_is_403(self, client, store, set_auth):
        _use_keys([_SECRET])
        _seed_role(client)
        set_auth(_product_ctx())
        body = canonical_body(_BODY)
        token = sign_assertion(
            secret=_SECRET, org_id=_ORG, agent_id=_AGENT, approved_by=_APPROVER,
            tool="academia.kb.escrever", method="POST", path="/api/kb/wrong-path", body=body,
        )
        resp = self._post(client, token=token, body=body)
        assert resp.status_code == 403
        assert resp.json()["code"] == "assertion_invalid"

    def test_tool_mismatch_is_403(self, client, store, set_auth):
        _use_keys([_SECRET])
        _seed_role(client)
        set_auth(_product_ctx())
        body = canonical_body(_BODY)
        token = sign_assertion(
            secret=_SECRET, org_id=_ORG, agent_id=_AGENT, approved_by=_APPROVER,
            tool="academia.decisao.registrar", method="POST", path="/api/kb", body=body,
        )
        resp = self._post(client, token=token, body=body)
        assert resp.status_code == 403
        assert resp.json()["code"] == "assertion_invalid"

    def test_expired_assertion_is_403(self, client, store, set_auth):
        _use_keys([_SECRET])
        _seed_role(client)
        set_auth(_product_ctx())
        body = canonical_body(_BODY)
        token = sign_assertion(
            secret=_SECRET, org_id=_ORG, agent_id=_AGENT, approved_by=_APPROVER,
            tool="academia.kb.escrever", method="POST", path="/api/kb", body=body,
            exp_delta=-30,
        )
        resp = self._post(client, token=token, body=body)
        assert resp.status_code == 403
        assert resp.json()["code"] == "assertion_invalid"

    def test_wrong_aud_is_403(self, client, store, set_auth):
        _use_keys([_SECRET])
        _seed_role(client)
        set_auth(_product_ctx())
        body = canonical_body(_BODY)
        token = sign_assertion(
            secret=_SECRET, org_id=_ORG, agent_id=_AGENT, approved_by=_APPROVER,
            tool="academia.kb.escrever", method="POST", path="/api/kb", body=body,
            aud="some-other-product",
        )
        resp = self._post(client, token=token, body=body)
        assert resp.status_code == 403
        assert resp.json()["code"] == "assertion_invalid"

    def test_org_mismatch_is_403(self, client, store, set_auth):
        _use_keys([_SECRET])
        _seed_role(client)
        set_auth(_product_ctx())
        body = canonical_body(_BODY)
        token = sign_assertion(
            secret=_SECRET, org_id=uuid4(), agent_id=_AGENT, approved_by=_APPROVER,
            tool="academia.kb.escrever", method="POST", path="/api/kb", body=body,
        )
        resp = self._post(client, token=token, body=body)
        assert resp.status_code == 403
        assert resp.json()["code"] == "assertion_invalid"

    def test_sub_not_matching_principal_agent_is_403(self, client, store, set_auth):
        _use_keys([_SECRET])
        _seed_role(client)
        set_auth(_product_ctx())
        body = canonical_body(_BODY)
        token = sign_assertion(
            secret=_SECRET, org_id=_ORG, agent_id=uuid4(), approved_by=_APPROVER,
            tool="academia.kb.escrever", method="POST", path="/api/kb", body=body,
        )
        resp = self._post(client, token=token, body=body)
        assert resp.status_code == 403
        assert resp.json()["code"] == "assertion_invalid"

    def test_approver_without_write_role_is_403_approver_not_allowed(self, client, store, set_auth):
        _use_keys([_SECRET])
        _seed_role(client, role="viewer")  # READ-only, not WRITE
        set_auth(_product_ctx())
        body = canonical_body(_BODY)
        token = sign_assertion(
            secret=_SECRET, org_id=_ORG, agent_id=_AGENT, approved_by=_APPROVER,
            tool="academia.kb.escrever", method="POST", path="/api/kb", body=body,
        )
        resp = self._post(client, token=token, body=body)
        assert resp.status_code == 403
        assert resp.json()["code"] == "approver_not_allowed"

    def test_replay_is_409_assertion_used(self, client, store, set_auth):
        _use_keys([_SECRET])
        _seed_role(client)
        set_auth(_product_ctx())
        body = canonical_body({**_BODY, "slug": "replay-test"})
        jti = uuid4()
        token = sign_assertion(
            secret=_SECRET, org_id=_ORG, agent_id=_AGENT, approved_by=_APPROVER,
            tool="academia.kb.escrever", method="POST", path="/api/kb", body=body,
            jti=jti,
        )
        first = self._post(client, token=token, body=body)
        assert first.status_code == 201, first.text

        # Replay: same jti, but a DIFFERENT slug/body so it isn't just a
        # slug-conflict 409 — the assertion_used guard must fire first.
        replay_body = canonical_body({**_BODY, "slug": "replay-test-2"})
        replay_token = sign_assertion(
            secret=_SECRET, org_id=_ORG, agent_id=_AGENT, approved_by=_APPROVER,
            tool="academia.kb.escrever", method="POST", path="/api/kb", body=replay_body,
            jti=jti,
        )
        second = self._post(client, token=replay_token, body=replay_body)
        assert second.status_code == 409
        assert second.json()["code"] == "assertion_used"
