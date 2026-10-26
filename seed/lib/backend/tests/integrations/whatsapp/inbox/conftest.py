"""Shared fixtures: every store contract test runs against BOTH the Fake and
the Supabase-backed Real store (over the seed ``MockSupabaseClient``)."""
from __future__ import annotations

import uuid

import pytest

from noctusai_lib.integrations.whatsapp.connection_store import WhatsAppConnectionRecord
from noctusai_lib.integrations.whatsapp.inbox import build_whatsapp_chat_store
from noctusai_lib.testing.mocks import MockSupabaseClient

ORG = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_ORG = uuid.UUID("22222222-2222-2222-2222-222222222222")
CONN = uuid.UUID("33333333-3333-3333-3333-333333333333")


@pytest.fixture(params=["fake", "supabase"])
def store(request):
    if request.param == "fake":
        return build_whatsapp_chat_store(None, schema="monica", allow_fake=True)
    return build_whatsapp_chat_store(MockSupabaseClient(validate_schema=False), schema="monica")


@pytest.fixture
def record() -> WhatsAppConnectionRecord:
    return WhatsAppConnectionRecord(
        id=CONN, org_id=ORG, user_id=uuid.uuid4(), label="Mônica", base_url="http://waha:3000",
        session_name="default", webhook_url=None, created_at=None, updated_at=None,
        api_key="k", webhook_token="tok",
    )


def waha_message(
    *, mid: str, chat: str = "5511999990001@c.us", body: str = "oi", from_me: bool = False,
    ts: int = 1_790_000_000, event: str = "message", extra: dict | None = None,
) -> dict:
    """A WAHA webhook envelope for one message."""
    payload = {
        "id": mid,
        "timestamp": ts,
        "from": chat if not from_me else "5511000000000@c.us",
        "to": "5511000000000@c.us" if not from_me else chat,
        "fromMe": from_me,
        "body": body,
        "hasMedia": False,
        "_data": {"notifyName": "Paciente"},
    }
    payload.update(extra or {})
    return {"event": event, "session": "default", "payload": payload}
