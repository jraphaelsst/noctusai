"""Assistente IA do negócio (contract §E2) — Claude via the seed LLM stack.

The model call is the seed `FakeProvider` behind the route's `get_gerador_texto`
seam, so the assertions are about what igig SENDS (provider, model, the
context, no response cache for personal data) and how it answers failures —
not about any model's prose.

LGPD-gated (`igig.assistente_negocio`, `app/services/ai_consent_features.py`,
`default_granted=False`): the `_grant_assistente_negocio_consent` autouse
fixture below pre-seeds a granted `ai_consent` row so the happy-path tests
in this file exercise the ROUTE, not the consent guard — `TestConsentGuards`
at the end covers the refused-without-consent path.
"""
import pytest
from noctusai_lib.integrations.llm import LLMNotConfigured
from noctusai_lib.integrations.llm.providers.fake_provider import FakeProvider

from app.dependencies import coerce_org_uuid
from app.routers.assistente_router import get_gerador_texto
from app.services.assistente import MODELO_PADRAO_ID, GeradorTexto

ORG = str(coerce_org_uuid("test-org-123"))


@pytest.fixture
def api(crm_api):
    return crm_api


@pytest.fixture(autouse=True)
def _grant_assistente_negocio_consent(api):
    """`igig.assistente_negocio` is opt-in (`default_granted=False`) — without
    this, every happy-path test below would get HTTP 412 instead of exercising
    the route. `api._mock_supabase` is the SAME mock bound to the consent
    module by `bind_consent_module_to_mock(...)` in the `client` fixture
    (`crm_api` only overrides `get_db`/`get_admin_db` for the pipeline routes,
    not the consent guard's own admin client)."""
    api._mock_supabase.set_table_data("ai_consent", [{
        "feature_key": "igig.assistente_negocio",
        "granted": True, "user_id": "test-user-123",
        "granted_at": "2026-09-28T00:00:00Z", "revoked_at": None,
    }])


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
        assert kwargs["model"] == MODELO_PADRAO_ID, "pinned (leftovers item 16), not whatever sorts first"
        assert kwargs["cache"] is False, "personal data never goes to the response cache"
        assert kwargs["org_id"] == ORG
        [chamada] = chat.provider.calls
        prompt = "\n".join(str(m.get("content")) for m in chamada["messages"])
        assert "Padaria Sol" in prompt and "Proposta Retainer" in prompt
        assert "Leads" in prompt, "the stage label, not its id"

    def test_includes_the_pre_qualificacao_fields(self, api, igig_db, core_db, chat):
        """achado #8: the aba's own text says the assistant "lê o lead", but
        `montar_contexto` used to drop nicho/dores/orçamento/canais — exactly
        the four fields a formulário lead carries and the OTHER módulo-1
        sources (manual/WhatsApp/Meta) don't have."""
        core_db.table("organizations").insert({"id": ORG, "nome": "Agência Teste"}).execute()
        publico = api.raw().post(
            "/api/comercial/leads/publico",
            json={
                "org_id": ORG, "nome": "Ana", "empresa": "Padaria Sol",
                "nicho": "Alimentação", "canais_atuais": "Instagram, TikTok",
                "dores": "pouco alcance", "orcamento_disponivel": 5000,
            },
        )
        assert publico.status_code == 201, publico.text
        [negocio_pre] = [n for n in igig_db.table("negocio")._data]

        resp = api.post(f"/api/comercial/negocios/{negocio_pre['id']}/assistente",
                        json={"acao": "resumo"})
        assert resp.status_code == 200, resp.text
        prompt = "\n".join(str(m.get("content")) for m in chat.provider.calls[0]["messages"])
        assert "Alimentação" in prompt
        assert "Instagram, TikTok" in prompt
        assert "pouco alcance" in prompt
        assert "5000" in prompt

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

    def test_an_explicit_gerador_texto_model_overrides_the_pin(self, api, negocio):
        """The seam's own override still works — a caller (tests, a future
        operator setting) is not locked out of the pin."""
        from app.main import app

        fake = _Chat()
        app.dependency_overrides[get_gerador_texto] = lambda: GeradorTexto(chat=fake, model="claude-opus-5")
        try:
            resp = api.post(f"/api/comercial/negocios/{negocio['id']}/assistente", json={"acao": "resumo"})
        finally:
            app.dependency_overrides.pop(get_gerador_texto, None)
        assert resp.status_code == 200, resp.text
        assert fake.kwargs[0]["model"] == "claude-opus-5"


class TestConsentGuards:
    """`igig.assistente_negocio` is opt-in (`default_granted=False`) — a
    caller without a granted `ai_consent` row must be refused with HTTP 412
    `AI_CONSENT_REQUIRED`, never reaching the LLM call."""

    def test_returns_401_before_412_when_unauthenticated(self, api):
        """Auth is checked first — an unauthenticated caller gets 401, never
        412, regardless of consent state (strict `== 401`, not `in (401, 412)`
        — see `KB § PATTERNS/compliance/auth-boundary-false-green.md`)."""
        resp = api.raw().post("/api/comercial/negocios/x/assistente", json={"acao": "resumo"})
        assert resp.status_code == 401

    def test_returns_412_when_no_decision_and_default_false(self, api, negocio, chat):
        # Override the autouse fixture's grant — no stored decision at all.
        api._mock_supabase.set_table_data("ai_consent", [])
        resp = api.post(f"/api/comercial/negocios/{negocio['id']}/assistente", json={"acao": "resumo"})
        assert resp.status_code == 412
        assert resp.json()["error"]["code"] == "AI_CONSENT_REQUIRED"
        assert not chat.kwargs, "the LLM must never be called without consent"

    def test_returns_412_when_explicitly_revoked(self, api, negocio, chat):
        api._mock_supabase.set_table_data("ai_consent", [{
            "feature_key": "igig.assistente_negocio",
            "granted": False, "user_id": "test-user-123",
            "granted_at": None, "revoked_at": "2026-09-28T00:00:00Z",
        }])
        resp = api.post(f"/api/comercial/negocios/{negocio['id']}/assistente", json={"acao": "resumo"})
        assert resp.status_code == 412
        assert resp.json()["error"]["code"] == "AI_CONSENT_REQUIRED"
        assert not chat.kwargs

    def test_succeeds_when_consent_granted(self, api, negocio, chat):
        """The autouse fixture already grants consent — this pins the
        happy path explicitly against the guard (belt-and-suspenders with
        `TestAssistente.test_resumo_uses_claude_with_the_deal_context`)."""
        resp = api.post(f"/api/comercial/negocios/{negocio['id']}/assistente", json={"acao": "resumo"})
        assert resp.status_code == 200, resp.text
        assert chat.kwargs


class TestModeloPadrao:
    def test_is_pinned_to_sonnet_4_6(self):
        from app.services.assistente import modelo_padrao

        assert modelo_padrao() == MODELO_PADRAO_ID == "claude-sonnet-4-6"

    def test_fails_loudly_if_the_pin_ever_leaves_the_catalog(self, monkeypatch):
        import app.services.assistente as assistente_mod

        monkeypatch.setattr(assistente_mod, "MODELO_PADRAO_ID", "modelo-que-nao-existe")
        with pytest.raises(RuntimeError, match="não está no catálogo"):
            assistente_mod.modelo_padrao()
