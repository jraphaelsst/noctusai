"""``/api/admin/agent-settings`` — the platform-admin "Configurações do
agente" page: Julia's runtime specs (DB override, env default).

Model / persona stay on ``/api/agents/julia/persona``; the One Chat toggle
stays on ``POST /api/agents/{key}/toggle`` — the page composes both.
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_runtime_settings_service_dep, require_platform_admin
from app.schemas.admin import AgentSettingOut, AgentSettingsOut, AgentSettingsPatch
from app.services.runtime_settings import RuntimeSettingsError, RuntimeSettingsService
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(prefix="/api/admin/agent-settings", tags=["admin-agent-settings"])


def _out(views) -> AgentSettingsOut:
    return AgentSettingsOut(items=[AgentSettingOut(**asdict(v)) for v in views])


@router.get("", response_model=AgentSettingsOut)
async def get_agent_settings(
    ctx: AuthContext = Depends(require_platform_admin),
    service: RuntimeSettingsService = Depends(get_runtime_settings_service_dep),
) -> AgentSettingsOut:
    return _out(service.view())


@router.put("", response_model=AgentSettingsOut)
async def update_agent_settings(
    payload: AgentSettingsPatch,
    ctx: AuthContext = Depends(require_platform_admin),
    service: RuntimeSettingsService = Depends(get_runtime_settings_service_dep),
) -> AgentSettingsOut:
    patch = payload.model_dump(exclude_unset=True)
    try:
        return _out(service.update(patch, updated_by=ctx.user_id))
    except RuntimeSettingsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"detail": exc.detail, "code": "invalid_field", "field": exc.field},
        ) from exc


__all__ = ["router"]
