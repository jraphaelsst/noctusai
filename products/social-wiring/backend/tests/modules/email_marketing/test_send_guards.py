"""SendService's two honesty guards (2026-10-10):

- no RESEND_API_KEY ⇒ a LOUD dry-run: every row recorded `failed` with
  DRY_RUN_REASON, never "sent";
- a live batch is refused unless every rendered email carries that contact's
  own unsubscribe link (LGPD opt-out precondition), by construction.
"""
from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

from app.config import settings
from app.modules.email_marketing.services import send_service as ss


class _Result(SimpleNamespace):
    pass


class _Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.payload, self.op = db, table, [], None, "select"

    def select(self, *_a, **_k):
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def eq(self, col, val):
        self.filters.append((col, val, True))
        return self

    def neq(self, col, val):
        self.filters.append((col, val, False))
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def limit(self, *_a):
        return self

    def order(self, *_a, **_k):
        return self

    def execute(self):
        if self.op == "insert":
            self.db.rows.setdefault(self.table, []).append(dict(self.payload))
            return _Result(data=[dict(self.payload)], count=1)
        rows = [r for r in self.db.rows.get(self.table, [])
                if all((r.get(c) == v) is keep for c, v, keep in self.filters)]
        if self.op == "update":
            for r in rows:
                r.update(self.payload)
        return _Result(data=[dict(r) for r in rows], count=len(rows))


class _FakeDb:
    """Just the PostgREST calls _send_batch makes (select/update/eq/execute)."""

    def __init__(self, template_html: str):
        self.rows = {
            "campaigns": [{"id": "c1", "org_id": "o1", "status": "enviando", "total_sent": 0,
                           "templates": {"assunto": "Oi {{nome}}", "corpo_html": template_html}}],
            "send_logs": [{"id": "l1", "campaign_id": "c1", "org_id": "o1", "contact_id": "k1",
                           "email": "a@example.com", "status": "queued", "contacts": {"nome": "Ana"}}],
        }

    def table(self, name):
        return _Query(self, name)


class _Http:
    calls: list = []

    def __init__(self, *_a, **_k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None, timeout=None):
        _Http.calls.append({"url": url, "json": json})
        return SimpleNamespace(status_code=200, json=lambda: {"data": [{"id": "re_1"}]}, text="")


def _svc(template_html: str, **cfg):
    _Http.calls = []
    db = _FakeDb(template_html)
    svc = ss.SendService(db, settings.model_copy(update=cfg), http_client_factory=_Http)
    return svc, db


def _send(svc, db):
    return asyncio.run(svc._send_batch("c1", [dict(r) for r in db.rows["send_logs"]]))


def test_dry_run_is_loud_and_recorded_as_not_delivered(caplog):
    svc, db = _svc("<p>{{unsubscribe_url}}</p>", resend_api_key="")
    with caplog.at_level(logging.WARNING):
        assert _send(svc, db) == 0
    log = db.rows["send_logs"][0]
    assert log["status"] == "failed" and log["error_message"] == ss.DRY_RUN_REASON
    assert ss.DRY_RUN_REASON in caplog.text
    assert _Http.calls == []
    assert ss.delivery_mode(svc.settings) == {"mode": "dry_run", "reason": ss.DRY_RUN_REASON}


def test_live_send_without_the_link_in_the_template_is_refused():
    svc, db = _svc("<p>Oi {{nome}}</p>", resend_api_key="re_key", frontend_base_url="https://sw.example")
    assert _send(svc, db) == 0
    assert db.rows["send_logs"][0]["error_message"] == ss.UNSUBSCRIBE_REFUSAL
    assert _Http.calls == []


def test_live_send_without_a_frontend_base_url_is_refused():
    svc, db = _svc("<p>{{unsubscribe_url}}</p>", resend_api_key="re_key", frontend_base_url="")
    assert _send(svc, db) == 0
    assert db.rows["send_logs"][0]["error_message"] == ss.UNSUBSCRIBE_REFUSAL
    assert _Http.calls == []


def test_live_send_carries_the_contacts_own_link_and_list_unsubscribe():
    svc, db = _svc('<a href="{{unsubscribe_url}}">sair</a>', resend_api_key="re_key",
                   frontend_base_url="https://sw.example/")
    assert _send(svc, db) == 1
    (call,) = _Http.calls
    (email,) = call["json"]
    link = email["headers"]["List-Unsubscribe"].strip("<>")
    assert link.startswith("https://sw.example/descadastro/") and link in email["html"]
    assert db.rows["send_logs"][0]["status"] == "sent"
