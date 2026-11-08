"""Metas HTTP surface -- `create_metas_router(cfg, auth_dependency, admin_dependency, get_store)` at `/api/metas`.

    GET    /config                                  event types / modalities / goal categories (data)
    GET|POST /periods  ·  POST /periods/generate  ·  GET|PATCH|DELETE /periods/{id}
    GET|POST /teams    ·  GET|PATCH|DELETE /teams/{id}  ·  GET|POST /teams/{id}/members  ·  PATCH|DELETE /teams/{id}/members/{mid}
    GET|POST /goals    ·  GET /goals/summary?period_id  ·  GET|PATCH|DELETE /goals/{id}  ·  POST /goals/{id}/contributions
    GET /rules  ·  PUT /rules  ·  POST /rules/defaults  ·  DELETE /rules/{id}
    GET|PUT /settings
    GET|POST /events  ·  PATCH|DELETE /events/{id}
    GET /rankings?period_id|from&to&metric&team_id
    GET /closings?period_id  ·  POST /closings/close

`auth_dependency` yields `(user, token, org_id)` (+ `.is_admin`, the trusted role in the SELECTED org: `make_organ_auth`);
unauthenticated is a strict 401 there. `admin_dependency` is 403 unless admin. Structure (periods, teams, rules, settings,
closings, event adjustments, team / company goals) is the owner's; members read, log their own events and manage their own
goals. Handlers are plain `def` (the store does blocking IO), so FastAPI runs them in its threadpool.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from noctusai_lib.primitives.responses import success_response

from .config import MetasConfig
from .schemas import (
    CloseBody,
    ContributionBody,
    EventBody,
    EventPatch,
    GoalBody,
    GoalPatch,
    MemberBody,
    MemberPatch,
    PeriodBody,
    PeriodGenerate,
    PeriodPatch,
    RuleBody,
    SettingsBody,
    TeamBody,
    TeamPatch,
)
from .service import Actor, MetasService
from .store import MetasStore

MAX_PAGE = 200


def _dump(body: Any, **kw: Any) -> dict:
    """The body as a plain dict: JSON-safe values (UUIDs as text), but real `date`s -- the service does window math."""
    data = body.model_dump(mode="json", **kw)
    for name in ("starts_on", "ends_on", "occurred_on", "at"):
        if name in data and data[name] is not None:
            data[name] = getattr(body, name)
    return data


def create_metas_router(
    cfg: MetasConfig,
    auth_dependency: Callable[..., Any],
    admin_dependency: Callable[..., Any],
    *,
    get_store: Callable[[], MetasStore],
    prefix: str = "/api/metas",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags or ["metas"])

    def ctx_dep(auth: tuple = Depends(auth_dependency)) -> tuple[MetasService, Actor]:
        user, _token, org_id = auth
        return MetasService(get_store(), cfg), Actor(str(org_id), str(getattr(user, "id", None) or ""), bool(getattr(auth, "is_admin", False)))

    def org_admin_dep(auth: tuple = Depends(admin_dependency)) -> tuple[MetasService, Actor]:
        user, _token, org_id = auth
        return MetasService(get_store(), cfg), Actor(str(org_id), str(getattr(user, "id", None) or ""), True)

    @router.get("/config", name="metas_config")
    def config_route(_auth: tuple = Depends(auth_dependency)) -> dict:
        return success_response(cfg.as_dict())

    # -- periods
    @router.get("/periods", name="metas_periods_list")
    def periods_list(kind: Optional[str] = Query(None), status: Optional[str] = Query(None), containing: Optional[date] = Query(None), c=Depends(ctx_dep)) -> dict:
        svc, a = c
        return success_response(svc.list_periods(a.org_id, kind=kind, status=status, containing=containing))

    @router.post("/periods", status_code=201, name="metas_periods_create")
    def periods_create(body: PeriodBody, c=Depends(org_admin_dep)) -> dict:
        svc, a = c
        return success_response(svc.create_period(a.org_id, _dump(body)))

    @router.post("/periods/generate", status_code=201, name="metas_periods_generate")
    def periods_generate(body: PeriodGenerate, c=Depends(org_admin_dep)) -> dict:
        svc, a = c
        return success_response(svc.generate_periods(a.org_id, body.kind, body.starts_on, body.ends_on))

    @router.get("/periods/{period_id}", name="metas_periods_get")
    def periods_get(period_id: UUID, c=Depends(ctx_dep)) -> dict:
        svc, a = c
        return success_response(svc.get_period(a.org_id, str(period_id)))

    @router.patch("/periods/{period_id}", name="metas_periods_update")
    def periods_update(period_id: UUID, body: PeriodPatch, c=Depends(org_admin_dep)) -> dict:
        svc, a = c
        return success_response(svc.update_period(a.org_id, str(period_id), _dump(body, exclude_unset=True)))

    @router.delete("/periods/{period_id}", status_code=204, name="metas_periods_delete")
    def periods_delete(period_id: UUID, c=Depends(org_admin_dep)) -> Response:
        svc, a = c
        svc.delete_period(a.org_id, str(period_id))
        return Response(status_code=204)

    # -- teams
    @router.get("/teams", name="metas_teams_list")
    def teams_list(include_inactive: bool = Query(False), c=Depends(ctx_dep)) -> dict:
        svc, a = c
        return success_response(svc.list_teams(a.org_id, include_inactive=include_inactive and a.is_admin))

    @router.post("/teams", status_code=201, name="metas_teams_create")
    def teams_create(body: TeamBody, c=Depends(org_admin_dep)) -> dict:
        svc, a = c
        return success_response(svc.create_team(a.org_id, _dump(body)))

    @router.get("/teams/{team_id}", name="metas_teams_get")
    def teams_get(team_id: UUID, c=Depends(ctx_dep)) -> dict:
        svc, a = c
        return success_response(svc.get_team(a.org_id, str(team_id)))

    @router.patch("/teams/{team_id}", name="metas_teams_update")
    def teams_update(team_id: UUID, body: TeamPatch, c=Depends(org_admin_dep)) -> dict:
        svc, a = c
        return success_response(svc.update_team(a.org_id, str(team_id), _dump(body, exclude_unset=True)))

    @router.delete("/teams/{team_id}", status_code=204, name="metas_teams_disband")
    def teams_disband(team_id: UUID, c=Depends(org_admin_dep)) -> Response:
        svc, a = c
        svc.disband_team(a.org_id, str(team_id))
        return Response(status_code=204)

    @router.get("/teams/{team_id}/members", name="metas_members_list")
    def members_list(team_id: UUID, include_left: bool = Query(False), c=Depends(ctx_dep)) -> dict:
        svc, a = c
        return success_response(svc.list_members(a.org_id, str(team_id), include_left=include_left and a.is_admin))

    @router.post("/teams/{team_id}/members", status_code=201, name="metas_members_add")
    def members_add(team_id: UUID, body: MemberBody, c=Depends(org_admin_dep)) -> dict:
        svc, a = c
        return success_response(svc.add_member(a.org_id, str(team_id), str(body.user_id), body.role))

    @router.patch("/teams/{team_id}/members/{member_id}", name="metas_members_update")
    def members_update(team_id: UUID, member_id: UUID, body: MemberPatch, c=Depends(org_admin_dep)) -> dict:
        svc, a = c
        return success_response(svc.update_member(a.org_id, str(team_id), str(member_id), body.role))

    @router.delete("/teams/{team_id}/members/{member_id}", status_code=204, name="metas_members_remove")
    def members_remove(team_id: UUID, member_id: UUID, c=Depends(org_admin_dep)) -> Response:
        svc, a = c
        svc.remove_member(a.org_id, str(team_id), str(member_id))
        return Response(status_code=204)

    # -- goals
    @router.get("/goals/summary", name="metas_goals_summary")
    def goals_summary(period_id: UUID = Query(...), c=Depends(ctx_dep)) -> dict:
        svc, a = c
        return success_response(svc.summary(a, str(period_id)))

    @router.get("/goals", name="metas_goals_list")
    def goals_list(
        scope: Optional[str] = Query(None), subject_id: Optional[UUID] = Query(None), period_id: Optional[UUID] = Query(None),
        category: Optional[str] = Query(None), status: Optional[str] = Query(None), c=Depends(ctx_dep),
    ) -> dict:
        svc, a = c
        return success_response(svc.list_goals(
            a, scope=scope, subject_id=str(subject_id) if subject_id else None, period_id=str(period_id) if period_id else None,
            category=category, status=status,
        ))

    @router.post("/goals", status_code=201, name="metas_goals_create")
    def goals_create(body: GoalBody, c=Depends(ctx_dep)) -> dict:
        svc, a = c
        return success_response(svc.create_goal(a, _dump(body, exclude_none=True)))

    @router.get("/goals/{goal_id}", name="metas_goals_get")
    def goals_get(goal_id: UUID, c=Depends(ctx_dep)) -> dict:
        svc, a = c
        return success_response(svc.get_goal(a, str(goal_id)))

    @router.patch("/goals/{goal_id}", name="metas_goals_update")
    def goals_update(goal_id: UUID, body: GoalPatch, c=Depends(ctx_dep)) -> dict:
        svc, a = c
        return success_response(svc.update_goal(a, str(goal_id), _dump(body, exclude_unset=True)))

    @router.delete("/goals/{goal_id}", status_code=204, name="metas_goals_delete")
    def goals_delete(goal_id: UUID, c=Depends(ctx_dep)) -> Response:
        svc, a = c
        svc.delete_goal(a, str(goal_id))
        return Response(status_code=204)

    @router.post("/goals/{goal_id}/contributions", status_code=201, name="metas_goals_contribute")
    def goals_contribute(goal_id: UUID, body: ContributionBody, c=Depends(ctx_dep)) -> dict:
        svc, a = c
        return success_response(svc.contribute(a, str(goal_id), body.amount, body.at, body.note))

    # -- rules / settings
    @router.get("/rules", name="metas_rules_list")
    def rules_list(period_id: Optional[UUID] = Query(None), c=Depends(ctx_dep)) -> dict:
        svc, a = c
        return success_response(svc.list_rules(a.org_id, period_id=str(period_id) if period_id else None))

    @router.put("/rules", name="metas_rules_upsert")
    def rules_upsert(body: RuleBody, c=Depends(org_admin_dep)) -> dict:
        svc, a = c
        return success_response(svc.upsert_rule(a.org_id, _dump(body)))

    @router.post("/rules/defaults", status_code=201, name="metas_rules_defaults")
    def rules_defaults(c=Depends(org_admin_dep)) -> dict:
        svc, a = c
        return success_response(svc.seed_default_rules(a.org_id))

    @router.delete("/rules/{rule_id}", status_code=204, name="metas_rules_delete")
    def rules_delete(rule_id: UUID, c=Depends(org_admin_dep)) -> Response:
        svc, a = c
        svc.delete_rule(a.org_id, str(rule_id))
        return Response(status_code=204)

    @router.get("/settings", name="metas_settings_get")
    def settings_get(c=Depends(ctx_dep)) -> dict:
        svc, a = c
        return success_response(svc.get_settings(a.org_id))

    @router.put("/settings", name="metas_settings_put")
    def settings_put(body: SettingsBody, c=Depends(org_admin_dep)) -> dict:
        svc, a = c
        return success_response(svc.put_settings(a.org_id, _dump(body, exclude_unset=True)))

    # -- events
    @router.get("/events", name="metas_events_list")
    def events_list(
        member_id: Optional[UUID] = Query(None), team_id: Optional[UUID] = Query(None), period_id: Optional[UUID] = Query(None),
        event_type: Optional[str] = Query(None), frm: Optional[date] = Query(None, alias="from"), to: Optional[date] = Query(None),
        limit: int = Query(50, ge=1, le=MAX_PAGE), offset: int = Query(0, ge=0), c=Depends(ctx_dep),
    ) -> dict:
        svc, a = c
        return success_response(svc.list_events(
            a, member_id=str(member_id) if member_id else None, team_id=str(team_id) if team_id else None,
            period_id=str(period_id) if period_id else None, event_type=event_type, start=frm, end=to, limit=limit, offset=offset,
        ))

    @router.post("/events", name="metas_events_create")
    def events_create(body: EventBody, response: Response, c=Depends(ctx_dep)) -> dict:
        svc, a = c
        event, created = svc.record_event(a, _dump(body))
        response.status_code = 201 if created else 200  # a replay of a dedupe_key is a 200 with the first event
        return success_response(event)

    @router.patch("/events/{event_id}", name="metas_events_adjust")
    def events_adjust(event_id: UUID, body: EventPatch, c=Depends(org_admin_dep)) -> dict:
        svc, a = c
        return success_response(svc.adjust_event(a, str(event_id), _dump(body, exclude_unset=True)))

    @router.delete("/events/{event_id}", status_code=204, name="metas_events_delete")
    def events_delete(event_id: UUID, c=Depends(org_admin_dep)) -> Response:
        svc, a = c
        svc.delete_event(a, str(event_id))
        return Response(status_code=204)

    # -- rankings / closings
    @router.get("/rankings", name="metas_rankings")
    def rankings(
        period_id: Optional[UUID] = Query(None), frm: Optional[date] = Query(None, alias="from"), to: Optional[date] = Query(None),
        metric: Optional[str] = Query(None), team_id: Optional[UUID] = Query(None), c=Depends(ctx_dep),
    ) -> dict:
        svc, a = c
        return success_response(svc.rankings(a, period_id=str(period_id) if period_id else None, start=frm, end=to, metric=metric, team_id=str(team_id) if team_id else None))

    @router.get("/closings", name="metas_closings_list")
    def closings_list(period_id: UUID = Query(...), c=Depends(ctx_dep)) -> dict:
        svc, a = c
        return success_response(svc.list_closings(a, str(period_id)))

    @router.post("/closings/close", name="metas_closings_close")
    def closings_close(body: CloseBody, response: Response, c=Depends(org_admin_dep)) -> dict:
        svc, a = c
        snapshots, reused = svc.close_period(a, str(body.period_id))
        response.status_code = 200 if reused else 201
        return success_response({"period_id": str(body.period_id), "snapshots": snapshots, "reused": reused})

    return router


__all__ = ["create_metas_router"]
