"""Each migrated sender resolves the org's line through julia_linha -- and names the reason when there is none."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from noctusai_lib.integrations.whatsapp import FakeWahaClient

from app.services import media_service
from app.services.julia_linha import LinhaDaOrg, SemLinha
from app.services.notification_service import NotificationService

ORG = uuid4()


def _linha(org, base="https://waha.test", key="chave"):
    return LinhaDaOrg(org_id=org, connection=SimpleNamespace(
        id=uuid4(), base_url=base, api_key=key, session_name="sessao-x", org_id=org))


class _Admin:
    def __init__(self):
        self.inserted: list = []

    def schema(self, _):
        return self

    def table(self, _):
        return self

    def insert(self, payload):
        self.inserted.append(payload)
        return self

    def execute(self):
        return MagicMock(data=[])


def _svc(admin, resolver, **kw):
    return NotificationService(
        admin_supabase=admin, smtp_host="", smtp_port=0, smtp_user="", smtp_password="", line_resolver=resolver, **kw)


# A DECLARED kind (app/services/notification_kinds.py): `_dispatch` refuses an undeclared one (owner-notification catalog).
KIND = "lead"

RECIP = [{"id": str(uuid4()), "name": "A", "email": None, "whatsapp_number": "+5511999990000", "is_active": True}]


def test_notification_sends_with_the_org_lines_credentials():
    seen = {}

    def factory(**kw):
        seen.update(kw)
        return FakeWahaClient()

    svc = _svc(_Admin(), _linha, whatsapp_client_factory=factory)
    out = asyncio.run(svc._dispatch(kind=KIND,org_id=ORG, recipients=RECIP, message={"text": "oi", "subject": "s", "html": "h"}))
    assert out.succeeded == 1
    assert seen == {"base_url": "https://waha.test", "api_key": "chave", "session": "sessao-x"}


def test_notification_without_a_line_logs_a_sem_linha_failure_row_and_does_not_send():
    def sem(org):
        raise SemLinha(org)

    admin = _Admin()
    sent = []
    svc = _svc(admin, sem, whatsapp_client_factory=lambda **kw: sent.append(kw))
    out = asyncio.run(svc._dispatch(kind=KIND,org_id=ORG, recipients=RECIP, message={"text": "oi", "subject": "s", "html": "h"}))
    assert sent == [] and out.failed == 1 and out.succeeded == 0
    rows = [p for p in admin.inserted if p.get("channel") == "whatsapp"]
    assert rows and rows[0]["status"] == "failed" and rows[0]["error_message"] == "sem_linha"


def test_notification_does_not_resolve_a_line_when_nobody_has_a_number():
    called = []
    svc = _svc(_Admin(), lambda org: called.append(org))
    asyncio.run(svc._dispatch(kind=KIND,org_id=ORG, recipients=[{**RECIP[0], "whatsapp_number": None, "email": "a@b.c"}],
                              message={"text": "oi", "subject": "s", "html": "h"}))
    assert called == []


def test_media_service_takes_host_and_key_from_the_org_line(monkeypatch):
    monkeypatch.setattr("app.services.julia_linha.linha_da_org", lambda org, **kw: _linha(org, base="https://m.test/", key="mk"))
    svc = media_service.make_media_service(org_id=ORG)
    assert svc._waha_base_url == "https://m.test" and svc._waha_api_key == "mk"


def test_media_service_without_a_line_has_no_waha_host_and_logs(monkeypatch, caplog):
    def sem(org, **kw):
        raise SemLinha(org)

    monkeypatch.setattr("app.services.julia_linha.linha_da_org", sem)
    with caplog.at_level("WARNING"):
        svc = media_service.make_media_service(org_id=ORG)
    assert svc._waha_base_url == "" and svc._waha_api_key == ""
    assert "sem_linha" in caplog.text


def test_batch_notifier_resolves_the_line_per_org_and_names_a_missing_one(caplog):
    from app.modules.edicao_fotos.services.notifier import MultiChannelBatchReadyNotifier

    def sem(org):
        raise SemLinha(org)

    n = MultiChannelBatchReadyNotifier(core_client=lambda: None, repo=None, preferences=None, line_resolver=sem)
    with pytest.raises(SemLinha):
        n._build_whatsapp_client(str(ORG))
    ok = MultiChannelBatchReadyNotifier(
        core_client=lambda: None, repo=None, preferences=None, line_resolver=_linha, whatsapp_client_factory=lambda **kw: kw)
    assert ok._build_whatsapp_client(str(ORG))["session"] == "sessao-x"


def test_intake_reply_without_a_line_logs_the_reason_and_sends_nothing(caplog):
    from app.services.whatsapp_intake_service import WhatsAppIntakeService

    def sem(org):
        raise SemLinha(org)

    intake = WhatsAppIntakeService.__new__(WhatsAppIntakeService)
    intake._line_resolver = sem
    intake._org_id = ORG
    intake._admin = None
    intake._redis = MagicMock()
    with caplog.at_level("ERROR"):
        asyncio.run(intake._reply("+5511999990000", "oi"))
    assert "sem_linha" in caplog.text
