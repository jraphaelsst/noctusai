"""`/api/julia/roteamento`: the `/julia/agente` page backend (julia-v2 Q4) -- LINE ROUTING only, white-label, per org.

The page is not wired to Julia's behaviour (that is agents' Controles). It lists the org's lines, flips "this number feeds the
agent" and sets the hand-off notification target; the work is the SAME function the legacy switch uses (one routing
implementation). Strict `== 401` on every auth boundary.
"""
from __future__ import annotations

import pytest

from tests.routers.test_julia_agente_routes import (  # noqa: F401  (fixtures + scene shared with the legacy routes)
    H,
    admin,
    member,
    override_settings_factory,
    _off_connection,
)
from tests.support.julia_world import (
    ADMIN_ID,
    CONNECTION_ID,
    CORRETOR_ID,
    OTHER_ORG_ID,
    OWNER_ID,
)

BASE = "/api/julia/roteamento"
LINHA = f"{BASE}/linhas/{CONNECTION_ID}"


class TestAuth:
    @pytest.mark.parametrize("method,url,body", [("get", BASE, None), ("put", LINHA, {"alimenta": True})])
    def test_no_token_is_401(self, admin, method, url, body):
        r = getattr(admin.tc, method)(url, **({"json": body} if body is not None else {}))
        assert r.status_code == 401

    def test_a_member_reads_but_cannot_write(self, member):
        member.w.seed_connection()
        assert member.get(BASE).status_code == 200
        assert member.tc.put(LINHA, json={"alimenta": False}, headers=H).status_code == 403

    def test_a_line_of_another_org_is_404(self, admin):
        admin.w.seed_connection(org_id=OTHER_ORG_ID)
        assert admin.put(LINHA, {"alimenta": False}).status_code == 404


class TestListar:
    def test_it_lists_only_routing_facts_for_the_org(self, admin):
        admin.w.seed_connection()
        admin.w.seed_connection(id="00000000-0000-4000-8000-0000000000e9", org_id=OTHER_ORG_ID, label="de outra org")
        data = admin.get(BASE).json()["data"]
        assert [l["connection_id"] for l in data["linhas"]] == [CONNECTION_ID]
        linha = data["linhas"][0]
        assert set(linha) == {"connection_id", "label", "alimenta", "alimenta_desde", "numeros_autorizados", "destino_handoff_user_id"}
        assert linha["alimenta"] is True and linha["numeros_autorizados"] == 1 and linha["destino_handoff_user_id"] is None

    def test_no_agent_behaviour_or_state_is_part_of_it(self, admin):
        """Behaviour (on / draining / off, health, versions) is agents' -- this page only links there."""
        admin.w.seed_connection()
        text = admin.get(BASE).text
        for gone in ("status_agente", "modo", "versao_ativa", "llm_configurado", "token", "erro"):
            assert gone not in text
        assert admin.w.agents.status_calls == [] and admin.w.agents.thread_reads == []

    def test_the_default_hand_off_target_is_the_org_owner(self, admin):
        admin.w.seed_connection()
        data = admin.get(BASE).json()["data"]
        assert data["destino_handoff_padrao"] == {"tipo": "dono_da_organizacao", "user_id": OWNER_ID}

    def test_the_link_to_agents_is_resolved_server_side(self, admin, monkeypatch):
        monkeypatch.setenv("PRODUCT_URL_AGENTS", "https://agents.example.test")
        admin.w.seed_connection()
        assert admin.get(BASE).json()["data"]["agents_url"] == "https://agents.example.test"

    def test_an_org_with_no_lines_is_an_empty_list_not_an_error(self, admin):
        assert admin.get(BASE).json()["data"]["linhas"] == []


class TestAlimentar:
    def test_turning_a_number_on_runs_every_precondition_and_snapshots(self, admin):
        _off_connection(admin.w)
        admin.w.waha.fake_chat_list = [{"id": "5511988887777@c.us"}]
        r = admin.put(LINHA, {"alimenta": True})
        assert r.status_code == 200 and r.json()["data"]["alimenta"] is True
        assert admin.conn()["agente_leads_ativo"] is True
        assert "5511988887777@c.us" in admin.snapshot_ids()  # 11.1: chats that already existed are never Julia's

    def test_the_same_preconditions_as_the_legacy_switch_still_block_it(self, admin):
        _off_connection(admin.w, authorized_numbers=[])
        r = admin.put(LINHA, {"alimenta": True})
        assert r.status_code == 409 and admin.conn()["agente_leads_ativo"] is False

    def test_turning_it_off_never_touches_agents(self, admin):
        admin.w.seed_connection()
        r = admin.put(LINHA, {"alimenta": False})
        assert r.status_code == 200 and r.json()["data"]["alimenta"] is False
        assert admin.w.agents.turns == [] and admin.w.agents.participante_calls == []

    def test_the_hand_off_target_is_set_and_validated(self, admin):
        admin.w.seed_connection()
        ok = admin.put(LINHA, {"alimenta": True, "destino_handoff_user_id": ADMIN_ID})
        assert ok.json()["data"]["destino_handoff_user_id"] == ADMIN_ID
        bad = admin.put(LINHA, {"alimenta": True, "destino_handoff_user_id": CORRETOR_ID})
        assert bad.status_code == 422 and "destinatario_invalido" in bad.text
        assert admin.conn()["agente_handoff_notificar_user_id"] == ADMIN_ID  # the refused change did not land

    def test_an_explicit_null_goes_back_to_the_default_and_absent_keeps_it(self, admin):
        admin.w.seed_connection(agente_handoff_notificar_user_id=ADMIN_ID)
        assert admin.put(LINHA, {"alimenta": True}).json()["data"]["destino_handoff_user_id"] == ADMIN_ID
        assert admin.put(LINHA, {"alimenta": True, "destino_handoff_user_id": None}).json()["data"]["destino_handoff_user_id"] is None

    def test_a_strict_body_rejects_unknown_fields(self, admin):
        admin.w.seed_connection()
        assert admin.put(LINHA, {"alimenta": True, "agente_leads_key": "outro"}).status_code == 422
        assert admin.put(LINHA, {}).status_code == 422
