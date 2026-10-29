"""`ClientsService` against both stores: CRUD, booking lifecycle, payments, schedules, summary, lead conversion."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from noctusai_lib.domain.clients import (
    CLIENTE_COM_FINANCEIRO,
    SESSAO_COM_PAGAMENTO,
    VALOR_EXCEDE_ABERTO,
    ClientFilters,
    ClientsError,
    ClientsService,
    FakeClientsStore,
)
from noctusai_lib.primitives.exceptions import NotFoundError

from .conftest import ACCOUNT, CFG, ORG_A, ORG_B, T0, VALID_CPF


def _client(svc, **kw):
    return svc.create(ORG_A, {"name": "Ana", **kw}, is_admin=True)


def _at(day: date, hh: int, mm: int = 0) -> datetime:
    """A São Paulo wall-clock instant (UTC-3, no DST in 2026)."""
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=timezone(timedelta(hours=-3)))


def _code(exc_info) -> str:
    return exc_info.value.code


# -- clients ----------------------------------------------------------------------------------------


def test_create_normalizes_and_masks(svc):
    c = svc.create(ORG_A, {"name": "  Ana ", "phone": "(11) 99457-3387", "doc": "529.982.247-25", "tags": ["a", " a", "b"]})
    assert c["name"] == "Ana" and c["phone"] == "+5511994573387" and c["status"] == "ativo"
    assert c["doc"] == "***.982.247-**" and c["tags"] == ["a", "b"] and c["started_at"] == "2026-11-02"
    assert svc.get(ORG_A, c["id"], is_admin=True)["doc"] == VALID_CPF
    assert c["summary"] == {"next_session_at": None, "last_session_at": None, "sessions_done": 0,
                            "open_cents": 0, "overdue_cents": 0, "paid_cents": 0}


@pytest.mark.parametrize("data, code", [
    ({"name": "x", "status": "vip"}, "status_invalido"),
    ({"name": "x", "phone": "12"}, "telefone_invalido"),
    ({"name": "x", "doc": "11111111111"}, "documento_invalido"),
    ({"name": "  "}, "nome_obrigatorio"),
])
def test_create_validation(svc, data, code):
    with pytest.raises(ClientsError) as e:
        svc.create(ORG_A, data)
    assert _code(e) == code


def test_update_and_org_isolation(svc):
    c = _client(svc)
    assert svc.update(ORG_A, c["id"], {"status": "pausado", "notes": "x"})["status"] == "pausado"
    with pytest.raises(NotFoundError):
        svc.get(ORG_B, c["id"])
    with pytest.raises(NotFoundError):
        svc.update(ORG_B, c["id"], {"name": "y"})
    with pytest.raises(NotFoundError):
        svc.create_session(ORG_B, c["id"], {"starts_at": _at(date(2026, 11, 3), 10)})


def test_list_filters_tags_and_order(svc):
    for name, tags, status in (("bia", ["x"], "ativo"), ("Ana", ["y"], "pausado"), ("Caio", ["x", "z"], "ativo")):
        svc.create(ORG_A, {"name": name, "tags": tags, "status": status})
    svc.create(ORG_B, {"name": "Outro", "tags": ["w"]})
    rows, nxt = svc.list_clients(ORG_A, ClientFilters(), limit=2)
    assert nxt == 2 and len(rows) == 2
    assert svc.tags(ORG_A) == ["x", "y", "z"]
    assert [r["name"] for r in svc.list_clients(ORG_A, ClientFilters(tag="x"))[0]] and all(
        "x" in r["tags"] for r in svc.list_clients(ORG_A, ClientFilters(tag="x"))[0]
    )
    assert {r["name"] for r in svc.list_clients(ORG_A, ClientFilters(status="pausado"))[0]} == {"Ana"}


def test_search_by_name_and_phone_digits(booking, clock):
    svc = ClientsService(FakeClientsStore(), CFG, booking, clock=clock)
    svc.create(ORG_A, {"name": "Ana Souza", "phone": "11 99457-3387"})
    svc.create(ORG_A, {"name": "Bruno"})
    assert [r["name"] for r in svc.list_clients(ORG_A, ClientFilters(q="souz"))[0]] == ["Ana Souza"]
    assert [r["name"] for r in svc.list_clients(ORG_A, ClientFilters(q="(11) 99457"))[0]] == ["Ana Souza"]


def test_list_summary_is_batched_not_per_client(booking, clock):
    class Counting(FakeClientsStore):
        calls = 0

        def sessions_of_clients(self, org_id, client_ids):
            Counting.calls += 1
            return super().sessions_of_clients(org_id, client_ids)

    store = Counting()
    svc = ClientsService(store, CFG, booking, clock=clock)
    for n in "abcde":
        c = svc.create(ORG_A, {"name": n, "default_price_cents": 10000})
        svc.create_session(ORG_A, c["id"], {"starts_at": _at(date(2026, 10, 30), 10), "status": "realizada"})
    Counting.calls = 0
    rows, _ = svc.list_clients(ORG_A, ClientFilters(), limit=50)
    assert Counting.calls == 1 and all(r["summary"]["open_cents"] == 10000 for r in rows)


# -- booking lifecycle -------------------------------------------------------------------------------


def _entry(booking, entry_id):
    return next(e for e in booking.entries.values() if e["id"] == entry_id)


def test_billable_session_books_a_receivable(svc, booking):
    c = _client(svc, doc=VALID_CPF)
    s = svc.create_session(ORG_A, c["id"], {"starts_at": _at(date(2026, 10, 28), 14, 30), "status": "realizada", "price_cents": 20000})
    e = _entry(booking, s["entry_id"])
    assert e["source"] == "external" and e["source_ref"] == f"clients:session:{s['id']}"
    assert e["description"] == "Sessão — Ana — 28/10/2026 14:30" and e["amount_cents"] == 20000
    assert e["due_date"] == date(2026, 10, 28) and e["competence_month"] == date(2026, 10, 1)
    assert e["counterparty_name"] == "Ana" and e["counterparty_doc"] == VALID_CPF and e["category_hint"] == "Serviços"
    assert s["payment_status"] == "overdue" and s["starts_at"] == "2026-10-28T14:30:00-03:00"
    fin = svc.client_finance(ORG_A, c["id"])
    assert (fin["open_cents"], fin["overdue_cents"], fin["paid_cents"]) == (20000, 20000, 0)
    assert fin["entries"][0]["session_id"] == s["id"] and fin["entries"][0]["overdue"] is True


@pytest.mark.parametrize("data", [
    {"status": "agendada", "price_cents": 100},      # not a billable status
    {"status": "realizada", "waive_charge": True, "price_cents": 100},
    {"status": "realizada", "price_cents": 0},
    {"status": "realizada"},                          # no session price, no client default
])
def test_non_billable_sessions_book_nothing(svc, booking, data):
    c = _client(svc)
    s = svc.create_session(ORG_A, c["id"], {"starts_at": _at(date(2026, 11, 3), 10), **data})
    assert s["entry_id"] is None and s["payment_status"] == "none" and not booking.entries


def test_client_default_price_is_the_fallback(svc, booking):
    c = _client(svc, default_price_cents=15000)
    s = svc.create_session(ORG_A, c["id"], {"starts_at": _at(date(2026, 11, 3), 10), "status": "falta"})
    assert s["price_cents"] is None and _entry(booking, s["entry_id"])["amount_cents"] == 15000


def test_unbill_cancels_and_rebill_books_fresh(svc, booking):
    c = _client(svc, default_price_cents=10000)
    s = svc.create_session(ORG_A, c["id"], {"starts_at": _at(date(2026, 11, 3), 10)})
    assert s["entry_id"] is None
    s = svc.update_session(ORG_A, s["id"], {"status": "realizada"})
    first = s["entry_id"]
    assert first and _entry(booking, first)["status"] == "open"
    s = svc.update_session(ORG_A, s["id"], {"status": "cancelada"})
    assert s["entry_id"] is None and _entry(booking, first)["status"] == "cancelled"
    s = svc.update_session(ORG_A, s["id"], {"status": "realizada"})
    assert s["entry_id"] not in (None, first)
    assert _entry(booking, s["entry_id"])["source_ref"] == f"clients:session:{s['id']}:1"
    assert svc.client_finance(ORG_A, c["id"])["open_cents"] == 10000  # the cancelled one counts nothing


def test_price_edit_updates_unsettled_and_409s_when_settled(svc, booking):
    c = _client(svc)
    s = svc.create_session(ORG_A, c["id"], {"starts_at": _at(date(2026, 11, 3), 10), "status": "realizada", "price_cents": 10000})
    svc.update_session(ORG_A, s["id"], {"price_cents": 12000})
    assert _entry(booking, s["entry_id"])["amount_cents"] == 12000
    svc.update_session(ORG_A, s["id"], {"notes": "ok"})  # an unrelated edit never touches money
    svc.record_payment(ORG_A, c["id"], {"amount_cents": 5000, "paid_on": date(2026, 11, 2), "account_id": ACCOUNT, "method": "pix"})
    for patch in ({"price_cents": 9000}, {"status": "cancelada"}, {"waive_charge": True}):
        with pytest.raises(ClientsError) as e:
            svc.update_session(ORG_A, s["id"], patch)
        assert _code(e) == SESSAO_COM_PAGAMENTO and e.value.status_code == 409
    assert svc.update_session(ORG_A, s["id"], {"notes": "still editable"})["notes"] == "still editable"
    with pytest.raises(ClientsError) as e:
        svc.delete_session(ORG_A, s["id"])
    assert _code(e) == SESSAO_COM_PAGAMENTO


def test_moving_a_booked_session_moves_its_due_date(svc, booking):
    c = _client(svc)
    s = svc.create_session(ORG_A, c["id"], {"starts_at": _at(date(2026, 11, 3), 10), "status": "realizada", "price_cents": 10000})
    svc.update_session(ORG_A, s["id"], {"starts_at": _at(date(2026, 12, 1), 11)})
    e = _entry(booking, s["entry_id"])
    assert e["due_date"] == date(2026, 12, 1) and e["competence_month"] == date(2026, 12, 1)
    assert e["description"].endswith("01/12/2026 11:00")


def test_delete_unsettled_session_cancels_its_receivable(svc, booking):
    c = _client(svc)
    s = svc.create_session(ORG_A, c["id"], {"starts_at": _at(date(2026, 11, 3), 10), "status": "realizada", "price_cents": 10000})
    svc.delete_session(ORG_A, s["id"])
    assert _entry(booking, s["entry_id"])["status"] == "cancelled"
    with pytest.raises(NotFoundError):
        svc.delete_session(ORG_A, s["id"])


def test_delete_client_refused_with_finance(svc):
    c = _client(svc)
    svc.create_session(ORG_A, c["id"], {"starts_at": _at(date(2026, 11, 3), 10), "status": "realizada", "price_cents": 1})
    with pytest.raises(ClientsError) as e:
        svc.delete(ORG_A, c["id"])
    assert _code(e) == CLIENTE_COM_FINANCEIRO and e.value.status_code == 409
    free = svc.create(ORG_A, {"name": "Sem dinheiro"})
    svc.create_session(ORG_A, free["id"], {"starts_at": _at(date(2026, 11, 3), 10)})
    svc.delete(ORG_A, free["id"])
    with pytest.raises(NotFoundError):
        svc.get(ORG_A, free["id"])


# -- payments ----------------------------------------------------------------------------------------


def _three_sessions(svc):
    c = _client(svc)
    ids = []
    for day, price in ((date(2026, 10, 5), 10000), (date(2026, 10, 12), 10000), (date(2026, 11, 9), 10000)):
        ids.append(svc.create_session(ORG_A, c["id"], {"starts_at": _at(day, 10), "status": "realizada", "price_cents": price})["id"])
    return c, ids


def test_payment_allocates_oldest_due_first(svc, booking):
    c, ids = _three_sessions(svc)
    out = svc.record_payment(ORG_A, c["id"], {"amount_cents": 15000, "paid_on": date(2026, 11, 2), "account_id": ACCOUNT,
                                              "method": "pix", "notes": "parcial"})
    assert len(out["settlement_ids"]) == 2
    fin = out["finance"]
    assert (fin["open_cents"], fin["paid_cents"], fin["overdue_cents"]) == (15000, 15000, 5000)
    by_session = {e["session_id"]: e for e in fin["entries"]}
    assert by_session[ids[0]]["status"] == "paid" and by_session[ids[1]]["status"] == "partial"
    assert [e["due_date"] for e in fin["entries"]] == ["2026-11-09", "2026-10-12", "2026-10-05"]  # newest first
    assert {st["method"] for st in booking.settlements.values()} == {"pix"}
    assert {st["account_id"] for st in booking.settlements.values()} == {ACCOUNT}
    statuses = {s["id"]: s["payment_status"] for s in svc.client_sessions(ORG_A, c["id"])}
    assert statuses == {ids[0]: "paid", ids[1]: "overdue", ids[2]: "open"}


def test_payment_record_keeps_method_notes_and_settlements(booking, clock):
    store = FakeClientsStore()
    svc = ClientsService(store, CFG, booking, clock=clock)
    c, _ids = _three_sessions(svc)
    out = svc.record_payment(ORG_A, c["id"], {"amount_cents": 30000, "paid_on": date(2026, 11, 2), "account_id": ACCOUNT,
                                              "method": "dinheiro", "notes": "em espécie"})
    (payment,) = store.tables["payments"].values()
    assert payment["method"] == "dinheiro" and payment["notes"] == "em espécie" and payment["settlement_ids"] == out["settlement_ids"]
    assert out["finance"]["open_cents"] == 0 and out["finance"]["paid_cents"] == 30000


def test_payment_on_chosen_entries_and_refusals(svc):
    c, ids = _three_sessions(svc)
    fin = svc.client_finance(ORG_A, c["id"])
    newest = next(e["entry_id"] for e in fin["entries"] if e["session_id"] == ids[2])
    out = svc.record_payment(ORG_A, c["id"], {"amount_cents": 10000, "paid_on": date(2026, 11, 2), "account_id": ACCOUNT,
                                              "method": "cartao", "entry_ids": [newest]})
    assert next(e for e in out["finance"]["entries"] if e["entry_id"] == newest)["status"] == "paid"
    base = {"paid_on": date(2026, 11, 2), "account_id": ACCOUNT, "method": "pix"}
    for data, code in (
        ({**base, "amount_cents": 20001}, VALOR_EXCEDE_ABERTO),
        ({**base, "amount_cents": 100, "method": "boleto"}, "metodo_invalido"),
        ({**base, "amount_cents": 100, "entry_ids": ["00000000-0000-4000-8000-0000000000aa"]}, "lancamento_invalido"),
        ({**base, "amount_cents": 100, "entry_ids": [newest]}, "lancamento_invalido"),  # already paid
    ):
        with pytest.raises(ClientsError) as e:
            svc.record_payment(ORG_A, c["id"], data)
        assert _code(e) == code and e.value.status_code == 422


def test_payment_with_nothing_open_exceeds(svc):
    c = _client(svc)
    with pytest.raises(ClientsError) as e:
        svc.record_payment(ORG_A, c["id"], {"amount_cents": 1, "paid_on": date(2026, 11, 2), "account_id": ACCOUNT, "method": "pix"})
    assert _code(e) == VALOR_EXCEDE_ABERTO


# -- schedules ---------------------------------------------------------------------------------------


def _sched_sessions(svc, client_id, schedule_id):
    return sorted((s for s in svc.client_sessions(ORG_A, client_id) if s["schedule_id"] == schedule_id), key=lambda s: s["starts_at"])


def test_schedule_materializes_eight_weeks_idempotently(svc):
    c = _client(svc, session_duration_min=45)
    sch = svc.create_schedule(ORG_A, c["id"], {"weekday": 0, "time": "10:00", "price_cents": 18000})
    assert sch["time"] == "10:00" and sch["duration_min"] == 45 and sch["starts_on"] == "2026-11-02"
    got = _sched_sessions(svc, c["id"], sch["id"])
    # today (Mon 02/11) 10:00 local is still ahead of 09:00 now -> 02/11 .. 28/12 = 9 Mondays within today + 8 weeks
    assert got[0]["starts_at"] == "2026-11-02T10:00:00-03:00" and got[-1]["starts_at"] == "2026-12-28T10:00:00-03:00"
    assert len(got) == 9 and all(s["status"] == "agendada" and s["entry_id"] is None for s in got)
    assert svc.top_up(ORG_A) == 0 and len(_sched_sessions(svc, c["id"], sch["id"])) == 9


def test_horizon_rolls_forward_and_deleted_sessions_stay_deleted(svc, clock):
    c = _client(svc)
    sch = svc.create_schedule(ORG_A, c["id"], {"weekday": 2, "time": "18:30"})
    first = _sched_sessions(svc, c["id"], sch["id"])
    svc.delete_session(ORG_A, first[3]["id"])
    clock.at = T0 + timedelta(days=7)
    assert svc.top_up(ORG_A) == 1  # one new Wednesday at the far end; the deleted one is not resurrected
    ids = {s["id"] for s in _sched_sessions(svc, c["id"], sch["id"])}
    assert first[3]["id"] not in ids and len(ids) == len(first)  # -1 deleted, +1 new


def test_schedule_window_caps_generation(svc):
    c = _client(svc)
    sch = svc.create_schedule(ORG_A, c["id"], {"weekday": 4, "time": "08:00", "starts_on": date(2026, 11, 20), "ends_on": date(2026, 12, 4)})
    assert [s["starts_at"][:10] for s in _sched_sessions(svc, c["id"], sch["id"])] == ["2026-11-20", "2026-11-27", "2026-12-04"]
    with pytest.raises(ClientsError) as e:
        svc.create_schedule(ORG_A, c["id"], {"weekday": 1, "time": "08:00", "starts_on": date(2026, 12, 4), "ends_on": date(2026, 12, 1)})
    assert _code(e) == "agenda_invalida"


def test_schedule_edit_rewrites_only_future_untouched_sessions(svc, booking, clock):
    c = _client(svc, default_price_cents=10000)
    sch = svc.create_schedule(ORG_A, c["id"], {"weekday": 0, "time": "10:00"})
    gen = _sched_sessions(svc, c["id"], sch["id"])
    done = svc.update_session(ORG_A, gen[1]["id"], {"status": "realizada"})  # handled + booked
    clock.at = T0 + timedelta(days=1)  # gen[0] (today 10:00) is now in the past
    svc.update_schedule(ORG_A, sch["id"], {"time": "15:00"})
    after = _sched_sessions(svc, c["id"], sch["id"])
    times = {s["id"]: s["starts_at"] for s in after}
    assert times[gen[0]["id"]] == gen[0]["starts_at"]  # past: untouched
    assert times[done["id"]] == gen[1]["starts_at"] and done["entry_id"]  # handled: untouched
    assert all(s["starts_at"].endswith("15:00:00-03:00") for s in after if s["id"] not in (gen[0]["id"], done["id"]))
    # price-only edit rewrites in place (same ids)
    ids = {s["id"] for s in after}
    svc.update_schedule(ORG_A, sch["id"], {"price_cents": 9000})
    again = _sched_sessions(svc, c["id"], sch["id"])
    assert {s["id"] for s in again} == ids
    assert all(s["price_cents"] == 9000 for s in again if s["status"] == "agendada" and s["starts_at"] > "2026-11-03")


def test_deactivate_and_delete_schedule(svc):
    c = _client(svc)
    sch = svc.create_schedule(ORG_A, c["id"], {"weekday": 0, "time": "10:00"})
    gen = _sched_sessions(svc, c["id"], sch["id"])
    kept = svc.update_session(ORG_A, gen[2]["id"], {"status": "cancelada"})
    assert svc.update_schedule(ORG_A, sch["id"], {"active": False})["active"] is False
    assert [s["id"] for s in _sched_sessions(svc, c["id"], sch["id"])] == [kept["id"]]
    assert svc.top_up(ORG_A) == 0
    svc.delete_schedule(ORG_A, sch["id"])
    left = svc.client_sessions(ORG_A, c["id"])
    assert [s["id"] for s in left] == [kept["id"]] and left[0]["schedule_id"] is None
    assert svc.list_schedules(ORG_A, c["id"]) == []


# -- summary + agenda --------------------------------------------------------------------------------


def test_summary(svc):
    c = _client(svc, default_price_cents=10000)
    svc.create_session(ORG_A, c["id"], {"starts_at": _at(date(2026, 10, 20), 10), "status": "realizada"})
    svc.create_session(ORG_A, c["id"], {"starts_at": _at(date(2026, 10, 27), 10), "status": "falta"})
    svc.create_session(ORG_A, c["id"], {"starts_at": _at(date(2026, 11, 1), 10), "status": "cancelada"})
    svc.create_session(ORG_A, c["id"], {"starts_at": _at(date(2026, 11, 5), 16)})
    s = svc.get(ORG_A, c["id"])["summary"]
    assert s["next_session_at"] == "2026-11-05T16:00:00-03:00" and s["last_session_at"] == "2026-10-27T10:00:00-03:00"
    assert (s["sessions_done"], s["open_cents"], s["overdue_cents"], s["paid_cents"]) == (1, 20000, 20000, 0)


def test_agenda_spans_clients_ascending_with_names(svc):
    a, b = _client(svc), svc.create(ORG_A, {"name": "Bia"})
    svc.create_session(ORG_A, b["id"], {"starts_at": _at(date(2026, 11, 4), 9)})
    svc.create_session(ORG_A, a["id"], {"starts_at": _at(date(2026, 11, 3), 23, 30)})  # 02:30 UTC next day
    svc.create_session(ORG_A, a["id"], {"starts_at": _at(date(2026, 11, 10), 9)})
    got = svc.agenda(ORG_A, date(2026, 11, 3), date(2026, 11, 4))
    assert [(s["client_name"], s["starts_at"][:16]) for s in got] == [("Ana", "2026-11-03T23:30"), ("Bia", "2026-11-04T09:00")]
    assert svc.agenda(ORG_B, date(2026, 11, 3), date(2026, 11, 4)) == []
    for start, end in ((date(2026, 11, 5), date(2026, 11, 4)), (date(2026, 1, 1), date(2026, 3, 15))):
        with pytest.raises(ClientsError) as e:
            svc.agenda(ORG_A, start, end)
        assert _code(e) == "filtro_invalido"


# -- lead conversion ---------------------------------------------------------------------------------


def test_ensure_from_lead_is_idempotent(svc):
    lead = {"id": "11111111-1111-4111-8111-111111111111", "name": "Lia", "phone": "+5511994573387",
            "email": "lia@x.com", "tags": ["indicação"], "whatsapp_chat_id": "5511994573387@c.us"}
    first, created = svc.ensure_from_lead(ORG_A, lead)
    again, created_again = svc.ensure_from_lead(ORG_A, {**lead, "name": "Lia renomeada"})
    assert created and not created_again and first["id"] == again["id"]
    assert (first["name"], first["phone"], first["tags"], first["status"], first["whatsapp_chat_id"]) == (
        "Lia", "+5511994573387", ["indicação"], "ativo", "5511994573387@c.us")
    rows, _ = svc.list_clients(ORG_A, ClientFilters(lead_id=lead["id"]))
    assert [r["id"] for r in rows] == [first["id"]]
    other, created_b = svc.ensure_from_lead(ORG_B, lead)
    assert created_b and other["id"] != first["id"]
