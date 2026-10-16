"""Real-DB checks for migration 020 (content_plans + content_plan_items).

REQUIRES migration 020 applied (the tech-lead applies it at integration
time). Every test skips cleanly when the tables are absent or Supabase creds
are unset — the guard probe below.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.realdb


@pytest.fixture(scope="module", autouse=True)
def _require_content_plans(orbity_db):
    try:
        orbity_db.table("content_plans").select("id,creation_mode").limit(1).execute()
        orbity_db.table("content_plan_items").select("id,task_id,post_id").limit(1).execute()
    except Exception as exc:  # noqa: BLE001 — PGRST205/42P01 => not applied yet
        pytest.skip(f"content_plans migration (020) not applied: {type(exc).__name__}")


def _plan(db, org_id, **over):
    return db.table("content_plans").insert(
        {"org_id": org_id, "title": "Nov", "month": "2026-11", **over}
    ).execute().data[0]


def test_defaults_and_roundtrip(orbity_db, test_org_a):
    plan = _plan(orbity_db, test_org_a["id"])
    try:
        assert plan["status"] == "active" and plan["creation_mode"] == "manual"
        item = orbity_db.table("content_plan_items").insert(
            {"org_id": test_org_a["id"], "plan_id": plan["id"], "title": "Reels"}
        ).execute().data[0]
        assert item["status"] == "planned" and item["order_position"] == 0
    finally:
        orbity_db.table("content_plans").delete().eq("id", plan["id"]).execute()


@pytest.mark.parametrize("bad", [
    {"month": "2026-13"}, {"status": "archived"}, {"creation_mode": "imported"},
])
def test_plan_checks_reject_bad_values(orbity_db, test_org_a, bad):
    with pytest.raises(Exception):
        _plan(orbity_db, test_org_a["id"], **bad)


def test_item_checks_and_cascade(orbity_db, test_org_a):
    plan = _plan(orbity_db, test_org_a["id"])
    org = test_org_a["id"]
    try:
        for bad in ({"status": "done"}, {"platform": "myspace"}):
            with pytest.raises(Exception):
                orbity_db.table("content_plan_items").insert(
                    {"org_id": org, "plan_id": plan["id"], "title": "x", **bad}).execute()
        item = orbity_db.table("content_plan_items").insert(
            {"org_id": org, "plan_id": plan["id"], "title": "x"}).execute().data[0]
    finally:
        orbity_db.table("content_plans").delete().eq("id", plan["id"]).execute()
    left = orbity_db.table("content_plan_items").select("id").eq("id", item["id"]).execute().data
    assert left == []  # ON DELETE CASCADE


def test_deleting_task_keeps_item_and_nulls_task_id(orbity_db, test_org_a):
    org = test_org_a["id"]
    plan = _plan(orbity_db, org)
    task = orbity_db.table("tasks").insert({"org_id": org, "title": "t"}).execute().data[0]
    try:
        item = orbity_db.table("content_plan_items").insert({
            "org_id": org, "plan_id": plan["id"], "title": "x",
            "task_id": task["id"], "status": "task_created"}).execute().data[0]
        orbity_db.table("tasks").delete().eq("id", task["id"]).execute()
        row = orbity_db.table("content_plan_items").select("task_id,status") \
            .eq("id", item["id"]).execute().data[0]
        assert row["task_id"] is None
    finally:
        orbity_db.table("content_plans").delete().eq("id", plan["id"]).execute()


def test_rows_invisible_to_anon(orbity_db, anon_fin_db, test_org_a):
    plan = _plan(orbity_db, test_org_a["id"])
    try:
        item = orbity_db.table("content_plan_items").insert(
            {"org_id": test_org_a["id"], "plan_id": plan["id"], "title": "x"}).execute().data[0]
        assert anon_fin_db.table("content_plans").select("id").eq("id", plan["id"]).execute().data == []
        assert anon_fin_db.table("content_plan_items").select("id").eq("id", item["id"]).execute().data == []
    finally:
        orbity_db.table("content_plans").delete().eq("id", plan["id"]).execute()


def test_claim_compare_and_set_lets_exactly_one_winner(orbity_db, test_org_a):
    from app.services.content_plans_service import ContentPlansService
    from uuid import UUID

    org = test_org_a["id"]
    plan = _plan(orbity_db, org)
    try:
        item = orbity_db.table("content_plan_items").insert(
            {"org_id": org, "plan_id": plan["id"], "title": "x"}).execute().data[0]
        svc = ContentPlansService(orbity_db, UUID(org))
        assert svc._claim_item(plan["id"], item["id"]) is True
        assert svc._claim_item(plan["id"], item["id"]) is False
        # a duplicate create_tasks call skips the claimed item and makes no task
        out = svc.create_tasks(plan, [item["id"]])
        assert out["created"] == 0 and out["skipped"] == 1
    finally:
        orbity_db.table("content_plans").delete().eq("id", plan["id"]).execute()
