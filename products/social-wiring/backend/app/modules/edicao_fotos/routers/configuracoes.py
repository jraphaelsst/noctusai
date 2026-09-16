"""`GET|PUT /api/edicao-fotos/configuracoes` (org) and
`GET|PUT /api/edicao-fotos/configuracoes/plataforma` — contract §8 + §1.

Org settings: READ for every member (the FE shows corretores a read-only
summary); WRITE for agency admin (owner/admin/manager) or platform admin —
always the caller's OWN org. Platform settings: platform admin only.

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

from app.modules.edicao_fotos.deps import (
    get_edicao_ports,
    require_member,
    require_org_admin,
    require_platform_admin,
)
from app.modules.edicao_fotos.errors import api_error
from app.modules.edicao_fotos.presenters import org_configuracoes_out, platform_settings_out
from app.modules.edicao_fotos.schemas import OrgSettingsBody, PlatformSettingsBody

router = APIRouter(prefix="/api/edicao-fotos/configuracoes", tags=["edicao-fotos"])


def refuse_economico(speed: str | None, model: str | None) -> None:
    if speed != Speed.ECONOMICO.value:
        return
    batch_ok = bool(model) and capabilities_for_model(model).supports_batch
    if not (ECONOMICO_IMPLEMENTED and batch_ok):
        raise api_error(422, "economico_indisponivel", "Modo Econômico indisponível.")


@router.get("")
async def get_org_settings_route(
    actor: Actor = Depends(require_member),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    settings = await ports.repo.get_org_settings(actor.org_id) or OrgSettings(org_id=actor.org_id)
    return org_configuracoes_out(settings, await ports.repo.get_platform_settings())


@router.put("")
async def put_org_settings_route(
    body: OrgSettingsBody,
    actor: Actor = Depends(require_org_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    model = (body.modelo_editor_imagem or "").strip() or None
    if model is not None and not capabilities_for_model(model).known:
        raise api_error(422, "modelo_desconhecido", f"Modelo {model} não está no catálogo.")
    refuse_economico(body.velocidade_padrao, model)
    platform = await ports.repo.get_platform_settings()
    override = None
    if body.velocidade_padrao is not None and Speed(body.velocidade_padrao) is not Speed(
        platform.velocidade_default
    ):
        override = Speed(body.velocidade_padrao)
    current = await ports.repo.get_org_settings(actor.org_id) or OrgSettings(org_id=actor.org_id)
    updated = dataclasses.replace(
        current,
        tipos_edicao_ativos=tuple(EditType(t) for t in dict.fromkeys(body.tipos_edicao_ativos)),
        modelo_editor_id=model,
        velocidade_override=override,
        notificacoes_ativas=(
            current.notificacoes_ativas
            if body.notificacoes_ativas is None
            else body.notificacoes_ativas
        ),
    )
    saved = await ports.repo.save_org_settings(updated)
    return org_configuracoes_out(saved, platform)


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
    refuse_economico(body.velocidade_default, None)
    saved = await ports.repo.update_platform_settings(
        velocidade_default=Speed(body.velocidade_default),
        notificacoes_globais_ativas=body.notificacoes_globais_ativas,
        preco_storage_gb_mes_usd=body.preco_storage_gb_mes_usd,
    )
    return platform_settings_out(saved)
