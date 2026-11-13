import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.live import registro as r
from app.live.numeros import canonico, eh_conversa_individual, numero_do_chat, numero_permitido
from app.live.wiring import LiveReplyConfigError, assert_live_reply_config, build_on_message, drain

POLICY_ON = '{"send":"enabled","mark_online":true,"full_sync":true,"auto_repair":true}'
POLICY_OFF = '{"send":"disabled","mark_online":false,"full_sync":false,"auto_repair":false,"webhook_relay":"http://w:3001"}'


def test_chat_kinds():
    assert eh_conversa_individual("5511988887777@c.us") and eh_conversa_individual("123@lid")
    for c in ("120363@g.us", "status@broadcast", "x@newsletter", "", "5511@broadcast"):
        assert not eh_conversa_individual(c)


def test_allow_list_rules():
    assert numero_permitido("5511988887777", [])  # empty = everyone
    assert numero_permitido("5511988887777", ["+55 (11) 98888-7777"])
    assert numero_permitido("551188887777", ["5511988887777"])  # BR 9th digit variant is the same line
    assert not numero_permitido("5511988887777", ["5521999990000"])
    assert not numero_permitido(None, ["5521999990000"])  # unknown (@lid) is never in a non-empty list
    assert numero_permitido(None, [])
    assert canonico("5511988887777") == "5511988887777" and numero_do_chat("1@lid") is None


def _s(**kw):
    base = dict(assistant_reply_enabled=True, assistant_waha_base_url="http://w", assistant_waha_line_policy=POLICY_ON,
                assistant_identity_hmac_key="k", encryption_key="e")
    base.update(kw)
    return SimpleNamespace(**base)


def test_boot_check():
    assert_live_reply_config(_s(assistant_reply_enabled=False, assistant_waha_base_url=""))  # off: nothing required
    assert_live_reply_config(_s())
    for missing in ("assistant_waha_base_url", "assistant_waha_line_policy", "assistant_identity_hmac_key", "encryption_key"):
        with pytest.raises(LiveReplyConfigError):
            assert_live_reply_config(_s(**{missing: ""}))
    with pytest.raises(LiveReplyConfigError):
        assert_live_reply_config(_s(assistant_waha_line_policy=POLICY_OFF))


def test_default_is_off_and_on_message_only_schedules(monkeypatch):
    from app.config import settings

    assert settings.assistant_reply_enabled is False  # starts OFF
    seen = []

    class Fake:
        async def responder(self, org, conn, message):
            await asyncio.sleep(0)
            seen.append(message.id)

    msg = SimpleNamespace(id="m1", from_me=False)

    async def go():
        on = build_on_message(lambda: Fake())
        await on(1, 2, None, msg)
        assert seen == []  # scheduled, not awaited inside the webhook
        await drain()

    monkeypatch.setattr(settings, "assistant_reply_enabled", False)
    asyncio.run(go())
    assert seen == []  # switch off => never scheduled
    monkeypatch.setattr(settings, "assistant_reply_enabled", True)
    asyncio.run(go())
    assert seen == ["m1"]


def test_migration_021_matches_the_outcome_enum_and_stores_no_phone():
    from noctusai_lib.testing.migrations import migration_sql

    sql = migration_sql(Path(__file__).resolve().parents[2], "respostas_eventos")
    for d in r.DESFECHOS:
        assert f"'{d}'" in sql
    assert "tier:service" in sql and "phone" not in sql.lower().replace("no phone", "").replace("a phone", "")
    assert "REVOKE UPDATE, DELETE" in sql and "UNIQUE (intake_id)" in sql


def test_webhook_ingest_fires_the_seam_only_for_an_admitted_1to1(monkeypatch):
    """ingest -> on_message: a group message is skipped before the seam; a 1:1 reaches it with the raw chat id."""
    from types import SimpleNamespace as NS
    from uuid import uuid4

    from noctusai_lib.integrations.whatsapp.inbox import ingest_waha_event

    from app.config import settings
    from app.routers.whatsapp_router import build_should_store
    from app.services.intake import IntakeChatStore

    class Rpc:
        def rpc(self, name, params):
            return NS(execute=lambda: NS(data=[{"id": str(uuid4()), "outcome": "pending"}]))

    got = []

    async def on_message(org, conn, chat, message):
        got.append((message.chat_id, chat.chat_id))

    def ev(mid, chat):
        return {"event": "message", "payload": {"id": mid, "from": chat, "fromMe": False, "body": "oi", "timestamp": 1_800_000_000,
                                                "source": "app", "hasMedia": False, "_data": {"notifyName": "X"}}}

    store = IntakeChatStore(lambda: Rpc(), lambda: "k")
    rec = NS(org_id=uuid4(), id=uuid4(), app_enabled=True)
    for e in (ev("g1", "120363000000000000@g.us"), ev("m1", "5511988887777@c.us")):
        asyncio.run(ingest_waha_event(e, connection=rec, chat_store=store, should_store=build_should_store(), on_message=on_message))
    assert len(got) == 1 and got[0][0] == "5511988887777@c.us" and got[0][1] != got[0][0]  # the store's chat is the HMAC
