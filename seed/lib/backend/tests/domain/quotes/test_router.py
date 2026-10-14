"""Staff router contract: paths, statuses, envelopes, pt-BR codes, authz (staff read / admin write), isolation."""
from __future__ import annotations

import pytest

from .conftest import ORG_B, VALID_CPF, build_harness, line, seed_party, tomorrow

U0 = "11111111-1111-1111-1111-111111111111"
P = "/api/quotes"

#: (method, path, is_write) -- the whole staff surface.
ROUTES = [
    ("GET", P, False), ("POST", P, True), ("POST", f"{P}/calculate", False), ("POST", f"{P}/expire-due", True),
    ("GET", f"{P}/{U0}", False), ("PATCH", f"{P}/{U0}", True), ("DELETE", f"{P}/{U0}", True), ("GET", f"{P}/{U0}/events", False),
    ("POST", f"{P}/{U0}/versions", True), ("POST", f"{P}/{U0}/send", True), ("POST", f"{P}/{U0}/accept", True),
    ("POST", f"{P}/{U0}/reject", True), ("POST", f"{P}/{U0}/convert", True), ("GET", f"{P}/{U0}/acceptance", False),
    ("GET", f"{P}/{U0}/pdf", False), ("GET", f"{P}/{U0}/docx", False), ("POST", f"{P}/{U0}/signature", True),
    ("GET", f"{P}/{U0}/signature", False),
]


def call(h, method, path, headers=None, **kw):
    return h.client.request(method, path, headers=headers or {}, **kw)


@pytest.fixture
def party(h):
    return seed_party(h.db)


def mk(h, party, headers=None, **over):
    r = call(h, "POST", P, headers or h.admin, json={"party_id": party["id"], "valid_until": tomorrow().isoformat(), "lines": [_line()], **over})
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _line(**over):
    base = line(**over)
    base["qty"] = float(base["qty"]) if not isinstance(base["qty"], float) else base["qty"]
    return base


def send_link(h, qid):
    r = call(h, "POST", f"{P}/{qid}/send", h.admin, json={"channel": "link"})
    assert r.status_code == 200, r.text
    return r.json()["data"]


@pytest.mark.parametrize("method, path, _write", ROUTES)
def test_unauthenticated_is_strictly_401(h, method, path, _write):
    assert call(h, method, path, json={}).status_code == 401


@pytest.mark.parametrize("method, path, write", [r for r in ROUTES if r[2]])
def test_staff_cannot_write(h, method, path, write):
    assert call(h, method, path, h.staff("user"), json={}).status_code == 403


@pytest.mark.parametrize("method, path, write", [r for r in ROUTES if not r[2]])
def test_staff_can_read(h, method, path, write):
    kw = {"json": {"lines": []}} if method == "POST" else {}
    assert call(h, method, path, h.staff("user"), **kw).status_code not in (401, 403)   # 200 / 404, never an authz refusal


def test_routes_that_need_a_host_dependency_are_absent_when_it_is_not_supplied(quotes_schema_cache):
    bare = build_harness(docx=False, signature=False)
    assert call(bare, "GET", f"{P}/{U0}/docx", bare.admin).status_code == 404
    assert call(bare, "POST", f"{P}/{U0}/signature", bare.admin, json={}).status_code in (404, 405)


def test_extra_fields_and_bad_values_are_rejected_not_silently_dropped(h, party):
    base = {"party_id": party["id"], "lines": []}
    assert call(h, "POST", P, h.admin, json={**base, "typo_field": 1}).status_code == 422
    assert call(h, "POST", P, h.admin, json={**base, "total_cents": 1}).status_code == 422           # the client never sends a total
    assert call(h, "POST", P, h.admin, json={**base, "convert_to": "invoice"}).status_code == 422
    assert call(h, "POST", P, h.admin, json={**base, "discount_cents": -1}).status_code == 422
    assert call(h, "POST", P, h.admin, json={**base, "lines": [{"description": "x", "qty": 0, "unit_price_cents": 1}]}).status_code == 422
    assert call(h, "POST", P, h.admin, json={**base, "lines": [{"description": "x", "qty": 1, "unit_price_cents": 1, "price": 9}]}).status_code == 422
    assert call(h, "POST", P, h.admin, json={"lines": []}).status_code == 422                       # party is required


def test_lifecycle_through_http(h, party):
    q = mk(h, party, title="Reforma")
    assert q["number"] == "ORC-00001" and q["total_cents"] == 20000 and q["status"] == "draft"
    r = call(h, "PATCH", f"{P}/{q['id']}", h.admin, json={"discount_cents": 1000, "notes": "n"})
    assert r.status_code == 200 and r.json()["data"]["total_cents"] == 19000
    assert call(h, "POST", f"{P}/calculate", h.staff(), json={"lines": [_line(qty=1.5, unit_price_cents=100)]}).json()["data"]["total_cents"] == 150
    sent = send_link(h, q["id"])
    assert sent["quote"]["status"] == "sent" and sent["url"].startswith("https://app.test/orcamento/") and sent["sent_to"] is None
    r = call(h, "POST", f"{P}/{q['id']}/versions", h.admin, json={})
    assert r.status_code == 201 and r.json()["data"]["version"] == 2
    page = call(h, "GET", P, h.staff()).json()
    assert page["pagination"]["total"] == 1 and page["data"][0]["id"] == r.json()["data"]["id"]
    ev = call(h, "GET", f"{P}/{q['id']}/events", h.staff()).json()["data"]
    assert [e["kind"] for e in ev] == ["created", "updated", "sent", "superseded"]


def test_delete_returns_204_then_404(h, party):
    q = mk(h, party)
    assert call(h, "DELETE", f"{P}/{q['id']}", h.admin).status_code == 204
    assert call(h, "GET", f"{P}/{q['id']}", h.staff()).status_code == 404


def test_pt_br_error_codes_and_statuses(h, party):
    q = mk(h, party)
    send_link(h, q["id"])
    r = call(h, "PATCH", f"{P}/{q['id']}", h.admin, json={"title": "x"})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "orcamento_bloqueado")
    r = call(h, "POST", P, h.admin, json={"party_id": U0, "lines": []})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "cliente_invalido")
    r = call(h, "POST", P, h.admin, json={"party_id": party["id"], "lines": [_line(discount_cents=999_999)]})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "desconto_invalido")
    r = call(h, "POST", f"{P}/{q['id']}/accept", h.admin, json={"signer_name": "Ana Souza"})
    assert r.status_code == 200
    r = call(h, "POST", f"{P}/{q['id']}/accept", h.admin, json={"signer_name": "Ana Souza"})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "orcamento_encerrado")
    r = call(h, "POST", f"{P}/{q['id']}/versions", h.admin, json={})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "transicao_invalida")


def test_org_isolation_over_http(h, party):
    q = mk(h, party)
    for method, path, kw in (("GET", f"{P}/{q['id']}", {}), ("PATCH", f"{P}/{q['id']}", {"json": {"title": "x"}}),
                             ("DELETE", f"{P}/{q['id']}", {}), ("POST", f"{P}/{q['id']}/send", {"json": {"channel": "link"}}),
                             ("POST", f"{P}/{q['id']}/versions", {"json": {}}), ("GET", f"{P}/{q['id']}/pdf", {}),
                             ("POST", f"{P}/{q['id']}/accept", {"json": {"signer_name": "Ana Souza"}})):
        assert call(h, method, path, h.staff("org-b-admin"), **kw).status_code == 404, (method, path)
    assert call(h, "GET", P, h.staff("org-b")).json()["pagination"]["total"] == 0
    other = seed_party(h.db, ORG_B)
    r = call(h, "POST", P, h.admin, json={"party_id": other["id"], "lines": []})        # org B's customer, org A's session
    assert r.status_code == 422


def test_send_by_email_attaches_the_pdf_and_names_the_link(h, party):
    q = mk(h, party)
    r = call(h, "POST", f"{P}/{q['id']}/send", h.admin, json={"channel": "email", "message": "Segue."})
    data = r.json()["data"]
    assert r.status_code == 200 and data["sent_to"] == "ana@cliente.com" and data["quote"]["last_sent_to"] == "ana@cliente.com"
    (mail,) = h.email.sent
    assert mail.to == ["ana@cliente.com"] and q["number"] in mail.subject and data["url"] in mail.text and data["url"] in mail.html
    (pdf,) = mail.attachments
    assert pdf.mime_type == "application/pdf" and pdf.content.startswith(b"%PDF") and pdf.filename == f"{q['number']}-v1.pdf"
    assert "Segue." in mail.text


def test_send_refusals(h, party, quotes_schema_cache):
    empty = mk(h, party, lines=[])
    r = call(h, "POST", f"{P}/{empty['id']}/send", h.admin, json={"channel": "link"})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "orcamento_vazio")
    nomail = seed_party(h.db, email=None)
    q = mk(h, nomail)
    r = call(h, "POST", f"{P}/{q['id']}/send", h.admin, json={"channel": "email"})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "email_indisponivel")
    assert call(h, "POST", f"{P}/{q['id']}/send", h.admin, json={"channel": "email", "to": "not-an-email"}).status_code == 422
    assert call(h, "POST", f"{P}/{q['id']}/send", h.admin, json={"channel": "email", "to": "x@y.com"}).status_code == 200
    unconfigured = build_harness(secret=None)
    p2 = seed_party(unconfigured.db)
    q2 = mk(unconfigured, p2)
    r = call(unconfigured, "POST", f"{P}/{q2['id']}/send", unconfigured.admin, json={"channel": "link"})
    assert (r.status_code, r.json()["error"]["code"]) == (503, "link_indisponivel")
    assert call(unconfigured, "GET", f"{P}/{q2['id']}", unconfigured.admin).json()["data"]["status"] == "draft"   # nothing moved


def test_pdf_and_docx_downloads(h, party):
    q = mk(h, party)
    r = call(h, "GET", f"{P}/{q['id']}/pdf", h.staff())
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    r = call(h, "GET", f"{P}/{q['id']}/docx", h.staff())
    assert r.status_code == 200 and r.headers["content-type"].endswith("wordprocessingml.document") and r.content


def test_staff_acceptance_converts_and_exposes_the_consent_record(h, party):
    q = mk(h, party, lines=[_line(kind="goods")])
    send_link(h, q["id"])
    r = call(h, "POST", f"{P}/{q['id']}/accept", h.admin, json={"signer_name": "Ana Souza", "note": "telefone"})
    data = r.json()["data"]
    assert data["status"] == "accepted" and data["conversion_status"] == "done" and data["acceptance"]["channel"] == "staff"
    assert h.handler.calls[0].convert_to == "order"
    got = call(h, "GET", f"{P}/{q['id']}/acceptance", h.staff()).json()["data"]
    assert got["signer_name"] == "Ana Souza" and got["decision"] == "accepted"


def test_convert_retry_route(h, party):
    h.handler.raises = RuntimeError("boom")
    q = mk(h, party, lines=[_line(kind="goods")])
    send_link(h, q["id"])
    r = call(h, "POST", f"{P}/{q['id']}/accept", h.admin, json={"signer_name": "Ana Souza"})
    assert r.json()["data"]["conversion_status"] == "failed"
    h.handler.raises = None
    r = call(h, "POST", f"{P}/{q['id']}/convert", h.admin)
    assert r.status_code == 200 and r.json()["data"]["conversion_status"] == "done"


def test_staff_rejection_needs_a_reason(h, party):
    q = mk(h, party)
    send_link(h, q["id"])
    assert call(h, "POST", f"{P}/{q['id']}/reject", h.admin, json={"reason": ""}).status_code == 422
    r = call(h, "POST", f"{P}/{q['id']}/reject", h.admin, json={"reason": "Preço"})
    assert r.json()["data"]["status"] == "rejected" and r.json()["data"]["rejection_reason"] == "Preço"


def test_signature_roundtrip_through_the_fake_provider(h, party):
    q = mk(h, party)
    send_link(h, q["id"])
    body = {"signers": [{"name": "Ana Souza", "email": "ana@cliente.com", "cpf": VALID_CPF}]}
    r = call(h, "POST", f"{P}/{q['id']}/signature", h.admin, json=body)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "transicao_invalida")           # not accepted yet
    call(h, "POST", f"{P}/{q['id']}/accept", h.admin, json={"signer_name": "Ana Souza"})
    r = call(h, "POST", f"{P}/{q['id']}/signature", h.admin, json={"signers": [{**body["signers"][0], "cpf": "11111111111"}]})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "assinatura_invalida")
    assert h.signature.calls == []                                                           # CPF refused BEFORE the provider
    r = call(h, "POST", f"{P}/{q['id']}/signature", h.admin, json=body)
    assert r.status_code == 201 and r.json()["data"]["status"] == "pendente"
    ext = r.json()["data"]["external_id"]
    assert call(h, "GET", f"{P}/{q['id']}", h.staff()).json()["data"]["signature_ref"] == ext
    r = call(h, "POST", f"{P}/{q['id']}/signature", h.admin, json=body)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "assinatura_invalida")           # already out for signature
    h.signature.marcar_assinado(ext, "ana@cliente.com")
    r = call(h, "GET", f"{P}/{q['id']}/signature", h.staff())
    assert r.json()["data"] == {"status": "concluido", "changed": True, "external_id": ext}


def test_expire_due_route(h, party):
    q = mk(h, party)
    send_link(h, q["id"])
    from datetime import date, timedelta

    h.db.table("quo_quotes").update({"valid_until": (date.today() - timedelta(days=3)).isoformat()}).eq("id", q["id"]).execute()
    assert call(h, "POST", f"{P}/expire-due", h.admin).json()["data"] == {"expired": 1}
    assert call(h, "GET", f"{P}/{q['id']}", h.staff()).json()["data"]["status"] == "expired"
