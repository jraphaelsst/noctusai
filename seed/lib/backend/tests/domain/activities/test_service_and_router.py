"""Org scoping, auth boundary (strict 401), admin gating, validation, the assignee check and the RPC refusal -> HTTP map."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from noctusai_lib.domain.activities import service
from noctusai_lib.domain.activities.errors import ActivitiesError, from_refusal
from noctusai_lib.primitives.exceptions import NotFoundError

from .conftest import ACT, CFG, ENTITY, MEMBER, ORG_A, ORG_B, STRANGER, USER, row

BASE = "/api/activities"
CREATE = {"entity_kind": "lead", "entity_id": ENTITY, "type_slug": "tarefa", "title": "Ligar"}

# (method, path, json): EVERY route; the count test fails when a new route has no row here.
STAFF_ROUTES = [
    ("GET", f"{BASE}/types", None),
    ("GET", BASE, None),
    ("GET", f"{BASE}/mine", None),
    ("POST", BASE, CREATE),
    ("GET", f"{BASE}/{ACT}", None),
    ("GET", f"{BASE}/{ACT}/events", None),
    ("PATCH", f"{BASE}/{ACT}", {"title": "x"}),
    ("POST", f"{BASE}/{ACT}/complete", {}),
    ("POST", f"{BASE}/{ACT}/reopen", None),
    ("POST", f"{BASE}/{ACT}/reassign", {"assignee_id": MEMBER}),
    ("POST", f"{BASE}/{ACT}/reschedule", {"due_at": "2030-01-01T10:00:00Z"}),
    ("POST", f"{BASE}/{ACT}/cancel", None),
]
ADMIN_ROUTES = [
    ("POST", f"{BASE}/types", {"slug": "visita", "label": "Visita", "kind": "visit"}),
    ("PATCH", f"{BASE}/types/tarefa", {"label": "Tarefa nova"}),
]


def _send(h, method, path, body, headers):
    return h.client.request(method, path, json=body, headers=headers)


def test_every_route_is_covered(h):
    routes = {(m, r.path) for r in h.app.routes if hasattr(r, "methods") for m in r.methods if r.path.startswith(BASE)}
    assert len(routes) == len(STAFF_ROUTES) + len(ADMIN_ROUTES)


@pytest.mark.parametrize("method,path,body", STAFF_ROUTES + ADMIN_ROUTES)
def test_unauthenticated_is_strictly_401(h, method, path, body):
    assert _send(h, method, path, body, {}).status_code == 401


@pytest.mark.parametrize("method,path,body", ADMIN_ROUTES)
def test_staff_cannot_write_activity_types_403(h, method, path, body):
    assert _send(h, method, path, body, h.staff()).status_code == 403


@pytest.mark.parametrize("method,path,body", [r for r in STAFF_ROUTES if r[0] != "GET"])
def test_staff_may_use_every_activity_write(h, method, path, body):
    h.db.set_rpc_data("act_create", {"status": "ok", "activity": row()})
    h.db.set_rpc_data("act_apply", {"status": "ok", "activity": row()})
    h.db.set_rpc_data("act_seed_types", {"status": "ok", "inserted": 0})
    assert _send(h, method, path, body, h.staff()).status_code in (200, 201)


def test_unknown_field_is_422_not_silently_dropped(h):
    r = h.client.post(BASE, json={**CREATE, "org_id": ORG_B}, headers=h.staff())
    assert r.status_code == 422


@pytest.mark.parametrize("patch", [{"entity_kind": "Bad Kind"}, {"title": ""}, {"entity_id": "nope"}, {"type_slug": "X Y"}])
def test_bad_create_body_is_422_before_any_rpc(h, patch):
    r = h.client.post(BASE, json={**CREATE, **patch}, headers=h.staff())
    assert r.status_code == 422 and h.db.rpc_calls == []


# ── types: lazy seed ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_an_empty_org_is_seeded_once_with_the_default_types(s):
    s.db.set_rpc_data("act_seed_types", {"status": "ok", "inserted": 3})
    service.list_types(s)
    (name, params), = s.db.rpc_calls
    assert name == "act_seed_types" and params["p_org"] == ORG_A
    assert [t["slug"] for t in params["p_rows"]] == ["tarefa", "ligacao", "reuniao"]


def test_an_org_that_already_has_types_is_not_reseeded(s):
    s.db.table("act_types").insert({"org_id": ORG_A, "slug": "tarefa", "label": "Tarefa", "kind": "task"}).execute()
    service.list_types(s)
    assert s.db.rpc_calls == []  # an org that deactivated / renamed a type is never overwritten by the preset


def test_the_preset_types_become_the_default_types():
    from noctusai_lib.domain.activities import ActivitiesConfig
    from noctusai_lib.domain.pipeline.market_presets import GENERIC_PRESET, REAL_ESTATE_PRESET

    assert [t.slug for t in ActivitiesConfig.for_preset("x", GENERIC_PRESET).default_types] == ["tarefa", "ligacao", "reuniao"]
    slugs = [t.slug for t in ActivitiesConfig.for_preset("x", REAL_ESTATE_PRESET).default_types]
    assert {"visita", "chave_retirada", "chave_devolucao", "manutencao", "campo"} <= set(slugs)


def test_a_type_is_org_scoped_and_a_bad_kind_is_a_422(h):
    h.db.set_rpc_data("act_seed_types", {"status": "ok", "inserted": 0})
    body = {"slug": "visita", "label": "Visita", "kind": "visit"}
    assert h.client.post(f"{BASE}/types", json=body, headers=h.admin).status_code == 201
    assert h.client.post(f"{BASE}/types", json={**body, "kind": "party"}, headers=h.admin).status_code == 422
    org_b = h.client.get(f"{BASE}/types", headers=h.staff("org-b")).json()["data"]
    assert [t["slug"] for t in org_b if t["slug"] == "visita"] == []


class _DuplicateKeyDb:
    """A db whose `act_types` insert loses the PK race (the mock does not enforce a composite PK; Postgres does: see the PGlite suite)."""

    def __init__(self, inner):
        self._inner = inner

    def table(self, name):
        if name != "act_types":
            return self._inner.table(name)
        inner = self._inner.table(name)

        class _T:
            def select(self, *a, **k):
                return inner.select(*a, **k)

            def insert(self, row):
                class _Q:
                    def execute(self_inner):
                        raise Exception({"code": "23505", "message": 'duplicate key value violates unique constraint "act_types_pkey"'})

                return _Q()

        return _T()

    def rpc(self, name, params=None):
        return self._inner.rpc(name, params)


def test_a_duplicate_type_slug_is_a_409_with_a_stable_code(db):
    db.set_rpc_data("act_seed_types", {"status": "ok", "inserted": 0})
    s_dup = service.Scope(_DuplicateKeyDb(db), CFG, ORG_A)
    db.table("act_types").insert({"org_id": ORG_A, "slug": "x", "label": "X", "kind": "task"}).execute()  # non-empty: no lazy seed
    with pytest.raises(ActivitiesError) as exc:
        service.create_type(s_dup, {"slug": "visita", "label": "Visita", "kind": "visit", "position": 0})
    assert exc.value.code == "tipo_duplicado" and exc.value.status_code == 409


# ── create: assignee + RPC ───────────────────────────────────────────────────────────────────────────────────────────
def test_create_sends_org_actor_and_stringified_ids_to_the_rpc(h):
    h.db.set_rpc_data("act_seed_types", {"status": "ok", "inserted": 0})
    h.db.set_rpc_data("act_create", {"status": "ok", "activity": row(assignee_id=MEMBER)})
    r = h.client.post(BASE, json={**CREATE, "assignee_id": MEMBER, "due_at": "2030-01-01T10:00:00Z"}, headers=h.staff())
    assert r.status_code == 201
    name, params = h.db.rpc_calls[-1]
    assert name == "act_create" and params["p_org"] == ORG_A
    assert params["p_row"]["created_by"] == USER and params["p_row"]["assignee_id"] == MEMBER
    assert params["p_row"]["due_at"].startswith("2030-01-01T10:00:00")


def test_assigning_a_non_member_is_a_422_before_any_rpc(h):
    h.db.set_rpc_data("act_seed_types", {"status": "ok", "inserted": 0})
    r = h.client.post(BASE, json={**CREATE, "assignee_id": STRANGER}, headers=h.staff())
    assert r.status_code == 422 and r.json()["error"]["code"] == "responsavel_invalido"
    assert [n for n, _ in h.db.rpc_calls if n != "act_seed_types"] == []


def test_reassign_checks_membership_and_null_unassigns(h):
    h.db.set_rpc_data("act_apply", {"status": "ok", "activity": row()})
    bad = h.client.post(f"{BASE}/{ACT}/reassign", json={"assignee_id": STRANGER}, headers=h.staff())
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "responsavel_invalido" and h.db.rpc_calls == []
    ok = h.client.post(f"{BASE}/{ACT}/reassign", json={"assignee_id": None}, headers=h.staff())
    assert ok.status_code == 200
    assert h.db.rpc_calls[-1][1]["p_args"] == {"assignee_id": None} and h.db.rpc_calls[-1][1]["p_intent"] == "reatribuir"


def test_a_member_of_another_org_is_not_assignable_here(h):
    # MEMBER belongs to org A only: from org B's session it must be refused
    r = h.client.post(f"{BASE}/{ACT}/reassign", json={"assignee_id": MEMBER}, headers=h.staff("org-b"))
    assert r.status_code == 422


@pytest.mark.parametrize(
    "path,body,intent,args",
    [
        ("complete", {"outcome": "sem_resposta"}, "concluir", {"outcome": "sem_resposta"}),
        ("complete", None, "concluir", {"outcome": "realizada"}),
        ("reopen", None, "reabrir", {}),
        ("cancel", None, "cancelar", {}),
        ("reschedule", {"due_at": None}, "reagendar", {"due_at": None}),
    ],
)
def test_each_intent_reaches_the_rpc_with_its_name_and_the_actor(h, path, body, intent, args):
    h.db.set_rpc_data("act_apply", {"status": "ok", "activity": row()})
    assert h.client.post(f"{BASE}/{ACT}/{path}", json=body, headers=h.staff()).status_code == 200
    name, params = h.db.rpc_calls[-1]
    assert name == "act_apply" and params["p_intent"] == intent and params["p_args"] == args
    assert params["p_actor"] == USER and params["p_org"] == ORG_A and params["p_id"] == ACT


def test_a_bad_outcome_is_a_422_at_the_boundary(h):
    assert h.client.post(f"{BASE}/{ACT}/complete", json={"outcome": "talvez"}, headers=h.staff()).status_code == 422


@pytest.mark.parametrize(
    "code,status",
    [("atividade_encerrada", 409), ("atividade_inexistente", 404), ("desfecho_invalido", 422), ("tipo_invalido", 422), ("titulo_invalido", 422)],
)
def test_rpc_refusals_map_to_stable_codes(h, code, status):
    h.db.set_rpc_data("act_apply", {"status": "refused", "code": code})
    r = h.client.post(f"{BASE}/{ACT}/complete", json={}, headers=h.staff())
    assert r.status_code == status


def test_an_unknown_refusal_code_is_loud_not_swallowed():
    with pytest.raises(RuntimeError):
        from_refusal({"status": "refused", "code": "something_new"})


def test_an_unexpected_rpc_payload_is_loud(s):
    s.db.set_rpc_data("act_apply", {"unexpected": True})
    with pytest.raises(RuntimeError):
        service.cancel(s, ACT, user_id=USER)


# ── reads: org isolation, filters, overdue ───────────────────────────────────────────────────────────────────────────
def _insert(s, **over):
    r = row(**over)
    s.db.table("act_activities").insert(r).execute()
    return r


def test_a_foreign_org_activity_is_a_404_and_its_events_are_unreadable(s, s_b):
    mine = _insert(s)
    with pytest.raises(NotFoundError):
        service.get_activity(s_b, mine["id"])
    with pytest.raises(NotFoundError):
        service.list_events(s_b, mine["id"])
    assert service.list_activities(s_b)[1] == 0


def test_the_default_list_is_the_open_ones_and_status_selects_the_rest(s):
    _insert(s, id="a1000000-0000-4000-8000-000000000001")
    _insert(s, id="a1000000-0000-4000-8000-000000000002", done_at="2026-11-02T10:00:00+00:00", outcome="realizada")
    _insert(s, id="a1000000-0000-4000-8000-000000000003", cancelled_at="2026-11-02T10:00:00+00:00")
    ids = lambda status: sorted(r["id"][-1] for r in service.list_activities(s, status=status)[0])  # noqa: E731
    assert ids("open") == ["1"] and ids("done") == ["2"] and ids("cancelled") == ["3"] and ids("all") == ["1", "2", "3"]
    with pytest.raises(ActivitiesError):
        service.list_activities(s, status="nope")


def test_filters_by_entity_assignee_type_and_kind(s):
    _insert(s, id="a1000000-0000-4000-8000-000000000001", assignee_id=MEMBER)
    _insert(s, id="a1000000-0000-4000-8000-000000000002", entity_id="33333333-3333-4333-8333-333333333333", type_slug="visita", kind="visit")
    only = lambda **kw: [r["id"][-1] for r in service.list_activities(s, **kw)[0]]  # noqa: E731
    assert only(entity_id=ENTITY, entity_kind="lead") == ["1", "2"][:1] or only(entity_id=ENTITY) == ["1"]
    assert only(assignee_id=MEMBER) == ["1"]
    assert only(type_slug="visita") == ["2"] and only(kind="visit") == ["2"]
    with pytest.raises(ActivitiesError):
        service.list_activities(s, kind="party")


def test_overdue_is_derived_on_read_and_never_for_a_finished_one():
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert service.present(row(due_at=past))["overdue"] is True
    assert service.present(row(due_at=future))["overdue"] is False
    assert service.present(row(due_at=None))["overdue"] is False
    assert service.present(row(due_at=past, done_at=past))["overdue"] is False
    assert service.present(row(due_at=past, cancelled_at=past))["overdue"] is False


def test_the_overdue_filter_returns_only_open_past_due_rows(s):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    _insert(s, id="a1000000-0000-4000-8000-000000000001", due_at=past)
    _insert(s, id="a1000000-0000-4000-8000-000000000002", due_at=future)
    _insert(s, id="a1000000-0000-4000-8000-000000000003", due_at=past, done_at=past)
    assert [r["id"][-1] for r in service.list_activities(s, overdue=True)[0]] == ["1"]


def test_mine_lists_only_the_callers_own(h):
    s = service.Scope(h.db, CFG, ORG_A)
    _insert(s, id="a1000000-0000-4000-8000-000000000001", assignee_id=USER)
    _insert(s, id="a1000000-0000-4000-8000-000000000002", assignee_id=MEMBER)
    data = h.client.get(f"{BASE}/mine", headers=h.staff()).json()
    assert [r["id"][-1] for r in data["data"]] == ["1"] and data["pagination"]["total"] == 1


def test_open_activities_are_ordered_by_due_date(s):
    _insert(s, id="a1000000-0000-4000-8000-000000000001", due_at="2030-03-01T10:00:00+00:00")
    _insert(s, id="a1000000-0000-4000-8000-000000000002", due_at="2030-01-01T10:00:00+00:00")
    assert [r["id"][-1] for r in service.list_activities(s)[0]] == ["2", "1"]


def test_events_of_one_activity_come_back_in_order(s):
    _insert(s)
    for i, ev in enumerate(["atividade_criada", "atividade_concluida"], start=1):
        s.db.table("act_events").insert({"id": f"e{i}000000-0000-4000-8000-000000000000", "seq": i, "org_id": ORG_A, "activity_id": ACT, "event": ev, "data": {}}).execute()
    assert [e["event"] for e in service.list_events(s, ACT)] == ["atividade_criada", "atividade_concluida"]


def test_cfg_for_another_schema_is_refused_by_the_mount():
    from noctusai_seed.organs import mount_activities

    with pytest.raises(ValueError):
        mount_activities(schema="other", auth_dependency=lambda: None, get_admin_client=lambda: None, get_core_client=lambda: None, cfg=CFG)
