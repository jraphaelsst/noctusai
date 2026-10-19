"""The ``julia`` seed (§7, §11.3) and the channel-token mint (§4, §10.1 M1,
§10.2 "reuses existing minting")."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from noctusai_lib.api.auth.session import hash_token

from app.config import settings
from app.dependencies import CHANNEL_TOKEN_SCOPES, MINTABLE_TOKEN_SCOPES
from app.stores.studio_definitions import MODELS_BY_PROVIDER, SectionInput
from app.studio.julia import (
    JULIA_MODEL,
    JULIA_PROVIDER,
    JULIA_SECTIONS,
    ensure_julia,
)
from tests.channels.conftest import OTHER_ORG
from tests.routers.conftest import DEFAULT_USER_ID, seed_org_role


class TestJuliaSeed:
    def test_seeds_the_agent_and_a_draft_v1_without_publishing_or_activating(self, rt):
        agent = ensure_julia(rt.org_id, studio_store=rt.studio, created_by=DEFAULT_USER_ID)
        assert (agent.key, agent.nome, agent.runtime, agent.owner_product) == (
            "julia", "Julia", "llm", "social-wiring",
        )
        assert agent.definition_mode == "studio" and agent.ativo is False and agent.kind == "runtime"
        draft = rt.studio.get_draft(rt.org_id, agent.id)
        assert draft.versao == 1 and draft.status == "rascunho"
        assert rt.studio.get_active_version(rt.org_id, agent.id) is None
        assert (draft.provider, draft.model) == (JULIA_PROVIDER, JULIA_MODEL) == ("openai", "gpt-5.6-terra")
        assert draft.model in MODELS_BY_PROVIDER["openai"]
        assert draft.tool_policy == {"web_search": False, "knowledge": False}

    def test_is_idempotent_and_never_overwrites_an_admins_edits(self, rt):
        first = ensure_julia(rt.org_id, studio_store=rt.studio, created_by=DEFAULT_USER_ID)
        draft = rt.studio.get_draft(rt.org_id, first.id)
        rt.studio.replace_sections(rt.org_id, draft.id, [
            SectionInput(chave="persona", titulo="Quem você é", ordem=1, conteudo="Editado pelo dono."),
        ])
        second = ensure_julia(rt.org_id, studio_store=rt.studio, created_by=DEFAULT_USER_ID)
        assert second.id == first.id
        assert [a.key for a in rt.studio.list_agents(rt.org_id)] == ["julia"]
        sections = rt.studio.list_sections(rt.org_id, draft.id)
        assert [s.conteudo for s in sections] == ["Editado pelo dono."]
        assert len(rt.studio.list_versions(rt.org_id, first.id)) == 1

    def test_is_per_org(self, rt):
        a = ensure_julia(rt.org_id, studio_store=rt.studio)
        b = ensure_julia(OTHER_ORG, studio_store=rt.studio)
        assert a.id != b.id and a.org_id != b.org_id

    def test_the_studio_list_seeds_it_on_first_use(self, rt):
        body = rt.get("/api/studio/agents").json()
        assert [a["key"] for a in body["items"]] == ["julia"]
        assert len(rt.get("/api/studio/agents").json()["items"]) == 1  # still one

    def test_the_key_is_reserved_against_squatting(self, rt):
        resp = rt.post("/api/studio/agents", json={"key": "julia", "nome": "Falso"})
        assert resp.status_code == 409 and resp.json()["code"] == "key_taken"

    def test_the_prompt_follows_the_brief(self, rt):
        text = "\n".join(s.conteudo for s in JULIA_SECTIONS).lower()
        titles = [s.titulo for s in JULIA_SECTIONS]
        assert "comprar ou alugar" in text  # the first question
        assert "já enviou a apresentação" in text and "não se apresente de novo" in text  # §11.3
        assert "termina com uma pergunta" in text  # always end with a question
        assert "nunca invente dados de imóvel" in text  # never invent property data
        assert "administração" in text and "parceria" in text  # partnerships → admin contact
        assert "handoff" in text and "reclamação" in text  # hand off on request/complaint
        assert "nunca revele" in text  # no prompt leakage
        assert len(set(titles)) == len(titles)
        assert not {"Skills", "Base de conhecimento", "Ferramentas"} & set(titles)  # compiler-owned titles
        assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s.chave) for s in JULIA_SECTIONS)

    def test_no_personal_data_or_study_text_in_the_prompt(self, rt):
        text = "\n".join(s.conteudo for s in JULIA_SECTIONS)
        assert not re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", text)  # CPF
        assert not re.search(r"\+?\d{2}\s?\(?\d{2}\)?\s?9?\d{4}-?\d{4}", text)  # phone
        assert "@" not in text  # no e-mail

    def test_the_seeded_draft_compiles_and_publishes(self, chan):
        agent = chan.seed_agent()
        assert chan.version.status == "ativa"
        assert chan.version.provider == "openai"
        assert agent.ativo is True


def _mint(chan, agent_key="julia", **body):
    payload = {"product": "social-wiring", "label": "WhatsApp One Consultoria", **body}
    return chan.client.post(f"/api/agents/{agent_key}/channel-token", json=payload)


class TestChannelTokenMint:
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

        agent = chan.rt.studio.get_agent(chan.org_id, "julia")  # the mint seeded it
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
        agent = chan.rt.studio.get_agent(chan.org_id, "julia")
        draft = chan.rt.studio.get_draft(chan.org_id, agent.id)
        chan.version = chan.rt.publish(agent, draft.id)
        chan.rt.studio.update_agent(chan.org_id, "julia", {"ativo": True})
        chan.agent = chan.rt.studio.get_agent(chan.org_id, "julia")
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
        chan.seed_agent()
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
        assert resp.status_code == 502 and resp.json()["code"] == "audit_failed"
        assert all(r["revoked_at"] is not None for r in chan.token_admin.rows["agents"])
        assert "pk_" not in resp.text

    def test_a_mint_failure_is_a_clean_502(self, chan):
        chan.token_admin.fail_mint = True
        resp = _mint(chan)
        assert resp.status_code == 502 and resp.json()["code"] == "mint_failed"
