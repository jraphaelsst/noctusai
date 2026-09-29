"""Tests for ``noctus.dev.notify`` — hermetic: every transport is injected
through the tool's DI seams (no network, no monkey-patching)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "seed" / "lib" / "backend"))

from tools.noctus.dev.migrate_product import FakeSqlExecutor  # noqa: E402
from tools.noctus.dev.notify import _RECIPIENTS_SQL, notify  # noqa: E402

ROW = {"name": "Owner", "email": "owner@example.com", "whatsapp_number": "+55 (11) 99999-0000"}


def _db(rows=None):
    return FakeSqlExecutor(preset_rows={_RECIPIENTS_SQL: [ROW] if rows is None else rows})


class FakeGmail:
    def __init__(self, exc=None):
        self.calls, self.exc = [], exc

    async def send_message(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        return SimpleNamespace(message_id="gm-1")


class FakeWaha:
    def __init__(self, status="WORKING"):
        self.status, self.sent = status, []

    async def get_session(self):
        return {"status": self.status}

    async def send_text(self, chat_id, text):
        self.sent.append((chat_id, text))
        return {"id": "wa-1"}


class TestPlanned:
    def test_no_confirm_sends_nothing(self):
        gm, wa = FakeGmail(), FakeWaha()
        r = notify("hello\nbody", executor=_db(), env={}, gmail_client=gm, waha_client=wa)
        assert r["status"] == "planned" and r["ok"] is False
        assert r["subject"] == "hello"
        assert r["channels"]["email"]["status"] == "planned"
        assert "owner@example.com" in r["channels"]["email"]["detail"]
        assert r["channels"]["whatsapp"]["status"] == "planned"
        assert gm.calls == [] and wa.sent == []


class TestSend:
    def test_email_and_whatsapp_sent(self):
        gm, wa = FakeGmail(), FakeWaha()
        r = notify("hi", subject="S", confirm=True, executor=_db(), env={}, gmail_client=gm, waha_client=wa)
        assert r["ok"] is True
        assert r["channels"]["email"] == {"status": "sent", "detail": "sent via gmail", "id": "gm-1"}
        assert gm.calls[0]["to"] == "owner@example.com" and gm.calls[0]["subject"] == "S"
        assert wa.sent == [("5511999990000@c.us", "hi")]

    def test_overrides_skip_recipient_lookup(self):
        db = _db()
        r = notify("x", channels=["email"], to_email="o@x.io", confirm=True, executor=db, env={}, gmail_client=FakeGmail())
        assert r["ok"] is True and db.executed == []

    def test_gmail_failure_surfaced_verbatim(self):
        gm = FakeGmail(exc=RuntimeError("403 insufficient scope"))
        r = notify("x", channels=["email"], confirm=True, executor=_db(), env={}, gmail_client=gm)
        assert r["ok"] is False
        assert r["channels"]["email"]["status"] == "failed"
        assert "403 insufficient scope" in r["channels"]["email"]["detail"]

    def test_whatsapp_unavailable_still_sends_email(self):
        gm, wa = FakeGmail(), FakeWaha(status="FAILED")
        r = notify("x", confirm=True, executor=_db(), env={}, gmail_client=gm, waha_client=wa)
        assert r["channels"]["whatsapp"]["status"] == "unavailable"
        assert "FAILED" in r["channels"]["whatsapp"]["detail"]
        assert r["channels"]["email"]["status"] == "sent"
        assert r["ok"] is False and wa.sent == []


class TestEmailTransportSelection:
    def test_no_credentials_unavailable_names_missing(self):
        r = notify("x", channels=["email"], confirm=True, executor=_db(), env={"GOOGLE_OAUTH_CLIENT_ID": "a"})
        ch = r["channels"]["email"]
        assert ch["status"] == "unavailable"
        assert "GOOGLE_OAUTH_REFRESH_TOKEN" in ch["detail"] and "SMTP_HOST" in ch["detail"]

    def test_plan_reports_transport_gmail_when_trio_present(self):
        env = {"GOOGLE_OAUTH_CLIENT_ID": "a", "GOOGLE_OAUTH_CLIENT_SECRET": "b", "GOOGLE_OAUTH_REFRESH_TOKEN": "c"}
        r = notify("x", channels=["email"], executor=_db(), env=env)
        assert "transport=gmail" in r["channels"]["email"]["detail"]

    def test_plan_reports_smtp_when_only_smtp(self):
        env = {"SMTP_HOST": "h", "SMTP_PORT": "587", "SMTP_USER": "u", "SMTP_PASSWORD": "p"}
        r = notify("x", channels=["email"], executor=_db(), env=env)
        assert "transport=smtp" in r["channels"]["email"]["detail"]

    def test_whatsapp_missing_base_url_unavailable(self):
        r = notify("x", channels=["whatsapp"], confirm=True, executor=_db(), env={})
        assert r["channels"]["whatsapp"]["status"] == "unavailable"
        assert "WAHA_BASE_URL" in r["channels"]["whatsapp"]["detail"]


class TestRecipientResolution:
    def test_no_active_row_is_typed_error(self):
        r = notify("x", executor=_db(rows=[]), env={})
        assert r["ok"] is False and r["status"] == "error"
        assert r["error"]["type"] == "recipient_resolution_failed"

    def test_multiple_rows_is_typed_error(self):
        r = notify("x", executor=_db(rows=[ROW, ROW]), env={})
        assert r["error"]["type"] == "recipient_resolution_failed"

    def test_query_failure_is_typed_error(self):
        fake = FakeSqlExecutor(fail_on={"notification_recipients"})
        r = notify("x", executor=fake, env={})
        assert r["error"]["type"] == "recipient_resolution_failed"

    def test_unknown_channel_rejected(self):
        assert notify("x", channels=["sms"], env={})["error"]["type"] == "invalid_input"
