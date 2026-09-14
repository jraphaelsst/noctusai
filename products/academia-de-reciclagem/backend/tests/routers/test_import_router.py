"""Tests for `app/routers/import_router.py` — contract §B.6.

Uses A1's `FakeKnowledgeStore` (`store` fixture) via
`app.dependency_overrides[get_store]` and `set_auth` to substitute
arbitrary `AuthContext`s — both from `tests/routers/conftest.py`, same
pattern every other router suite in this package uses.

Every fixture bundle line below is synthetic, neutral, PT-BR-flavoured
placeholder text — never real client content (this repo is public).
"""
from __future__ import annotations

import json
from uuid import UUID, uuid4

from noctusai_lib.api.auth.session.types import AuthContext

_ORG = UUID("00000000-0000-4000-8000-0000000000aa")
_ADMIN_USER = UUID("00000000-0000-4000-8000-0000000000bb")
_MEMBER_USER = UUID("00000000-0000-4000-8000-0000000000cc")


def _admin_ctx() -> AuthContext:
    return AuthContext(
        org_id=_ORG, caller_kind="user", user_id=_ADMIN_USER, scopes=[],
        raw_token="s-admin", api_token_id=None,
    )


def _member_ctx() -> AuthContext:
    return AuthContext(
        org_id=_ORG, caller_kind="user", user_id=_MEMBER_USER, scopes=[],
        raw_token="s-member", api_token_id=None,
    )


def _product_ctx(*, scopes: list[str] | None = None) -> AuthContext:
    # Even a product token carrying the `academia:import` scope must be
    # refused (contract §B.0: "never granted to an agent") — the router
    # dependency refuses on `caller_kind` alone, never on scope
    # presence/absence, so this is the stronger case to exercise.
    return AuthContext(
        org_id=_ORG, caller_kind="product", user_id=None,
        scopes=scopes if scopes is not None else ["academia:import"],
        raw_token="pk_test", api_token_id=uuid4(),
    )


def _seed_role(client, user_id: UUID, role: str) -> None:
    client.mock_supabase.set_table_data(
        "noctus_users", [{"id": str(user_id), "org_id": str(_ORG), "org_role": role}]
    )


def _bundle_line(
    *,
    path: str = "KNOWLEDGE-BASE/GERAL/exemplo.md",
    content: str = "# Exemplo\n\nConteudo de exemplo sem segredos, apenas texto comum.",
    git_sha: str = "abc123",
    git_author_raw: str = "Fulano da Silva",
    git_committed_at: str = "2026-01-01T00:00:00Z",
    git_message: str = "add exemplo",
) -> dict:
    return {
        "path": path,
        "git_sha": git_sha,
        "git_author_raw": git_author_raw,
        "git_committed_at": git_committed_at,
        "git_message": git_message,
        "content": content,
    }


def _jsonl_body(*lines: dict) -> bytes:
    return ("\n".join(json.dumps(ln, ensure_ascii=False) for ln in lines) + "\n").encode("utf-8")


def _post_jsonl(client, body: bytes):
    return client.raw().post(
        "/api/import",
        content=body,
        headers={"content-type": "application/x-ndjson"},
    )


class TestAuthBoundary:
    def test_unauthenticated_is_401(self, client, store):
        resp = client.raw().post("/api/import", content=b"", headers={"content-type": "application/x-ndjson"})
        assert resp.status_code == 401

    def test_member_is_403_role_missing(self, client, store, set_auth):
        set_auth(_member_ctx())
        _seed_role(client, _MEMBER_USER, "member")
        resp = _post_jsonl(client, _jsonl_body(_bundle_line()))
        assert resp.status_code == 403
        assert resp.json()["code"] == "role_missing"

    def test_product_token_is_403_product_forbidden(self, client, store, set_auth):
        set_auth(_product_ctx())
        resp = _post_jsonl(client, _jsonl_body(_bundle_line()))
        assert resp.status_code == 403
        assert resp.json()["code"] == "product_forbidden"

    def test_product_token_without_the_scope_is_still_product_forbidden(self, client, store, set_auth):
        # The refusal is unconditional on caller_kind, not a side effect
        # of the scope simply being absent.
        set_auth(_product_ctx(scopes=[]))
        resp = _post_jsonl(client, _jsonl_body(_bundle_line()))
        assert resp.status_code == 403
        assert resp.json()["code"] == "product_forbidden"


class TestSuccessfulImport:
    def test_report_shape_and_counts(self, client, store, set_auth):
        set_auth(_admin_ctx())
        _seed_role(client, _ADMIN_USER, "owner")

        resp = _post_jsonl(client, _jsonl_body(_bundle_line()))
        assert resp.status_code == 200, resp.text
        body = resp.json()

        verificacao = body["verificacao"]
        assert verificacao["revisoes_git"] == 1
        assert verificacao["revisoes_importadas"] == 1
        assert verificacao["entidades"] == {"kb_entry": 1}
        assert verificacao["hashes_head_ok"] is True
        assert verificacao["codigos"] == {"D": 0, "Q": 0, "T": 0}
        assert body["avisos"] == []

        assert len(store.kb_revisions) == 1
        assert len(store.kb_entries) == 1
        assert store.kb_entries[0]["slug"] == "geral-exemplo"

    def test_idempotent_repost_writes_zero_new_revisions(self, client, store, set_auth):
        set_auth(_admin_ctx())
        _seed_role(client, _ADMIN_USER, "owner")
        body = _jsonl_body(_bundle_line())

        first = _post_jsonl(client, body)
        assert first.status_code == 200, first.text
        revisions_after_first = len(store.kb_revisions)
        assert revisions_after_first == 1

        second = _post_jsonl(client, body)
        assert second.status_code == 200, second.text
        # `revisoes_importadas` counts `import_entity` CALLS, not net-new
        # revisions (contract §B.6 settled definition) — it stays 1 on
        # replay. Idempotency is proven on the store's revision count.
        assert second.json()["verificacao"]["revisoes_importadas"] == 1
        assert len(store.kb_revisions) == revisions_after_first

    def test_multipart_upload_works_the_same_as_jsonl(self, client, store, set_auth):
        set_auth(_admin_ctx())
        _seed_role(client, _ADMIN_USER, "owner")
        body = _jsonl_body(_bundle_line(path="KNOWLEDGE-BASE/GERAL/multipart.md"))

        resp = client.raw().post(
            "/api/import",
            files={"bundle": ("bundle.jsonl", body, "application/x-ndjson")},
        )
        assert resp.status_code == 200, resp.text
        verificacao = resp.json()["verificacao"]
        assert verificacao["revisoes_importadas"] == 1
        assert verificacao["entidades"] == {"kb_entry": 1}
        assert len(store.kb_revisions) == 1


class TestRefusals:
    def test_malformed_json_line_is_422_bundle_invalid(self, client, store, set_auth):
        set_auth(_admin_ctx())
        _seed_role(client, _ADMIN_USER, "owner")

        resp = _post_jsonl(client, b"this is not json\n")
        assert resp.status_code == 422
        assert resp.json()["code"] == "bundle_invalid"

    def test_too_many_lines_is_422_bundle_too_large(self, client, store, set_auth):
        set_auth(_admin_ctx())
        _seed_role(client, _ADMIN_USER, "owner")

        body = ("x\n" * 5001).encode("utf-8")
        resp = _post_jsonl(client, body)
        assert resp.status_code == 422
        assert resp.json()["code"] == "bundle_too_large"

    def test_path_denylist_is_422_secret_detected(self, client, store, set_auth):
        set_auth(_admin_ctx())
        _seed_role(client, _ADMIN_USER, "owner")

        line = _bundle_line(path="config/.env.production", content="ALGO=valor")
        resp = _post_jsonl(client, _jsonl_body(line))
        assert resp.status_code == 422
        assert resp.json()["code"] == "secret_detected"
        assert "config/.env.production" in resp.json()["detail"]

    def test_content_secret_scan_is_422_secret_detected_names_path_not_value(self, client, store, set_auth):
        set_auth(_admin_ctx())
        _seed_role(client, _ADMIN_USER, "owner")

        secret_token = "ghp_1234567890abcdefghijklmnopqrstuvwx"
        line = _bundle_line(
            path="KNOWLEDGE-BASE/GERAL/leak.md",
            content=f"# Leak\n\ntoken: {secret_token}",
        )
        resp = _post_jsonl(client, _jsonl_body(line))
        assert resp.status_code == 422
        payload = resp.json()
        assert payload["code"] == "secret_detected"
        assert "KNOWLEDGE-BASE/GERAL/leak.md" in payload["detail"]
        assert secret_token not in payload["detail"]
