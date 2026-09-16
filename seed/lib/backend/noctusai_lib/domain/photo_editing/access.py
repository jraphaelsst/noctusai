"""Server-computed capabilities (contract §2 ``GET /capacidades``).

Every frontend gate reads this; it is NEVER derived from SSO metadata.
Role inputs come from the consumer's trusted resolvers; the curator grant
comes from ``noctusai_lib.domain.permissions``.
"""

from __future__ import annotations

from typing import Any

from noctusai_lib.domain.permissions import PermissionGrantRepository
from noctusai_lib.domain.photo_editing.learning import Actor
from noctusai_lib.domain.photo_editing.pipeline import ECONOMICO_IMPLEMENTED
from noctusai_lib.domain.photo_editing.types import (
    CORRETOR_ROLES,
    PHOTO_CURATOR_PERMISSION,
    OrgSettings,
)
from noctusai_lib.integrations.image_edit import capabilities_for_model


async def compute_capabilities(
    *,
    actor: Actor,
    settings: OrgSettings | None,
    grants: PermissionGrantRepository,
) -> dict[str, Any]:
    settings = settings or OrgSettings(org_id=actor.org_id or "")
    is_curator = await grants.has_permission(
        user_id=actor.user_id, permission=PHOTO_CURATOR_PERMISSION
    )
    admin = actor.is_platform_admin
    agency_admin = actor.is_agency_admin
    member = agency_admin or actor.org_role in CORRETOR_ROLES
    model = settings.modelo_editor_id
    if not model:
        economico, motivo = False, "sem_modelo"
    elif not capabilities_for_model(model).supports_batch:
        economico, motivo = False, "modelo_sem_batch"
    elif not ECONOMICO_IMPLEMENTED:
        economico, motivo = False, "nao_implementado"
    else:
        economico, motivo = True, None
    tipos = list(t.value for t in settings.tipos_edicao_ativos)
    return {
        "pode_criar_lote": (admin or member) and bool(model) and bool(tipos),
        "pode_ver_veredito": admin or agency_admin,
        "pode_gerir_pool": admin or is_curator,
        "pode_aprovar_regras": admin or agency_admin,
        "pode_ativar_guia": admin or is_curator,
        "dashboard": "plataforma" if admin else ("org" if agency_admin else None),
        "modelo_configurado": bool(model),
        "economico_disponivel": economico,
        "economico_bloqueado_motivo": motivo,
        "tipos_edicao_ativos": tipos,
        "limites": {
            "fotos_por_lote": settings.limite_fotos_por_lote,
            "bytes_por_foto": settings.limite_bytes_por_foto,
        },
    }


__all__ = ["compute_capabilities"]
