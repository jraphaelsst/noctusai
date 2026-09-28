"""Tests for `PortalGrupoterapiaService` — contract §Grupoterapia, member
side. Exercises the SECURITY invariant directly: `nenhum` never gets a
`link_sala`, `ouvir` gets one but is refused a speaking seat, `falar`
reserves (or gets `lotada`/`indisponivel` per the RPC result).
"""
import asyncio

from noctusai_lib.testing import MockSupabaseClient

from app.services.portal_grupoterapia_service import (
    PortalGrupoterapiaError,
    PortalGrupoterapiaService,
)

ORG_ID = "11111111-1111-1111-1111-111111111111"
SESSAO_1 = "22222222-2222-2222-2222-222222222222"
MEMBRO_1 = "44444444-4444-4444-4444-444444444444"
PLANO_OUVINTE = "77777777-7777-7777-7777-777777777777"
PLANO_PREMIUM = "88888888-8888-8888-8888-888888888888"

_NOW = "2026-10-01T00:00:00+00:00"
_FUTURE = "2026-10-05T19:00:00+00:00"
_PAST = "2026-01-01T19:00:00+00:00"


def _sessao_row(**over) -> dict:
    base = {
        "id": SESSAO_1,
        "org_id": ORG_ID,
        "titulo": "Roda de acolhimento",
        "descricao": None,
        "inicio": _FUTURE,
        "duracao_minutos": 90,
        "link_sala": "https://meet.example/roda",
        "vagas_fala": 8,
        "status": "agendada",
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    base.update(over)
    return base


def _plano_row(plano_id, nivel) -> dict:
    return {
        "id": plano_id, "org_id": ORG_ID, "nome": "Plano",
        "preco_centavos": 700, "ciclo": "mensal", "ativo": True, "ordem": 1,
        "entitlements": {"grupoterapia": nivel},
        "created_at": _NOW, "updated_at": _NOW,
    }


def _membro_row(*, plano_id=None, status="ativo") -> dict:
    return {
        "id": MEMBRO_1, "org_id": ORG_ID, "nome": "Ana", "email": "ana@x.com",
        "status": status, "plano_id": plano_id,
    }


def _svc(mock, *, plano_id=None, status="ativo") -> PortalGrupoterapiaService:
    return PortalGrupoterapiaService(
        user_client=mock, admin_client=mock, org_id=ORG_ID,
        membro=_membro_row(plano_id=plano_id, status=status),
    )


class TestListarNivelNenhum:
    def test_no_plano_never_exposes_link_sala(self):
        mock = MockSupabaseClient()
        mock.set_table_data("grupoterapia_sessoes", [_sessao_row()])
        result = asyncio.run(_svc(mock, plano_id=None).listar())
        assert result["nivel"] == "nenhum"
        assert len(result["items"]) == 1
        for item in result["items"]:
            assert item["link_sala"] is None
            assert item["acesso"] == "bloqueado"

    def test_expired_status_never_exposes_link_sala(self):
        mock = MockSupabaseClient()
        mock.set_table_data("planos", [_plano_row(PLANO_PREMIUM, "falar")])
        mock.set_table_data("grupoterapia_sessoes", [_sessao_row()])
        result = asyncio.run(
            _svc(mock, plano_id=PLANO_PREMIUM, status="pausado").listar()
        )
        assert result["nivel"] == "nenhum"
        for item in result["items"]:
            assert item["link_sala"] is None


class TestListarNivelOuvir:
    def test_ouvir_gets_link_sala_but_capped_acesso(self):
        mock = MockSupabaseClient()
        mock.set_table_data("planos", [_plano_row(PLANO_OUVINTE, "ouvir")])
        mock.set_table_data("grupoterapia_sessoes", [_sessao_row()])
        result = asyncio.run(_svc(mock, plano_id=PLANO_OUVINTE).listar())
        assert result["nivel"] == "ouvir"
        item = result["items"][0]
        assert item["acesso"] == "ouvir"
        assert item["link_sala"] == "https://meet.example/roda"


class TestListarWindow:
    def test_past_sessions_excluded(self):
        mock = MockSupabaseClient()
        mock.set_table_data("planos", [_plano_row(PLANO_PREMIUM, "falar")])
        mock.set_table_data("grupoterapia_sessoes", [
            _sessao_row(id="past", inicio=_PAST),
            _sessao_row(id="future", inicio=_FUTURE),
        ])
        result = asyncio.run(_svc(mock, plano_id=PLANO_PREMIUM).listar())
        ids = {i["id"] for i in result["items"]}
        assert ids == {"future"}

    def test_vagas_restantes_and_minha_reserva(self):
        mock = MockSupabaseClient()
        mock.set_table_data("planos", [_plano_row(PLANO_PREMIUM, "falar")])
        mock.set_table_data("grupoterapia_sessoes", [_sessao_row(vagas_fala=2)])
        mock.set_table_data("grupoterapia_reservas", [
            {"id": "r1", "org_id": ORG_ID, "sessao_id": SESSAO_1,
             "membro_id": MEMBRO_1, "status": "confirmada"},
            {"id": "r2", "org_id": ORG_ID, "sessao_id": SESSAO_1,
             "membro_id": "other-membro", "status": "confirmada"},
        ])
        result = asyncio.run(_svc(mock, plano_id=PLANO_PREMIUM).listar())
        item = result["items"][0]
        assert item["vagas_restantes"] == 0
        assert item["minha_reserva"] is True


class TestReservarNivelOuvir:
    def test_ouvir_cannot_reserve_403(self):
        mock = MockSupabaseClient()
        mock.set_table_data("planos", [_plano_row(PLANO_OUVINTE, "ouvir")])
        try:
            asyncio.run(
                _svc(mock, plano_id=PLANO_OUVINTE).reservar(
                    sessao_id=SESSAO_1, autor_id=None,
                )
            )
            raise AssertionError("expected PortalGrupoterapiaError")
        except PortalGrupoterapiaError as exc:
            assert exc.status_code == 403
            assert exc.detail == "Seu plano não inclui a vez de fala."


class TestReservarNivelFalar:
    def test_confirmada_writes_evento(self):
        mock = MockSupabaseClient()
        mock.set_table_data("planos", [_plano_row(PLANO_PREMIUM, "falar")])
        mock.set_rpc_data("reservar_vaga_fala", "confirmada")
        outcome = asyncio.run(
            _svc(mock, plano_id=PLANO_PREMIUM).reservar(
                sessao_id=SESSAO_1, autor_id=None,
            )
        )
        assert outcome == "confirmada"
        eventos = mock.table("membro_eventos").select("*").execute().data
        assert len(eventos) == 1
        assert eventos[0]["tipo"] == "grupoterapia"
        assert eventos[0]["membro_id"] == MEMBRO_1

    def test_lotada_409(self):
        mock = MockSupabaseClient()
        mock.set_table_data("planos", [_plano_row(PLANO_PREMIUM, "falar")])
        mock.set_rpc_data("reservar_vaga_fala", "lotada")
        try:
            asyncio.run(
                _svc(mock, plano_id=PLANO_PREMIUM).reservar(
                    sessao_id=SESSAO_1, autor_id=None,
                )
            )
            raise AssertionError("expected PortalGrupoterapiaError")
        except PortalGrupoterapiaError as exc:
            assert exc.status_code == 409
            assert exc.detail == "Não há mais vagas de fala nesta sessão."
        eventos = mock.table("membro_eventos").select("*").execute().data
        assert eventos == []

    def test_indisponivel_409(self):
        mock = MockSupabaseClient()
        mock.set_table_data("planos", [_plano_row(PLANO_PREMIUM, "falar")])
        mock.set_rpc_data("reservar_vaga_fala", "indisponivel")
        try:
            asyncio.run(
                _svc(mock, plano_id=PLANO_PREMIUM).reservar(
                    sessao_id=SESSAO_1, autor_id=None,
                )
            )
            raise AssertionError("expected PortalGrupoterapiaError")
        except PortalGrupoterapiaError as exc:
            assert exc.status_code == 409
            assert exc.detail == "Sessão indisponível para reservas."


class TestCancelar:
    def test_cancels_own_confirmed_reserva(self):
        mock = MockSupabaseClient()
        mock.set_table_data("planos", [_plano_row(PLANO_PREMIUM, "falar")])
        mock.set_table_data("grupoterapia_reservas", [
            {"id": "r1", "org_id": ORG_ID, "sessao_id": SESSAO_1,
             "membro_id": MEMBRO_1, "status": "confirmada"},
        ])
        asyncio.run(
            _svc(mock, plano_id=PLANO_PREMIUM).cancelar(
                sessao_id=SESSAO_1, autor_id=None,
            )
        )
        row = mock.table("grupoterapia_reservas").select("*").execute().data[0]
        assert row["status"] == "cancelada"
        eventos = mock.table("membro_eventos").select("*").execute().data
        assert len(eventos) == 1

    def test_cancel_with_no_reservation_is_a_no_op(self):
        mock = MockSupabaseClient()
        mock.set_table_data("planos", [_plano_row(PLANO_PREMIUM, "falar")])
        mock.set_table_data("grupoterapia_reservas", [])
        asyncio.run(
            _svc(mock, plano_id=PLANO_PREMIUM).cancelar(
                sessao_id=SESSAO_1, autor_id=None,
            )
        )
        eventos = mock.table("membro_eventos").select("*").execute().data
        assert eventos == []
