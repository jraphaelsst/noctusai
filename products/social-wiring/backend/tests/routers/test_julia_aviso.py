"""Lais privacy notice (contract 11.2/11.3): public read, admin read/write.

Strict `== 401` / `== 403` per KB § PATTERNS/compliance/auth-boundary-false-green.md.
Seeds through `get_scoped_admin_client` (the cached instance the route reads).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.testing import (
    TEST_USER_ID,
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)

PUBLIC = "/api/public/lais/privacidade"
ADMIN = "/api/lais/agente/aviso"
ORG = "test-org-123"


def _mock(org_role):
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id=ORG, org_role=org_role))
    )
    mock_sb.set_table_data(
        "noctus_users", [{"id": TEST_USER_ID, "org_id": ORG, "org_role": org_role}]
    )
    return mock_sb


def _client_for(org_role, org_name="Empresa Exemplo"):
    mock_sb = _mock(org_role)
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.dependencies import get_scoped_admin_client
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        mock_sb.set_table_data(
            "organizations", [{"id": ORG, "nome": org_name}]
        )
        c = TestClient(app, raise_server_exceptions=True)
        c.sw = get_scoped_admin_client("social_wiring")
        c.core = mock_sb
        yield c


@pytest.fixture
def admin_client():
    yield from _client_for("owner")


@pytest.fixture
def member_client():
    yield from _client_for(None)


def _h():
    return {"Authorization": "Bearer test-token"}


def _body(**over):
    base = {
        "titulo": "Aviso de privacidade",
        "empresa_nome": "Empresa Exemplo",
        "contato_email": "privacidade@exemplo.test",
        "contato_whatsapp": None,
        "secoes": [{"n": "1", "title": "Controlador", "blocks": [{"p": "Empresa Exemplo."}, {"ul": ["a", "b"]}]}],
        "mensagem_inicial": "Oi! Sou a Julia da {empresa}. Dados: {link}",
    }
    base.update(over)
    return base


class TestAuth:
    def test_get_admin_without_token_is_401(self, admin_client):
        assert admin_client.get(ADMIN).status_code == 401

    def test_put_without_token_is_401(self, admin_client):
        assert admin_client.put(ADMIN, json=_body()).status_code == 401

    def test_member_can_read(self, member_client):
        assert member_client.get(ADMIN, headers=_h()).status_code == 200

    def test_member_cannot_write(self, member_client):
        assert member_client.put(ADMIN, json=_body(), headers=_h()).status_code == 403


class TestLazyDefault:
    def test_first_read_creates_default_template(self, admin_client):
        data = admin_client.get(ADMIN, headers=_h()).json()["data"]
        assert data["versao"] == 1
        assert "{link}" in data["mensagem_inicial"]
        assert "{empresa}" in data["mensagem_inicial"]
        titulos = " ".join(s["title"] for s in data["secoes"]).lower()
        for chave in ("controlador", "dados", "base legal", "direitos", "automatizadas"):
            assert chave in titulos
        texto = str(data["secoes"])
        assert "art. 7º, V" in texto and "180 dias" in texto and "OpenAI" in texto
        assert "apagar meus dados" in texto
        # Unknown controller data -> "a definir" + incomplete flag
        assert "a definir" in texto
        assert data["incompleto"] is True
        assert data["slug"]

    def test_second_read_is_stable_not_recreated(self, admin_client):
        a = admin_client.get(ADMIN, headers=_h()).json()["data"]
        b = admin_client.get(ADMIN, headers=_h()).json()["data"]
        assert a["slug"] == b["slug"]
        assert len(admin_client.sw.table("lais_aviso_privacidade").select("*").execute().data) == 1


class TestPut:
    def test_requires_link_placeholder(self, admin_client):
        r = admin_client.put(ADMIN, json=_body(mensagem_inicial="Oi sem link"), headers=_h())
        assert r.status_code == 422
        assert "link_obrigatorio" in r.text

    def test_versao_increments_and_slug_is_stable(self, admin_client):
        first = admin_client.get(ADMIN, headers=_h()).json()["data"]
        r1 = admin_client.put(ADMIN, json=_body(), headers=_h())
        assert r1.status_code == 200
        r2 = admin_client.put(ADMIN, json=_body(titulo="Novo"), headers=_h())
        d2 = r2.json()["data"]
        assert d2["versao"] == first["versao"] + 2
        assert d2["slug"] == first["slug"]
        assert d2["titulo"] == "Novo"
        assert d2["incompleto"] is False

    def test_rejects_malformed_block(self, admin_client):
        bad = _body(secoes=[{"n": "1", "title": "x", "blocks": [{"p": "a", "ul": ["b"]}]}])
        assert admin_client.put(ADMIN, json=bad, headers=_h()).status_code == 422


class TestSlug:
    def test_slug_is_url_safe_and_unique(self):
        from app.services import lais_aviso_service as svc

        assert svc.slugify("One Consultoria Imobiliária Ltda.") == "one-consultoria-imobiliaria-ltda"
        client = MockSupabaseClient()
        client.set_table_data(svc.TABLE, [{"slug": "one"}, {"slug": "one-2"}])
        assert svc._slug_unico(client, "one") == "one-3"


class TestPublic:
    def test_public_returns_only_notice_fields(self, admin_client):
        admin_client.get(ADMIN, headers=_h())
        slug = admin_client.sw.table("lais_aviso_privacidade").select("*").execute().data[0]["slug"]
        r = admin_client.get(f"{PUBLIC}/{slug}")  # no Authorization header
        assert r.status_code == 200
        data = r.json()["data"]
        assert set(data) == {
            "titulo", "empresa_nome", "contato_email", "contato_whatsapp",
            "secoes", "versao", "atualizado_em",
        }
        assert "org_id" not in r.text and TEST_USER_ID not in r.text
        assert "slug" not in data and "mensagem_inicial" not in data

    def test_unknown_slug_is_404(self, admin_client):
        assert admin_client.get(f"{PUBLIC}/nao-existe").status_code == 404
