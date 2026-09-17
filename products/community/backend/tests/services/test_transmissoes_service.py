"""Tests for `TransmissoesService` — contract §Transmissões.

Each test builds its OWN `FakeJobRepository` (via `jobs_repo=`) rather
than relying on the process-lifetime singleton, so tests never leak
`dedupe_key` state into each other.
"""
import asyncio
from uuid import UUID

from noctusai_lib.domain.jobs import make_job_repository
from noctusai_lib.integrations.whatsapp.fake_adapter import FakeWahaClient
from noctusai_lib.testing import MockSupabaseClient

from app.services.transmissoes_service import TransmissoesService, TransmissoesServiceError

ORG = UUID("00000000-0000-0000-0000-000000000123")
GRUPO_1 = "11111111-1111-1111-1111-111111111111"
GRUPO_2 = "22222222-2222-2222-2222-222222222222"
CHAT_1 = "5511999990000@g.us"
CHAT_2 = "5511999990001@g.us"


def _svc(*, grupos=None, transmissoes=None, destinos=None):
    mock = MockSupabaseClient()
    mock.set_table_data("grupos", grupos or [])
    mock.set_table_data("transmissoes", transmissoes or [])
    mock.set_table_data("transmissao_destinos", destinos or [])
    svc = TransmissoesService(mock, org_id=ORG)
    return svc, mock


def _grupo_row(id_, chat_id):
    return {"id": id_, "org_id": str(ORG), "chat_id": chat_id, "nome": "G", "ativo": True}


class TestCreate:
    def test_create_201_with_destinos(self):
        svc, _ = _svc(grupos=[_grupo_row(GRUPO_1, CHAT_1)])
        row = asyncio.run(svc.create(
            payload={
                "titulo": "Aviso", "corpo": "Olá pessoal", "tipo": "anuncio",
                "grupo_ids": [GRUPO_1], "agendada_para": None,
            },
            criada_por=None,
        ))
        assert row["estado"] == "rascunho"
        assert len(row["destinos"]) == 1

    def test_unknown_grupo_422(self):
        svc, _ = _svc(grupos=[])
        try:
            asyncio.run(svc.create(
                payload={
                    "titulo": "Aviso", "corpo": "Olá", "tipo": "anuncio",
                    "grupo_ids": ["unknown"], "agendada_para": None,
                },
                criada_por=None,
            ))
            assert False, "expected error"
        except TransmissoesServiceError as exc:
            assert exc.status_code == 422
            assert exc.detail == "Grupo inválido na lista de destinos."

    def test_agendada_para_sets_estado_agendada(self):
        svc, _ = _svc(grupos=[_grupo_row(GRUPO_1, CHAT_1)])
        row = asyncio.run(svc.create(
            payload={
                "titulo": "Lembrete", "corpo": "...", "tipo": "lembrete_evento",
                "grupo_ids": [GRUPO_1], "agendada_para": "2026-10-01T10:00:00+00:00",
            },
            criada_por=None,
        ))
        assert row["estado"] == "agendada"


class TestUpdate:
    def test_update_rascunho_200(self):
        svc, _ = _svc(
            grupos=[_grupo_row(GRUPO_1, CHAT_1)],
            transmissoes=[{
                "id": "t1", "org_id": str(ORG), "titulo": "X", "corpo": "Y",
                "tipo": "anuncio", "estado": "rascunho",
            }],
        )
        row = asyncio.run(svc.update(transmissao_id="t1", payload={"titulo": "Novo"}))
        assert row["titulo"] == "Novo"

    def test_update_enviada_409(self):
        svc, _ = _svc(transmissoes=[{
            "id": "t1", "org_id": str(ORG), "titulo": "X", "corpo": "Y",
            "tipo": "anuncio", "estado": "enviada",
        }])
        try:
            asyncio.run(svc.update(transmissao_id="t1", payload={"titulo": "Novo"}))
            assert False, "expected error"
        except TransmissoesServiceError as exc:
            assert exc.status_code == 409
            assert exc.detail == "Só é possível editar uma transmissão em rascunho."


class TestDelete:
    def test_delete_rascunho_204(self):
        svc, _ = _svc(transmissoes=[{
            "id": "t1", "org_id": str(ORG), "titulo": "X", "corpo": "Y",
            "tipo": "anuncio", "estado": "rascunho",
        }])
        ok = asyncio.run(svc.delete(transmissao_id="t1"))
        assert ok is True

    def test_delete_enviada_409(self):
        svc, _ = _svc(transmissoes=[{
            "id": "t1", "org_id": str(ORG), "titulo": "X", "corpo": "Y",
            "tipo": "anuncio", "estado": "enviada",
        }])
        try:
            asyncio.run(svc.delete(transmissao_id="t1"))
            assert False, "expected error"
        except TransmissoesServiceError as exc:
            assert exc.status_code == 409


class TestEnviar:
    def test_all_destinos_succeed_estado_enviada(self):
        svc, mock = _svc(
            grupos=[_grupo_row(GRUPO_1, CHAT_1), _grupo_row(GRUPO_2, CHAT_2)],
            transmissoes=[{
                "id": "t1", "org_id": str(ORG), "titulo": "X", "corpo": "Olá",
                "tipo": "anuncio", "estado": "rascunho",
            }],
            destinos=[
                {"id": "d1", "org_id": str(ORG), "transmissao_id": "t1", "grupo_id": GRUPO_1, "estado": "pendente"},
                {"id": "d2", "org_id": str(ORG), "transmissao_id": "t1", "grupo_id": GRUPO_2, "estado": "pendente"},
            ],
        )
        waha = FakeWahaClient()
        jobs_repo = make_job_repository(use_fake=True)
        result = asyncio.run(svc.enviar(transmissao_id="t1", waha_client=waha, jobs_repo=jobs_repo))
        assert result["destinos"] == 2

        transmissao = mock.table("transmissoes").select("*").eq("id", "t1").execute().data[0]
        assert transmissao["estado"] == "enviada"
        assert transmissao["enviada_em"] is not None
        assert len(waha.sent_messages) == 2

        destinos_finais = mock.table("transmissao_destinos").select("*").eq("transmissao_id", "t1").execute().data
        assert all(d["estado"] == "enviado" for d in destinos_finais)

    def test_all_destinos_fail_estado_falhou_with_erro(self):
        svc, mock = _svc(
            grupos=[_grupo_row(GRUPO_1, CHAT_1)],
            transmissoes=[{
                "id": "t1", "org_id": str(ORG), "titulo": "X", "corpo": "Olá",
                "tipo": "anuncio", "estado": "rascunho",
            }],
            destinos=[
                {"id": "d1", "org_id": str(ORG), "transmissao_id": "t1", "grupo_id": GRUPO_1, "estado": "pendente"},
            ],
        )

        class _BrokenWaha(FakeWahaClient):
            async def send_text(self, chat_id, text):
                raise RuntimeError("waha indisponível")

        waha = _BrokenWaha()
        jobs_repo = make_job_repository(use_fake=True)
        result = asyncio.run(svc.enviar(transmissao_id="t1", waha_client=waha, jobs_repo=jobs_repo))
        assert result["destinos"] == 1

        transmissao = mock.table("transmissoes").select("*").eq("id", "t1").execute().data[0]
        assert transmissao["estado"] == "falhou"

        destino = mock.table("transmissao_destinos").select("*").eq("id", "d1").execute().data[0]
        assert destino["estado"] == "falhou"
        assert destino["erro"] == "waha indisponível"

    def test_dedupe_key_prevents_double_send_same_destino(self):
        svc, mock = _svc(
            grupos=[_grupo_row(GRUPO_1, CHAT_1)],
            transmissoes=[{
                "id": "t1", "org_id": str(ORG), "titulo": "X", "corpo": "Olá",
                "tipo": "anuncio", "estado": "rascunho",
            }],
            destinos=[
                {"id": "d1", "org_id": str(ORG), "transmissao_id": "t1", "grupo_id": GRUPO_1, "estado": "pendente"},
            ],
        )
        waha = FakeWahaClient()
        jobs_repo = make_job_repository(use_fake=True)
        asyncio.run(svc.enviar(transmissao_id="t1", waha_client=waha, jobs_repo=jobs_repo))
        asyncio.run(svc.enviar(transmissao_id="t1", waha_client=waha, jobs_repo=jobs_repo))
        # The SAME jobs_repo (shared dedupe_key) means the second enviar's
        # enqueue is a no-op for this destino — only one message sent.
        assert len(waha.sent_messages) == 1

    def test_missing_transmissao_404(self):
        svc, _ = _svc()
        try:
            asyncio.run(svc.enviar(
                transmissao_id="unknown", waha_client=FakeWahaClient(),
                jobs_repo=make_job_repository(use_fake=True),
            ))
            assert False, "expected error"
        except TransmissoesServiceError as exc:
            assert exc.status_code == 404
