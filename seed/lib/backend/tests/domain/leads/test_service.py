"""Service behaviour -- runs against the Fake AND the Real (PostgREST double) store."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from noctusai_lib.domain.leads import LeadFilters, LeadsError, ORPHAN_STAGE

from .conftest import CFG, CONN, ORG_A, ORG_B


def mk(svc, name="Ana", org=ORG_A, **kw):
    return svc.create(org, {"name": name, **kw})


def test_create_defaults_and_phone_is_canonical(svc):
    lead = mk(svc, phone="(11) 99457-3387", email="a@x.com")
    assert lead["stage"] == "lead" and lead["origin"] == "outro"
    assert lead["phone"] == "+5511994573387"
    assert lead["first_contact_at"] is not None


def test_create_rejects_unknown_stage_origin_and_bad_phone(svc):
    for bad, code in (({"stage": "x"}, "etapa_invalida"), ({"origin": "x"}, "origem_invalida"), ({"phone": "123"}, "telefone_invalido")):
        with pytest.raises(LeadsError) as e:
            mk(svc, **bad)
        assert e.value.code == code and e.value.status_code == 422


def test_name_is_required(svc):
    with pytest.raises(LeadsError):
        svc.create(ORG_A, {"name": "   "})


def test_update_patch_and_clear_phone(svc):
    lead = mk(svc, phone="11994573387")
    out = svc.update(ORG_A, lead["id"], {"notes": "retornar sexta", "phone": None})
    assert out["notes"] == "retornar sexta" and out["phone"] is None


def test_org_isolation_reads_writes_and_deletes(svc):
    lead = mk(svc)
    for fn in (lambda: svc.get(ORG_B, lead["id"]), lambda: svc.update(ORG_B, lead["id"], {"name": "x"}), lambda: svc.delete(ORG_B, lead["id"]), lambda: svc.move(ORG_B, lead["id"], "fechado")):
        with pytest.raises(Exception) as e:
            fn()
        assert getattr(e.value, "status_code", None) == 404
    assert svc.get(ORG_A, lead["id"])["name"] == "Ana"


def test_delete_removes(svc):
    lead = mk(svc)
    svc.delete(ORG_A, lead["id"])
    with pytest.raises(Exception) as e:
        svc.get(ORG_A, lead["id"])
    assert e.value.status_code == 404


# -- list filters ---------------------------------------------------------------------------------------

@pytest.fixture
def seeded(svc):
    jan = datetime(2026, 1, 10, tzinfo=timezone.utc)
    mar = datetime(2026, 3, 10, tzinfo=timezone.utc)
    mk(svc, "Ana Souza", phone="11994573387", origin="instagram", first_contact_at=jan)
    mk(svc, "Bruno Lima", phone="21988887777", origin="whatsapp", stage="atendimento", first_contact_at=mar, email="bruno@x.com")
    mk(svc, "Carla", origin="indicacao", stage="atendimento", first_contact_at=mar, notes="quer terapia online")
    mk(svc, "Outra Org", org=ORG_B)
    return svc


def names(svc, **f):
    rows, _ = svc.list_leads(ORG_A, LeadFilters(**f), limit=50)
    return sorted(r["name"] for r in rows)


@pytest.mark.parametrize(
    "filters, expected",
    [
        ({}, ["Ana Souza", "Bruno Lima", "Carla"]),
        ({"stage": "atendimento"}, ["Bruno Lima", "Carla"]),
        ({"origin": "instagram"}, ["Ana Souza"]),
        ({"stage": "atendimento", "origin": "whatsapp"}, ["Bruno Lima"]),
        ({"first_from": datetime(2026, 2, 1, tzinfo=timezone.utc)}, ["Bruno Lima", "Carla"]),
        ({"first_to": datetime(2026, 2, 1, tzinfo=timezone.utc)}, ["Ana Souza"]),
        ({"first_from": datetime(2026, 2, 1, tzinfo=timezone.utc), "first_to": datetime(2026, 3, 11, tzinfo=timezone.utc), "stage": "atendimento"}, ["Bruno Lima", "Carla"]),
    ],
)
def test_list_filter_combinations(seeded, filters, expected):
    assert names(seeded, **filters) == expected


# Text search is one rule (`store.matches` == the PostgREST `or_` the Real store sends). The PostgREST double does not
# evaluate `or_()`, so the rule is exercised on the Fake and the Real store's EXPRESSION is pinned in test_store_expression.py.
@pytest.fixture
def seeded_fake():
    from noctusai_lib.domain.leads import FakeLeadsStore, LeadsService

    svc = LeadsService(FakeLeadsStore(), CFG)
    svc.create(ORG_A, {"name": "Ana Souza", "phone": "11994573387", "origin": "instagram"})
    svc.create(ORG_A, {"name": "Bruno Lima", "phone": "21988887777", "origin": "whatsapp", "email": "bruno@x.com"})
    svc.create(ORG_A, {"name": "Carla", "origin": "indicacao", "notes": "quer terapia online"})
    return svc


@pytest.mark.parametrize(
    "q, expected",
    [("souza", ["Ana Souza"]), ("BRUNO@X", ["Bruno Lima"]), ("terapia", ["Carla"]), ("zzz", []), ("Rua 123", [])],
)
def test_text_search_name_email_notes(seeded_fake, q, expected):
    assert names(seeded_fake, q=q) == expected


def test_text_search_combines_with_other_filters(seeded_fake):
    assert names(seeded_fake, q="ana", origin="whatsapp") == []
    assert names(seeded_fake, q="ana", origin="instagram") == ["Ana Souza"]


@pytest.mark.parametrize("typed", ["+5511994573387", "(11) 99457-3387", "11 99457", "994573387", "+55 11 99457-3387"])
def test_search_matches_what_the_user_types_against_the_canonical_phone(seeded_fake, typed):
    assert names(seeded_fake, q=typed) == ["Ana Souza"]


def test_unknown_stage_filter_is_refused(seeded):
    with pytest.raises(LeadsError):
        seeded.list_leads(ORG_A, LeadFilters(stage="nada"))


def test_cursor_pagination_walks_every_lead_once(svc):
    for i in range(7):
        mk(svc, f"L{i}")
    seen, offset = [], 0
    while offset is not None:
        rows, offset = svc.list_leads(ORG_A, LeadFilters(), limit=3, offset=offset)
        seen += [r["id"] for r in rows]
    assert len(seen) == 7 == len(set(seen))


# -- move & board ordering ------------------------------------------------------------------------------

def col(svc, stage):
    return [c["name"] for c in next(c for c in svc.board(ORG_A) if c["etapa"] == stage)["cards"]]


def test_new_leads_stack_on_top_of_the_first_column(svc):
    for n in ("a", "b", "c"):
        mk(svc, n)
    assert col(svc, "lead") == ["c", "b", "a"]


def test_move_between_stages_inserts_at_index_with_one_write(svc):
    a, b, c = (mk(svc, n) for n in "abc")  # lead column: c b a
    svc.move(ORG_A, a["id"], "atendimento", 0)
    svc.move(ORG_A, b["id"], "atendimento", 0)
    svc.move(ORG_A, c["id"], "atendimento", 1)  # between b and a
    assert col(svc, "atendimento") == ["b", "c", "a"]
    assert col(svc, "lead") == []
    before = {x["id"]: x["position"] for x in svc.board(ORG_A)[1]["cards"]}
    svc.move(ORG_A, a["id"], "atendimento", 0)  # reorder inside the column: only `a` changes position
    after = {x["id"]: x["position"] for x in svc.board(ORG_A)[1]["cards"]}
    assert col(svc, "atendimento") == ["a", "b", "c"]
    assert {k for k in before if before[k] != after[k]} == {a["id"]}


def test_move_to_the_end_and_clamped_index(svc):
    a, b = mk(svc, "a"), mk(svc, "b")  # b, a
    svc.move(ORG_A, b["id"], "lead", 99)
    assert col(svc, "lead") == ["a", "b"]


def test_move_stamps_stage_changed_only_when_the_stage_changes(svc):
    a = mk(svc, "a")
    same = svc.move(ORG_A, a["id"], "lead", 0)
    assert same["stage_changed_at"] == a["stage_changed_at"]
    moved = svc.move(ORG_A, a["id"], "fechado", 0)
    assert moved["stage"] == "fechado" and moved["stage_changed_at"] != a["stage_changed_at"]


def test_move_to_unknown_stage_is_refused(svc):
    a = mk(svc, "a")
    with pytest.raises(LeadsError):
        svc.move(ORG_A, a["id"], "nada", 0)


def test_patch_with_a_new_stage_moves_the_lead_to_the_top(svc):
    a, b = mk(svc, "a"), mk(svc, "b")
    svc.move(ORG_A, a["id"], "atendimento", 0)
    svc.update(ORG_A, b["id"], {"stage": "atendimento"})
    assert col(svc, "atendimento") == ["b", "a"]


def test_board_emits_every_stage_with_true_totals_and_respects_filters(svc):
    for i in range(3):
        mk(svc, f"L{i}", origin="instagram")
    mk(svc, "w", origin="whatsapp")
    board = svc.board(ORG_A)
    assert [c["etapa"] for c in board] == list(CFG.stage_slugs)
    assert board[0]["total"] == 4 and board[1]["total"] == 0 and board[1]["cards"] == []
    assert svc.board(ORG_A, LeadFilters(origin="whatsapp"))[0]["total"] == 1


def test_board_total_counts_all_even_when_cards_are_capped(store):
    from dataclasses import replace

    from noctusai_lib.domain.leads import LeadsConfig, LeadsService

    cfg = LeadsConfig(stages=CFG.stages, origins=CFG.origins, board_stage_limit=2)
    s = LeadsService(store, cfg)
    for i in range(5):
        s.create(ORG_A, {"name": f"n{i}"})
    first = s.board(ORG_A)[0]
    assert first["total"] == 5 and first["exibidos"] == 2 and len(first["cards"]) == 2


def test_leads_on_a_removed_stage_show_in_sem_etapa_instead_of_vanishing(store):
    from noctusai_lib.domain.leads import LeadsConfig, LeadsService

    old = LeadsService(store, CFG)
    x = old.create(ORG_A, {"name": "x", "stage": "negociacao"})
    new = LeadsService(store, LeadsConfig(stages=["lead", "fechado"], origins=CFG.origins))
    board = new.board(ORG_A)
    assert board[-1]["etapa"] == ORPHAN_STAGE and [c["id"] for c in board[-1]["cards"]] == [x["id"]]
    assert [r["id"] for r in new.list_leads(ORG_A, LeadFilters(stage=ORPHAN_STAGE))[0]] == [x["id"]]
    new.move(ORG_A, x["id"], "lead", 0)  # and it can be dragged back onto the funnel
    assert new.board(ORG_A)[-1]["etapa"] != ORPHAN_STAGE


# -- whatsapp seam --------------------------------------------------------------------------------------

CHAT = {
    "chat_id": "5511994573387@c.us",
    "name": "Marina",
    "phone": "5511994573387",
    "last_message_preview": "Oi, queria marcar uma conversa",
    "last_message_at": datetime(2026, 10, 1, 12, tzinfo=timezone.utc),
}


def test_upsert_from_whatsapp_creates_the_lead_on_the_first_stage(svc):
    lead = asyncio.run(svc.upsert_from_whatsapp(ORG_A, CONN, CHAT))
    assert lead["origin"] == "whatsapp" and lead["stage"] == "lead"
    assert lead["phone"] == "+5511994573387" and lead["name"] == "Marina"
    assert lead["whatsapp_connection_id"] == CONN and lead["whatsapp_chat_id"] == CHAT["chat_id"]
    assert lead["last_message_preview"].startswith("Oi")


def test_upsert_from_whatsapp_is_idempotent_by_connection_and_chat(svc):
    first = asyncio.run(svc.upsert_from_whatsapp(ORG_A, CONN, CHAT))
    again = asyncio.run(svc.upsert_from_whatsapp(ORG_A, CONN, {**CHAT, "name": "Outro nome"}))
    assert again["id"] == first["id"] and again["name"] == "Marina"
    assert len(svc.list_leads(ORG_A, LeadFilters())[0]) == 1
    other_conn = asyncio.run(svc.upsert_from_whatsapp(ORG_A, "11111111-1111-4111-8111-111111111111", CHAT))
    assert other_conn["id"] != first["id"]


def test_upsert_accepts_an_object_and_a_chat_without_a_resolvable_phone(svc):
    class Chat:
        chat_id = "123@lid"
        name = None
        phone = None
        last_message_preview = None
        last_message_at = None

    lead = asyncio.run(svc.upsert_from_whatsapp(ORG_A, CONN, Chat()))
    assert lead["phone"] is None and lead["name"] == "Contato sem nome"


def test_upsert_survives_a_concurrent_insert_race():
    """Another webhook inserts between our `find` and `insert`: the UNIQUE guard fires and the winner is returned."""
    from noctusai_lib.domain.leads import FakeLeadsStore, LeadsService

    store = FakeLeadsStore()  # the PostgREST double enforces no UNIQUE index; the DB guard is proven in test_sql (PGlite)

    class Racy:
        def __init__(self, inner):
            self.inner, self.raced = inner, False

        def __getattr__(self, name):
            return getattr(self.inner, name)

        def find_by_chat(self, org, conn, chat):
            found = self.inner.find_by_chat(org, conn, chat)
            if not found and not self.raced:
                self.raced = True
                LeadsService(self.inner, CFG).upsert_lead_from_chat(org, conn, CHAT)  # the competing webhook
            return found

    s = LeadsService(Racy(store), CFG)
    lead, created = s.upsert_lead_from_chat(ORG_A, CONN, CHAT)
    assert created is False and len(s.list_leads(ORG_A, LeadFilters())[0]) == 1 and lead["whatsapp_chat_id"] == CHAT["chat_id"]


def test_deleting_a_lead_then_touching_does_not_recreate_it(svc):
    lead = asyncio.run(svc.upsert_from_whatsapp(ORG_A, CONN, CHAT))
    svc.delete(ORG_A, lead["id"])
    assert asyncio.run(svc.touch_last_message(ORG_A, CONN, CHAT["chat_id"], preview="oi")) is None
    assert svc.list_leads(ORG_A, LeadFilters())[0] == []


def test_touch_last_message_updates_the_card_but_never_rewinds_it(svc):
    asyncio.run(svc.upsert_from_whatsapp(ORG_A, CONN, CHAT))
    newer = datetime(2026, 10, 2, tzinfo=timezone.utc)
    got = asyncio.run(svc.touch_last_message(ORG_A, CONN, CHAT["chat_id"], preview="  Posso amanhã?  ", at=newer))
    assert got["last_message_preview"] == "Posso amanhã?"
    late = asyncio.run(svc.touch_last_message(ORG_A, CONN, CHAT["chat_id"], preview="antiga", at=datetime(2026, 9, 1, tzinfo=timezone.utc)))
    assert late["last_message_preview"] == "Posso amanhã?"
