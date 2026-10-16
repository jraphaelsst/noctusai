"""Accept / reject: the claim-then-record order, the consent record, the convert-on-accept seam and its failure modes."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from noctusai_lib.domain.quotes import (
    Channel, FakeQuoteAcceptHandler, NoopQuoteAcceptHandler, QuoteAcceptContext, QuoteConversion, decisions, quotes as svc,
)
from noctusai_lib.domain.quotes.errors import QuotesError

from .conftest import ORG_A, QuotesDb, line, make_db, seed_party, today, tomorrow


@pytest.fixture
def party(db):
    return seed_party(db)


def sent(s, party, **over):
    q = svc.create_quote(s, {"party_id": party["id"], "valid_until": tomorrow(), "lines": [line(kind="goods")], **over})
    svc.transition(s, svc.get_row(s, q["id"]), "sent", expect=["draft"], extra={"sent_at": "2026-10-14T00:00:00+00:00"})
    return q["id"]


def public_accept(s, qid, **over):
    kw = dict(channel=Channel.PUBLIC_LINK, signer_name="Ana Souza", agree=True, ip="203.0.113.7", user_agent="Mozilla/5.0")
    return decisions.accept_quote(s, qid, **{**kw, **over})


def code(e):
    return e.value.code


def acceptance_rows(db):
    return db.table("quo_acceptances").select("*").execute().data


# ─── the consent record ──────────────────────────────────────────────────────


def test_public_accept_records_who_when_where_and_exactly_what_was_shown(db, s, party):
    qid = sent(s, party)
    out = public_accept(s, qid, user_agent="U" * 500)
    quote, acc = out["quote"], out["acceptance"]
    assert quote["status"] == "accepted" and quote["accepted_at"]
    assert (acc["decision"], acc["channel"], acc["signer_name"], acc["ip"]) == ("accepted", "public_link", "Ana Souza", "203.0.113.7")
    assert len(acc["user_agent"]) == 300                                         # a hostile header cannot bloat the record
    row = svc.get_row(s, qid)
    assert acc["consent_text"] == decisions.consent_text(row, "Ana Souza")
    assert row["number"] in acc["consent_text"] and "R$ 200,00" in acc["consent_text"] and "versão 1" in acc["consent_text"]
    assert acc["content_sha256"] == decisions.content_sha256(row, svc.quote_lines(s, qid))
    assert acceptance_rows(db) == [acc]


def test_public_accept_requires_explicit_agreement_and_a_name(s, party):
    qid = sent(s, party)
    with pytest.raises(QuotesError) as e:
        public_accept(s, qid, agree=False)
    assert (code(e), e.value.status_code) == ("consentimento_obrigatorio", 422)
    with pytest.raises(QuotesError) as e:
        public_accept(s, qid, signer_name=" a ")
    assert code(e) == "nome_obrigatorio"
    assert svc.get_row(s, qid)["status"] == "sent"                                # refusals decided nothing


def test_staff_can_record_an_offline_acceptance_without_the_consent_sentence(s, party):
    qid = sent(s, party)
    out = decisions.accept_quote(s, qid, channel=Channel.STAFF, signer_name="Ana Souza", note="aceite por telefone", user_id="u1")
    acc = out["acceptance"]
    assert (acc["channel"], acc["consent_text"], acc["reason"], acc["decided_by"]) == ("staff", None, "aceite por telefone", "u1")


def test_content_hash_pins_what_was_offered(s, party):
    qid = sent(s, party)
    row, lines = svc.get_row(s, qid), svc.quote_lines(s, qid)
    base = decisions.content_sha256(row, lines)
    assert decisions.content_sha256(row, lines) == base and len(base) == 64
    assert decisions.content_sha256({**row, "terms": "outro"}, lines) != base
    assert decisions.content_sha256(row, [{**lines[0], "unit_price_cents": 1}]) != base
    assert decisions.content_sha256({**row, "id": "irrelevant", "status": "x"}, lines) == base      # bookkeeping is not content


# ─── state machine ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("status, expected", [("draft", "transicao_invalida"), ("rejected", "orcamento_encerrado"), ("accepted", "orcamento_encerrado")])
def test_only_an_open_quote_can_be_decided(s, party, status, expected):
    q = svc.create_quote(s, {"party_id": party["id"], "valid_until": tomorrow(), "lines": [line()]})
    s.tbl("quotes").update({"status": status, **({"accepted_at": "2026-10-14T00:00:00+00:00"} if status == "accepted" else {})}).eq("id", q["id"]).execute()
    with pytest.raises(QuotesError) as e:
        public_accept(s, q["id"])
    assert (code(e), e.value.status_code) == (expected, 409)


def test_an_expired_offer_cannot_be_accepted(s, party):
    qid = sent(s, party)
    s.tbl("quotes").update({"valid_until": (today() - timedelta(days=2)).isoformat()}).eq("id", qid).execute()
    with pytest.raises(QuotesError) as e:
        public_accept(s, qid)
    assert code(e) == "orcamento_expirado" and svc.get_row(s, qid)["status"] == "expired"


def test_a_superseded_version_cannot_be_accepted_the_new_one_can(s, party):
    qid = sent(s, party)
    v2 = svc.new_version(s, qid)
    with pytest.raises(QuotesError) as e:
        public_accept(s, qid)
    assert code(e) == "orcamento_substituido"
    svc.transition(s, svc.get_row(s, v2["id"]), "sent", expect=["draft"])
    assert public_accept(s, v2["id"])["quote"]["status"] == "accepted"


def test_the_second_decision_loses(db, s, party):
    qid = sent(s, party)
    public_accept(s, qid)
    for attempt in (lambda: public_accept(s, qid), lambda: decisions.reject_quote(s, qid, channel=Channel.PUBLIC_LINK, reason="não")):
        with pytest.raises(QuotesError) as e:
            attempt()
        assert (code(e), e.value.status_code) == ("orcamento_encerrado", 409)
    assert len(acceptance_rows(db)) == 1                                           # one decision per version


def test_viewed_quotes_are_decidable_too(s, party):
    qid = sent(s, party)
    svc.transition(s, svc.get_row(s, qid), "viewed", expect=["sent"])
    assert public_accept(s, qid)["quote"]["status"] == "accepted"


def test_a_failed_consent_write_undoes_the_claim(quotes_schema_cache):
    class NoAcceptanceDb(QuotesDb):
        def table(self, name):
            if name == "quo_acceptances":
                raise RuntimeError("disk full")
            return super().table(name)

    db = make_db()
    from noctusai_lib.domain.quotes._common import Scope
    from .conftest import CFG

    s = Scope(db, CFG, ORG_A)
    qid = sent(s, seed_party(db))
    broken = Scope(NoAcceptanceDb.__new__(NoAcceptanceDb), CFG, ORG_A)
    broken.db.__dict__.update(db.__dict__)                                         # same data, acceptance table unwritable
    with pytest.raises(RuntimeError):
        public_accept(broken, qid)
    row = svc.get_row(s, qid)
    assert (row["status"], row["accepted_at"], row["conversion_status"]) == ("sent", None, "none")   # still decidable
    assert public_accept(s, qid)["quote"]["status"] == "accepted"


# ─── reject ──────────────────────────────────────────────────────────────────


def test_reject_records_the_decision_and_allows_a_revision(db, s, party):
    qid = sent(s, party)
    out = decisions.reject_quote(s, qid, channel=Channel.PUBLIC_LINK, reason="  caro demais ", ip="198.51.100.2")
    row = svc.get_row(s, qid)
    assert (row["status"], row["rejection_reason"], bool(row["rejected_at"])) == ("rejected", "caro demais", True)
    acc = out["acceptance"]
    assert (acc["decision"], acc["signer_name"], acc["consent_text"], acc["ip"]) == ("rejected", "(não informado)", None, "198.51.100.2")
    assert svc.new_version(s, qid)["version"] == 2


def test_staff_rejection_requires_a_reason(s, party):
    qid = sent(s, party)
    with pytest.raises(QuotesError) as e:
        decisions.reject_quote(s, qid, channel=Channel.STAFF, reason="  ")
    assert code(e) == "motivo_obrigatorio"
    decisions.reject_quote(s, qid, channel=Channel.PUBLIC_LINK)                    # the customer may decline silently


# ─── convert-on-accept ───────────────────────────────────────────────────────


def test_goods_hand_off_as_an_order_and_the_handler_gets_plain_data(db, s, party):
    handler = FakeQuoteAcceptHandler()
    qid = sent(s, party)
    out = public_accept(s, qid, handler=handler)
    assert (out["quote"]["conversion_status"], out["quote"]["conversion_kind"], out["quote"]["conversion_ref"]) == ("done", "order", f"fake-order-{qid}")
    (ctx,) = handler.calls
    assert isinstance(ctx, QuoteAcceptContext) and ctx.convert_to == "order" and ctx.org_id == ORG_A
    assert ctx.quote["id"] == qid and ctx.quote["total_cents"] == 20000 and ctx.lines[0]["description"] == "Serviço de instalação"
    assert ctx.acceptance["signer_name"] == "Ana Souza" and not hasattr(ctx, "db")
    assert [e["kind"] for e in db.table("quo_events").select("*").execute().data][-2:] == ["accepted", "converted"]


def test_services_hand_off_as_a_contract(s, party):
    handler = FakeQuoteAcceptHandler()
    qid = sent(s, party, lines=[line(kind="service")])
    assert public_accept(s, qid, handler=handler)["quote"]["conversion_kind"] == "contract"


def test_nothing_to_convert_never_calls_the_handler(s, party):
    handler = FakeQuoteAcceptHandler()
    for over in ({"convert_to": "none"}, {"lines": [line(kind="goods"), line(kind="service")]}):
        qid = sent(s, party, **over)
        out = public_accept(s, qid, handler=handler)
        assert out["quote"]["conversion_status"] == "none"
    assert handler.calls == []


def test_default_noop_handler_marks_the_conversion_skipped(s, party):
    out = public_accept(s, sent(s, party))
    assert out["quote"]["conversion_status"] == "skipped" and out["quote"].get("conversion_ref") is None
    assert isinstance(NoopQuoteAcceptHandler().handle(None), type(None))   # type: ignore[arg-type]


def test_a_failing_handler_never_undoes_the_acceptance_and_is_retryable(db, s, party):
    handler = FakeQuoteAcceptHandler(raises=ConnectionError("commerce down"))
    qid = sent(s, party)
    out = public_accept(s, qid, handler=handler)
    q = out["quote"]
    assert q["status"] == "accepted" and q["conversion_status"] == "failed" and "commerce down" in q["conversion_error"]
    assert [e["kind"] for e in db.table("quo_events").select("*").execute().data][-1] == "conversion_failed"
    handler.raises = None
    healed = decisions.convert_quote(s, qid, handler)
    assert (healed["conversion_status"], healed["conversion_error"]) == ("done", None)
    n = len(handler.calls)
    assert decisions.convert_quote(s, qid, handler)["conversion_status"] == "done" and len(handler.calls) == n   # done is final


def test_convert_needs_an_accepted_quote_and_a_real_handler(s, party):
    qid = sent(s, party)
    with pytest.raises(QuotesError) as e:
        decisions.convert_quote(s, qid, FakeQuoteAcceptHandler())
    assert code(e) == "transicao_invalida"
    public_accept(s, qid)                                                          # no handler wired -> skipped
    with pytest.raises(QuotesError) as e:
        decisions.convert_quote(s, qid, NoopQuoteAcceptHandler())
    assert code(e) == "conversao_indisponivel"
    assert decisions.convert_quote(s, qid, FakeQuoteAcceptHandler())["conversion_status"] == "done"   # wired later: heals


def test_handler_may_decline_by_returning_none(s, party):
    class Declines:
        def handle(self, ctx):
            return None

    assert public_accept(s, sent(s, party), handler=Declines())["quote"]["conversion_status"] == "skipped"
    assert QuoteConversion("order", "x").detail == {}
