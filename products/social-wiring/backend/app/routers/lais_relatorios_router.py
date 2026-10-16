"""Lais > Relatorios (wave 10, contract section 12).

  GET /api/lais/relatorios?operacao=compra|aluguel&mes=YYYY-MM&aba=imoveis|bairros[&bairro=]
      org member (A7: a member's numbers cover only the contatos they own; admins/owners the org).
      bad operacao / mes / aba -> 422 `operacao_invalida` / `mes_invalido` / `aba_invalida`.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request

from app.dependencies import get_current_user_org, get_scoped_admin_client
from app.services import lais_acesso, lais_relatorios_service as svc

router = APIRouter(prefix="/api/lais/relatorios", tags=["lais-relatorios"])


def get_relatorios_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


@router.get("")
def obter(
    operacao: str = "compra",
    mes: Optional[str] = None,
    aba: str = "imoveis",
    bairro: Optional[str] = None,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_relatorios_client),
) -> dict[str, Any]:
    ctx = lais_acesso.contexto(auth, request)
    return {"data": svc.relatorio(client, ctx, operacao=operacao, mes=mes or svc.mes_atual(), aba=aba, bairro=bairro)}
