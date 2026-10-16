"""
ContentPlansService — read-side via MockSupabaseClient(data=...), write-side
asserted through inserted_payloads / updated_payloads. No patching.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from noctusai_lib.testing import MockSupabaseClient

from app.services.content_plans_service import (
    ContentPlansService,
    PlanReferenceError,
    build_task_description,
    release_stale_claims,
)

ORG = UUID("00000000-0000-0000-0000-000000000001")
PLAN_ID = "11111111-1111-1111-1111-111111111111"
CLIENT_ID = "22222222-2222-2222-2222-222222222222"
TS = "2026-01-01T00:00:00+00:00"


def _plan(**over) -> dict:
    return {"id": PLAN_ID, "org_id": str(ORG), "client_id": CLIENT_ID, "campaign_id": None,
            "title": "Novembro", "month": "2026-11", "strategy_context": {}, "status": "active",
            "creation_mode": "manual", "created_at": TS, "updated_at": TS, **over}


def _item(n: int, **over) -> dict:
    return {"id": f"item-{n}", "org_id": str(ORG), "plan_id": PLAN_ID, "order_position": n,
            "title": f"Item {n}", "description": "Desc", "format": "reels", "platform": "instagram",
            "post_date": "2026-11-10", "due_date": None, "caption": None, "reference_notes": None,
            "status": "planned", "task_id": None, "post_id": None,
            "created_at": TS, "updated_at": TS, **over}


def _svc(**tables):
    db = MockSupabaseClient(schema="orbity")
    for name, rows in tables.items():
        db.set_table_data(name, rows)
    return db, ContentPlansService(db, org_id=ORG)


class TestPlans:
    def test_list_embeds_items_ordered(self):
        _db, svc = _svc(content_plans=[_plan()],
                        content_plan_items=[_item(1), _item(0)])
        out = svc.list_plans()
        assert out["total"] == 1
        assert [i["order_position"] for i in out["items"][0]["items"]] == [0, 1]

    def test_create_plan_stamps_org_and_appends_items_in_order(self):
        db, svc = _svc(content_plans=[_plan()], clients=[{"id": CLIENT_ID, "org_id": str(ORG)}],
                       content_plan_items=[])
        svc.create_plan({"title": "N", "month": "2026-11", "client_id": CLIENT_ID,
                         "items": [{"title": "a"}, {"title": "b"}]})
        plan_payload = db.table("content_plans").inserted_payloads[0]
        assert plan_payload["org_id"] == str(ORG)
        assert "items" not in plan_payload
        items = db.table("content_plan_items").inserted_payloads
        assert [i["order_position"] for i in items] == [0, 1]
        assert all(i["org_id"] == str(ORG) and i["status"] == "planned" for i in items)

    def test_create_plan_rejects_foreign_client(self):
        _db, svc = _svc(content_plans=[_plan()], clients=[])
        with pytest.raises(PlanReferenceError):
            svc.create_plan({"title": "N", "month": "2026-11", "client_id": CLIENT_ID})

    def test_append_continues_after_last_position(self):
        db, svc = _svc(content_plan_items=[_item(0), _item(4)])
        svc.append_items(PLAN_ID, [{"title": "novo", "rogue": "x"}])
        payload = db.table("content_plan_items").inserted_payloads[0]
        assert payload["order_position"] == 5
        assert "rogue" not in payload


class TestDeleteItem:
    def test_item_with_task_is_discarded_and_task_kept(self):
        db, svc = _svc(content_plan_items=[_item(0, task_id="t-1", status="task_created")])
        assert svc.delete_item(PLAN_ID, "item-0") == {"deleted": False, "discarded": True}
        assert db.table("content_plan_items").updated_payloads == [{"status": "discarded"}]
        assert db.table("tasks").updated_payloads == []

    def test_item_without_task_is_hard_deleted(self):
        db, svc = _svc(content_plan_items=[_item(0)])
        assert svc.delete_item(PLAN_ID, "item-0") == {"deleted": True, "discarded": False}
        assert db.table("content_plan_items").updated_payloads == []

    def test_missing_item_returns_none(self):
        _db, svc = _svc(content_plan_items=[])
        assert svc.delete_item(PLAN_ID, "nope") is None


class TestReorder:
    def test_assigns_positions_in_given_order(self):
        db, svc = _svc(content_plan_items=[_item(0), _item(1), _item(2)])
        out = svc.reorder_items(PLAN_ID, ["item-2", "item-0", "item-1"])
        assert [o["id"] for o in out] == ["item-2", "item-0", "item-1"]
        assert [o["order_position"] for o in out] == [0, 1, 2]
        assert {"order_position": 0} in db.table("content_plan_items").updated_payloads

    def test_foreign_ids_rejected(self):
        _db, svc = _svc(content_plan_items=[_item(0)])
        with pytest.raises(PlanReferenceError):
            svc.reorder_items(PLAN_ID, ["item-0", "intruder"])


class TestCreateTasks:
    def test_only_eligible_items_get_tasks(self):
        db, svc = _svc(content_plan_items=[
            _item(0),
            _item(1, task_id="t-old", status="task_created"),
            _item(2, status="discarded"),
        ])
        out = svc.create_tasks(_plan(), ["item-0", "item-1", "item-2"])
        assert out["created"] == 1 and out["skipped"] == 2 and out["failed"] == 0
        tasks = db.table("tasks").inserted_payloads
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Item 0"
        assert tasks[0]["org_id"] == str(ORG)
        assert tasks[0]["client_id"] == CLIENT_ID
        links = db.table("content_plan_items").updated_payloads
        assert links[0] == {"status": "task_pending"}
        assert links[-1]["status"] == "task_created" and links[-1]["task_id"]

    def test_due_date_prefers_item_due_date_then_post_date(self):
        db, svc = _svc(content_plan_items=[
            _item(0, due_date="2026-11-05"), _item(1, due_date=None, post_date="2026-11-12")])
        svc.create_tasks(_plan(), ["item-0", "item-1"])
        due = [t["due_date"] for t in db.table("tasks").inserted_payloads]
        assert due == ["2026-11-05", "2026-11-12"]

    def test_description_carries_caption_and_references(self):
        text = build_task_description(_item(0, caption="Legenda X", reference_notes="Ref Y"))
        assert text.startswith("Desc")
        assert "Legenda sugerida:\nLegenda X" in text
        assert "Referências:\nRef Y" in text
        assert build_task_description({"title": "t"}) is None

    def test_assignee_is_forwarded(self):
        db, svc = _svc(content_plan_items=[_item(0)])
        svc.create_tasks(_plan(), ["item-0"], assignee_user_id="user-9")
        assert db.table("tasks").inserted_payloads[0]["assignee_user_id"] == "user-9"


class TestPromoteToPost:
    def test_creates_draft_post_and_links_item(self):
        db, svc = _svc(content_plan_items=[_item(0, caption="Cap")])
        out = svc.promote_to_post(_plan(campaign_id="camp-1"), "item-0")
        post = db.table("content_posts").inserted_payloads[0]
        assert post["status"] == "draft" and post["platform"] == "instagram"
        assert post["campaign_id"] == "camp-1" and post["client_id"] == CLIENT_ID
        assert post["caption"] == "Cap"
        assert post["scheduled_for"].startswith("2026-11-10T")
        assert out["item_id"] == "item-0"
        assert "post_id" in db.table("content_plan_items").updated_payloads[0]

    def test_item_already_promoted_is_refused(self):
        _db, svc = _svc(content_plan_items=[_item(0, post_id="p-1")])
        with pytest.raises(ValueError):
            svc.promote_to_post(_plan(), "item-0")

    def test_item_without_platform_is_refused(self):
        _db, svc = _svc(content_plan_items=[_item(0, platform=None)])
        with pytest.raises(ValueError):
            svc.promote_to_post(_plan(), "item-0")


class TestClaim:
    def test_claim_precedes_task_creation_and_filters_unclaimed(self):
        db, svc = _svc(content_plan_items=[_item(0)])
        svc.create_tasks(_plan(), ["item-0"])
        updates = db.table("content_plan_items").updated_payloads
        assert updates[0] == {"status": "task_pending"}
        assert updates[1]["status"] == "task_created"

    def test_lost_claim_skips_item_and_creates_no_task(self):
        from noctusai_lib.testing import MockSupabaseResponse

        db = MockSupabaseClient(schema="orbity")
        # 1st execute = items read, 2nd = the claim UPDATE matching 0 rows
        # (another caller already flipped the row).
        db.set_sequential_responses("content_plan_items", [
            MockSupabaseResponse(data=[_item(0)]),
            MockSupabaseResponse(data=[]),
        ])
        out = ContentPlansService(db, org_id=ORG).create_tasks(_plan(), ["item-0"])
        assert out == {"created": 0, "skipped": 1, "failed": 0, "task_ids": []}
        assert db.table("tasks").inserted_payloads == []

    def test_pending_item_is_not_eligible(self):
        db, svc = _svc(content_plan_items=[_item(0, status="task_pending")])
        out = svc.create_tasks(_plan(), ["item-0"])
        assert out["created"] == 0 and out["skipped"] == 1
        assert db.table("tasks").inserted_payloads == []

    def test_failed_task_insert_releases_claim(self):
        from noctusai_lib.testing import MockSupabaseResponse

        db = MockSupabaseClient(schema="orbity")
        db.set_table_data("content_plan_items", [_item(0, status="in_progress")])
        db.set_sequential_responses("tasks", [MockSupabaseResponse(data=[], error="boom")])
        out = ContentPlansService(db, org_id=ORG).create_tasks(_plan(), ["item-0"])
        assert out["failed"] == 1 and out["created"] == 0
        assert {"status": "in_progress"} in db.table("content_plan_items").updated_payloads


class TestStaleClaimSweeper:
    """An item stuck in 'task_pending' with no task (a crash between claim and link) is released after 15 minutes."""

    NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)

    def _ago(self, minutes: int) -> str:
        return (self.NOW - timedelta(minutes=minutes)).isoformat()

    def _status_of(self, db, item_id):
        return next(r["status"] for r in db.table("content_plan_items")._data if r["id"] == item_id)

    def test_only_old_unlinked_claims_go_back_to_planned(self):
        db, _svc_ = _svc(content_plan_items=[
            _item(0, status="task_pending", updated_at=self._ago(16)),                       # abandoned claim
            _item(1, status="task_pending", updated_at=self._ago(5)),                        # a live request holds it
            _item(2, status="task_pending", updated_at=self._ago(60), task_id="t-1"),        # linked: never reverted
            _item(3, status="task_created", updated_at=self._ago(60), task_id="t-3"),
            _item(4, status="discarded", updated_at=self._ago(60)),
            _item(5, status="planned", updated_at=self._ago(60)),
        ])
        assert release_stale_claims(db, now=self.NOW) == 1
        assert [self._status_of(db, f"item-{n}") for n in range(6)] == [
            "planned", "task_pending", "task_pending", "task_created", "discarded", "planned"]

    def test_a_released_item_can_get_its_task_again(self):
        db, svc = _svc(content_plan_items=[_item(0, status="task_pending", updated_at=self._ago(30))])
        assert svc.create_tasks(_plan(), ["item-0"])["skipped"] == 1  # stuck: not eligible
        release_stale_claims(db, now=self.NOW)
        out = svc.create_tasks(_plan(), ["item-0"])
        assert out["created"] == 1 and out["skipped"] == 0

    def test_nothing_to_release_is_zero(self):
        db, _svc_ = _svc(content_plan_items=[_item(0)])
        assert release_stale_claims(db, now=self.NOW) == 0
