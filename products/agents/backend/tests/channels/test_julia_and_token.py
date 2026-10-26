"""The ``julia`` seed (§7, §11.3) and the channel-token mint (§4, §10.1 M1,
§10.2 "reuses existing minting")."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from noctusai_lib.api.auth.session import hash_token

from app.config import settings
from app.dependencies import CHANNEL_TOKEN_SCOPES, MINTABLE_TOKEN_SCOPES
from app.stores.studio_definitions import MODELS_BY_PROVIDER
from app.studio.plataforma import ensure_definicao, ensure_instancia, ensure_instancias
from tests.channels.conftest import OTHER_ORG
from tests.routers.conftest import DEFAULT_USER_ID, seed_org_role
from noctusai_lib.testing import handler_status

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
        resp = rt.post("/api/studio/agents", json={"key": "bia", "nome": "Falso"})
        assert resp.status_code == 409 and resp.json()["code"] == "key_taken"


def _platform_definition_other(rt):
    return ensure_definicao(PLATFORM_ORG, "outro-agente", studio_store=rt.studio, nome="Outro", instanciavel=True)


class TestTheV2World:
    def test_the_world_fixture_publishes_a_content_complete_definition_for_the_org(self, chan):
        agent = chan.seed_agent()
        assert chan.version.status == "ativa" and chan.version.provider == "openai"
        assert (agent.definition_scope, agent.ativo) == ("instancia", True)
        assert chan.rt.studio.list_versions(chan.org_id, agent.id) == []  # an instance owns no versions


def _mint(chan, agent_key="julia", **body):
    payload = {"product": "social-wiring", "label": "WhatsApp One Consultoria", **body}
    return chan.client.post(f"/api/agents/{agent_key}/channel-token", json=payload)


class TestChannelTokenMint:
    @pytest.fixture(autouse=True)
    def _per_org_agent(self, chan):
        """The org's `julia` instance of the platform definition: the mint no longer seeds a row."""
        chan.seed_agent(ativo=False)

    def test_admin_mints_a_token_shown_once_with_the_contracted_row(self, chan):
        resp = _mint(chan)
        assert resp.status_code == 201, resp.text
        assert resp.headers["Cache-Control"] == "no-store"
        body = resp.json()
        assert body["token"].startswith("pk_") and body["prefix"] == body["token"][:11]
        assert sorted(body["scopes"]) == sorted(CHANNEL_TOKEN_SCOPES)
        expires = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
        assert abs((expires - (datetime.now(timezone.utc) + timedelta(days=30))).total_seconds()) < 120
        assert settings.channel_token_ttl_days == 30

        agent = chan.rt.studio.get_agent(chan.org_id, "julia")  # the per-org agent the mint binds to
        row = chan.token_admin.rows["agents"][0]
        assert row["org_id"] == str(chan.org_id)
        assert row["issuer"] == "social-wiring"
        assert row["principal_agent_id"] == str(agent.id)
        assert set(row["scopes"]) == set(CHANNEL_TOKEN_SCOPES) and set(row["scopes"]) <= MINTABLE_TOKEN_SCOPES
        assert row["minted_by"] == str(DEFAULT_USER_ID)
        assert row["human_personal"] is False and row["revoked_at"] is None
        assert datetime.fromisoformat(row["expires_at"]) == expires

    def test_only_a_hash_of_the_secret_is_stored(self, chan):
        body = _mint(chan).json()
        row = chan.token_admin.rows["agents"][0]
        assert row["token_hash"] == hash_token(body["token"])
        assert body["token"] not in repr(chan.token_admin.rows)
        assert body["token"] not in repr(chan.audit.rows)

    def test_the_minted_token_is_bound_to_the_agent_and_works_on_the_channel_routes(self, chan):
        """The mint output is what SW holds: the row's issuer/principal/scopes drive the guards."""
        body = _mint(chan).json()
        row = chan.token_admin.rows["agents"][0]
        # Resolve through the SAME seed row mapper the SupabaseApiTokenResolver uses.
        with chan.as_token(*row["scopes"], issuer=row["issuer"], principal=UUID(row["principal_agent_id"])):
            assert chan.request("GET", "/api/channels/agents/julia/status").status_code == 200
            # NOC-REMEDIATE[drop-lead-imob-alias]: social-wiring still sends the pre-rename key
            # for one release; it resolves to the very same agent.
            old = chan.request("GET", "/api/channels/agents/lead-imob/status")
            assert old.status_code == 200 and old.json()["agent_key"] == "julia"
            assert body["scopes"]

    def test_mint_is_audit_logged(self, chan):
        body = _mint(chan).json()
        [row] = chan.audit.rows
        assert (row.method, row.status, row.org_id) == ("MINT", 201, chan.org_id)
        assert row.api_token_id == UUID(body["id"])
        assert "julia" in row.path and str(DEFAULT_USER_ID) in row.path

    def test_rotation_overlaps_minting_never_revokes_the_old_token(self, chan):
        first, second = _mint(chan).json(), _mint(chan, label="rotação").json()
        assert first["token"] != second["token"]
        rows = chan.token_admin.rows["agents"]
        assert len(rows) == 2 and all(r["revoked_at"] is None for r in rows)

    def test_revoke_stamps_the_row_and_is_audit_logged(self, chan):
        first, second = _mint(chan).json(), _mint(chan, label="rotação").json()
        resp = chan.client.delete(f"/api/agents/julia/channel-token/{first['id']}")
        assert resp.status_code == 204
        rows = {r["id"]: r for r in chan.token_admin.rows["agents"]}
        assert rows[first["id"]]["revoked_at"] is not None and rows[second["id"]]["revoked_at"] is None
        assert [(a.method, a.status) for a in chan.audit.rows] == [("MINT", 201), ("MINT", 201), ("REVOKE", 204)]

    def test_revoking_another_orgs_token_is_404_and_changes_nothing(self, chan):
        other = chan.token_admin.mint(
            "agents", org_id=OTHER_ORG, label="x", scopes=["agents:channel-turn"],
            expires_at=datetime.now(timezone.utc) + timedelta(days=1), issuer="social-wiring",
        )
        _mint(chan)
        resp = chan.client.delete(f"/api/agents/julia/channel-token/{other.info.id}")
        assert resp.status_code == 404 and resp.json()["code"] == "token_not_found"
        assert all(r["revoked_at"] is None for r in chan.token_admin.rows["agents"])

    def test_a_member_cannot_mint_or_revoke(self, chan):
        seed_org_role(chan.client, role="member")
        assert _mint(chan).status_code == 403
        assert chan.client.delete(f"/api/agents/julia/channel-token/{uuid4()}").status_code == 403
        assert chan.token_admin.rows == {}

    def test_a_product_token_can_never_mint(self, chan):
        with chan.as_token("agents:channel-turn", "agents:channel-status"):
            resp = chan.request("POST", "/api/agents/julia/channel-token",
                                json={"product": "social-wiring", "label": "x"})
        assert resp.status_code == 403 and resp.json()["code"] == "user_required"
        assert chan.token_admin.rows == {}

    def test_unauthenticated_mint_is_401(self, chan):
        resp = chan.request("POST", "/api/agents/julia/channel-token",
                            json={"product": "social-wiring", "label": "x"})
        assert resp.status_code == 401

    @pytest.mark.parametrize("body", [
        {"product": "other", "label": "x"},
        {"product": "social-wiring"},
        {"product": "social-wiring", "label": ""},
        {"product": "social-wiring", "label": "x", "scopes": ["agents:channel-turn", "studio:publish"]},
        {"product": "social-wiring", "label": "x", "issuer": "agents"},
        {"product": "social-wiring", "label": "x", "expires_at": "2099-01-01T00:00:00Z"},
    ])
    def test_the_request_cannot_choose_scopes_issuer_or_ttl(self, chan, body):
        resp = chan.client.post("/api/agents/julia/channel-token", json=body)
        assert resp.status_code == 422
        assert chan.token_admin.rows == {}

    def test_unknown_or_non_llm_agent_is_404(self, chan):
        chan.rt.make_agent("isa", publish=False)
        assert _mint(chan, "isa").status_code == 404
        assert _mint(chan, "nope").status_code == 404

    def test_an_unaudited_mint_is_revoked_and_fails(self, chan):
        chan.audit.fail = True
        resp = _mint(chan)
        assert handler_status(resp) == 502 and resp.json()["code"] == "audit_failed"
        assert all(r["revoked_at"] is not None for r in chan.token_admin.rows["agents"])
        assert "pk_" not in resp.text

    def test_a_mint_failure_is_a_clean_502(self, chan):
        chan.token_admin.fail_mint = True
        resp = _mint(chan)
        assert handler_status(resp) == 502 and resp.json()["code"] == "mint_failed"
