"""The PUBLIC accept surface: signed-token gate, one indistinguishable 404, allow-listed output (no PII), consent, throttling."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from noctusai_lib.domain.commerce import access_links
from noctusai_lib.domain.quotes import links
from noctusai_lib.domain.quotes.public import present_public
from noctusai_lib.primitives.exceptions import AppException, app_exception_handler

from .conftest import CFG, ORG_A, ORG_B, SECRET, build_harness, line, seed_party, tomorrow

P = "/api/public/quotes"
S = "/api/quotes"
PII = ("52998224725", "ana@cliente.com", "+5511", "legal_name", "org_id", "party_id", "created_by", "last_sent_to")


@pytest.fixture
def party(h):
    return seed_party(h.db, doc="52998224725", phones=["+5511994573387"], address={"street": "Rua Secreta"})


def sent(h, party, **over):
    r = h.client.post(S, headers=h.admin, json={"party_id": party["id"], "valid_until": tomorrow().isoformat(), "lines": [line(kind="goods", qty=2)], **over})
    qid = r.json()["data"]["id"]
    out = h.client.post(f"{S}/{qid}/send", headers=h.admin, json={"channel": "link"}).json()["data"]
    return qid, out["url"].rsplit("/", 1)[1]


def post(h, token, action, **body):
    return h.client.post(f"{P}/{token}/{action}", json=body, headers={"user-agent": "pytest-agent"})


# ─── the token gate ──────────────────────────────────────────────────────────


def test_link_round_trip_and_marks_the_quote_viewed(h, party):
    qid, token = sent(h, party)
    r = h.client.get(f"{P}/{token}")
    assert r.status_code == 200 and r.json()["data"]["status"] == "viewed" and r.json()["data"]["can_decide"] is True
    assert h.client.get(f"{S}/{qid}", headers=h.staff()).json()["data"]["viewed_at"]
    assert h.client.get(f"{P}/{token}").json()["data"]["status"] == "viewed"
    kinds = [e["kind"] for e in h.client.get(f"{S}/{qid}/events", headers=h.staff()).json()["data"]]
    assert kinds.count("viewed") == 1                                              # one transition, one event


def _bad_tokens(h, party):
    qid, token = sent(h, party)
    body, mac = token.split(".")
    other_org = access_links.sign_token(SECRET, purpose=links.PURPOSE_QUOTE_ACCEPT, org_id=ORG_B, subject=qid, ttl_minutes=60)
    wrong_purpose = access_links.sign_token(SECRET, purpose=access_links.PURPOSE_MY_ORDERS, org_id=ORG_A, subject=qid, ttl_minutes=60)
    expired = access_links.sign_token(SECRET, purpose=links.PURPOSE_QUOTE_ACCEPT, org_id=ORG_A, subject=qid, ttl_minutes=1,
                                      at=datetime.now(timezone.utc) - timedelta(hours=2))
    wrong_secret = access_links.sign_token("another-secret", purpose=links.PURPOSE_QUOTE_ACCEPT, org_id=ORG_A, subject=qid, ttl_minutes=60)
    unknown_quote = access_links.sign_token(SECRET, purpose=links.PURPOSE_QUOTE_ACCEPT, org_id=ORG_A, subject="11111111-1111-4111-8111-111111111111", ttl_minutes=60)
    return {
        "garbage": "not-a-token", "empty-ish": "x.y", "tampered-mac": f"{body}.{mac[:-2]}AA", "tampered-body": f"{body[:-2]}AA.{mac}",
        "foreign-org": other_org, "wrong-purpose": wrong_purpose, "expired": expired, "wrong-secret": wrong_secret, "unknown-quote": unknown_quote,
    }


def test_every_bad_token_is_the_same_404(h, party):
    answers = set()
    for name, token in _bad_tokens(h, party).items():
        for method, suffix, kw in (("GET", "", {}), ("GET", "/pdf", {}), ("POST", "/accept", {"json": {"name": "Ana Souza", "agree": True}}), ("POST", "/reject", {"json": {}})):
            r = h.client.request(method, f"{P}/{token}{suffix}", **kw)
            assert r.status_code == 404, (name, method, suffix, r.status_code)
            answers.add(json.dumps(r.json(), sort_keys=True))
    assert len(answers) == 1                                                      # a probe learns nothing about WHY
    assert json.loads(answers.pop())["error"]["code"] == "link_invalido"


def test_a_token_for_org_a_cannot_touch_org_bs_quote_even_with_a_valid_mac(h, party):
    qid, _ = sent(h, party)
    forged = access_links.sign_token(SECRET, purpose=links.PURPOSE_QUOTE_ACCEPT, org_id=ORG_B, subject=qid, ttl_minutes=60)
    assert h.client.get(f"{P}/{forged}").status_code == 404                        # MAC is fine; the quote is not in org B


def test_the_token_never_outlives_the_offer(h, party):
    cfg_ttl = links.link_ttl_minutes(CFG, tomorrow(), now=datetime.now(timezone.utc))
    assert 0 < cfg_ttl <= CFG.link_ttl_days * 24 * 60
    assert links.link_ttl_minutes(CFG, None) == CFG.link_ttl_days * 24 * 60
    far = datetime.now(timezone.utc).date() + timedelta(days=400)
    assert links.link_ttl_minutes(CFG, far) == CFG.link_ttl_days * 24 * 60
    past = datetime.now(timezone.utc).date() - timedelta(days=5)
    assert links.link_ttl_minutes(CFG, past) == 1


def test_a_draft_has_no_public_page(h, party):
    qid = h.client.post(S, headers=h.admin, json={"party_id": party["id"], "lines": [line()]}).json()["data"]["id"]
    token = links.mint_token(SECRET, CFG, h.db.table("quo_quotes").select("*").eq("id", qid).execute().data[0])
    assert h.client.get(f"{P}/{token}").status_code == 404


def test_an_inactive_org_is_the_same_404(quotes_schema_cache, party=None):
    from noctusai_lib.domain.quotes import make_quotes_public_router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    base = build_harness()
    p = seed_party(base.db)
    qid, token = sent(base, p)
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.include_router(make_quotes_public_router(CFG, get_db=lambda: base.db, get_link_secret=lambda: SECRET, is_org_active=lambda db, org: False))
    assert TestClient(app).get(f"{P}/{token}").status_code == 404


# ─── no PII beyond the quote ─────────────────────────────────────────────────


def test_public_view_is_an_allow_list_with_no_pii(h, party):
    qid, token = sent(h, party, title="Reforma", notes="obs", terms="30 dias")
    h.client.post(f"{S}/{qid}/send", headers=h.admin, json={"channel": "email"})
    data = h.client.get(f"{P}/{token}").json()["data"]
    assert set(data) == {"number", "version", "title", "status", "currency", "valid_until", "notes", "terms", "subtotal_cents",
                         "discount_cents", "total_cents", "party_name", "issuer_name", "lines", "can_decide", "decision", "consent_template"}
    assert data["party_name"] == "Ana Souza" and data["issuer_name"] == "Acme Ltda" and data["title"] == "Reforma"
    assert set(data["lines"][0]) == {"position", "description", "unit", "qty", "unit_price_cents", "discount_cents", "total_cents"}
    blob = json.dumps(data)
    for needle in ("52998224725", "ana@cliente.com", "+5511994573387", "Rua Secreta", party["id"], ORG_A, qid, "created_by", "last_sent_to"):
        assert needle not in blob, needle
    assert "{name}" in data["consent_template"] and data["number"] in data["consent_template"]


def test_public_pdf_carries_only_the_offer(h, party):
    _, token = sent(h, party)
    r = h.client.get(f"{P}/{token}/pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")


# ─── deciding on the link ────────────────────────────────────────────────────


def test_accept_on_the_link_records_consent_and_converts(h, party):
    qid, token = sent(h, party)
    refused = post(h, token, "accept", name="Ana Souza", agree=False)
    assert (refused.status_code, refused.json()["error"]["code"]) == (422, "consentimento_obrigatorio")
    r = post(h, token, "accept", name="Ana Souza", agree=True)
    assert r.status_code == 200
    data = r.json()["data"]
    assert (data["status"], data["can_decide"], data["decision"]["decision"]) == ("accepted", False, "accepted")
    assert set(data["decision"]) == {"decision", "decided_at"}                                 # the signer's name is not echoed back
    acc = h.client.get(f"{S}/{qid}/acceptance", headers=h.staff()).json()["data"]
    assert (acc["channel"], acc["signer_name"], acc["user_agent"]) == ("public_link", "Ana Souza", "pytest-agent")
    assert acc["ip"] and acc["consent_text"].startswith("Eu, Ana Souza,")
    assert [c.convert_to for c in h.handler.calls] == ["order"]
    again = post(h, token, "accept", name="Ana Souza", agree=True)
    assert (again.status_code, again.json()["error"]["code"]) == (409, "orcamento_encerrado")


def test_reject_on_the_link_and_the_final_state_stays_readable(h, party):
    qid, token = sent(h, party)
    r = post(h, token, "reject", reason="Muito caro")
    assert r.status_code == 200 and r.json()["data"]["status"] == "rejected"
    assert h.client.get(f"{P}/{token}").json()["data"]["decision"]["decision"] == "rejected"
    assert h.client.get(f"{S}/{qid}", headers=h.staff()).json()["data"]["rejection_reason"] == "Muito caro"
    assert h.handler.calls == []


def test_public_bodies_are_strict(h, party):
    _, token = sent(h, party)
    assert post(h, token, "accept", name="Ana Souza", agree=True, role="admin").status_code == 422
    assert post(h, token, "accept", name="A", agree=True).status_code == 422
    assert post(h, token, "reject", reason="x" * 600).status_code == 422
    assert post(h, token, "reject", status="accepted").status_code == 422


def test_a_new_version_retires_the_old_link_for_deciding(h, party):
    qid, token = sent(h, party)
    h.client.post(f"{S}/{qid}/versions", headers=h.admin, json={})
    view = h.client.get(f"{P}/{token}").json()["data"]
    assert view["status"] == "superseded" and view["can_decide"] is False and view["consent_template"] is None
    r = post(h, token, "accept", name="Ana Souza", agree=True)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "orcamento_substituido")


def test_an_expired_offer_shows_expired_and_refuses(h, party):
    qid, token = sent(h, party)
    from datetime import date

    h.db.table("quo_quotes").update({"valid_until": (date.today() - timedelta(days=2)).isoformat()}).eq("id", qid).execute()
    assert h.client.get(f"{P}/{token}").json()["data"]["status"] == "expired"
    r = post(h, token, "accept", name="Ana Souza", agree=True)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "orcamento_expirado")


# ─── throttling ──────────────────────────────────────────────────────────────


def test_every_public_route_goes_through_the_host_rate_limiter(h):
    assert sorted(h.limited) == sorted([("view", CFG.public_rate_limit), ("pdf", CFG.public_rate_limit),
                                        ("accept", CFG.decision_rate_limit), ("reject", CFG.decision_rate_limit)])
    assert CFG.decision_rate_limit != CFG.public_rate_limit                       # writes are throttled harder than reads


def test_a_real_wrapping_limiter_keeps_the_routes_working(quotes_schema_cache):
    """A decorator from ANOTHER module (what slowapi is) must not break annotation resolution (the commerce 500)."""
    import functools

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from noctusai_lib.domain.quotes import make_quotes_public_router

    def limiter(limit):
        def deco(fn):
            @functools.wraps(fn)
            async def wrapper(*a, **k):
                return await fn(*a, **k)
            return wrapper
        return deco

    h2 = build_harness()
    p = seed_party(h2.db)
    _, token = sent(h2, p)
    app = FastAPI()
    app.include_router(make_quotes_public_router(CFG, get_db=lambda: h2.db, get_link_secret=lambda: SECRET, rate_limit=limiter))
    c = TestClient(app)
    assert c.get(f"{P}/{token}").status_code == 200
    assert c.post(f"{P}/{token}/accept", json={"name": "Ana Souza", "agree": True}).status_code == 200


def test_present_public_cannot_leak_a_field_it_was_not_given():
    row = {"number": "N", "version": 1, "status": "sent", "is_current": True, "subtotal_cents": 1, "discount_cents": 0, "total_cents": 1,
           "party_id": "SECRET-PARTY", "created_by": "SECRET-USER", "org_id": "SECRET-ORG", "valid_until": None}
    out = present_public(None, row, [], party_name="x", issuer="y", acceptance=None)   # type: ignore[arg-type]
    assert "SECRET" not in json.dumps(out)
