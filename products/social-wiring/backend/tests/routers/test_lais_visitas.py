"""Lais wave 5 -- Visitas (contract section 7): slot computation, the `pedido_visita` action, the
state machine + routes, CPF never in clear, strict `== 401`.

Seams: mock DB, seed `FakeWahaClient`, hooks via `registrar_hook` -- nothing of ours is patched.
Fixtures carry no personal data (the CPF is the well-known invalid-by-checksum test pattern)."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.clients.agents import LaisAction, TurnResult
from app.services import lais_acoes_service as acoes
from app.services import lais_contatos_service as contatos
from app.services import lais_visitas_service as svc

from tests.support.lais_world import CONNECTION_ID, ENCRYPTION_KEY, LEAD_CHAT, ORG_ID, OTHER_ORG_ID, World

BASE = "/api/lais/visitas"
H = {"Authorization": "Bearer test-token"}
CPF = "52998224725"
GRADE_TODA_SEMANA = {d: [{"inicio": "09:00", "fim": "17:00"}] for d in svc.DIAS}
SEG = datetime(2026, 10, 19, 8, 0, tzinfo=svc.TZ)  # a Monday, 08:00 Sao Paulo


def _perfil(**over):
    base = {"ativo": True, "cpf_obrigatorio": False, "min_dias": 0, "min_horas": 0, "max_dias": 14, "grade": GRADE_TODA_SEMANA}
    base.update(over)
    return base


# ── slots (pure over the mock DB + the seed SchedulingEngine) ───────────────
class TestSlots:
    def test_grade_per_weekday_30_min_slots(self):
        w = World()
        w.sw.set_table_data("lais_visitas", [])
        perfil = _perfil(grade={"seg": [{"inicio": "09:00", "fim": "10:30"}], "ter": [{"inicio": "14:00", "fim": "15:00"}]}, max_dias=2)
        slots = svc.slots_livres(w.sw, ORG_ID, perfil, agora=SEG)
        horas = [(svc._dt(s["inicio"]).astimezone(svc.TZ).strftime("%a %H:%M")) for s in slots]
        assert horas == ["Mon 09:00", "Mon 09:30", "Mon 10:00", "Tue 14:00", "Tue 14:30"]
        assert all(svc._dt(s["fim"]) - svc._dt(s["inicio"]) == timedelta(minutes=30) for s in slots)

    def test_minimum_window_cuts_the_start(self):
        w = World()
        w.sw.set_table_data("lais_visitas", [])
        perfil = _perfil(grade={"seg": [{"inicio": "09:00", "fim": "11:00"}]}, min_horas=2, max_dias=1)
        slots = svc.slots_livres(w.sw, ORG_ID, perfil, agora=SEG)  # 08:00 + 2h => from 10:00
        assert [svc._dt(s["inicio"]).astimezone(svc.TZ).strftime("%H:%M") for s in slots] == ["10:00", "10:30"]

    def test_maximum_window_cuts_the_end(self):
        w = World()
        w.sw.set_table_data("lais_visitas", [])
        perfil = _perfil(grade=GRADE_TODA_SEMANA, max_dias=1)
        slots = svc.slots_livres(w.sw, ORG_ID, perfil, agora=SEG)
        assert slots and max(svc._dt(s["fim"]) for s in slots) <= SEG + timedelta(days=1)

    def test_a_booked_visit_is_not_offered_again_but_a_cancelled_one_is(self):
        w = World()
        ini = SEG.replace(hour=9)
        w.sw.set_table_data("lais_visitas", [
            {"id": str(uuid4()), "org_id": ORG_ID, "inicio": ini.isoformat(), "fim": (ini + timedelta(minutes=30)).isoformat(), "status": "confirmada"},
            {"id": str(uuid4()), "org_id": ORG_ID, "inicio": (ini + timedelta(minutes=30)).isoformat(),
             "fim": (ini + timedelta(hours=1)).isoformat(), "status": "cancelada"},
        ])
        perfil = _perfil(grade={"seg": [{"inicio": "09:00", "fim": "10:30"}]}, max_dias=1)
        horas = [svc._dt(s["inicio"]).astimezone(svc.TZ).strftime("%H:%M") for s in svc.slots_livres(w.sw, ORG_ID, perfil, agora=SEG)]
        assert horas == ["09:30", "10:00"]

    def test_another_orgs_visit_does_not_block(self):
        w = World()
        ini = SEG.replace(hour=9)
        w.sw.set_table_data("lais_visitas", [
            {"id": str(uuid4()), "org_id": OTHER_ORG_ID, "inicio": ini.isoformat(), "fim": (ini + timedelta(minutes=30)).isoformat(), "status": "confirmada"}])
        perfil = _perfil(grade={"seg": [{"inicio": "09:00", "fim": "09:30"}]}, max_dias=1)
        assert len(svc.slots_livres(w.sw, ORG_ID, perfil, agora=SEG)) == 1

    @pytest.mark.parametrize("grade", [
        {"seg": [{"inicio": "09:10", "fim": "10:00"}]},
        {"seg": [{"inicio": "10:00", "fim": "09:00"}]},
        {"seg": [{"inicio": "09:00", "fim": "10:00"}, {"inicio": "09:30", "fim": "11:00"}]},
        {"xxx": [{"inicio": "09:00", "fim": "10:00"}]},
        {"seg": [{"inicio": "9h", "fim": "10:00"}]},
    ])
    def test_invalid_grade_is_rejected(self, grade):
        with pytest.raises(ValueError):
            svc.ConfigVisitas(config={"geral": _perfil(grade=grade)})

    def test_separated_config_needs_both_profiles(self):
        with pytest.raises(ValueError):
            svc.ConfigVisitas(separar_operacao=True, config={"compra": _perfil()})
        assert svc.ConfigVisitas(separar_operacao=True, config={"compra": _perfil(), "aluguel": _perfil()})

    def test_per_operation_grade(self):
        w = World()
        w.sw.set_table_data("lais_visitas", [])
        cfg = {"separar_operacao": True, "config": {
            "compra": _perfil(grade={"seg": [{"inicio": "09:00", "fim": "09:30"}]}, max_dias=1),
            "aluguel": _perfil(grade={"seg": [{"inicio": "15:00", "fim": "15:30"}]}, max_dias=1),
        }}
        w.sw.set_table_data("lais_visitas_config", [{"org_id": ORG_ID, **cfg}])
        compra = svc.horarios_para_ferramenta(w.sw, ORG_ID, 7, "compra", agora=SEG)
        aluguel = svc.horarios_para_ferramenta(w.sw, ORG_ID, 7, "aluguel", agora=SEG)
        assert svc._dt(compra[0]["inicio"]).astimezone(svc.TZ).hour == 9
        assert svc._dt(aluguel[0]["inicio"]).astimezone(svc.TZ).hour == 15
        assert svc.horarios_para_ferramenta(w.sw, ORG_ID, 7, None, agora=SEG) == []  # no slot valid for both


# ── the `pedido_visita` action ──────────────────────────────────────────────
def _mundo(*, perfil=None, lead=False):
    w = World()
    w.sw.set_table_data("lais_visitas", [])
    w.sw.set_table_data("atendimento_agendamentos", [])
    w.sw.set_table_data("atendimentos", [])
    w.sw.set_table_data("lais_visitas_config", [{"org_id": ORG_ID, "separar_operacao": False, "config": {"geral": perfil or _perfil()}}])
    w.seed_connection()
    contato = contatos.obter_ou_criar_contato(w.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT, telefone_e164="+5511988887777")
    if lead:
        lead_id, atend_id = str(uuid4()), str(uuid4())
        w.sw.set_table_data("atendimentos", [{"id": atend_id, "org_id": ORG_ID, "lead_id": lead_id, "created_at": "2026-10-01T00:00:00+00:00"}])
        contatos.atualizar_contato(w.sw, contato["id"], {"lead_id": lead_id})
        contato = w.contato()
        w.atend_id = atend_id
    return w, contato


def _primeiro_slot(w):
    return svc.slots_livres(w.sw, ORG_ID, _perfil())[0]


def _pedir(w, contato, payload, *, seq=1, lote="lote-1"):
    res = TurnResult(conversation_id=str(uuid4()), partes=(), status="respondido", actions=(LaisAction("pedido_visita", seq, payload),))
    return asyncio.run(acoes.aplicar(w.sw, org_id=ORG_ID, contato=contato, result=res, lote_hash=lote))


class TestPedidoVisita:
    def test_the_handler_is_registered(self):
        from app.routers import lais_visitas_router  # noqa: F401  (import binds the handler)

        assert acoes.HANDLERS["pedido_visita"] is svc._h_pedido_visita

    def test_valid_request_inserts_solicitada_emits_event_and_calls_the_hook(self):
        w, contato = _mundo()
        visto: list = []
        anterior = svc.HOOKS["on_visita_solicitada"]
        svc.registrar_hook("on_visita_solicitada", lambda org, c, v: visto.append((org, c["id"], v["status"])))
        try:
            slot = _primeiro_slot(w)
            (r,) = _pedir(w, contato, {"inicio": slot["inicio"], "codigo": "CA1"})
        finally:
            svc.registrar_hook("on_visita_solicitada", anterior)
        assert r["estado"] == "aplicada"
        (v,) = w.rows("lais_visitas")
        assert v["status"] == "solicitada" and v["codigo_imovel"] == "CA1" and v["agendamento_id"] is None
        assert [e["tipo"] for e in w.rows("lais_eventos")] == ["pre_agendamento_visita"]
        assert visto == [(ORG_ID, contato["id"], "solicitada")]

    def test_a_failing_hook_never_loses_the_visit(self):
        w, contato = _mundo()
        anterior = svc.HOOKS["on_visita_solicitada"]
        svc.registrar_hook("on_visita_solicitada", lambda *a: 1 / 0)
        try:
            _pedir(w, contato, {"inicio": _primeiro_slot(w)["inicio"]})
        finally:
            svc.registrar_hook("on_visita_solicitada", anterior)
        assert len(w.rows("lais_visitas")) == 1

    @pytest.mark.parametrize("payload,erro", [
        ({"inicio": "2020-01-01T10:00:00-03:00"}, "horario_indisponivel"),   # past
        ({"inicio": "nao-e-data"}, "inicio_invalido"),
        ({}, "inicio_invalido"),
    ])
    def test_invalid_slots_are_refused(self, payload, erro):
        w, contato = _mundo()
        _pedir(w, contato, payload)
        assert w.rows("lais_visitas") == []
        assert w.rows("lais_acoes_aplicadas")[0]["resultado"] == {"erro": erro}

    def test_a_slot_off_the_30_min_grid_or_outside_the_grade_is_refused(self):
        w, contato = _mundo(perfil=_perfil(grade={d: [{"inicio": "09:00", "fim": "09:30"}] for d in svc.DIAS}))
        slot = svc._dt(svc.slots_livres(w.sw, ORG_ID, _perfil(grade={d: [{"inicio": "09:00", "fim": "09:30"}] for d in svc.DIAS}))[0]["inicio"])
        _pedir(w, contato, {"inicio": (slot + timedelta(minutes=10)).isoformat()}, lote="a")
        _pedir(w, contato, {"inicio": (slot + timedelta(hours=2)).isoformat()}, lote="b", seq=1)
        assert w.rows("lais_visitas") == []

    def test_double_booking_the_same_slot_is_refused(self):
        w, contato = _mundo()
        inicio = _primeiro_slot(w)["inicio"]
        _pedir(w, contato, {"inicio": inicio}, lote="a")
        _pedir(w, contato, {"inicio": inicio}, lote="b")
        assert len(w.rows("lais_visitas")) == 1

    def test_disabled_visits_are_refused(self):
        w, contato = _mundo(perfil=_perfil(ativo=False))
        _pedir(w, contato, {"inicio": _primeiro_slot(w)["inicio"]})
        assert w.rows("lais_visitas") == []

    def test_cpf_required_when_the_switch_is_on(self):
        w, contato = _mundo(perfil=_perfil(cpf_obrigatorio=True))
        inicio = _primeiro_slot(w)["inicio"]
        _pedir(w, contato, {"inicio": inicio}, lote="a")
        _pedir(w, contato, {"inicio": inicio, "cpf": "123"}, lote="b")
        assert w.rows("lais_visitas") == []
        _pedir(w, contato, {"inicio": inicio, "cpf": CPF}, lote="c")
        assert len(w.rows("lais_visitas")) == 1

    def test_cpf_is_never_stored_in_clear_anywhere(self):
        w, contato = _mundo(perfil=_perfil(cpf_obrigatorio=True))
        _pedir(w, contato, {"inicio": _primeiro_slot(w)["inicio"], "cpf": "529.982.247-25"})
        (v,) = w.rows("lais_visitas")
        assert v["cpf_final"] == "725" and len(v["cpf_hash"]) == 64 and CPF not in v["cpf_hash"]
        for tabela in ("lais_visitas", "lais_acoes_aplicadas", "lais_eventos", "lais_contatos"):
            blob = json.dumps(w.rows(tabela), default=str)
            assert CPF not in blob and "529.982.247-25" not in blob, tabela
        assert "cpf" not in w.rows("lais_acoes_aplicadas")[0]["payload"]
        assert "cpf_hash" not in svc.saida(v)  # nor in the API shape

    def test_replaying_the_same_batch_books_once(self):
        w, contato = _mundo()
        inicio = _primeiro_slot(w)["inicio"]
        _pedir(w, contato, {"inicio": inicio})
        (r,) = _pedir(w, contato, {"inicio": inicio})
        assert r["estado"] == "repetida" and len(w.rows("lais_visitas")) == 1


# ── routes ──────────────────────────────────────────────────────────────────
class Scene:
    def __init__(self, tc, world, contato):
        self.tc, self.w, self.contato = tc, world, contato

    def get(self, url, **kw):
        return self.tc.get(url, headers=H, **kw)

    def put(self, url, json, **kw):
        return self.tc.put(url, json=json, headers=H, **kw)

    def post(self, url, json=None, **kw):
        return self.tc.post(url, json=json if json is not None else {}, headers=H, **kw)

    def pedir(self, **payload):
        inicio = payload.pop("inicio", None) or _primeiro_slot(self.w)["inicio"]
        _pedir(self.w, self.contato, {"inicio": inicio, **payload}, lote=str(uuid4()))
        return self.w.rows("lais_visitas")[-1]


def _scene(override_settings_factory, *, role, lead=False):
    w, contato = _mundo(lead=lead)
    w.core.set_table_data("noctus_users", [{"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": role}])
    w.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role=role)))
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=w.admin),
    ):
        from app.main import app
        from app.routers.whatsapp_connections_router import get_waha_client_factory

        bind_consent_module_to_mock(w.root)
        app.dependency_overrides[get_waha_client_factory] = lambda: (lambda **kw: w.waha)
        override_settings_factory(encryption_key=ENCRYPTION_KEY)
        yield Scene(TestClient(app), w, contato)
        app.dependency_overrides.pop(get_waha_client_factory, None)


@pytest.fixture
def override_settings_factory():
    from app.config import settings as _settings
    from app.dependencies import get_settings
    from app.main import app

    overrides: dict = {}
    previous = app.dependency_overrides.get(get_settings)

    def apply(**kw):
        overrides.update(kw)
        stub = _settings.model_copy(update=dict(overrides))
        app.dependency_overrides[get_settings] = lambda: stub

    yield apply
    if previous is None:
        app.dependency_overrides.pop(get_settings, None)
    else:
        app.dependency_overrides[get_settings] = previous


@pytest.fixture
def admin(override_settings_factory):
    yield from _scene(override_settings_factory, role="owner")


@pytest.fixture
def admin_lead(override_settings_factory):
    yield from _scene(override_settings_factory, role="owner", lead=True)


@pytest.fixture
def member(override_settings_factory):
    yield from _scene(override_settings_factory, role="member")


class TestAuth:
    @pytest.mark.parametrize("method,url,body", [
        ("get", f"{BASE}/config", None),
        ("put", f"{BASE}/config", {"config": {}}),
        ("get", BASE, None),
        ("post", f"{BASE}/{uuid4()}/confirmar", {}),
        ("post", f"{BASE}/{uuid4()}/remarcar", {"inicio": "2026-10-20T10:00:00-03:00", "fim": "2026-10-20T10:30:00-03:00"}),
        ("post", f"{BASE}/{uuid4()}/cancelar", {}),
    ])
    def test_no_token_is_401(self, admin, method, url, body):
        r = getattr(admin.tc, method)(url, **({"json": body} if body is not None else {}))
        assert r.status_code == 401

    def test_a_member_can_read_but_not_write_the_config(self, member):
        assert member.get(f"{BASE}/config").status_code == 200
        r = member.put(f"{BASE}/config", {"separar_operacao": False, "config": {"geral": _perfil()}})
        assert r.status_code == 403


class TestConfigRoutes:
    def test_default_then_roundtrip(self, admin):
        d = admin.w.sw
        d.set_table_data("lais_visitas_config", [])
        pad = admin.get(f"{BASE}/config").json()["data"]
        assert pad["separar_operacao"] is False and pad["config"]["geral"]["grade"]["sab"] == [{"inicio": "09:00", "fim": "18:00"}]
        corpo = {"separar_operacao": False, "config": {"geral": _perfil(cpf_obrigatorio=True)}}
        assert admin.put(f"{BASE}/config", corpo).status_code == 200
        assert admin.get(f"{BASE}/config").json()["data"]["config"]["geral"]["cpf_obrigatorio"] is True

    def test_unknown_field_and_bad_grade_are_422(self, admin):
        assert admin.put(f"{BASE}/config", {"config": {"geral": _perfil()}, "x": 1}).status_code == 422
        assert admin.put(f"{BASE}/config", {"config": {"geral": _perfil(grade={"seg": [{"inicio": "09:10", "fim": "10:00"}]})}}).status_code == 422


class TestList:
    @pytest.mark.parametrize("view", ["mes", "month", "", "semanas"])
    def test_other_views_are_422_view_invalida(self, admin, view):
        r = admin.get(f"{BASE}?view={view}")
        assert r.status_code == 422 and r.json()["error"]["code"] == "view_invalida"

    def test_week_and_day_views(self, admin):
        v = admin.pedir()
        dia = svc._dt(v["inicio"]).astimezone(svc.TZ).date().isoformat()
        semana = admin.get(f"{BASE}?view=semana&data={dia}").json()["data"]
        dia_ = admin.get(f"{BASE}?view=dia&data={dia}").json()["data"]
        fora = admin.get(f"{BASE}?view=dia&data=2030-01-01").json()["data"]
        assert [x["id"] for x in semana] == [x["id"] for x in dia_] == [v["id"]] and fora == []
        assert "cpf_hash" not in semana[0]

    def test_filters(self, admin):
        v = admin.pedir()
        dia = svc._dt(v["inicio"]).astimezone(svc.TZ).date().isoformat()
        assert admin.get(f"{BASE}?view=semana&data={dia}&status=cancelada").json()["data"] == []
        assert admin.get(f"{BASE}?view=semana&data=lixo").status_code == 422

    def test_another_orgs_visit_is_not_listed(self, admin):
        v = admin.pedir()
        admin.w.sw.table("lais_visitas").update({"org_id": OTHER_ORG_ID}).eq("id", v["id"]).execute()
        dia = svc._dt(v["inicio"]).astimezone(svc.TZ).date().isoformat()
        assert admin.get(f"{BASE}?view=semana&data={dia}").json()["data"] == []


class TestTransitions:
    def test_confirm_with_a_card_creates_exactly_one_agendamento_and_messages_the_lead(self, admin_lead):
        s = admin_lead
        v = s.pedir()
        r = s.post(f"{BASE}/{v['id']}/confirmar")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["status"] == "confirmada" and d["agendamento_id"] and d["mensagem_enviada"] is True and d["aviso"] is None
        (ag,) = s.w.rows("atendimento_agendamentos")
        assert ag["tipo"] == "visita" and ag["atendimento_id"] == s.w.atend_id and ag["id"] == d["agendamento_id"]
        assert any("Visita confirmada" in t for t in s.w.sent_texts())

    def test_confirm_without_a_card_keeps_agendamento_null_and_says_so(self, admin):
        v = admin.pedir()
        d = admin.post(f"{BASE}/{v['id']}/confirmar").json()["data"]
        assert d["status"] == "confirmada" and d["agendamento_id"] is None and "sem_card" in d["aviso"]
        assert admin.w.rows("atendimento_agendamentos") == []

    def test_confirm_forces_envio_through_the_wave3_hook_when_not_sent(self, admin_lead):
        chamadas: list = []
        anterior = svc.HOOKS["forcar_envio_sw"]
        svc.registrar_hook("forcar_envio_sw", lambda org, c, v: chamadas.append(v["id"]))
        try:
            v = admin_lead.pedir()
            admin_lead.post(f"{BASE}/{v['id']}/confirmar")
        finally:
            svc.registrar_hook("forcar_envio_sw", anterior)
        assert chamadas == [v["id"]]

    def test_remarcar_updates_visit_and_the_single_agendamento(self, admin_lead):
        s = admin_lead
        v = s.pedir()
        s.post(f"{BASE}/{v['id']}/confirmar")
        novo = svc.slots_livres(s.w.sw, ORG_ID, _perfil(), ignorar_visita_id=v["id"])[3]
        r = s.post(f"{BASE}/{v['id']}/remarcar", {"inicio": novo["inicio"], "fim": novo["fim"]})
        assert r.status_code == 200 and r.json()["data"]["status"] == "remarcada"
        (ag,) = s.w.rows("atendimento_agendamentos")
        assert svc._dt(ag["quando"]) == svc._dt(novo["inicio"])
        assert any("remarcada" in t for t in s.w.sent_texts())

    def test_remarcar_to_an_invalid_or_taken_slot_is_422(self, admin):
        a, b = admin.pedir(), None
        outro = svc.slots_livres(admin.w.sw, ORG_ID, _perfil())[1]
        b = admin.pedir(inicio=outro["inicio"])
        r = admin.post(f"{BASE}/{a['id']}/remarcar", {"inicio": b["inicio"], "fim": b["fim"]})
        assert r.status_code == 422 and r.json()["error"]["code"] == "horario_indisponivel"
        off = svc._dt(a["inicio"]) + timedelta(minutes=10)
        r = admin.post(f"{BASE}/{a['id']}/remarcar", {"inicio": off.isoformat(), "fim": (off + timedelta(minutes=30)).isoformat()})
        assert r.status_code == 422

    def test_cancelar_soft_deletes_the_agendamento_and_messages_the_lead(self, admin_lead):
        s = admin_lead
        v = s.pedir()
        s.post(f"{BASE}/{v['id']}/confirmar")
        r = s.post(f"{BASE}/{v['id']}/cancelar", {"motivo": "lead desistiu"})
        assert r.status_code == 200 and r.json()["data"]["status"] == "cancelada"
        (ag,) = s.w.rows("atendimento_agendamentos")
        assert ag["deleted_at"]
        assert s.w.rows("lais_visitas")[0]["motivo_cancelamento"] == "lead desistiu"
        assert any("cancelada" in t for t in s.w.sent_texts())

    @pytest.mark.parametrize("antes,acao", [
        ("cancelada", "confirmar"), ("cancelada", "remarcar"), ("cancelada", "cancelar"),
        ("confirmada", "confirmar"),
    ])
    def test_illegal_transitions_are_409(self, admin, antes, acao):
        v = admin.pedir()
        if antes == "cancelada":
            assert admin.post(f"{BASE}/{v['id']}/cancelar").status_code == 200
        else:
            assert admin.post(f"{BASE}/{v['id']}/confirmar").status_code == 200
        corpo = {"inicio": v["inicio"], "fim": v["fim"]} if acao == "remarcar" else {}
        r = admin.post(f"{BASE}/{v['id']}/{acao}", corpo)
        assert r.status_code == 409 and r.json()["error"]["code"] == "transicao_invalida"

    def test_a_rescheduled_visit_can_be_confirmed_again(self, admin):
        v = admin.pedir()
        novo = svc.slots_livres(admin.w.sw, ORG_ID, _perfil(), ignorar_visita_id=v["id"])[2]
        admin.post(f"{BASE}/{v['id']}/remarcar", {"inicio": novo["inicio"], "fim": novo["fim"]})
        assert admin.post(f"{BASE}/{v['id']}/confirmar").json()["data"]["status"] == "confirmada"

    def test_unknown_visit_and_other_org_are_404(self, admin):
        assert admin.post(f"{BASE}/{uuid4()}/confirmar").status_code == 404
        v = admin.pedir()
        admin.w.sw.table("lais_visitas").update({"org_id": OTHER_ORG_ID}).eq("id", v["id"]).execute()
        assert admin.post(f"{BASE}/{v['id']}/confirmar").status_code == 404

    def test_a_message_that_cannot_leave_does_not_undo_the_state_change(self, admin):
        admin.w.sw.table("whatsapp_connections").update({"id": str(uuid4())}).eq("id", CONNECTION_ID).execute()  # contato points at a vanished line
        v = admin.pedir()
        d = admin.post(f"{BASE}/{v['id']}/confirmar").json()["data"]
        assert d["status"] == "confirmada" and d["mensagem_enviada"] is False

    def test_extra_body_fields_are_422(self, admin):
        v = admin.pedir()
        assert admin.post(f"{BASE}/{v['id']}/cancelar", {"motivo": "x", "extra": 1}).status_code == 422


class TestFerramentaHorariosVisita:
    def test_the_tool_serves_slots_from_the_config(self):
        from app.services.lais_ferramentas_service import FERRAMENTAS

        w, _ = _mundo()
        slots = FERRAMENTAS["horarios_visita"](w.sw, ORG_ID, {"dias": 3})
        assert slots and set(slots[0]) == {"inicio", "fim"}
        w.sw.set_table_data("lais_visitas_config", [{"org_id": ORG_ID, "separar_operacao": False, "config": {"geral": _perfil(ativo=False)}}])
        assert FERRAMENTAS["horarios_visita"](w.sw, ORG_ID, {"dias": 3}) == []
