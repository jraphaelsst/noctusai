"""Assistente IA do negócio (contract §E2) — Claude via the seed LLM stack.

The model call is the seed `FakeProvider` behind the route's `get_gerador_texto`
seam, so the assertions are about what igig SENDS (provider, model, the
context, no response cache for personal data) and how it answers failures —
not about any model's prose.
"""
import pytest
from noctusai_lib.integrations.llm import LLMNotConfigured
from noctusai_lib.integrations.llm.models import models_for
from noctusai_lib.integrations.llm.providers.fake_provider import FakeProvider

from app.dependencies import coerce_org_uuid
from app.routers.assistente_router import get_gerador_texto
from app.services.assistente import GeradorTexto

ORG = str(coerce_org_uuid("test-org-123"))


@pytest.fixture
def api(crm_api):
    return crm_api


@pytest.fixture
def negocio(api, igig_db) -> dict:
    resp = api.post("/api/comercial/negocios", json={
        "lead": {"nome": "João", "empresa": "Padaria Sol", "email": "joao@sol.com"},
        "valor_estimado": 3000,
    })
    assert resp.status_code == 201, resp.text
    dados = resp.json()["data"]
    igig_db.table("orcamento").insert({
        "org_id": ORG, "negocio_id": dados["id"], "lead_id": dados["lead_id"],
        "titulo": "Proposta Retainer", "versao": 1, "status": "enviado", "total_mensal": 2500,
    }).execute()
    return dados


class _Chat:
    """`chat_completion`-shaped callable backed by the seed FakeProvider —
    records the kwargs igig passes (the provider/model/cache choice is what
    this seam exists to pin)."""

    def __init__(self, respostas=("Resumo: lead quente.",), erro=None):
        self.provider = FakeProvider(chat_responses=list(respostas))
        self.kwargs: list[dict] = []
        self.erro = erro

    async def __call__(self, messages, **kwargs):
        self.kwargs.append(kwargs)
        if self.erro:
            raise self.erro
        return await self.provider.chat_completion(
            messages, model=kwargs["model"], api_key="fake", temperature=kwargs["temperature"],
            max_tokens=kwargs["max_tokens"],
        )


@pytest.fixture
def chat(api):
    from app.main import app

    fake = _Chat()
    app.dependency_overrides[get_gerador_texto] = lambda: GeradorTexto(chat=fake)
    yield fake
    app.dependency_overrides.pop(get_gerador_texto, None)


class TestAssistente:
    def test_requires_auth(self, api):
        resp = api.raw().post("/api/comercial/negocios/x/assistente", json={"acao": "resumo"})
        assert resp.status_code == 401

    def test_resumo_uses_claude_with_the_deal_context(self, api, negocio, chat):
        resp = api.post(f"/api/comercial/negocios/{negocio['id']}/assistente", json={"acao": "resumo"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"] == {"texto": "Resumo: lead quente."}

        [kwargs] = chat.kwargs
        assert kwargs["provider"] == "anthropic"
        assert kwargs["model"] == models_for("anthropic", "chat")[0].id
        assert kwargs["cache"] is False, "personal data never goes to the response cache"
        assert kwargs["org_id"] == ORG
        [chamada] = chat.provider.calls
        prompt = "\n".join(str(m.get("content")) for m in chamada["messages"])
        assert "Padaria Sol" in prompt and "Proposta Retainer" in prompt
        assert "Leads" in prompt, "the stage label, not its id"

    def test_rascunho_names_the_channel(self, api, negocio, chat):
        resp = api.post(f"/api/comercial/negocios/{negocio['id']}/assistente",
                        json={"acao": "rascunho_mensagem", "canal": "email"})
        assert resp.status_code == 200
        prompt = "\n".join(str(m.get("content")) for m in chat.provider.calls[0]["messages"])
        assert "Assunto:" in prompt

    def test_unknown_negocio_is_404(self, api, chat):
        resp = api.post("/api/comercial/negocios/nao-existe/assistente", json={"acao": "resumo"})
        assert resp.status_code == 404

    def test_invalid_acao_is_422(self, api, negocio, chat):
        resp = api.post(f"/api/comercial/negocios/{negocio['id']}/assistente", json={"acao": "vender"})
        assert resp.status_code == 422

    def test_missing_key_answers_a_machine_code(self, api, negocio):
        from app.main import app

        fake = _Chat(erro=LLMNotConfigured("anthropic"))
        app.dependency_overrides[get_gerador_texto] = lambda: GeradorTexto(chat=fake)
        try:
            resp = api.post(f"/api/comercial/negocios/{negocio['id']}/assistente",
                            json={"acao": "proxima_acao"})
        finally:
            app.dependency_overrides.pop(get_gerador_texto, None)
        assert resp.status_code == 503
        assert resp.json()["code"] == "ia_nao_configurada"
