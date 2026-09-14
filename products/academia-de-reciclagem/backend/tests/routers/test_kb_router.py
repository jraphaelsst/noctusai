"""Tests for `app/routers/kb_router.py` — contract §B.1."""
from __future__ import annotations

from uuid import UUID, uuid4

from noctusai_lib.api.auth.session.types import AuthContext

from app.dependencies import get_approval_assertion_keys
from app.main import app
from tests.routers.conftest import canonical_body, sign_assertion

_ORG = UUID("00000000-0000-4000-8000-0000000000aa")
_USER = UUID("00000000-0000-4000-8000-0000000000bb")
_AGENT = UUID("00000000-0000-4000-8000-0000000000cc")
_SECRET = "test-approval-secret-32-bytes-minimum-for-hs256"


def _user_ctx(org_id=_ORG, user_id=_USER) -> AuthContext:
    return AuthContext(
        org_id=org_id,
        caller_kind="user",
        user_id=user_id,
        scopes=[],
        raw_token="session-1",
        api_token_id=None,
    )


def _viewer_ctx() -> AuthContext:
    return _user_ctx(user_id=UUID("00000000-0000-4000-8000-0000000000ee"))


def _product_ctx(scopes: list[str], *, human_personal=False, principal_agent_id=_AGENT) -> AuthContext:
    return AuthContext(
        org_id=_ORG,
        caller_kind="product",
        user_id=None,
        scopes=scopes,
        raw_token="tok-1",
        api_token_id=uuid4(),
        principal_agent_id=principal_agent_id,
        human_personal=human_personal,
    )


def _seed_role(client, user_id: UUID, role: str) -> None:
    client.mock_supabase.set_table_data(
        "noctus_users", [{"id": str(user_id), "org_id": str(_ORG), "org_role": role}]
    )


def _use_assertion_secret():
    """DI override for `get_approval_assertion_keys` — the seam a test
    uses instead of `monkeypatch.setattr(settings, ...)` (which trips
    `check_no_self_monkeypatch`)."""
    app.dependency_overrides[get_approval_assertion_keys] = lambda: [_SECRET]


class TestAuthBoundary:
    def test_unauthenticated_get_is_401(self, client, store):
        resp = client.raw().get("/api/kb")
        assert resp.status_code == 401

    def test_unauthenticated_post_is_401(self, client, store):
        resp = client.raw().post("/api/kb", json={"categoria": "geral", "titulo": "x", "corpo_md": "y", "motivo": "z"})
        assert resp.status_code == 401

    def test_viewer_role_cannot_write(self, client, store, set_auth):
        set_auth(_viewer_ctx())
        _seed_role(client, UUID("00000000-0000-4000-8000-0000000000ee"), "viewer")
        resp = client.raw().post(
            "/api/kb", json={"categoria": "geral", "titulo": "x", "corpo_md": "y", "motivo": "z"}
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "role_missing"

    def test_product_token_missing_scope_is_403(self, client, store, set_auth):
        set_auth(_product_ctx(scopes=["academia:read"]))
        resp = client.raw().post(
            "/api/kb", json={"categoria": "geral", "titulo": "x", "corpo_md": "y", "motivo": "z"}
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "scope_missing"


class TestCreateAndGet:
    def test_owner_creates_entry_slug_derived(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client, _USER, "owner")
        resp = client.raw().post(
            "/api/kb",
            json={
                "categoria": "dominio",
                "titulo": "Domínio Regulatório PNRS",
                "corpo_md": "# corpo",
                "motivo": "primeira entrada",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["slug"] == "dominio-regulatorio-pnrs"
        assert body["categoria"] == "dominio"
        assert body["current_revision"]["rev_no"] == 1
        assert body["current_revision"]["author_kind"] == "human"

        get_resp = client.raw().get(f"/api/kb/{body['slug']}")
        assert get_resp.status_code == 200
        assert get_resp.json()["corpo_md"] == "# corpo"

    def test_duplicate_slug_is_409(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client, _USER, "owner")
        payload = {"slug": "dup", "categoria": "geral", "titulo": "A", "corpo_md": "x", "motivo": "m"}
        first = client.raw().post("/api/kb", json=payload)
        assert first.status_code == 201
        second = client.raw().post("/api/kb", json=payload)
        assert second.status_code == 409
        assert second.json()["code"] == "conflict"

    def test_get_unknown_slug_is_404(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client, _USER, "owner")
        resp = client.raw().get("/api/kb/does-not-exist")
        assert resp.status_code == 404

    def test_extra_field_is_422(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client, _USER, "owner")
        resp = client.raw().post(
            "/api/kb",
            json={
                "categoria": "geral", "titulo": "A", "corpo_md": "x", "motivo": "m",
                "campo_desconhecido": "boom",
            },
        )
        assert resp.status_code == 422


class TestUpdateAndArchive:
    def test_update_replaces_fields_and_rename(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client, _USER, "owner")
        create = client.raw().post(
            "/api/kb",
            json={"slug": "old-slug", "categoria": "geral", "titulo": "A", "corpo_md": "x", "motivo": "m"},
        )
        assert create.status_code == 201

        resp = client.raw().put(
            "/api/kb/old-slug",
            json={"novo_slug": "new-slug", "titulo": "B", "motivo": "renomeando"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["slug"] == "new-slug"
        assert body["titulo"] == "B"
        assert body["current_revision"]["rev_no"] == 2

    def test_archive_sets_flag(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client, _USER, "owner")
        client.raw().post(
            "/api/kb",
            json={"slug": "to-archive", "categoria": "geral", "titulo": "A", "corpo_md": "x", "motivo": "m"},
        )
        resp = client.raw().post("/api/kb/to-archive/archive", json={"motivo": "obsoleto"})
        assert resp.status_code == 200
        assert resp.json()["arquivado"] is True


class TestRevisions:
    def test_revisions_list_newest_first(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client, _USER, "owner")
        client.raw().post(
            "/api/kb",
            json={"slug": "rev-test", "categoria": "geral", "titulo": "A", "corpo_md": "x", "motivo": "m1"},
        )
        client.raw().put("/api/kb/rev-test", json={"titulo": "B", "motivo": "m2"})
        resp = client.raw().get("/api/kb/rev-test/revisions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert [r["rev_no"] for r in body["items"]] == [2, 1]
        assert body["items"][0]["motivo"] == "m2"


class TestAgentWriteWithAssertion:
    def teardown_method(self, method):
        app.dependency_overrides.pop(get_approval_assertion_keys, None)

    def test_valid_assertion_creates_with_agent_provenance(self, client, store, set_auth):
        _use_assertion_secret()
        approved_by = UUID("00000000-0000-4000-8000-0000000000ff")
        _seed_role(client, approved_by, "owner")
        set_auth(_product_ctx(scopes=["academia:kb:write", "academia:read"]))

        body_dict = {"slug": "agent-entry", "categoria": "geral", "titulo": "A", "corpo_md": "x", "motivo": "m"}
        raw_body = canonical_body(body_dict)
        token = sign_assertion(
            secret=_SECRET,
            org_id=_ORG,
            agent_id=_AGENT,
            approved_by=approved_by,
            tool="academia.kb.escrever",
            method="POST",
            path="/api/kb",
            body=raw_body,
        )
        resp = client.raw().post(
            "/api/kb",
            content=raw_body,
            headers={"content-type": "application/json", "X-Approval-Assertion": token},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["current_revision"]["author_kind"] == "agent"

        revs = client.raw().get("/api/kb/agent-entry/revisions").json()
        rev = revs["items"][0]
        assert rev["user_id"] == str(approved_by)
        assert rev["agent_id"] == str(_AGENT)
        assert rev["approval_id"] is not None

    def test_missing_assertion_for_non_personal_product_token_is_403(self, client, store, set_auth):
        _use_assertion_secret()
        set_auth(_product_ctx(scopes=["academia:kb:write"]))
        body_dict = {"slug": "no-assertion", "categoria": "geral", "titulo": "A", "corpo_md": "x", "motivo": "m"}
        resp = client.raw().post(
            "/api/kb",
            content=canonical_body(body_dict),
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "assertion_invalid"

    def test_human_personal_token_writes_without_assertion(self, client, store, set_auth):
        minted_by = UUID("00000000-0000-4000-8000-0000000000aa")
        ctx = _product_ctx(scopes=["academia:kb:write", "academia:read"], human_personal=True)
        ctx = ctx._replace(minted_by=minted_by)
        set_auth(ctx)
        body_dict = {"slug": "personal-entry", "categoria": "geral", "titulo": "A", "corpo_md": "x", "motivo": "m"}
        resp = client.raw().post(
            "/api/kb",
            content=canonical_body(body_dict),
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 201, resp.text
        revs = client.raw().get("/api/kb/personal-entry/revisions").json()
        rev = revs["items"][0]
        assert rev["author_kind"] == "human"
        assert rev["user_id"] == str(minted_by)
        assert rev["approval_id"] is None
