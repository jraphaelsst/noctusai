"""Social Wiring's owner notifications pass the core catalog gate: declared kinds, the owner's switch, the send ledger,
and the Vista-sync warnings the owner asked for on 2026-11-09 ("warn me" = WhatsApp)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from noctusai_lib.domain.notification_catalog import (
    FakeNotificationGate,
    configure_notification_gate,
    declared_kinds,
)

from app.services import imoveis_atualizacao_service as atualizacao
from app.services.notification_kinds import KINDS, PRODUCT
from app.services.notification_service import DispatchOutcome, NotificationService
from tests.services.test_notification_service import _MockSupabase, _service


@pytest.fixture
def gate():
    g = FakeNotificationGate(PRODUCT)
    configure_notification_gate(g)
    yield g
    configure_notification_gate(None)


def test_every_sw_kind_is_declared_for_the_catalog():
    declared = {k.kind for k in declared_kinds(PRODUCT)}
    assert {k.kind for k in KINDS} <= declared
    for k in ("upload", "lead", "conflito", "conflito_imovel", "conflito_empresa", "visita_feedback",
              "imoveis_delistados", "imoveis_sync_falhou", "imoveis_vista_listar_vazio", "vista_divergencias",
              "imoveis_novos_vista", "julia_alerta", "julia_opt_out", "julia_handoff", "julia_conclusao"):
        assert k in declared, k


def _roster(admin: _MockSupabase) -> str:
    rid = str(uuid4())
    admin.set_select(data=[{"id": rid, "name": "Dono", "email": None, "whatsapp_number": "+5511999990000",
                            "is_active": True}])
    return rid


@pytest.mark.asyncio
async def test_switched_off_kind_sends_nothing_and_is_ledgered_as_suppressed(gate):
    gate.disabled.add("imoveis_delistados")
    admin = _MockSupabase()
    _roster(admin)
    wa = MagicMock()
    wa.send_text = AsyncMock()
    svc = _service(admin, whatsapp_client_factory=lambda *a, **k: wa)
    out = await svc.notify_imoveis_delistados(org_id=uuid4(), codigos=["ONE1"], exclusivos=[])
    assert out.attempted == 0
    wa.send_text.assert_not_called()
    assert [s["status"] for s in gate.sends] == ["suppressed"]


@pytest.mark.asyncio
async def test_delisting_warning_reaches_whatsapp_and_names_exclusives(gate):
    admin = _MockSupabase()
    _roster(admin)
    wa = MagicMock()
    wa.send_text = AsyncMock()
    svc = _service(admin, whatsapp_client_factory=lambda *a, **k: wa)
    out = await svc.notify_imoveis_delistados(org_id=uuid4(), codigos=["ONE1", "ONE2"], exclusivos=["ONE2"])
    assert out.succeeded == 1
    texto = wa.send_text.await_args.args[1]
    assert "2 imóveis saíram do Vista" in texto and "ONE2" in texto and "Nada foi apagado" in texto
    assert gate.sends[-1]["status"] == "sent" and gate.sends[-1]["kind"] == "imoveis_delistados"


@pytest.mark.asyncio
async def test_no_recipient_is_ledgered_not_silent(gate):
    admin = _MockSupabase()
    admin.set_select(data=[])
    out = await _service(admin).notify_imoveis_sync_falhou(org_id=uuid4(), status="falhou", motivo="Timeout")
    assert out == DispatchOutcome()
    assert gate.sends[-1]["status"] == "no_recipient"


class _Tabela:
    """`imoveis_sync_execucoes` reads for `_status_anterior` (row 0 = the run just closed)."""

    def __init__(self, statuses):
        self.statuses = statuses

    def schema(self, _):
        return self

    def table(self, _):
        return self

    def select(self, *_):
        return self

    def eq(self, *_):
        return self

    def neq(self, *_):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        return SimpleNamespace(data=[{"status": s} for s in self.statuses])


@pytest.mark.asyncio
async def test_sync_run_warns_on_delisting_and_on_failure_transition_only():
    notificador = MagicMock()
    notificador.notify_imoveis_delistados = AsyncMock()
    notificador.notify_imoveis_sync_falhou = AsyncMock()
    notificador.notify_imoveis_listar_vazio = AsyncMock()
    report = SimpleNamespace(removidos_codigos=["CA1"], removidos_exclusivos=["CA1"])
    org = uuid4()

    await atualizacao._avisar_dono(_Tabela(["incompleto", "ok"]), org, "incompleto", report, {}, notificador)
    notificador.notify_imoveis_delistados.assert_awaited_once()
    notificador.notify_imoveis_sync_falhou.assert_awaited_once()

    notificador.notify_imoveis_sync_falhou.reset_mock()
    await atualizacao._avisar_dono(_Tabela(["incompleto", "incompleto"]), org, "incompleto",
                                   SimpleNamespace(removidos_codigos=[]), {}, notificador)
    notificador.notify_imoveis_sync_falhou.assert_not_awaited()  # same bad status again: no repeat every 2h

    await atualizacao._avisar_dono(_Tabela(["ok", "ok"]), org, "ok", SimpleNamespace(removidos_codigos=[]), {},
                                   notificador, aviso_listar_vazio=True)
    notificador.notify_imoveis_listar_vazio.assert_awaited_once()


@pytest.mark.asyncio
async def test_owner_warning_failure_never_breaks_the_run(caplog):
    notificador = MagicMock()
    notificador.notify_imoveis_delistados = AsyncMock(side_effect=RuntimeError("waha down"))
    with caplog.at_level("ERROR"):
        await atualizacao._avisar_dono(_Tabela(["ok"]), uuid4(), "ok",
                                       SimpleNamespace(removidos_codigos=["X1"]), {}, notificador)
    assert any("owner WhatsApp warning failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_paused_and_new_refs_ride_one_message_per_run():
    notificador = MagicMock()
    notificador.notify_imoveis_delistados = AsyncMock()
    notificador.notify_imoveis_novos_vista = AsyncMock()
    notificador.notify_imoveis_sync_falhou = AsyncMock()
    # "ca1" delisted by the detail pass AND paused; "CA2" paused by the listar sweep only; "CA9" new in Vista.
    report = SimpleNamespace(removidos_codigos=["ca1"], removidos_exclusivos=[], pausados_codigos=["CA1", "CA2"],
                             novos_vista_codigos=["CA9"])
    await atualizacao._avisar_dono(_Tabela(["ok"]), uuid4(), "ok", report, {}, notificador)
    kw = notificador.notify_imoveis_delistados.await_args.kwargs
    assert kw["codigos"] == ["CA1", "CA2"] and kw["pausados"] == ["CA1", "CA2"]
    notificador.notify_imoveis_novos_vista.assert_awaited_once()
    assert notificador.notify_imoveis_novos_vista.await_args.kwargs["codigos"] == ["CA9"]


def test_delisting_message_names_paused_codes_and_the_decision():
    msg = NotificationService._build_delistados_message(["CA1", "CA2"], [], ["CA2"])
    assert "Pausados no site" in msg["text"] and "CA2" in msg["text"] and "restaurar" in msg["text"]
    assert "voltam sozinhos" not in msg["text"]  # a paused ref never comes back on its own


@pytest.mark.asyncio
async def test_new_refs_reach_whatsapp(gate):
    admin = _MockSupabase()
    _roster(admin)
    wa = MagicMock()
    wa.send_text = AsyncMock()
    out = await _service(admin, whatsapp_client_factory=lambda *a, **k: wa).notify_imoveis_novos_vista(
        org_id=uuid4(), codigos=["CA9"])
    assert out.succeeded == 1 and "CA9" in wa.send_text.await_args.args[1]
    assert gate.sends[-1]["kind"] == "imoveis_novos_vista"


def test_julia_report_kinds_map_to_catalog():
    from app.services.julia_relatorio_service import TIPO_ALERTA, TIPO_CONCLUSAO, TIPO_HANDOFF, catalogo_kind

    assert catalogo_kind(TIPO_ALERTA, {"tipo_alerta": "insatisfacao"}) == "julia_alerta"
    assert catalogo_kind(TIPO_ALERTA, {"tipo_alerta": "opt_out"}) == "julia_opt_out"
    assert catalogo_kind(TIPO_HANDOFF, {}) == "julia_handoff"
    assert catalogo_kind(TIPO_CONCLUSAO, {}) == "julia_conclusao"


def test_notification_service_is_still_constructible():
    assert isinstance(_service(_MockSupabase()), NotificationService)
