"""`/api/proveniencia/registro` — a SEPARATE router, deliberately (same
reasoning as `card_hub/router.py`'s own `defaults_router` on
`/api/negociacao`): this is a static catalog, not a cliente resource, so it
gets its own prefix rather than a literal segment under `/api/clientes`
that would need the same collision bookkeeping `/tags` already needs.

The per-contract lineage route (`GET /api/clientes/{cliente_id}/contratos/
{contrato_id}/proveniencia`) stays under `/api/clientes` instead, next to
its sibling `.../validacao-extracao` — see `contrato_gerador/router.py`.

Auth is asserted strictly (`== 401`) in
`tests/modules/card_hub/test_auth_boundary_proveniencia.py`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user_org
from app.modules.card_hub.proveniencia import linhagem

router = APIRouter(prefix="/api/proveniencia", tags=["proveniencia"])


@router.get("/registro")
async def get_proveniencia_registro_route(auth=Depends(get_current_user_org)) -> dict:
    """Static JSON of `fontes.FONTES` + `fontes.MANUAL_APENAS`, reshaped for
    the FE's upload-channel hints — no org-scoped data, same answer for
    every caller; `auth` is required anyway (this catalog names internal
    document-type vocabulary, not something to leak anonymously)."""
    return linhagem.linhagem_do_registro()


__all__ = ["router"]
