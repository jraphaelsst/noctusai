"""Julia wave 11 -- Equipes / Distribuicao (contract section 13): CRUD + members, admin-only writes, metrics,
the Conversas `equipe` filter, round-robin fairness, keep-last-responsible, the Sim/Nao and funil/julia modes,
the handoff wiring (attendant picked BEFORE the notification) and `estado.atendente_nome`.

Seams: mock DB, seed Fakes -- nothing of ours is patched. Every route is strict `== 401` without a session."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.clients.agents import FakeAgentsClient, HandoffAction, TurnResult
from app.services import julia_contexto_service as ctxsvc
from app.services import julia_equipes_service as svc
from app.services.julia_lead_turn_service import process_lead_batch

from tests.routers.test_julia_conversas import OUTRO, _novo_contato
from tests.support.julia_world import CONNECTION_ID, CORRETOR_ID, ENCRYPTION_KEY, LEAD_CHAT, MEMBER_ID, ORG_ID, OTHER_ORG_ID, OWNER_ID, World, buffer_lead

H = {"Authorization": "Bearer test-token"}
U1, U2, U3 = CORRETOR_ID, MEMBER_ID, OUTRO
FORA = "00000000-0000-4000-8000-0000000000aa"  # user of ANOTHER org


def _mundo(role: str = "owner"):
    w = World()
    for t in ("julia_etiquetas", "julia_contato_etiquetas", "julia_equipes", "julia_equipe_membros", "julia_distribuicao_cursor",
              "julia_atribuicoes", "julia_visitas", "julia_conhecimento_secoes", "julia_notas", "julia_feedback"):
        w.sw.set_table_data(t, [])
    w.seed_connection(user_id=OWNER_ID)
    w.seed_chat()
    _novo_contato(w, LEAD_CHAT, nome="Ana", telefone_e164="+5511988887777")
    w.core.set_table_data("noctus_users", [
        {"id": OWNER_ID, "org_id": ORG_ID, "org_role": "owner", "nome": "Dono", "last_active_at": None},
        {"id": CORRETOR_ID, "org_id": ORG_ID, "org_role": "corretor", "nome": "Carla", "last_active_at": "2026-10-10T10:00:00+00:00"},
        {"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": role, "nome": "Chefe", "last_active_at": None},
        {"id": MEMBER_ID, "org_id": ORG_ID, "org_role": "member", "nome": "Marcos", "last_active_at": None},
        {"id": OUTRO, "org_id": ORG_ID, "org_role": "member", "nome": "Olga", "last_active_at": None},
        {"id": FORA, "org_id": OTHER_ORG_ID, "org_role": "member", "nome": "Fora", "last_active_at": None},
    ])
    return w


class Scene:
    def __init__(self, tc, w):
        self.tc, self.w = tc, w

    def req(self, m, url, json=None, **kw):
        return getattr(self.tc, m)(url, headers=H, **({"json": json} if json is not None else {}), **kw)

    def equipe(self, nome="Vendas", **over):
        r = self.req("post", "/api/julia/equipes", {"nome": nome, **over})
        assert r.status_code == 201, r.text
        return r.json()["data"]

    def membro(self, equipe_id, user_id, **over):
        r = self.req("post", f"/api/julia/equipes/{equipe_id}/membros", {"user_id": user_id, **over})
        assert r.status_code == 201, r.text
        return r.json()["data"]


@pytest.fixture(autouse=True)
def _public_url(monkeypatch):
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test")


@pytest.fixture
def override_settings_factory():
    from app.config import settings as _settings
    from app.dependencies import get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: _settings.model_copy(update={"encryption_key": ENCRYPTION_KEY})
    yield
    app.dependency_overrides.pop(get_settings, None)


def _scene(role):
    w = _mundo(role)
    w.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role=role)))
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=w.admin),
    ):
        from app.main import app
        from app.routers.julia_conversas_router import get_conversas_client
        from app.routers.julia_equipes_router import get_equipes_client

        bind_consent_module_to_mock(w.root)
        app.dependency_overrides[get_equipes_client] = lambda: w.sw
        app.dependency_overrides[get_conversas_client] = lambda: w.sw
        yield Scene(TestClient(app), w)
        app.dependency_overrides.pop(get_equipes_client, None)
        app.dependency_overrides.pop(get_conversas_client, None)


@pytest.fixture
def admin(override_settings_factory):
    yield from _scene("owner")


@pytest.fixture
def member(override_settings_factory):
    yield from _scene("member")


# ── strict 401 ──────────────────────────────────────────────────────────────
class TestAuth:
    @pytest.mark.parametrize("metodo,url,corpo", [
        ("get", "/api/julia/equipes", None),
        ("post", "/api/julia/equipes", {"nome": "x"}),
        ("get", f"/api/julia/equipes/{uuid4()}", None),
        ("patch", f"/api/julia/equipes/{uuid4()}", {"nome": "x"}),
        ("delete", f"/api/julia/equipes/{uuid4()}", None),
        ("post", f"/api/julia/equipes/{uuid4()}/membros", {"user_id": str(uuid4())}),
        ("patch", f"/api/julia/equipes/{uuid4()}/membros/{uuid4()}", {"ativo": False}),
        ("delete", f"/api/julia/equipes/{uuid4()}/membros/{uuid4()}", None),
        ("put", f"/api/julia/equipes/{uuid4()}/membros/ordem", {"ordem": []}),
        ("get", f"/api/julia/equipes/{uuid4()}/metricas?mes=2026-10", None),
    ])
    def test_no_token_is_401(self, admin, metodo, url, corpo):
        r = getattr(admin.tc, metodo)(url, **({"json": corpo} if corpo is not None else {}))
        assert r.status_code == 401


# ── admin-only writes, member reads ─────────────────────────────────────────
class TestPermissoes:
    def test_member_reads_but_never_writes(self, member):
        e = svc.criar(member.w.sw, member.w.core, ORG_ID, nome="Vendas")
        assert member.req("get", "/api/julia/equipes").status_code == 200
        assert member.req("get", f"/api/julia/equipes/{e['id']}").status_code == 200
        assert member.req("get", f"/api/julia/equipes/{e['id']}/metricas?mes=2026-10").status_code == 200
        for m, url, body in [
            ("post", "/api/julia/equipes", {"nome": "Outra"}),
            ("patch", f"/api/julia/equipes/{e['id']}", {"nome": "X"}),
            ("delete", f"/api/julia/equipes/{e['id']}", None),
            ("post", f"/api/julia/equipes/{e['id']}/membros", {"user_id": U2}),
            ("patch", f"/api/julia/equipes/{e['id']}/membros/{U2}", {"ativo": False}),
            ("delete", f"/api/julia/equipes/{e['id']}/membros/{U2}", None),
            ("put", f"/api/julia/equipes/{e['id']}/membros/ordem", {"ordem": []}),
        ]:
            assert member.req(m, url, body).status_code == 403, (m, url)
        assert len(svc.listar(member.w.sw, member.w.core, ORG_ID)) == 1

    def test_org_admin_writes(self, override_settings_factory):
        for s in _scene("admin"):
            assert s.req("post", "/api/julia/equipes", {"nome": "Locação"}).status_code == 201


# ── CRUD + members ──────────────────────────────────────────────────────────
class TestCrud:
    def test_create_defaults_and_roundtrip(self, admin):
        e = admin.equipe("Vendas")
        assert (e["atende_apos_julia"], e["modo"], e["manter_ultimo"], e["membros"]) == (True, "funil", True, [])
        e2 = admin.req("patch", f"/api/julia/equipes/{e['id']}", {"modo": "julia", "atende_apos_julia": False, "manter_ultimo": False}).json()["data"]
        assert (e2["modo"], e2["atende_apos_julia"], e2["manter_ultimo"]) == ("julia", False, False)
        assert [x["id"] for x in admin.req("get", "/api/julia/equipes").json()["data"]] == [e["id"]]
        assert admin.req("delete", f"/api/julia/equipes/{e['id']}").status_code == 204
        assert admin.req("get", f"/api/julia/equipes/{e['id']}").status_code == 404

    def test_duplicate_name_is_409_and_bad_input_422(self, admin):
        admin.equipe("Vendas")
        assert admin.req("post", "/api/julia/equipes", {"nome": "vendas"}).status_code == 409
        assert admin.req("post", "/api/julia/equipes", {"nome": ""}).status_code == 422
        assert admin.req("post", "/api/julia/equipes", {"nome": "x", "modo": "robo"}).status_code == 422
        assert admin.req("post", "/api/julia/equipes", {"nome": "x", "extra": 1}).status_code == 422

    def test_members_add_remove_order_and_org_scope(self, admin):
        e = admin.equipe()
        admin.membro(e["id"], U1)
        admin.membro(e["id"], U2)
        r = admin.req("post", f"/api/julia/equipes/{e['id']}/membros", {"user_id": U2})
        assert r.status_code == 409
        assert admin.req("post", f"/api/julia/equipes/{e['id']}/membros", {"user_id": FORA}).status_code == 422  # another org
        d = admin.req("put", f"/api/julia/equipes/{e['id']}/membros/ordem", {"ordem": [U2, U1]}).json()["data"]
        assert [m["user_id"] for m in d["membros"]] == [U2, U1] and [m["nome"] for m in d["membros"]] == ["Marcos", "Carla"]
        assert admin.req("put", f"/api/julia/equipes/{e['id']}/membros/ordem", {"ordem": [U2]}).status_code == 422
        d = admin.req("patch", f"/api/julia/equipes/{e['id']}/membros/{U1}", {"ativo": False}).json()["data"]
        assert [m["ativo"] for m in d["membros"]] == [True, False]
        assert admin.req("delete", f"/api/julia/equipes/{e['id']}/membros/{U1}").status_code == 204
        assert admin.req("delete", f"/api/julia/equipes/{e['id']}/membros/{U1}").status_code == 404
        assert [m["user_id"] for m in admin.req("get", f"/api/julia/equipes/{e['id']}").json()["data"]["membros"]] == [U2]

    def test_another_orgs_team_is_404(self, admin):
        admin.w.sw.table("julia_equipes").insert({"id": str(uuid4()), "org_id": OTHER_ORG_ID, "nome": "Alheia"}).execute()
        eid = admin.w.sw.table("julia_equipes").select("id").eq("org_id", OTHER_ORG_ID).execute().data[0]["id"]
        assert admin.req("get", f"/api/julia/equipes/{eid}").status_code == 404
        assert admin.req("get", "/api/julia/equipes").json()["data"] == []


# ── distribution ────────────────────────────────────────────────────────────
def _contato(w, n):
    _novo_contato(w, f"55119{n:08d}@c.us", nome=f"L{n}")
    return w.contato(f"55119{n:08d}@c.us")


def _auto(s, *users, **over):
    e = s.equipe("Vendas", modo="julia", atende_apos_julia=True, **over)
    for u in users:
        s.membro(e["id"], u)
    return e


class TestDistribuicao:
    def test_round_robin_is_fair_and_follows_member_order(self, admin):
        _auto(admin, U1, U2, U3)
        w = admin.w
        picks = [svc.atribuir_responsavel(w.sw, w.core, ORG_ID, _contato(w, n))["user_id"] for n in range(1, 10)]
        assert picks == [U1, U2, U3] * 3
        assert len(w.rows("julia_atribuicoes")) == 9
        assert {c["responsavel_user_id"] for c in w.rows("julia_contatos") if c["chat_id"] != LEAD_CHAT} == {U1, U2, U3}

    def test_inactive_and_foreign_members_are_skipped(self, admin):
        e = _auto(admin, U1, U2, U3)
        admin.req("patch", f"/api/julia/equipes/{e['id']}/membros/{U2}", {"ativo": False})
        w = admin.w
        w.sw.table("julia_equipe_membros").insert({"equipe_id": e["id"], "org_id": ORG_ID, "user_id": FORA, "ativo": True, "ordem": 9}).execute()
        picks = [svc.atribuir_responsavel(w.sw, w.core, ORG_ID, _contato(w, n))["user_id"] for n in range(1, 5)]
        assert picks == [U1, U3, U1, U3]

    def test_keeps_the_last_responsible_when_on_and_still_active(self, admin):
        e = _auto(admin, U1, U2)
        w = admin.w
        c = _contato(w, 1)
        w.sw.table("julia_contatos").update({"responsavel_user_id": U2}).eq("id", c["id"]).execute()
        r = svc.atribuir_responsavel(w.sw, w.core, ORG_ID, w.contato("55119" + "00000001@c.us"))
        assert (r["user_id"], r["criterio"]) == (U2, "ultimo_responsavel")
        assert w.rows("julia_distribuicao_cursor") == []  # the cursor did not move
        # off, or the responsible left the team -> round-robin instead
        admin.req("patch", f"/api/julia/equipes/{e['id']}", {"manter_ultimo": False})
        r = svc.atribuir_responsavel(w.sw, w.core, ORG_ID, w.contato("55119" + "00000001@c.us"))
        assert (r["user_id"], r["criterio"]) == (U1, "round_robin")
        admin.req("patch", f"/api/julia/equipes/{e['id']}", {"manter_ultimo": True})
        admin.req("patch", f"/api/julia/equipes/{e['id']}/membros/{U1}", {"ativo": False})
        r = svc.atribuir_responsavel(w.sw, w.core, ORG_ID, w.contato("55119" + "00000001@c.us"))
        assert (r["user_id"], r["criterio"]) == (U2, "round_robin")

    @pytest.mark.parametrize("over", [{"atende_apos_julia": False}, {"modo": "funil"}])
    def test_nao_and_funil_never_auto_assign(self, admin, over):
        e = admin.equipe("Vendas", **{"modo": "julia", **over})
        admin.membro(e["id"], U1)
        w = admin.w
        assert svc.atribuir_responsavel(w.sw, w.core, ORG_ID, _contato(w, 1)) is None
        assert w.rows("julia_atribuicoes") == [] and w.contato("55119" + "00000001@c.us")["responsavel_user_id"] is None

    def test_no_active_member_assigns_nobody(self, admin):
        e = _auto(admin, U1)
        admin.req("patch", f"/api/julia/equipes/{e['id']}/membros/{U1}", {"ativo": False})
        w = admin.w
        assert svc.atribuir_responsavel(w.sw, w.core, ORG_ID, _contato(w, 1)) is None

    def test_two_teams_alternate(self, admin):
        _auto(admin, U1)
        e2 = admin.equipe("Locação", modo="julia")
        admin.membro(e2["id"], U2)
        for i, e in enumerate(admin.w.rows("julia_equipes")):  # the mock stamps no created_at; the DB does
            admin.w.sw.table("julia_equipes").update({"created_at": f"2026-10-0{i + 1}T00:00:00+00:00"}).eq("id", e["id"]).execute()
        admin.w.sw.table("julia_equipes").update({"created_at": "2026-10-01T00:00:00+00:00"}).eq("nome", "Vendas").execute()
        admin.w.sw.table("julia_equipes").update({"created_at": "2026-10-02T00:00:00+00:00"}).eq("nome", "Locação").execute()
        w = admin.w
        picks = [svc.atribuir_responsavel(w.sw, w.core, ORG_ID, _contato(w, n))["user_id"] for n in range(1, 5)]
        assert picks == [U1, U2, U1, U2]

    def test_estado_carries_atendente_nome_and_keeps_the_other_keys(self, admin):
        w = admin.w
        c = _contato(w, 1)
        base = ctxsvc.montar(w.sw, ORG_ID, c, ferramentas_habilitadas=False)["estado"]
        assert "atendente_nome" not in base
        w.sw.table("julia_contatos").update({"responsavel_user_id": U2}).eq("id", c["id"]).execute()
        c = w.contato("55119" + "00000001@c.us")
        estado = ctxsvc.montar(w.sw, ORG_ID, c, ferramentas_habilitadas=False)["estado"]
        assert estado["atendente_nome"] == "Marcos"
        assert set(base) <= set(estado)


# ── handoff wiring ──────────────────────────────────────────────────────────
CONV = "11111111-1111-4111-8111-111111111111"


@pytest.mark.asyncio
class TestHandoff:
    async def test_attendant_is_picked_before_notifying_and_gets_the_notification(self):
        w = _mundo()
        w.core.set_table_data("notifications", [])
        e = svc.criar(w.sw, w.core, ORG_ID, nome="Vendas", modo="julia")
        svc.adicionar_membro(w.sw, w.core, ORG_ID, e["id"], U2)
        w.agents = FakeAgentsClient([TurnResult(conversation_id=CONV, partes=("Já chamo alguém",), status="handoff",
                                                actions=(HandoffAction("quer humano"),))])
        key = buffer_lead(w, LEAD_CHAT, ["quero falar com gente"])
        await process_lead_batch(key, w.buffer.memory_for(key), deps=w.deps())
        assert w.contato()["responsavel_user_id"] == U2
        assert [n["user_id"] for n in w.notifications() if (n.get("metadata") or {}).get("tipo") == "julia_handoff"] == [U2]

    async def test_without_a_team_the_handoff_notifies_the_connection_owner_as_before(self):
        w = _mundo()
        w.core.set_table_data("notifications", [])
        w.agents = FakeAgentsClient([TurnResult(conversation_id=CONV, partes=("ok",), status="handoff", actions=(HandoffAction("x"),))])
        key = buffer_lead(w, LEAD_CHAT, ["oi"])
        await process_lead_batch(key, w.buffer.memory_for(key), deps=w.deps())
        assert w.contato()["responsavel_user_id"] is None
        assert [n["user_id"] for n in w.notifications() if (n.get("metadata") or {}).get("tipo") == "julia_handoff"] == [OWNER_ID]


# ── metrics ─────────────────────────────────────────────────────────────────
class TestMetricas:
    def test_tpr_distribuicao_conversas_and_ultimo_acesso(self, admin):
        e = _auto(admin, U1, U2)
        w = admin.w
        c = _contato(w, 1)
        t0 = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
        svc.atribuir_responsavel(w.sw, w.core, ORG_ID, c, "handoff", agora=t0)  # -> U1
        for n, minutos in ((1, -5), (2, 90)):  # one BEFORE the assignment, one 90 min after
            w.sw.table("conversation_messages").insert({
                "id": str(uuid4()), "org_id": ORG_ID, "session_id": "s", "connection_id": CONNECTION_ID, "chat_id": c["chat_id"],
                "direction": "outbound", "body": "oi", "created_at": (t0 + timedelta(minutes=minutos)).isoformat()}).execute()
        d = admin.req("get", f"/api/julia/equipes/{e['id']}/metricas?mes=2026-10").json()["data"]
        por = {m["user_id"]: m for m in d["membros"]}
        assert por[U1]["tpr_medio_s"] == 5400.0 and por[U1]["tpr_amostras"] == 1
        assert (por[U1]["distribuicao"], por[U1]["distribuicao_pct"], por[U1]["conversas"]) == (1, 100.0, 1)
        assert por[U1]["ultimo_acesso"] == "2026-10-10T10:00:00+00:00" and por[U2]["ultimo_acesso"] is None
        assert (por[U2]["distribuicao"], por[U2]["tpr_medio_s"], por[U2]["conversas"]) == (0, None, 0)
        assert d["fontes"]["ultimo_acesso"] == "core.noctus_users.last_active_at"
        outro_mes = admin.req("get", f"/api/julia/equipes/{e['id']}/metricas?mes=2026-09").json()["data"]
        assert outro_mes["total_atribuicoes"] == 0

    @pytest.mark.parametrize("mes", ["2026-13", "2026-1", "x"])
    def test_bad_month_is_422(self, admin, mes):
        e = admin.equipe()
        assert admin.req("get", f"/api/julia/equipes/{e['id']}/metricas?mes={mes}").status_code == 422


# ── Conversas: the equipe filter ────────────────────────────────────────────
class TestFiltroEquipe:
    def test_equipe_filters_by_responsavel_membership(self, admin):
        e = admin.equipe()
        admin.membro(e["id"], U2)
        w = admin.w
        a, b = _contato(w, 1), _contato(w, 2)
        w.sw.table("julia_contatos").update({"responsavel_user_id": U2}).eq("id", a["id"]).execute()
        w.sw.table("julia_contatos").update({"responsavel_user_id": U3}).eq("id", b["id"]).execute()
        r = admin.req("get", f"/api/julia/conversas?equipe={e['id']}")
        assert r.status_code == 200 and r.json()["meta"]["equipe"] == [e["id"]] and "equipe_ignorada" not in r.json()["meta"]
        assert {i["id"] for i in r.json()["data"]} == {a["id"]}
        k = admin.req("get", f"/api/julia/conversas?view=kanban&equipe={e['id']}").json()["data"]["colunas"][0]
        assert {i["id"] for i in k["itens"]} == {a["id"]}
        assert admin.req("get", "/api/julia/conversas?equipe=nao-uuid").status_code == 422

    def test_another_orgs_team_matches_nothing(self, admin):
        admin.w.sw.table("julia_equipes").insert({"id": str(uuid4()), "org_id": OTHER_ORG_ID, "nome": "Alheia"}).execute()
        eid = admin.w.sw.table("julia_equipes").select("id").eq("org_id", OTHER_ORG_ID).execute().data[0]["id"]
        admin.w.sw.table("julia_equipe_membros").insert({"equipe_id": eid, "org_id": OTHER_ORG_ID, "user_id": U2, "ativo": True, "ordem": 0}).execute()
        assert admin.req("get", f"/api/julia/conversas?equipe={eid}").json()["data"] == []
