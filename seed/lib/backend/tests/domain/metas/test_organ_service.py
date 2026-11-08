"""MetasService over both stores: periods, teams, goals (3 levels), rules, events, rankings, closings."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from noctusai_lib.domain.metas.errors import MetasError
from noctusai_lib.domain.metas.service import competition_ranks
from noctusai_lib.primitives.exceptions import NotFoundError

from .conftest import ADMIN, ANA, BIA, CAIO, ORG_A, ORG_B, actor

JAN = {"name": "Janeiro", "kind": "monthly", "starts_on": date(2026, 1, 1), "ends_on": date(2026, 1, 31)}


def code(exc: pytest.ExceptionInfo) -> str:
    return exc.value.code


def seeded(svc):
    """Org A: January period, one team (Ana leader, Bia member), default rules."""
    period = svc.create_period(ORG_A, JAN)
    team = svc.create_team(ORG_A, {"name": "Equipe Norte", "leader_id": ANA})
    svc.add_member(ORG_A, team["id"], BIA)
    svc.seed_default_rules(ORG_A)
    return period, team


# -- periods ---------------------------------------------------------------------------------------------------------


def test_period_window_and_parent_are_validated(svc):
    with pytest.raises(MetasError) as e:
        svc.create_period(ORG_A, {**JAN, "ends_on": date(2025, 12, 1)})
    assert code(e) == "periodo_invalido"
    with pytest.raises(MetasError) as e:
        svc.create_period(ORG_A, {**JAN, "kind": "open_ended"})
    assert code(e) == "periodo_invalido"
    quarter = svc.create_period(ORG_A, {"name": "T1", "kind": "quarterly", "starts_on": date(2026, 1, 1), "ends_on": date(2026, 3, 31)})
    child = svc.create_period(ORG_A, {**JAN, "parent_id": quarter["id"]})
    assert child["parent_id"] == quarter["id"]
    with pytest.raises(MetasError):  # a child outside its parent
        svc.create_period(ORG_A, {"name": "Abril", "kind": "monthly", "starts_on": date(2026, 4, 1), "ends_on": date(2026, 4, 30), "parent_id": quarter["id"]})


def test_generate_periods_is_idempotent_and_resolve_picks_the_narrowest(svc):
    first = svc.generate_periods(ORG_A, "monthly", date(2026, 1, 10), date(2026, 3, 5))
    assert [p["starts_on"] for p in first] == ["2026-01-01", "2026-02-01", "2026-03-01"]
    assert svc.generate_periods(ORG_A, "monthly", date(2026, 1, 10), date(2026, 3, 5)) == []
    svc.create_period(ORG_A, {"name": "Semana", "kind": "weekly", "starts_on": date(2026, 2, 2), "ends_on": date(2026, 2, 8)})
    assert svc.resolve_period(ORG_A, date(2026, 2, 3))["kind"] == "weekly"
    assert svc.resolve_period(ORG_A, date(2026, 2, 20))["kind"] == "monthly"
    assert svc.resolve_period(ORG_A, date(2027, 1, 1)) is None


def test_other_org_cannot_see_a_period(svc):
    p = svc.create_period(ORG_A, JAN)
    assert svc.list_periods(ORG_B) == []
    with pytest.raises(NotFoundError):
        svc.get_period(ORG_B, p["id"])


# -- teams -----------------------------------------------------------------------------------------------------------


def test_team_names_are_unique_per_org(svc, unique_enforced):
    svc.create_team(ORG_A, {"name": "Equipe Norte"})
    with pytest.raises(MetasError) as e:
        svc.create_team(ORG_A, {"name": "Equipe Norte"})
    assert code(e) == "equipe_duplicada"
    assert svc.create_team(ORG_B, {"name": "Equipe Norte"})["name"] == "Equipe Norte"  # another org may reuse it


def test_teams_members_history_and_leader_sync(svc):
    _p, team = seeded(svc)
    with pytest.raises(MetasError) as e:
        svc.add_member(ORG_A, team["id"], BIA)
    assert code(e) == "membro_duplicado"
    members = svc.list_members(ORG_A, team["id"])
    assert {m["user_id"]: m["role"] for m in members} == {ANA: "leader", BIA: "member"}
    bia = next(m for m in members if m["user_id"] == BIA)
    svc.remove_member(ORG_A, team["id"], bia["id"])
    assert [m["user_id"] for m in svc.list_members(ORG_A, team["id"])] == [ANA]
    assert len(svc.list_members(ORG_A, team["id"], include_left=True)) == 2  # the history stays
    svc.add_member(ORG_A, team["id"], BIA)  # rejoining after leaving is fine
    svc.disband_team(ORG_A, team["id"])
    assert svc.list_teams(ORG_A) == [] and len(svc.list_teams(ORG_A, include_inactive=True)) == 1
    assert svc.list_members(ORG_A, team["id"]) == []


# -- goals -----------------------------------------------------------------------------------------------------------


def test_goal_levels_permissions_and_uniqueness(svc):
    period, team = seeded(svc)
    owner, member = actor(), actor(user=BIA, admin=False)
    company = svc.create_goal(owner, {"scope": "company", "category": "vgv", "target": 1_000_000, "period_id": period["id"]})
    assert company["starts_on"] == "2026-01-01" and company["subject_id"] is None
    svc.create_goal(owner, {"scope": "team", "subject_id": team["id"], "category": "vgv", "target": 400_000, "period_id": period["id"]})
    with pytest.raises(MetasError) as e:  # a member cannot set team / company goals
        svc.create_goal(member, {"scope": "team", "subject_id": team["id"], "category": "vendas", "target": 3})
    assert code(e) == "sem_permissao"
    mine = svc.create_goal(member, {"scope": "individual", "category": "vgv", "target": 100_000, "period_id": period["id"]})
    assert mine["subject_id"] == BIA
    with pytest.raises(MetasError) as e:  # ...nor an individual goal of someone else
        svc.create_goal(member, {"scope": "individual", "subject_id": CAIO, "category": "pessoal", "target": 3})
    assert code(e) == "sem_permissao"
    leader = actor(user=ANA, admin=False)  # a team leader manages the goals of their members
    assert svc.create_goal(leader, {"scope": "individual", "subject_id": BIA, "category": "vendas", "target": 2, "period_id": period["id"]})["scope"] == "individual"
    with pytest.raises(MetasError) as e:
        svc.create_goal(owner, {"scope": "individual", "category": "nope", "target": 1})
    assert code(e) == "meta_invalida"


def test_goal_is_unique_per_scope_subject_category_and_period(svc, unique_enforced):
    period, team = seeded(svc)
    body = {"scope": "company", "category": "vgv", "target": 1000, "period_id": period["id"]}
    svc.create_goal(actor(), body)
    with pytest.raises(MetasError) as e:
        svc.create_goal(actor(), {**body, "target": 5})
    assert code(e) == "meta_duplicada"
    # another category / another subject / no period at all are different keys
    svc.create_goal(actor(), {**body, "category": "vendas"})
    svc.create_goal(actor(), {"scope": "team", "subject_id": team["id"], "category": "vgv", "target": 1, "period_id": period["id"]})
    svc.create_goal(actor(), {"scope": "company", "category": "vgv", "target": 1})
    svc.create_goal(actor(), {"scope": "company", "category": "vgv", "target": 2})


def test_goal_visibility_and_summary(svc):
    period, _team = seeded(svc)
    owner = actor()
    svc.create_goal(owner, {"scope": "company", "category": "vgv", "target": 1000, "period_id": period["id"]})
    svc.create_goal(owner, {"scope": "individual", "subject_id": BIA, "category": "vgv", "target": 100, "period_id": period["id"]})
    svc.create_goal(owner, {"scope": "individual", "subject_id": CAIO, "category": "vgv", "target": 100, "period_id": period["id"]})
    seen = svc.list_goals(actor(user=CAIO, admin=False))
    assert {(g["scope"], g["subject_id"]) for g in seen} == {("company", None), ("individual", CAIO)}  # not Bia's
    assert len(svc.list_goals(actor(user=ANA, admin=False))) == 2  # company + Bia (Ana leads her team)
    summary = svc.summary(owner, period["id"])
    assert len(summary["company"]) == 1 and len(summary["members"]) == 2 and summary["teams"] == []


def test_manual_goal_contributions_flip_status_and_report_crossings(svc):
    member = actor(user=BIA, admin=False)
    goal = svc.create_goal(member, {"scope": "individual", "category": "pessoal", "target": 100})
    step = svc.contribute(member, goal["id"], 30)
    assert step["realized"] == 30 and step["status"] == "in_progress" and step["crossed_threshold_pct"] == 25.0
    done = svc.contribute(member, goal["id"], 80, note="bônus")
    assert done["completed_now"] and done["status"] == "completed" and done["progress"]["percent_complete"] == 100.0
    g2 = svc.create_goal(actor(), {"scope": "individual", "subject_id": BIA, "category": "vgv", "target": 5})
    with pytest.raises(MetasError) as e:  # an event-fed goal takes no manual contribution
        svc.contribute(actor(), g2["id"], 1)
    assert code(e) == "meta_invalida"


def test_goal_realized_comes_from_events_by_category_source(svc):
    period, _t = seeded(svc)
    owner = actor()
    for who, value in ((BIA, 200_000), (ANA, 300_000)):
        svc.record_event(owner, {"member_id": who, "event_type": "venda", "occurred_on": date(2026, 1, 10), "value": value})
    g_value = svc.create_goal(owner, {"scope": "company", "category": "vgv", "target": 1_000_000, "period_id": period["id"]})
    g_count = svc.create_goal(owner, {"scope": "individual", "subject_id": BIA, "category": "vendas", "target": 2, "period_id": period["id"]})
    g_points = svc.create_goal(owner, {"scope": "individual", "subject_id": ANA, "category": "pontos", "target": 100, "period_id": period["id"]})
    assert svc.get_goal(owner, g_value["id"])["realized"] == 500_000
    assert svc.get_goal(owner, g_count["id"])["realized"] == 1
    assert svc.get_goal(owner, g_points["id"])["realized"] == 50  # one `venda` rule = 50


# -- rules / settings / events ---------------------------------------------------------------------------------------


def test_default_rules_are_seeded_once_and_period_rules_override(svc):
    period, _t = seeded(svc)
    assert svc.seed_default_rules(ORG_A) == []  # idempotent
    ev, created = svc.record_event(actor(), {"member_id": BIA, "event_type": "venda", "occurred_on": date(2026, 1, 5)})
    assert created and ev["points"] == 50 and ev["period_id"] == period["id"]
    svc.upsert_rule(ORG_A, {"event_type": "venda", "points": 80, "period_id": period["id"], "modality": "padrao"})
    ev2, _ = svc.record_event(actor(), {"member_id": BIA, "event_type": "venda", "occurred_on": date(2026, 1, 6)})
    assert ev2["points"] == 80
    half, _ = svc.record_event(actor(), {"member_id": BIA, "event_type": "venda", "modality": "compartilhada", "occurred_on": date(2026, 1, 7), "fraction": 0.5})
    assert half["points"] == 12.5  # 25 * 0.5 (no period rule for this modality: the org-wide one)
    with pytest.raises(MetasError) as e:
        svc.upsert_rule(ORG_A, {"event_type": "ghost", "points": 1})
    assert code(e) == "regra_invalida"


def test_events_dedupe_privacy_and_closed_period(svc):
    period, team = seeded(svc)
    member = actor(user=BIA, admin=False)
    ev, created = svc.record_event(member, {"event_type": "captacao", "occurred_on": date(2026, 1, 3), "dedupe_key": "crm:1"})
    assert created and ev["member_id"] == BIA and ev["team_id"] == team["id"]
    again, created2 = svc.record_event(member, {"event_type": "captacao", "occurred_on": date(2026, 1, 3), "dedupe_key": "crm:1"})
    assert not created2 and again["id"] == ev["id"]
    with pytest.raises(MetasError) as e:  # a member cannot score someone else, nor hand out points
        svc.record_event(member, {"member_id": CAIO, "event_type": "captacao"})
    assert code(e) == "sem_permissao"
    with pytest.raises(MetasError) as e:
        svc.record_event(member, {"event_type": "captacao", "points": 99})
    assert code(e) == "sem_permissao"
    svc.record_event(actor(), {"member_id": CAIO, "event_type": "visita", "occurred_on": date(2026, 1, 4)})
    assert {x["member_id"] for x in svc.list_events(actor())} == {BIA, CAIO}
    assert {x["member_id"] for x in svc.list_events(member)} == {BIA}
    assert {x["member_id"] for x in svc.list_events(actor(user=ANA, admin=False))} == {BIA}  # the leader sees the team
    svc.close_period(actor(), period["id"])
    with pytest.raises(MetasError) as e:
        svc.record_event(actor(), {"member_id": BIA, "event_type": "captacao", "occurred_on": date(2026, 1, 9)})
    assert code(e) == "periodo_fechado"


def test_manual_adjustment_marks_the_event(svc):
    seeded(svc)
    ev, _ = svc.record_event(actor(), {"member_id": BIA, "event_type": "captacao", "occurred_on": date(2026, 1, 3)})
    adj = svc.adjust_event(actor(), ev["id"], {"points": 7, "notes": "ajuste"})
    assert adj["points"] == 7 and adj["manual_adjustment"] is True and adj["adjusted_by"] == ADMIN
    with pytest.raises(MetasError):
        svc.adjust_event(actor(user=BIA, admin=False), ev["id"], {"points": 1})


def test_settings_default_then_saved(svc):
    assert svc.get_settings(ORG_A)["is_default"] is True
    svc.put_settings(ORG_A, {"value_per_point": 5000, "default_ranking_metric": "value"})
    s = svc.put_settings(ORG_A, {"weight_value": 2})
    assert s["value_per_point"] == 5000 and s["weight_value"] == 2 and s["default_ranking_metric"] == "value" and not s["is_default"]
    with pytest.raises(MetasError):
        svc.put_settings(ORG_A, {"value_per_point": 0})


# -- rankings + closings ---------------------------------------------------------------------------------------------


def test_competition_ranks_share_ties():
    assert competition_ranks([("a", 5), ("b", 5), ("c", 3)]) == [("a", 5, 1), ("b", 5, 1), ("c", 3, 3)]


def test_rankings_scoring_privacy_and_metric(svc):
    period, _team = seeded(svc)
    svc.put_settings(ORG_A, {"value_per_point": 100_000, "weight_points": 1, "weight_value": 10})
    o = actor()
    svc.record_event(o, {"member_id": BIA, "event_type": "venda", "occurred_on": date(2026, 1, 5), "value": 200_000})  # 50 pts, 2 vp
    svc.record_event(o, {"member_id": ANA, "event_type": "visita", "occurred_on": date(2026, 1, 5)})  # 0 pts (no rule)
    svc.record_event(o, {"member_id": CAIO, "event_type": "captacao", "occurred_on": date(2026, 1, 5)})  # 1 pt
    r = svc.rankings(o, period_id=period["id"])
    assert r["metric"] == "unified" and r["entries"][0]["member_id"] == BIA
    bia = r["entries"][0]
    assert bia["points"] == 50 and bia["value"] == 200_000 and bia["unified"] == 50 + 2 * 10
    assert svc.rankings(o, period_id=period["id"], metric="value")["entries"][0]["member_id"] == BIA
    # Caio is on no team: he sees only himself; Ana (team) sees her team + herself
    assert [e["member_id"] for e in svc.rankings(actor(user=CAIO, admin=False), period_id=period["id"])["entries"]] == [CAIO]
    assert {e["member_id"] for e in svc.rankings(actor(user=ANA, admin=False), period_id=period["id"])["entries"]} == {ANA, BIA}
    with pytest.raises(MetasError):
        svc.rankings(o, period_id=period["id"], metric="vibes")
    with pytest.raises(MetasError):
        svc.rankings(o)


def test_close_period_is_idempotent_immutable_and_ranks_from_snapshots(svc):
    period, team = seeded(svc)
    o = actor()
    svc.create_goal(o, {"scope": "individual", "subject_id": BIA, "category": "vgv", "target": 150_000, "period_id": period["id"]})
    svc.record_event(o, {"member_id": BIA, "event_type": "venda", "occurred_on": date(2026, 1, 5), "value": 200_000})
    svc.record_event(o, {"member_id": BIA, "event_type": "captacao", "occurred_on": date(2026, 1, 6)})
    snaps, reused = svc.close_period(o, period["id"])
    assert not reused and len(snaps) == 1
    s = snaps[0]
    assert s["member_id"] == BIA and s["team_id"] == team["id"] and s["value_realized"] == 200_000 and s["value_target"] == 150_000
    assert s["activity_points"] == 51 and s["counts"] == {"venda": 1, "captacao": 1} and s["unified_score"] == 51 + 20
    assert svc.get_period(ORG_A, period["id"])["status"] == "closed"
    again, reused2 = svc.close_period(o, period["id"])
    assert reused2 and [x["id"] for x in again] == [s["id"]]
    assert svc.rankings(o, period_id=period["id"])["closed"] is True
    with pytest.raises(MetasError) as e:
        svc.update_period(ORG_A, period["id"], {"name": "x"})
    assert code(e) == "periodo_fechado"
    with pytest.raises(MetasError) as e:
        svc.delete_period(ORG_A, period["id"])
    assert code(e) == "fechamento_existente"
    with pytest.raises(MetasError):
        svc.close_period(actor(user=BIA, admin=False), period["id"])
    assert [c["member_id"] for c in svc.list_closings(actor(user=BIA, admin=False), period["id"])] == [BIA]
    assert svc.list_closings(actor(user=CAIO, admin=False), period["id"]) == []


def test_crash_between_snapshots_and_flip_is_finished_by_a_retry(svc):
    period, _t = seeded(svc)
    svc.record_event(actor(), {"member_id": BIA, "event_type": "captacao", "occurred_on": date(2026, 1, 6)})
    svc.close_period(actor(), period["id"])
    svc.store.update("periods", ORG_A, period["id"], {"status": "review"})  # simulate the flip that never landed
    _snaps, reused = svc.close_period(actor(), period["id"])
    assert reused and svc.get_period(ORG_A, period["id"])["status"] == "closed"


def test_status_is_recomputed_not_trusted(svc):
    seeded(svc)
    today = date.today()
    g = svc.create_goal(actor(), {"scope": "individual", "subject_id": BIA, "category": "pessoal", "target": 10, "starts_on": today - timedelta(days=10), "ends_on": today + timedelta(days=10)})
    assert g["progress"]["status"] == "pending"
    with pytest.raises(MetasError):
        svc.update_goal(actor(), g["id"], {"status": "completed"})
    assert svc.update_goal(actor(), g["id"], {"status": "abandoned"})["progress"]["status"] == "abandoned"
