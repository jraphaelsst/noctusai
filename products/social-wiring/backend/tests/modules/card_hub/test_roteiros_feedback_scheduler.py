"""The daily "Visita de {cliente} aconteceu?" digest."""
from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import roteiros_feedback_scheduler as sched
from app.modules.card_hub import roteiros_service as svc
from app.services.notification_service import NotificationService
from tests.modules.card_hub.test_roteiros_feedback import ORG, db  # noqa: F401


class _Notifier:
    def __init__(self):
        self.calls = []

    async def notify_visita_feedback(self, *, org_id, pendentes):
        self.calls.append((org_id, pendentes))


@pytest.mark.asyncio
async def test_one_digest_per_org_with_due_roteiros(db):  # noqa: F811
    mock, cid, _ = db
    svc.criar(mock, ORG, cid, imoveis=["ONE9001"], data_visita=date(2020, 1, 1))
    notifier = _Notifier()
    resumo = await sched.avisar_todas_orgs(mock, notifier)
    assert resumo == {"orgs": 1, "roteiros": 1, "falhas": 0}
    assert notifier.calls[0][0] == ORG
    assert notifier.calls[0][1][0]["cliente_nome"] == "Ana"


@pytest.mark.asyncio
async def test_no_due_roteiro_sends_nothing(db):  # noqa: F811
    mock, cid, _ = db
    svc.criar(mock, ORG, cid, imoveis=["ONE9001"], data_visita=date(2999, 1, 1))
    notifier = _Notifier()
    assert (await sched.avisar_todas_orgs(mock, notifier))["orgs"] == 0
    assert notifier.calls == []


def test_message_names_the_cliente_and_links_the_card():
    msg = NotificationService._build_visita_feedback_message(
        object.__new__(NotificationService),
        [{"cliente_nome": "Ana", "cliente_id": "c1"}],
    )
    assert "Visita de Ana aconteceu?" in msg["text"]
