"""FakeRoutineStore invariants (event-in-same-unit), Supabase store plumbing, DDL emission."""
from __future__ import annotations

from uuid import uuid4

import pytest

from noctusai_lib.domain.routines import (
    FakeRoutineStore,
    RoutineConflict,
    RoutineInvalid,
    RoutineNotFound,
    make_routine_store,
    routines_tables_sql,
)
from noctusai_lib.domain.routines.store_supabase import SupabaseRoutineStore, map_db_error

ORG, OTHER, ACTOR = uuid4(), uuid4(), uuid4()
CRON = "0 7 * * *"


def _mk(s, name="news", **kw):
    return s.create_routine(org_id=kw.pop("org", ORG), name=name, cron=CRON, mode="trigger", config={"q": "x"},
                            actor_id=ACTOR)


def _kinds(s, org=ORG, **kw):
    return [e.kind for e in s.list_events(org, **kw)]


def test_create_starts_disabled_with_created_event():
    s = FakeRoutineStore()
    r = _mk(s)
    assert (r.ativo, r.killed, r.mode, dict(r.config)) == (False, False, "trigger", {"q": "x"})
    assert _kinds(s) == ["created"]
    assert s.list_events(ORG)[0].actor_id == ACTOR


def test_create_validates_cron_mode_name_and_uniqueness_per_org():
    s = FakeRoutineStore()
    with pytest.raises(RoutineInvalid):
        s.create_routine(org_id=ORG, name="a", cron="not a cron", mode="trigger", config={}, actor_id=ACTOR)
    with pytest.raises(RoutineInvalid):
        s.create_routine(org_id=ORG, name="a", cron=CRON, mode="auto", config={}, actor_id=ACTOR)
    with pytest.raises(RoutineInvalid):
        s.create_routine(org_id=ORG, name=" ", cron=CRON, mode="trigger", config={}, actor_id=ACTOR)
    _mk(s)
    with pytest.raises(RoutineConflict):
        _mk(s)
    _mk(s, org=OTHER)  # other org ok


def test_edit_emits_edited_and_mode_changed_only_on_real_changes():
    s = FakeRoutineStore()
    r = _mk(s)
    s.update_routine(org_id=ORG, routine_id=r.id, actor_id=ACTOR, cron=CRON, config={"q": "x"})  # no-op
    assert _kinds(s) == ["created"]
    out = s.update_routine(org_id=ORG, routine_id=r.id, actor_id=ACTOR, cron="30 6 * * *",
                           config={"q": "y"}, mode="routine", reason="validated")
    assert (out.cron, out.mode, dict(out.config)) == ("30 6 * * *", "routine", {"q": "y"})
    ev = s.list_events(ORG)
    assert [e.kind for e in ev] == ["created", "edited", "mode_changed"]
    assert ev[1].detail["changed"] == ["cron", "config"]
    assert ev[2].detail == {"from": "trigger", "to": "routine"} and ev[2].reason == "validated"


def test_flips_need_reason_and_record_actor_and_reason():
    s = FakeRoutineStore()
    r = _mk(s)
    with pytest.raises(RoutineInvalid):
        s.set_enabled(org_id=ORG, routine_id=r.id, enabled=True, actor_id=ACTOR, reason=" ")
    assert s.get_routine(ORG, r.id).ativo is False
    s.set_enabled(org_id=ORG, routine_id=r.id, enabled=True, actor_id=ACTOR, reason="validated")
    s.set_enabled(org_id=ORG, routine_id=r.id, enabled=True, actor_id=ACTOR, reason="again")  # idempotent
    s.set_enabled(org_id=ORG, routine_id=r.id, enabled=False, actor_id=ACTOR, reason="pause")
    ev = s.list_events(ORG)
    assert [e.kind for e in ev] == ["created", "enabled", "disabled"]
    assert (ev[1].actor_id, ev[1].reason) == (ACTOR, "validated")


def test_kill_disables_blocks_runnable_and_enable_revives():
    s = FakeRoutineStore()
    r = _mk(s)
    s.set_enabled(org_id=ORG, routine_id=r.id, enabled=True, actor_id=ACTOR, reason="go")
    assert [x.id for x in s.list_runnable()] == [r.id]
    with pytest.raises(RoutineInvalid):
        s.kill(org_id=ORG, routine_id=r.id, actor_id=ACTOR, reason="")
    k = s.kill(org_id=ORG, routine_id=r.id, actor_id=ACTOR, reason="bad output")
    assert (k.killed, k.ativo) == (True, False) and s.list_runnable() == []
    assert _kinds(s)[-1] == "killed"
    s.set_enabled(org_id=ORG, routine_id=r.id, enabled=True, actor_id=ACTOR, reason="fixed")
    assert s.get_routine(ORG, r.id).killed is False and len(s.list_runnable()) == 1


def test_master_switch_default_on_flip_is_event_and_hides_runnable():
    s = FakeRoutineStore()
    r = _mk(s)
    s.set_enabled(org_id=ORG, routine_id=r.id, enabled=True, actor_id=ACTOR, reason="go")
    assert s.master_enabled(ORG) is True
    with pytest.raises(RoutineInvalid):
        s.set_master(org_id=ORG, enabled=False, actor_id=ACTOR, reason="")
    s.set_master(org_id=ORG, enabled=False, actor_id=ACTOR, reason="incident")
    assert s.master_enabled(ORG) is False and s.list_runnable() == []
    last = s.list_events(ORG)[-1]
    assert (last.scope, last.routine_id, last.kind, last.reason) == ("master", None, "disabled", "incident")
    assert s.master_enabled(OTHER) is True  # per org


def test_record_event_only_run_kinds_and_rejected_needs_reason_and_org_scope():
    s = FakeRoutineStore()
    r = _mk(s)
    for kind in ("created", "killed", "bogus"):
        with pytest.raises(RoutineInvalid):
            s.record_event(org_id=ORG, routine_id=r.id, kind=kind, actor_id=ACTOR)
    with pytest.raises(RoutineInvalid):
        s.record_event(org_id=ORG, routine_id=r.id, kind="rejected", actor_id=ACTOR)
    s.record_event(org_id=ORG, routine_id=r.id, kind="run_started", actor_id=ACTOR, detail={"run_id": "1"})
    with pytest.raises(RoutineNotFound):
        s.record_event(org_id=OTHER, routine_id=r.id, kind="run_started", actor_id=ACTOR)


def test_org_scoping_and_event_filters_and_append_only_surface():
    s = FakeRoutineStore()
    r = _mk(s)
    with pytest.raises(RoutineNotFound):
        s.get_routine(OTHER, r.id)
    assert s.list_routines(OTHER) == []
    s.record_event(org_id=ORG, routine_id=r.id, kind="run_started", actor_id=ACTOR)
    assert _kinds(s, kinds=["run_started"]) == ["run_started"]
    assert len(s.list_events(ORG, limit=1)) == 1
    assert not any(hasattr(s, n) for n in ("delete_event", "update_event"))


def test_factory_requires_client_never_degrades_to_fake():
    assert isinstance(make_routine_store("p", use_fake=True), FakeRoutineStore)
    with pytest.raises(RuntimeError):
        make_routine_store("p")
    assert isinstance(make_routine_store("p", client=object()), SupabaseRoutineStore)


def test_supabase_error_mapping():
    assert isinstance(map_db_error(Exception("routines_not_found")), RoutineNotFound)
    assert isinstance(map_db_error(Exception('duplicate key "routines_org_name_key"')), RoutineConflict)
    assert isinstance(map_db_error(Exception("violates routine_events_reason_ck")), RoutineInvalid)


class _Rpc:
    def __init__(self, log, name, params, data):
        self.log, self.name, self.params, self.data = log, name, params, data

    def execute(self):
        self.log.append((self.name, self.params))
        return type("R", (), {"data": self.data})()


def test_supabase_store_calls_the_atomic_functions_and_validates_before_the_round_trip():
    log = []
    rid = uuid4()

    class Client:
        def rpc(self, name, params):
            return _Rpc(log, name, params, str(rid))

        def table(self, name):
            raise AssertionError("reads not needed here")

    st = SupabaseRoutineStore(Client(), schema="p")
    with pytest.raises(RoutineInvalid):
        st.set_enabled(org_id=ORG, routine_id=rid, enabled=False, actor_id=ACTOR, reason="")
    with pytest.raises(RoutineInvalid):
        st.create_routine(org_id=ORG, name="n", cron="bad", mode="trigger", config={}, actor_id=ACTOR)
    assert log == []


def test_ddl_is_per_schema_tiered_append_only_and_locked_down():
    sql = routines_tables_sql("sw_news")
    for t in ("routines", "routine_master_switches", "routine_events"):
        assert f"COMMENT ON TABLE sw_news.{t} IS 'tier:org';" in sql
        assert f"ALTER TABLE sw_news.{t} ENABLE ROW LEVEL SECURITY;" in sql
        assert f"REVOKE ALL ON sw_news.{t} FROM PUBLIC, anon, authenticated;" in sql
    assert "REVOKE UPDATE, DELETE, TRUNCATE ON sw_news.routine_events FROM service_role;" in sql
    assert "BEFORE UPDATE OR DELETE ON sw_news.routine_events" in sql
    for k in ("created", "edited", "mode_changed", "enabled", "disabled", "killed", "run_started",
              "run_finished", "draft_created", "approved", "rejected"):
        assert f"'{k}'" in sql
    for fn in ("routines_create", "routines_update", "routines_set_enabled", "routines_kill", "routines_set_master"):
        assert f"FUNCTION sw_news.{fn}(" in sql
        assert f"REVOKE EXECUTE ON FUNCTION sw_news.{fn}(" in sql
    assert sql.count("SECURITY DEFINER SET search_path = sw_news, pg_temp") == 5
    assert "{" not in sql.replace("'{}'", "")  # no unformatted placeholders left
    with pytest.raises(ValueError):
        routines_tables_sql("bad; drop")
