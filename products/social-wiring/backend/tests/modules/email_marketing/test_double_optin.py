"""Double opt-in (P1b(d)): pending on form/api/flagged import, the signed
confirmation mail, the public confirm endpoints, resend, and the send gate.

The sender is injected through the router's DI seam
(`app.dependency_overrides[get_confirmation_sender]`), settings through
`get_settings` — never a patch of our own code.
"""
from __future__ import annotations

import asyncio
import re
import time

import pytest
from noctusai_lib.integrations.email import FakeEmailSender, ResendEmailSender
from noctusai_lib.security import signed_tokens
from noctusai_lib.testing import MockSupabaseClient

from app.config import settings
from app.dependencies import get_settings
from app.modules.email_marketing.routers.contacts import get_confirmation_sender
from app.modules.email_marketing.services import click_tracking as ct
from app.modules.email_marketing.services import email_optin as eo
from app.modules.email_marketing.services.send_service import SendService
from app.modules.email_marketing.services.unsubscribe_links import make_token as make_unsub_token

ORG = "test-org-123"
BASE = "https://sw.example"
SECRET = settings.jwt_secret
CONTACTS = "/api/email-marketing/contacts"
CONFIRM = "/api/email-marketing/confirm"


def _cfg(**update):
    return settings.model_copy(update={"frontend_base_url": BASE, **update})


@pytest.fixture
def fake(client):
    """A FakeEmailSender behind the sender seam + a settings with a frontend URL."""
    sender = FakeEmailSender()
    app = client.raw().app
    app.dependency_overrides[get_confirmation_sender] = lambda: sender
    app.dependency_overrides[get_settings] = lambda: _cfg()
    yield sender
    app.dependency_overrides.pop(get_confirmation_sender, None)
    app.dependency_overrides.pop(get_settings, None)


def _contacts(client):
    return client.mock_supabase.table("contacts").select("*").execute().data


def _link_token(sent_email) -> str:
    m = re.search(re.escape(BASE + eo.CONFIRM_PATH) + r"([A-Za-z0-9_\-.]+)", sent_email.text)
    assert m, sent_email.text
    assert BASE + eo.CONFIRM_PATH + m.group(1) in sent_email.html
    return m.group(1)


def _contact(optin="pending", email="lead@test.com", org=ORG, cid="k1", status="active"):
    return {"id": cid, "org_id": org, "email": email, "nome": "Lead", "status": status,
            "email_optin": optin, "email_confirmed_at": None}


# ── creation paths ───────────────────────────────────────────────────────────

class TestCreation:
    @pytest.mark.parametrize("source", ["form", "api"])
    def test_form_and_api_start_pending_and_get_a_signed_link(self, client, fake, source):
        client.mock_supabase.set_table_data("contacts", [])
        resp = client.post(CONTACTS, json={"email": "lead@test.com", "nome": "Lead", "source": source})
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["email_optin"] == "pending"
        assert data["confirmation"] == {"sent": True, "reason": None}
        (mail,) = fake.sent
        assert mail.to == ["lead@test.com"] and mail.subject == "Confirme seu e-mail"
        payload = eo.verify_token(SECRET, _link_token(mail))
        assert payload == {"org_id": ORG, "contact_id": data["id"], "email": "lead@test.com"}

    def test_manual_is_not_required_and_sends_nothing(self, client, fake):
        client.mock_supabase.set_table_data("contacts", [])
        resp = client.post(CONTACTS, json={"email": "lead@test.com"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["email_optin"] == "not_required"
        assert "confirmation" not in data
        assert fake.sent == []

    def test_client_cannot_choose_its_own_optin_state(self, client, fake):
        resp = client.post(CONTACTS, json={"email": "x@test.com", "email_optin": "confirmed"})
        assert resp.status_code == 422

    def test_import_flag_makes_new_addresses_pending_and_mails_them(self, client, fake):
        client.mock_supabase.set_table_data("contacts", [_contact(optin="confirmed", email="old@test.com")])
        resp = client.post(f"{CONTACTS}/import", json={
            "double_opt_in": True,
            "contacts": [{"email": "old@test.com"}, {"email": "new@test.com"}],
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["confirmation"] == {"requested": 1, "sent": 1, "failed": 0, "reason": None}
        assert [m.to for m in fake.sent] == [["new@test.com"]]
        by_email = {c["email"]: c for c in _contacts(client)}
        assert by_email["new@test.com"]["email_optin"] == "pending"
        assert by_email["old@test.com"]["email_optin"] == "confirmed"  # never demoted

    def test_import_without_flag_is_not_required(self, client, fake):
        client.mock_supabase.set_table_data("contacts", [])
        resp = client.post(f"{CONTACTS}/import", json={"contacts": [{"email": "n@test.com"}]})
        assert resp.status_code == 200
        assert "confirmation" not in resp.json()["data"]
        assert _contacts(client)[0]["email_optin"] == "not_required"
        assert fake.sent == []


class TestNothingFaked:
    def test_no_resend_key_leaves_pending_and_says_why(self, client):
        """The REAL sender dependency, with no key: no Fake stands in."""
        client.mock_supabase.set_table_data("contacts", [])
        app = client.raw().app
        app.dependency_overrides[get_settings] = lambda: _cfg(resend_api_key="")
        try:
            resp = client.post(CONTACTS, json={"email": "lead@test.com", "source": "form"})
        finally:
            app.dependency_overrides.pop(get_settings, None)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["confirmation"] == {"sent": False, "reason": eo.REASON_NO_SENDER}
        assert _contacts(client)[0]["email_optin"] == "pending"

    def test_no_frontend_url_sends_nothing(self, client, fake):
        client.mock_supabase.set_table_data("contacts", [])
        client.raw().app.dependency_overrides[get_settings] = lambda: _cfg(frontend_base_url="")
        resp = client.post(CONTACTS, json={"email": "lead@test.com", "source": "api"})
        assert resp.json()["data"]["confirmation"] == {"sent": False, "reason": eo.REASON_NO_LINK}
        assert fake.sent == []

    def test_sender_factory_is_real_or_none_never_fake(self):
        assert eo.build_confirmation_sender(_cfg(resend_api_key="")) is None
        assert isinstance(eo.build_confirmation_sender(_cfg(resend_api_key="re_x")), ResendEmailSender)

    def test_empty_secret_builds_no_link(self):
        assert eo.confirm_url(_cfg(jwt_secret=""), ORG, "k1", "a@test.com") is None


# ── public confirm endpoints ────────────────────────────────────────────────

def _token(**over):
    payload = {"org_id": ORG, "contact_id": "k1", "email": "lead@test.com", **over}
    return eo.make_token(SECRET, payload["org_id"], payload["contact_id"], payload["email"])


class TestConfirm:
    def test_get_shows_the_address(self, client):
        resp = client.raw().get(f"{CONFIRM}/{_token()}")
        assert resp.status_code == 200
        assert resp.json() == {"email": "lead@test.com", "valid": True}

    def test_post_confirms_then_is_idempotent(self, client):
        client.mock_supabase.set_table_data("contacts", [_contact()])
        resp = client.raw().post(f"{CONFIRM}/{_token()}")
        assert resp.status_code == 200 and resp.json()["ok"] is True
        assert "already" not in resp.json()
        row = _contacts(client)[0]
        assert row["email_optin"] == "confirmed" and row["email_confirmed_at"]
        again = client.raw().post(f"{CONFIRM}/{_token()}")
        assert again.status_code == 200 and again.json()["already"] is True

    def test_expired_token_is_400(self, client):
        client.mock_supabase.set_table_data("contacts", [_contact()])
        old = signed_tokens.sign(
            eo.TOKEN_PURPOSE, {"org_id": ORG, "contact_id": "k1", "email": "lead@test.com"}, SECRET,
            ttl_seconds=eo.CONFIRM_TTL_SECONDS, now=lambda: time.time() - eo.CONFIRM_TTL_SECONDS - 60,
        )
        assert client.raw().get(f"{CONFIRM}/{old}").status_code == 400
        assert client.raw().post(f"{CONFIRM}/{old}").status_code == 400
        assert _contacts(client)[0]["email_optin"] == "pending"

    def test_forged_token_is_400(self, client):
        client.mock_supabase.set_table_data("contacts", [_contact()])
        forged = eo.make_token("not-our-secret", ORG, "k1", "lead@test.com")
        assert client.raw().post(f"{CONFIRM}/{forged}").status_code == 400
        assert _contacts(client)[0]["email_optin"] == "pending"

    def test_unsubscribe_and_click_tokens_do_not_confirm(self, client):
        client.mock_supabase.set_table_data("contacts", [_contact()])
        for other in (make_unsub_token(SECRET, ORG, "k1", "lead@test.com"),
                      ct.make_token(SECRET, "l1", "https://shop.example/")):
            assert client.raw().get(f"{CONFIRM}/{other}").status_code == 400
            assert client.raw().post(f"{CONFIRM}/{other}").status_code == 400
        assert _contacts(client)[0]["email_optin"] == "pending"

    def test_confirm_token_does_not_unsubscribe(self, client):
        client.mock_supabase.set_table_data("contacts", [_contact()])
        token = _token()
        assert client.raw().get(f"/api/email-marketing/unsubscribe/{token}").status_code == 400
        assert client.raw().post(f"/api/email-marketing/unsubscribe/{token}").status_code == 400
        assert _contacts(client)[0]["status"] == "active"

    def test_changed_address_is_not_confirmed(self, client):
        client.mock_supabase.set_table_data("contacts", [_contact(email="new@test.com")])
        assert client.raw().post(f"{CONFIRM}/{_token()}").status_code == 400
        assert _contacts(client)[0]["email_optin"] == "pending"


# ── resend ───────────────────────────────────────────────────────────────────

class TestResend:
    def test_resends_to_a_pending_contact(self, client, fake):
        client.mock_supabase.set_table_data("contacts", [_contact()])
        resp = client.post(f"{CONTACTS}/k1/resend-confirmation")
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["confirmation"] == {"sent": True, "reason": None}
        (mail,) = fake.sent
        assert eo.verify_token(SECRET, _link_token(mail))["contact_id"] == "k1"

    def test_without_auth_is_strict_401(self, client, fake):
        client.mock_supabase.set_table_data("contacts", [_contact()])
        assert client.raw().post(f"{CONTACTS}/k1/resend-confirmation").status_code == 401
        assert fake.sent == []

    def test_other_org_contact_is_404(self, client, fake):
        client.mock_supabase.set_table_data("contacts", [_contact(org="other-org")])
        assert client.post(f"{CONTACTS}/k1/resend-confirmation").status_code == 404
        assert fake.sent == []

    def test_not_pending_is_409(self, client, fake):
        client.mock_supabase.set_table_data("contacts", [_contact(optin="confirmed")])
        assert client.post(f"{CONTACTS}/k1/resend-confirmation").status_code == 409
        assert fake.sent == []


# ── send gate ────────────────────────────────────────────────────────────────

class TestSendGate:
    def test_predicate_is_an_allowlist(self):
        assert eo.receives_marketing_email(_contact(optin="not_required"))
        assert eo.receives_marketing_email(_contact(optin="confirmed"))
        assert not eo.receives_marketing_email(_contact(optin="pending"))
        assert not eo.receives_marketing_email(_contact(optin="confirmed", status="unsubscribed"))
        assert not eo.receives_marketing_email({"id": "k", "email": "a@test.com", "status": "active"})

    def test_campaign_queue_excludes_pending(self):
        db = MockSupabaseClient()
        db.set_table_data("campaigns", [{"id": "c1", "list_id": "L"}])
        db.set_table_data("contact_list_members", [
            {"list_id": "L", "contact_id": cid, "contacts": _contact(optin=optin, email=f"{cid}@t.com", cid=cid)}
            for cid, optin in (("k1", "pending"), ("k2", "confirmed"), ("k3", "not_required"))
        ])
        db.set_table_data("send_logs", [])
        assert SendService(db, _cfg()).queue_campaign_sends("c1", ORG) == 2
        queued = {r["contact_id"] for r in db.table("send_logs").select("*").execute().data}
        assert queued == {"k2", "k3"}

    @pytest.mark.parametrize("optin, sends", [("pending", 0), ("confirmed", 1), ("not_required", 1)])
    def test_automation_send_email_step_excludes_pending(self, optin, sends):
        from noctusai_lib.domain.jobs import FakeJobRepository

        from tests.modules.email_marketing.test_automation_executor import TPL, FakeDb, drain

        db, repo = FakeDb(), FakeJobRepository()
        db.contact["email_optin"] = optin
        db.steps(("send_email", {"template_id": TPL}), ("add_tag", {"tag": "seguiu"}))
        drain(db, repo)
        assert len(db.rows["send_logs"]) == sends
        assert db.contact["tags"] == ["seguiu"]  # the flow continues; only the mail is held back
        assert db.enrollment["status"] == "completed"


def test_confirmation_send_failure_is_reported():
    class _Boom:
        async def send(self, email):
            from noctusai_lib.integrations.email import EmailSendError
            raise EmailSendError("resend 500")

    out = asyncio.run(eo.send_confirmation(_Boom(), _cfg(), _contact()))
    assert out["sent"] is False and "resend 500" in out["reason"]
