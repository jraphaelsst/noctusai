"""Engagement HTTP surface -- `create_engagement_router(...)` at `/api/engagement`.

    GET  /leaderboard?kind=monthly|weekly|...&from&to&limit    ranked totals (SQL SUM over the ledger)
    GET  /me                                                   the caller's points, metrics, badges, recent awards
    GET  /members/{id}                                         the same card for another member (admin)
    POST /events                                               score one action (idempotent on idempotency_key)
    GET|PUT /rules  ·  DELETE /rules/{id}                      points per (source, action), caps (admin writes)
    GET|PUT /badges ·  DELETE /badges/{id}                     badge thresholds (admin writes)
    DELETE /members/{id}/points                                LGPD delete-by-subject (admin)

`auth_dependency` yields `(user, token, org_id)` + `.is_admin` (`make_organ_auth`); unauthenticated is a strict 401 there.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from noctusai_lib.domain._organ_common import OrgTableStore
from noctusai_lib.primitives.responses import success_response

from .schemas import BadgeRuleBody, EngagementEventBody, PointRuleBody
from .service import Actor, EngagementService

MAX_LIMIT = 200


def create_engagement_router(
    auth_dependency: Callable[..., Any],
    admin_dependency: Callable[..., Any],
    *,
    get_store: Callable[[], OrgTableStore],
    get_ledger: Callable[[str], Any],
    member_scope: Optional[Callable[[Actor], Optional[set[str]]]] = None,
    prefix: str = "/api/engagement",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags or ["engagement"])

    def _mk(auth: Any, admin: bool) -> tuple[EngagementService, Actor]:
        user, _token, org_id = auth
        actor = Actor(str(org_id), str(getattr(user, "id", None) or ""), admin or bool(getattr(auth, "is_admin", False)))
        return EngagementService(get_store(), get_ledger, member_scope=member_scope), actor

    def ctx_dep(auth: tuple = Depends(auth_dependency)) -> tuple[EngagementService, Actor]:
        return _mk(auth, False)

    def org_admin_dep(auth: tuple = Depends(admin_dependency)) -> tuple[EngagementService, Actor]:
        return _mk(auth, True)

    @router.get("/leaderboard", name="engagement_leaderboard")
    def leaderboard_route(
        kind: str = Query("monthly", max_length=20), frm: Optional[date] = Query(None, alias="from"), to: Optional[date] = Query(None),
        limit: int = Query(50, ge=1, le=MAX_LIMIT), c=Depends(ctx_dep),
    ) -> dict:
        svc, a = c
        return success_response(svc.leaderboard(a, kind=kind, start=frm, end=to, limit=limit))

    @router.get("/me", name="engagement_me")
    def me(c=Depends(ctx_dep)) -> dict:
        svc, a = c
        return success_response(svc.member_card(a))

    @router.get("/members/{member_id}", name="engagement_member")
    def member(member_id: str, c=Depends(org_admin_dep)) -> dict:
        svc, a = c
        return success_response(svc.member_card(a, member_id))

    @router.delete("/members/{member_id}/points", name="engagement_erase_member")
    def erase_member(member_id: str, c=Depends(org_admin_dep)) -> dict:
        svc, a = c
        return success_response({"member_id": member_id, "deleted": svc.erase_member(a, member_id)})

    @router.post("/events", name="engagement_record")
    def record(body: EngagementEventBody, response: Response, c=Depends(ctx_dep)) -> dict:
        svc, a = c
        data = body.model_dump(mode="json")
        data["occurred_at"] = body.occurred_at
        result = svc.record(a, data)
        response.status_code = 200 if result["duplicate"] else 201
        return success_response(result)

    @router.get("/rules", name="engagement_rules_list")
    def rules_list(c=Depends(ctx_dep)) -> dict:
        svc, a = c
        return success_response(svc.list_rules(a.org_id))

    @router.put("/rules", name="engagement_rules_upsert")
    def rules_upsert(body: PointRuleBody, c=Depends(org_admin_dep)) -> dict:
        svc, a = c
        return success_response(svc.upsert_rule(a.org_id, body.model_dump()))

    @router.delete("/rules/{rule_id}", status_code=204, name="engagement_rules_delete")
    def rules_delete(rule_id: UUID, c=Depends(org_admin_dep)) -> Response:
        svc, a = c
        svc.delete_rule(a.org_id, str(rule_id))
        return Response(status_code=204)

    @router.get("/badges", name="engagement_badges_list")
    def badges_list(c=Depends(ctx_dep)) -> dict:
        svc, a = c
        return success_response(svc.list_badges(a.org_id))

    @router.put("/badges", name="engagement_badges_upsert")
    def badges_upsert(body: BadgeRuleBody, c=Depends(org_admin_dep)) -> dict:
        svc, a = c
        return success_response(svc.upsert_badge(a.org_id, body.model_dump()))

    @router.delete("/badges/{badge_row_id}", status_code=204, name="engagement_badges_delete")
    def badges_delete(badge_row_id: UUID, c=Depends(org_admin_dep)) -> Response:
        svc, a = c
        svc.delete_badge(a.org_id, str(badge_row_id))
        return Response(status_code=204)

    return router


__all__ = ["create_engagement_router"]
