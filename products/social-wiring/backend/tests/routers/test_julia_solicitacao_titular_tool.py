"""`POST /api/julia/ferramentas/solicitacao-titular`: Julia (the model) registers a lead's data-subject request.

Same auth family as every Julia tool (product token, scope `social-wiring:lais-tools`, issuer `agents`; strict `== 401`
without a credential). It only RECORDS (and tells the admins): nothing is deleted. The org is the token's, never the body's."""
from __future__ import annotations

from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from noctusai_lib.api.auth.session import AuthContext

from tests.support.julia_world import CONNECTION_ID, LEAD_CHAT, ORG_ID, OTHER_ORG_ID, World

_SCOPE = "social-wiring:lais-tools"
URL = "/api/julia/ferramentas/solicitacao-titular"


def _product(*, scopes=(_SCOPE,), issuer="agents", org=ORG_ID):
    return AuthContext(org_id=UUID(org), caller_kind="product", user_id=None, scopes=list(scopes),
                       raw_token="t", api_token_id=uuid4(), issuer=issuer)


@pytest.fixture
def tool(client):
    from app.dependencies import get_auth_context
    from app.main import app
    from app.routers.julia_ferramentas_router import get_ferramentas_client

    w = World()
    w.seed_connection()
    lead = {"id": str(uuid4()), "org_id": ORG_ID, "connection_id": CONNECTION_ID, "chat_id": LEAD_CHAT, "gen": 0}
    w.sw.table("julia_contatos").insert(lead).execute()
    app.dependency_overrides[get_ferramentas_client] = lambda: w.sw
    prev = app.dependency_overrides.get(get_auth_context)

    class T:
        raw = client.raw()
        world = w
        lead_ref = lead["id"]

        def as_ctx(self, ctx):
            app.dependency_overrides[get_auth_context] = lambda: ctx

        def post(self, body):
            with patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=w.root):
                return self.raw.post(URL, json=body)

    yield T()
    app.dependency_overrides.pop(get_ferramentas_client, None)
    if prev is None:
        app.dependency_overrides.pop(get_auth_context, None)
    else:
        app.dependency_overrides[get_auth_context] = prev


def _body(t, **over):
    return {"lead_ref": t.lead_ref, "tipo": "eliminacao", "trecho": "quero apagar meus dados", **over}


class TestAuth:
    def test_no_credential_is_exactly_401(self, tool):
        assert tool.post(_body(tool)).status_code == 401

    def test_a_human_session_is_403(self, tool):
        tool.as_ctx(AuthContext(org_id=UUID(ORG_ID), caller_kind="user", user_id=uuid4(), scopes=[], raw_token="s", api_token_id=None))
        assert tool.post(_body(tool)).status_code == 403

    def test_missing_scope_and_foreign_issuer_are_403(self, tool):
        tool.as_ctx(_product(scopes=["social-wiring:one-chat:read"]))
        assert tool.post(_body(tool)).status_code == 403
        tool.as_ctx(_product(issuer="outro"))
        assert tool.post(_body(tool)).status_code == 403


class TestRegistrar:
    def test_it_records_with_a_15_day_deadline_and_tells_the_admins(self, tool):
        tool.as_ctx(_product())
        r = tool.post(_body(tool, chat_id=LEAD_CHAT))
        assert r.status_code == 200
        data = r.json()["data"]
        [linha] = tool.world.rows("julia_solicitacoes_titular")
        assert data == {"id": linha["id"], "prazo_em": linha["prazo_em"]}
        assert linha["status"] == "aberta" and linha["tipo"] == "eliminacao" and linha["contato_id"] == tool.lead_ref
        assert linha["notificacao_status"] == "enviada"
        assert tool.world.contato() is not None and tool.world.agents.leads_apagados == []

    def test_a_lead_of_another_org_is_404_and_the_body_cannot_name_an_org(self, tool):
        tool.as_ctx(_product(org=OTHER_ORG_ID))
        assert tool.post(_body(tool)).status_code == 404
        tool.as_ctx(_product())
        assert tool.post(_body(tool, org_id=OTHER_ORG_ID)).status_code == 422
        assert tool.world.rows("julia_solicitacoes_titular") == []

    def test_bad_tipo_or_empty_excerpt_is_422(self, tool):
        tool.as_ctx(_product())
        assert tool.post(_body(tool, tipo="apagar_tudo")).status_code == 422
        assert tool.post(_body(tool, trecho="")).status_code == 422
