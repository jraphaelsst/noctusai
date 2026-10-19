"""Julia > Início "Painel" (wave 9).

  GET /api/julia/painel?mes=YYYY-MM     org member -> {data: {atividades, funil, por_canal, status_por_canal,
                                       por_hora, fora_horario_pct, por_dia_semana, melhor_dia, seis_meses}}

`mes` defaults to the current month (America/Sao_Paulo); a malformed one is 422 `mes_invalido`. A member sees
the numbers of their own contatos only (A7); admins the whole org. `atividades.consumo` is null when agents
is unconfigured/unreachable (and for members). `melhor_dia` / `por_dia_semana` index 0 = segunda ... 6 = domingo.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request

from app.dependencies import coerce_org_uuid, get_current_user_org, get_scoped_admin_client
from app.routers.julia_agente_router import get_agents_client_factory
from app.services import julia_acesso, julia_painel_service as svc

router = APIRouter(prefix="/api/julia/painel", tags=["julia-painel"])


def get_painel_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


@router.get("")
async def painel(
    mes: Optional[str] = None,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_painel_client),
    client_factory=Depends(get_agents_client_factory),
) -> dict[str, Any]:
    mes = svc.validar_mes(mes)
    ctx = julia_acesso.contexto(auth, request)
    agents = client_factory(coerce_org_uuid(auth[2])) if ctx.admin else None
    return {"data": await svc.painel(client, ctx, mes=mes, client_agents=agents)}
