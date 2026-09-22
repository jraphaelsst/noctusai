"""Reminders — the lifted `_dispara_em` / `_cancelar_lembretes` /
`_sync_lembrete` mechanics (social-wiring `agendamentos_service`)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from noctusai_lib.domain.card_hub import lembretes
from noctusai_lib.testing.mocks import MockSupabaseClient
from tests.domain.card_hub.conftest import ORG_ID, lead_config


@pytest.fixture
def cfg():
    return lead_config(lambda ids: {})


@pytest.fixture
def db():
    return MockSupabaseClient(validate_schema=False, schema="crm")


class TestDisparaEm:
    def test_subtracts_the_lead_time(self):
        assert lembretes.dispara_em("2026-09-22T15:00:00+00:00", 60) == "2026-09-22T14:00:00+00:00"

    def test_accepts_a_zulu_suffix(self):
        assert lembretes.dispara_em("2026-09-22T15:00:00Z", 0) == "2026-09-22T15:00:00+00:00"

    @pytest.mark.parametrize("quando,minutos", [(None, 10), ("2026-09-22T15:00:00Z", None), ("", 5)])
    def test_no_reminder_without_both(self, quando, minutos):
        assert lembretes.dispara_em(quando, minutos) is None


class TestSync:
    def test_schedules_one_pending_row(self, cfg, db):
        eid, ag = str(uuid4()), str(uuid4())
        lid = lembretes.sync_lembrete(
            cfg, db, ORG_ID, eid, scope={"agendamento_id": ag}, quando="2026-10-01T10:00:00+00:00", minutos=30
        )
        rows = db.table(cfg.tables.lembretes).select("*").execute().data
        assert [(r["id"], r["lead_id"], r["agendamento_id"], r["dispara_em"], r["cancelado_em"]) for r in rows] == [
            (lid, eid, ag, "2026-10-01T09:30:00+00:00", None)
        ]
        assert rows[0]["destinatarios"] == []

    def test_rescheduling_cancels_only_the_same_scope(self, cfg, db):
        """🔴 Scoped to the reminding thing, never to the card: editing one
        appointment must not kill another appointment's reminder."""
        eid, a1, a2 = str(uuid4()), str(uuid4()), str(uuid4())
        first = lembretes.sync_lembrete(cfg, db, ORG_ID, eid, scope={"agendamento_id": a1}, quando="2026-10-01T10:00:00+00:00", minutos=30)
        other = lembretes.sync_lembrete(cfg, db, ORG_ID, eid, scope={"agendamento_id": a2}, quando="2026-10-02T10:00:00+00:00", minutos=30)
        lembretes.sync_lembrete(cfg, db, ORG_ID, eid, scope={"agendamento_id": a1}, quando="2026-10-03T10:00:00+00:00", minutos=30)

        by_id = {r["id"]: r for r in db.table(cfg.tables.lembretes).select("*").execute().data}
        assert by_id[first]["cancelado_em"] is not None
        assert by_id[other]["cancelado_em"] is None
        pending = [r for r in by_id.values() if r["cancelado_em"] is None]
        assert len(pending) == 2

    def test_clearing_the_time_cancels_without_rescheduling(self, cfg, db):
        eid, ag = str(uuid4()), str(uuid4())
        lembretes.sync_lembrete(cfg, db, ORG_ID, eid, scope={"agendamento_id": ag}, quando="2026-10-01T10:00:00+00:00", minutos=30)
        assert lembretes.sync_lembrete(cfg, db, ORG_ID, eid, scope={"agendamento_id": ag}, quando=None, minutos=30) is None
        rows = db.table(cfg.tables.lembretes).select("*").execute().data
        assert len(rows) == 1 and rows[0]["cancelado_em"] is not None

    def test_an_unscoped_cancel_is_refused(self, cfg, db):
        with pytest.raises(ValueError):
            lembretes.cancelar_lembretes(cfg, db, ORG_ID, scope={})
