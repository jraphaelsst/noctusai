"""Quote lifecycle through the service layer: create / edit / items / list / get / delete / versions / expiry / isolation."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from noctusai_lib.domain.quotes import quotes as svc
from noctusai_lib.domain.quotes._common import local_today
from noctusai_lib.domain.quotes.errors import QuotesError
from noctusai_lib.primitives.exceptions import NotFoundError

from .conftest import CFG, ORG_B, line, seed_item, seed_party, tomorrow


@pytest.fixture
def party(db):
    return seed_party(db)


def mk(s, party, **over):
    return svc.create_quote(s, {"party_id": party["id"], "valid_until": tomorrow(), "lines": [line()], **over})


def code(exc):
    return exc.value.code


# ─── create ──────────────────────────────────────────────────────────────────


def test_create_numbers_per_org_and_computes_totals(db, s, s_b, party):
    q = mk(s, party, discount_cents=500, title=" Reforma ")
    assert (q["number"], q["version"], q["status"], q["is_current"]) == ("ORC-00001", 1, "draft", True)
    assert q["root_id"] == q["id"] and q["title"] == "Reforma"
    assert (q["subtotal_cents"], q["discount_cents"], q["total_cents"]) == (20000, 500, 19500)
    assert q["party"]["legal_name"] == "Ana Souza" and q["effective_convert_to"] == "contract"
    assert mk(s, party)["number"] == "ORC-00002"
    other = seed_party(db, ORG_B)
    assert svc.create_quote(s_b, {"party_id": other["id"], "lines": [line()]})["number"] == "ORC-00001"  # sequence is per org


def test_default_validity_and_past_validity_refused(s, party):
    q = svc.create_quote(s, {"party_id": party["id"], "lines": []})
    assert q["valid_until"] == (local_today(CFG) + timedelta(days=CFG.default_valid_days)).isoformat()
    with pytest.raises(QuotesError) as e:
        mk(s, party, valid_until=date.today() - timedelta(days=3))
    assert code(e) == "validade_invalida"


def test_party_must_exist_in_this_org_and_be_active(db, s, party):
    foreign = seed_party(db, ORG_B)
    for pid in (foreign["id"], "11111111-1111-4111-8111-111111111111"):
        with pytest.raises(QuotesError) as e:
            svc.create_quote(s, {"party_id": pid, "lines": []})
        assert code(e) == "cliente_invalido"
    archived = seed_party(db, is_active=False)
    with pytest.raises(QuotesError):
        svc.create_quote(s, {"party_id": archived["id"], "lines": []})


def test_item_lines_default_from_the_item_and_snapshot(db, s, party):
    chair = seed_item(db, name="Cadeira", price_cents=15000, unit="UN")
    work = seed_item(db, name="Montagem", item_type="service", price_cents=8000, unit="H")
    q = svc.create_quote(s, {"party_id": party["id"], "lines": [
        {"item_id": chair["id"], "qty": "2"}, {"item_id": work["id"], "qty": "1.5", "unit_price_cents": 9000, "description": "Montagem especial"}]})
    a, b = q["lines"]
    assert (a["description"], a["unit"], a["kind"], a["unit_price_cents"], a["total_cents"]) == ("Cadeira", "UN", "goods", 15000, 30000)
    assert (b["description"], b["unit"], b["kind"], b["total_cents"]) == ("Montagem especial", "H", "service", 13500)
    assert q["effective_convert_to"] == "none"            # mixed goods + service
    db.table("itm_items").update({"name": "Renomeada", "price_cents": 1}).eq("id", chair["id"]).execute()
    assert svc.get_quote(s, q["id"])["lines"][0]["description"] == "Cadeira"   # snapshot, not a live join


def test_item_of_another_org_or_missing_price_is_refused(db, s, party):
    foreign = seed_item(db, ORG_B)
    with pytest.raises(QuotesError) as e:
        svc.create_quote(s, {"party_id": party["id"], "lines": [{"item_id": foreign["id"], "qty": "1"}]})
    assert code(e) == "item_invalido"
    unpriced = seed_item(db, price_cents=None)
    with pytest.raises(QuotesError) as e:
        svc.create_quote(s, {"party_id": party["id"], "lines": [{"item_id": unpriced["id"], "qty": "1"}]})
    assert code(e) == "linha_invalida"
    with pytest.raises(QuotesError) as e:
        svc.create_quote(s, {"party_id": party["id"], "lines": [{"qty": "1", "unit_price_cents": 1}]})
    assert code(e) == "linha_invalida"


def test_effective_convert_to_derives_unless_explicit(s, party):
    goods = mk(s, party, lines=[line(kind="goods")])
    assert goods["effective_convert_to"] == "order"
    assert mk(s, party, lines=[line(kind="goods")], convert_to="none")["effective_convert_to"] == "none"
    assert mk(s, party, lines=[line(kind="goods")], convert_to="contract")["effective_convert_to"] == "contract"
    assert mk(s, party, lines=[])["effective_convert_to"] == "none"


def test_calculate_is_a_pure_preview(db, s, party):
    out = svc.calculate(s, {"discount_cents": 100, "lines": [line(qty="3", unit_price_cents=250)]})
    assert (out["subtotal_cents"], out["total_cents"]) == (750, 650)
    assert db.table("quo_quotes").select("*").execute().data == [] and db.rpc_calls == []


# ─── edit ────────────────────────────────────────────────────────────────────


def test_update_replaces_lines_and_recomputes(s, party):
    q = mk(s, party)
    out = svc.update_quote(s, q["id"], {"lines": [line(qty="1", unit_price_cents=700), line(description="B", qty="2", unit_price_cents=100)], "discount_cents": 50})
    assert [ln["position"] for ln in out["lines"]] == [0, 1] and out["total_cents"] == 850
    out = svc.update_quote(s, q["id"], {"discount_cents": 0})              # discount-only keeps the stored lines
    assert out["total_cents"] == 900 and len(out["lines"]) == 2
    out = svc.update_quote(s, q["id"], {"notes": "  obs  ", "terms": "  ", "title": "T"})
    assert (out["notes"], out["terms"], out["title"]) == ("obs", None, "T")


def test_update_refuses_a_discount_above_the_subtotal(s, party):
    q = mk(s, party)
    with pytest.raises(QuotesError) as e:
        svc.update_quote(s, q["id"], {"discount_cents": 99_999_99})
    assert code(e) == "desconto_invalido"
    assert svc.get_quote(s, q["id"])["discount_cents"] == 0


def test_only_a_draft_is_editable_or_deletable(s, party):
    q = mk(s, party)
    svc.transition(s, svc.get_row(s, q["id"]), "sent", expect=["draft"])
    with pytest.raises(QuotesError) as e:
        svc.update_quote(s, q["id"], {"title": "x"})
    assert (code(e), e.value.status_code) == ("orcamento_bloqueado", 409)
    with pytest.raises(QuotesError) as e:
        svc.delete_quote(s, q["id"])
    assert code(e) == "orcamento_bloqueado"


def test_delete_draft_keeps_its_history(db, s, party):
    q = mk(s, party)
    svc.delete_quote(s, q["id"], user_id="u")
    with pytest.raises(NotFoundError):
        svc.get_quote(s, q["id"])
    kinds = [e["kind"] for e in db.table("quo_events").select("*").execute().data]
    assert kinds == ["created", "deleted"]


# ─── read / list / isolation ─────────────────────────────────────────────────


def test_foreign_org_id_is_indistinguishable_from_missing(db, s, s_b, party):
    q = mk(s, party)
    with pytest.raises(NotFoundError):
        svc.get_quote(s_b, q["id"])
    for call in (lambda: svc.update_quote(s_b, q["id"], {"title": "x"}), lambda: svc.delete_quote(s_b, q["id"]),
                 lambda: svc.new_version(s_b, q["id"]), lambda: svc.list_events(s_b, q["id"])):
        with pytest.raises(NotFoundError):
            call()


def test_list_filters_pages_and_shows_only_current_versions(s, party):
    a, b = mk(s, party), mk(s, party)
    svc.transition(s, svc.get_row(s, a["id"]), "sent", expect=["draft"])
    v2 = svc.new_version(s, a["id"])
    rows, total, page, size = svc.list_quotes(s)
    assert total == 2 and {r["id"] for r in rows} == {b["id"], v2["id"]}
    rows, total, *_ = svc.list_quotes(s, include_versions=True)
    assert total == 3
    rows, total, *_ = svc.list_quotes(s, status="superseded", include_versions=True)
    assert total == 1 and rows[0]["id"] == a["id"] and rows[0]["party"]["legal_name"] == "Ana Souza"
    assert svc.list_quotes(s, party_id=party["id"])[1] == 2
    assert svc.list_quotes(s, page=1, page_size=1)[0].__len__() == 1
    with pytest.raises(QuotesError):
        svc.list_quotes(s, status="bogus")


def test_list_never_crosses_orgs(db, s, s_b, party):
    mk(s, party)
    assert svc.list_quotes(s_b)[1] == 0


# ─── versions ────────────────────────────────────────────────────────────────


def test_new_version_copies_lines_supersedes_and_shares_the_number(db, s, party):
    q = mk(s, party, discount_cents=100)
    with pytest.raises(QuotesError) as e:                       # a draft is edited in place, not revised
        svc.new_version(s, q["id"])
    assert code(e) == "transicao_invalida"
    svc.transition(s, svc.get_row(s, q["id"]), "viewed", expect=["draft"])
    v2 = svc.new_version(s, q["id"], valid_until=tomorrow() + timedelta(days=9), user_id="u")
    assert (v2["number"], v2["version"], v2["status"], v2["is_current"]) == (q["number"], 2, "draft", True)
    assert v2["root_id"] == q["root_id"] and v2["id"] != q["id"]
    assert [(ln["description"], ln["total_cents"]) for ln in v2["lines"]] == [(ln["description"], ln["total_cents"]) for ln in q["lines"]]
    assert v2["lines"][0]["id"] != q["lines"][0]["id"]
    old = svc.get_row(s, q["id"])
    assert (old["status"], old["is_current"]) == ("superseded", False)
    kinds = [e["kind"] for e in db.table("quo_events").select("*").execute().data]
    assert kinds[-2:] == ["superseded", "versioned"]
    with pytest.raises(QuotesError) as e:                       # the old one is no longer revisable
        svc.new_version(s, q["id"])
    assert code(e) == "orcamento_substituido"


def test_rejected_and_expired_versions_keep_their_status_when_revised(s, party):
    q = mk(s, party)
    svc.transition(s, svc.get_row(s, q["id"]), "rejected", expect=["draft"])
    svc.new_version(s, q["id"])
    old = svc.get_row(s, q["id"])
    assert (old["status"], old["is_current"]) == ("rejected", False)


def test_an_accepted_quote_cannot_be_revised(s, party):
    q = mk(s, party)
    svc.transition(s, svc.get_row(s, q["id"]), "sent", expect=["draft"])
    row = svc.get_row(s, q["id"])
    svc.transition(s, row, "accepted", expect=["sent"], extra={"accepted_at": "2026-10-14T00:00:00+00:00"})
    with pytest.raises(QuotesError) as e:
        svc.new_version(s, q["id"])
    assert code(e) == "transicao_invalida"


# ─── expiry ──────────────────────────────────────────────────────────────────


def _open(s, party, days_ahead):
    q = mk(s, party, valid_until=tomorrow())
    svc.transition(s, svc.get_row(s, q["id"]), "sent", expect=["draft"])
    # age the offer without touching the code under test: the validity column is a draft-time input.
    s.tbl("quotes").update({"valid_until": (date.today() + timedelta(days=days_ahead)).isoformat()}).eq("id", q["id"]).execute()
    return q["id"]


def test_reading_an_open_quote_past_validity_persists_expired(db, s, party):
    qid = _open(s, party, -2)
    got = svc.get_quote(s, qid)
    assert got["status"] == "expired" and got["expired_at"]
    assert svc.get_row(s, qid)["status"] == "expired"
    assert [e["kind"] for e in db.table("quo_events").select("*").execute().data][-1] == "expired"
    assert svc.get_quote(s, qid)["status"] == "expired"                      # idempotent: one event only
    assert sum(1 for e in db.table("quo_events").select("*").execute().data if e["kind"] == "expired") == 1


def test_a_draft_does_not_expire_and_a_future_offer_stays_open(s, party):
    draft = mk(s, party)
    svc.update_quote(s, draft["id"], {"title": "x"})
    assert svc.get_quote(s, draft["id"])["status"] == "draft"
    assert svc.get_quote(s, _open(s, party, +5))["status"] == "sent"


def test_validity_is_judged_in_the_orgs_civil_day(s, party):
    qid = _open(s, party, 0)                                    # valid THROUGH today (local)
    row = svc.get_row(s, qid)
    assert not svc.is_past_validity(s, row)
    day = date.fromisoformat(str(row["valid_until"])[:10])
    next_day = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(days=1)
    assert not svc.is_past_validity(s, row, at=next_day + timedelta(hours=2, minutes=30))   # 23:30 local, still the validity day
    assert svc.is_past_validity(s, row, at=next_day + timedelta(hours=3, minutes=30))       # 00:30 local, next day


def test_expire_due_flips_every_open_past_validity_quote(s, party):
    a, b, c = _open(s, party, -1), _open(s, party, -5), _open(s, party, 3)
    assert svc.expire_due(s) == 2
    assert [svc.get_row(s, i)["status"] for i in (a, b, c)] == ["expired", "expired", "sent"]
    assert svc.expire_due(s) == 0


def test_a_quote_expired_by_a_racing_reader_is_reread_not_clobbered(s, party):
    qid = _open(s, party, -1)
    stale = svc.get_row(s, qid)
    svc.get_quote(s, qid)                                       # another reader flips it first
    assert svc.expire_if_due(s, stale)["status"] == "expired"
