"""
Recorrência Router — Recurring transaction automation endpoints.

Provides endpoints to trigger monthly rent generation, recurring entries,
and overdue payment detection.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header
from app.dependencies import get_current_user, get_user_client, get_org_id, log_action
from app.services.recorrencia_service import RecorrenciaService
from app.responses import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recorrencia", tags=["recorrencia"])


@router.post("/alugueis")
async def gerar_alugueis(
    referencia: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    """Generate monthly rent charges for active lease contracts."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    org_id = get_org_id(user)

    service = RecorrenciaService(db, org_id)
    result = service.gerar_alugueis_mes(referencia)

    log_action(user.id, "gerar_alugueis", "recorrencia",
               descricao=f"Aluguéis gerados: {result['gerados']} para {result['referencia']}")

    return success_response(result)


@router.post("/lancamentos")
async def gerar_lancamentos_recorrentes(
    authorization: Optional[str] = Header(None),
):
    """Process all recurring financial entries for current month."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    org_id = get_org_id(user)

    service = RecorrenciaService(db, org_id)
    result = service.gerar_lancamentos_recorrentes()

    log_action(user.id, "gerar_recorrentes", "recorrencia",
               descricao=f"Lançamentos recorrentes: {result['gerados']}")

    return success_response(result)


@router.post("/inadimplencia")
async def verificar_inadimplencia(
    authorization: Optional[str] = Header(None),
):
    """Check and mark overdue payments."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    org_id = get_org_id(user)

    service = RecorrenciaService(db, org_id)
    result = service.verificar_inadimplencia()

    log_action(user.id, "verificar_inadimplencia", "recorrencia",
               descricao=f"Inadimplência: {result['total_atualizados']} atualizados")

    return success_response(result)
