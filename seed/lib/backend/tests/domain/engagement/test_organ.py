"""Engagement organ: the DDL's guards, the org-scoped ledger (Fake + Real double), the service and the router."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.engagement import (
    EngagementActor,
    EngagementConfig,
    EngagementError,
    EngagementService,
    FakeOrgPointsLedger,
    OrgPointsLedger,
    PointAward,
    build_engagement_store,
    create_engagement_router,
    engagement_migration,
    make_org_points_ledger,
)
from noctusai_lib.primitives.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from noctusai_lib.testing import _schema_cache
from noctusai_lib.testing.migration_parser import parse_sql
from noctusai_lib.testing.mocks import MockSupabaseClient

ORG_A = "5b0e8f7a-1c2d-4e3f-9a8b-7c6d5e4f3a2b"
ORG_B = "9c8d7e6f-5a4b-4c3d-8e2f-1a0b9c8d7e6f"
ADMIN, ANA, BIA = "u-admin", "u-ana", "u-bia"
SCHEMA = "engx"
CFG = EngagementConfig(schema=SCHEMA)
NOW = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)


def test_migration_is_service_only_append_only_and_tiered():
    sql = engagement_migration(CFG)
    for table in ("eng_points", "eng_point_rules", "eng_badge_rules"):
        assert f"COMMENT ON TABLE {SCHEMA}.{table} IS 'tier:org';" in sql
        assert f"REVOKE ALL ON {SCHEMA}.{table} FROM PUBLIC, anon, authenticated;" in sql
    assert "GRANT SELECT" not in sql  # nothing readable by `authenticated`
    assert "RAISE EXCEPTION 'eng_points is append-only'" in sql
    assert "current_setting('engagement.erase_points', true) = 'on'" in sql  # the one gated DELETE path
    assert "REVOKE EXECUTE ON FUNCTION metasx" not in sql
    for fn in ("eng_points_totals(UUID, TEXT[], TIMESTAMPTZ, TIMESTAMPTZ)", "eng_erase_member_points(UUID, TEXT)"):
        assert f"REVOKE EXECUTE ON FUNCTION {SCHEMA}.{fn} FROM PUBLIC, anon, authenticated;" in sql
    assert "sum(g.points)" in sql  # totals are a SQL SUM


# -- ledgers ---------------------------------------------------------------------------------------------------------


@pytest.fixture
def real_schema():
    base = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
    _schema_cache.set_cache_for_tests({**base, **parse_sql(engagement_migration(CFG), source_label="engagement_migration")})
    yield
    _schema_cache.set_cache_for_tests(base)


def _award(member="m1", key="k1", points=5, action="post") -> PointAward:
    return PointAward(member, "platform", action, points, NOW, key)


def test_fake_ledger_is_idempotent_windowed_and_erasable():
    ledger = FakeOrgPointsLedger()
    assert ledger.record(_award()) is True and ledger.record(_award()) is False
    ledger.record(_award(key="k2", points=3))
    assert ledger.totals() == {"m1": 8}
    assert ledger.totals(since=datetime(2026, 2, 1, tzinfo=timezone.utc)) == {}
    assert ledger.erase_member("m1") == 2 and ledger.totals() == {}
    assert ledger.record(_award()) is True  # the key is free again after an erase


def test_real_ledger_records_scopes_by_org_and_translates_only_unique_violations(real_schema):
    client = MockSupabaseClient(validate_schema=True, schema=SCHEMA)
    a, b = OrgPointsLedger(client, CFG, ORG_A), OrgPointsLedger(client, CFG, ORG_B)
    assert a.record(_award()) is True
    assert [x.points for x in a.history("m1")] == [5] and b.history("m1") == []

    class _Boom:
        def table(self, name):
            return self

        def schema(self, name):
            return self

        def insert(self, row):
            return self

        def execute(self):
            raise RuntimeError("connection reset")

    with pytest.raises(RuntimeError):  # a genuine failure is never swallowed as "already recorded"
        OrgPointsLedger(_Boom(), CFG, ORG_A).record(_award())

    class _Dup(_Boom):
        def execute(self):
            err = RuntimeError("duplicate key value violates unique constraint")
            err.code = "23505"
            raise err

    assert OrgPointsLedger(_Dup(), CFG, ORG_A).record(_award()) is False


def test_real_ledger_totals_and_erase_go_through_the_sql_functions():
    calls = []

    class _Rpc:
        def __init__(self, name, params):
            calls.append((name, params))

        def execute(self):
            class R:
                data = [{"member_id": "m1", "points": 8}] if calls[-1][0] == "eng_points_totals" else 2

            return R

    class _Client:
        def rpc(self, name, params):
            return _Rpc(name, params)

    ledger = OrgPointsLedger(_Client(), CFG, ORG_A)
    assert ledger.totals(["m1"], since=NOW) == {"m1": 8}
    assert calls[0] == ("eng_points_totals", {"p_org": ORG_A, "p_members": ["m1"], "p_since": NOW.isoformat()})
    assert ledger.erase_member("m1") == 2 and calls[1] == ("eng_erase_member_points", {"p_org": ORG_A, "p_member": "m1"})
    assert ledger.totals([]) == {}


def test_factories_never_hand_back_a_silent_fake():
    assert isinstance(make_org_points_ledger(CFG, use_fake=True), FakeOrgPointsLedger)
    with pytest.raises(RuntimeError):
        make_org_points_ledger(CFG, org_id=ORG_A)
    with pytest.raises(RuntimeError):
        build_engagement_store(CFG)


# -- service ---------------------------------------------------------------------------------------------------------


@pytest.fixture
def parts():
    ledgers: dict[str, FakeOrgPointsLedger] = {}
    store = build_engagement_store(CFG, use_fake=True)
    svc = EngagementService(store, lambda org: ledgers.setdefault(org, FakeOrgPointsLedger()))
    return svc, store, ledgers


def act(user=ADMIN, admin=True, org=ORG_A) -> EngagementActor:
    return EngagementActor(org, user, admin)


def test_rules_drive_points_caps_idempotency_and_badges(parts):
    svc, _store, _l = parts
    svc.upsert_rule(ORG_A, {"source": "platform", "action": "post", "points": 5, "daily_cap": 8, "period_cap": None})
    svc.upsert_badge(ORG_A, {"badge_id": "poster", "metric": "count:platform.post", "threshold": 2, "label": "Poster"})
    me = act(BIA, False)
    r1 = svc.record(me, {"source": "platform", "action": "post", "idempotency_key": "e1", "occurred_at": NOW})
    assert r1["awards"][0]["points"] == 5 and not r1["duplicate"]
    assert svc.record(me, {"source": "platform", "action": "post", "idempotency_key": "e1", "occurred_at": NOW})["duplicate"] is True
    r3 = svc.record(me, {"source": "platform", "action": "post", "idempotency_key": "e2", "occurred_at": NOW})
    assert r3["awards"][0]["points"] == 3  # clipped by the daily cap (8 - 5)
    assert svc.record(me, {"source": "platform", "action": "unscored", "idempotency_key": "e3"})["awards"] == []
    card = svc.member_card(me)
    assert card["points"] == 8 and [b["earned"] for b in card["badges"]] == [True]
    with pytest.raises(EngagementError) as e:
        svc.record(me, {"member_id": ANA, "source": "platform", "action": "post", "idempotency_key": "e9"})
    assert e.value.code == "sem_permissao"


def test_rule_validation_uses_the_domain_value_objects(parts):
    svc, _s, _l = parts
    with pytest.raises(EngagementError) as e:
        svc.upsert_rule(ORG_A, {"source": "platform", "action": "post", "points": 5, "daily_cap": 10, "period_cap": 4})
    assert e.value.code == "regra_invalida"
    svc.upsert_rule(ORG_A, {"source": "platform", "action": "post", "points": 5})
    svc.upsert_rule(ORG_A, {"source": "platform", "action": "post", "points": 7})  # an update, not a second row
    assert [r["points"] for r in svc.list_rules(ORG_A)] == [7] and svc.list_rules(ORG_B) == []


def test_leaderboard_scope_window_and_lgpd_erase(parts):
    svc, _s, ledgers = parts
    svc.upsert_rule(ORG_A, {"source": "platform", "action": "post", "points": 5})
    for who, n in ((ANA, 3), (BIA, 1)):
        for i in range(n):
            svc.record(act(who, False), {"source": "platform", "action": "post", "idempotency_key": f"{who}{i}", "occurred_at": NOW})
    lb = svc.leaderboard(act(BIA, False), kind="monthly", start=NOW.date().replace(day=1), end=NOW.date().replace(day=28), limit=10)
    assert [(e["member_id"], e["points"], e["rank"]) for e in lb["entries"]] == [(ANA, 15, 1), (BIA, 5, 2)]
    scoped = EngagementService(svc.store, lambda org: ledgers[org], member_scope=lambda a: {a.user_id})
    assert [e["member_id"] for e in scoped.leaderboard(act(BIA, False), kind="monthly", start=NOW.date(), end=NOW.date(), limit=10)["entries"]] == [BIA]
    with pytest.raises(EngagementError):
        svc.erase_member(act(BIA, False), ANA)
    assert svc.erase_member(act(), ANA) == 3
    assert svc.leaderboard(act(), kind="monthly", start=NOW.date(), end=NOW.date(), limit=10)["entries"][0]["member_id"] == BIA


# -- router ----------------------------------------------------------------------------------------------------------


class _Auth(tuple):
    is_admin: bool = False


def _auth(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    who = authorization.split(" ", 1)[1]

    class _User:
        id = {"admin": ADMIN, "bia": BIA}[who]

    a = _Auth((_User(), "tok", ORG_A))
    a.is_admin = who == "admin"
    return a


async def _admin_dep(authorization: Optional[str] = Header(None)):
    a = _auth(authorization)
    if not a.is_admin:
        raise HTTPException(status_code=403, detail="restrito")
    return a


@pytest.fixture
def client():
    store, ledgers = build_engagement_store(CFG, use_fake=True), {}
    router = create_engagement_router(
        _auth, _admin_dep, get_store=lambda: store, get_ledger=lambda org: ledgers.setdefault(org, FakeOrgPointsLedger())
    )
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(router)
    return TestClient(app)


E = "/api/engagement"
ID = "00000000-0000-4000-8000-000000000009"


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/leaderboard"), ("get", "/me"), ("get", "/members/x"), ("delete", "/members/x/points"), ("post", "/events"),
        ("get", "/rules"), ("put", "/rules"), ("delete", f"/rules/{ID}"), ("get", "/badges"), ("put", "/badges"), ("delete", f"/badges/{ID}"),
    ],
)
def test_unauthenticated_is_strictly_401(client, method, path):
    kw = {"json": {}} if method in ("post", "put") else {}
    assert getattr(client, method)(E + path, **kw).status_code == 401


def test_admin_only_routes_are_403_for_a_member(client):
    bia = {"Authorization": "Bearer bia"}
    assert client.put(f"{E}/rules", json={"source": "platform", "action": "x", "points": 1}, headers=bia).status_code == 403
    assert client.put(f"{E}/badges", json={"badge_id": "b", "metric": "points", "threshold": 1}, headers=bia).status_code == 403
    assert client.delete(f"{E}/members/{BIA}/points", headers=bia).status_code == 403
    assert client.get(f"{E}/members/{BIA}", headers=bia).status_code == 403


def test_score_over_http_is_idempotent(client):
    admin, bia = {"Authorization": "Bearer admin"}, {"Authorization": "Bearer bia"}
    assert client.put(f"{E}/rules", json={"source": "platform", "action": "post", "points": 4}, headers=admin).status_code == 200
    body = {"source": "platform", "action": "post", "idempotency_key": "k1"}
    first = client.post(f"{E}/events", json=body, headers=bia)
    assert first.status_code == 201 and first.json()["data"]["awards"][0]["points"] == 4
    assert client.post(f"{E}/events", json=body, headers=bia).status_code == 200
    assert client.get(f"{E}/me", headers=bia).json()["data"]["points"] == 4
    assert client.post(f"{E}/events", json={**body, "extra": 1}, headers=bia).status_code == 422
