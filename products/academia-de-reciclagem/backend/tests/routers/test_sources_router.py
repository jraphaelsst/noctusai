"""Tests for `app/routers/sources_router.py` — contract §B.5."""
from __future__ import annotations

from uuid import UUID

from noctusai_lib.api.auth.session.types import AuthContext

_ORG = UUID("00000000-0000-4000-8000-0000000000aa")
_USER = UUID("00000000-0000-4000-8000-0000000000bb")


def _user_ctx() -> AuthContext:
    return AuthContext(
        org_id=_ORG, caller_kind="user", user_id=_USER, scopes=[],
        raw_token="s1", api_token_id=None,
    )


def _seed_role(client, role: str = "owner") -> None:
    client.mock_supabase.set_table_data(
        "noctus_users", [{"id": str(_USER), "org_id": str(_ORG), "org_role": role}]
    )


_BASE = {
    "url": "https://example.gov.br/regra",
    "titulo": "Regra X",
    "trecho_citado": "trecho",
    "resumo": "resumo",
    "vigencia_confirmada": True,
}


class TestAuthBoundary:
    def test_unauthenticated_is_401(self, client, store):
        resp = client.raw().post("/api/sources", json={**_BASE, "kb_slug": "x"})
        assert resp.status_code == 401


class TestCreate:
    def test_unknown_kb_slug_is_404(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        resp = client.raw().post("/api/sources", json={**_BASE, "kb_slug": "nao-existe"})
        assert resp.status_code == 404

    def test_success_not_on_allowlist_gets_aviso(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        client.raw().post(
            "/api/kb",
            json={"slug": "regra-x", "categoria": "geral", "titulo": "A", "corpo_md": "x", "motivo": "m"},
        )
        resp = client.raw().post("/api/sources", json={**_BASE, "kb_slug": "regra-x"})
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["kb_slug"] == "regra-x"
        assert body["accessed_at"]
        # Empty allowlist by default (contract §B.5's aviso behaviour) —
        # every host is "off allowlist" until an operator configures one.
        assert body["aviso"] is not None

    def test_malformed_url_is_422(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        resp = client.raw().post("/api/sources", json={**_BASE, "url": "not-a-url", "kb_slug": "x"})
        assert resp.status_code == 422
