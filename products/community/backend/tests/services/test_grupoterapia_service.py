"""Tests for `GrupoterapiaService` — contract §Grupoterapia, staff side.

Exercises the service directly (no HTTP) against a data-seeded
`MockSupabaseClient` — no monkeypatching of our own code.
"""
import asyncio

from noctusai_lib.testing import MockSupabaseClient

from app.services.grupoterapia_service import GrupoterapiaService, GrupoterapiaServiceError

ORG_ID = "11111111-1111-1111-1111-111111111111"
SESSAO_1 = "22222222-2222-2222-2222-222222222222"
SESSAO_2 = "33333333-3333-3333-3333-333333333333"
MEMBRO_1 = "44444444-4444-4444-4444-444444444444"
MEMBRO_2 = "55555555-5555-5555-5555-555555555555"


def _sessao_row(**over) -> dict:
    base = {
        "id": SESSAO_1,
        "org_id": ORG_ID,
        "titulo": "Roda de acolhimento",
        "descricao": None,
        "inicio": "2026-10-01T19:00:00+00:00",
        "duracao_minutos": 90,
        "link_sala": "https://meet.example/roda",
        "vagas_fala": 8,
        "status": "agendada",
        "criado_por": None,
        "created_at": "2026-09-01T00:00:00+00:00",
        "updated_at": "2026-09-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _reserva_row(**over) -> dict:
    base = {
        "id": "66666666-6666-6666-6666-666666666666",
        "org_id": ORG_ID,
        "sessao_id": SESSAO_1,
        "membro_id": MEMBRO_1,
        "status": "confirmada",
        "created_at": "2026-09-02T00:00:00+00:00",
        "updated_at": "2026-09-02T00:00:00+00:00",
    }
    base.update(over)
    return base


class TestList:
    def test_list_counts_confirmed_reservas_only(self):
        mock = MockSupabaseClient()
        mock.set_table_data("grupoterapia_sessoes", [_sessao_row()])
        mock.set_table_data("grupoterapia_reservas", [
            _reserva_row(id="r1", status="confirmada"),
            _reserva_row(id="r2", status="confirmada", membro_id=MEMBRO_2),
            _reserva_row(id="r3", status="cancelada", membro_id="not-counted"),
        ])
        service = GrupoterapiaService(mock, org_id=ORG_ID)
        result = asyncio.run(service.list())
        assert result["total"] == 1
        assert result["items"][0]["reservas"] == 2

    def test_list_filters_by_status(self):
        mock = MockSupabaseClient()
        mock.set_table_data("grupoterapia_sessoes", [
            _sessao_row(id=SESSAO_1, status="agendada"),
            _sessao_row(id=SESSAO_2, status="cancelada"),
        ])
        service = GrupoterapiaService(mock, org_id=ORG_ID)
        result = asyncio.run(service.list(status="cancelada"))
        assert result["total"] == 1
        assert result["items"][0]["id"] == SESSAO_2


class TestCreate:
    def test_create_defaults_status_agendada(self):
        mock = MockSupabaseClient()
        service = GrupoterapiaService(mock, org_id=ORG_ID)
        row = asyncio.run(service.create(payload={
            "titulo": "Nova sessão", "inicio": "2026-11-01T19:00:00+00:00",
            "duracao_minutos": 90, "vagas_fala": 8,
        }))
        assert row["status"] == "agendada"
        assert row["titulo"] == "Nova sessão"
        assert row["reservas"] == 0


class TestUpdate:
    def test_update_partial_fields(self):
        mock = MockSupabaseClient()
        mock.set_table_data("grupoterapia_sessoes", [_sessao_row()])
        service = GrupoterapiaService(mock, org_id=ORG_ID)
        row = asyncio.run(service.update(
            sessao_id=SESSAO_1, payload={"vagas_fala": 4}, autor_id=None,
        ))
        assert row["vagas_fala"] == 4

    def test_update_unknown_returns_none(self):
        mock = MockSupabaseClient()
        mock.set_table_data("grupoterapia_sessoes", [])
        service = GrupoterapiaService(mock, org_id=ORG_ID)
        row = asyncio.run(service.update(
            sessao_id="does-not-exist", payload={"vagas_fala": 4}, autor_id=None,
        ))
        assert row is None

    def test_cancel_writes_evento_per_confirmed_reserva(self):
        mock = MockSupabaseClient()
        mock.set_table_data("grupoterapia_sessoes", [_sessao_row()])
        mock.set_table_data("grupoterapia_reservas", [
            _reserva_row(id="r1", membro_id=MEMBRO_1, status="confirmada"),
            _reserva_row(id="r2", membro_id=MEMBRO_2, status="confirmada"),
            _reserva_row(id="r3", membro_id="not-notified", status="cancelada"),
        ])
        service = GrupoterapiaService(mock, org_id=ORG_ID)
        row = asyncio.run(service.update(
            sessao_id=SESSAO_1, payload={"status": "cancelada"}, autor_id=None,
        ))
        assert row["status"] == "cancelada"
        eventos = mock.table("membro_eventos").select("*").execute().data
        assert len(eventos) == 2
        notified = {e["membro_id"] for e in eventos}
        assert notified == {MEMBRO_1, MEMBRO_2}
        assert all(e["tipo"] == "grupoterapia" for e in eventos)

    def test_cancel_is_not_re_fired_on_already_cancelled_session(self):
        mock = MockSupabaseClient()
        mock.set_table_data("grupoterapia_sessoes", [_sessao_row(status="cancelada")])
        mock.set_table_data("grupoterapia_reservas", [
            _reserva_row(id="r1", membro_id=MEMBRO_1, status="confirmada"),
        ])
        service = GrupoterapiaService(mock, org_id=ORG_ID)
        asyncio.run(service.update(
            sessao_id=SESSAO_1, payload={"status": "cancelada", "vagas_fala": 2},
            autor_id=None,
        ))
        eventos = mock.table("membro_eventos").select("*").execute().data
        assert eventos == []


class TestDelete:
    def test_delete_ok_with_no_reservations(self):
        mock = MockSupabaseClient()
        mock.set_table_data("grupoterapia_sessoes", [_sessao_row()])
        mock.set_table_data("grupoterapia_reservas", [])
        service = GrupoterapiaService(mock, org_id=ORG_ID)
        assert asyncio.run(service.delete(sessao_id=SESSAO_1)) is True

    def test_delete_blocked_with_reservations(self):
        mock = MockSupabaseClient()
        mock.set_table_data("grupoterapia_sessoes", [_sessao_row()])
        mock.set_table_data("grupoterapia_reservas", [_reserva_row()])
        service = GrupoterapiaService(mock, org_id=ORG_ID)
        try:
            asyncio.run(service.delete(sessao_id=SESSAO_1))
            raise AssertionError("expected GrupoterapiaServiceError")
        except GrupoterapiaServiceError as exc:
            assert exc.status_code == 409
            assert exc.detail == "Sessão com reservas — cancele em vez de excluir."

    def test_delete_blocked_even_with_only_cancelled_reservations(self):
        mock = MockSupabaseClient()
        mock.set_table_data("grupoterapia_sessoes", [_sessao_row()])
        mock.set_table_data("grupoterapia_reservas", [_reserva_row(status="cancelada")])
        service = GrupoterapiaService(mock, org_id=ORG_ID)
        try:
            asyncio.run(service.delete(sessao_id=SESSAO_1))
            raise AssertionError("expected GrupoterapiaServiceError")
        except GrupoterapiaServiceError as exc:
            assert exc.status_code == 409


class TestReservas:
    def test_get_reservas_denormalizes_membro_nome(self):
        mock = MockSupabaseClient()
        mock.set_table_data("membros", [{"id": MEMBRO_1, "org_id": ORG_ID, "nome": "Ana"}])
        mock.set_table_data("grupoterapia_reservas", [_reserva_row()])
        service = GrupoterapiaService(mock, org_id=ORG_ID)
        result = asyncio.run(service.get_reservas(sessao_id=SESSAO_1))
        assert result["total"] == 1
        assert result["items"][0]["membro_nome"] == "Ana"
