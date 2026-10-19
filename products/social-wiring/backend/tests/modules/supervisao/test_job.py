"""Maya's jobs (maya-blocks CONTRACT §2.3 / §3.1 / §3.4): nightly scorecard upsert is idempotent (incl. the
NULL agent_key of a human block), the owner-only report (in-app rule + email digest via the seed
`FakeEmailSender`), the handoff sweep, and the scheduler registration. Seams: mock DB, the notification
service's own core-provider seam, the seed FakeEmailSender -- nothing of ours is patched."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import pytest
from noctusai_lib.integrations.email import FakeEmailSender

from app.modules.supervisao import relatorio
from app.modules.supervisao import scheduler as job
from app.modules.supervisao import service as svc
from app.services import julia_eventos_service as eventos
from app.services import julia_notificacoes_service as notif

from tests.support.julia_world import ADMIN_ID, MEMBER_ID, ORG_ID, OTHER_ORG_ID, OWNER_ID, World

AGORA = datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc)  # 07:00 in São Paulo
ONTEM = date(2026, 10, 18)
OWNER_EMAIL = "dona@example.com"
ADMIN_EMAIL = "admin@example.com"


@contextmanager
def _core_injetado(w):
    notif.registrar_core_provider(lambda: w.core)
    try:
        yield
    finally:
        notif.registrar_core_provider(None)


def _mundo(*, ativa=True, blocos=(("sdr", "julia", True), ("atendimento", None, True), ("juridico", None, False))):
    w = World()
    for t in ("julia_envio_entregas", "julia_atribuicoes", "atendimento_handoffs", "agente_scorecards",
              "julia_notificacao_prefs", "pipeline_movimentos", "cliente_notas", "atendimentos", "processos_venda"):
        w.sw.set_table_data(t, [])
    w.core.set_table_data("noctus_users", [
        {"id": OWNER_ID, "org_id": ORG_ID, "org_role": "owner", "email": OWNER_EMAIL},
        {"id": ADMIN_ID, "org_id": ORG_ID, "org_role": "admin", "email": ADMIN_EMAIL},
        {"id": MEMBER_ID, "org_id": ORG_ID, "org_role": "member", "email": "m@example.com"},
    ])
    w.sw.set_table_data("supervisao_config", [
        {"org_id": ORG_ID, "supervisao_ativa": ativa, "horas_para_assumir": 24,
         "updated_at": "2026-10-01T12:00:00+00:00", "created_at": "2026-10-01T12:00:00+00:00"},
        {"org_id": OTHER_ORG_ID, "supervisao_ativa": False, "horas_para_assumir": 24,
         "updated_at": "2026-10-01T12:00:00+00:00", "created_at": "2026-10-01T12:00:00+00:00"},
    ])
    w.sw.set_table_data("atendimento_blocos", [
        {"id": f"b{i}", "org_id": ORG_ID, "bloco": b, "agent_key": k, "ativo": a,
         "pipeline": None if b == "sdr" else ("funil" if b == "atendimento" else "processos_venda"),
         "etapas": []}
        for i, (b, k, a) in enumerate(blocos)
    ])
    w.sw.set_table_data("julia_contatos", [
        {"id": "c1", "org_id": ORG_ID, "created_at": "2026-10-18T13:00:00+00:00"},
    ])
    notif.registrar()
    return w


def _rodar(w, sender):
    with _core_injetado(w):
        return asyncio.run(job.executar_diario(client=w.sw, core=w.core, agora=AGORA, sender_factory=lambda: sender))


def _relatorios(w):
    return [e for e in w.sw.table("julia_eventos").select("*").execute().data if e["tipo"] == "relatorio"]


class TestScorecardsDiarios:
    def test_upserts_last_7_days_for_each_ativo_block_and_rerun_is_idempotent(self):
        w, fake = _mundo(), FakeEmailSender()
        _rodar(w, fake)
        primeira = w.sw.table("agente_scorecards").select("*").execute().data
        assert len(primeira) == 14  # sdr + atendimento (juridico is not ativo) x 7 days
        assert {(r["bloco"], r["agent_key"], r["rubrica_versao"]) for r in primeira} == {
            ("sdr", "julia", "sdr.v2"), ("atendimento", None, "atendimento.v1")}
        assert sorted({r["dia"] for r in primeira}) == [(ONTEM - timedelta(days=k)).isoformat() for k in range(6, -1, -1)]
        _rodar(w, fake)
        segunda = w.sw.table("agente_scorecards").select("*").execute().data
        assert len(segunda) == 14  # NULLS NOT DISTINCT: the human block's NULL agent_key did not duplicate
        sdr_ontem = next(r for r in segunda if r["bloco"] == "sdr" and r["dia"] == ONTEM.isoformat())
        assert sdr_ontem["metricas"]["leads_entrada"] == 1 and sdr_ontem["calculado_at"] == AGORA.isoformat()

    def test_days_before_supervision_was_on_have_missing_handoff_metrics(self):
        w = _mundo()
        w.sw.table("supervisao_config").update({"updated_at": "2026-10-16T12:00:00+00:00"}).eq("org_id", ORG_ID).execute()
        _rodar(w, FakeEmailSender())
        rows = {(r["bloco"], r["dia"]): r["metricas"] for r in w.sw.table("agente_scorecards").select("*").execute().data}
        assert rows[("sdr", "2026-10-16")]["handoffs_emitidos"] is None   # supervision turned on mid-day
        assert rows[("sdr", "2026-10-17")]["handoffs_emitidos"] == 0
        assert rows[("atendimento", "2026-10-15")]["handoffs_recebidos"] is None

    def test_org_with_supervision_off_gets_nothing(self):
        w, fake = _mundo(ativa=False), FakeEmailSender()
        assert _rodar(w, fake) == {}
        assert w.sw.table("agente_scorecards").select("*").execute().data == []
        assert _relatorios(w) == [] and fake.sent == []

    def test_no_ativo_block_means_no_scorecard_and_no_report(self):
        w, fake = _mundo(blocos=(("sdr", "julia", False),)), FakeEmailSender()
        out = _rodar(w, fake)
        assert out[ORG_ID]["relatorio"] == {"status": "sem_scorecards"} and fake.sent == []

    def test_nothing_lead_facing_is_written(self):
        w = _mundo()
        _rodar(w, FakeEmailSender())
        assert w.sent_texts() == []
        assert w.sw.table("julia_contatos").select("*").execute().data == [
            {"id": "c1", "org_id": ORG_ID, "created_at": "2026-10-18T13:00:00+00:00"}]


class TestRelatorioDono:
    def test_once_per_day_in_app_and_email_to_owners_only(self):
        w, fake = _mundo(), FakeEmailSender()
        _rodar(w, fake)
        _rodar(w, fake)  # same day again: the stored event is the marker
        rels = _relatorios(w)
        assert len(rels) == 1 and rels[0]["contato_id"] is None
        assert rels[0]["payload"] == {"origem": "supervisao", "dia": ONTEM.isoformat(), "falhas_registro": 0}
        assert [n["user_id"] for n in w.notifications()] == [OWNER_ID]
        assert w.notifications()[0]["metadata"]["link"] == "/supervisao?dia=2026-10-18"
        assert [e.to for e in fake.sent] == [[OWNER_EMAIL]]
        email = fake.sent[0]
        assert email.subject == "[Supervisão] Relatório de 18/10/2026"
        assert "SDR (Julia)" in email.text and "Leads de entrada: 1" in email.text
        assert "Taxa de qualificação: sem dado" not in email.text  # 1 lead in: the ratio exists (0.0%)
        assert "Handoffs por motivo: nenhum" in email.text

    def test_registration_failures_of_the_day_flag_every_scorecard_and_the_report(self):
        """G4: `supervisao_falha` events of the day -> `falhas_registro` / `dados_incompletos` on each scorecard, and
        the nightly report (event payload + email text) says so."""
        w, fake = _mundo(), FakeEmailSender()
        for codigo in ("handoff_movimento", "aceite_sem_ator"):
            w.sw.table("julia_eventos").insert({
                "org_id": ORG_ID, "tipo": "supervisao_falha", "contato_id": None, "lido_por": [],
                "payload": {"codigo": codigo, "dia": ONTEM.isoformat(), "ids": {}}, "created_at": "2026-10-18T15:00:00+00:00"}).execute()
        _rodar(w, fake)
        ontem = [r for r in w.sw.table("agente_scorecards").select("*").execute().data if r["dia"] == ONTEM.isoformat()]
        assert ontem and all(r["metricas"]["falhas_registro"] == 2 and r["metricas"]["dados_incompletos"] is True for r in ontem)
        anteontem = [r for r in w.sw.table("agente_scorecards").select("*").execute().data
                     if r["dia"] == (ONTEM - timedelta(days=1)).isoformat()]
        assert anteontem and all(r["metricas"]["dados_incompletos"] is False for r in anteontem)
        assert _relatorios(w)[0]["payload"]["falhas_registro"] == 2
        assert "ATENÇÃO: 2 falha(s) de registro" in fake.sent[0].text
        assert "Dados incompletos: sim" in fake.sent[0].text

    def test_email_not_configured_keeps_the_in_app_report(self):
        w = _mundo()
        with _core_injetado(w):
            out = asyncio.run(relatorio.enviar_relatorio(w.sw, w.core, ORG_ID, ONTEM, sender_factory=lambda: None))
        assert out["status"] == "sem_scorecards"  # no scorecards computed yet -> nothing at all
        _rodar(w, None)
        assert len(_relatorios(w)) == 1 and [n["user_id"] for n in w.notifications()] == [OWNER_ID]

    def test_missing_values_render_as_missing_never_zero(self):
        assert relatorio.formatar("qualificacao_taxa", None) == "sem dado"
        assert relatorio.formatar("tpr_p50_s", None) == "sem dado"
        assert relatorio.formatar("qualificacao_taxa", 0.2903) == "29.0%"
        assert relatorio.formatar("tpr_p90_s", 610.0) == "10.2 min"


class TestRegraNotificacao:
    def test_supervision_relatorio_goes_to_owners_only(self):
        w = _mundo()
        with _core_injetado(w):
            eventos.emitir(w.sw, ORG_ID, "relatorio", None, {"origem": "supervisao", "dia": "2026-10-18"})
        assert sorted(n["user_id"] for n in w.notifications()) == [OWNER_ID]

    def test_other_contato_less_relatorio_still_reaches_owners_and_admins(self):
        w = _mundo()
        with _core_injetado(w):
            eventos.emitir(w.sw, ORG_ID, "relatorio", None, {})
        assert sorted(n["user_id"] for n in w.notifications()) == sorted([OWNER_ID, ADMIN_ID])

    def test_owner_can_switch_the_relatorio_type_off(self):
        w = _mundo()
        w.sw.set_table_data("julia_notificacao_prefs", [{"org_id": ORG_ID, "user_id": OWNER_ID, "tipo": "relatorio", "in_app": False}])
        with _core_injetado(w):
            eventos.emitir(w.sw, ORG_ID, "relatorio", None, {"origem": "supervisao", "dia": "2026-10-18"})
        assert w.notifications() == []


class TestSweep:
    """The scheduled 15-min job delegates to the blocks slice's `handoffs.varrer` (one status machine)."""

    H = "00000000-0000-4000-8000-0000000000{:02d}"

    def _handoff(self, w, n, criado, atendimento_id=None, origem="o", gatilho="novo_lead"):
        w.sw.table("atendimento_handoffs").insert({
            "id": self.H.format(n), "org_id": ORG_ID, "de_bloco": "sdr", "para_bloco": "atendimento",
            "gatilho": gatilho, "origem_evento": f"{origem}{n}", "status": "emitido", "created_at": criado,
            "atendimento_id": atendimento_id, "assumido_at": None, "expirado_at": None}).execute()

    def _estado(self, w, n):
        return next(r for r in w.sw.table("atendimento_handoffs").select("*").execute().data if r["id"] == self.H.format(n))

    def test_first_signal_assumes_deadline_expires_julia_notes_never_count(self):
        w = _mundo()
        w.sw.set_table_data("atendimentos", [
            {"id": "a1", "org_id": ORG_ID, "cliente_id": "k1"}, {"id": "a2", "org_id": ORG_ID, "cliente_id": "k2"},
            {"id": "a3", "org_id": ORG_ID, "cliente_id": "k3"}, {"id": "a4", "org_id": ORG_ID, "cliente_id": "k4"}])
        w.sw.set_table_data("processos_venda", [{"id": "p4", "org_id": ORG_ID, "atendimento_id": "a4"}])
        self._handoff(w, 1, "2026-10-19T08:00:00+00:00", "a1")   # stage move later -> assumido
        self._handoff(w, 2, "2026-10-19T08:00:00+00:00", "a2")   # human note -> assumido
        self._handoff(w, 3, "2026-10-17T08:00:00+00:00", "a3")   # only Julia's note, past deadline -> expirado
        self._handoff(w, 4, "2026-10-17T08:00:00+00:00", "a4")   # processo move after the deadline -> expirado
        self._handoff(w, 5, "2026-10-19T08:00:00+00:00", None)   # no card, not due -> stays emitido
        w.sw.set_table_data("pipeline_movimentos", [
            {"id": "m0", "org_id": ORG_ID, "responsavel_id": OWNER_ID, "entidade_id": "a1", "created_at": "2026-10-19T07:00:00+00:00"},  # before
            # stored oldest-first: `varrer` takes `.order("created_at").limit(1)`, and MockSupabaseClient's
            # `.order()` does not sort -- the real PostgREST does.
            {"id": "m2", "org_id": ORG_ID, "responsavel_id": OWNER_ID, "entidade_id": "a1", "created_at": "2026-10-19T09:00:00+00:00"},
            {"id": "m1", "org_id": ORG_ID, "responsavel_id": OWNER_ID, "entidade_id": "a1", "created_at": "2026-10-19T09:30:00+00:00"},
            {"id": "m4", "org_id": ORG_ID, "responsavel_id": OWNER_ID, "entidade_id": "p4", "created_at": "2026-10-18T09:00:00+00:00"},
        ])
        w.sw.set_table_data("cliente_notas", [
            {"id": "n2", "org_id": ORG_ID, "cliente_id": "k2", "autor_id": OWNER_ID, "created_at": "2026-10-19T08:30:00+00:00"},
            {"id": "n3", "org_id": ORG_ID, "cliente_id": "k3", "autor_id": None, "created_at": "2026-10-17T09:00:00+00:00"},
        ])
        out = job.executar_sweep(client=w.sw, agora=AGORA)
        assert out == {ORG_ID: {"assumidos": 2, "expirados": 2}}
        h1, h2, h3, h4, h5 = (self._estado(w, n) for n in range(1, 6))
        assert (h1["status"], h1["assumido_at"]) == ("assumido", "2026-10-19T09:00:00+00:00")
        assert (h2["status"], h2["assumido_at"]) == ("assumido", "2026-10-19T08:30:00+00:00")
        assert (h3["status"], h3["expirado_at"]) == ("expirado", AGORA.isoformat())
        assert h4["status"] == "expirado" and h4["assumido_at"] is None
        assert h5["status"] == "emitido"
        assert job.executar_sweep(client=w.sw, agora=AGORA) == {ORG_ID: {"assumidos": 0, "expirados": 0}}

    def test_movimento_that_created_the_handoff_is_not_a_takeover(self):
        w = _mundo()
        w.sw.set_table_data("atendimentos", [{"id": "a1", "org_id": ORG_ID, "cliente_id": None}])
        self._handoff(w, 1, "2026-10-19T08:00:00+00:00", "a1", origem="m", gatilho="movimento_etapa")
        w.sw.set_table_data("pipeline_movimentos", [
            {"id": "m1", "org_id": ORG_ID, "responsavel_id": OWNER_ID, "entidade_id": "a1", "created_at": "2026-10-19T08:00:01+00:00"}])
        job.executar_sweep(client=w.sw, agora=AGORA)
        assert self._estado(w, 1)["status"] == "emitido"


class TestRegistro:
    def test_jobs_registered_on_the_seed_scheduler_at_07h_sp(self):
        class Sched:
            def __init__(self):
                self.jobs = {}

            def register(self, name, fn, **kw):
                self.jobs[name] = kw

        s = Sched()
        job.configure(scheduler=s)
        assert s.jobs[job.JOB_DIARIO]["cron"] == "0 7 * * *"
        assert s.jobs[job.JOB_SWEEP]["cron"] == job.CRON_SWEEP


@pytest.fixture(autouse=True)
def _limpa_sinks():
    yield
    notif.registrar_core_provider(None)
