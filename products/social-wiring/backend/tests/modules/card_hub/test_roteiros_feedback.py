"""Roteiro feedback, visited list, due list and funnel metrics (CONTRACT sw-lead-to-contract §3)."""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

import pytest
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_
from noctusai_lib.testing.mocks import MockSupabaseClient

from app.modules.card_hub import metricas_service
from app.modules.card_hub import roteiros_feedback_service as fb
from app.modules.card_hub import roteiros_service as svc
from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_agendamentos import atendimento_row
from tests.modules.card_hub.test_roteiros import imovel_row, registry_row

ORG = UUID(ORG_ID)
AGORA = datetime(2026, 10, 10, 12, 0, tzinfo=fb.TZ)


@pytest.fixture
def db():
    mock = MockSupabaseClient()
    cid, aid = str(uuid4()), str(uuid4())
    codigos = ("ONE9001", "ONE9002", "ONE9003")
    mock.set_table_data("clientes", [cliente_row(cid)])
    mock.set_table_data("atendimentos", [atendimento_row(aid, cid)])
    mock.set_table_data("imovel_registry", [registry_row(c) for c in codigos])
    mock.set_table_data("imoveis", [imovel_row(c) for c in codigos])
    mock.set_table_data("imovel_dados", [])
    mock.set_table_data("roteiros", [])
    mock.set_table_data("visitas", [])
    mock.set_table_data("atendimento_propostas", [])
    mock.set_table_data("pipeline_stages", [])
    mock.set_table_data("cliente_membros", [])
    mock.set_table_data("lead_corretores", [])
    return mock, UUID(cid), aid


def _roteiro(mock, cid, **kw):
    r = svc.criar(mock, ORG, cid, imoveis=["ONE9001", "ONE9002", "ONE9003"],
                  data_visita=kw.pop("data_visita", date(2026, 10, 9)))
    return r, UUID(r["id"]), [UUID(v["id"]) for v in r["visitas"]]


class TestCriarFunil:
    def test_missing_stage_is_reported_on_the_response(self, db):
        mock, cid, _ = db
        r, _, _ = _roteiro(mock, cid)
        assert r["funil"]["moveu"] is False and r["funil"]["motivo"] == "etapa_inexistente"
        assert r["feedback_status"] == "pendente"


class TestPendentes:
    def test_due_roteiro_listed_with_visitas(self, db):
        mock, cid, aid = db
        r, rid, vids = _roteiro(mock, cid)
        out = fb.pendentes(mock, ORG, agora=AGORA)
        assert len(out) == 1
        assert out[0]["roteiro_id"] == str(rid) and out[0]["atendimento_id"] == aid
        assert out[0]["cliente_nome"] == "Ana"
        assert [v["imovel_codigo"] for v in out[0]["visitas"]] == ["ONE9001", "ONE9002", "ONE9003"]
        assert out[0]["visitas"][0]["titulo"]

    def test_future_roteiro_not_due(self, db):
        mock, cid, _ = db
        _roteiro(mock, cid, data_visita=date(2026, 10, 11))
        assert fb.pendentes(mock, ORG, agora=AGORA) == []

    def test_today_respects_hora_visita(self, db):
        mock, cid, _ = db
        _, rid, _ = _roteiro(mock, cid, data_visita=date(2026, 10, 10))
        mock.table("roteiros").update({"hora_visita": "15:00:00"}).eq("id", str(rid)).execute()
        assert fb.pendentes(mock, ORG, agora=AGORA) == []
        assert len(fb.pendentes(mock, ORG, agora=AGORA.replace(hour=16))) == 1

    def test_answered_roteiro_leaves_the_list(self, db):
        mock, cid, _ = db
        _, rid, vids = _roteiro(mock, cid)
        fb.responder(mock, ORG, cid, rid, aconteceu=False, visitas=[])
        assert fb.pendentes(mock, ORG, agora=AGORA) == []


class TestResponder:
    def _todas(self, vids, **over):
        return [{"visita_id": str(v), "realizada": True, **over} for v in vids]

    def test_aconteceu_true_marks_visitas_and_roteiro(self, db):
        mock, cid, _ = db
        _, rid, vids = _roteiro(mock, cid)
        itens = self._todas(vids)
        itens[2] = {"visita_id": str(vids[2]), "realizada": False, "motivo": "imovel_indisponivel",
                    "observacao": "vendido"}
        out = fb.responder(mock, ORG, cid, rid, aconteceu=True, visitas=itens)
        assert out["feedback_status"] == "respondido" and out["feedback_em"]
        st = [(v["status"], v["nao_realizada_motivo"]) for v in out["visitas"]]
        assert st == [("realizada", None), ("realizada", None), ("nao_realizada", "imovel_indisponivel")]
        assert out["visitas"][0]["realizada_em"] and out["visitas"][2]["observacao"] == "vendido"
        assert out["contagem"]["realizadas"] == 2

    def test_aconteceu_true_requires_every_visita(self, db):
        mock, cid, _ = db
        _, rid, vids = _roteiro(mock, cid)
        with pytest.raises(ValidationError_):
            fb.responder(mock, ORG, cid, rid, aconteceu=True, visitas=self._todas(vids[:2]))
        assert svc.obter(mock, ORG, cid, rid)["feedback_status"] == "pendente"

    def test_realizada_false_requires_motivo(self, db):
        mock, cid, _ = db
        _, rid, vids = _roteiro(mock, cid)
        itens = self._todas(vids)
        itens[0]["realizada"] = False
        with pytest.raises(ValidationError_) as exc:
            fb.responder(mock, ORG, cid, rid, aconteceu=True, visitas=itens)
        assert exc.value.details["field"] == "motivo"
        # nothing half-written
        assert {v["status"] for v in svc.obter(mock, ORG, cid, rid)["visitas"]} == {"pendente"}

    def test_invalid_motivo_is_400(self, db):
        mock, cid, _ = db
        _, rid, vids = _roteiro(mock, cid)
        itens = self._todas(vids)
        itens[0].update(realizada=False, motivo="bogus")
        with pytest.raises(ValidationError_):
            fb.responder(mock, ORG, cid, rid, aconteceu=True, visitas=itens)

    def test_aconteceu_false_defaults_everything_to_outro(self, db):
        mock, cid, _ = db
        _, rid, vids = _roteiro(mock, cid)
        out = fb.responder(mock, ORG, cid, rid, aconteceu=False, visitas=[
            {"visita_id": str(vids[0]), "realizada": False, "motivo": "cliente_desistiu"}])
        assert [v["status"] for v in out["visitas"]] == ["nao_realizada"] * 3
        assert [v["nao_realizada_motivo"] for v in out["visitas"]] == ["cliente_desistiu", "outro", "outro"]

    def test_aconteceu_false_rejects_a_realizada_entry(self, db):
        mock, cid, _ = db
        _, rid, vids = _roteiro(mock, cid)
        with pytest.raises(ValidationError_):
            fb.responder(mock, ORG, cid, rid, aconteceu=False,
                         visitas=[{"visita_id": str(vids[0]), "realizada": True}])

    def test_unknown_visita_is_404_and_foreign_roteiro_too(self, db):
        mock, cid, _ = db
        _, rid, vids = _roteiro(mock, cid)
        with pytest.raises(NotFoundError):
            fb.responder(mock, ORG, cid, rid, aconteceu=False,
                         visitas=[{"visita_id": str(uuid4()), "realizada": False}])
        with pytest.raises(NotFoundError):
            fb.responder(mock, ORG, cid, uuid4(), aconteceu=False, visitas=[])

    def test_second_answer_is_409(self, db):
        mock, cid, _ = db
        _, rid, vids = _roteiro(mock, cid)
        fb.responder(mock, ORG, cid, rid, aconteceu=False, visitas=[])
        with pytest.raises(fb.RoteiroJaRespondido) as exc:
            fb.responder(mock, ORG, cid, rid, aconteceu=False, visitas=[])
        assert exc.value.status_code == 409


class TestVisitadas:
    def test_only_realizadas_with_proposta_state(self, db):
        mock, cid, aid = db
        _, rid, vids = _roteiro(mock, cid)
        itens = [{"visita_id": str(vids[0]), "realizada": True},
                 {"visita_id": str(vids[1]), "realizada": True},
                 {"visita_id": str(vids[2]), "realizada": False, "motivo": "reagendada"}]
        fb.responder(mock, ORG, cid, rid, aconteceu=True, visitas=itens)
        mock.set_table_data("atendimento_propostas", [
            {"id": "p-old", "org_id": ORG_ID, "atendimento_id": aid, "visita_id": str(vids[0]),
             "status": "cancelada", "created_at": "2026-10-10T10:00:00+00:00"},
            {"id": "p-1", "org_id": ORG_ID, "atendimento_id": aid, "visita_id": str(vids[0]),
             "status": "enviada", "created_at": "2026-10-10T11:00:00+00:00"},
        ])
        out = fb.visitadas(mock, ORG, cid, rid)
        assert [v["imovel_codigo"] for v in out] == ["ONE9001", "ONE9002"]
        assert out[0]["proposta"] == {"id": "p-1", "status": "enviada"}
        assert out[1]["proposta"] is None and out[1]["realizada_em"]

    def test_cancelled_proposta_frees_the_button(self, db):
        mock, cid, aid = db
        _, rid, vids = _roteiro(mock, cid)
        fb.responder(mock, ORG, cid, rid, aconteceu=True, visitas=[
            {"visita_id": str(v), "realizada": True} for v in vids])
        mock.set_table_data("atendimento_propostas", [
            {"id": "p", "org_id": ORG_ID, "atendimento_id": aid, "visita_id": str(vids[0]),
             "status": "cancelada", "created_at": "2026-10-10T10:00:00+00:00"}])
        assert fb.visitadas(mock, ORG, cid, rid)[0]["proposta"] is None


class TestMetricas:
    def test_funnel_counts_and_motivos(self, db):
        mock, cid, aid = db
        mock.table("atendimentos").update({"created_at": "2026-10-01T00:00:00+00:00"}).eq("id", aid).execute()
        _, rid, vids = _roteiro(mock, cid)
        mock.table("roteiros").update({"created_at": "2026-10-03T00:00:00+00:00"}).eq("id", str(rid)).execute()
        fb.responder(mock, ORG, cid, rid, aconteceu=True, visitas=[
            {"visita_id": str(vids[0]), "realizada": True},
            {"visita_id": str(vids[1]), "realizada": False, "motivo": "reagendada"},
            {"visita_id": str(vids[2]), "realizada": False, "motivo": "reagendada"}])
        mock.set_table_data("atendimento_propostas", [
            {"id": "a", "org_id": ORG_ID, "atendimento_id": aid, "visita_id": str(vids[0]),
             "status": "aceita", "created_at": "2099-01-01T00:00:00+00:00", "aceita_em": "2099-01-03T00:00:00+00:00"},
            {"id": "b", "org_id": ORG_ID, "atendimento_id": aid, "visita_id": None,
             "status": "recusada", "created_at": "2026-10-09T00:00:00+00:00"}])
        m = metricas_service.funil(mock, ORG, de=date(2026, 10, 1), ate=date(2026, 10, 31))
        assert m["leads"] == 1 and m["com_roteiro"] == 1
        assert m["visitas_agendadas"] == 3 and m["visitas_realizadas"] == 1
        assert m["visitas_nao_realizadas"] == {"reagendada": 2}
        assert (m["propostas_criadas"], m["propostas_aceitas"], m["propostas_recusadas"]) == (2, 1, 1)
        assert m["tempo_medio_dias"]["lead_a_roteiro"] == 2.0
        assert m["tempo_medio_dias"]["proposta_a_aceite"] == 2.0

    def test_cohort_is_bounded_by_the_period(self, db):
        mock, cid, aid = db
        mock.table("atendimentos").update({"created_at": "2026-01-01T00:00:00+00:00"}).eq("id", aid).execute()
        m = metricas_service.funil(mock, ORG, de=date(2026, 10, 1), ate=date(2026, 10, 31))
        assert m["leads"] == 0 and m["tempo_medio_dias"]["lead_a_roteiro"] is None

    def test_corretor_filter_falls_back_to_the_lead_when_the_card_has_no_member(self, db):
        mock, cid, aid = db
        corretor = uuid4()
        mock.table("atendimentos").update({"lead_id": "L1"}).eq("id", aid).execute()
        mock.set_table_data("leads", [{"id": "L1", "org_id": ORG_ID, "corretor_id": str(corretor)}])
        assert metricas_service.funil(mock, ORG, corretor_id=corretor)["leads"] == 1
        assert metricas_service.funil(mock, ORG, corretor_id=uuid4())["leads"] == 0


class TestAuthBoundary:
    @pytest.mark.parametrize("method,path,body", [
        ("get", "/api/roteiros/pendentes-feedback", None),
        ("get", "/api/metricas/atendimentos", None),
        ("post", f"/api/clientes/{uuid4()}/roteiros/{uuid4()}/feedback", {"aconteceu": False, "visitas": []}),
        ("get", f"/api/clientes/{uuid4()}/roteiros/{uuid4()}/visitadas", None),
    ])
    def test_no_token_is_exactly_401(self, anon_client, method, path, body):
        r = getattr(anon_client, method)(path, **({"json": body} if body is not None else {}))
        assert r.status_code == 401


class TestHoraVisita:
    def test_create_and_patch_store_the_time(self, db):
        from datetime import time

        mock, cid, _ = db
        r = svc.criar(mock, ORG, cid, imoveis=["ONE9001"], data_visita=date(2026, 10, 10),
                      hora_visita=time(15, 30))
        assert r["hora_visita"] == "15:30:00"
        rid = UUID(r["id"])
        assert svc.atualizar(mock, ORG, cid, rid, hora_visita=time(9, 0))["hora_visita"] == "09:00:00"
        assert svc.atualizar(mock, ORG, cid, rid, titulo="x")["hora_visita"] == "09:00:00"  # unset = untouched
        assert svc.atualizar(mock, ORG, cid, rid, hora_visita=None)["hora_visita"] is None  # explicit null clears

    def test_it_makes_the_prompt_due_only_after_that_time(self, db):
        from datetime import time

        mock, cid, _ = db
        svc.criar(mock, ORG, cid, imoveis=["ONE9001"], data_visita=date(2026, 10, 10),
                  hora_visita=time(15, 0))
        assert fb.pendentes(mock, ORG, agora=AGORA) == []  # 12:00
        assert len(fb.pendentes(mock, ORG, agora=AGORA.replace(hour=15, minute=1))) == 1

    def test_schemas_accept_hh_mm(self):
        from datetime import time

        from app.modules.card_hub.roteiro_schemas import RoteiroCreateBodyV2, RoteiroPatchBodyV2

        b = RoteiroCreateBodyV2(imoveis=["A"], data_visita="2026-10-10", hora_visita="15:30")
        assert b.hora_visita == time(15, 30)
        assert RoteiroPatchBodyV2(hora_visita=None).model_dump(exclude_unset=True) == {"hora_visita": None}
        with pytest.raises(Exception):
            RoteiroCreateBodyV2(imoveis=["A"], data_visita="2026-10-10", hora_visita="25:99")


def _membros(mock, cid, aid_unused=None, corretores=()):
    """corretores: [(id, nome, email_login, telefone)] — all assigned to the card."""
    mock.set_table_data("lead_corretores", [
        {"id": i, "org_id": ORG_ID, "nome": n, "ativo": True, "email_login": e, "telefone": t}
        for i, n, e, t in corretores])
    mock.set_table_data("cliente_membros", [
        {"cliente_id": str(cid), "lead_corretor_id": i, "org_id": ORG_ID} for i, *_ in corretores])


class TestMembrosDoCard:
    def test_pendentes_names_every_assigned_member(self, db):
        mock, cid, _ = db
        _membros(mock, cid, corretores=[("k1", "Bruno", "b@x.com", None), ("k2", "Ana", None, "5511")])
        _roteiro(mock, cid)
        p = fb.pendentes(mock, ORG, agora=AGORA)[0]
        assert [m["nome"] for m in p["membros"]] == ["Ana", "Bruno"] and p["destino"] == "membros"

    def test_no_member_says_org_in_the_payload(self, db):
        mock, cid, _ = db
        _membros(mock, cid, corretores=[])
        _roteiro(mock, cid)
        p = fb.pendentes(mock, ORG, agora=AGORA)[0]
        assert p["membros"] == [] and p["destino"] == "org"


class _Recorder:
    """NotificationService with only the transport seam (`_dispatch`) recorded."""

    @staticmethod
    def build(mock):
        from app.services.notification_service import DispatchOutcome, NotificationService

        class Rec(NotificationService):
            sent: list = []

            async def _dispatch(self, *, kind, org_id, recipients, message, **kw):
                self.sent.append(([r["name"] for r in recipients], message["text"]))
                return DispatchOutcome(recipients=len(recipients), attempted=1, succeeded=1)

            # The test mock's cached schema for this table still has the
            # pre-046 `client_id` column, so the real tier query (`marca_id`)
            # cannot be built against it; the roster read is replaced by the
            # equivalent plain read. Routing (who gets asked) is what is tested.
            def _fetch_recipients_scoped(self, *, org_id, marca_id):
                return [r for r in self._admin.schema("x").table("notification_recipients").select("*").execute().data
                        if r.get("is_active")]

        svc_ = object.__new__(Rec)
        # `MockSupabaseClient.schema()` returns a fresh EMPTY wrapper per call
        # (see card_hub.deps), so the scoped mock is handed back as-is.
        svc_._admin = type("Admin", (), {"schema": lambda self, _n: mock})()
        svc_.sent = []
        return svc_


@pytest.mark.asyncio
class TestNotifyMembros:
    async def test_every_member_is_asked_once(self, db):
        mock, cid, _ = db
        _membros(mock, cid, corretores=[("k1", "Bruno", "b@x.com", None), ("k2", "Ana", None, "5511")])
        _roteiro(mock, cid)
        n = _Recorder.build(mock)
        await n.notify_visita_feedback(org_id=ORG, pendentes=fb.pendentes(mock, ORG, agora=AGORA))
        assert sorted(s[0][0] for s in n.sent) == ["Ana", "Bruno"]
        assert all("Visita de Ana aconteceu?" in s[1] for s in n.sent)  # the cliente is "Ana"

    async def test_no_member_falls_back_to_the_org_roster(self, db):
        mock, cid, _ = db
        _membros(mock, cid, corretores=[])
        mock.set_table_data("notification_recipients", [
            {"id": "n1", "org_id": ORG_ID, "name": "Dono", "email": "d@x.com", "whatsapp_number": None,
             "is_active": True, "marca_id": None}])
        _roteiro(mock, cid)
        n = _Recorder.build(mock)
        await n.notify_visita_feedback(org_id=ORG, pendentes=fb.pendentes(mock, ORG, agora=AGORA))
        assert [s[0] for s in n.sent] == [["Dono"]]

    async def test_members_without_any_channel_fall_back_too(self, db):
        mock, cid, _ = db
        _membros(mock, cid, corretores=[("k1", "Bruno", None, None)])
        mock.set_table_data("notification_recipients", [
            {"id": "n1", "org_id": ORG_ID, "name": "Dono", "email": "d@x.com", "whatsapp_number": None,
             "is_active": True, "marca_id": None}])
        _roteiro(mock, cid)
        n = _Recorder.build(mock)
        await n.notify_visita_feedback(org_id=ORG, pendentes=fb.pendentes(mock, ORG, agora=AGORA))
        assert [s[0] for s in n.sent] == [["Dono"]]


class TestMetricasCorretor:
    def _cohort(self, db):
        mock, cid, aid = db
        mock.table("atendimentos").update({"lead_id": "L1"}).eq("id", aid).execute()
        return mock, cid

    def test_a_card_counts_for_each_assigned_member(self, db):
        mock, cid = self._cohort(db)
        _membros(mock, cid, corretores=[("k1", "Bruno", None, None), ("k2", "Ana", None, None)])
        mock.set_table_data("leads", [])
        for k in ("k1", "k2"):
            assert metricas_service.funil(mock, ORG, corretor_id=k)["leads"] == 1
        assert metricas_service.funil(mock, ORG, corretor_id="k3")["leads"] == 0

    def test_lead_corretor_is_only_the_fallback_for_a_card_with_no_member(self, db):
        mock, cid = self._cohort(db)
        mock.set_table_data("leads", [{"id": "L1", "org_id": ORG_ID, "corretor_id": "k9"}])
        _membros(mock, cid, corretores=[])
        assert metricas_service.funil(mock, ORG, corretor_id="k9")["leads"] == 1
        # once the card HAS a member, the lead's corretor no longer claims it
        _membros(mock, cid, corretores=[("k1", "Bruno", None, None)])
        assert metricas_service.funil(mock, ORG, corretor_id="k9")["leads"] == 0
