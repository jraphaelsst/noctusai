"""Scheduled broadcast sweep — `TransmissoesService.executar_agendadas` + job."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from noctusai_lib.domain.jobs import make_job_repository
from noctusai_lib.integrations.whatsapp.fake_adapter import FakeWahaClient
from noctusai_lib.testing import MockSupabaseClient

from app.scheduler import TRANSMISSOES_AGENDADAS_JOB, configure, transmissoes_agendadas_job
from app.services.transmissoes_service import TransmissoesService

ORG = UUID("00000000-0000-0000-0000-000000000123")
GRUPO = "11111111-1111-1111-1111-111111111111"
CHAT = "5511999990000@g.us"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def _svc(agendada_para, estado="agendada"):
    mock = MockSupabaseClient()
    mock.set_table_data("grupos", [{"id": GRUPO, "org_id": str(ORG), "chat_id": CHAT, "nome": "G"}])
    mock.set_table_data("transmissoes", [{
        "id": "t1", "org_id": str(ORG), "titulo": "A", "corpo": "Olá", "tipo": "anuncio",
        "estado": estado, "agendada_para": agendada_para.isoformat(),
    }])
    mock.set_table_data("transmissao_destinos", [{
        "id": "d1", "org_id": str(ORG), "transmissao_id": "t1", "grupo_id": GRUPO, "estado": "pendente",
    }])
    return TransmissoesService(mock, org_id=ORG), mock


def _estado(mock):
    return mock.table("transmissoes").select("*").eq("id", "t1").execute().data[0]["estado"]


class _Counting(FakeWahaClient):
    def __init__(self):
        super().__init__()
        self.sent = 0

    async def send_text(self, *a, **k):
        self.sent += 1
        return await super().send_text(*a, **k)


def test_due_row_sent_once_even_across_two_ticks():
    svc, mock = _svc(NOW - timedelta(minutes=1))
    client = _Counting()
    repo = make_job_repository(use_fake=True)
    r1 = asyncio.run(svc.executar_agendadas(waha_client=client, now=NOW, jobs_repo=repo))
    r2 = asyncio.run(svc.executar_agendadas(waha_client=client, now=NOW, jobs_repo=repo))
    assert r1["enviadas"] == 1 and r2["vencidas"] == 0
    assert client.sent == 1
    assert _estado(mock) == "enviada"


def test_claim_loser_does_not_send():
    svc, mock = _svc(NOW - timedelta(minutes=1))
    assert svc._claim("t1", "enviando") is True
    assert svc._claim("t1", "enviando") is False  # second claimant loses
    client = _Counting()
    asyncio.run(svc.executar_agendadas(waha_client=client, now=NOW))
    assert client.sent == 0  # no longer "agendada"


def test_not_due_row_untouched():
    svc, mock = _svc(NOW + timedelta(hours=1))
    client = _Counting()
    r = asyncio.run(svc.executar_agendadas(waha_client=client, now=NOW))
    assert r["vencidas"] == 0 and client.sent == 0
    assert _estado(mock) == "agendada"


def test_not_connected_keeps_agendada_and_warns(caplog):
    svc, mock = _svc(NOW - timedelta(minutes=5))
    with caplog.at_level(logging.WARNING):
        r = asyncio.run(svc.executar_agendadas(waha_client=None, now=NOW))
    assert r["adiadas"] == 1
    assert _estado(mock) == "agendada"
    assert any("não está conectado" in m for m in caplog.messages)


def test_not_connected_past_24h_marks_falhou():
    svc, mock = _svc(NOW - timedelta(hours=25))
    r = asyncio.run(svc.executar_agendadas(waha_client=None, now=NOW))
    assert r["falhas"] == 1
    assert _estado(mock) == "falhou"
    destino = mock.table("transmissao_destinos").select("*").execute().data[0]
    assert destino["estado"] == "falhou" and "WhatsApp" in destino["erro"]


def test_job_registered_every_minute():
    from noctusai_lib.api.scheduler import scheduler

    configure()
    jobs = [j for j in scheduler.get_jobs() if j.id == TRANSMISSOES_AGENDADAS_JOB]
    assert len(jobs) == 1


def test_job_delegates_and_swallows_into_log():
    class _Boom:
        async def executar_agendadas(self, **_):
            raise RuntimeError("db down")

    assert asyncio.run(transmissoes_agendadas_job(_Boom())) == {"erro": "db down"}


class TestEnviarManualClaim:
    def test_lost_claim_409_and_no_send(self):
        for estado in ("enviando", "enviada"):
            svc, mock = _svc(NOW, estado=estado)
            client = _Counting()
            try:
                asyncio.run(svc.enviar(transmissao_id="t1", waha_client=client))
                assert False, "expected 409"
            except Exception as exc:
                assert exc.status_code == 409
                assert exc.code == "TRANSMISSAO_JA_ENVIADA"
                assert "já" in exc.detail
            assert client.sent == 0
            assert _estado(mock) == estado

    def test_rascunho_claims_and_sends_once(self):
        svc, mock = _svc(NOW, estado="rascunho")
        client = _Counting()
        repo = make_job_repository(use_fake=True)
        asyncio.run(svc.enviar(transmissao_id="t1", waha_client=client, jobs_repo=repo))
        assert client.sent == 1 and _estado(mock) == "enviada"
