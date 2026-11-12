"""The service over the Fake store: rotation, keep-last, capacity, out-of-office, rules, events, card projection, isolation."""
from __future__ import annotations

from datetime import timedelta

import pytest

from noctusai_lib.domain.assignment import AssignmentConfig, AssignmentError, AssignmentService, CapacityFull, Pick
from noctusai_lib.domain.assignment.store import T_ASSIGNMENTS, T_EVENTS
from noctusai_lib.primitives.exceptions import AppException

from .conftest import ADMIN, CARD1, CARD2, CARD3, CARD4, NOW, ORG_A, ORG_B, OUTSIDER, U1, U2, U3, U4, Env


def assign(env: Env, card: str, org: str = ORG_A, **kw) -> dict:
    return env.svc.assign(org, subject_kind="card", subject_id=card, **kw)


def events(env: Env, org: str = ORG_A) -> list[dict]:
    return sorted(env.store.tables.select(T_EVENTS, org), key=lambda e: e["created_at"])


def test_round_robin_rotates_through_the_team_and_records_one_event_each(env):
    env.team("Vendas", [U1, U2, U3])
    picked = [assign(env, c)["user_id"] for c in (CARD1, CARD2, CARD3, CARD4)]
    assert picked == [U1, U2, U3, U1]
    assert [e["event"] for e in events(env)] == ["assigned"] * 4
    assert {e["criterion"] for e in events(env)} == {"round_robin"}


def test_assigning_writes_the_funnel_owner_column_in_the_same_commit(env):
    env.team("Vendas", [U1])
    assign(env, CARD1)
    assert env.card_writes == [(CARD1, U1)]


def test_a_host_without_a_card_table_writes_no_projection():
    env = Env(cfg=AssignmentConfig(schema="asgx"))
    env.team("Vendas", [U1])
    assign(env, CARD1)
    assert env.card_writes == []


def test_assign_is_idempotent_for_the_same_owner_and_writes_no_second_event(env):
    env.team("Vendas", [U1, U2])
    first = assign(env, CARD1)
    again = assign(env, CARD1)  # keep_last: the same person, nothing changed
    assert first["user_id"] == again["user_id"] == U1
    assert again["changed"] is False and again["event"] is None
    assert len(events(env)) == 1


def test_keep_last_off_rotates_a_returning_subject_and_records_a_reassignment():
    env = Env()
    env.team("Vendas", [U1, U2])
    env.svc.put_settings(ORG_A, {"keep_last": False})
    assign(env, CARD1)
    second = assign(env, CARD1)
    assert second["user_id"] == U2 and second["event"] == "reassigned"
    last = events(env)[-1]
    assert (last["event"], last["from_user_id"], last["to_user_id"]) == ("reassigned", U1, U2)


def test_inactive_out_of_office_and_full_members_are_skipped_until_they_are_back(env):
    team = env.team("Vendas", [U1, U2, U3, U4])
    env.svc.update_member(ORG_A, team["id"], U1, {"active": False})
    env.svc.update_member(ORG_A, team["id"], U2, {"ooo_from": (NOW - timedelta(hours=1)).isoformat(), "ooo_until": (NOW + timedelta(days=2)).isoformat()})
    env.svc.update_member(ORG_A, team["id"], U3, {"capacity": 1})
    assert assign(env, CARD1)["user_id"] == U3
    assert assign(env, CARD2)["user_id"] == U4  # U3 is now at capacity
    assert assign(env, CARD3)["user_id"] == U4
    env.clock.advance(days=3)  # U2's absence ended
    assert assign(env, CARD4)["user_id"] == U2


def test_closing_a_subject_frees_the_members_seat_and_keeps_the_owner_as_history(env):
    team = env.team("Vendas", [U1])
    env.svc.update_member(ORG_A, team["id"], U1, {"capacity": 1})
    assign(env, CARD1)
    assert assign(env, CARD2) == {"assigned": False, "reason": "no_available_member", "strategy": "round_robin"}
    env.svc.close(ORG_A, subject_kind="card", subject_id=CARD1, actor_id=ADMIN)
    assert assign(env, CARD2)["user_id"] == U1
    kept = env.svc.get_assignment(ORG_A, "card", CARD1)
    assert kept["user_id"] == U1 and kept["closed_at"] is not None
    assert env.card_writes[-1] == (CARD2, U1)  # closing does not clear the funnel owner


def test_no_candidate_is_an_outcome_recorded_as_an_event_not_an_error(env):
    out = assign(env, CARD1)
    assert out == {"assigned": False, "reason": "no_team", "strategy": "round_robin"}
    (e,) = events(env)
    assert (e["event"], e["criterion"], e["to_user_id"]) == ("no_candidate", "no_team", None)


def test_manual_strategy_assigns_nobody_and_records_no_noise(env):
    env.team("Vendas", [U1])
    env.svc.put_settings(ORG_A, {"strategy": "manual"})
    assert assign(env, CARD1)["reason"] == "manual"
    assert events(env) == []


def test_by_source_routes_a_source_to_its_team_and_others_to_the_default_team(env):
    ads = env.team("Anúncios", [U1])
    base = env.team("Balcão", [U2])
    env.svc.put_rule(ORG_A, kind="source", match_value="meta_ads", team_id=ads["id"])
    env.svc.put_settings(ORG_A, {"strategy": "by_source", "default_team_id": base["id"]})
    assert assign(env, CARD1, source="meta_ads")["user_id"] == U1
    assert assign(env, CARD2, source="portal")["user_id"] == U2
    assert [e["criterion"] for e in events(env)] == ["by_source", "by_source"]


def test_by_unit_is_a_declared_seam_over_a_nullable_org_unit_id(env):
    unit = "77777777-7777-4777-8777-777777777777"
    filial = env.team("Filial Centro", [U3], org_unit_id=unit)
    env.team("Matriz", [U1])
    env.svc.put_settings(ORG_A, {"strategy": "by_unit"})
    out = assign(env, CARD1, org_unit_id=unit)
    assert out["user_id"] == U3 and out["team_id"] == filial["id"]
    (row,) = env.store.tables.select(T_ASSIGNMENTS, ORG_A)
    assert row["org_unit_id"] == unit


def test_a_custom_strategy_registered_by_name_is_selectable_and_recorded_as_custom():
    env = Env(hooks={"by_plantao": lambda snap, ctx: Pick(U2, snap.teams[0].id, "x")})
    env.team("Plantão", [U1, U2])
    assert "by_plantao" in env.svc.get_settings(ORG_A)["custom"]
    env.svc.put_settings(ORG_A, {"strategy": "by_plantao"})
    out = assign(env, CARD1)
    assert out["user_id"] == U2 and out["criterion"] == "custom:by_plantao"


def test_an_unknown_strategy_cannot_be_selected(env):
    with pytest.raises(AssignmentError) as err:
        env.svc.put_settings(ORG_A, {"strategy": "nope"})
    assert err.value.code == "estrategia_invalida" and err.value.status_code == 422


def test_a_hook_named_like_a_builtin_is_refused_at_construction():
    with pytest.raises(ValueError, match="builtin"):
        Env(hooks={"round_robin": lambda s, c: None})


def test_a_manual_reassign_is_recorded_with_who_did_it_and_ignores_capacity(env):
    team = env.team("Vendas", [U1, U2])
    env.svc.update_member(ORG_A, team["id"], U2, {"capacity": 1})
    assign(env, CARD1)  # U1
    env.svc.reassign(ORG_A, subject_kind="card", subject_id=CARD1, to_user_id=U2, actor_id=ADMIN, note="férias")
    env.svc.reassign(ORG_A, subject_kind="card", subject_id=CARD2, to_user_id=U2, actor_id=ADMIN)  # over U2's capacity: a human decided
    moved = [e for e in events(env) if e["event"] == "reassigned"][0]
    assert (moved["from_user_id"], moved["to_user_id"], moved["actor_id"], moved["criterion"], moved["note"]) == (U1, U2, ADMIN, "manual", "férias")
    assert env.card_writes[-1] == (CARD2, U2)


def test_reassign_refuses_a_person_outside_the_org(env):
    env.team("Vendas", [U1])
    with pytest.raises(AssignmentError) as err:
        env.svc.reassign(ORG_A, subject_kind="card", subject_id=CARD1, to_user_id=OUTSIDER)
    assert err.value.code == "membro_invalido"


def test_unassign_clears_the_owner_and_the_funnel_column_and_keeps_the_history(env):
    env.team("Vendas", [U1])
    assign(env, CARD1)
    out = env.svc.unassign(ORG_A, subject_kind="card", subject_id=CARD1, actor_id=ADMIN)
    assert out == {"changed": True, "event": "unassigned"}
    assert env.svc.get_assignment(ORG_A, "card", CARD1) is None
    assert env.card_writes[-1] == (CARD1, None)
    assert [e["event"] for e in events(env)] == ["assigned", "unassigned"]
    assert env.svc.unassign(ORG_A, subject_kind="card", subject_id=CARD1) == {"changed": False, "event": None}


def test_a_user_who_left_the_org_is_not_a_candidate_whatever_a_stale_seat_says(env):
    env.team("Vendas", [U1, U2])
    env.directory.remove(ORG_A, U1)
    assert assign(env, CARD1)["user_id"] == U2
    (team,) = env.svc.list_teams(ORG_A)
    assert [(m["user_id"], m["in_org"], m["unavailable_reason"]) for m in team["members"]][0] == (U1, False, "left_org")


def test_everything_is_scoped_to_the_org(env):
    team_a = env.team("Vendas", [U1])
    env.team("Vendas", [U2], org=ORG_B)  # the same name is free in another org
    assert assign(env, CARD1)["user_id"] == U1
    assert assign(env, CARD1, org=ORG_B)["user_id"] == U2  # same card id, other org: its own assignment
    assert [t["name"] for t in env.svc.list_teams(ORG_B)] == ["Vendas"]
    with pytest.raises(AppException) as err:
        env.svc.get_team(ORG_B, team_a["id"])
    assert err.value.status_code == 404
    with pytest.raises(AppException):
        env.svc.add_member(ORG_B, team_a["id"], U2)
    assert len(events(env, ORG_A)) == 1 and len(events(env, ORG_B)) == 1


def test_team_names_are_unique_per_org_case_insensitively(env):
    env.svc.create_team(ORG_A, name="Vendas")
    with pytest.raises(AssignmentError) as err:
        env.svc.create_team(ORG_A, name=" vendas ")
    assert err.value.code == "equipe_duplicada" and err.value.status_code == 409


def test_a_member_cannot_sit_twice_in_a_team_nor_join_from_outside_the_org(env):
    team = env.team("Vendas", [U1])
    with pytest.raises(AssignmentError) as dup:
        env.svc.add_member(ORG_A, team["id"], U1)
    with pytest.raises(AssignmentError) as out:
        env.svc.add_member(ORG_A, team["id"], OUTSIDER)
    assert (dup.value.code, out.value.code) == ("membro_duplicado", "membro_invalido")


def test_capacity_and_out_of_office_are_validated(env):
    team = env.team("Vendas", [U1])
    for patch in ({"capacity": 0}, {"capacity": -2}, {"ooo_from": NOW.isoformat(), "ooo_until": (NOW - timedelta(days=1)).isoformat()}):
        with pytest.raises(AssignmentError):
            env.svc.update_member(ORG_A, team["id"], U1, patch)
    cleared = env.svc.update_member(ORG_A, team["id"], U1, {"capacity": 3})
    assert cleared["members"][0]["capacity"] == 3
    assert env.svc.update_member(ORG_A, team["id"], U1, {"capacity": None})["members"][0]["capacity"] is None


def test_member_order_defines_the_rotation_and_must_list_exactly_the_members(env):
    team = env.team("Vendas", [U1, U2, U3])
    env.svc.order_members(ORG_A, team["id"], [U3, U1, U2])
    assert [assign(env, c)["user_id"] for c in (CARD1, CARD2, CARD3)] == [U3, U1, U2]
    with pytest.raises(AssignmentError) as err:
        env.svc.order_members(ORG_A, team["id"], [U1, U2])
    assert err.value.code == "ordem_invalida"


def test_removing_a_team_takes_its_rotation_with_it_and_keeps_the_history(env):
    team = env.team("Vendas", [U1])
    assign(env, CARD1)
    env.svc.delete_team(ORG_A, team["id"])
    assert env.svc.list_teams(ORG_A) == []
    assert assign(env, CARD2)["reason"] == "no_team"
    assert env.svc.get_assignment(ORG_A, "card", CARD1)["user_id"] == U1  # the past owner is not rewritten


def test_rules_are_validated_and_upserted_per_kind_and_value(env):
    a, b = env.team("A", [U1]), env.team("B", [U2])
    with pytest.raises(AssignmentError):
        env.svc.put_rule(ORG_A, kind="bogus", match_value="x", team_id=a["id"])
    first = env.svc.put_rule(ORG_A, kind="source", match_value="site", team_id=a["id"])
    again = env.svc.put_rule(ORG_A, kind="source", match_value="site", team_id=b["id"])
    assert first["id"] == again["id"] and again["team_id"] == b["id"]
    assert len(env.svc.list_rules(ORG_A)) == 1


def test_workload_shows_open_subjects_and_availability_per_org_member(env):
    team = env.team("Vendas", [U1, U2])
    env.svc.update_member(ORG_A, team["id"], U2, {"active": False})
    assign(env, CARD1)
    rows = {r["user_id"]: r for r in env.svc.workload(ORG_A)}
    assert rows[U1]["open_count"] == 1 and rows[U1]["available"] is True
    assert rows[U2]["available"] is False and rows[U2]["unavailable_reasons"] == ["inactive"]
    assert rows[ADMIN]["teams"] == [] and rows[ADMIN]["available"] is False


def test_a_concurrent_capacity_loss_is_retried_on_fresh_facts_then_given_up_loudly():
    """Another writer takes U1's last seat between the snapshot and the commit: the loser decides again, never over-assigns."""
    env = Env()
    team = env.team("Vendas", [U1, U2])
    env.svc.update_member(ORG_A, team["id"], U1, {"capacity": 1})

    class RacyLedger:
        """The real ledger's own refusal (capacity checked under a lock), injected once through the ledger seam."""

        def __init__(self, inner):
            self.inner, self.refused = inner, 0

        def commit(self, org_id, row):
            if row["user_id"] == U1 and not self.refused:
                self.refused += 1
                # the competing writer wins U1's last seat first, then this commit is refused by the capacity check
                self.inner.commit(org_id, {**row, "subject_id": CARD2, "enforce_capacity": False, "advance_cursor": False})
                raise CapacityFull("asg_capacity_full")
            return self.inner.commit(org_id, row)

        def release(self, org_id, row):
            return self.inner.release(org_id, row)

    racy = RacyLedger(env.store.ledger)
    svc = AssignmentService(type(env.store)(env.store.tables, racy), env.directory, env.cfg, clock=env.clock)
    out = svc.assign(ORG_A, subject_kind="card", subject_id=CARD1)
    assert racy.refused == 1 and out["user_id"] == U2  # retried: U1 was refused, the rotation moved on to U2


def test_giving_up_after_repeated_capacity_races_is_a_conflict_not_a_silent_miss():
    env = Env()
    env.team("Vendas", [U1])

    class AlwaysFull:
        def commit(self, org_id, row):
            raise CapacityFull("asg_capacity_full")

        def release(self, org_id, row):  # pragma: no cover - not used here
            raise AssertionError

    svc = AssignmentService(type(env.store)(env.store.tables, AlwaysFull()), env.directory, env.cfg, clock=env.clock)
    with pytest.raises(AssignmentError) as err:
        svc.assign(ORG_A, subject_kind="card", subject_id=CARD1)
    assert err.value.code == "capacidade_esgotada" and err.value.status_code == 409


def test_malformed_subject_ids_are_refused_before_any_write(env):
    with pytest.raises(AssignmentError):
        env.svc.assign(ORG_A, subject_kind="card", subject_id="not-a-uuid")
    with pytest.raises(AssignmentError):
        env.svc.assign(ORG_A, subject_kind="Bad Kind!", subject_id=CARD1)
    assert events(env) == []
