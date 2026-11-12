"""Assignment HTTP surface -- `make_assignment_router(...)` at `/api/assignment` (access tier `org`, service-role store).

    GET    /settings · /teams · /teams/{id} · /rules · /workload · /events?subject_kind&subject_id&limit&offset
    GET    /assignments/{subject_kind}/{subject_id}      the current owner of a subject (404 when none)
    POST   /assign                                       pick an owner with the org's strategy   (any org member: staff / automation)
    POST   /close                                        the work is done: owner stays as history, seat freed (any org member)
    POST   /reassign · /unassign                         a human moves / clears the owner (org admin, or the CURRENT owner handing off)
    PUT    /settings                                     strategy, default team, keep-last           (org admin)
    POST   /teams · PATCH|DELETE /teams/{id}             (org admin)
    POST   /teams/{id}/members · PATCH|DELETE /teams/{id}/members/{user_id} · PUT /teams/{id}/order   (org admin)
    PUT    /rules · DELETE /rules/{id}                   source / unit -> team                       (org admin)

`auth_dependency` yields `(user, token, org_id)` + `.is_admin` (`make_organ_auth`); unauthenticated is a strict 401 there, and
`make_router(tier="org", guard=auth_dependency)` makes it a router-level dependency so no route added later can skip it.
"""
from __future__ import annotations

from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import Depends, Query, Response

from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.primitives.responses import success_response

from .errors import SEM_PERMISSAO_CODE, AssignmentError, not_found
from .schemas import AssignBody, MemberBody, MemberPatch, OrderBody, ReassignBody, ReleaseBody, RuleBody, SettingsBody, TeamBody, TeamPatch
from .service import Actor, AssignmentService

MAX_LIMIT = 200


def make_assignment_router(
    auth_dependency: Callable[..., Any],
    admin_dependency: Callable[..., Any],
    *,
    get_service: Callable[[], AssignmentService],
    prefix: str = "/api/assignment",
    tags: Optional[list[str]] = None,
) -> Any:
    router = make_router(tier="org", guard=auth_dependency, prefix=prefix, tags=tags or ["assignment"])

    def _actor(auth: Any, *, admin: bool = False) -> Actor:
        user, _token, org_id = auth
        return Actor(str(org_id), str(getattr(user, "id", None) or ""), admin or bool(getattr(auth, "is_admin", False)))

    def member(auth: tuple = Depends(auth_dependency)) -> tuple[AssignmentService, Actor]:
        return get_service(), _actor(auth)

    def admin(auth: tuple = Depends(admin_dependency)) -> tuple[AssignmentService, Actor]:
        return get_service(), _actor(auth, admin=True)

    # -- reads ---------------------------------------------------------------------------------------------------

    @router.get("/settings", name="assignment_settings")
    def settings_route(c=Depends(member)) -> dict:
        svc, a = c
        return success_response(svc.get_settings(a.org_id))

    @router.get("/teams", name="assignment_teams")
    def teams_route(c=Depends(member)) -> dict:
        svc, a = c
        return success_response(svc.list_teams(a.org_id))

    @router.get("/teams/{team_id}", name="assignment_team")
    def team_route(team_id: UUID, c=Depends(member)) -> dict:
        svc, a = c
        return success_response(svc.get_team(a.org_id, str(team_id)))

    @router.get("/rules", name="assignment_rules")
    def rules_route(c=Depends(member)) -> dict:
        svc, a = c
        return success_response(svc.list_rules(a.org_id))

    @router.get("/workload", name="assignment_workload")
    def workload_route(c=Depends(member)) -> dict:
        svc, a = c
        return success_response(svc.workload(a.org_id))

    @router.get("/events", name="assignment_events")
    def events_route(
        subject_kind: Optional[str] = Query(None, max_length=40), subject_id: Optional[UUID] = Query(None),
        limit: int = Query(50, ge=1, le=MAX_LIMIT), offset: int = Query(0, ge=0, le=100000), c=Depends(member),
    ) -> dict:
        svc, a = c
        return success_response(svc.events(a.org_id, subject_kind=subject_kind, subject_id=str(subject_id) if subject_id else None, limit=limit, offset=offset))

    @router.get("/assignments/{subject_kind}/{subject_id}", name="assignment_get")
    def assignment_route(subject_kind: str, subject_id: UUID, c=Depends(member)) -> dict:
        svc, a = c
        row = svc.get_assignment(a.org_id, subject_kind, str(subject_id))
        if row is None:
            raise not_found("Atribuição")
        return success_response(row)

    # -- the verbs -----------------------------------------------------------------------------------------------

    @router.post("/assign", name="assignment_assign")
    def assign_route(body: AssignBody, c=Depends(member)) -> dict:
        svc, a = c
        return success_response(svc.assign(
            a.org_id, subject_kind=body.subject_kind, subject_id=str(body.subject_id), source=body.source,
            org_unit_id=str(body.org_unit_id) if body.org_unit_id else None, team_id=str(body.team_id) if body.team_id else None,
            actor_id=a.user_id or None, note=body.note,
        ))

    @router.post("/close", name="assignment_close")
    def close_route(body: ReleaseBody, c=Depends(member)) -> dict:
        svc, a = c
        return success_response(svc.close(a.org_id, subject_kind=body.subject_kind, subject_id=str(body.subject_id), actor_id=a.user_id or None, note=body.note))

    def _may_move(svc: AssignmentService, a: Actor, subject_kind: str, subject_id: str) -> None:
        """Admin, or the CURRENT owner handing the subject off -- nobody else takes a colleague's lead away."""
        if a.is_admin:
            return
        current = svc.get_assignment(a.org_id, subject_kind, subject_id)
        if current is None or current.get("closed_at") is not None or current["user_id"] != a.user_id:
            raise AssignmentError(SEM_PERMISSAO_CODE, "Só um administrador ou o responsável atual pode mudar o responsável.", 403)

    @router.post("/reassign", name="assignment_reassign")
    def reassign_route(body: ReassignBody, c=Depends(member)) -> dict:
        svc, a = c
        _may_move(svc, a, body.subject_kind, str(body.subject_id))
        return success_response(svc.reassign(
            a.org_id, subject_kind=body.subject_kind, subject_id=str(body.subject_id), to_user_id=str(body.to_user_id),
            actor_id=a.user_id or None, team_id=str(body.team_id) if body.team_id else None, note=body.note,
        ))

    @router.post("/unassign", name="assignment_unassign")
    def unassign_route(body: ReleaseBody, c=Depends(member)) -> dict:
        svc, a = c
        _may_move(svc, a, body.subject_kind, str(body.subject_id))
        return success_response(svc.unassign(a.org_id, subject_kind=body.subject_kind, subject_id=str(body.subject_id), actor_id=a.user_id or None, note=body.note))

    # -- configuration (org admin) -------------------------------------------------------------------------------

    @router.put("/settings", name="assignment_settings_put")
    def settings_put(body: SettingsBody, c=Depends(admin)) -> dict:
        svc, a = c
        return success_response(svc.put_settings(a.org_id, body.model_dump(mode="json", exclude_unset=True)))

    @router.post("/teams", status_code=201, name="assignment_team_create")
    def team_create(body: TeamBody, c=Depends(admin)) -> dict:
        svc, a = c
        return success_response(svc.create_team(a.org_id, **body.model_dump(mode="json")))

    @router.patch("/teams/{team_id}", name="assignment_team_update")
    def team_update(team_id: UUID, body: TeamPatch, c=Depends(admin)) -> dict:
        svc, a = c
        return success_response(svc.update_team(a.org_id, str(team_id), body.model_dump(mode="json", exclude_unset=True)))

    @router.delete("/teams/{team_id}", status_code=204, name="assignment_team_delete")
    def team_delete(team_id: UUID, c=Depends(admin)) -> Response:
        svc, a = c
        svc.delete_team(a.org_id, str(team_id))
        return Response(status_code=204)

    @router.post("/teams/{team_id}/members", status_code=201, name="assignment_member_add")
    def member_add(team_id: UUID, body: MemberBody, c=Depends(admin)) -> dict:
        svc, a = c
        return success_response(svc.add_member(a.org_id, str(team_id), **body.model_dump(mode="json")))

    @router.patch("/teams/{team_id}/members/{user_id}", name="assignment_member_update")
    def member_update(team_id: UUID, user_id: UUID, body: MemberPatch, c=Depends(admin)) -> dict:
        svc, a = c
        return success_response(svc.update_member(a.org_id, str(team_id), str(user_id), body.model_dump(mode="json", exclude_unset=True)))

    @router.delete("/teams/{team_id}/members/{user_id}", status_code=204, name="assignment_member_remove")
    def member_remove(team_id: UUID, user_id: UUID, c=Depends(admin)) -> Response:
        svc, a = c
        svc.remove_member(a.org_id, str(team_id), str(user_id))
        return Response(status_code=204)

    @router.put("/teams/{team_id}/order", name="assignment_member_order")
    def member_order(team_id: UUID, body: OrderBody, c=Depends(admin)) -> dict:
        svc, a = c
        return success_response(svc.order_members(a.org_id, str(team_id), [str(u) for u in body.order]))

    @router.put("/rules", name="assignment_rule_put")
    def rule_put(body: RuleBody, c=Depends(admin)) -> dict:
        svc, a = c
        return success_response(svc.put_rule(a.org_id, kind=body.kind, match_value=body.match_value, team_id=str(body.team_id)))

    @router.delete("/rules/{rule_id}", status_code=204, name="assignment_rule_delete")
    def rule_delete(rule_id: UUID, c=Depends(admin)) -> Response:
        svc, a = c
        svc.delete_rule(a.org_id, str(rule_id))
        return Response(status_code=204)

    return router


__all__ = ["make_assignment_router"]
