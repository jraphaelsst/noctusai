"""`GET /api/guia-documentos` — its own prefix, like `proveniencia_router`:
a catalog, not a cliente resource. Returns the BARE `GuiaDocumentos` payload
(no envelope). Authenticated and org-scoped: the only org data read is the
org's own stage labels/order and block configuration (presentation of the
lead flow); everything else is derived from code catalogs —
see `guia_documentos_service`.

Auth is asserted strictly (`== 401`) in
`tests/modules/card_hub/test_guia_documentos.py`.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user_org
from app.modules.atendimento_blocos import repository as blocos_repo
from app.modules.card_hub import guia_documentos_service as svc
from app.modules.card_hub.auth import auth_parts
from app.modules.card_hub.deps import get_card_hub_client

router = APIRouter(prefix="/api/guia-documentos", tags=["guia-documentos"])


@router.get("")
def get_guia_documentos_route(
    auth=Depends(get_current_user_org),
    client: Any = Depends(get_card_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    rotulos, etapas = svc.etapas_da_org(blocos_repo.etapas_da_org(client, org_id))
    return svc.montar_guia(
        rotulos_etapa=rotulos,
        config_blocos=blocos_repo.configuracao_efetiva(client, org_id),
        etapas_org=etapas,
    )


__all__ = ["router"]
