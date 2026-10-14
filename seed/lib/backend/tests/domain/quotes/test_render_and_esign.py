"""Rendering (HTML / PDF / DOCX gate) and the e-signature hand-off + webhook apply."""
from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.domain.quotes import Channel, decisions, esign, quotes as svc, render
from noctusai_lib.domain.quotes.errors import QuotesError
from noctusai_lib.integrations.docx_render import FakeDocxRenderAdapter
from noctusai_lib.integrations.signature import EventoAssinatura, FakeSignatureAdapter

from .conftest import VALID_CPF, docx_template_bytes, line, seed_party, tomorrow

SIGNERS = [{"name": "Ana Souza", "email": "ana@cliente.com", "cpf": VALID_CPF}]


@pytest.fixture
def accepted(db, s):
    p = seed_party(db)
    q = svc.create_quote(s, {"party_id": p["id"], "valid_until": tomorrow(), "title": "Reforma <b>x</b>", "notes": "linha1\nlinha2",
                             "lines": [line(description="Tinta & Cia 😀", kind="goods", qty="2.5", unit_price_cents=1999)]})
    svc.transition(s, svc.get_row(s, q["id"]), "sent", expect=["draft"])
    decisions.accept_quote(s, q["id"], channel=Channel.STAFF, signer_name="Ana Souza")
    return q["id"]


def ctx_of(s, qid):
    v = svc.get_quote(s, qid)
    return render.quote_context(v, v["lines"], party_name="Ana Souza", issuer_name="Acme Ltda")


def test_context_is_display_ready(s, accepted):
    ctx = ctx_of(s, accepted)
    assert ctx["total"] == "R$ 49,98" and ctx["lines"][0]["qty"] == "2,5" and ctx["lines"][0]["unit_price"] == "R$ 19,99"
    assert ctx["status"] == "Aceito" and ctx["valid_until"].count("/") == 2 and ctx["lines"][0]["n"] == 1


def test_html_escapes_user_text_and_drops_what_fonts_cannot_draw(s, accepted):
    html = render.render_html(ctx_of(s, accepted))
    assert "&lt;b&gt;x&lt;/b&gt;" in html and "<b>x</b>" not in html
    assert "Tinta &amp; Cia" in html and "😀" not in html and "linha1<br/>linha2" in html


def test_pdf_is_a_real_pdf(s, accepted):
    pdf = render.render_pdf(ctx_of(s, accepted))
    assert pdf.startswith(b"%PDF") and len(pdf) > 800
    assert render.render_pdf(ctx_of(s, accepted), deterministic=True) == render.render_pdf(ctx_of(s, accepted), deterministic=True)


def test_docx_fills_the_host_template_and_reports_gaps(s, accepted):
    adapter = FakeDocxRenderAdapter()
    out = render.render_docx(adapter, docx_template_bytes(), ctx_of(s, accepted))
    assert out[:2] == b"PK" and adapter.calls
    with pytest.raises(QuotesError) as e:
        render.render_docx(adapter, docx_template_bytes("{{ number }} {{ cnpj_do_cliente }}"), ctx_of(s, accepted))
    assert (e.value.code, e.value.status_code) == ("modelo_invalido", 422) and e.value.details["missing"] == ["cnpj_do_cliente"]


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_signature_request_stores_the_envelope_and_validates_signers_first(db, s, accepted):
    adapter = FakeSignatureAdapter()
    with pytest.raises(QuotesError) as e:
        run(esign.request_signature(s, accepted, adapter, [{**SIGNERS[0], "cpf": "123"}]))
    assert e.value.code == "assinatura_invalida" and adapter.calls == []
    out = run(esign.request_signature(s, accepted, adapter, SIGNERS, message="Assine", user_id="u"))
    row = svc.get_row(s, accepted)
    assert (row["signature_ref"], row["signature_status"]) == (out["external_id"], "pendente") and out["provider"]
    assert adapter.calls[0][0] == "criar_envelope"


def test_webhook_events_move_forward_only(db, s, accepted):
    adapter = FakeSignatureAdapter()
    ext = run(esign.request_signature(s, accepted, adapter, SIGNERS))["external_id"]
    done = EventoAssinatura(external_id=ext, status="concluido", provedor="fake", ocorrido_em=__import__("datetime").datetime.now())
    assert esign.apply_signature_event(s, done) == {"status": "concluido", "changed": True}
    assert esign.apply_signature_event(s, done) == {"status": "concluido", "changed": False}          # replay
    late_cancel = EventoAssinatura(external_id=ext, status="cancelado", provedor="fake", ocorrido_em=done.ocorrido_em)
    assert esign.apply_signature_event(s, late_cancel)["changed"] is False                            # terminal never regresses
    assert svc.get_row(s, accepted)["signature_status"] == "concluido"
    assert esign.apply_signature_event(s, EventoAssinatura(external_id="unknown", status="concluido", provedor="fake", ocorrido_em=done.ocorrido_em)) is None


def test_signature_events_cannot_cross_orgs(db, s, s_b, accepted):
    ext = run(esign.request_signature(s, accepted, FakeSignatureAdapter(), SIGNERS))["external_id"]
    ev = EventoAssinatura(external_id=ext, status="concluido", provedor="fake", ocorrido_em=__import__("datetime").datetime.now())
    assert esign.apply_signature_event(s_b, ev) is None
