"""Click tracking (P1b(c)): link rewrite in live sends + the public signed redirect."""
from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace
from urllib.parse import urlsplit

from noctusai_lib.security import signed_tokens
from noctusai_lib.testing import MockSupabaseClient

from app.config import settings
from app.modules.email_marketing.services import click_tracking as ct
from app.modules.email_marketing.services import send_service as ss
from app.modules.email_marketing.services.unsubscribe_links import make_token as make_unsub_token

BASE = "https://sw.example"
SECRET = settings.jwt_secret
UNSUB = "https://sw.example/descadastro/tok"


def _token_of(href: str) -> str:
    path = urlsplit(href).path
    assert path.startswith(ct.CLICK_PATH), href
    return path[len(ct.CLICK_PATH):]


def _hrefs(html: str) -> list[str]:
    return re.findall(r"""href\s*=\s*["']([^"']*)["']""", html)


# ── rewrite ──────────────────────────────────────────────────────────────────

class TestRewrite:
    HTML = (
        '<p>Veja https://texto.example/nao-e-link</p>'
        '<a href="https://shop.example/a?x=1&amp;y=2" class="btn">Loja</a>'
        "<a title='href=\"https://evil.example\"' href='http://blog.example/p'>Blog</a>"
        f'<a href="{UNSUB}">Descadastrar</a>'
        '<a href="mailto:oi@example.com">Mail</a>'
        '<a href="tel:+5511999999999">Tel</a>'
        '<a href="#topo">Topo</a>'
    )

    def _rewrite(self, send_log_id="log-1"):
        return ct.rewrite_links(self.HTML, base=BASE, secret=SECRET, send_log_id=send_log_id, keep={UNSUB})

    def test_http_and_https_hrefs_are_rewritten_with_the_original_url_signed(self):
        out = self._rewrite()
        hrefs = _hrefs(out)
        tracked = [h for h in hrefs if h.startswith(BASE + ct.CLICK_PATH)]
        assert len(tracked) == 2
        targets = [ct.verify_token(SECRET, _token_of(h)) for h in tracked]
        assert targets == [
            {"send_log_id": "log-1", "url": "https://shop.example/a?x=1&y=2"},
            {"send_log_id": "log-1", "url": "http://blog.example/p"},
        ]

    def test_unsubscribe_mailto_tel_anchor_and_text_are_untouched(self):
        out = self._rewrite()
        assert f'<a href="{UNSUB}">Descadastrar</a>' in out
        assert '<a href="mailto:oi@example.com">Mail</a>' in out
        assert '<a href="tel:+5511999999999">Tel</a>' in out
        assert '<a href="#topo">Topo</a>' in out
        assert "<p>Veja https://texto.example/nao-e-link</p>" in out
        # other attributes survive, and an href= inside another attribute's value is not a link
        assert 'class="btn"' in out
        assert "title='href=\"https://evil.example\"'" in out

    def test_tokens_are_per_recipient(self):
        a = [h for h in _hrefs(self._rewrite("log-a")) if ct.CLICK_PATH in h]
        b = [h for h in _hrefs(self._rewrite("log-b")) if ct.CLICK_PATH in h]
        assert a[0] != b[0]
        assert ct.verify_token(SECRET, _token_of(b[0]))["send_log_id"] == "log-b"

    def test_non_http_target_never_verifies(self):
        token = signed_tokens.sign(ct.TOKEN_PURPOSE, {"s": "log-1", "u": "javascript:alert(1)"}, SECRET)
        assert ct.verify_token(SECRET, token) is None


# ── live send integration ────────────────────────────────────────────────────

class _Http:
    calls: list = []

    def __init__(self, *_a, **_k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None, timeout=None):
        _Http.calls.append(json)
        return SimpleNamespace(status_code=200, json=lambda: {"data": [{"id": "re_1"}, {"id": "re_2"}]}, text="")


def test_live_send_rewrites_links_per_recipient_and_keeps_unsubscribe():
    db = MockSupabaseClient()
    db.set_table_data("campaigns", [{
        "id": "c1", "org_id": "o1", "status": "enviando", "total_sent": 0,
        "templates": {"assunto": "Oi", "corpo_html": '<p><a href="https://shop.example/">Loja</a></p>'},
    }])
    logs = [
        {"id": "l1", "campaign_id": "c1", "org_id": "o1", "contact_id": "k1", "email": "a@example.com",
         "status": "queued", "contacts": {"nome": "Ana"}},
        {"id": "l2", "campaign_id": "c1", "org_id": "o1", "contact_id": "k2", "email": "b@example.com",
         "status": "queued", "contacts": {"nome": "Bia"}},
    ]
    db.set_table_data("send_logs", logs)
    _Http.calls = []
    svc = ss.SendService(db, settings.model_copy(update={"resend_api_key": "re_key", "frontend_base_url": BASE}),
                         http_client_factory=_Http)
    assert asyncio.run(svc._send_batch("c1", [dict(r) for r in logs])) == 2

    emails = _Http.calls[0]
    targets = []
    for email, log in zip(emails, logs):
        tracked = [h for h in _hrefs(email["html"]) if ct.CLICK_PATH in h]
        assert len(tracked) == 1
        targets.append(ct.verify_token(SECRET, _token_of(tracked[0])))
        unsub = email["headers"]["List-Unsubscribe"].strip("<>")
        assert f'href="{unsub}"' in email["html"]  # the footer link is verbatim
    assert targets == [{"send_log_id": "l1", "url": "https://shop.example/"},
                       {"send_log_id": "l2", "url": "https://shop.example/"}]


# ── public redirect ──────────────────────────────────────────────────────────

def _send_log(status="delivered", clicked_at=None):
    return [{"id": "l1", "org_id": "o1", "contact_id": "k1", "email": "a@example.com",
             "status": status, "clicked_at": clicked_at}]


def _click(client, token, **headers):
    return client.raw().get(f"/api/email-marketing/t/c/{token}", headers=headers, follow_redirects=False)


class TestRedirect:
    def test_valid_token_records_and_redirects_to_the_signed_url(self, client):
        client.mock_supabase.set_table_data("send_logs", _send_log())
        client.mock_supabase.set_table_data("link_clicks", [])
        token = ct.make_token(SECRET, "l1", "https://shop.example/a?x=1")
        resp = _click(client, token, **{"user-agent": "Mozilla/5.0", "cf-connecting-ip": "203.0.113.7"})
        assert resp.status_code == 302
        assert resp.headers["location"] == "https://shop.example/a?x=1"
        clicks = client.mock_supabase.table("link_clicks").inserted_payloads
        assert len(clicks) == 1
        assert clicks[0]["send_log_id"] == "l1"
        assert clicks[0]["url"] == "https://shop.example/a?x=1"
        assert clicks[0]["user_agent"] == "Mozilla/5.0"
        assert clicks[0]["ip_address"] == "203.0.113.7"
        log = client.mock_supabase.table("send_logs").select("*").execute().data[0]
        assert log["status"] == "clicked" and log["clicked_at"]

    def test_repeat_clicks_add_rows_but_never_regress_status(self, client):
        client.mock_supabase.set_table_data("send_logs", _send_log(status="bounced", clicked_at="2026-10-01T00:00:00+00:00"))
        client.mock_supabase.set_table_data("link_clicks", [])
        token = ct.make_token(SECRET, "l1", "https://shop.example/")
        assert _click(client, token).status_code == 302
        assert _click(client, token).status_code == 302
        assert len(client.mock_supabase.table("link_clicks").inserted_payloads) == 2
        log = client.mock_supabase.table("send_logs").select("*").execute().data[0]
        assert log["status"] == "bounced"
        assert log["clicked_at"] == "2026-10-01T00:00:00+00:00"
        assert client.mock_supabase.table("send_logs").updated_payloads == []

    def test_forged_token_is_400_and_records_nothing(self, client):
        client.mock_supabase.set_table_data("send_logs", _send_log())
        client.mock_supabase.set_table_data("link_clicks", [])
        forged = signed_tokens.sign(ct.TOKEN_PURPOSE, {"s": "l1", "u": "https://evil.example/"}, "not-our-secret")
        resp = _click(client, forged)
        assert resp.status_code == 400
        assert "location" not in resp.headers
        assert client.mock_supabase.table("link_clicks").inserted_payloads == []

    def test_unsubscribe_token_is_not_a_click_token(self, client):
        token = make_unsub_token(SECRET, "o1", "k1", "a@example.com")
        assert _click(client, token).status_code == 400

    def test_click_token_is_not_an_unsubscribe_token(self, client):
        token = ct.make_token(SECRET, "l1", "https://shop.example/")
        assert client.raw().get(f"/api/email-marketing/unsubscribe/{token}").status_code == 400
        assert client.raw().post(f"/api/email-marketing/unsubscribe/{token}").status_code == 400

    def test_non_http_target_is_refused(self, client):
        token = signed_tokens.sign(ct.TOKEN_PURPOSE, {"s": "l1", "u": "javascript:alert(1)"}, SECRET)
        resp = _click(client, token)
        assert resp.status_code == 400
        assert "location" not in resp.headers
