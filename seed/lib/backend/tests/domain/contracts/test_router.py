"""Router contract: paths, statuses, envelopes, pt-BR codes, authz (staff read / admin write), masking, signature, attachments."""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.contracts import ATTACHMENT_UPLOAD_MAX_BYTES, ATTACHMENT_UPLOAD_PATH_PATTERN
from noctusai_lib.domain.contracts import signature as sig
from noctusai_lib.domain.contracts._common import Scope

from .conftest import CFG, ORG_A, VALID_CPF, VALID_CPF_2, body, build_harness, mk_party, run

U0 = "11111111-1111-1111-1111-111111111111"
P = "/api/contracts"

ROUTES = [
    ("GET", P, False), ("POST", P, True), ("POST", f"{P}/billing/run", True),
    ("GET", f"{P}/{U0}", False), ("PATCH", f"{P}/{U0}", True), ("DELETE", f"{P}/{U0}", True),
    ("POST", f"{P}/{U0}/activate", True), ("POST", f"{P}/{U0}/suspend", True), ("POST", f"{P}/{U0}/resume", True),
    ("POST", f"{P}/{U0}/terminate", True), ("POST", f"{P}/{U0}/amendments", True), ("POST", f"{P}/{U0}/readjust", True),
    ("GET", f"{P}/{U0}/versions", False), ("GET", f"{P}/{U0}/billing-preview", False), ("GET", f"{P}/{U0}/billings", False),
    ("GET", f"{P}/{U0}/usage", False), ("POST", f"{P}/{U0}/usage", True), ("POST", f"{P}/{U0}/document", True),
    ("POST", f"{P}/{U0}/signature", True), ("POST", f"{P}/{U0}/signature/sync", True), ("POST", f"{P}/{U0}/signature/cancel", True),
    ("GET", f"{P}/{U0}/attachments", False), ("POST", f"{P}/{U0}/attachments", True),
    ("DELETE", f"{P}/{U0}/attachments/{U0}", True),
]


def call(h, method, path, headers=None, **kw):
    return h.client.request(method, path, headers=headers or {}, **kw)


def create(h, headers=None, **over):
    r = call(h, "POST", P, headers or h.admin, json=body(**over))
    assert r.status_code == 201, r.text
    return r.json()["data"]


@pytest.mark.parametrize("method, path, _w", ROUTES)
def test_unauthenticated_is_strictly_401(h, method, path, _w):
    assert call(h, method, path, json={}).status_code == 401


@pytest.mark.parametrize("method, path, write", [r for r in ROUTES if r[2]])
def test_staff_cannot_write(h, method, path, write):
    kw = {"files": {"file": ("a.pdf", b"%PDF-1.4", "application/pdf")}} if path.endswith("/attachments") and method == "POST" else {"json": {}}
    assert call(h, method, path, h.staff("user"), **kw).status_code == 403


@pytest.mark.parametrize("method, path, write", [r for r in ROUTES if not r[2]])
def test_staff_can_read(h, method, path, write):
    assert call(h, method, path, h.staff("user")).status_code not in (401, 403)


def test_extra_fields_and_bad_enums_are_422(h):
    for bad in ({"typo": 1}, {"billing_model": "weekly"}, {"readjustment_index": "SELIC"}, {"amount_cents": -1},
                {"lines": [{"description": "x", "unit_price_cents": 1, "oops": 1}]}):
        assert call(h, "POST", P, h.admin, json=body(**bad)).status_code == 422, bad
    c = create(h)
    assert call(h, "POST", f"{P}/{c['id']}/amendments", h.admin, json={"summary": "x", "changes": {"billing_model": "one_time"}}).status_code == 422
    assert call(h, "POST", f"{P}/{c['id']}/suspend", h.admin, json={"reason": ""}).status_code == 422


def test_full_lifecycle_over_http(h):
    c = create(h, first_due_date="2026-11-10", notice_days=0)
    assert c["status"] == "draft" and c["terminable_from"]
    assert call(h, "GET", f"{P}?q=tráfego", h.staff()).json()["pagination"]["total"] == 1
    act = call(h, "POST", f"{P}/{c['id']}/activate", h.admin).json()["data"]
    assert act["status"] == "active"
    assert len(h.billing.entries) >= 1
    prev = call(h, "GET", f"{P}/{c['id']}/billing-preview?count=3", h.staff()).json()["data"]
    assert len(prev["items"]) == 3
    assert call(h, "POST", f"{P}/{c['id']}/suspend", h.admin, json={"reason": "pausa"}).json()["data"]["status"] == "suspended"
    assert call(h, "POST", f"{P}/{c['id']}/resume", h.admin).json()["data"]["status"] == "active"
    am = call(h, "POST", f"{P}/{c['id']}/amendments", h.admin, json={"summary": "Reajuste de escopo", "changes": {"notice_days": 15}})
    assert am.status_code == 201 and am.json()["data"]["notice_days"] == 15
    versions = call(h, "GET", f"{P}/{c['id']}/versions", h.staff()).json()["data"]
    assert [v["kind"] for v in versions] == ["initial", "suspension", "resumption", "amendment"]
    r = call(h, "POST", f"{P}/{c['id']}/terminate", h.admin, json={"reason": "fim", "effective_on": date.today().isoformat()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "aviso_previo_nao_cumprido"
    ok = call(h, "POST", f"{P}/{c['id']}/terminate", h.admin, json={"reason": "fim", "effective_on": "2099-01-01"})
    assert ok.json()["data"]["status"] == "terminated"
    assert call(h, "POST", f"{P}/{c['id']}/activate", h.admin).json()["error"]["code"] == "transicao_invalida"


def test_readjust_preview_and_apply_over_http(h):
    c = create(h, readjustment_index="IGPM")
    call(h, "POST", f"{P}/{c['id']}/activate", h.admin)
    prev = call(h, "POST", f"{P}/{c['id']}/readjust", h.admin, json={"percent_bp": 500}).json()["data"]
    assert prev["amount_cents_after"] == 157500 and prev["applied"] is False and "contract" not in prev
    done = call(h, "POST", f"{P}/{c['id']}/readjust", h.admin, json={"percent_bp": 500, "apply": True}).json()["data"]
    assert done["applied"] is True
    assert call(h, "GET", f"{P}/{c['id']}", h.staff()).json()["data"]["amount_cents"] == 157500


def test_party_doc_is_masked_for_staff_not_admin(h):
    p = mk_party(Scope(h.db, CFG, ORG_A))
    c = create(h, party_id=p["id"])
    assert c["party_doc"] == VALID_CPF
    seen = call(h, "GET", f"{P}/{c['id']}", h.staff()).json()["data"]
    assert seen["party_doc"] == "***.982.247-**" and seen["party_name"] == "Ana Souza"


def test_other_orgs_see_nothing(h):
    c = create(h)
    assert call(h, "GET", f"{P}/{c['id']}", h.staff("org-b")).status_code == 404
    assert call(h, "PATCH", f"{P}/{c['id']}", h.staff("org-b-admin"), json={"title": "x"}).status_code == 404
    assert call(h, "GET", P, h.staff("org-b")).json()["pagination"]["total"] == 0


def test_billing_run_route_runs_the_job_for_the_callers_org(h):
    c = create(h, first_due_date="2026-11-10")
    call(h, "POST", f"{P}/{c['id']}/activate", h.admin)
    out = call(h, "POST", f"{P}/billing/run", h.admin).json()["data"]
    assert out["contracts"] == 1 and out["failed"] == 0


def test_retainer_usage_over_http(h):
    c = create(h, billing_model="retainer", retainer_minutes=600, excess_rate_cents=10000)
    r = call(h, "POST", f"{P}/{c['id']}/usage", h.admin, json={"minutes": 700, "period": "2026-11-05"})
    assert r.status_code == 201
    usage = call(h, "GET", f"{P}/{c['id']}/usage", h.staff()).json()["data"]
    assert usage == [{"month": "2026-11", "minutes": 700, "included_minutes": 600, "excess_cents": 16667}]  # 100 min over x R$100/h = 166.67, half up
    assert call(h, "POST", f"{P}/{create(h)['id']}/usage", h.admin, json={"minutes": 5}).json()["error"]["code"] == "uso_nao_aplicavel"


# --- document + signature ----------------------------------------------------------------------------------


def test_document_render_and_signature_flow_activates_on_completion(h):
    p = mk_party(Scope(h.db, CFG, ORG_A))
    c = create(h, party_id=p["id"], number="CT-9", notice_days=30, penalty_cents=100000, readjustment_index="IPCA")
    no_doc = call(h, "POST", f"{P}/{c['id']}/signature", h.admin, json={"signers": [{"name": "Ana", "email": "a@x.com", "cpf": VALID_CPF}]})
    assert no_doc.status_code == 409 and no_doc.json()["error"]["code"] == "documento_nao_gerado"
    doc = call(h, "POST", f"{P}/{c['id']}/document", h.admin, json={}).json()["data"]["document_body"]
    for needle in ("CT-9", "Ana Souza", "R$ 1.500,00", "aviso prévio de 30 dias", "multa de R$ 1.000,00", "índice IPCA"):
        assert needle in doc, needle
    bad = call(h, "POST", f"{P}/{c['id']}/signature", h.admin, json={"signers": [{"name": "A", "email": "nope", "cpf": VALID_CPF}]})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "signatario_invalido"
    bad_cpf = call(h, "POST", f"{P}/{c['id']}/signature", h.admin, json={"signers": [{"name": "A", "email": "a@x.com", "cpf": "11111111111"}]})
    assert bad_cpf.json()["error"]["code"] == "signatario_invalido"
    sent = call(h, "POST", f"{P}/{c['id']}/signature", h.admin, json={"signers": [{"name": "Ana", "email": "a@x.com", "cpf": VALID_CPF},
                                                                                  {"name": "Bia", "email": "b@x.com", "cpf": VALID_CPF_2, "role": "vendedor"}]})
    assert sent.status_code == 201 and sent.json()["data"]["signature_status"] == "pendente" and sent.json()["data"]["signature_link"]
    again = call(h, "POST", f"{P}/{c['id']}/signature", h.admin, json={"signers": [{"name": "Ana", "email": "a@x.com", "cpf": VALID_CPF}]})
    assert again.json()["error"]["code"] == "assinatura_em_andamento"
    ext = call(h, "GET", f"{P}/{c['id']}", h.staff()).json()["data"]["signature_external_id"]
    h.adapter.marcar_assinado(ext, "a@x.com")
    part = call(h, "POST", f"{P}/{c['id']}/signature/sync", h.admin).json()["data"]
    assert part["signature_status"] == "parcial" and part["status"] == "draft"
    h.adapter.marcar_assinado(ext, "b@x.com")
    done = call(h, "POST", f"{P}/{c['id']}/signature/sync", h.admin).json()["data"]
    assert done["signature_status"] == "concluido" and done["signed_at"]
    assert done["status"] == "active" and len(h.billing.entries) >= 1  # signed -> activated -> billing started


def test_signature_can_be_cancelled_while_pending(h):
    c = create(h)
    call(h, "POST", f"{P}/{c['id']}/document", h.admin, json={})
    call(h, "POST", f"{P}/{c['id']}/signature", h.admin, json={"signers": [{"name": "Ana", "email": "a@x.com", "cpf": VALID_CPF}]})
    out = call(h, "POST", f"{P}/{c['id']}/signature/cancel", h.admin, json={"reason": "erro no texto"}).json()["data"]
    assert out["signature_status"] == "cancelado"
    assert call(h, "POST", f"{P}/{c['id']}/signature/cancel", h.admin, json={"reason": "x"}).status_code == 409


def test_signature_event_folding_is_forward_only_and_activates_a_draft(db, billing):
    from datetime import datetime, timezone

    from noctusai_lib.domain.contracts import contracts
    from noctusai_lib.integrations.signature.types import EventoAssinatura

    from .conftest import mk

    s = Scope(db, CFG, ORG_A)
    c = mk(s)
    ev = lambda st: EventoAssinatura(external_id="e1", status=st, provedor="d4sign", ocorrido_em=datetime.now(timezone.utc))  # noqa: E731
    out = sig.apply_signature_event(s, c, ev("parcial"), billing=billing)
    assert out["signature_status"] == "parcial" and out["status"] == "draft"
    back = sig.apply_signature_event(s, out, ev("pendente"), billing=billing)
    assert back["signature_status"] == "parcial"  # never regresses
    done = sig.apply_signature_event(s, contracts.get_contract(s, c["id"]), ev("concluido"), billing=billing)
    assert done["status"] == "active" and done["signed_at"] and len(billing.entries) >= 1
    late = sig.apply_signature_event(s, contracts.get_contract(s, c["id"]), ev("cancelado"), billing=billing)
    assert late["signature_status"] == "concluido"


def test_signature_routes_refuse_loudly_without_an_adapter(contracts_schema_cache):
    h = build_harness(with_signature=False)
    c = create(h)
    call(h, "POST", f"{P}/{c['id']}/document", h.admin, json={})
    r = call(h, "POST", f"{P}/{c['id']}/signature", h.admin, json={"signers": [{"name": "Ana", "email": "a@x.com", "cpf": VALID_CPF}]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "assinatura_nao_configurada"


# --- attachments -------------------------------------------------------------------------------------------


def test_attachment_upload_list_delete(h):
    c = create(h)
    pdf = b"%PDF-1.4 signed"
    up = call(h, "POST", f"{P}/{c['id']}/attachments", h.admin, files={"file": ("../../assinado.pdf", pdf, "application/pdf")}, data={"kind": "signed"})
    assert up.status_code == 201, up.text
    row = up.json()["data"]
    assert row["filename"] == "assinado.pdf" and row["kind"] == "signed" and "storage_path" not in row and row["url"]
    keys = run(h.storage.list_keys(bucket=CFG.bucket, prefix=f"{ORG_A}/contracts/{c['id']}/"))
    assert len(keys) == 1
    assert len(call(h, "GET", f"{P}/{c['id']}/attachments", h.staff()).json()["data"]) == 1
    assert call(h, "POST", f"{P}/{c['id']}/attachments", h.admin, files={"file": ("x.pdf", b"not a pdf", "application/pdf")}).status_code == 422
    assert call(h, "GET", f"{P}/{c['id']}/attachments", h.staff("org-b")).status_code == 404
    assert call(h, "DELETE", f"{P}/{c['id']}/attachments/{row['id']}", h.admin).status_code == 204
    assert call(h, "GET", f"{P}/{c['id']}/attachments", h.staff()).json()["data"] == []


def test_attachments_without_storage_refuse_loudly(contracts_schema_cache):
    h = build_harness(with_storage=False)
    c = create(h)
    r = call(h, "GET", f"{P}/{c['id']}/attachments", h.staff())
    assert r.status_code == 409 and r.json()["error"]["code"] == "armazenamento_nao_configurado"


def test_upload_route_is_declared_for_the_body_cap():
    assert ATTACHMENT_UPLOAD_PATH_PATTERN == "/api/contracts/*/attachments"
    assert ATTACHMENT_UPLOAD_MAX_BYTES > 10 * 1024 * 1024
