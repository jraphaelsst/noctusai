"""skill-scout notices: a declared core kind, WhatsApp ONLY (never e-mail / bell), sent through the owner line."""
from __future__ import annotations

from app import notification_kinds as kinds
from app.services import skill_scout_notice_service as svc
from noctusai_lib.domain.notification_catalog import (
    FakeNotificationGate,
    FakeOwnerLineTransport,
    FakeOwnerRecipientSource,
    OwnerRecipient,
    declared_kinds,
)


def test_kind_is_declared_for_core_and_whatsapp_only():
    (k,) = [k for k in declared_kinds("core") if k.kind == kinds.KIND_SKILL_SCOUT_NOVO_SKILL]
    assert k.canais == ("whatsapp",)


def test_notice_goes_out_on_the_owner_line_with_name_summary_and_link():
    transport = FakeOwnerLineTransport()
    out = svc.avisar_novo_skill(
        nome="pdf-forms", resumo="Preenche formulários PDF.", fonte_url="https://example.com/pdf-forms",
        gate=FakeNotificationGate("core"),
        recipients=FakeOwnerRecipientSource([OwnerRecipient("+5511900000000")]), transport=transport,
    )
    assert (out.status, out.delivered) == ("sent", 1)
    (_, texto), = transport.sent
    assert "pdf-forms" in texto and "Preenche formulários PDF." in texto and "https://example.com/pdf-forms" in texto


def test_switched_off_is_suppressed_and_sends_nothing():
    gate = FakeNotificationGate("core")
    gate.disabled.add(kinds.KIND_SKILL_SCOUT_NOVO_SKILL)
    transport = FakeOwnerLineTransport()
    out = svc.avisar_novo_skill(
        nome="x", resumo="y", fonte_url=None, gate=gate,
        recipients=FakeOwnerRecipientSource([OwnerRecipient("+5511900000000")]), transport=transport,
    )
    assert out.status == "suppressed" and transport.sent == []
