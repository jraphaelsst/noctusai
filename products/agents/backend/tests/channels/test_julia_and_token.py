"""The ``julia`` seed (§7, §11.3) and the channel token a platform grant mints (the human mint route is gone)."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.dependencies import CHANNEL_TOKEN_SCOPES, MINTABLE_TOKEN_SCOPES
from app.stores.studio_definitions import MODELS_BY_PROVIDER
from app.studio.plataforma import ensure_definicao, ensure_instancia, ensure_instancias
from tests.channels.conftest import OTHER_ORG
from tests.routers.conftest import DEFAULT_USER_ID

PLATFORM_ORG = UUID(int=900001)


def _platform_definition(rt, **kw):
    """A platform definition (TEST DATA: key + settings are passed in, never registered in code)."""
    rt.studio.mark_platform_org(PLATFORM_ORG)
    params = dict(
        nome="Julia", runtime="llm", owner_product="social-wiring", instanciavel=False,
        escopo_qualificacao="sdr", padrao_qualificacao="imob-lead",
        rascunho_padrao={"provider": "openai", "model": "gpt-5.6-terra", "tool_policy": {"web_search": False, "knowledge": False}},
    )
    grant = kw.pop("grant", True)
    params.update(kw)
    d = ensure_definicao(PLATFORM_ORG, "julia", studio_store=rt.studio, created_by=DEFAULT_USER_ID, **params)
    if grant:  # 050: a product-owned (closed) definition reaches an org only by an explicit grant
        for org in (rt.org_id, OTHER_ORG):
            rt.studio.grant_definition_org(d.id, org, DEFAULT_USER_ID)
    return d


class TestPlatformDefinitionsAreData:
    """A platform definition is a DB row: ONE per key + an instance per org. Structure only; no code registry."""

    def test_without_a_platform_definition_nothing_is_created(self, rt):
        assert ensure_instancia(rt.org_id, "julia", studio_store=rt.studio) is None
        assert ensure_instancias(rt.org_id, studio_store=rt.studio) == []
        assert rt.studio.list_agents(rt.org_id) == []

    def test_a_new_key_needs_a_name(self, rt):
        rt.studio.mark_platform_org(PLATFORM_ORG)
        with pytest.raises(ValueError):
            ensure_definicao(PLATFORM_ORG, "qualquer", studio_store=rt.studio)

    def test_the_definition_is_created_once_with_the_given_data_and_settings_only(self, rt):
        d = _platform_definition(rt)
        assert (d.key, d.nome, d.runtime, d.owner_product) == ("julia", "Julia", "llm", "social-wiring")
        assert (d.definition_scope, d.conteudo_modo, d.ativo) == ("plataforma", "linhas", False)
        assert (d.escopo_qualificacao, d.padrao_qualificacao, d.usa_canais) == ("sdr", "imob-lead", True)
        draft = rt.studio.get_draft(PLATFORM_ORG, d.id)
        assert draft.versao == 1 and draft.status == "rascunho"
        assert (draft.provider, draft.model) == ("openai", "gpt-5.6-terra")
        assert draft.model in MODELS_BY_PROVIDER["openai"]
        assert draft.tool_policy == {"web_search": False, "knowledge": False}
        # STRUCTURE only: not one prompt row.
        assert rt.studio.list_sections(PLATFORM_ORG, draft.id) == []
        assert rt.studio.list_textos(PLATFORM_ORG, draft.id) == []
        assert rt.studio.list_ferramentas(PLATFORM_ORG, draft.id) == []
        assert _platform_definition(rt).id == d.id  # idempotent

    def test_an_org_gets_an_instance_without_versions_or_text(self, rt):
        d = _platform_definition(rt)
        agent = ensure_instancia(rt.org_id, "julia", studio_store=rt.studio)
        assert (agent.definition_scope, agent.definition_agent_id, agent.conteudo_modo) == ("instancia", d.id, "linhas")
        assert (agent.key, agent.runtime, agent.owner_product, agent.ativo) == ("julia", "llm", "social-wiring", False)
        assert rt.studio.list_versions(rt.org_id, agent.id) == []

    def test_a_closed_definition_is_never_instantiated_without_a_grant(self, rt):
        _platform_definition(rt, grant=False)
        assert ensure_instancia(rt.org_id, "julia", studio_store=rt.studio) is None
        assert ensure_instancias(rt.org_id, studio_store=rt.studio) == []

    def test_is_idempotent_and_per_org(self, rt):
        _platform_definition(rt)
        a = ensure_instancia(rt.org_id, "julia", studio_store=rt.studio)
        assert ensure_instancia(rt.org_id, "julia", studio_store=rt.studio).id == a.id
        b = ensure_instancia(OTHER_ORG, "julia", studio_store=rt.studio)
        assert a.id != b.id and a.org_id != b.org_id and a.definition_agent_id == b.definition_agent_id
        assert [x.key for x in rt.studio.list_agents(rt.org_id)] == ["julia"]

    def test_the_studio_list_gives_an_org_an_instance_of_every_published_instantiable_definition(self, rt):
        from tests.studio.rt.fakes import publish

        assert rt.get("/api/studio/agents").json()["items"] == []  # no definition yet: nothing stranded
        d = _platform_definition(rt)
        # a DRAFT-only definition is not instantiated by the list (nothing to run yet)
        assert rt.get("/api/studio/agents").json()["items"] == []
        draft = rt.studio.get_draft(PLATFORM_ORG, d.id)
        publish(rt.studio, PLATFORM_ORG, d, draft.id, DEFAULT_USER_ID, catalog=None)
        other = _platform_definition_other(rt)  # published? no -> never instantiated
        body = rt.get("/api/studio/agents").json()
        assert [a["key"] for a in body["items"]] == ["julia"]
        assert body["items"][0]["definition_scope"] == "instancia"
        assert body["items"][0]["usa_canais"] is True
        assert len(rt.get("/api/studio/agents").json()["items"]) == 1  # still one
        assert other.key not in [a["key"] for a in body["items"]]

    def test_a_key_that_is_a_platform_definition_is_refused_for_an_org_agent(self, rt):
        _platform_definition(rt)
        resp = rt.post("/api/studio/agents", json={"key": "julia", "nome": "Falso"})
        assert resp.status_code == 409 and resp.json()["code"] == "key_taken"

    def test_the_legacy_default_keys_stay_reserved(self, rt):
        resp = rt.post("/api/studio/agents", json={"key": "one-chat", "nome": "Falso"})
        assert resp.status_code == 409 and resp.json()["code"] == "key_taken"


def _platform_definition_other(rt):
    return ensure_definicao(PLATFORM_ORG, "outro-agente", studio_store=rt.studio, nome="Outro", instanciavel=True)


class TestTheV2World:
    def test_the_world_fixture_publishes_a_content_complete_definition_for_the_org(self, chan):
        agent = chan.seed_agent()
        assert chan.version.status == "ativa" and chan.version.provider == "openai"
        assert (agent.definition_scope, agent.ativo) == ("instancia", True)
        assert chan.rt.studio.list_versions(chan.org_id, agent.id) == []  # an instance owns no versions


class TestMintedChannelTokenWorks:
    """There is no human mint route (Julia-line S5): a channel token comes from a platform grant. What stays tested
    here is that a token with the grant's issuer / principal / scopes drives the channel guards."""

    def test_a_token_bound_to_the_agent_works_on_the_channel_routes(self, chan):
        agent = chan.seed_agent(ativo=False)
        minted = chan.token_admin.mint(
            "agents", org_id=chan.org_id, label="grant", scopes=sorted(CHANNEL_TOKEN_SCOPES),
            expires_at=None, principal_agent_id=agent.id, issuer="social-wiring",
        )
        row = chan.token_admin.rows["agents"][0]
        assert minted.secret not in repr(chan.token_admin.rows)  # only a hash is stored
        assert set(row["scopes"]) <= MINTABLE_TOKEN_SCOPES
        with chan.as_token(*row["scopes"], issuer=row["issuer"], principal=UUID(row["principal_agent_id"])):
            assert chan.request("GET", "/api/channels/agents/julia/status").status_code == 200
            # NOC-REMEDIATE[drop-lead-imob-alias]: social-wiring still sends the pre-rename key
            # for one release; it resolves to the very same agent.
            old = chan.request("GET", "/api/channels/agents/lead-imob/status")
            assert old.status_code == 200 and old.json()["agent_key"] == "julia"

    def test_the_human_mint_route_is_gone(self, chan):
        chan.seed_agent(ativo=False)
        body = {"product": "social-wiring", "label": "x"}
        assert chan.client.post("/api/agents/julia/channel-token", json=body).status_code in (404, 405)
        assert chan.client.delete(f"/api/agents/julia/channel-token/{uuid4()}").status_code in (404, 405)
        assert chan.token_admin.rows == {}
