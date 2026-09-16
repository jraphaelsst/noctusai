"""`GET|PUT /api/edicao-fotos/configuracoes` (org) and
`GET|PUT /api/edicao-fotos/configuracoes/plataforma` — contract §8 + §1.

Org settings: agency admin (owner/admin/manager) or platform admin, always
for the caller's OWN org. Platform settings: platform admin only.

Econômico is refused with the contract code `economico_indisponivel` (C8 —
no batch-capable priced model, no engine path in R1)."""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter, Depends

from noctusai_lib.domain.photo_editing import (
    ECONOMICO_IMPLEMENTED,
    Actor,
    EditType,
    OrgSettings,
    PhotoEditingPorts,
    Speed,
)
from noctusai_lib.integrations.image_edit import capabilities_for_model
from noctusai_lib.integrations.llm.models import models_for

from app.modules.edicao_fotos.deps import (
    get_edicao_ports,
    require_org_admin,
    require_platform_admin,
)
from app.modules.edicao_fotos.errors import api_error
from app.modules.edicao_fotos.presenters import org_settings_out, platform_settings_out
from app.modules.edicao_fotos.schemas import OrgSettingsBody, PlatformSettingsBody

router = APIRouter(prefix="/api/edicao-fotos/configuracoes", tags=["edicao-fotos"])


def _refuse_economico(speed: str | None, model: str | None) -> None:
    if speed != Speed.ECONOMICO.value:
        return
    batch_ok = bool(model) and capabilities_for_model(model).supports_batch
    if not (ECONOMICO_IMPLEMENTED and batch_ok):
        raise api_error(422, "economico_indisponivel", "Modo Econômico indisponível.")


def _catalog() -> list[dict]:
    return [
        {"id": e.id, "label": e.label, "suporta_lote": e.supports_batch}
        for e in models_for("openai", "image_edit")
    ]


@router.get("")
async def get_org_settings_route(
    actor: Actor = Depends(require_org_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    settings = await ports.repo.get_org_settings(actor.org_id) or OrgSettings(org_id=actor.org_id)
    return {**org_settings_out(settings), "modelos_edicao": _catalog()}


@router.put("")
async def put_org_settings_route(
    body: OrgSettingsBody,
    actor: Actor = Depends(require_org_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    model = (body.modelo_editor_id or "").strip() or None
    if model is not None and not capabilities_for_model(model).known:
        raise api_error(422, "modelo_desconhecido", f"Modelo {model} não está no catálogo.")
    _refuse_economico(body.velocidade_override, model)
    current = await ports.repo.get_org_settings(actor.org_id) or OrgSettings(org_id=actor.org_id)
    updated = dataclasses.replace(
        current,
        tipos_edicao_ativos=tuple(EditType(t) for t in dict.fromkeys(body.tipos_edicao_ativos)),
        modelo_editor_id=model,
        velocidade_override=Speed(body.velocidade_override) if body.velocidade_override else None,
        notificacoes_ativas=body.notificacoes_ativas,
    )
    saved = await ports.repo.save_org_settings(updated)
    return {**org_settings_out(saved), "modelos_edicao": _catalog()}


@router.get("/plataforma")
async def get_platform_settings_route(
    _actor: Actor = Depends(require_platform_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    return platform_settings_out(await ports.repo.get_platform_settings())


@router.put("/plataforma")
async def put_platform_settings_route(
    body: PlatformSettingsBody,
    _actor: Actor = Depends(require_platform_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    # A platform default has no model of its own: Econômico is refused
    # outright while the engine has no path for it.
    _refuse_economico(body.velocidade_default, None)
    saved = await ports.repo.update_platform_settings(
        velocidade_default=Speed(body.velocidade_default),
        notificacoes_globais_ativas=body.notificacoes_globais_ativas,
        preco_storage_gb_mes_usd=body.preco_storage_gb_mes_usd,
    )
    return platform_settings_out(saved)
