"""
Content plans service — monthly plans, ordered items, tasks from items,
promotion of an item to a content_post (existing approval flow).

Relationship to the 011 pipeline (reuse, not duplication):
  plan.campaign_id -> content_campaigns   (optional editorial container)
  item.task_id     -> tasks               (production task, TasksService)
  item.post_id     -> content_posts       (draft post that then follows the
                                           unchanged approval flow)

Rules enforced here (the DB only holds the shape):
  * tasks are created ONLY for items with no task_id and not discarded;
  * deleting an item that already has a task is a soft delete (-> discarded,
    task kept); otherwise it is a hard delete;
  * item order is `order_position` (0-based, contiguous per plan).

The Supabase client is user-scoped (RLS enforced). Every query is also
filtered by org_id explicitly. Filtering that the SQL can express is ALSO
re-applied in Python on rows we read back, so correctness never depends on
a single layer. No silent errors: every except logs and re-raises.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from app.services.tasks_service import TasksService

logger = logging.getLogger(__name__)

_ITEM_COLUMNS = (
    "title", "description", "format", "platform", "post_date", "due_date",
    "caption", "reference_notes",
)


#: A claim ('task_pending' with no task yet) older than this was abandoned by a crashed request: the claim is held for
#: the milliseconds between the compare-and-set and the task insert, so 15 minutes is far beyond any live holder.
STALE_CLAIM_MINUTES = 15


def release_stale_claims(db: Any, *, now: datetime | None = None, max_age_minutes: int = STALE_CLAIM_MINUTES) -> int:
    """Release the items stuck in ``task_pending`` (no task linked, untouched for ``max_age_minutes``) back to 'planned'.

    A crash between ``_claim_item`` and the task link leaves the item claimed forever (the claim filters it out of every
    later "Criar tarefas"). Cross-org, one UPDATE: it re-states every predicate (status, ``task_id IS NULL``, age), so an
    item a live request just linked (``task_created``) or touched is never reverted. Returns how many items were released.
    """
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(minutes=max_age_minutes)).isoformat()
    rows = (
        db.table("content_plan_items")
        .update({"status": "planned"})
        .eq("status", "task_pending")
        .is_("task_id", "null")
        .lt("updated_at", cutoff)
        .execute()
        .data
        or []
    )
    if rows:
        logger.warning("content_plans: released %d stale task_pending claim(s)", len(rows))
    return len(rows)


class PlanReferenceError(ValueError):
    """client_id / campaign_id does not belong to the caller's org."""


def build_task_description(item: dict[str, Any]) -> str | None:
    parts = [
        item.get("description"),
        f"Legenda sugerida:\n{item['caption']}" if item.get("caption") else None,
        f"Referências:\n{item['reference_notes']}" if item.get("reference_notes") else None,
    ]
    text = "\n\n".join(p for p in parts if p)
    return text or None


class ContentPlansService:
    def __init__(self, db: Any, org_id: UUID) -> None:
        self._db = db
        self._org_id = str(org_id)

    def _t(self, table: str):
        return self._db.table(table)

    # ------------------------------------------------------------------
    # Internal reads
    # ------------------------------------------------------------------

    def _rows(self, query, op: str) -> list[dict[str, Any]]:
        try:
            return query.execute().data or []
        except Exception:
            logger.exception("content_plans.%s failed org=%s", op, self._org_id)
            raise

    def _items_of(self, plan_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        by_plan: dict[str, list[dict[str, Any]]] = {pid: [] for pid in plan_ids}
        if not plan_ids:
            return by_plan
        rows = self._rows(
            self._t("content_plan_items")
            .select("*")
            .eq("org_id", self._org_id)
            .in_("plan_id", plan_ids)
            .order("order_position", desc=False),
            "items_of",
        )
        for row in rows:
            if str(row.get("plan_id")) in by_plan:
                by_plan[str(row["plan_id"])].append(row)
        for lst in by_plan.values():
            lst.sort(key=lambda r: (r.get("order_position") or 0, str(r.get("created_at") or "")))
        return by_plan

    def _assert_owned(self, table: str, row_id: str | None, label: str) -> None:
        if not row_id:
            return
        query = self._t(table).select("id").eq("org_id", self._org_id).eq("id", str(row_id))
        if table == "clients":
            query = query.is_("deleted_at", "null")  # a deleted client is not assignable
        rows = self._rows(query, f"assert_owned.{table}")
        if not rows:
            raise PlanReferenceError(f"{label} não encontrado")

    def _plan_row(self, plan_id: str) -> dict[str, Any] | None:
        rows = self._rows(
            self._t("content_plans").select("*").eq("org_id", self._org_id).eq("id", plan_id),
            "get_plan",
        )
        return rows[0] if rows else None

    def _next_position(self, plan_id: str) -> int:
        rows = self._items_of([plan_id]).get(plan_id, [])
        return max((int(r.get("order_position") or 0) for r in rows), default=-1) + 1

    # ------------------------------------------------------------------
    # Plans
    # ------------------------------------------------------------------

    def list_plans(
        self,
        client_id: str | None = None,
        month: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        query = (
            self._t("content_plans")
            .select("*")
            .eq("org_id", self._org_id)
            .order("created_at", desc=True)
        )
        if client_id:
            query = query.eq("client_id", client_id)
        if month:
            query = query.eq("month", month)
        if status:
            query = query.eq("status", status)
        plans = self._rows(query, "list_plans")
        offset = (page - 1) * page_size
        page_rows = plans[offset: offset + page_size]
        items = self._items_of([str(p["id"]) for p in page_rows])
        return {
            "items": [{**p, "items": items.get(str(p["id"]), [])} for p in page_rows],
            "total": len(plans),
            "page": page,
            "page_size": page_size,
        }

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        plan = self._plan_row(plan_id)
        if not plan:
            return None
        return {**plan, "items": self._items_of([plan_id]).get(plan_id, [])}

    def create_plan(self, data: dict[str, Any]) -> dict[str, Any]:
        items = data.pop("items", [])
        self._assert_owned("clients", data.get("client_id"), "Cliente")
        self._assert_owned("content_campaigns", data.get("campaign_id"), "Campanha")
        row = {**data, "org_id": self._org_id}
        rows = self._rows(self._t("content_plans").insert(row), "create_plan")
        if not rows:
            raise RuntimeError("Insert returned no data")
        plan = rows[0]
        created = self.append_items(str(plan["id"]), items) if items else []
        return {**plan, "items": created}

    def update_plan(self, plan_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        self._assert_owned("clients", data.get("client_id"), "Cliente")
        self._assert_owned("content_campaigns", data.get("campaign_id"), "Campanha")
        rows = self._rows(
            self._t("content_plans").update(data).eq("org_id", self._org_id).eq("id", plan_id),
            "update_plan",
        )
        if not rows:
            return None
        return {**rows[0], "items": self._items_of([plan_id]).get(plan_id, [])}

    def delete_plan(self, plan_id: str) -> bool:
        rows = self._rows(
            self._t("content_plans").delete().eq("org_id", self._org_id).eq("id", plan_id),
            "delete_plan",
        )
        return bool(rows)

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------

    def append_items(self, plan_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Append items at the end of the plan, preserving the given order."""
        if not items:
            return []
        start = self._next_position(plan_id)
        payload = [
            {
                **{k: v for k, v in item.items() if k in _ITEM_COLUMNS},
                "org_id": self._org_id,
                "plan_id": plan_id,
                "order_position": start + i,
                "status": "planned",
            }
            for i, item in enumerate(items)
        ]
        return self._rows(self._t("content_plan_items").insert(payload), "append_items")

    def _item_row(self, plan_id: str, item_id: str) -> dict[str, Any] | None:
        rows = self._rows(
            self._t("content_plan_items")
            .select("*")
            .eq("org_id", self._org_id)
            .eq("plan_id", plan_id)
            .eq("id", item_id),
            "get_item",
        )
        return rows[0] if rows else None

    def update_item(self, plan_id: str, item_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        rows = self._rows(
            self._t("content_plan_items")
            .update(data)
            .eq("org_id", self._org_id)
            .eq("plan_id", plan_id)
            .eq("id", item_id),
            "update_item",
        )
        return rows[0] if rows else None

    def delete_item(self, plan_id: str, item_id: str) -> dict[str, bool] | None:
        """None -> not found. With a task: discard (task kept). Otherwise hard delete."""
        item = self._item_row(plan_id, item_id)
        if not item:
            return None
        if item.get("task_id"):
            self._rows(
                self._t("content_plan_items")
                .update({"status": "discarded"})
                .eq("org_id", self._org_id)
                .eq("plan_id", plan_id)
                .eq("id", item_id),
                "discard_item",
            )
            return {"deleted": False, "discarded": True}
        self._rows(
            self._t("content_plan_items")
            .delete()
            .eq("org_id", self._org_id)
            .eq("plan_id", plan_id)
            .eq("id", item_id),
            "delete_item",
        )
        return {"deleted": True, "discarded": False}

    def reorder_items(self, plan_id: str, ids: list[str]) -> list[dict[str, Any]]:
        """Give `ids` positions 0..n-1 in order; unlisted items follow, in their old order."""
        current = self._items_of([plan_id]).get(plan_id, [])
        known = {str(r["id"]) for r in current}
        unknown = [i for i in ids if i not in known]
        if unknown:
            raise PlanReferenceError("Itens não pertencem ao plano")
        if len(set(ids)) != len(ids):
            raise PlanReferenceError("Lista de itens com repetição")
        order = list(ids) + [str(r["id"]) for r in current if str(r["id"]) not in set(ids)]
        by_id = {str(r["id"]): r for r in current}
        out: list[dict[str, Any]] = []
        for pos, item_id in enumerate(order):
            if int(by_id[item_id].get("order_position") or 0) != pos:
                self._rows(
                    self._t("content_plan_items")
                    .update({"order_position": pos})
                    .eq("org_id", self._org_id)
                    .eq("plan_id", plan_id)
                    .eq("id", item_id),
                    "reorder_item",
                )
            out.append({**by_id[item_id], "order_position": pos})
        return out

    # ------------------------------------------------------------------
    # Tasks from items
    # ------------------------------------------------------------------

    def _claim_item(self, plan_id: str, item_id: str) -> bool:
        """Compare-and-set: flip the item to 'task_pending' iff it is still
        unclaimed (task_id IS NULL, not discarded, not already pending).
        True only for the single caller whose UPDATE matched the row."""
        rows = self._rows(
            self._t("content_plan_items")
            .update({"status": "task_pending"})
            .eq("org_id", self._org_id)
            .eq("plan_id", plan_id)
            .eq("id", item_id)
            .is_("task_id", "null")
            .neq("status", "discarded")
            .neq("status", "task_pending"),
            "claim_item",
        )
        return bool(rows)

    def _release_claim(self, plan_id: str, item_id: str, prior_status: str) -> None:
        try:
            self._rows(
                self._t("content_plan_items")
                .update({"status": prior_status})
                .eq("org_id", self._org_id)
                .eq("plan_id", plan_id)
                .eq("id", item_id)
                .eq("status", "task_pending"),
                "release_claim",
            )
        except Exception:
            logger.error(
                "content_plans.release_claim FAILED item=%s org=%s (stuck in task_pending)",
                item_id, self._org_id,
            )

    def create_tasks(
        self,
        plan: dict[str, Any],
        item_ids: list[str],
        assignee_user_id: str | None = None,
    ) -> dict[str, Any]:
        """One task per ELIGIBLE selected item (no task_id, not discarded), each
        claimed by compare-and-set first so concurrent calls never double-create."""
        plan_id = str(plan["id"])
        wanted = {str(i) for i in item_ids}
        items = [
            r for r in self._items_of([plan_id]).get(plan_id, [])
            if str(r["id"]) in wanted
        ]
        eligible = [
            r for r in items
            if not r.get("task_id") and r.get("status") not in ("discarded", "task_pending")
        ]
        skipped = len(wanted) - len(eligible)
        tasks = TasksService(self._db, UUID(self._org_id))
        task_ids: list[str] = []
        failed = 0
        for item in eligible:
            prior_status = item.get("status") or "planned"
            if not self._claim_item(plan_id, str(item["id"])):
                skipped += 1  # a concurrent call won the compare-and-set
                continue
            due = item.get("due_date") or item.get("post_date")
            payload: dict[str, Any] = {
                "id": str(uuid4()),
                "title": item["title"],
                "status": "todo",
                "priority": "med",
            }
            description = build_task_description(item)
            if description:
                payload["description"] = description
            if plan.get("client_id"):
                payload["client_id"] = str(plan["client_id"])
            if due:
                payload["due_date"] = str(due)
            if assignee_user_id:
                payload["assignee_user_id"] = str(assignee_user_id)
            try:
                task = tasks.create_task(payload)
            except Exception:
                logger.exception(
                    "content_plans.create_tasks task insert failed org=%s item=%s",
                    self._org_id, item["id"],
                )
                self._release_claim(plan_id, str(item["id"]), prior_status)
                failed += 1
                continue
            try:
                self._rows(
                    self._t("content_plan_items")
                    .update({"status": "task_created", "task_id": str(task["id"])})
                    .eq("org_id", self._org_id)
                    .eq("id", str(item["id"])),
                    "link_task",
                )
            except Exception:
                # Task exists but the link failed: surface it as a failure so
                # the caller does not believe the item is covered.
                logger.error(
                    "content_plans.create_tasks ORPHAN task=%s item=%s org=%s",
                    task.get("id"), item["id"], self._org_id,
                )
                failed += 1
                continue
            task_ids.append(str(task["id"]))
        return {
            "created": len(task_ids),
            "skipped": skipped,
            "failed": failed,
            "task_ids": task_ids,
        }

    # ------------------------------------------------------------------
    # Promote item -> content_post (existing approval flow)
    # ------------------------------------------------------------------

    def promote_to_post(self, plan: dict[str, Any], item_id: str) -> dict[str, Any] | None:
        """Create the draft content_post for an item. None -> item not found.

        Raises ValueError for items that cannot be promoted (already has a
        post, discarded, or no platform).
        """
        item = self._item_row(str(plan["id"]), item_id)
        if not item:
            return None
        if item.get("post_id"):
            raise ValueError("Este conteúdo já virou um post")
        if item.get("status") == "discarded":
            raise ValueError("Conteúdo descartado não pode virar post")
        if not item.get("platform"):
            raise ValueError("Defina a plataforma antes de criar o post")
        post_row: dict[str, Any] = {
            "org_id": self._org_id,
            "platform": item["platform"],
            "status": "draft",
        }
        if plan.get("campaign_id"):
            post_row["campaign_id"] = str(plan["campaign_id"])
        if plan.get("client_id"):
            post_row["client_id"] = str(plan["client_id"])
        if item.get("caption"):
            post_row["caption"] = item["caption"]
        if item.get("post_date"):
            post_row["scheduled_for"] = f"{item['post_date']}T12:00:00+00:00"
        posts = self._rows(self._t("content_posts").insert(post_row), "promote_insert_post")
        if not posts:
            raise RuntimeError("Insert returned no data")
        post = posts[0]
        self._rows(
            self._t("content_plan_items")
            .update({"post_id": str(post["id"])})
            .eq("org_id", self._org_id)
            .eq("id", item_id),
            "promote_link_post",
        )
        return {"post": post, "item_id": item_id}
