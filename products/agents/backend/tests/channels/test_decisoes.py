"""``POST /api/channels/agents/{agent_key}/decisoes/{chave}`` — a transport-side choice decided by the rule of the
agent version's decision ROW (``agent_version_decisoes``, D13): the first user is the Meta first-contact template
(``abordagem-meta``). The caller carries no rule; the fallback is the option the row flags ``padrao``. The model
is the seed's ``FakeProvider``; nothing of ours is patched."""
from __future__ import annotations

from uuid import uuid4

from noctusai_lib.integrations.llm import ChatToolsResponse, FakeProvider, LLMUsage, ToolCall

from tests.channels.julia_v2 import JULIA_KEY
from tests.channels.conftest import OTHER_ORG, turn_body

URL = f"/api/channels/agents/{JULIA_KEY}/decisoes/abordagem-meta"
BODY = {"opcoes": ["template_a", "template_b"], "dados": {"codigo_imovel": "ONE9551", "campanha": "Casas Granja"}}


def _escolha(args: dict, cost: float = 0.0007) -> FakeProvider:
    return FakeProvider(tool_responses=[ChatToolsResponse(
        tool_calls=(ToolCall("d", "registrar_escolha", args),), finish_reason="tool_calls",
        usage=LLMUsage(80, 20, 0, 0, cost))])


def _post(chan, body=None, url=URL, **kw):
    with chan.as_token(**kw):
        return chan.request("POST", url, json=body if body is not None else BODY)


class TestDecisao:
    def test_the_rule_of_the_version_row_decides(self, chan):
        chan.seed_agent(com_decisao=True)
        chan.use_provider(_escolha({"escolha": "template_b", "motivo": "Veio pelo imóvel ONE9551; tel 11 99999-0000"}))
        resp = _post(chan)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["escolha"] == "template_b" and body["regra"] == "versao"
        assert "99999" not in body["motivo"]
        assert body["usage"] == {"custo_usd": 0.0007, "tokens_entrada": 80, "tokens_saida": 20}
        call = next(c for c in chan.provider.calls if c["method"] == "chat_with_tools")
        assert call["tool_choice"] == "registrar_escolha"
        assert call["api_key"] == "sk-org-a-key"
        system, user = call["messages"][0].content, call["messages"][1].content
        # every word of the call is a row: the system text (with the rule), the labels, the tool description
        assert "txt:decisao.sistema regra: escolha por origem" == system
        assert user.startswith("txt:decisao.rotulo_opcoes template_a, template_b")
        assert "codigo_imovel: ONE9551" in user and "txt:decisao.rotulo_dados" in user
        [tool] = call["tools"]
        assert tool.description == "desc:registrar_escolha"

    def test_the_caller_cannot_bring_a_rule_and_the_old_field_is_ignored(self, chan):
        chan.seed_agent(com_decisao=True)
        chan.use_provider(_escolha({"escolha": "template_a", "motivo": "x"}))
        resp = _post(chan, {**BODY, "regra_padrao": "Sempre template_b (v1 field)"})
        assert resp.status_code == 200
        system = next(c for c in chan.provider.calls if c["method"] == "chat_with_tools")["messages"][0].content
        assert "template_b (v1 field)" not in system

    def test_a_row_without_a_rule_answers_its_padrao_option_without_a_model_call(self, chan):
        chan.seed_agent(com_decisao="sem_regra")
        chan.use_provider(_escolha({"escolha": "template_b", "motivo": "x"}))
        body = _post(chan).json()
        assert (body["escolha"], body["regra"]) == ("template_a", "padrao_da_versao")
        assert [c for c in chan.provider.calls if c["method"] == "chat_with_tools"] == []

    def test_a_model_that_cannot_decide_falls_back_to_the_padrao_option_never_a_guess(self, chan):
        chan.seed_agent(com_decisao=True)
        chan.use_provider(_escolha({"escolha": "agressiva", "motivo": "x"}))
        body = _post(chan).json()
        assert (body["escolha"], body["regra"]) == ("template_a", "padrao_da_versao")

    def test_no_tool_call_falls_back_to_the_padrao_option(self, chan):
        chan.seed_agent(com_decisao=True)
        chan.use_provider(FakeProvider(tool_responses=["só texto"]))
        assert _post(chan).json()["regra"] == "padrao_da_versao"

    def test_an_unknown_decision_is_404(self, chan):
        chan.seed_agent()
        resp = _post(chan)
        assert resp.status_code == 404 and resp.json()["code"] == "decisao_nao_encontrada"

    def test_options_outside_the_row_are_422(self, chan):
        chan.seed_agent(com_decisao=True)
        resp = _post(chan, {**BODY, "opcoes": ["template_a", "outra"]})
        assert resp.status_code == 422 and resp.json()["code"] == "invalid_field"

    def test_no_published_version_is_409(self, chan):
        chan.seed_agent(publish=False)
        chan.use_provider(_escolha({"escolha": "template_b", "motivo": "x"}))
        resp = _post(chan)
        assert resp.status_code == 409 and resp.json()["code"] == "no_active_version"

    def test_no_org_key_is_424(self, chan):
        chan.seed_agent(com_decisao=True)
        chan.use_provider(_escolha({"escolha": "template_b", "motivo": "x"}), key_for_org=False)
        resp = _post(chan)
        assert resp.status_code == 424 and resp.json()["code"] == "llm_not_configured"

    def test_bad_bodies_and_keys_are_422(self, chan):
        chan.seed_agent(com_decisao=True)
        chan.use_provider(_escolha({"escolha": "template_b", "motivo": "x"}))
        for body in (
            {**BODY, "opcoes": ["template_a"]},
            {**BODY, "opcoes": ["template_a", "template_a"]},
            {**BODY, "x": 1},
            {**BODY, "dados": {"a": "x" * 501}},
        ):
            resp = _post(chan, body)
            assert resp.status_code == 422 and resp.json()["code"] == "invalid_field", body
        resp = _post(chan, url=f"/api/channels/agents/{JULIA_KEY}/decisoes/Abordagem_Meta")
        assert resp.status_code == 422 and resp.json()["code"] == "invalid_field"


class TestDecisaoAuth:
    def test_without_credential_is_401(self, chan):
        chan.seed_agent(com_decisao=True)
        assert chan.request("POST", URL, json=BODY).status_code == 401

    def test_human_session_is_403(self, chan):
        chan.seed_agent(com_decisao=True)
        assert chan.client.post(URL, json=BODY).status_code == 403

    def test_a_token_bound_to_another_agent_is_403(self, chan):
        chan.seed_agent(com_decisao=True)
        chan.use_provider(_escolha({"escolha": "template_b", "motivo": "x"}))
        resp = _post(chan, principal=uuid4())
        assert resp.status_code == 403 and resp.json()["code"] == "agent_not_allowed"

    def test_another_orgs_token_cannot_reach_this_agent(self, chan):
        chan.seed_agent(com_decisao=True)
        chan.use_provider(_escolha({"escolha": "template_b", "motivo": "x"}))
        resp = _post(chan, org_id=OTHER_ORG)
        assert resp.status_code == 404 and resp.json()["code"] == "agent_not_found"


class TestDecisionRowsStayOutOfTheConversation:
    def test_the_rule_is_never_in_the_turn_prompt(self, chan):
        chan.seed_agent(com_decisao=True)
        chan.use_provider(FakeProvider(tool_responses=["Você procura comprar ou alugar?"]))
        assert chan.turn(turn_body("Oi")).status_code == 200
        call = next(c for c in chan.provider.calls if c["method"] == "chat_with_tools")
        system = "\n".join(m.content for m in call["messages"] if m.role == "system")
        assert "escolha por origem" not in system
        assert "Persona do teste." in system
