"""``POST /api/channels/agents/{agent_key}/decisoes/{chave}`` — a transport-side choice decided by the rule the
owner keeps in the agent's prompt section ``decisao-<chave>`` (first user: the Meta first-contact template,
``abordagem-meta``). The model is the seed's ``FakeProvider``; nothing of ours is patched."""
from __future__ import annotations

from uuid import uuid4

from noctusai_lib.integrations.llm import ChatToolsResponse, FakeProvider, LLMUsage, ToolCall

from app.studio.julia import JULIA_KEY, JULIA_SECTIONS
from tests.channels.conftest import OTHER_ORG, turn_body

URL = f"/api/channels/agents/{JULIA_KEY}/decisoes/abordagem-meta"
REGRA_PADRAO = "Use `comercial` se houver codigo_imovel, senão `neutra`."
BODY = {"opcoes": ["comercial", "neutra"], "dados": {"codigo_imovel": "ONE9551", "campanha": "Casas Granja"},
        "regra_padrao": REGRA_PADRAO}


def _escolha(args: dict, cost: float = 0.0007) -> FakeProvider:
    return FakeProvider(tool_responses=[ChatToolsResponse(
        tool_calls=(ToolCall("d", "registrar_escolha", args),), finish_reason="tool_calls",
        usage=LLMUsage(80, 20, 0, 0, cost))])


def _post(chan, body=None, url=URL, **kw):
    with chan.as_token(**kw):
        return chan.request("POST", url, json=body if body is not None else BODY)


def _seed_without_rule(chan):
    """A published julia version whose sections lack ``decisao-abordagem-meta`` (an org seeded before it)."""
    chan.seed_agent(publish=False)
    studio = chan.rt.studio
    draft = studio.get_draft(chan.org_id, chan.agent.id)
    studio.replace_sections(chan.org_id, draft.id, [s for s in JULIA_SECTIONS if not s.chave.startswith("decisao-")])
    chan.version = chan.rt.publish(chan.agent, draft.id)


class TestDecisao:
    def test_the_owners_prompt_section_decides(self, chan):
        chan.seed_agent()
        chan.use_provider(_escolha({"escolha": "comercial", "motivo": "Veio pelo imóvel ONE9551; tel 11 99999-0000"}))
        resp = _post(chan)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["escolha"] == "comercial" and body["regra"] == "secao"
        assert "99999" not in body["motivo"]
        assert body["usage"] == {"custo_usd": 0.0007, "tokens_entrada": 80, "tokens_saida": 20}
        call = next(c for c in chan.provider.calls if c["method"] == "chat_with_tools")
        assert call["tool_choice"] == "registrar_escolha"
        assert call["api_key"] == "sk-org-a-key"
        system, user = call["messages"][0].content, call["messages"][1].content
        regra = next(s for s in JULIA_SECTIONS if s.chave == "decisao-abordagem-meta").conteudo
        assert regra in system and REGRA_PADRAO not in system
        assert "codigo_imovel: ONE9551" in user and "comercial, neutra" in user

    def test_an_owner_edit_of_the_section_is_what_decides(self, chan):
        chan.seed_agent(publish=False)
        studio = chan.rt.studio
        draft = studio.get_draft(chan.org_id, chan.agent.id)
        nova = "Sempre `neutra`, exceto campanhas com 'Lançamento' no nome."
        studio.replace_sections(chan.org_id, draft.id, [
            s if s.chave != "decisao-abordagem-meta" else type(s)(
                chave=s.chave, titulo=s.titulo, ordem=s.ordem, conteudo=nova, ativo=True)
            for s in JULIA_SECTIONS
        ])
        chan.version = chan.rt.publish(chan.agent, draft.id)
        chan.use_provider(_escolha({"escolha": "neutra", "motivo": "regra"}))
        assert _post(chan).json()["regra"] == "secao"
        system = next(c for c in chan.provider.calls if c["method"] == "chat_with_tools")["messages"][0].content
        assert nova in system

    def test_without_the_section_the_callers_default_rule_applies_and_says_so(self, chan):
        _seed_without_rule(chan)
        chan.use_provider(_escolha({"escolha": "neutra", "motivo": "sem código"}))
        body = _post(chan).json()
        assert body["regra"] == "padrao" and body["escolha"] == "neutra"
        system = next(c for c in chan.provider.calls if c["method"] == "chat_with_tools")["messages"][0].content
        assert REGRA_PADRAO in system

    def test_an_answer_outside_the_options_is_502_never_a_guess(self, chan):
        chan.seed_agent()
        chan.use_provider(_escolha({"escolha": "agressiva", "motivo": "x"}))
        resp = _post(chan)
        assert resp.status_code == 502 and resp.json()["code"] == "llm_upstream"

    def test_no_tool_call_is_502(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=["só texto"]))
        assert _post(chan).json()["code"] == "llm_upstream"

    def test_no_published_version_is_409(self, chan):
        chan.seed_agent(publish=False)
        chan.use_provider(_escolha({"escolha": "neutra", "motivo": "x"}))
        resp = _post(chan)
        assert resp.status_code == 409 and resp.json()["code"] == "no_active_version"

    def test_no_org_key_is_424(self, chan):
        chan.seed_agent()
        chan.use_provider(_escolha({"escolha": "neutra", "motivo": "x"}), key_for_org=False)
        resp = _post(chan)
        assert resp.status_code == 424 and resp.json()["code"] == "llm_not_configured"

    def test_bad_bodies_and_keys_are_422(self, chan):
        chan.seed_agent()
        chan.use_provider(_escolha({"escolha": "neutra", "motivo": "x"}))
        for body in (
            {**BODY, "opcoes": ["comercial"]},
            {**BODY, "opcoes": ["comercial", "comercial"]},
            {**BODY, "x": 1},
            {**BODY, "dados": {"a": "x" * 501}},
            {k: v for k, v in BODY.items() if k != "regra_padrao"},
        ):
            resp = _post(chan, body)
            assert resp.status_code == 422 and resp.json()["code"] == "invalid_field", body
        resp = _post(chan, url=f"/api/channels/agents/{JULIA_KEY}/decisoes/Abordagem_Meta")
        assert resp.status_code == 422 and resp.json()["code"] == "invalid_field"


class TestDecisaoAuth:
    def test_without_credential_is_401(self, chan):
        chan.seed_agent()
        assert chan.request("POST", URL, json=BODY).status_code == 401

    def test_human_session_is_403(self, chan):
        chan.seed_agent()
        assert chan.client.post(URL, json=BODY).status_code == 403

    def test_a_token_bound_to_another_agent_is_403(self, chan):
        chan.seed_agent()
        chan.use_provider(_escolha({"escolha": "neutra", "motivo": "x"}))
        resp = _post(chan, principal=uuid4())
        assert resp.status_code == 403 and resp.json()["code"] == "agent_not_allowed"

    def test_another_orgs_token_cannot_reach_this_agent(self, chan):
        chan.seed_agent()
        chan.use_provider(_escolha({"escolha": "neutra", "motivo": "x"}))
        resp = _post(chan, org_id=OTHER_ORG)
        assert resp.status_code == 404 and resp.json()["code"] == "agent_not_found"


class TestDecisionSectionsStayOutOfTheConversation:
    def test_the_rule_section_is_never_in_the_turn_prompt(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=["Você procura comprar ou alugar?"]))
        assert chan.turn(turn_body("Oi")).status_code == 200
        call = next(c for c in chan.provider.calls if c["method"] == "chat_with_tools")
        system = "\n".join(m.content for m in call["messages"] if m.role == "system")
        assert "Abordagem comercial" not in system and "abordagem do primeiro contato" not in system.lower()
        assert "Você é a Julia" in system

